import discord
from discord import app_commands
from discord.ui import View, Select, Button, Modal, TextInput
from discord.ext import commands
from typing import Optional, Literal, List, Union
import asyncpg
import os
from dotenv import load_dotenv
import logging
import asyncio
import traceback
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta, time
from .ratelimiter import RateLimiter, RateLimitType, rate_limited, get_rate_limiter

# CONFIGURATION

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent

# Weekday mapping
WEEKDAY_MAP = {
    'monday': 0, 'mon': 0,
    'tuesday': 1, 'tue': 1,
    'wednesday': 2, 'wed': 2,
    'thursday': 3, 'thu': 3,
    'friday': 4, 'fri': 4,
    'saturday': 5, 'sat': 5,
    'sunday': 6, 'sun': 6
}


class DatabaseManager:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def ensure_tables_exist(self, guild_id: int):
        """Check if required tables exist."""
        async with self.pool.acquire() as conn:
            tables = await conn.fetch("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            table_names = [t['table_name'] for t in tables]

            required_tables = [
                'message_tracking_hourly',
                'voice_session_history_hourly',
                'emoji_usage_hourly',
                'user_mentions_hourly',
                'invite_tracking',
                'activity_sessions_hourly',
                'daily_activity_log',
                'activity_streaks',
                'role_growth_hourly',
                'member_joins_hourly',
                'member_leaves_hourly'
            ]

            missing_tables = [
                t for t in required_tables if t not in table_names]
            if missing_tables:
                logger.warning(f"Missing tables: {missing_tables}")
                return False
            return True

    # ======================================================================
    # HELPER METHODS
    # ======================================================================

    def parse_weekday_input(self, weekday_str: str) -> Optional[int]:
        """Convert weekday name to number (0=Monday to 6=Sunday)"""
        if weekday_str is None:
            return None
        weekday_lower = weekday_str.lower().strip()
        return WEEKDAY_MAP.get(weekday_lower)

    def parse_weekdays_input(self, weekdays_str: str) -> List[int]:
        """Parse comma-separated weekday names to list of numbers"""
        if not weekdays_str:
            return []
        result = []
        for part in weekdays_str.split(','):
            day_num = self.parse_weekday_input(part.strip())
            if day_num is not None:
                result.append(day_num)
        return sorted(set(result))

    def parse_times_input(self, times_str: str) -> List[str]:
        """Parse comma-separated times to list"""
        if not times_str:
            return []
        result = []
        for part in times_str.split(','):
            time_part = part.strip()
            if re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', time_part):
                result.append(time_part)
        return sorted(set(result))

    def parse_date_input(self, date_str: str) -> Optional[datetime]:
        """Parse date string in DD-MM-YYYY, DD/MM/YYYY, or DD.MM.YYYY format"""
        if not date_str:
            return None

        cleaned = date_str.strip().replace('/', '-').replace('.', '-')
        cleaned = re.sub(r'\s+', '', cleaned)

        parts = cleaned.split('-')
        if len(parts) != 3:
            return None

        try:
            day = int(parts[0])
            month = int(parts[1])
            year = int(parts[2])

            if day < 1 or day > 31 or month < 1 or month > 12 or year < 2000 or year > 2100:
                return None

            return datetime(year, month, day, 0, 0, 0, tzinfo=timezone.utc)
        except ValueError:
            return None

    def _calculate_next_recurrence(self, pattern: str, weekdays: Optional[Union[int, List[int]]] = None,
                                   days_of_month: Optional[Union[int,
                                                                 List[int]]] = None,
                                   times: Optional[Union[str,
                                                         List[str]]] = None,
                                   interval_days: Optional[int] = None) -> datetime:
        """Calculate the next execution time for recurring schedules"""
        now = datetime.now(timezone.utc)

        if weekdays is not None and not isinstance(weekdays, list):
            weekdays = [weekdays]
        if days_of_month is not None and not isinstance(days_of_month, list):
            days_of_month = [days_of_month]
        if times is not None and not isinstance(times, list):
            times = [times]

        if not times:
            times = ["00:00"]

        candidates = []

        for time_str in times:
            parts = time_str.split(':')
            target_hour = int(parts[0])
            target_minute = int(parts[1]) if len(parts) > 1 else 0
            target_second = int(parts[2]) if len(parts) > 2 else 0

            if pattern == 'daily':
                next_time = now.replace(hour=target_hour, minute=target_minute,
                                        second=target_second, microsecond=0)
                if next_time <= now:
                    next_time += timedelta(days=1)
                candidates.append(next_time)

            elif pattern == 'weekly' and weekdays:
                current_weekday = now.weekday()
                for weekday in weekdays:
                    days_ahead = weekday - current_weekday
                    if days_ahead <= 0:
                        days_ahead += 7
                    next_time = now + timedelta(days=days_ahead)
                    next_time = next_time.replace(hour=target_hour, minute=target_minute,
                                                  second=target_second, microsecond=0)
                    candidates.append(next_time)

            elif pattern == 'weekday' and weekdays:
                valid_weekdays = [d for d in weekdays if d < 5]
                if valid_weekdays:
                    current_weekday = now.weekday()
                    for weekday in valid_weekdays:
                        days_ahead = weekday - current_weekday
                        if days_ahead <= 0:
                            days_ahead += 7
                        next_time = now + timedelta(days=days_ahead)
                        next_time = next_time.replace(hour=target_hour, minute=target_minute,
                                                      second=target_second, microsecond=0)
                        candidates.append(next_time)

            elif pattern == 'monthly' and days_of_month:
                year = now.year
                month = now.month

                for day in days_of_month:
                    if month == 12:
                        last_day = 31
                    else:
                        last_day = (datetime(year, month + 1, 1) -
                                    timedelta(days=1)).day
                    target_day = min(day, last_day)

                    next_time = datetime(year, month, target_day, target_hour, target_minute,
                                         target_second, tzinfo=timezone.utc)
                    if next_time <= now:
                        if month == 12:
                            next_time = datetime(year + 1, 1, target_day, target_hour, target_minute,
                                                 target_second, tzinfo=timezone.utc)
                        else:
                            next_time = datetime(year, month + 1, target_day, target_hour, target_minute,
                                                 target_second, tzinfo=timezone.utc)
                    candidates.append(next_time)

            elif pattern == 'custom_days' and interval_days:
                next_time = now.replace(hour=target_hour, minute=target_minute,
                                        second=target_second, microsecond=0)
                if next_time <= now:
                    next_time += timedelta(days=interval_days)
                candidates.append(next_time)

        return min(candidates) if candidates else now + timedelta(days=1)

    # ======================================================================
    # SCHEDULED RESET METHODS
    # ======================================================================

    async def create_advanced_reset_schedule(self, guild_id: int, requested_by_id: int,
                                             reset_types: List[str],
                                             schedule_type: str,
                                             target_time: Optional[datetime] = None,
                                             recurring_pattern: Optional[str] = None,
                                             recurring_weekdays: Optional[List[int]] = None,
                                             recurring_days_of_month: Optional[List[int]] = None,
                                             recurring_times: Optional[List[str]] = None,
                                             recurring_interval_days: Optional[int] = None,
                                             delete_from_date: Optional[datetime] = None,
                                             delete_to_date: Optional[datetime] = None,
                                             time_period_days: Optional[int] = None,
                                             scope_type: Optional[str] = None,
                                             scope_details: Optional[str] = None,
                                             channel_id: Optional[int] = None,
                                             category_id: Optional[int] = None,
                                             schedule_name: Optional[str] = None,
                                             enabled: bool = True) -> int:
        """Create an advanced reset schedule with name and enabled status"""
        try:
            async with self.pool.acquire() as conn:
                time_objects = None
                if recurring_times:
                    time_objects = []
                    for time_str in recurring_times:
                        parts = time_str.split(':')
                        hour = int(parts[0])
                        minute = int(parts[1]) if len(parts) > 1 else 0
                        second = int(parts[2]) if len(parts) > 2 else 0
                        time_objects.append(
                            time(hour=hour, minute=minute, second=second))

                next_execution = None
                if schedule_type == "recurring" and recurring_pattern and enabled:
                    next_execution = self._calculate_next_recurrence(
                        recurring_pattern, recurring_weekdays, recurring_days_of_month,
                        recurring_times, recurring_interval_days
                    )
                elif schedule_type == "one_time" and target_time and enabled:
                    next_execution = target_time

                result = await conn.fetchrow("""
                    INSERT INTO reset_schedules (
                        guild_id, requested_by_id, reset_types, schedule_type,
                        target_time, recurring_pattern, recurring_weekdays, recurring_days_of_month,
                        recurring_times, recurring_interval_days, delete_from_date, delete_to_date,
                        time_period_days, scope_type, scope_details, channel_id, category_id,
                        next_execution_at, created_at, schedule_name, enabled
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, NOW(), $19, $20)
                    RETURNING id
                """,
                                             guild_id, requested_by_id, reset_types, schedule_type,
                                             target_time, recurring_pattern,
                                             recurring_weekdays, recurring_days_of_month,
                                             time_objects,
                                             recurring_interval_days, delete_from_date, delete_to_date,
                                             time_period_days, scope_type, scope_details, channel_id, category_id,
                                             next_execution, schedule_name, enabled
                                             )

                return result['id'] if result else None

        except Exception as e:
            logger.error(f"Failed to create advanced reset schedule: {e}")
            logger.error(traceback.format_exc())
            raise

    async def get_all_schedules_for_guild(self, guild_id: int) -> List[dict]:
        """Get ALL schedules for a guild (both enabled and disabled) for display"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT id, guild_id, requested_by_id, target_time, reset_types,
                           schedule_type, recurring_pattern, recurring_weekdays, recurring_days_of_month,
                           recurring_times, recurring_interval_days, next_execution_at, time_period_days,
                           scope_type, scope_details, channel_id, category_id,
                           delete_from_date, delete_to_date, schedule_name, enabled,
                           completed, created_at
                    FROM reset_schedules
                    WHERE guild_id = $1 AND completed = FALSE
                    ORDER BY created_at DESC
                """, guild_id)

                return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get schedules for guild {guild_id}: {e}")
            logger.error(traceback.format_exc())
            return []

    async def get_pending_reset_schedules(self, lookahead_hours: int = 12) -> List[dict]:
        """Get all pending reset schedules within the next X hours (only enabled ones)"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT id, guild_id, requested_by_id, target_time, reset_types,
                           schedule_type, recurring_pattern, recurring_weekdays, recurring_days_of_month,
                           recurring_times, recurring_interval_days, next_execution_at, time_period_days,
                           scope_type, scope_details, channel_id, category_id,
                           delete_from_date, delete_to_date, schedule_name, enabled
                    FROM reset_schedules
                    WHERE completed = FALSE 
                    AND enabled = TRUE
                    AND (next_execution_at <= NOW() + make_interval(hours => $1) OR schedule_type = 'date_range')
                    ORDER BY next_execution_at ASC NULLS LAST
                """, lookahead_hours)

                return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get pending reset schedules: {e}")
            logger.error(traceback.format_exc())
            return []

    async def get_due_reset_schedules(self) -> List[dict]:
        """Get all reset schedules that are due for execution (only enabled ones)"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT id, guild_id, requested_by_id, reset_types,
                           schedule_type, recurring_pattern, recurring_weekdays, recurring_days_of_month,
                           recurring_times, recurring_interval_days, time_period_days,
                           scope_type, scope_details, channel_id, category_id,
                           delete_from_date, delete_to_date, schedule_name, enabled
                    FROM reset_schedules
                    WHERE completed = FALSE 
                    AND enabled = TRUE
                    AND schedule_type != 'date_range'
                    AND next_execution_at <= NOW()
                    ORDER BY next_execution_at ASC
                """)

                return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get due reset schedules: {e}")
            logger.error(traceback.format_exc())
            return []

    async def mark_schedule_completed(self, schedule_id: int, executed_at: datetime = None):
        """Mark a reset schedule as completed and update next execution for recurring schedules"""
        try:
            if executed_at is None:
                executed_at = datetime.now(timezone.utc)

            async with self.pool.acquire() as conn:
                schedule = await conn.fetchrow("""
                    SELECT schedule_type, recurring_pattern, recurring_weekdays, recurring_days_of_month,
                           recurring_times, recurring_interval_days, failure_count, enabled
                    FROM reset_schedules
                    WHERE id = $1
                """, schedule_id)

                if schedule and schedule['schedule_type'] == 'recurring' and schedule['enabled']:
                    next_execution = self._calculate_next_recurrence(
                        schedule['recurring_pattern'],
                        schedule['recurring_weekdays'],
                        schedule['recurring_days_of_month'],
                        schedule['recurring_times'],
                        schedule['recurring_interval_days']
                    )

                    await conn.execute("""
                        UPDATE reset_schedules 
                        SET last_executed_at = $2, next_execution_at = $3, failure_count = 0, last_error = NULL
                        WHERE id = $1
                    """, schedule_id, executed_at, next_execution)
                else:
                    await conn.execute("""
                        UPDATE reset_schedules 
                        SET completed = TRUE, executed_at = $2
                        WHERE id = $1
                    """, schedule_id, executed_at)

                logger.info(f"Updated schedule {schedule_id}")

        except Exception as e:
            logger.error(f"Failed to mark schedule {schedule_id}: {e}")
            logger.error(traceback.format_exc())
            raise

    async def execute_scheduled_reset(self, schedule: dict) -> dict:
        """Execute a scheduled reset based on schedule data"""
        try:
            guild_id = schedule['guild_id']
            reset_types = schedule['reset_types']

            results = {}

            channel_id = schedule.get('channel_id')
            category_id = schedule.get('category_id')
            time_period_days = schedule.get('time_period_days')
            delete_from_date = schedule.get('delete_from_date')
            delete_to_date = schedule.get('delete_to_date')

            for reset_type in reset_types:
                try:
                    result = await self.reset_server_stats(
                        guild_id=guild_id,
                        stat_type=reset_type,
                        channel_id=channel_id,
                        category_id=category_id,
                        time_period_days=time_period_days,
                        delete_from_date=delete_from_date,
                        delete_to_date=delete_to_date
                    )
                    results[reset_type] = result
                except Exception as e:
                    logger.error(
                        f"Failed to execute scheduled reset for type {reset_type}: {e}")
                    results[reset_type] = {'error': str(e)}

            return results

        except Exception as e:
            logger.error(f"Failed to execute scheduled reset: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_schedule(self, schedule_id: int, guild_id: int) -> bool:
        """Delete a schedule instantly"""
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute("""
                    DELETE FROM reset_schedules 
                    WHERE id = $1 AND guild_id = $2
                """, schedule_id, guild_id)

                return result.split()[-1] == '1'
        except Exception as e:
            logger.error(f"Failed to delete schedule {schedule_id}: {e}")
            return False

    # ======================================================================
    # SERVER DELETION LOGIC
    # ======================================================================

    async def delete_server_all(self, guild_id: int,
                                channel_id: Optional[int] = None,
                                category_id: Optional[int] = None,
                                time_period_days: Optional[int] = None,
                                delete_from_date: Optional[datetime] = None,
                                delete_to_date: Optional[datetime] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    conditions = ["guild_id = $1"]
                    params = [guild_id]
                    param_counter = 2

                    if channel_id:
                        conditions.append(f"channel_id = ${param_counter}")
                        params.append(channel_id)
                        param_counter += 1

                    if category_id:
                        conditions.append(f"category_id = ${param_counter}")
                        params.append(category_id)
                        param_counter += 1

                    if time_period_days:
                        conditions.append(
                            f"hour >= NOW() - INTERVAL '{time_period_days} days'")
                        conditions.append(
                            f"day >= NOW() - INTERVAL '{time_period_days} days'")

                    if delete_from_date:
                        conditions.append(f"hour >= ${param_counter}")
                        params.append(delete_from_date)
                        param_counter += 1
                        conditions.append(f"day >= ${param_counter}")
                        params.append(delete_from_date)
                        param_counter += 1

                    if delete_to_date:
                        conditions.append(f"hour <= ${param_counter}")
                        params.append(delete_to_date)
                        param_counter += 1
                        conditions.append(f"day <= ${param_counter}")
                        params.append(delete_to_date)
                        param_counter += 1

                    where_clause = " AND ".join(conditions)

                    tables_with_channel_category = [
                        'message_tracking_hourly',
                        'voice_session_history_hourly',
                        'emoji_usage_hourly',
                        'user_mentions_hourly'
                    ]

                    deleted_counts = {}

                    for table in tables_with_channel_category:
                        try:
                            result = await conn.execute(f"DELETE FROM {table} WHERE {where_clause}", *params)
                            deleted_counts[table] = result.split()[-1]
                        except Exception as e:
                            logger.warning(f"Error deleting from {table}: {e}")
                            deleted_counts[table] = "0 (error)"

                    if not channel_id and not category_id:
                        server_tables = [
                            'invite_tracking',
                            'activity_sessions_hourly',
                            'daily_activity_log',
                            'activity_streaks',
                            'role_growth_hourly',
                            'member_joins_hourly',
                            'member_leaves_hourly'
                        ]

                        for table in server_tables:
                            try:
                                if time_period_days:
                                    if table in ['daily_activity_log']:
                                        await conn.execute(f"DELETE FROM {table} WHERE guild_id = $1 AND day >= NOW() - INTERVAL '{time_period_days} days'", guild_id)
                                    else:
                                        result = await conn.execute(f"DELETE FROM {table} WHERE guild_id = $1", guild_id)
                                else:
                                    result = await conn.execute(f"DELETE FROM {table} WHERE guild_id = $1", guild_id)
                                deleted_counts[table] = result.split(
                                )[-1] if not time_period_days else "deleted"
                            except Exception as e:
                                logger.warning(
                                    f"Error deleting from {table}: {e}")
                                deleted_counts[table] = "0 (error)"

                    return deleted_counts

        except Exception as e:
            logger.error(f"Error in delete_server_all: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_server_messages(self, guild_id: int,
                                     channel_id: Optional[int] = None,
                                     category_id: Optional[int] = None,
                                     time_period_days: Optional[int] = None,
                                     delete_from_date: Optional[datetime] = None,
                                     delete_to_date: Optional[datetime] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    conditions = ["guild_id = $1"]
                    params = [guild_id]
                    param_counter = 2

                    if channel_id:
                        conditions.append(f"channel_id = ${param_counter}")
                        params.append(channel_id)
                        param_counter += 1

                    if category_id:
                        conditions.append(f"category_id = ${param_counter}")
                        params.append(category_id)
                        param_counter += 1

                    if time_period_days:
                        conditions.append(
                            f"hour >= NOW() - INTERVAL '{time_period_days} days'")

                    if delete_from_date:
                        conditions.append(f"hour >= ${param_counter}")
                        params.append(delete_from_date)
                        param_counter += 1

                    if delete_to_date:
                        conditions.append(f"hour <= ${param_counter}")
                        params.append(delete_to_date)
                        param_counter += 1

                    where_clause = " AND ".join(conditions)
                    result = await conn.execute(f"DELETE FROM message_tracking_hourly WHERE {where_clause}", *params)
                    deleted_count = result.split()[-1]
                    return int(deleted_count) if deleted_count.isdigit() else 0

        except Exception as e:
            logger.error(f"Error in delete_server_messages: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_server_voice(self, guild_id: int,
                                  channel_id: Optional[int] = None,
                                  category_id: Optional[int] = None,
                                  time_period_days: Optional[int] = None,
                                  delete_from_date: Optional[datetime] = None,
                                  delete_to_date: Optional[datetime] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    conditions = ["guild_id = $1"]
                    params = [guild_id]
                    param_counter = 2

                    if channel_id:
                        conditions.append(f"channel_id = ${param_counter}")
                        params.append(channel_id)
                        param_counter += 1

                    if category_id:
                        conditions.append(f"category_id = ${param_counter}")
                        params.append(category_id)
                        param_counter += 1

                    if time_period_days:
                        conditions.append(
                            f"hour >= NOW() - INTERVAL '{time_period_days} days'")

                    if delete_from_date:
                        conditions.append(f"hour >= ${param_counter}")
                        params.append(delete_from_date)
                        param_counter += 1

                    if delete_to_date:
                        conditions.append(f"hour <= ${param_counter}")
                        params.append(delete_to_date)
                        param_counter += 1

                    where_clause = " AND ".join(conditions)

                    deleted_counts = {}
                    result1 = await conn.execute(f"DELETE FROM voice_session_history_hourly WHERE {where_clause}", *params)
                    deleted_counts['voice_session_history_hourly'] = result1.split(
                    )[-1]
                    return deleted_counts

        except Exception as e:
            logger.error(f"Error in delete_server_voice: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_server_invites(self, guild_id: int, time_period_days: Optional[int] = None,
                                    delete_from_date: Optional[datetime] = None,
                                    delete_to_date: Optional[datetime] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    if time_period_days:
                        result = await conn.execute(f"DELETE FROM invite_tracking WHERE guild_id = $1 AND created_at >= NOW() - INTERVAL '{time_period_days} days'", guild_id)
                    elif delete_from_date or delete_to_date:
                        conditions = ["guild_id = $1"]
                        params = [guild_id]
                        param_counter = 2
                        if delete_from_date:
                            conditions.append(
                                f"created_at >= ${param_counter}")
                            params.append(delete_from_date)
                            param_counter += 1
                        if delete_to_date:
                            conditions.append(
                                f"created_at <= ${param_counter}")
                            params.append(delete_to_date)
                            param_counter += 1
                        where_clause = " AND ".join(conditions)
                        result = await conn.execute(f"DELETE FROM invite_tracking WHERE {where_clause}", *params)
                    else:
                        result = await conn.execute(f"DELETE FROM invite_tracking WHERE guild_id = $1", guild_id)
                    deleted_count = result.split()[-1]
                    return int(deleted_count) if deleted_count.isdigit() else 0

        except Exception as e:
            logger.error(f"Error in delete_server_invites: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_server_emoji(self, guild_id: int,
                                  channel_id: Optional[int] = None,
                                  category_id: Optional[int] = None,
                                  time_period_days: Optional[int] = None,
                                  delete_from_date: Optional[datetime] = None,
                                  delete_to_date: Optional[datetime] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    conditions = ["guild_id = $1"]
                    params = [guild_id]
                    param_counter = 2

                    if channel_id:
                        conditions.append(f"channel_id = ${param_counter}")
                        params.append(channel_id)
                        param_counter += 1

                    if category_id:
                        conditions.append(f"category_id = ${param_counter}")
                        params.append(category_id)
                        param_counter += 1

                    if time_period_days:
                        conditions.append(
                            f"hour >= NOW() - INTERVAL '{time_period_days} days'")

                    if delete_from_date:
                        conditions.append(f"hour >= ${param_counter}")
                        params.append(delete_from_date)
                        param_counter += 1

                    if delete_to_date:
                        conditions.append(f"hour <= ${param_counter}")
                        params.append(delete_to_date)
                        param_counter += 1

                    where_clause = " AND ".join(conditions)
                    result = await conn.execute(f"DELETE FROM emoji_usage_hourly WHERE {where_clause}", *params)
                    deleted_count = result.split()[-1]
                    return int(deleted_count) if deleted_count.isdigit() else 0

        except Exception as e:
            logger.error(f"Error in delete_server_emoji: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_server_activity(self, guild_id: int, time_period_days: Optional[int] = None,
                                     delete_from_date: Optional[datetime] = None,
                                     delete_to_date: Optional[datetime] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    deleted_counts = {}

                    if time_period_days:
                        result1 = await conn.execute(f"DELETE FROM activity_sessions_hourly WHERE guild_id = $1 AND hour >= NOW() - INTERVAL '{time_period_days} days'", guild_id)
                        result2 = await conn.execute(f"DELETE FROM daily_activity_log WHERE guild_id = $1 AND day >= NOW() - INTERVAL '{time_period_days} days'", guild_id)
                        result3 = await conn.execute(f"DELETE FROM activity_streaks WHERE guild_id = $1", guild_id)
                    elif delete_from_date or delete_to_date:
                        conditions = ["guild_id = $1"]
                        params = [guild_id]
                        param_counter = 2
                        if delete_from_date:
                            conditions.append(f"hour >= ${param_counter}")
                            params.append(delete_from_date)
                            param_counter += 1
                            conditions.append(f"day >= ${param_counter}")
                            params.append(delete_from_date)
                            param_counter += 1
                        if delete_to_date:
                            conditions.append(f"hour <= ${param_counter}")
                            params.append(delete_to_date)
                            param_counter += 1
                            conditions.append(f"day <= ${param_counter}")
                            params.append(delete_to_date)
                            param_counter += 1
                        where_clause = " AND ".join(conditions)
                        result1 = await conn.execute(f"DELETE FROM activity_sessions_hourly WHERE {where_clause}", *params)
                        result2 = await conn.execute(f"DELETE FROM daily_activity_log WHERE {where_clause}", *params)
                        result3 = await conn.execute(f"DELETE FROM activity_streaks WHERE guild_id = $1", guild_id)
                    else:
                        result1 = await conn.execute(f"DELETE FROM activity_sessions_hourly WHERE guild_id = $1", guild_id)
                        result2 = await conn.execute(f"DELETE FROM daily_activity_log WHERE guild_id = $1", guild_id)
                        result3 = await conn.execute(f"DELETE FROM activity_streaks WHERE guild_id = $1", guild_id)

                    deleted_counts['activity_sessions_hourly'] = result1.split(
                    )[-1]
                    deleted_counts['daily_activity_log'] = result2.split()[-1]
                    deleted_counts['activity_streaks'] = result3.split()[-1]
                    return deleted_counts

        except Exception as e:
            logger.error(f"Error in delete_server_activity: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_server_mentions(self, guild_id: int,
                                     channel_id: Optional[int] = None,
                                     category_id: Optional[int] = None,
                                     time_period_days: Optional[int] = None,
                                     delete_from_date: Optional[datetime] = None,
                                     delete_to_date: Optional[datetime] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    conditions = ["guild_id = $1"]
                    params = [guild_id]
                    param_counter = 2

                    if channel_id:
                        conditions.append(f"channel_id = ${param_counter}")
                        params.append(channel_id)
                        param_counter += 1

                    if category_id:
                        conditions.append(f"category_id = ${param_counter}")
                        params.append(category_id)
                        param_counter += 1

                    if time_period_days:
                        conditions.append(
                            f"hour >= NOW() - INTERVAL '{time_period_days} days'")

                    if delete_from_date:
                        conditions.append(f"hour >= ${param_counter}")
                        params.append(delete_from_date)
                        param_counter += 1

                    if delete_to_date:
                        conditions.append(f"hour <= ${param_counter}")
                        params.append(delete_to_date)
                        param_counter += 1

                    where_clause = " AND ".join(conditions)
                    result = await conn.execute(f"DELETE FROM user_mentions_hourly WHERE {where_clause}", *params)
                    deleted_count = result.split()[-1]
                    return int(deleted_count) if deleted_count.isdigit() else 0

        except Exception as e:
            logger.error(f"Error in delete_server_mentions: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_server_role_growth(self, guild_id: int, time_period_days: Optional[int] = None,
                                        delete_from_date: Optional[datetime] = None,
                                        delete_to_date: Optional[datetime] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    if time_period_days:
                        result = await conn.execute(f"DELETE FROM role_growth_hourly WHERE guild_id = $1 AND hour >= NOW() - INTERVAL '{time_period_days} days'", guild_id)
                    elif delete_from_date or delete_to_date:
                        conditions = ["guild_id = $1"]
                        params = [guild_id]
                        param_counter = 2
                        if delete_from_date:
                            conditions.append(f"hour >= ${param_counter}")
                            params.append(delete_from_date)
                            param_counter += 1
                        if delete_to_date:
                            conditions.append(f"hour <= ${param_counter}")
                            params.append(delete_to_date)
                            param_counter += 1
                        where_clause = " AND ".join(conditions)
                        result = await conn.execute(f"DELETE FROM role_growth_hourly WHERE {where_clause}", *params)
                    else:
                        result = await conn.execute(f"DELETE FROM role_growth_hourly WHERE guild_id = $1", guild_id)
                    deleted_count = result.split()[-1]
                    return int(deleted_count) if deleted_count.isdigit() else 0

        except Exception as e:
            logger.error(f"Error in delete_server_role_growth: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_server_member_growth(self, guild_id: int, time_period_days: Optional[int] = None,
                                          delete_from_date: Optional[datetime] = None,
                                          delete_to_date: Optional[datetime] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    deleted_counts = {}

                    if time_period_days:
                        result1 = await conn.execute(f"DELETE FROM member_joins_hourly WHERE guild_id = $1 AND hour >= NOW() - INTERVAL '{time_period_days} days'", guild_id)
                        result2 = await conn.execute(f"DELETE FROM member_leaves_hourly WHERE guild_id = $1 AND hour >= NOW() - INTERVAL '{time_period_days} days'", guild_id)
                    elif delete_from_date or delete_to_date:
                        conditions = ["guild_id = $1"]
                        params = [guild_id]
                        param_counter = 2
                        if delete_from_date:
                            conditions.append(f"hour >= ${param_counter}")
                            params.append(delete_from_date)
                            param_counter += 1
                        if delete_to_date:
                            conditions.append(f"hour <= ${param_counter}")
                            params.append(delete_to_date)
                            param_counter += 1
                        where_clause = " AND ".join(conditions)
                        result1 = await conn.execute(f"DELETE FROM member_joins_hourly WHERE {where_clause}", *params)
                        result2 = await conn.execute(f"DELETE FROM member_leaves_hourly WHERE {where_clause}", *params)
                    else:
                        result1 = await conn.execute(f"DELETE FROM member_joins_hourly WHERE guild_id = $1", guild_id)
                        result2 = await conn.execute(f"DELETE FROM member_leaves_hourly WHERE guild_id = $1", guild_id)

                    deleted_counts['member_joins_hourly'] = result1.split()[-1]
                    deleted_counts['member_leaves_hourly'] = result2.split()[-1]
                    return deleted_counts

        except Exception as e:
            logger.error(f"Error in delete_server_member_growth: {e}")
            logger.error(traceback.format_exc())
            raise

    # ======================================================================
    # USER DELETION LOGIC
    # ======================================================================

    async def delete_user_all(self, guild_id: int, user_id: int,
                              channel_id: Optional[int] = None,
                              category_id: Optional[int] = None,
                              time_period_days: Optional[int] = None,
                              delete_from_date: Optional[datetime] = None,
                              delete_to_date: Optional[datetime] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    conditions = ["guild_id = $1", "user_id = $2"]
                    params = [guild_id, user_id]
                    param_counter = 3

                    if channel_id:
                        conditions.append(f"channel_id = ${param_counter}")
                        params.append(channel_id)
                        param_counter += 1

                    if category_id:
                        conditions.append(f"category_id = ${param_counter}")
                        params.append(category_id)
                        param_counter += 1

                    if time_period_days:
                        conditions.append(
                            f"hour >= NOW() - INTERVAL '{time_period_days} days'")
                        conditions.append(
                            f"day >= NOW() - INTERVAL '{time_period_days} days'")

                    if delete_from_date:
                        conditions.append(f"hour >= ${param_counter}")
                        params.append(delete_from_date)
                        param_counter += 1
                        conditions.append(f"day >= ${param_counter}")
                        params.append(delete_from_date)
                        param_counter += 1

                    if delete_to_date:
                        conditions.append(f"hour <= ${param_counter}")
                        params.append(delete_to_date)
                        param_counter += 1
                        conditions.append(f"day <= ${param_counter}")
                        params.append(delete_to_date)
                        param_counter += 1

                    where_clause = " AND ".join(conditions)

                    user_tables = [
                        'message_tracking_hourly',
                        'voice_session_history_hourly',
                        'emoji_usage_hourly',
                        'user_mentions_hourly'
                    ]

                    deleted_counts = {}

                    for table in user_tables:
                        try:
                            result = await conn.execute(f"DELETE FROM {table} WHERE {where_clause}", *params)
                            deleted_counts[table] = result.split()[-1]
                        except Exception as e:
                            logger.warning(f"Error deleting from {table}: {e}")
                            deleted_counts[table] = "0 (error)"

                    if not channel_id and not category_id:
                        user_only_tables = [
                            'invite_tracking',
                            'activity_sessions_hourly',
                            'daily_activity_log',
                            'activity_streaks',
                            'role_growth_hourly'
                        ]

                        for table in user_only_tables:
                            try:
                                if time_period_days:
                                    if table == 'daily_activity_log':
                                        await conn.execute(f"DELETE FROM {table} WHERE guild_id = $1 AND user_id = $2 AND day >= NOW() - INTERVAL '{time_period_days} days'", guild_id, user_id)
                                    else:
                                        result = await conn.execute(f"DELETE FROM {table} WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)
                                else:
                                    result = await conn.execute(f"DELETE FROM {table} WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)
                                deleted_counts[table] = result.split(
                                )[-1] if not time_period_days else "deleted"
                            except Exception as e:
                                logger.warning(
                                    f"Error deleting from {table}: {e}")
                                deleted_counts[table] = "0 (error)"

                    return deleted_counts

        except Exception as e:
            logger.error(f"Error in delete_user_all: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_user_messages(self, guild_id: int, user_id: int,
                                   channel_id: Optional[int] = None,
                                   category_id: Optional[int] = None,
                                   time_period_days: Optional[int] = None,
                                   delete_from_date: Optional[datetime] = None,
                                   delete_to_date: Optional[datetime] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    conditions = ["guild_id = $1", "user_id = $2"]
                    params = [guild_id, user_id]
                    param_counter = 3

                    if channel_id:
                        conditions.append(f"channel_id = ${param_counter}")
                        params.append(channel_id)
                        param_counter += 1

                    if category_id:
                        conditions.append(f"category_id = ${param_counter}")
                        params.append(category_id)
                        param_counter += 1

                    if time_period_days:
                        conditions.append(
                            f"hour >= NOW() - INTERVAL '{time_period_days} days'")

                    if delete_from_date:
                        conditions.append(f"hour >= ${param_counter}")
                        params.append(delete_from_date)
                        param_counter += 1

                    if delete_to_date:
                        conditions.append(f"hour <= ${param_counter}")
                        params.append(delete_to_date)
                        param_counter += 1

                    where_clause = " AND ".join(conditions)
                    result = await conn.execute(f"DELETE FROM message_tracking_hourly WHERE {where_clause}", *params)
                    deleted_count = result.split()[-1]
                    return int(deleted_count) if deleted_count.isdigit() else 0

        except Exception as e:
            logger.error(f"Error in delete_user_messages: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_user_voice(self, guild_id: int, user_id: int,
                                channel_id: Optional[int] = None,
                                category_id: Optional[int] = None,
                                time_period_days: Optional[int] = None,
                                delete_from_date: Optional[datetime] = None,
                                delete_to_date: Optional[datetime] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    conditions = ["guild_id = $1", "user_id = $2"]
                    params = [guild_id, user_id]
                    param_counter = 3

                    if channel_id:
                        conditions.append(f"channel_id = ${param_counter}")
                        params.append(channel_id)
                        param_counter += 1

                    if category_id:
                        conditions.append(f"category_id = ${param_counter}")
                        params.append(category_id)
                        param_counter += 1

                    if time_period_days:
                        conditions.append(
                            f"hour >= NOW() - INTERVAL '{time_period_days} days'")

                    if delete_from_date:
                        conditions.append(f"hour >= ${param_counter}")
                        params.append(delete_from_date)
                        param_counter += 1

                    if delete_to_date:
                        conditions.append(f"hour <= ${param_counter}")
                        params.append(delete_to_date)
                        param_counter += 1

                    where_clause = " AND ".join(conditions)
                    result = await conn.execute(f"DELETE FROM voice_session_history_hourly WHERE {where_clause}", *params)
                    deleted_count = result.split()[-1]
                    return int(deleted_count) if deleted_count.isdigit() else 0

        except Exception as e:
            logger.error(f"Error in delete_user_voice: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_user_invites(self, guild_id: int, user_id: int,
                                  time_period_days: Optional[int] = None,
                                  delete_from_date: Optional[datetime] = None,
                                  delete_to_date: Optional[datetime] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    if time_period_days:
                        result = await conn.execute(f"DELETE FROM invite_tracking WHERE guild_id = $1 AND (inviter_id = $2 OR invitee_id = $2) AND created_at >= NOW() - INTERVAL '{time_period_days} days'", guild_id, user_id)
                    elif delete_from_date or delete_to_date:
                        conditions = ["guild_id = $1",
                                      "(inviter_id = $2 OR invitee_id = $2)"]
                        params = [guild_id, user_id]
                        param_counter = 3
                        if delete_from_date:
                            conditions.append(
                                f"created_at >= ${param_counter}")
                            params.append(delete_from_date)
                            param_counter += 1
                        if delete_to_date:
                            conditions.append(
                                f"created_at <= ${param_counter}")
                            params.append(delete_to_date)
                            param_counter += 1
                        where_clause = " AND ".join(conditions)
                        result = await conn.execute(f"DELETE FROM invite_tracking WHERE {where_clause}", *params)
                    else:
                        result = await conn.execute(f"DELETE FROM invite_tracking WHERE guild_id = $1 AND (inviter_id = $2 OR invitee_id = $2)", guild_id, user_id)
                    deleted_count = result.split()[-1]
                    return int(deleted_count) if deleted_count.isdigit() else 0

        except Exception as e:
            logger.error(f"Error in delete_user_invites: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_user_emoji(self, guild_id: int, user_id: int,
                                channel_id: Optional[int] = None,
                                category_id: Optional[int] = None,
                                time_period_days: Optional[int] = None,
                                delete_from_date: Optional[datetime] = None,
                                delete_to_date: Optional[datetime] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    conditions = ["guild_id = $1", "user_id = $2"]
                    params = [guild_id, user_id]
                    param_counter = 3

                    if channel_id:
                        conditions.append(f"channel_id = ${param_counter}")
                        params.append(channel_id)
                        param_counter += 1

                    if category_id:
                        conditions.append(f"category_id = ${param_counter}")
                        params.append(category_id)
                        param_counter += 1

                    if time_period_days:
                        conditions.append(
                            f"hour >= NOW() - INTERVAL '{time_period_days} days'")

                    if delete_from_date:
                        conditions.append(f"hour >= ${param_counter}")
                        params.append(delete_from_date)
                        param_counter += 1

                    if delete_to_date:
                        conditions.append(f"hour <= ${param_counter}")
                        params.append(delete_to_date)
                        param_counter += 1

                    where_clause = " AND ".join(conditions)
                    result = await conn.execute(f"DELETE FROM emoji_usage_hourly WHERE {where_clause}", *params)
                    deleted_count = result.split()[-1]
                    return int(deleted_count) if deleted_count.isdigit() else 0

        except Exception as e:
            logger.error(f"Error in delete_user_emoji: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_user_activity(self, guild_id: int, user_id: int,
                                   time_period_days: Optional[int] = None,
                                   delete_from_date: Optional[datetime] = None,
                                   delete_to_date: Optional[datetime] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    deleted_counts = {}

                    if time_period_days:
                        result1 = await conn.execute(f"DELETE FROM activity_sessions_hourly WHERE guild_id = $1 AND user_id = $2 AND hour >= NOW() - INTERVAL '{time_period_days} days'", guild_id, user_id)
                        result2 = await conn.execute(f"DELETE FROM daily_activity_log WHERE guild_id = $1 AND user_id = $2 AND day >= NOW() - INTERVAL '{time_period_days} days'", guild_id, user_id)
                        result3 = await conn.execute(f"DELETE FROM activity_streaks WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)
                    elif delete_from_date or delete_to_date:
                        conditions = ["guild_id = $1", "user_id = $2"]
                        params = [guild_id, user_id]
                        param_counter = 3
                        if delete_from_date:
                            conditions.append(f"hour >= ${param_counter}")
                            params.append(delete_from_date)
                            param_counter += 1
                            conditions.append(f"day >= ${param_counter}")
                            params.append(delete_from_date)
                            param_counter += 1
                        if delete_to_date:
                            conditions.append(f"hour <= ${param_counter}")
                            params.append(delete_to_date)
                            param_counter += 1
                            conditions.append(f"day <= ${param_counter}")
                            params.append(delete_to_date)
                            param_counter += 1
                        where_clause = " AND ".join(conditions)
                        result1 = await conn.execute(f"DELETE FROM activity_sessions_hourly WHERE {where_clause}", *params)
                        result2 = await conn.execute(f"DELETE FROM daily_activity_log WHERE {where_clause}", *params)
                        result3 = await conn.execute(f"DELETE FROM activity_streaks WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)
                    else:
                        result1 = await conn.execute(f"DELETE FROM activity_sessions_hourly WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)
                        result2 = await conn.execute(f"DELETE FROM daily_activity_log WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)
                        result3 = await conn.execute(f"DELETE FROM activity_streaks WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)

                    deleted_counts['activity_sessions_hourly'] = result1.split(
                    )[-1]
                    deleted_counts['daily_activity_log'] = result2.split()[-1]
                    deleted_counts['activity_streaks'] = result3.split()[-1]
                    return deleted_counts

        except Exception as e:
            logger.error(f"Error in delete_user_activity: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_user_mentions(self, guild_id: int, user_id: int,
                                   channel_id: Optional[int] = None,
                                   category_id: Optional[int] = None,
                                   time_period_days: Optional[int] = None,
                                   delete_from_date: Optional[datetime] = None,
                                   delete_to_date: Optional[datetime] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    conditions = ["guild_id = $1", "mentioned_user_id = $2"]
                    params = [guild_id, user_id]
                    param_counter = 3

                    if channel_id:
                        conditions.append(f"channel_id = ${param_counter}")
                        params.append(channel_id)
                        param_counter += 1

                    if category_id:
                        conditions.append(f"category_id = ${param_counter}")
                        params.append(category_id)
                        param_counter += 1

                    if time_period_days:
                        conditions.append(
                            f"hour >= NOW() - INTERVAL '{time_period_days} days'")

                    if delete_from_date:
                        conditions.append(f"hour >= ${param_counter}")
                        params.append(delete_from_date)
                        param_counter += 1

                    if delete_to_date:
                        conditions.append(f"hour <= ${param_counter}")
                        params.append(delete_to_date)
                        param_counter += 1

                    where_clause = " AND ".join(conditions)
                    result = await conn.execute(f"DELETE FROM user_mentions_hourly WHERE {where_clause}", *params)
                    deleted_count = result.split()[-1]
                    return int(deleted_count) if deleted_count.isdigit() else 0

        except Exception as e:
            logger.error(f"Error in delete_user_mentions: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_user_role_growth(self, guild_id: int, user_id: int,
                                      time_period_days: Optional[int] = None,
                                      delete_from_date: Optional[datetime] = None,
                                      delete_to_date: Optional[datetime] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    if time_period_days:
                        result = await conn.execute(f"DELETE FROM role_growth_hourly WHERE guild_id = $1 AND user_id = $2 AND hour >= NOW() - INTERVAL '{time_period_days} days'", guild_id, user_id)
                    elif delete_from_date or delete_to_date:
                        conditions = ["guild_id = $1", "user_id = $2"]
                        params = [guild_id, user_id]
                        param_counter = 3
                        if delete_from_date:
                            conditions.append(f"hour >= ${param_counter}")
                            params.append(delete_from_date)
                            param_counter += 1
                        if delete_to_date:
                            conditions.append(f"hour <= ${param_counter}")
                            params.append(delete_to_date)
                            param_counter += 1
                        where_clause = " AND ".join(conditions)
                        result = await conn.execute(f"DELETE FROM role_growth_hourly WHERE {where_clause}", *params)
                    else:
                        result = await conn.execute(f"DELETE FROM role_growth_hourly WHERE guild_id = $1 AND user_id = $2", guild_id, user_id)
                    deleted_count = result.split()[-1]
                    return int(deleted_count) if deleted_count.isdigit() else 0

        except Exception as e:
            logger.error(f"Error in delete_user_role_growth: {e}")
            logger.error(traceback.format_exc())
            raise

    # ======================================================================
    # RESET METHODS
    # ======================================================================

    async def reset_server_stats(self, guild_id: int, stat_type: str,
                                 channel_id: Optional[int] = None,
                                 category_id: Optional[int] = None,
                                 time_period_days: Optional[int] = None,
                                 delete_from_date: Optional[datetime] = None,
                                 delete_to_date: Optional[datetime] = None):

        try:
            stat_type_lower = stat_type.lower()
            result = None

            if stat_type_lower == "all":
                result = await self.delete_server_all(guild_id, channel_id, category_id, time_period_days, delete_from_date, delete_to_date)
            elif stat_type_lower == "messages":
                result = await self.delete_server_messages(guild_id, channel_id, category_id, time_period_days, delete_from_date, delete_to_date)
            elif stat_type_lower == "voice activity":
                result = await self.delete_server_voice(guild_id, channel_id, category_id, time_period_days, delete_from_date, delete_to_date)
            elif stat_type_lower == "invite tracking":
                result = await self.delete_server_invites(guild_id, time_period_days, delete_from_date, delete_to_date)
            elif stat_type_lower == "emoji stats":
                result = await self.delete_server_emoji(guild_id, channel_id, category_id, time_period_days, delete_from_date, delete_to_date)
            elif stat_type_lower == "activity":
                result = await self.delete_server_activity(guild_id, time_period_days, delete_from_date, delete_to_date)
            elif stat_type_lower == "mentions":
                result = await self.delete_server_mentions(guild_id, channel_id, category_id, time_period_days, delete_from_date, delete_to_date)
            elif stat_type_lower == "role growth":
                result = await self.delete_server_role_growth(guild_id, time_period_days, delete_from_date, delete_to_date)
            elif stat_type_lower == "member growth":
                result = await self.delete_server_member_growth(guild_id, time_period_days, delete_from_date, delete_to_date)

            return result

        except Exception as e:
            logger.error(f"Failed to reset server stats: {e}")
            logger.error(traceback.format_exc())
            raise

    async def reset_user_stats(self, guild_id: int, user_id: int, stat_type: str,
                               channel_id: Optional[int] = None,
                               category_id: Optional[int] = None,
                               time_period_days: Optional[int] = None,
                               delete_from_date: Optional[datetime] = None,
                               delete_to_date: Optional[datetime] = None):

        try:
            stat_type_lower = stat_type.lower()
            result = None

            if stat_type_lower == "all":
                result = await self.delete_user_all(guild_id, user_id, channel_id, category_id, time_period_days, delete_from_date, delete_to_date)
            elif stat_type_lower == "messages":
                result = await self.delete_user_messages(guild_id, user_id, channel_id, category_id, time_period_days, delete_from_date, delete_to_date)
            elif stat_type_lower == "voice activity":
                result = await self.delete_user_voice(guild_id, user_id, channel_id, category_id, time_period_days, delete_from_date, delete_to_date)
            elif stat_type_lower == "invite tracking":
                result = await self.delete_user_invites(guild_id, user_id, time_period_days, delete_from_date, delete_to_date)
            elif stat_type_lower == "emoji stats":
                result = await self.delete_user_emoji(guild_id, user_id, channel_id, category_id, time_period_days, delete_from_date, delete_to_date)
            elif stat_type_lower == "activity":
                result = await self.delete_user_activity(guild_id, user_id, time_period_days, delete_from_date, delete_to_date)
            elif stat_type_lower == "mentions":
                result = await self.delete_user_mentions(guild_id, user_id, channel_id, category_id, time_period_days, delete_from_date, delete_to_date)
            elif stat_type_lower == "role growth":
                result = await self.delete_user_role_growth(guild_id, user_id, time_period_days, delete_from_date, delete_to_date)

            return result

        except Exception as e:
            logger.error(f"Failed to reset user stats: {e}")
            logger.error(traceback.format_exc())
            raise


# =========================================================
# PREMIUM HELPER
# =========================================================

async def _guild_has_optimization(bot, guild_id: int) -> bool:
    """Return True if the guild has an active Optimization+ subscription."""
    db_cog = bot.get_cog('DatabaseStats')
    if db_cog is None:
        return False
    return await db_cog.guild_has_module_access(guild_id, 'optimization')


# =========================================================
# DELETE SCHEDULE MODAL
# =========================================================

class DeleteScheduleModal(Modal, title="Delete Reset Schedule"):
    def __init__(self, db_manager, guild_id: int, schedule_id: int, schedule_name: Optional[str], current_view):
        super().__init__(timeout=300)
        self.db_manager = db_manager
        self.guild_id = guild_id
        self.schedule_id = schedule_id
        self.schedule_name = schedule_name
        self.current_view = current_view
        self.rate_limiter = get_rate_limiter()

        self.confirm_input = TextInput(
            label="Enter Schedule ID to Delete",
            placeholder=f"Enter {schedule_id}",
            required=True,
            max_length=10
        )
        self.add_item(self.confirm_input)

    @rate_limited(RateLimitType.MESSAGE, timeout=15.0)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            if self.confirm_input.value.strip() != str(self.schedule_id):
                embed = discord.Embed(
                    title="Deletion Failed",
                    description=f"You must enter the correct schedule ID ({self.schedule_id}) to delete this schedule.",
                    color=discord.Color.red()
                )
                await interaction.response.edit_message(embed=embed, view=self.current_view)
                return

            success = await self.db_manager.delete_schedule(self.schedule_id, self.guild_id)

            if success:
                embed = discord.Embed(
                    title="Schedule Deleted",
                    description=f"Schedule #{self.schedule_id}{f' ({self.schedule_name})' if self.schedule_name else ''} has been successfully deleted.",
                    color=discord.Color.green(),
                    timestamp=datetime.now(timezone.utc)
                )
            else:
                embed = discord.Embed(
                    title="Deletion Failed",
                    description=f"Schedule #{self.schedule_id} could not be found or already completed.",
                    color=discord.Color.red()
                )

            all_schedules = await self.db_manager.get_all_schedules_for_guild(self.guild_id)

            if all_schedules:
                new_view = ScheduleView(
                    all_schedules, self.db_manager, self.guild_id, interaction.user.id, interaction.guild)
                await interaction.response.edit_message(embed=new_view.create_embed(), view=new_view)
            else:
                embed = discord.Embed(
                    title="Reset Schedules",
                    description="No reset schedules found for this server.\n\nYou can create schedules using the `/reset` command.",
                    color=discord.Color.blue(),
                    timestamp=datetime.now(timezone.utc)
                )
                await interaction.response.edit_message(embed=embed, view=None)

        except Exception as e:
            logger.error(f"Error deleting schedule: {e}")
            embed = discord.Embed(
                title="Deletion Failed",
                description=f"An error occurred: {str(e)[:200]}",
                color=discord.Color.red()
            )
            await interaction.response.edit_message(embed=embed, view=self.current_view)


# =========================================================
# SCHEDULE VIEW
# =========================================================

# =========================================================
# SCHEDULE VIEW - FIXED
# =========================================================

class ScheduleView(View):
    def __init__(self, schedules: List[dict], db_manager, guild_id: int, user_id: int, guild: discord.Guild = None):
        super().__init__(timeout=180)
        self.schedules = schedules
        self.db_manager = db_manager
        self.guild_id = guild_id
        self.user_id = user_id
        self.guild = guild
        self.current_index = 0
        self.rate_limiter = get_rate_limiter()
        self._update_buttons()

    def _update_buttons(self):
        self.clear_items()

        total_schedules = len(self.schedules)

        prev_button = Button(
            label="◀",
            style=discord.ButtonStyle.secondary,
            row=0,
            disabled=(self.current_index == 0 or total_schedules == 0)
        )
        prev_button.callback = self.prev_callback

        page_indicator = Button(
            label=f"Schedule {self.current_index + 1}/{total_schedules}" if total_schedules > 0 else "No Schedules",
            style=discord.ButtonStyle.primary,
            row=0,
            disabled=True
        )

        next_button = Button(
            label="▶",
            style=discord.ButtonStyle.secondary,
            row=0,
            disabled=(self.current_index >= total_schedules -
                      1 or total_schedules == 0)
        )
        next_button.callback = self.next_callback

        self.add_item(prev_button)
        self.add_item(page_indicator)
        self.add_item(next_button)

        delete_button = Button(
            label="Delete Schedule",
            style=discord.ButtonStyle.danger,
            emoji="🗑️",
            row=1
        )
        delete_button.callback = self.delete_callback
        self.add_item(delete_button)

    @rate_limited(RateLimitType.MESSAGE, timeout=15.0)
    async def prev_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            embed = discord.Embed(
                title="Permission Denied", description="You cannot use these buttons!", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        if self.current_index > 0:
            self.current_index -= 1
            self._update_buttons()
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @rate_limited(RateLimitType.MESSAGE, timeout=15.0)
    async def next_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            embed = discord.Embed(
                title="Permission Denied", description="You cannot use these buttons!", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        if self.current_index < len(self.schedules) - 1:
            self.current_index += 1
            self._update_buttons()
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @rate_limited(RateLimitType.MESSAGE, timeout=15.0)
    async def delete_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            embed = discord.Embed(
                title="Permission Denied", description="You cannot use this button!", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        current_schedule = self.schedules[self.current_index]
        modal = DeleteScheduleModal(
            self.db_manager,
            self.guild_id,
            current_schedule['id'],
            current_schedule.get('schedule_name'),
            self
        )
        await interaction.response.send_modal(modal)

    def create_embed(self) -> discord.Embed:
        # ... (keep the existing create_embed method unchanged)
        if not self.schedules:
            embed = discord.Embed(
                title="Reset Schedules",
                description="No reset schedules found for this server.\n\nYou can create schedules using the `/reset` command.",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            return embed

        schedule = self.schedules[self.current_index]

        schedule_type = schedule.get('schedule_type', 'one_time')
        reset_types = ", ".join(schedule['reset_types'])

        if schedule.get('schedule_name'):
            title = schedule['schedule_name']
        else:
            title = "Schedule"

        enabled = schedule.get('enabled', True)
        status_emoji = "🟢" if enabled else "🔴"
        status_text = "Enabled" if enabled else "Disabled"

        embed = discord.Embed(
            title=title,
            description=f"**Status:** {status_emoji} {status_text}",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )

        embed.add_field(name="Schedule ID",
                        value=f"`{schedule['id']}`", inline=True)
        embed.add_field(name="Reset Types",
                        value=f"```{reset_types}```", inline=False)

        scope_display = schedule.get('scope_type', 'Unknown')
        if schedule.get('scope_type') == 'channel' and schedule.get('channel_id') and self.guild:
            channel = self.guild.get_channel(schedule['channel_id'])
            if channel:
                scope_display = f"#{channel.name}"
        elif schedule.get('scope_type') == 'category' and schedule.get('category_id') and self.guild:
            category = discord.utils.get(
                self.guild.categories, id=schedule['category_id'])
            if category:
                scope_display = category.name
        elif schedule.get('scope_type') == 'user' and schedule.get('scope_details'):
            if 'User:' in schedule.get('scope_details', ''):
                parts = schedule['scope_details'].split('User:')
                if len(parts) > 1:
                    scope_display = parts[1].strip().split(' -')[0]
        elif schedule.get('scope_type') == 'server':
            scope_display = "Server"

        embed.add_field(
            name="Scope", value=f"```{scope_display}```", inline=True)

        if schedule.get('scope_details'):
            embed.add_field(
                name="Target", value=f"```{schedule['scope_details'][:100]}```", inline=False)

        if schedule_type == 'recurring':
            pattern = schedule.get('recurring_pattern', 'unknown')
            times = schedule.get('recurring_times', [])
            time_str = ', '.join([str(t) for t in times]) if times else schedule.get(
                'recurring_time', '00:00')
            embed.add_field(name="Schedule Type",
                            value=f"```Recurring ({pattern})```", inline=True)
            embed.add_field(
                name="Time(s)", value=f"```{time_str}```", inline=True)

            if schedule.get('recurring_weekdays'):
                weekdays = schedule['recurring_weekdays']
                weekday_names = ['Monday', 'Tuesday', 'Wednesday',
                                 'Thursday', 'Friday', 'Saturday', 'Sunday']
                weekday_str = ', '.join([weekday_names[w]
                                        for w in weekdays if 0 <= w < 7])
                embed.add_field(name="Weekdays",
                                value=f"```{weekday_str}```", inline=False)

            if schedule.get('recurring_days_of_month'):
                embed.add_field(
                    name="Days of Month", value=f"```{', '.join([str(d) for d in schedule['recurring_days_of_month']])}```", inline=False)

            if schedule.get('recurring_interval_days'):
                embed.add_field(
                    name="Interval", value=f"```Every {schedule['recurring_interval_days']} days```", inline=False)

            if schedule.get('next_execution_at') and enabled:
                next_time = schedule['next_execution_at']
                embed.add_field(
                    name="Next Execution", value=f"<t:{int(next_time.timestamp())}:F>", inline=False)
            elif not enabled:
                embed.add_field(
                    name="Next Execution", value="```Disabled - Will not run```", inline=False)

        elif schedule_type == 'date_range':
            embed.add_field(name="Schedule Type",
                            value=f"```Date Range```", inline=True)
            if schedule.get('delete_from_date'):
                embed.add_field(
                    name="From", value=f"<t:{int(schedule['delete_from_date'].timestamp())}:F>", inline=True)
            if schedule.get('delete_to_date'):
                embed.add_field(
                    name="To", value=f"<t:{int(schedule['delete_to_date'].timestamp())}:F>", inline=True)
        else:
            embed.add_field(name="Schedule Type",
                            value=f"```One-time```", inline=True)
            if schedule.get('target_time') and enabled:
                embed.add_field(
                    name="Scheduled Time", value=f"<t:{int(schedule['target_time'].timestamp())}:F>", inline=True)

        if schedule.get('time_period_days'):
            embed.add_field(
                name="Time Period", value=f"```Last {schedule['time_period_days']} days```", inline=False)

        embed.add_field(
            name="ℹ️ Edit Schedules",
            value="You can edit everything related to the schedule (name, reset types, schedule pattern, scope, time period, enabled/disabled) through the [web dashboard](https://statshq.xyz/Dashboard/Reset/).",
            inline=False
        )

        total_schedules = len(self.schedules)
        embed.set_footer(
            text=f"Schedule {self.current_index + 1} of {total_schedules} | Use Delete to remove")

        return embed


# =========================================================
# DATE RANGE MODAL
# =========================================================

class DateRangeModal(Modal, title="Date Range Selection"):
    def __init__(self, view):
        super().__init__(timeout=300)
        self.view = view
        self.rate_limiter = get_rate_limiter()

        self.from_date = TextInput(
            label="From Date (Optional)",
            placeholder="DD-MM-YYYY (e.g., 01-01-2024)",
            max_length=10,
            required=False
        )
        self.add_item(self.from_date)

        self.to_date = TextInput(
            label="To Date (Optional)",
            placeholder="DD-MM-YYYY (e.g., 31-12-2024)",
            max_length=10,
            required=False
        )
        self.add_item(self.to_date)

    @rate_limited(RateLimitType.MESSAGE, timeout=15.0)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            from_date_str = self.from_date.value.strip()
            to_date_str = self.to_date.value.strip()

            from_date_obj = self.view.db_manager.parse_date_input(
                from_date_str) if from_date_str else None
            to_date_obj = self.view.db_manager.parse_date_input(
                to_date_str) if to_date_str else None

            if from_date_str and not from_date_obj:
                await interaction.response.send_message(
                    "❌ Invalid From Date format! Use DD-MM-YYYY (e.g., 25-12-2024)",
                    ephemeral=True
                )
                return

            if to_date_str and not to_date_obj:
                await interaction.response.send_message(
                    "❌ Invalid To Date format! Use DD-MM-YYYY (e.g., 25-12-2024)",
                    ephemeral=True
                )
                return

            if from_date_obj and to_date_obj and from_date_obj > to_date_obj:
                await interaction.response.send_message(
                    "❌ From Date must be before To Date!",
                    ephemeral=True
                )
                return

            self.view.date_range_from = from_date_obj
            self.view.date_range_to = to_date_obj
            self.view.time_option = 'range'

            from_text = from_date_obj.strftime(
                '%d-%m-%Y') if from_date_obj else "Start"
            to_text = to_date_obj.strftime(
                '%d-%m-%Y') if to_date_obj else "End"
            self.view.time_period_text = f"Deleting stats from {from_text} to {to_text}"

            await interaction.response.defer()
            await self.view.show_advanced_schedule()

        except Exception as e:
            logger.error(f"Error in date range modal: {e}")
            await interaction.response.send_message(
                f"❌ An error occurred: {str(e)[:200]}",
                ephemeral=True
            )


# =========================================================
# TIME PERIOD MODAL
# =========================================================

class TimePeriodModal(Modal, title="Days Back Selection"):
    def __init__(self, view):
        super().__init__(timeout=300)
        self.view = view
        self.rate_limiter = get_rate_limiter()

        self.days_input = TextInput(
            label="Number of Days",
            placeholder="Enter number of days (1-365)",
            min_length=1,
            max_length=3,
            required=True
        )
        self.add_item(self.days_input)

    @rate_limited(RateLimitType.MESSAGE, timeout=15.0)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            days_str = self.days_input.value.strip()
            days = int(days_str)
            if days < 1 or days > 365:
                await interaction.response.send_message(
                    "Please enter a number between 1 and 365 days.",
                    ephemeral=True
                )
                return

            self.view.time_option = 'days'
            self.view.time_period_days = days
            self.view.time_period_text = f"Deleting stats from the last {days} days"

            await interaction.response.defer()
            await self.view.show_advanced_schedule()

        except ValueError:
            await interaction.response.send_message(
                "Please enter a valid number.",
                ephemeral=True
            )


# =========================================================
# ADVANCED SCHEDULE MODAL (5 inputs max)
# =========================================================

class AdvancedScheduleModal(Modal, title="Schedule Reset"):
    def __init__(self, view, scope_text: str, scope_details: str, time_period_text: str):
        super().__init__(timeout=300)
        self.view = view
        self.scope_text = scope_text
        self.scope_details = scope_details
        self.time_period_text = time_period_text
        self.rate_limiter = get_rate_limiter()

        self.schedule_name = TextInput(
            label="Schedule Name (Optional)",
            placeholder="Give your schedule a name (e.g., Weekly Cleanup)",
            max_length=100,
            required=False
        )
        self.add_item(self.schedule_name)

        self.time_of_day = TextInput(
            label="Time of Day (Required)",
            placeholder="HH:MM (24-hour format, e.g., 18:00, 14:30)",
            max_length=5,
            required=True
        )
        self.add_item(self.time_of_day)

        self.every_x_days = TextInput(
            label="Every X Days (Optional)",
            placeholder="Enter number of days (e.g., 3, 7, 14)",
            max_length=3,
            required=False
        )
        self.add_item(self.every_x_days)

        self.weekdays = TextInput(
            label="Weekdays (Optional)",
            placeholder="Enter weekdays (e.g., monday,wednesday,friday or mon,wed,fri)",
            max_length=50,
            required=False
        )
        self.add_item(self.weekdays)

        self.month_days = TextInput(
            label="Month Days (Optional)",
            placeholder="Enter days of month (e.g., 1,15,28)",
            max_length=30,
            required=False
        )
        self.add_item(self.month_days)

    @rate_limited(RateLimitType.MESSAGE, timeout=15.0)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            time_str = self.time_of_day.value.strip()
            if not time_str:
                await interaction.response.send_message(
                    "❌ Time of day is required for scheduling!",
                    ephemeral=True
                )
                return

            try:
                parts = time_str.split(':')
                if len(parts) < 2:
                    raise ValueError
                hour = int(parts[0])
                minute = int(parts[1])
                if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                    raise ValueError
            except ValueError:
                await interaction.response.send_message(
                    "❌ Invalid time format! Please use HH:MM (e.g., 18:00, 14:30)",
                    ephemeral=True
                )
                return

            weekdays_list = None
            weekdays_has_value = bool(self.weekdays.value.strip())
            if weekdays_has_value:
                weekdays_list = self.view.db_manager.parse_weekdays_input(
                    self.weekdays.value)
                if not weekdays_list:
                    await interaction.response.send_message(
                        "❌ Invalid weekday format! Use full names (monday, tuesday) or short (mon, tue)",
                        ephemeral=True
                    )
                    return

            month_days_list = None
            month_days_has_value = bool(self.month_days.value.strip())
            if month_days_has_value:
                try:
                    month_days_list = [int(d.strip())
                                       for d in self.month_days.value.split(',')]
                    for d in month_days_list:
                        if d < 1 or d > 31:
                            raise ValueError
                except ValueError:
                    await interaction.response.send_message(
                        "❌ Invalid month days! Please enter numbers between 1 and 31, comma-separated",
                        ephemeral=True
                    )
                    return

            interval_days = None
            interval_has_value = bool(self.every_x_days.value.strip())
            if interval_has_value:
                try:
                    interval_days = int(self.every_x_days.value.strip())
                    if interval_days < 1 or interval_days > 365:
                        raise ValueError
                except ValueError:
                    await interaction.response.send_message(
                        "❌ Invalid interval! Please enter a number between 1 and 365",
                        ephemeral=True
                    )
                    return

            provided_count = sum(
                [weekdays_has_value, month_days_has_value, interval_has_value])
            if provided_count > 1:
                await interaction.response.send_message(
                    "❌ You can only specify ONE schedule type!\n\n"
                    "Choose either:\n"
                    "• Weekdays (e.g., monday, wednesday, friday)\n"
                    "• Month Days (e.g., 1, 15, 28)\n"
                    "• Every X Days (e.g., 3, 7, 14)\n\n"
                    "If you leave all empty, it will run daily.",
                    ephemeral=True
                )
                return

            if weekdays_has_value:
                pattern = 'weekly'
            elif month_days_has_value:
                pattern = 'monthly'
            elif interval_has_value:
                pattern = 'custom_days'
            else:
                pattern = 'daily'

            times_list = [time_str]

            self.view.schedule_data = {
                'pattern': pattern,
                'times': times_list,
                'weekdays': weekdays_list,
                'month_days': month_days_list,
                'interval_days': interval_days,
                'schedule_name': self.schedule_name.value.strip() or None
            }

            desc_parts = []
            if pattern == 'daily':
                desc_parts.append(f"Every day at {time_str}")
            elif pattern == 'weekly' and weekdays_list:
                weekday_names = ['Monday', 'Tuesday', 'Wednesday',
                                 'Thursday', 'Friday', 'Saturday', 'Sunday']
                weekday_str = ', '.join([weekday_names[w]
                                        for w in weekdays_list])
                desc_parts.append(f"Every {weekday_str} at {time_str}")
            elif pattern == 'monthly' and month_days_list:
                def get_ordinal(n):
                    if 11 <= n <= 13:
                        return 'th'
                    return {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
                month_day_str = ', '.join(
                    [f"{d}{get_ordinal(d)}" for d in month_days_list])
                desc_parts.append(
                    f"Every {month_day_str} of the month at {time_str}")
            elif pattern == 'custom_days' and interval_days:
                desc_parts.append(f"Every {interval_days} days at {time_str}")

            self.view.schedule_description = ' | '.join(desc_parts)

            await interaction.response.defer()
            await self.view.show_confirmation()

        except Exception as e:
            logger.error(f"Error in advanced schedule modal: {e}")
            await interaction.response.send_message(
                f"❌ An error occurred: {str(e)[:200]}",
                ephemeral=True
            )


# =========================================================
# ID INPUT MODAL
# =========================================================

class IDInputModal(Modal, title="Enter Channel/Category ID"):

    def __init__(self, scope: str, view):
        super().__init__(timeout=300)
        self.scope = scope
        self.view = view
        self.rate_limiter = get_rate_limiter()

        self.id_input = TextInput(
            label=f"Enter {scope.capitalize()} ID",
            placeholder=f"Paste the {scope} ID here...",
            max_length=30,
            required=True
        )
        self.add_item(self.id_input)

    @rate_limited(RateLimitType.MESSAGE, timeout=15.0)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            id_str = self.id_input.value.strip()
            if not id_str.isdigit():
                await interaction.response.send_message(
                    f"Invalid ID! Please enter a valid numeric ID.",
                    ephemeral=True
                )
                return

            channel_id = int(id_str)

            if self.scope == "channel":
                channel = interaction.guild.get_channel(channel_id)
                if not channel or not isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
                    await interaction.response.send_message(
                        f"Channel not found! Make sure the ID is correct and the channel exists in this server.",
                        ephemeral=True
                    )
                    return

                self.view.channel_id = channel_id
                self.view.selected_channel = channel

            else:
                category = discord.utils.get(
                    interaction.guild.categories, id=channel_id)
                if not category:
                    await interaction.response.send_message(
                        f"Category not found! Make sure the ID is correct and the category exists in this server.",
                        ephemeral=True
                    )
                    return

                self.view.category_id = channel_id
                self.view.selected_category = category

            await interaction.response.defer()
            await self.view.show_page_3()

        except ValueError:
            await interaction.response.send_message(
                "Invalid ID format! Please enter a valid numeric ID.",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in ID input modal: {e}")
            await interaction.response.send_message(
                f"An error occurred: {str(e)[:200]}",
                ephemeral=True
            )


# =========================================================
# RESET VIEW (6 Pages)
# =========================================================
class ResetView(View):
    def __init__(self, interaction: discord.Interaction, db_manager: DatabaseManager,
                 command_type: Literal["server", "user"], target_user_id: Optional[int] = None,
                 bot=None):
        super().__init__(timeout=300)
        self.interaction = interaction
        self.db_manager = db_manager
        self.command_type = command_type
        self.target_user_id = target_user_id
        self.bot = bot  # stored so we can check premium in page 5
        self.scope = None
        self.stat_type = None
        self.channel_id = None
        self.category_id = None
        self.current_page = 1
        self.selected_channel = None
        self.selected_category = None
        self.time_option = None
        self.time_period_days = None
        self.time_period_text = None
        self.date_range_from = None
        self.date_range_to = None
        self.schedule_data = None
        self.schedule_description = None
        self.confirmation_scope_text = None
        self.confirmation_time_period_text = None
        self.rate_limiter = get_rate_limiter()

    def create_embed(self, title: str, description: str, color: int = 0xff0000) -> discord.Embed:
        embed = discord.Embed(
            title=title, description=description, color=color)
        embed.set_footer(text="Stats Reset System")
        return embed

    # PAGE 1: SELECT SCOPE
    async def show_page_1(self):
        self.clear_items()
        self.current_page = 1

        if self.command_type == "server":
            title = "Reset Server Stats"
            description = "**Page 1/6**\n**Where do you want to reset statistics?**\n\nSelect from the dropdown below:"
        else:
            user_text = f"<@{self.target_user_id}>" if self.target_user_id else "your"
            title = f"Reset {user_text.capitalize()} Stats"
            description = f"**Page 1/6**\n**Where do you want to reset {user_text} statistics?**\n\nSelect from the dropdown below:"

        embed = self.create_embed(title, description)

        select = Select(
            placeholder="Select scope...",
            options=[
                discord.SelectOption(
                    label="Server", value="server", description="Reset stats for entire server"),
                discord.SelectOption(label="Channel", value="channel",
                                     description="Reset stats for a specific channel"),
                discord.SelectOption(label="Category", value="category",
                                     description="Reset stats for a specific category")
            ]
        )
        select.callback = self.page1_scope_callback
        self.add_item(select)
        await self.interaction.edit_original_response(embed=embed, view=self)

    @rate_limited(RateLimitType.MESSAGE, timeout=30.0)
    async def page1_scope_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.interaction.user.id:
            await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
            return
        self.scope = interaction.data['values'][0]
        if self.scope == "server":
            await interaction.response.defer()
            await self.show_page_3()
        else:
            await interaction.response.defer()
            await self.show_page_2()

    # PAGE 2: SELECT CHANNEL/CATEGORY
    async def show_page_2(self):
        self.clear_items()
        self.current_page = 2

        if self.scope == "channel":
            title = "Select Channel"
            description = "**Page 2/6**\n**Select a channel to reset statistics from:**\n\nChoose from the dropdown below **OR** click 'Input ID' to enter a channel ID manually."
            placeholder = "Choose a channel..."
            input_button_label = "Input Channel ID"

            channels = [ch for ch in self.interaction.guild.channels
                        if isinstance(ch, (discord.TextChannel, discord.VoiceChannel))]

            options = []
            for channel in channels[:25]:
                channel_type = "📝" if isinstance(
                    channel, discord.TextChannel) else "🔊"
                options.append(discord.SelectOption(
                    label=f"{channel_type} {channel.name}",
                    value=str(channel.id),
                    description=f"{channel.name[:50]}"
                ))

        else:
            title = "Select Category"
            description = "**Page 2/6**\n**Select a category to reset statistics from:**\n\nChoose from the dropdown below **OR** click 'Input ID' to enter a category ID manually."
            placeholder = "Choose a category..."
            input_button_label = "Input Category ID"

            categories = self.interaction.guild.categories[:25]
            options = []
            for category in categories:
                options.append(discord.SelectOption(
                    label=f"📁 {category.name}",
                    value=str(category.id),
                    description=f"{category.name[:50]}"
                ))

        if not options:
            embed = self.create_embed(
                "Error", f"No {self.scope}s found in this server!")
            await self.interaction.edit_original_response(embed=embed, view=None)
            return

        embed = self.create_embed(title, description)
        select = Select(placeholder=placeholder, options=options)
        select.callback = self.page2_selection_callback
        self.add_item(select)

        input_id_button = Button(
            label=input_button_label, style=discord.ButtonStyle.secondary, emoji="🔢")
        input_id_button.callback = self.page2_input_id_callback
        self.add_item(input_id_button)

        back_button = Button(
            label="Back", style=discord.ButtonStyle.gray, emoji="⬅️")
        back_button.callback = self.page2_back_callback
        self.add_item(back_button)
        await self.interaction.edit_original_response(embed=embed, view=self)

    @rate_limited(RateLimitType.MESSAGE, timeout=30.0)
    async def page2_selection_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.interaction.user.id:
            await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
            return
        selected_id = int(interaction.data['values'][0])
        if self.scope == "channel":
            self.channel_id = selected_id
            self.selected_channel = interaction.guild.get_channel(selected_id)
        else:
            self.category_id = selected_id
            self.selected_category = discord.utils.get(
                interaction.guild.categories, id=selected_id)
        await interaction.response.defer()
        await self.show_page_3()

    @rate_limited(RateLimitType.MESSAGE, timeout=30.0)
    async def page2_input_id_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.interaction.user.id:
            await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
            return
        modal = IDInputModal(self.scope, self)
        await interaction.response.send_modal(modal)

    @rate_limited(RateLimitType.MESSAGE, timeout=30.0)
    async def page2_back_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.interaction.user.id:
            await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
            return
        await interaction.response.defer()
        await self.show_page_1()

    # PAGE 3: SELECT STAT TYPE
    async def show_page_3(self):
        self.clear_items()
        self.current_page = 3

        scope_text = ""
        if self.scope == "server":
            scope_text = "Server"
        elif self.scope == "channel" and self.selected_channel:
            scope_text = f"#{self.selected_channel.name}"
        elif self.scope == "category" and self.selected_category:
            scope_text = f"{self.selected_category.name}"

        if self.command_type == "server":
            title = "Select Stat Type"
            description = f"**Page 3/6**\n**Which type of statistics do you want to reset from {scope_text}?**\n\nSelect from the dropdown below:"
        else:
            user_text = f"<@{self.target_user_id}>" if self.target_user_id else "your"
            title = "Select Stat Type"
            description = f"**Page 3/6**\n**Which type of {user_text} statistics do you want to reset from {scope_text}?**\n\nSelect from the dropdown below:"

        embed = self.create_embed(title, description)

        if self.command_type == "server":
            if self.scope == "server":
                options = [
                    discord.SelectOption(
                        label="All", value="all", description="Reset ALL statistics (irreversible!)", emoji="⚠️"),
                    discord.SelectOption(
                        label="Messages", value="messages", description="Reset message tracking", emoji="💬"),
                    discord.SelectOption(label="Voice Activity", value="voice activity",
                                         description="Reset voice session history", emoji="🔊"),
                    discord.SelectOption(label="Invite Tracking", value="invite tracking",
                                         description="Reset invite tracking", emoji="📨"),
                    discord.SelectOption(
                        label="Emoji Stats", value="emoji stats", description="Reset emoji usage", emoji="😀"),
                    discord.SelectOption(label="Activity", value="activity",
                                         description="Reset activity tracking (sessions, streaks, logs)", emoji="🎮"),
                    discord.SelectOption(
                        label="Mentions", value="mentions", description="Reset user mentions", emoji="📢"),
                    discord.SelectOption(label="Role Growth", value="role growth",
                                         description="Reset role growth tracking", emoji="👥"),
                    discord.SelectOption(label="Member Growth", value="member growth",
                                         description="Reset member join/leave tracking", emoji="📈")
                ]
            else:
                options = [
                    discord.SelectOption(
                        label="All", value="all", description="Reset ALL statistics", emoji="⚠️"),
                    discord.SelectOption(
                        label="Messages", value="messages", description="Reset message tracking", emoji="💬"),
                    discord.SelectOption(label="Voice Activity", value="voice activity",
                                         description="Reset voice activity", emoji="🔊"),
                    discord.SelectOption(
                        label="Emoji Stats", value="emoji stats", description="Reset emoji usage", emoji="😀"),
                    discord.SelectOption(
                        label="Mentions", value="mentions", description="Reset user mentions", emoji="📢")
                ]
        else:
            if self.scope == "server":
                options = [
                    discord.SelectOption(
                        label="All", value="all", description="Reset ALL statistics", emoji="⚠️"),
                    discord.SelectOption(
                        label="Messages", value="messages", description="Reset message tracking", emoji="💬"),
                    discord.SelectOption(label="Voice Activity", value="voice activity",
                                         description="Reset voice activity", emoji="🔊"),
                    discord.SelectOption(label="Activity", value="activity",
                                         description="Reset activity tracking (sessions, streaks, logs)", emoji="🎮"),
                    discord.SelectOption(label="Invite Tracking", value="invite tracking",
                                         description="Reset invite tracking", emoji="📨"),
                    discord.SelectOption(
                        label="Emoji Stats", value="emoji stats", description="Reset emoji usage", emoji="😀"),
                    discord.SelectOption(
                        label="Mentions", value="mentions", description="Reset mentions", emoji="📢"),
                    discord.SelectOption(label="Role Growth", value="role growth",
                                         description="Reset role growth tracking", emoji="👥")
                ]
            else:
                options = [
                    discord.SelectOption(
                        label="All", value="all", description="Reset ALL statistics", emoji="⚠️"),
                    discord.SelectOption(
                        label="Messages", value="messages", description="Reset message tracking", emoji="💬"),
                    discord.SelectOption(label="Voice Activity", value="voice activity",
                                         description="Reset voice activity", emoji="🔊"),
                    discord.SelectOption(
                        label="Emoji Stats", value="emoji stats", description="Reset emoji usage", emoji="😀"),
                    discord.SelectOption(
                        label="Mentions", value="mentions", description="Reset mentions", emoji="📢")
                ]

        select = Select(placeholder="Select stat type...", options=options)
        select.callback = self.page3_stat_callback
        self.add_item(select)

        back_button = Button(
            label="Back", style=discord.ButtonStyle.gray, emoji="⬅️")
        back_button.callback = self.page3_back_callback
        self.add_item(back_button)
        await self.interaction.edit_original_response(embed=embed, view=self)

    @rate_limited(RateLimitType.MESSAGE, timeout=30.0)
    async def page3_stat_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.interaction.user.id:
            await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
            return
        self.stat_type = interaction.data['values'][0]
        await interaction.response.defer()
        await self.show_time_period()

    @rate_limited(RateLimitType.MESSAGE, timeout=30.0)
    async def page3_back_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.interaction.user.id:
            await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
            return
        await interaction.response.defer()
        if self.scope == "server":
            await self.show_page_1()
        else:
            await self.show_page_2()

    # PAGE 4: TIME PERIOD SELECTION
    async def show_time_period(self):
        self.clear_items()
        self.current_page = 4

        title = "Time Period"
        description = "**Page 4/6**\n**Choose which data to delete:**\n\n"
        description += "• **Skip:** Delete ALL stats with no time limit\n"
        description += "• **Days Back:** Delete stats from the last X days\n"
        description += "• **Date Range:** Delete stats within a specific date range\n\n"
        description += "Use the buttons below to choose."

        embed = self.create_embed(title, description)

        skip_button = Button(label="Skip", style=discord.ButtonStyle.secondary)
        skip_button.callback = self.page4_skip_callback
        self.add_item(skip_button)

        days_button = Button(
            label="Days Back", style=discord.ButtonStyle.primary)
        days_button.callback = self.page4_days_callback
        self.add_item(days_button)

        range_button = Button(label="Date Range",
                              style=discord.ButtonStyle.primary)
        range_button.callback = self.page4_range_callback
        self.add_item(range_button)

        back_button = Button(
            label="Back", style=discord.ButtonStyle.gray, emoji="⬅️")
        back_button.callback = self.page4_back_callback
        self.add_item(back_button)

        await self.interaction.edit_original_response(embed=embed, view=self)

    @rate_limited(RateLimitType.MESSAGE, timeout=30.0)
    async def page4_skip_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.interaction.user.id:
            await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
            return
        self.time_option = 'skip'
        self.time_period_text = "Deleting ALL stats (no time limit)"
        await interaction.response.defer()
        await self.show_advanced_schedule()

    @rate_limited(RateLimitType.MESSAGE, timeout=30.0)
    async def page4_days_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.interaction.user.id:
            await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
            return
        modal = TimePeriodModal(self)
        await interaction.response.send_modal(modal)

    @rate_limited(RateLimitType.MESSAGE, timeout=30.0)
    async def page4_range_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.interaction.user.id:
            await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
            return
        modal = DateRangeModal(self)
        await interaction.response.send_modal(modal)

    @rate_limited(RateLimitType.MESSAGE, timeout=30.0)
    async def page4_back_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.interaction.user.id:
            await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
            return
        await interaction.response.defer()
        await self.show_page_3()

    # PAGE 5: ADVANCED SCHEDULING (premium-gated)
    async def show_advanced_schedule(self):
        self.clear_items()
        self.current_page = 5

        # Check Optimization+ once for the whole page
        has_premium = False
        if self.bot:
            guild_id = self.interaction.guild.id
            has_premium = await _guild_has_optimization(self.bot, guild_id)

        scope_text = ""
        scope_details = ""

        if self.command_type == "server":
            scope_text = "Server Reset"
            if self.scope == "server":
                scope_details = "Server"
            elif self.scope == "channel" and self.selected_channel:
                scope_details = f"#{self.selected_channel.name}"
            elif self.scope == "category" and self.selected_category:
                scope_details = f"{self.selected_category.name}"
        else:
            user_text = f"<@{self.target_user_id}>" if self.target_user_id else "Yourself"
            scope_text = "User Reset"
            if self.scope == "server":
                scope_details = f"{user_text}"
            elif self.scope == "channel" and self.selected_channel:
                scope_details = f"{user_text} - #{self.selected_channel.name}"
            elif self.scope == "category" and self.selected_category:
                scope_details = f"{user_text} - {self.selected_category.name}"

        # Store these for the schedule modal
        self.schedule_scope_text = scope_text
        self.schedule_scope_details = scope_details

        title = "Schedule Reset (Optional)"
        description = "**Page 5/6**\n**Do you want to schedule this reset to run automatically?**\n\n"
        description += "• **Skip:** Run the reset immediately\n"

        if has_premium:
            description += "• **Schedule:** Set up automatic recurring resets\n\n"
        else:
            description += "• **Schedule:** ⭐ **Requires Optimization+**\n\n"

        description += f"**Reset Details:**\n"
        description += f"• **Command Type:** `{scope_text}`\n"
        description += f"• **Target:** {scope_details}\n"
        description += f"• **Stat Type:** `{self.stat_type}`\n"
        description += f"• **Time Period:** {self.time_period_text}\n\n"
        description += "**Schedule Types:**\n"
        description += "• **Daily:** Runs every day at the specified time(s)\n"
        description += "• **Weekly:** Runs on the selected day(s) at the specified time(s)\n"
        description += "• **Monthly:** Runs on the selected day(s) of the month at the specified time(s)\n"
        description += "• **Custom:** Runs every X days at the specified time(s)"

        embed = self.create_embed(title, description)

        skip_button = Button(label="Skip", style=discord.ButtonStyle.secondary)
        skip_button.callback = self.page5_skip_callback
        self.add_item(skip_button)

        # Schedule button — always visible, but gate the action behind premium
        schedule_button = Button(
            label="Schedule Reset ⭐" if not has_premium else "Schedule Reset",
            style=discord.ButtonStyle.primary,
            emoji="📅"
        )
        schedule_button.callback = self.page5_schedule_callback
        self.add_item(schedule_button)

        back_button = Button(
            label="Back", style=discord.ButtonStyle.gray, emoji="⬅️")
        back_button.callback = self.page5_back_callback
        self.add_item(back_button)
        await self.interaction.edit_original_response(embed=embed, view=self)

    @rate_limited(RateLimitType.MESSAGE, timeout=30.0)
    async def page5_skip_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.interaction.user.id:
            await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
            return
        self.schedule_data = None
        await interaction.response.defer()
        await self.show_confirmation()

    @rate_limited(RateLimitType.MESSAGE, timeout=30.0)
    async def page5_schedule_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.interaction.user.id:
            await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
            return

        # Re-check premium at click time (handles subscription changes mid-session)
        premium_now = await _guild_has_optimization(self.bot, interaction.guild.id) if self.bot else False
        if not premium_now:
            embed = discord.Embed(
                title="⭐ Optimization+ Required",
                description=(
                    "Scheduling automated resets is a premium feature available exclusively "
                    "to servers with an active **Optimization+** subscription.\n\n"
                    "You can still run an immediate reset by pressing **Skip**."
                ),
                color=discord.Color.gold()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        modal = AdvancedScheduleModal(
            self,
            self.schedule_scope_text,
            self.schedule_scope_details,
            self.time_period_text
        )
        await interaction.response.send_modal(modal)

    @rate_limited(RateLimitType.MESSAGE, timeout=30.0)
    async def page5_back_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.interaction.user.id:
            await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
            return
        await interaction.response.defer()
        await self.show_time_period()

    # PAGE 6: CONFIRMATION
    async def show_confirmation(self):
        self.clear_items()
        self.current_page = 6

        scope_text = ""
        if self.scope == "server":
            scope_text = "Server"
        elif self.scope == "channel" and self.selected_channel:
            scope_text = f"#{self.selected_channel.name}"
        elif self.scope == "category" and self.selected_category:
            scope_text = f"{self.selected_category.name}"

        # Store these for use in the confirmation callback
        self.confirmation_scope_text = scope_text
        self.confirmation_time_period_text = self.time_period_text if self.time_period_text else "Deleting ALL stats (no time limit)"

        description = f"**Page 6/6 - FINAL CONFIRMATION**\n\n"
        description += f"**Reset Details:**\n"
        description += f"• **Type:** `{'Server' if self.command_type == 'server' else 'User'} Reset`\n"
        description += f"• **Target:** {self.confirmation_scope_text}\n"
        description += f"• **Stat Type:** `{self.stat_type}`\n"
        description += f"• **Time Period:** {self.confirmation_time_period_text}\n"

        if self.schedule_data:
            description += f"\n**Schedule Configuration:**\n"
            description += f"• **Schedule:** {self.schedule_description}\n"
            if self.schedule_data.get('schedule_name'):
                description += f"• **Schedule Name:** {self.schedule_data['schedule_name']}\n"
            description += f"\n**Note:** You can manage (edit/delete) this schedule later using `/reset schedules`\n"
            description += f"Edit everything related to the schedule (name, reset types, schedule pattern, scope, time period, enabled/disabled) through the [web dashboard](https://statshq.xyz/Dashboard/Reset/)."

        description += f"\n\n**This action is PERMANENT and CANNOT be undone!**"

        embed = self.create_embed("Confirm Reset", description)

        confirm_button = Button(
            label="Confirm", style=discord.ButtonStyle.danger)
        confirm_button.callback = self.page6_confirm_callback
        self.add_item(confirm_button)

        back_button = Button(
            label="Back", style=discord.ButtonStyle.gray, emoji="⬅️")
        back_button.callback = self.page6_back_callback
        self.add_item(back_button)

        await self.interaction.edit_original_response(embed=embed, view=self)

    @rate_limited(RateLimitType.MESSAGE, timeout=30.0)
    async def page6_confirm_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.interaction.user.id:
            await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
            return

        # If a schedule was configured, do a final premium check before saving
        if self.schedule_data:
            premium_now = await _guild_has_optimization(self.bot, interaction.guild.id) if self.bot else False
            if not premium_now:
                embed = discord.Embed(
                    title="⭐ Optimization+ Required",
                    description=(
                        "Scheduling automated resets requires an active **Optimization+** subscription.\n\n"
                        "Go back and choose **Skip** on the scheduling page to run an immediate reset instead."
                    ),
                    color=discord.Color.gold()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

        processing_embed = self.create_embed(
            "Processing...", "This may take a moment...")
        await interaction.edit_original_response(embed=processing_embed)

        # Use stored instance variables
        scope_text = self.confirmation_scope_text
        time_period_text = self.confirmation_time_period_text

        try:
            if self.schedule_data:
                schedule_id = await self.db_manager.create_advanced_reset_schedule(
                    guild_id=interaction.guild.id,
                    requested_by_id=interaction.user.id,
                    reset_types=[self.stat_type],
                    schedule_type="recurring",
                    recurring_pattern=self.schedule_data['pattern'],
                    recurring_weekdays=self.schedule_data.get('weekdays'),
                    recurring_days_of_month=self.schedule_data.get(
                        'month_days'),
                    recurring_times=self.schedule_data.get('times'),
                    recurring_interval_days=self.schedule_data.get(
                        'interval_days'),
                    time_period_days=self.time_period_days if self.time_option == 'days' else None,
                    delete_from_date=self.date_range_from if self.time_option == 'range' else None,
                    delete_to_date=self.date_range_to if self.time_option == 'range' else None,
                    scope_type=self.scope,
                    scope_details=f"{scope_text}",
                    channel_id=self.channel_id,
                    category_id=self.category_id,
                    schedule_name=self.schedule_data.get('schedule_name'),
                    enabled=True
                )

                embed = discord.Embed(
                    title="Reset Scheduled!",
                    color=discord.Color.green(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(name="Stat Type",
                                value=f"`{self.stat_type}`", inline=True)
                embed.add_field(name="Target", value=scope_text, inline=True)
                embed.add_field(name="Time Period",
                                value=time_period_text, inline=False)
                embed.add_field(
                    name="Schedule", value=self.schedule_description, inline=False)
                embed.add_field(name="Schedule ID",
                                value=f"`{schedule_id}`", inline=True)

                if self.schedule_data.get('schedule_name'):
                    embed.add_field(
                        name="Schedule Name", value=self.schedule_data['schedule_name'], inline=True)

                embed.add_field(
                    name="Manage Schedules",
                    value="Use `/reset schedules` to view and delete schedules.\nEdit everything related to the schedule through the [web dashboard](https://statshq.xyz/Dashboard/Reset/).",
                    inline=False
                )
            else:
                if self.command_type == "server":
                    result = await self.db_manager.reset_server_stats(
                        guild_id=interaction.guild.id,
                        stat_type=self.stat_type,
                        channel_id=self.channel_id,
                        category_id=self.category_id,
                        time_period_days=self.time_period_days if self.time_option == 'days' else None,
                        delete_from_date=self.date_range_from if self.time_option == 'range' else None,
                        delete_to_date=self.date_range_to if self.time_option == 'range' else None
                    )
                    if isinstance(result, dict):
                        total = sum(int(str(count).split()[0]) if str(
                            count).isdigit() else 0 for count in result.values())
                    else:
                        total = result if isinstance(result, int) else 0

                    embed = self.create_embed(
                        "Reset Successful!",
                        f"Successfully deleted **{self.stat_type}** from **{scope_text}**!\n\n"
                        f"**Total: {total} records deleted.**",
                        color=0x00ff00
                    )
                else:
                    target_user = self.target_user_id if self.target_user_id else interaction.user.id
                    result = await self.db_manager.reset_user_stats(
                        guild_id=interaction.guild.id,
                        user_id=target_user,
                        stat_type=self.stat_type,
                        channel_id=self.channel_id,
                        category_id=self.category_id,
                        time_period_days=self.time_period_days if self.time_option == 'days' else None,
                        delete_from_date=self.date_range_from if self.time_option == 'range' else None,
                        delete_to_date=self.date_range_to if self.time_option == 'range' else None
                    )
                    if isinstance(result, dict):
                        total = sum(int(str(count).split()[0]) if str(
                            count).isdigit() else 0 for count in result.values())
                    else:
                        total = result if isinstance(result, int) else 0

                    user_text = f"<@{target_user}>" if self.target_user_id else "your"
                    embed = self.create_embed(
                        "Reset Successful!",
                        f"Successfully deleted **{self.stat_type}** for {user_text} stats from **{scope_text}**!\n\n"
                        f"**Total: {total} records deleted.**",
                        color=0x00ff00
                    )

            await interaction.edit_original_response(embed=embed, view=None)

        except Exception as e:
            logger.error(f"Reset failed: {e}")
            logger.error(traceback.format_exc())
            error_embed = self.create_embed(
                "Reset Failed!",
                f"An error occurred: ```{str(e)[:1000]}```\n\nPlease try again or contact support."
            )
            await interaction.edit_original_response(embed=error_embed, view=None)

    @rate_limited(RateLimitType.MESSAGE, timeout=30.0)
    async def page6_back_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.interaction.user.id:
            await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
            return
        await interaction.response.defer()
        await self.show_advanced_schedule()

# =========================================================
# INTERNAL FUNCTION
# =========================================================


@rate_limited(RateLimitType.MESSAGE, timeout=30.0)
async def _handle_reset_command(self, ctx_or_interaction, command_type: str, target_user: Optional[discord.User] = None, is_interaction: bool = False):
    try:
        if is_interaction:
            user = ctx_or_interaction.user
            guild = ctx_or_interaction.guild
            send_method = ctx_or_interaction.response.send_message
        else:
            user = ctx_or_interaction.author
            guild = ctx_or_interaction.guild
            send_method = ctx_or_interaction.send

        if not self.db_manager or not self.db_pool:
            if is_interaction:
                await send_method("Database connection not ready. Please try again in a moment.", ephemeral=True)
            else:
                await send_method("Database connection not ready. Please try again in a moment.", delete_after=10)
            return

        try:
            async with self.db_pool.acquire() as conn:
                await conn.fetchval('SELECT 1')
        except Exception as e:
            if is_interaction:
                await send_method(f"Database connection error: {str(e)[:200]}", ephemeral=True)
            else:
                await send_method(f"Database connection error: {str(e)[:200]}", delete_after=10)
            return

        has_permission = await self.check_reset_permissions(ctx_or_interaction if is_interaction else guild, user, command_type, target_user)
        if not has_permission:
            settings_cog = self.bot.get_cog("Settings")
            if settings_cog:
                settings = await settings_cog.get_guild_settings(guild.id)
                permission_level = settings.get('permission_level', 'Default')
                required_permission = "Manage Server" if permission_level == "Moderator" else "Administrator"

                embed = discord.Embed(
                    title="Permission Denied",
                    description=f"You need the `{required_permission}` permission to access this command.",
                    color=discord.Color.red()
                )
                if is_interaction:
                    await send_method(embed=embed, ephemeral=True)
                else:
                    await send_method(embed=embed, delete_after=10)
                return
            else:
                embed = discord.Embed(
                    title="Permission Denied",
                    description="You need the `Administrator` permission to access this command.",
                    color=discord.Color.red()
                )
                if is_interaction:
                    await send_method(embed=embed, ephemeral=True)
                else:
                    await send_method(embed=embed, delete_after=10)
                return

        target_user_id = None
        if command_type == "user":
            target_user_id = target_user.id if target_user else user.id

        if not is_interaction:
            embed = discord.Embed(
                title=f"{'Server' if command_type == 'server' else 'User'} Stats Reset",
                description="This command allows you to reset statistics. Please follow the 6-step process.\n\n"
                "**Note:** This action is irreversible!",
                color=0xff0000
            )
            embed.set_footer(text="Stats Reset System")

            message = await send_method(embed=embed)

            class FakeInteraction:
                def __init__(self, guild, user, message):
                    self.guild = guild
                    self.user = user
                    self.response = type('obj', (object,), {
                                         'edit_message': lambda **kwargs: message.edit(**kwargs)})()
                    self.edit_original_response = message.edit
                    self.original_response = lambda: message

            fake_interaction = FakeInteraction(guild, user, message)
            view = ResetView(fake_interaction, self.db_manager,
                             command_type, target_user_id, bot=self.bot)
            self.active_sessions[message.id] = {
                'guild_id': guild.id, 'user_id': user.id, 'target_user_id': target_user_id,
                'command_type': command_type, 'view': view
            }
            await view.show_page_1()

        else:
            view = ResetView(ctx_or_interaction, self.db_manager,
                             command_type, target_user_id, bot=self.bot)
            embed = view.create_embed(
                f"{'Server' if command_type == 'server' else 'User'} Stats Reset",
                "This command allows you to reset statistics. Please follow the 6-step process.\n\n"
                "**Note:** This action is irreversible!"
            )
            await send_method(embed=embed, view=view, ephemeral=True)
            await view.show_page_1()

            message = await ctx_or_interaction.original_response()
            self.active_sessions[message.id] = {
                'guild_id': guild.id, 'user_id': user.id, 'target_user_id': target_user_id,
                'command_type': command_type, 'view': view
            }

    except Exception as e:
        logger.error(f"Error in _handle_reset_command: {e}")
        if is_interaction:
            try:
                await ctx_or_interaction.followup.send("An error occurred while setting up the reset command.", ephemeral=True)
            except:
                pass
        else:
            try:
                await ctx_or_interaction.send("An error occurred while setting up the reset command.", delete_after=10)
            except:
                pass


# =========================================================
# MAIN COG CLASS
# =========================================================

class ResetStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_pool = None
        self.db_manager = None
        self.active_sessions = {}
        self.rate_limiter = get_rate_limiter()
        self.schedule_check_task = None
        self._schedule_checker_started = False

    async def create_db_pool(self):
        try:
            db_host = os.getenv('DB_HOST', 'localhost')
            db_port = int(os.getenv('DB_PORT', 5432))
            db_user = os.getenv('DB_USER')
            db_password = os.getenv('DB_PASSWORD')
            db_name = os.getenv('DB_NAME')

            if not all([db_user, db_password, db_name]):
                logger.error("Missing database environment variables!")
                return False

            self.db_pool = await asyncpg.create_pool(
                host=db_host, port=db_port, user=db_user, password=db_password,
                database=db_name, min_size=1, max_size=10, command_timeout=60
            )

            self.db_manager = DatabaseManager(self.db_pool)
            return True

        except Exception as e:
            logger.error(f"Failed to create database pool: {e}")
            logger.error(traceback.format_exc())
            self.db_pool = None
            self.db_manager = None
            return False

    async def cog_load(self):
        success = await self.create_db_pool()
        if not success:
            logger.error("Failed to establish database connection!")

    async def cog_unload(self):
        if self.db_pool:
            await self.db_pool.close()

    async def check_reset_permissions(self, interaction_or_guild, user: discord.Member, command_type: str, target_user: Optional[discord.User] = None) -> bool:
        if isinstance(interaction_or_guild, discord.Interaction):
            guild = interaction_or_guild.guild
        else:
            guild = interaction_or_guild

        if user.guild_permissions.administrator:
            return True

        settings_cog = self.bot.get_cog("Settings")
        if not settings_cog:
            return False

        settings = await settings_cog.get_guild_settings(guild.id)
        permission_level = settings.get('permission_level', 'Default')

        if command_type == "server":
            if permission_level == "All":
                return True
            elif permission_level == "Moderator":
                return user.guild_permissions.manage_guild
            return False

        elif command_type == "user":
            if permission_level == "All":
                return True
            elif permission_level == "Default" or permission_level == "User Restriction":
                if target_user and target_user.id != user.id:
                    return False
                return True
            elif permission_level == "Moderator":
                return user.guild_permissions.manage_guild
            return False

        return False

    async def check_and_execute_scheduled_resets(self):
        """Find any due reset schedules and run them, called periodically by DatabaseStats' cron."""
        if not self.db_manager:
            logger.warning(
                "check_and_execute_scheduled_resets called but db_manager not ready")
            return

        try:
            due_schedules = await self.db_manager.get_due_reset_schedules()
        except Exception as e:
            logger.error(f"Failed to fetch due reset schedules: {e}")
            logger.error(traceback.format_exc())
            return

        if not due_schedules:
            return

        logger.info(
            f"Found {len(due_schedules)} due reset schedule(s) to execute")

        for schedule in due_schedules:
            schedule_id = schedule['id']
            try:
                results = await self.db_manager.execute_scheduled_reset(schedule)
                await self.db_manager.mark_schedule_completed(schedule_id)
                logger.info(
                    f"Executed schedule {schedule_id} (guild {schedule['guild_id']}): {results}")
            except Exception as e:
                logger.error(
                    f"Failed to execute scheduled reset {schedule_id}: {e}")
                logger.error(traceback.format_exc())

    # =========================================================
    # PREFIX COMMANDS
    # =========================================================

    @commands.group(name="reset", invoke_without_command=True)
    async def reset_group_prefix(self, ctx: commands.Context):
        await ctx.send("Available commands:\n- `reset server` - Reset server statistics\n- `reset user [member]` - Reset user statistics\n- `rs` - Shortcut for reset server\n- `ru [member]` - Shortcut for reset user")

    @reset_group_prefix.command(name="server")
    async def reset_server_prefix(self, ctx: commands.Context):
        await _handle_reset_command(self, ctx, "server", is_interaction=False)

    @reset_group_prefix.command(name="user")
    async def reset_user_prefix(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        await _handle_reset_command(self, ctx, "user", member, is_interaction=False)

    @commands.command(name="rs")
    async def reset_server_shortcut(self, ctx: commands.Context):
        await _handle_reset_command(self, ctx, "server", is_interaction=False)

    @commands.command(name="ru")
    async def reset_user_shortcut(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        await _handle_reset_command(self, ctx, "user", member, is_interaction=False)

    # =========================================================
    # SLASH COMMANDS
    # =========================================================

    reset_group = app_commands.Group(
        name="reset", description="Reset statistics commands")

    @reset_group.command(name="server", description="Reset server statistics")
    async def reset_server(self, interaction: discord.Interaction):
        await _handle_reset_command(self, interaction, "server", is_interaction=True)

    @reset_group.command(name="user", description="Reset user statistics")
    @app_commands.describe(user="Optional: User to reset stats for")
    async def reset_user(self, interaction: discord.Interaction, user: Optional[discord.User] = None):
        await _handle_reset_command(self, interaction, "user", user, is_interaction=True)

    @reset_group.command(name="schedules", description="View and delete reset schedules (Admin only)")
    @app_commands.default_permissions(administrator=True)
    async def view_schedules(self, interaction: discord.Interaction):
        if not self.db_manager:
            embed = discord.Embed(
                title="Error", description="Database not ready.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        try:
            guild_schedules = await self.db_manager.get_all_schedules_for_guild(interaction.guild.id)

            if not guild_schedules:
                embed = discord.Embed(
                    title="Reset Schedules",
                    description="No reset schedules found for this server.\n\nYou can create schedules using the `/reset` command.",
                    color=discord.Color.blue(),
                    timestamp=datetime.now(timezone.utc)
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            view = ScheduleView(guild_schedules, self.db_manager,
                                interaction.guild.id, interaction.user.id, interaction.guild)
            await interaction.response.send_message(embed=view.create_embed(), view=view, ephemeral=True)

        except Exception as e:
            logger.error(f"Error in view_schedules: {e}")
            embed = discord.Embed(title="Error", description=str(e)[
                                  :200], color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)

    # ERROR HANDLING
    @reset_server.error
    async def reset_server_error(self, interaction: discord.Interaction, error):
        logger.error(f"Reset server error: {error}")
        logger.error(traceback.format_exc())
        embed = discord.Embed(
            title="Error", description=f"An error occurred: ```{str(error)[:500]}```", color=0xff0000)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @reset_user.error
    async def reset_user_error(self, interaction: discord.Interaction, error):
        logger.error(f"Reset user error: {error}")
        logger.error(traceback.format_exc())
        embed = discord.Embed(
            title="Error", description=f"An error occurred: ```{str(error)[:500]}```", color=0xff0000)
        await interaction.response.send_message(embed=embed, ephemeral=True)


# =========================================================
# SETUP
# =========================================================

async def setup(bot):
    cog = ResetStats(bot)
    await bot.add_cog(cog)
