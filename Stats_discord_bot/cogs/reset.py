import discord
from discord import app_commands
from discord.ui import View, Select, Button, Modal, TextInput
from discord.ext import commands
from typing import Optional, Literal, List
import asyncpg
import os
from dotenv import load_dotenv
import logging
import asyncio
import traceback
from pathlib import Path
from datetime import datetime, timezone, timedelta
from .ratelimiter import RateLimiter, RateLimitType, rate_limited, get_rate_limiter

# CONFIGURATION

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent


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
    # SCHEDULED RESET METHODS
    # ======================================================================

    async def create_reset_schedule(self, guild_id: int, requested_by_id: int,
                                    reset_types: List[str], target_time: datetime,
                                    reason: Optional[str] = None) -> int:
        """Create a new reset schedule in the database"""
        try:
            async with self.pool.acquire() as conn:
                result = await conn.fetchrow("""
                    INSERT INTO reset_schedules (guild_id, requested_by_id, reset_types, target_time, reason)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id
                """, guild_id, requested_by_id, reset_types, target_time, reason)

                schedule_id = result['id'] if result else None
                logger.info(
                    f"Created reset schedule {schedule_id} for guild {guild_id} at {target_time}")
                return schedule_id

        except Exception as e:
            logger.error(f"Failed to create reset schedule: {e}")
            logger.error(traceback.format_exc())
            raise

    async def get_pending_reset_schedules(self, lookahead_hours: int = 12) -> List[dict]:
        """Get all pending reset schedules within the next X hours"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT id, guild_id, requested_by_id, target_time, reset_types, reason
                    FROM reset_schedules
                    WHERE completed = FALSE 
                    AND target_time <= NOW() + make_interval(hours => $1)
                    ORDER BY target_time ASC
                """, lookahead_hours)

                return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get pending reset schedules: {e}")
            logger.error(traceback.format_exc())
            return []

    async def get_due_reset_schedules(self) -> List[dict]:
        """Get all reset schedules that are due for execution (target_time <= now)"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT id, guild_id, requested_by_id, target_time, reset_types, reason
                    FROM reset_schedules
                    WHERE completed = FALSE 
                    AND target_time <= NOW()
                    ORDER BY target_time ASC
                """)

                return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get due reset schedules: {e}")
            logger.error(traceback.format_exc())
            return []

    async def mark_schedule_completed(self, schedule_id: int, executed_at: datetime = None):
        """Mark a reset schedule as completed"""
        try:
            if executed_at is None:
                executed_at = datetime.now(timezone.utc)

            async with self.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE reset_schedules 
                    SET completed = TRUE, executed_at = $2
                    WHERE id = $1
                """, schedule_id, executed_at)

                logger.info(
                    f"Marked schedule {schedule_id} as completed at {executed_at}")

        except Exception as e:
            logger.error(
                f"Failed to mark schedule {schedule_id} as completed: {e}")
            logger.error(traceback.format_exc())
            raise

    async def execute_scheduled_reset(self, schedule: dict) -> dict:
        """Execute a scheduled reset based on schedule data"""
        try:
            guild_id = schedule['guild_id']
            reset_types = schedule['reset_types']

            results = {}

            for reset_type in reset_types:
                try:
                    result = await self.reset_server_stats(
                        guild_id=guild_id,
                        stat_type=reset_type,
                        channel_id=None,
                        category_id=None
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

    async def cancel_schedule(self, schedule_id: int, guild_id: int) -> bool:
        """Cancel a pending reset schedule"""
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute("""
                    DELETE FROM reset_schedules 
                    WHERE id = $1 AND guild_id = $2 AND completed = FALSE
                """, schedule_id, guild_id)

                return result.split()[-1] == '1'
        except Exception as e:
            logger.error(f"Failed to cancel schedule {schedule_id}: {e}")
            return False

    # ======================================================================
    # SERVER DELETION LOGIC
    # ======================================================================

    async def delete_server_all(self, guild_id: int,
                                channel_id: Optional[int] = None,
                                category_id: Optional[int] = None,
                                time_period_days: Optional[int] = None):

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
                                     time_period_days: Optional[int] = None):

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
                                  time_period_days: Optional[int] = None):

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

    async def delete_server_invites(self, guild_id: int, time_period_days: Optional[int] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    if time_period_days:
                        result = await conn.execute(f"DELETE FROM invite_tracking WHERE guild_id = $1 AND created_at >= NOW() - INTERVAL '{time_period_days} days'", guild_id)
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
                                  time_period_days: Optional[int] = None):

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

                    where_clause = " AND ".join(conditions)
                    result = await conn.execute(f"DELETE FROM emoji_usage_hourly WHERE {where_clause}", *params)
                    deleted_count = result.split()[-1]
                    return int(deleted_count) if deleted_count.isdigit() else 0

        except Exception as e:
            logger.error(f"Error in delete_server_emoji: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_server_activity(self, guild_id: int, time_period_days: Optional[int] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    deleted_counts = {}

                    if time_period_days:
                        result1 = await conn.execute(f"DELETE FROM activity_sessions_hourly WHERE guild_id = $1 AND hour >= NOW() - INTERVAL '{time_period_days} days'", guild_id)
                        result2 = await conn.execute(f"DELETE FROM daily_activity_log WHERE guild_id = $1 AND day >= NOW() - INTERVAL '{time_period_days} days'", guild_id)
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
                                     time_period_days: Optional[int] = None):

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

                    where_clause = " AND ".join(conditions)
                    result = await conn.execute(f"DELETE FROM user_mentions_hourly WHERE {where_clause}", *params)
                    deleted_count = result.split()[-1]
                    return int(deleted_count) if deleted_count.isdigit() else 0

        except Exception as e:
            logger.error(f"Error in delete_server_mentions: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_server_role_growth(self, guild_id: int, time_period_days: Optional[int] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    if time_period_days:
                        result = await conn.execute(f"DELETE FROM role_growth_hourly WHERE guild_id = $1 AND hour >= NOW() - INTERVAL '{time_period_days} days'", guild_id)
                    else:
                        result = await conn.execute(f"DELETE FROM role_growth_hourly WHERE guild_id = $1", guild_id)
                    deleted_count = result.split()[-1]
                    return int(deleted_count) if deleted_count.isdigit() else 0

        except Exception as e:
            logger.error(f"Error in delete_server_role_growth: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_server_member_growth(self, guild_id: int, time_period_days: Optional[int] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    deleted_counts = {}

                    if time_period_days:
                        result1 = await conn.execute(f"DELETE FROM member_joins_hourly WHERE guild_id = $1 AND hour >= NOW() - INTERVAL '{time_period_days} days'", guild_id)
                        result2 = await conn.execute(f"DELETE FROM member_leaves_hourly WHERE guild_id = $1 AND hour >= NOW() - INTERVAL '{time_period_days} days'", guild_id)
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
                              time_period_days: Optional[int] = None):

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

                    where_clause = " AND ".join(conditions)

                    deleted_counts = {}

                    tables_with_user_and_channel = [
                        'message_tracking_hourly',
                        'voice_session_history_hourly',
                        'emoji_usage_hourly'
                    ]

                    for table in tables_with_user_and_channel:
                        try:
                            result = await conn.execute(f"DELETE FROM {table} WHERE {where_clause}", *params)
                            deleted_counts[table] = result.split()[-1]
                        except Exception as e:
                            logger.warning(f"Error deleting from {table}: {e}")
                            deleted_counts[table] = "0 (error)"

                    mention_conditions = [
                        "guild_id = $1", "(mentioned_user_id = $2 OR mentioner_user_id = $2)"]
                    mention_params = [guild_id, user_id]
                    mention_counter = 3

                    if channel_id:
                        mention_conditions.append(
                            f"channel_id = ${mention_counter}")
                        mention_params.append(channel_id)
                        mention_counter += 1

                    if category_id:
                        mention_conditions.append(
                            f"category_id = ${mention_counter}")
                        mention_params.append(category_id)
                        mention_counter += 1

                    if time_period_days:
                        mention_conditions.append(
                            f"hour >= NOW() - INTERVAL '{time_period_days} days'")

                    mention_where = " AND ".join(mention_conditions)
                    result = await conn.execute(f"DELETE FROM user_mentions_hourly WHERE {mention_where}", *mention_params)
                    deleted_counts['user_mentions_hourly'] = result.split()[-1]

                    if not channel_id and not category_id:
                        if time_period_days:
                            result = await conn.execute(f"DELETE FROM role_growth_hourly WHERE guild_id = $1 AND user_id = $2 AND hour >= NOW() - INTERVAL '{time_period_days} days'",
                                                        guild_id, user_id)
                        else:
                            result = await conn.execute(f"DELETE FROM role_growth_hourly WHERE guild_id = $1 AND user_id = $2",
                                                        guild_id, user_id)
                        deleted_counts['role_growth_hourly'] = result.split(
                        )[-1]

                        if time_period_days:
                            result = await conn.execute(f"""
                                DELETE FROM invite_tracking 
                                WHERE guild_id = $1 AND (inviter_id = $2 OR invitee_id = $2)
                                AND created_at >= NOW() - INTERVAL '{time_period_days} days'
                            """, guild_id, user_id)
                        else:
                            result = await conn.execute(f"""
                                DELETE FROM invite_tracking 
                                WHERE guild_id = $1 AND (inviter_id = $2 OR invitee_id = $2)
                            """, guild_id, user_id)
                        deleted_counts['invite_tracking'] = result.split()[-1]

                        if time_period_days:
                            result1 = await conn.execute(f"DELETE FROM activity_sessions_hourly WHERE guild_id = $1 AND user_id = $2 AND hour >= NOW() - INTERVAL '{time_period_days} days'",
                                                         guild_id, user_id)
                            result2 = await conn.execute(f"DELETE FROM daily_activity_log WHERE guild_id = $1 AND user_id = $2 AND day >= NOW() - INTERVAL '{time_period_days} days'",
                                                         guild_id, user_id)
                        else:
                            result1 = await conn.execute(f"DELETE FROM activity_sessions_hourly WHERE guild_id = $1 AND user_id = $2",
                                                         guild_id, user_id)
                            result2 = await conn.execute(f"DELETE FROM daily_activity_log WHERE guild_id = $1 AND user_id = $2",
                                                         guild_id, user_id)

                        result3 = await conn.execute(f"DELETE FROM activity_streaks WHERE guild_id = $1 AND user_id = $2",
                                                     guild_id, user_id)
                        deleted_counts['activity_sessions_hourly'] = result1.split(
                        )[-1]
                        deleted_counts['daily_activity_log'] = result2.split(
                        )[-1]
                        deleted_counts['activity_streaks'] = result3.split()[-1]

                        if time_period_days:
                            result4 = await conn.execute(f"DELETE FROM member_joins_hourly WHERE guild_id = $1 AND user_id = $2 AND hour >= NOW() - INTERVAL '{time_period_days} days'",
                                                         guild_id, user_id)
                            result5 = await conn.execute(f"DELETE FROM member_leaves_hourly WHERE guild_id = $1 AND user_id = $2 AND hour >= NOW() - INTERVAL '{time_period_days} days'",
                                                         guild_id, user_id)
                        else:
                            result4 = await conn.execute(f"DELETE FROM member_joins_hourly WHERE guild_id = $1 AND user_id = $2",
                                                         guild_id, user_id)
                            result5 = await conn.execute(f"DELETE FROM member_leaves_hourly WHERE guild_id = $1 AND user_id = $2",
                                                         guild_id, user_id)
                        deleted_counts['member_joins_hourly'] = result4.split(
                        )[-1]
                        deleted_counts['member_leaves_hourly'] = result5.split(
                        )[-1]

                    return deleted_counts

        except Exception as e:
            logger.error(f"Error in delete_user_all: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_user_messages(self, guild_id: int, user_id: int,
                                   channel_id: Optional[int] = None,
                                   category_id: Optional[int] = None,
                                   time_period_days: Optional[int] = None):

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
                                time_period_days: Optional[int] = None):

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

                    where_clause = " AND ".join(conditions)
                    deleted_counts = {}
                    result1 = await conn.execute(f"DELETE FROM voice_session_history_hourly WHERE {where_clause}", *params)
                    deleted_counts['voice_session_history_hourly'] = result1.split(
                    )[-1]
                    return deleted_counts

        except Exception as e:
            logger.error(f"Error in delete_user_voice: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_user_invites(self, guild_id: int, user_id: int, time_period_days: Optional[int] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    if time_period_days:
                        result = await conn.execute(f"""
                            DELETE FROM invite_tracking 
                            WHERE guild_id = $1 AND (inviter_id = $2 OR invitee_id = $2)
                            AND created_at >= NOW() - INTERVAL '{time_period_days} days'
                        """, guild_id, user_id)
                    else:
                        result = await conn.execute(f"""
                            DELETE FROM invite_tracking 
                            WHERE guild_id = $1 AND (inviter_id = $2 OR invitee_id = $2)
                        """, guild_id, user_id)
                    deleted_count = result.split()[-1]
                    return int(deleted_count) if deleted_count.isdigit() else 0

        except Exception as e:
            logger.error(f"Error in delete_user_invites: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_user_emoji(self, guild_id: int, user_id: int,
                                channel_id: Optional[int] = None,
                                category_id: Optional[int] = None,
                                time_period_days: Optional[int] = None):

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

                    where_clause = " AND ".join(conditions)
                    result = await conn.execute(f"DELETE FROM emoji_usage_hourly WHERE {where_clause}", *params)
                    deleted_count = result.split()[-1]
                    return int(deleted_count) if deleted_count.isdigit() else 0

        except Exception as e:
            logger.error(f"Error in delete_user_emoji: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_user_activity(self, guild_id: int, user_id: int, time_period_days: Optional[int] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    deleted_counts = {}

                    if time_period_days:
                        result1 = await conn.execute(f"DELETE FROM activity_sessions_hourly WHERE guild_id = $1 AND user_id = $2 AND hour >= NOW() - INTERVAL '{time_period_days} days'",
                                                     guild_id, user_id)
                        result2 = await conn.execute(f"DELETE FROM daily_activity_log WHERE guild_id = $1 AND user_id = $2 AND day >= NOW() - INTERVAL '{time_period_days} days'",
                                                     guild_id, user_id)
                    else:
                        result1 = await conn.execute(f"DELETE FROM activity_sessions_hourly WHERE guild_id = $1 AND user_id = $2",
                                                     guild_id, user_id)
                        result2 = await conn.execute(f"DELETE FROM daily_activity_log WHERE guild_id = $1 AND user_id = $2",
                                                     guild_id, user_id)

                    result3 = await conn.execute(f"DELETE FROM activity_streaks WHERE guild_id = $1 AND user_id = $2",
                                                 guild_id, user_id)
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
                                   time_period_days: Optional[int] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    conditions = [
                        "guild_id = $1", "(mentioned_user_id = $2 OR mentioner_user_id = $2)"]
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

                    where_clause = " AND ".join(conditions)
                    result = await conn.execute(f"DELETE FROM user_mentions_hourly WHERE {where_clause}", *params)
                    deleted_count = result.split()[-1]
                    return int(deleted_count) if deleted_count.isdigit() else 0

        except Exception as e:
            logger.error(f"Error in delete_user_mentions: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_user_role_growth(self, guild_id: int, user_id: int, time_period_days: Optional[int] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    if time_period_days:
                        result = await conn.execute(f"DELETE FROM role_growth_hourly WHERE guild_id = $1 AND user_id = $2 AND hour >= NOW() - INTERVAL '{time_period_days} days'",
                                                    guild_id, user_id)
                    else:
                        result = await conn.execute(f"DELETE FROM role_growth_hourly WHERE guild_id = $1 AND user_id = $2",
                                                    guild_id, user_id)
                    deleted_count = result.split()[-1]
                    return int(deleted_count) if deleted_count.isdigit() else 0

        except Exception as e:
            logger.error(f"Error in delete_user_role_growth: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_user_member_growth(self, guild_id: int, user_id: int, time_period_days: Optional[int] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    deleted_counts = {}

                    if time_period_days:
                        result1 = await conn.execute(f"DELETE FROM member_joins_hourly WHERE guild_id = $1 AND user_id = $2 AND hour >= NOW() - INTERVAL '{time_period_days} days'",
                                                     guild_id, user_id)
                        result2 = await conn.execute(f"DELETE FROM member_leaves_hourly WHERE guild_id = $1 AND user_id = $2 AND hour >= NOW() - INTERVAL '{time_period_days} days'",
                                                     guild_id, user_id)
                    else:
                        result1 = await conn.execute(f"DELETE FROM member_joins_hourly WHERE guild_id = $1 AND user_id = $2",
                                                     guild_id, user_id)
                        result2 = await conn.execute(f"DELETE FROM member_leaves_hourly WHERE guild_id = $1 AND user_id = $2",
                                                     guild_id, user_id)

                    deleted_counts['member_joins_hourly'] = result1.split()[-1]
                    deleted_counts['member_leaves_hourly'] = result2.split()[-1]
                    return deleted_counts

        except Exception as e:
            logger.error(f"Error in delete_user_member_growth: {e}")
            logger.error(traceback.format_exc())
            raise

    # ======================================================================
    # RESET METHODS
    # ======================================================================

    async def reset_server_stats(self, guild_id: int, stat_type: str,
                                 channel_id: Optional[int] = None,
                                 category_id: Optional[int] = None,
                                 time_period_days: Optional[int] = None):

        try:
            stat_type_lower = stat_type.lower()
            result = None

            if stat_type_lower == "all":
                result = await self.delete_server_all(guild_id, channel_id, category_id, time_period_days)
            elif stat_type_lower == "messages":
                result = await self.delete_server_messages(guild_id, channel_id, category_id, time_period_days)
            elif stat_type_lower == "voice activity":
                result = await self.delete_server_voice(guild_id, channel_id, category_id, time_period_days)
            elif stat_type_lower == "invite tracking":
                result = await self.delete_server_invites(guild_id, time_period_days)
            elif stat_type_lower == "emoji stats":
                result = await self.delete_server_emoji(guild_id, channel_id, category_id, time_period_days)
            elif stat_type_lower == "activity":
                result = await self.delete_server_activity(guild_id, time_period_days)
            elif stat_type_lower == "mentions":
                result = await self.delete_server_mentions(guild_id, channel_id, category_id, time_period_days)
            elif stat_type_lower == "role growth":
                result = await self.delete_server_role_growth(guild_id, time_period_days)
            elif stat_type_lower == "member growth":
                result = await self.delete_server_member_growth(guild_id, time_period_days)

            return result

        except Exception as e:
            logger.error(f"Failed to reset server stats: {e}")
            logger.error(traceback.format_exc())
            raise

    async def reset_user_stats(self, guild_id: int, user_id: int, stat_type: str,
                               channel_id: Optional[int] = None,
                               category_id: Optional[int] = None,
                               time_period_days: Optional[int] = None):

        try:
            stat_type_lower = stat_type.lower()
            result = None

            if stat_type_lower == "all":
                result = await self.delete_user_all(guild_id, user_id, channel_id, category_id, time_period_days)
            elif stat_type_lower == "messages":
                result = await self.delete_user_messages(guild_id, user_id, channel_id, category_id, time_period_days)
            elif stat_type_lower == "voice activity":
                result = await self.delete_user_voice(guild_id, user_id, channel_id, category_id, time_period_days)
            elif stat_type_lower == "invite tracking":
                result = await self.delete_user_invites(guild_id, user_id, time_period_days)
            elif stat_type_lower == "emoji stats":
                result = await self.delete_user_emoji(guild_id, user_id, channel_id, category_id, time_period_days)
            elif stat_type_lower == "activity":
                result = await self.delete_user_activity(guild_id, user_id, time_period_days)
            elif stat_type_lower == "mentions":
                result = await self.delete_user_mentions(guild_id, user_id, channel_id, category_id, time_period_days)
            elif stat_type_lower == "role growth":
                result = await self.delete_user_role_growth(guild_id, user_id, time_period_days)
            elif stat_type_lower == "member growth":
                result = await self.delete_user_member_growth(guild_id, user_id, time_period_days)

            return result

        except Exception as e:
            logger.error(f"Failed to reset user stats: {e}")
            logger.error(traceback.format_exc())
            raise


# =========================================================
# CANCEL SCHEDULE MODAL
# =========================================================

class CancelScheduleModal(Modal, title="Cancel Reset Schedule"):
    def __init__(self, db_manager, guild_id: int, current_view):
        super().__init__(timeout=300)
        self.db_manager = db_manager
        self.guild_id = guild_id
        self.current_view = current_view

        self.schedule_id_input = TextInput(
            label="Schedule ID",
            placeholder="Enter the ID of the schedule to cancel",
            min_length=1,
            max_length=10,
            required=True
        )
        self.add_item(self.schedule_id_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            schedule_id = int(self.schedule_id_input.value.strip())

            async with self.db_manager.pool.acquire() as conn:
                schedule = await conn.fetchrow("""
                    SELECT id, completed, reset_types, target_time, reason
                    FROM reset_schedules
                    WHERE id = $1 AND guild_id = $2
                """, schedule_id, self.guild_id)

                if not schedule:
                    embed = discord.Embed(
                        title="❌ Cancellation Failed",
                        description=f"Schedule #{schedule_id} not found in this server.",
                        color=discord.Color.red()
                    )
                    await interaction.response.edit_message(embed=embed, view=None)
                    return

                if schedule['completed']:
                    embed = discord.Embed(
                        title="❌ Cancellation Failed",
                        description=f"Schedule #{schedule_id} has already been completed and cannot be cancelled.",
                        color=discord.Color.red()
                    )
                    await interaction.response.edit_message(embed=embed, view=None)
                    return

                await conn.execute("""
                    DELETE FROM reset_schedules 
                    WHERE id = $1 AND guild_id = $2
                """, schedule_id, self.guild_id)

                target_time = schedule['target_time']
                reset_types = "', '".join(schedule['reset_types'])

                embed = discord.Embed(
                    title="✅ Schedule Cancelled",
                    description=f"Schedule #{schedule_id} has been successfully cancelled.",
                    color=discord.Color.green(),
                    timestamp=datetime.now(timezone.utc)
                )
                embed.add_field(name="Reset Types",
                                value=f"`{reset_types}`", inline=False)
                embed.add_field(
                    name="Scheduled Time", value=f"<t:{int(target_time.timestamp())}:F>", inline=True)
                if schedule['reason']:
                    embed.add_field(
                        name="Reason", value=schedule['reason'][:200], inline=False)

                # Refresh the schedules list and show updated view
                new_schedules = await self.db_manager.get_pending_reset_schedules(lookahead_hours=720)
                new_schedules = [
                    s for s in new_schedules if s['guild_id'] == self.guild_id]

                if new_schedules:
                    new_view = ScheduleView(
                        new_schedules, self.db_manager, self.guild_id, interaction.user.id)
                    await interaction.response.edit_message(embed=new_view.create_embed(), view=new_view)
                else:
                    embed = discord.Embed(
                        title="📅 Pending Reset Schedules",
                        description="📭 No pending reset schedules found.",
                        color=discord.Color.blue(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    await interaction.response.edit_message(embed=embed, view=None)

        except ValueError:
            embed = discord.Embed(
                title="❌ Cancellation Failed",
                description="Invalid Schedule ID. Please enter a valid number.",
                color=discord.Color.red()
            )
            await interaction.response.edit_message(embed=embed, view=self.current_view)
        except Exception as e:
            embed = discord.Embed(
                title="❌ Cancellation Failed",
                description=f"An error occurred: {str(e)[:200]}",
                color=discord.Color.red()
            )
            await interaction.response.edit_message(embed=embed, view=self.current_view)


# =========================================================
# SCHEDULE VIEW (1 schedule per page with proper button layout)
# =========================================================

class ScheduleView(View):
    def __init__(self, schedules: List[dict], db_manager, guild_id: int, user_id: int):
        super().__init__(timeout=180)
        self.schedules = schedules
        self.db_manager = db_manager
        self.guild_id = guild_id
        self.user_id = user_id
        self.current_index = 0
        self._update_buttons()

    def _update_buttons(self):
        self.clear_items()

        total_schedules = len(self.schedules)

        # Row 0: Navigation buttons
        # Previous button
        prev_button = Button(
            label="◀ Previous",
            style=discord.ButtonStyle.secondary,
            row=0,
            disabled=(self.current_index == 0 or total_schedules == 0)
        )

        # Page indicator
        page_indicator = Button(
            label=f"Schedule {self.current_index + 1}/{total_schedules}" if total_schedules > 0 else "No Schedules",
            style=discord.ButtonStyle.primary,
            row=0,
            disabled=True
        )

        # Next button
        next_button = Button(
            label="Next ▶",
            style=discord.ButtonStyle.secondary,
            row=0,
            disabled=(self.current_index >= total_schedules -
                      1 or total_schedules == 0)
        )

        async def prev_callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                embed = discord.Embed(
                    title="❌ Permission Denied", description="You cannot use these buttons!", color=discord.Color.red())
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            if self.current_index > 0:
                self.current_index -= 1
                self._update_buttons()
                await interaction.response.edit_message(embed=self.create_embed(), view=self)

        async def next_callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                embed = discord.Embed(
                    title="❌ Permission Denied", description="You cannot use these buttons!", color=discord.Color.red())
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            if self.current_index < len(self.schedules) - 1:
                self.current_index += 1
                self._update_buttons()
                await interaction.response.edit_message(embed=self.create_embed(), view=self)

        prev_button.callback = prev_callback
        next_button.callback = next_callback

        self.add_item(prev_button)
        self.add_item(page_indicator)
        self.add_item(next_button)

        # Row 1: Action buttons
        # Cancel button
        cancel_button = Button(
            label="❌ Cancel Schedule",
            style=discord.ButtonStyle.danger,
            emoji="🗑️",
            row=1
        )

        async def cancel_callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                embed = discord.Embed(
                    title="❌ Permission Denied", description="You cannot use this button!", color=discord.Color.red())
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            modal = CancelScheduleModal(self.db_manager, self.guild_id, self)
            await interaction.response.send_modal(modal)

        cancel_button.callback = cancel_callback
        self.add_item(cancel_button)

        # Refresh button
        refresh_button = Button(
            label="🔄 Refresh",
            style=discord.ButtonStyle.primary,
            row=1
        )

        async def refresh_callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                embed = discord.Embed(
                    title="❌ Permission Denied", description="You cannot use this button!", color=discord.Color.red())
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            new_schedules = await self.db_manager.get_pending_reset_schedules(lookahead_hours=720)
            new_schedules = [
                s for s in new_schedules if s['guild_id'] == self.guild_id]
            self.schedules = new_schedules
            self.current_index = 0
            self._update_buttons()
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

        refresh_button.callback = refresh_callback
        self.add_item(refresh_button)

    def create_embed(self) -> discord.Embed:
        if not self.schedules:
            embed = discord.Embed(
                title="📅 Pending Reset Schedules",
                description="📭 No pending reset schedules found.",
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            return embed

        schedule = self.schedules[self.current_index]

        # Parse the reason field to extract details
        reason_text = schedule.get('reason', 'No reason provided')

        scope_text = "Unknown"
        scope_details_text = "Unknown"
        time_period_text = "Unknown"
        interval_text = "Unknown"

        if reason_text and '|' in reason_text:
            parts = reason_text.split(' | ')
            for part in parts:
                if part.startswith('Scope:'):
                    scope_text = part.replace('Scope: ', '')
                elif part.startswith('Details:'):
                    scope_details_text = part.replace('Details: ', '')
                elif part.startswith('Time Period:'):
                    time_period_text = part.replace('Time Period: ', '')
                elif part.startswith('Scheduled every'):
                    interval_text = part

        target_time = schedule['target_time']
        reset_types = ", ".join(schedule['reset_types'])

        embed = discord.Embed(
            title=f"📅 Schedule #{schedule['id']}",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )

        embed.add_field(name="📊 Reset Types",
                        value=f"```{reset_types}```", inline=False)
        embed.add_field(
            name="🎯 Scope", value=f"```{scope_text}```", inline=True)
        embed.add_field(name="📍 Target",
                        value=f"```{scope_details_text}```", inline=True)
        embed.add_field(name="⏰ Time Period",
                        value=f"```{time_period_text}```", inline=False)
        embed.add_field(name="🕐 Scheduled Time",
                        value=f"<t:{int(target_time.timestamp())}:F>", inline=True)
        embed.add_field(name="📅 Relative Time",
                        value=f"<t:{int(target_time.timestamp())}:R>", inline=True)

        if interval_text != "Unknown":
            embed.add_field(name="🔄 Schedule",
                            value=f"```{interval_text}```", inline=False)

        total_schedules = len(self.schedules)
        embed.set_footer(
            text=f"Schedule {self.current_index + 1} of {total_schedules} | Use the buttons below to navigate or cancel")

        return embed


# =========================================================
# INPUT ID BUTTON
# =========================================================

class IDInputModal(Modal, title="Enter Channel/Category ID"):

    def __init__(self, scope: str, view):
        super().__init__(timeout=300)
        self.scope = scope
        self.view = view

        self.id_input = TextInput(
            label=f"Enter {scope.capitalize()} ID",
            placeholder=f"Paste the {scope} ID here...",
            max_length=30,
            required=True
        )
        self.add_item(self.id_input)

    async def on_submit(self, interaction: discord.Interaction):

        try:
            id_str = self.id_input.value.strip()
            if not id_str.isdigit():
                await interaction.response.send_message(
                    f"❌ Invalid ID! Please enter a valid numeric ID.",
                    ephemeral=True
                )
                return

            channel_id = int(id_str)

            if self.scope == "channel":
                channel = interaction.guild.get_channel(channel_id)
                if not channel or not isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
                    await interaction.response.send_message(
                        f"❌ Channel not found! Make sure the ID is correct and the channel exists in this server.",
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
                        f"❌ Category not found! Make sure the ID is correct and the category exists in this server.",
                        ephemeral=True
                    )
                    return

                self.view.category_id = channel_id
                self.view.selected_category = category

            await interaction.response.defer()
            await self.view.show_page_3()

        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid ID format! Please enter a valid numeric ID.",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in ID input modal: {e}")
            await interaction.response.send_message(
                f"❌ An error occurred: {str(e)[:200]}",
                ephemeral=True
            )


# =========================================================
# TIME PERIOD MODAL
# =========================================================

class TimePeriodModal(Modal, title="Select Time Period"):
    def __init__(self, view):
        super().__init__(timeout=300)
        self.view = view

        self.days_input = TextInput(
            label="Number of Days",
            placeholder="Enter number of days (1-365)",
            min_length=1,
            max_length=3,
            required=True
        )
        self.add_item(self.days_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            days = int(self.days_input.value.strip())
            if days < 1 or days > 365:
                await interaction.response.send_message(
                    "❌ Please enter a number between 1 and 365 days.",
                    ephemeral=True
                )
                return

            self.view.time_period_days = days
            await interaction.response.defer()
            await self.view.show_schedule_options()

        except ValueError:
            await interaction.response.send_message(
                "❌ Please enter a valid number.",
                ephemeral=True
            )


# =========================================================
# SCHEDULE MODAL
# =========================================================

class ScheduleModal(Modal, title="Schedule Reset"):
    def __init__(self, view, scope_text: str, scope_details: str, time_period_text: str):
        super().__init__(timeout=300)
        self.view = view
        self.scope_text = scope_text
        self.scope_details = scope_details
        self.time_period_text = time_period_text

        self.interval_input = TextInput(
            label="Days Between Resets",
            placeholder="Enter number of days (e.g., 3 for every 3 days)",
            min_length=1,
            max_length=3,
            required=True
        )
        self.add_item(self.interval_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            interval_days = int(self.interval_input.value.strip())
            if interval_days < 1 or interval_days > 365:
                await interaction.response.send_message(
                    "❌ Please enter a number between 1 and 365 days.",
                    ephemeral=True
                )
                return

            self.view.schedule_interval_days = interval_days

            target_time = datetime.now(
                timezone.utc) + timedelta(days=interval_days)

            reason = f"Scheduled every {interval_days} days | Scope: {self.scope_text} | Details: {self.scope_details} | Time Period: {self.time_period_text}"

            schedule_id = await self.view.db_manager.create_reset_schedule(
                guild_id=interaction.guild.id,
                requested_by_id=interaction.user.id,
                reset_types=[self.view.stat_type],
                target_time=target_time,
                reason=reason
            )

            # Edit the current message instead of sending a new one
            embed = discord.Embed(
                title="✅ Reset Scheduled!",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )

            embed.add_field(name="Stat Type",
                            value=f"```{self.view.stat_type}```", inline=True)
            embed.add_field(
                name="Target", value=f"```{self.scope_text}```", inline=True)
            embed.add_field(name="Scope Details",
                            value=f"```{self.scope_details}```", inline=False)
            embed.add_field(
                name="Time Period", value=f"```{self.time_period_text}```", inline=False)
            embed.add_field(
                name="Schedule", value=f"```Every {interval_days} days```", inline=True)
            embed.add_field(
                name="Next Reset", value=f"<t:{int(target_time.timestamp())}:F>", inline=True)
            embed.add_field(name="Schedule ID",
                            value=f"```{schedule_id}```", inline=True)

            embed.add_field(
                name="📋 Manage Schedules",
                value=f"Use `/reset schedules` to view or cancel this schedule.",
                inline=False
            )

            self.view.stop()
            await interaction.response.edit_message(embed=embed, view=None)

        except ValueError:
            await interaction.response.send_message(
                "❌ Please enter a valid number.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Failed to create schedule: {str(e)[:200]}",
                ephemeral=True
            )


# =========================================================
# RESET VIEW
# =========================================================

class ResetView(View):
    def __init__(self, interaction: discord.Interaction, db_manager: DatabaseManager,
                 command_type: Literal["server", "user"], target_user_id: Optional[int] = None):
        super().__init__(timeout=300)
        self.interaction = interaction
        self.db_manager = db_manager
        self.command_type = command_type
        self.target_user_id = target_user_id
        self.scope = None
        self.stat_type = None
        self.channel_id = None
        self.category_id = None
        self.current_page = 1
        self.selected_channel = None
        self.selected_category = None
        self.time_period_days = None
        self.schedule_interval_days = None

    def create_embed(self, title: str, description: str, color: int = 0xff0000) -> discord.Embed:
        embed = discord.Embed(
            title=title,
            description=description,
            color=color
        )
        embed.set_footer(text="Stats Reset System")
        return embed

    async def show_page_1(self):
        self.clear_items()
        self.current_page = 1

        if self.command_type == "server":
            title = "Reset Server Stats"
            description = "**Page 1/5**\n**Where do you want to reset statistics?**\n\nSelect from the dropdown below:"
        else:
            user_text = f"<@{self.target_user_id}>" if self.target_user_id else "your"
            title = f"Reset {user_text.capitalize()} Stats"
            description = f"**Page 1/5**\n**Where do you want to reset {user_text} statistics?**\n\nSelect from the dropdown below:"

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

        async def scope_callback(interaction: discord.Interaction):
            if interaction.user.id != self.interaction.user.id:
                await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
                return

            self.scope = select.values[0]

            if self.scope == "server":
                await interaction.response.defer()
                await self.show_page_3()
            else:
                await interaction.response.defer()
                await self.show_page_2()

        select.callback = scope_callback
        self.add_item(select)

        await self.interaction.edit_original_response(embed=embed, view=self)

    async def show_page_2(self):
        self.clear_items()
        self.current_page = 2

        if self.scope == "channel":
            title = "Select Channel"
            description = "**Page 2/5**\n**Select a channel to reset statistics from:**\n\nChoose from the dropdown below **OR** click 'Input ID' to enter a channel ID manually."
            placeholder = "Choose a channel..."
            input_button_label = "📝 Input Channel ID"

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
            description = "**Page 2/5**\n**Select a category to reset statistics from:**\n\nChoose from the dropdown below **OR** click 'Input ID' to enter a category ID manually."
            placeholder = "Choose a category..."
            input_button_label = "📝 Input Category ID"

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

        async def selection_callback(interaction: discord.Interaction):
            if interaction.user.id != self.interaction.user.id:
                await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
                return

            selected_id = int(select.values[0])
            if self.scope == "channel":
                self.channel_id = selected_id
                self.selected_channel = interaction.guild.get_channel(
                    selected_id)
            else:
                self.category_id = selected_id
                self.selected_category = discord.utils.get(
                    interaction.guild.categories, id=selected_id)

            await interaction.response.defer()
            await self.show_page_3()

        select.callback = selection_callback
        self.add_item(select)

        input_id_button = Button(
            label=input_button_label,
            style=discord.ButtonStyle.secondary,
            emoji="🔢"
        )

        async def input_id_callback(interaction: discord.Interaction):
            if interaction.user.id != self.interaction.user.id:
                await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
                return

            modal = IDInputModal(self.scope, self)
            await interaction.response.send_modal(modal)

        input_id_button.callback = input_id_callback
        self.add_item(input_id_button)

        back_button = Button(
            label="Back", style=discord.ButtonStyle.gray, emoji="⬅️")

        async def back_callback(interaction: discord.Interaction):
            if interaction.user.id != self.interaction.user.id:
                await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
                return

            await interaction.response.defer()
            await self.show_page_1()

        back_button.callback = back_callback
        self.add_item(back_button)

        await self.interaction.edit_original_response(embed=embed, view=self)

    async def show_page_3(self):
        self.clear_items()
        self.current_page = 3

        scope_text = ""
        if self.scope == "server":
            scope_text = "the entire server"
        elif self.scope == "channel" and self.selected_channel:
            scope_text = f"channel #{self.selected_channel.name}"
        elif self.scope == "category" and self.selected_category:
            scope_text = f"category {self.selected_category.name}"

        if self.command_type == "server":
            title = "Select Stat Type"
            description = f"**Page 3/5**\n**Which type of statistics do you want to reset from {scope_text}?**\n\nSelect from the dropdown below:"
        else:
            user_text = f"<@{self.target_user_id}>" if self.target_user_id else "your"
            title = "Select Stat Type"
            description = f"**Page 3/5**\n**Which type of {user_text} statistics do you want to reset from {scope_text}?**\n\nSelect from the dropdown below:"

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
                        label="Mentions", value="mentions", description="Reset mentions", emoji="📢")
                ]

        select = Select(placeholder="Select stat type...", options=options)

        async def stat_callback(interaction: discord.Interaction):
            if interaction.user.id != self.interaction.user.id:
                await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
                return

            self.stat_type = select.values[0]
            await interaction.response.defer()
            await self.show_time_period()

        select.callback = stat_callback
        self.add_item(select)

        back_button = Button(
            label="Back", style=discord.ButtonStyle.gray, emoji="⬅️")

        async def back_callback(interaction: discord.Interaction):
            if interaction.user.id != self.interaction.user.id:
                await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
                return

            await interaction.response.defer()
            if self.scope == "server":
                await self.show_page_1()
            else:
                await self.show_page_2()

        back_button.callback = back_callback
        self.add_item(back_button)

        await self.interaction.edit_original_response(embed=embed, view=self)

    async def show_time_period(self):
        self.clear_items()
        self.current_page = 4

        title = "Select Time Period"
        description = "**Page 4/5**\n**Do you want to delete stats from a specific time period?**\n\n"
        description += "• **Skip:** Delete ALL stats (no time limit)\n"
        description += "• **Days:** Delete stats from the last X days only\n\n"
        description += "Use the buttons below to choose."

        embed = self.create_embed(title, description)

        skip_button = Button(
            label="Skip (Delete All)",
            style=discord.ButtonStyle.secondary,
            emoji="⏭️"
        )

        async def skip_callback(interaction: discord.Interaction):
            if interaction.user.id != self.interaction.user.id:
                await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
                return

            self.time_period_days = None
            await interaction.response.defer()
            await self.show_confirmation()

        skip_button.callback = skip_callback
        self.add_item(skip_button)

        days_button = Button(
            label="Set Days Period",
            style=discord.ButtonStyle.primary,
            emoji="📅"
        )

        async def days_callback(interaction: discord.Interaction):
            if interaction.user.id != self.interaction.user.id:
                await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
                return

            modal = TimePeriodModal(self)
            await interaction.response.send_modal(modal)

        days_button.callback = days_callback
        self.add_item(days_button)

        back_button = Button(
            label="Back", style=discord.ButtonStyle.gray, emoji="⬅️")

        async def back_callback(interaction: discord.Interaction):
            if interaction.user.id != self.interaction.user.id:
                await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
                return

            await interaction.response.defer()
            await self.show_page_3()

        back_button.callback = back_callback
        self.add_item(back_button)

        await self.interaction.edit_original_response(embed=embed, view=self)

    async def show_schedule_options(self):
        self.clear_items()
        self.current_page = 5

        # Get scope text for display
        scope_text = ""
        scope_details = ""
        time_period_text = ""

        if self.command_type == "server":
            scope_text = "Server Reset"
            if self.scope == "server":
                scope_details = "Entire Server"
            elif self.scope == "channel" and self.selected_channel:
                scope_details = f"Channel: #{self.selected_channel.name} (ID: {self.selected_channel.id})"
            elif self.scope == "category" and self.selected_category:
                scope_details = f"Category: {self.selected_category.name} (ID: {self.selected_category.id})"
        else:
            user_text = f"<@{self.target_user_id}>" if self.target_user_id else "Yourself"
            scope_text = "User Reset"
            if self.scope == "server":
                scope_details = f"User: {user_text} - Server-wide"
            elif self.scope == "channel" and self.selected_channel:
                scope_details = f"User: {user_text} - Channel: #{self.selected_channel.name}"
            elif self.scope == "category" and self.selected_category:
                scope_details = f"User: {user_text} - Category: {self.selected_category.name}"

        if self.time_period_days:
            time_period_text = f"Deleting stats from the last {self.time_period_days} days"
        else:
            time_period_text = "Deleting ALL stats (no time limit)"

        title = "Schedule Reset"
        description = "**Page 5/5**\n**Do you want to schedule this reset to run automatically?**\n\n"
        description += "• **Confirm Now:** Run the reset immediately\n"
        description += "• **Schedule:** Set up automatic recurring resets\n\n"
        description += f"📋 **Reset Details:**\n"
        description += f"• **Command Type:** `{scope_text}`\n"
        description += f"• **Target:** {scope_details}\n"
        description += f"• **Stat Type:** `{self.stat_type}`\n"
        description += f"• **Time Period:** {time_period_text}\n"

        embed = self.create_embed(title, description)

        confirm_now_button = Button(
            label="Confirm Now",
            style=discord.ButtonStyle.success,
            emoji="✅"
        )

        async def confirm_now_callback(interaction: discord.Interaction):
            if interaction.user.id != self.interaction.user.id:
                await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
                return

            await interaction.response.defer()
            await self.execute_reset(interaction, scheduled=False)

        confirm_now_button.callback = confirm_now_callback
        self.add_item(confirm_now_button)

        schedule_button = Button(
            label="Schedule Reset",
            style=discord.ButtonStyle.primary,
            emoji="📅"
        )

        async def schedule_callback(interaction: discord.Interaction):
            if interaction.user.id != self.interaction.user.id:
                await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
                return

            modal = ScheduleModal(
                self, scope_text, scope_details, time_period_text)
            await interaction.response.send_modal(modal)

        schedule_button.callback = schedule_callback
        self.add_item(schedule_button)

        back_button = Button(
            label="Back", style=discord.ButtonStyle.gray, emoji="⬅️")

        async def back_callback(interaction: discord.Interaction):
            if interaction.user.id != self.interaction.user.id:
                await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
                return

            await interaction.response.defer()
            await self.show_time_period()

        back_button.callback = back_callback
        self.add_item(back_button)

        await self.interaction.edit_original_response(embed=embed, view=self)

    async def show_confirmation(self):
        await self.show_schedule_options()

    async def execute_reset(self, interaction: discord.Interaction, scheduled: bool = False):
        scope_text = ""
        if self.scope == "server":
            scope_text = "the entire server"
        elif self.scope == "channel" and self.selected_channel:
            scope_text = f"channel #{self.selected_channel.name}"
        elif self.scope == "category" and self.selected_category:
            scope_text = f"category {self.selected_category.name}"

        if self.time_period_days:
            period_text = f" (only data from last {self.time_period_days} days)"
        else:
            period_text = " (all data)"

        processing_embed = self.create_embed(
            "🔄 Processing...",
            f"Deleting **{self.stat_type}** from {scope_text}{period_text}. This may take a moment..."
        )
        await interaction.edit_original_response(embed=processing_embed, view=None)

        try:
            if self.command_type == "server":
                result = await self.db_manager.reset_server_stats(
                    guild_id=interaction.guild.id,
                    stat_type=self.stat_type,
                    channel_id=self.channel_id,
                    category_id=self.category_id,
                    time_period_days=self.time_period_days
                )

                if isinstance(result, dict):
                    total = sum(int(str(count).split()[0]) if str(
                        count).isdigit() else 0 for count in result.values())
                else:
                    total = result if isinstance(result, int) else 0

                success_embed = self.create_embed(
                    "✅ Reset Successful!",
                    f"Successfully deleted **{self.stat_type}** from **{scope_text}**{period_text}!\n\n" +
                    f"✅ **Total: {total} records deleted.**",
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
                    time_period_days=self.time_period_days
                )

                if isinstance(result, dict):
                    total = sum(int(str(count).split()[0]) if str(
                        count).isdigit() else 0 for count in result.values())
                else:
                    total = result if isinstance(result, int) else 0

                user_text = f"<@{target_user}>" if self.target_user_id else "your"
                success_embed = self.create_embed(
                    "✅ Reset Successful!",
                    f"Successfully deleted **{self.stat_type}** for {user_text} stats from **{scope_text}**{period_text}!\n\n" +
                    f"✅ **Total: {total} records deleted.**",
                    color=0x00ff00
                )

            await interaction.edit_original_response(embed=success_embed, view=None)

        except Exception as e:
            logger.error(f"Reset failed: {e}")
            logger.error(traceback.format_exc())

            error_embed = self.create_embed(
                "❌ Reset Failed!",
                f"An error occurred while deleting statistics:\n```{str(e)[:1000]}```\n\nPlease try again or contact support."
            )
            await interaction.edit_original_response(embed=error_embed, view=None)


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
                await send_method(
                    "⚠️ Database connection not ready. Please try again in a moment.",
                    ephemeral=True
                )
            else:
                await send_method(
                    "⚠️ Database connection not ready. Please try again in a moment.",
                    delete_after=10
                )
            return

        try:
            async with self.db_pool.acquire() as conn:
                await conn.fetchval('SELECT 1')
        except Exception as e:
            if is_interaction:
                await send_method(
                    f"❌ Database connection error: {str(e)[:200]}",
                    ephemeral=True
                )
            else:
                await send_method(
                    f"❌ Database connection error: {str(e)[:200]}",
                    delete_after=10
                )
            return

        has_permission = await self.check_reset_permissions(ctx_or_interaction if is_interaction else guild, user, command_type, target_user)
        if not has_permission:
            settings_cog = self.bot.get_cog("Settings")
            if settings_cog:
                settings = await settings_cog.get_guild_settings(guild.id)
                permission_level = settings.get('permission_level', 'Default')

                if permission_level == "Moderator":
                    required_permission = "Manage Server"
                else:
                    required_permission = "Administrator"

                embed = discord.Embed(
                    title="❌ Permission Denied",
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
                    title="❌ Permission Denied",
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
                title=f"🔧 {'Server' if command_type == 'server' else 'User'} Stats Reset",
                description="This command allows you to reset statistics. Please follow the 5-step process.\n\n"
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
                             command_type, target_user_id)

            self.active_sessions[message.id] = {
                'guild_id': guild.id,
                'user_id': user.id,
                'target_user_id': target_user_id,
                'command_type': command_type,
                'view': view
            }

            await view.show_page_1()

        else:
            view = ResetView(ctx_or_interaction, self.db_manager,
                             command_type, target_user_id)
            embed = view.create_embed(
                f"🔧 {'Server' if command_type == 'server' else 'User'} Stats Reset",
                "This command allows you to reset statistics. Please follow the 5-step process.\n\n"
                "**Note:** This action is irreversible!"
            )
            await send_method(embed=embed, view=view, ephemeral=True)

            await view.show_page_1()

            message = await ctx_or_interaction.original_response()
            self.active_sessions[message.id] = {
                'guild_id': guild.id,
                'user_id': user.id,
                'target_user_id': target_user_id,
                'command_type': command_type,
                'view': view
            }

    except Exception as e:
        logger.error(f"Error in _handle_reset_command: {e}")
        if is_interaction:
            try:
                await ctx_or_interaction.followup.send("❌ An error occurred while setting up the reset command.", ephemeral=True)
            except:
                pass
        else:
            try:
                await ctx_or_interaction.send("❌ An error occurred while setting up the reset command.", delete_after=10)
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
                host=db_host,
                port=db_port,
                user=db_user,
                password=db_password,
                database=db_name,
                min_size=1,
                max_size=10,
                command_timeout=60
            )

            self.db_manager = DatabaseManager(self.db_pool)
            return True

        except Exception as e:
            logger.error(f"❌ Failed to create database pool: {e}")
            logger.error(traceback.format_exc())
            self.db_pool = None
            self.db_manager = None
            return False

    async def start_schedule_checker(self):
        """Start the background task to check for scheduled resets every 12 hours"""
        if self._schedule_checker_started:
            return

        self._schedule_checker_started = True

        async def schedule_checker():
            await self.bot.wait_until_ready()
            while not self.bot.is_closed():
                try:
                    await self.check_and_execute_scheduled_resets()
                    await asyncio.sleep(12 * 60 * 60)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error in schedule checker: {e}")
                    await asyncio.sleep(3600)

        self.schedule_check_task = asyncio.create_task(schedule_checker())
        logger.info("✅ Started scheduled reset checker (runs every 12 hours)")

    async def check_and_execute_scheduled_resets(self):
        """Check for due reset schedules and execute them"""
        if not self.db_manager or not self.db_pool:
            logger.warning(
                "Cannot check scheduled resets - database not ready")
            return

        logger.info("🔍 Checking for due scheduled resets...")

        try:
            schedules = await self.db_manager.get_due_reset_schedules()

            if not schedules:
                logger.info("No due schedules found")
                return

            logger.info(f"Found {len(schedules)} due schedule(s) to execute")

            for schedule in schedules:
                try:
                    logger.info(
                        f"Executing schedule {schedule['id']} for guild {schedule['guild_id']}")

                    results = await self.db_manager.execute_scheduled_reset(schedule)

                    guild = self.bot.get_guild(schedule['guild_id'])
                    if guild:
                        requester = guild.get_member(
                            schedule['requested_by_id'])
                        if requester:
                            embed = discord.Embed(
                                title="🔄 Scheduled Reset Completed",
                                description=f"Your scheduled reset has been executed successfully!",
                                color=discord.Color.green(),
                                timestamp=datetime.now(timezone.utc)
                            )
                            embed.add_field(name="Stat Types", value=", ".join(
                                schedule['reset_types']), inline=False)
                            embed.add_field(name="Schedule ID", value=str(
                                schedule['id']), inline=True)

                            result_summary = []
                            for stat_type, result in results.items():
                                if isinstance(result, dict):
                                    total = sum(int(str(v).split()[0]) if str(
                                        v).isdigit() else 0 for v in result.values())
                                    result_summary.append(
                                        f"• {stat_type}: {total} records deleted")
                                elif isinstance(result, int):
                                    result_summary.append(
                                        f"• {stat_type}: {result} records deleted")
                                else:
                                    result_summary.append(
                                        f"• {stat_type}: Completed")

                            if result_summary:
                                embed.add_field(name="Results", value="\n".join(
                                    result_summary), inline=False)

                            try:
                                await requester.send(embed=embed)
                            except discord.Forbidden:
                                logger.warning(
                                    f"Cannot DM requester for schedule {schedule['id']}")

                    await self.db_manager.mark_schedule_completed(schedule['id'])
                    logger.info(
                        f"✅ Schedule {schedule['id']} completed successfully")

                except Exception as e:
                    logger.error(
                        f"Failed to execute schedule {schedule['id']}: {e}")
                    logger.error(traceback.format_exc())
                    try:
                        async with self.db_pool.acquire() as conn:
                            await conn.execute("""
                                UPDATE reset_schedules 
                                SET reason = CONCAT(reason, '\n[ERROR] ', $2)
                                WHERE id = $1
                            """, schedule['id'], str(e)[:500])
                    except Exception as log_error:
                        logger.error(
                            f"Failed to log error for schedule {schedule['id']}: {log_error}")

        except Exception as e:
            logger.error(f"Error checking scheduled resets: {e}")
            logger.error(traceback.format_exc())

    async def cog_load(self):
        success = await self.create_db_pool()
        if not success:
            logger.error("Failed to establish database connection!")
        else:
            await self.start_schedule_checker()

    async def cog_unload(self):
        if self.schedule_check_task:
            self.schedule_check_task.cancel()
            try:
                await self.schedule_check_task
            except asyncio.CancelledError:
                pass

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

    @reset_group.command(name="schedules", description="View pending reset schedules (Admin only)")
    @app_commands.default_permissions(administrator=True)
    async def view_schedules(self, interaction: discord.Interaction):
        if not self.db_manager:
            embed = discord.Embed(
                title="❌ Error", description="Database not ready.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        try:
            all_schedules = await self.db_manager.get_pending_reset_schedules(lookahead_hours=720)
            guild_schedules = [
                s for s in all_schedules if s['guild_id'] == interaction.guild.id]

            if not guild_schedules:
                embed = discord.Embed(
                    title="📅 Pending Reset Schedules",
                    description="📭 No pending reset schedules found for this server.",
                    color=discord.Color.blue(),
                    timestamp=datetime.now(timezone.utc)
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            view = ScheduleView(guild_schedules, self.db_manager,
                                interaction.guild.id, interaction.user.id)
            await interaction.response.send_message(embed=view.create_embed(), view=view, ephemeral=True)

        except Exception as e:
            embed = discord.Embed(title="❌ Error", description=str(e)[
                                  :200], color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)

    # ERROR HANDLING
    @reset_server.error
    async def reset_server_error(self, interaction: discord.Interaction, error):
        logger.error(f"Reset server error: {error}")
        logger.error(traceback.format_exc())
        embed = discord.Embed(
            title="❌ Error", description=f"An error occurred: ```{str(error)[:500]}```", color=0xff0000)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @reset_user.error
    async def reset_user_error(self, interaction: discord.Interaction, error):
        logger.error(f"Reset user error: {error}")
        logger.error(traceback.format_exc())
        embed = discord.Embed(
            title="❌ Error", description=f"An error occurred: ```{str(error)[:500]}```", color=0xff0000)
        await interaction.response.send_message(embed=embed, ephemeral=True)


# =========================================================
# SETUP
# =========================================================

async def setup(bot):
    cog = ResetStats(bot)
    await bot.add_cog(cog)
