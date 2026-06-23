from exceptions import (
    DatabaseError, DatabaseConnectionError, DatabaseQueryError, DatabaseTransactionError,
    DatabaseIntegrityError, DatabaseTimeoutError,
    CacheError, CacheConnectionError, CacheReadFailed, CacheWriteFailed, CacheDeleteFailed,
    CacheBatchFailed, CacheKeyNotFound, CacheTimeoutError, CacheSerializationError
)
import os
import asyncpg
import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta, date, time, timezone
import asyncio
from typing import List, Dict, Optional, Tuple, Any
import logging
from PIL import Image, ImageDraw, ImageFont
import io
import aiohttp
import json
import traceback
from pathlib import Path
import pytz
import sys
import gc
import re
from .ratelimiter import RateLimiter, RateLimitType, rate_limited, get_rate_limiter

root_dir = Path(__file__).parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

logger = logging.getLogger(__name__)

# =========================================================
# USER VERIFICATION FUNCTION WITH RATE LIMITING (ONLY FOR FALLBACK)
# =========================================================


@rate_limited(RateLimitType.API, timeout=1.0)
async def _fetch_user_limited(bot, user_id: int):
    """Rate-limited fetch_user for users who left the server."""
    try:
        return await bot.fetch_user(user_id)
    except discord.NotFound:
        return None
    except discord.HTTPException:
        return None
    except Exception:
        return None


async def get_user_info(bot, guild: discord.Guild, user_id: int) -> tuple:
    """
    Get user information and check if account exists.
    Returns: (member_object_or_None, username, account_exists)

    - If user is in guild: returns (member, name, True) - NO rate limiting
    - If user left but account exists: returns (None, name, True) - rate limited
    - If account deleted: returns (None, "[Deleted User]", False) - rate limited
    """
    try:
        member = guild.get_member(user_id)
        if member:
            return member, member.name, True

        user = await _fetch_user_limited(bot, user_id)
        if user:
            return None, user.name, True
        else:
            return None, "[Deleted User]", False
    except Exception:
        return None, f"User {user_id}", True


# =========================================================
# CONFIGURATION
# =========================================================
DB_HOST = os.getenv('DB_HOST', 'db')
DB_PORT = int(os.getenv('DB_PORT', 5432))
DB_NAME = os.getenv('DB_NAME', 'statshq')
DB_USER = os.getenv('DB_USER', 'statshq')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'strongpassword')

SESSION_THRESHOLD = 1800  # 30 minutes
PARTIAL_SAVE_INTERVAL = 30
USERS_PER_PAGE = 10
MAX_CUSTOM_DAYS = 2000
TIME_PERIODS = [7, 14, 30]
STREAK_MIN_SESSION_SECONDS = 60
DAILY_STREAK_UPDATE_HOUR = 0

BASE_DIR = Path(__file__).resolve().parent.parent

# =========================================================
# PAGE JUMP MODAL
# =========================================================


class PageJumpModal(discord.ui.Modal, title='Jump to Page'):
    def __init__(self, view, total_pages):
        super().__init__(timeout=60)
        self.view = view
        self.total_pages = total_pages

        self.page_number = discord.ui.TextInput(
            label=f'Enter page number (1-{total_pages})',
            placeholder=f'1 to {total_pages}',
            min_length=1,
            max_length=4,
            required=True
        )
        self.add_item(self.page_number)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            page = int(self.page_number.value) - 1

            if page < 0 or page >= self.total_pages:
                embed = discord.Embed(
                    title="❌ Invalid Page",
                    description=f"Page {page + 1} does not exist. Please enter a number between 1 and {self.total_pages}.",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            await interaction.response.defer()
            self.view.page = page
            await self.view.update_message(interaction)

        except ValueError:
            embed = discord.Embed(
                title="❌ Invalid Input",
                description="Please enter a valid page number.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


# =========================================================
# HELPER FUNCTIONS
# =========================================================


def ensure_timezone_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def get_guild_timezone(bot, guild_id: int) -> str:
    try:
        settings_cog = bot.get_cog('Settings')
        if not settings_cog:
            return 'UTC'
        settings = await settings_cog.get_guild_settings(guild_id)
        return settings.get('timezone', 'UTC')
    except Exception:
        return 'UTC'


def get_fonts():
    try:
        custom_font_path = BASE_DIR / "assets" / "fonts" / "HorndonD.ttf"
        if os.path.exists(custom_font_path):
            font_small = ImageFont.truetype(custom_font_path, 16)
            font_medium = ImageFont.truetype(custom_font_path, 20)
            font_large = ImageFont.truetype(custom_font_path, 24)
            font_larger = ImageFont.truetype(custom_font_path, 30)
            font_huge = ImageFont.truetype(custom_font_path, 40)
            font_giant = ImageFont.truetype(custom_font_path, 60)
            return font_small, font_medium, font_large, font_larger, font_huge, font_giant
    except:
        pass

    try:
        font_small = ImageFont.truetype("arial.ttf", 16)
        font_medium = ImageFont.truetype("arial.ttf", 20)
        font_large = ImageFont.truetype("arial.ttf", 24)
        font_larger = ImageFont.truetype("arial.ttf", 30)
        font_huge = ImageFont.truetype("arial.ttf", 40)
        font_giant = ImageFont.truetype("arial.ttf", 60)
        return font_small, font_medium, font_large, font_larger, font_huge, font_giant
    except:
        font_small = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_large = ImageFont.load_default()
        font_larger = ImageFont.load_default()
        font_huge = ImageFont.load_default()
        font_giant = ImageFont.load_default()
        return font_small, font_medium, font_large, font_larger, font_huge, font_giant


def draw_text_with_stroke(draw, position, text, font, fill, stroke_fill, stroke_width):
    x, y = position
    for dx in [-stroke_width, 0, stroke_width]:
        for dy in [-stroke_width, 0, stroke_width]:
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, font=font, fill=stroke_fill)
    draw.text((x, y), text, font=font, fill=fill)


def draw_text_centered_with_stroke(draw, text, center_position, font, fill="white", stroke_fill="black", stroke_width=2, max_width=None):
    center_x, center_y = center_position
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = center_x - (text_width // 2)
    y = center_y - (text_height // 2)

    if max_width and text_width > max_width:
        current_font = font
        original_size = font.size
        for size in range(original_size - 2, 8, -2):
            try:
                smaller_font = ImageFont.truetype(current_font.path, size)
                bbox = draw.textbbox((0, 0), text, font=smaller_font)
                text_width = bbox[2] - bbox[0]
                if text_width <= max_width:
                    text_height = bbox[3] - bbox[1]
                    x = center_x - (text_width // 2)
                    y = center_y - (text_height // 2)
                    draw_text_with_stroke(
                        draw, (x, y), text, smaller_font, fill, stroke_fill, stroke_width)
                    return
            except:
                continue

    draw_text_with_stroke(draw, (x, y), text, font, fill,
                          stroke_fill, stroke_width)


def draw_rounded_rectangle(draw, xy, radius, fill=None, outline=None):
    x1, y1, x2, y2 = xy
    draw.rectangle([x1 + radius, y1, x2 - radius, y2],
                   fill=fill, outline=outline)
    draw.rectangle([x1, y1 + radius, x2, y2 - radius],
                   fill=fill, outline=outline)
    draw.pieslice([x1, y1, x1 + radius * 2, y1 + radius * 2],
                  180, 270, fill=fill, outline=outline)
    draw.pieslice([x2 - radius * 2, y1, x2, y2 - radius * 2],
                  270, 360, fill=fill, outline=outline)
    draw.pieslice([x1, y2 - radius * 2, x1 + radius * 2, y2],
                  90, 180, fill=fill, outline=outline)
    draw.pieslice([x2 - radius * 2, y2 - radius * 2, x2, y2],
                  0, 90, fill=fill, outline=outline)


def format_duration(total_seconds):
    if total_seconds == 0:
        return "0s"
    days = total_seconds // (3600 * 24)
    hours = (total_seconds % (3600 * 24)) // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if days > 0:
        return f"{days}d {hours}h"
    elif hours > 0:
        return f"{hours}h {minutes}m"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{int(seconds)}s"


def format_user_count(count):
    return f"{count:,}"


def format_streak(streak_days):
    if streak_days >= 365:
        years = streak_days // 365
        days = streak_days % 365
        if days > 0:
            return f"{years}y {days}d"
        return f"{years}y"
    return f"{streak_days}d"

# =========================================================
# POSTGRESQL CONNECTION
# =========================================================


async def create_db_pool():
    try:
        return await asyncpg.create_pool(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
    except Exception as e:
        print(f"[ERROR] Database pool creation failed: {e}")
        raise DatabaseConnectionError(
            "Failed to create database connection pool", original=e)

# =========================================================
# ENCRYPTION HELPERS
# =========================================================


def encrypt_username(fernet, username: str) -> Optional[str]:
    """Encrypt username for privacy."""
    if not username or not fernet:
        return None
    try:
        return fernet.encrypt(username.encode()).decode()
    except Exception:
        return None


def decrypt_username(fernet, encrypted: Optional[str]) -> Optional[str]:
    """Decrypt username if possible."""
    if not encrypted or not fernet:
        return encrypted
    try:
        return fernet.decrypt(encrypted.encode()).decode()
    except Exception:
        return None


# =========================================================
# SESSION MANAGER
# =========================================================


class SessionManager:
    def __init__(self, db_pool, cog=None):
        self.db_pool = db_pool
        self.cog = cog

    def _get_fernet(self):
        """Get fernet instance from DatabaseStats cog if available."""
        if self.cog and self.cog.bot:
            db_stats = self.cog.bot.get_cog('DatabaseStats')
            if db_stats and hasattr(db_stats, 'fernet'):
                return db_stats.fernet
        return None

    async def save_partial_session_to_postgresql(self, guild_id: int, user_id: int, activity_type: str,
                                                 display_name: str, start_time: datetime, current_time: datetime,
                                                 is_bot: bool = False, role_ids: List[int] = None):
        """
        Save or update a partial session with encrypted username.
        """
        duration_seconds = int((current_time - start_time).total_seconds())
        if duration_seconds < 10:
            return False

        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)

        hour = start_time.replace(minute=0, second=0, microsecond=0)
        if hour.tzinfo is None:
            hour = hour.replace(tzinfo=timezone.utc)

        normalized_type = activity_type.lower().strip()
        normalized_name = display_name[:255].strip()

        # Get encrypted username
        fernet = self._get_fernet()
        encrypted_username = None
        if self.cog and self.cog.bot:
            guild = self.cog.bot.get_guild(guild_id)
            if guild:
                member = guild.get_member(user_id)
                if member:
                    encrypted_username = encrypt_username(fernet, str(member))
        if not encrypted_username:
            encrypted_username = encrypt_username(fernet, f"User {user_id}")

        async with self.db_pool.acquire() as conn:
            result = await conn.execute('''
                INSERT INTO activity_sessions_hourly
                (hour, guild_id, user_id, activity_type, display_name,
                 session_count, total_duration_seconds, partial_base_seconds,
                 is_bot, role_ids, last_end_time, encrypted_username)
                VALUES ($1, $2, $3, $4, $5, 0, $6, 0, $7, $8, $9, $10)
                ON CONFLICT (guild_id, user_id, activity_type, display_name, hour)
                DO UPDATE SET
                    total_duration_seconds = GREATEST(activity_sessions_hourly.total_duration_seconds, EXCLUDED.total_duration_seconds),
                    last_end_time = EXCLUDED.last_end_time,
                    role_ids = EXCLUDED.role_ids,
                    encrypted_username = EXCLUDED.encrypted_username
            ''',
                                        hour, guild_id, user_id, normalized_type, normalized_name,
                                        duration_seconds, is_bot, role_ids or [], current_time,
                                        encrypted_username
                                        )

            if 'INSERT' in result:
                if duration_seconds % 300 < 30:
                    print(
                        f"🆕 Partial save CREATING new session for {normalized_name}")
            else:
                if duration_seconds % 300 < 30:
                    print(
                        f"📝 Partial save UPDATING session for {normalized_name} (elapsed={duration_seconds}s)")

            try:
                await self.cog.db.log_daily_activity(
                    guild_id, user_id, current_time.date(), 1
                )
            except Exception as e:
                print(
                    f"[WARNING] Failed to log daily activity for user {user_id}: {e}")

            return True

    async def end_session_to_postgresql(self, guild_id: int, user_id: int, activity_type: str,
                                        display_name: str, start_time: datetime, end_time: datetime,
                                        is_bot: bool = False, role_ids: List[int] = None):
        """
        Called when a session ends. Writes the final duration and increments session_count with encrypted username.
        """
        duration_seconds = int((end_time - start_time).total_seconds())
        if duration_seconds < 5:
            return False

        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)

        hour = start_time.replace(minute=0, second=0, microsecond=0)
        if hour.tzinfo is None:
            hour = hour.replace(tzinfo=timezone.utc)

        normalized_type = activity_type.lower().strip()
        normalized_name = display_name[:255].strip()

        # Get encrypted username
        fernet = self._get_fernet()
        encrypted_username = None
        if self.cog and self.cog.bot:
            guild = self.cog.bot.get_guild(guild_id)
            if guild:
                member = guild.get_member(user_id)
                if member:
                    encrypted_username = encrypt_username(fernet, str(member))
        if not encrypted_username:
            encrypted_username = encrypt_username(fernet, f"User {user_id}")

        async with self.db_pool.acquire() as conn:
            existing = await conn.fetchrow('''
                SELECT hour, total_duration_seconds
                FROM activity_sessions_hourly
                WHERE guild_id = $1
                AND user_id = $2
                AND activity_type = $3
                AND display_name = $4
                AND hour = $5
            ''', guild_id, user_id, normalized_type, normalized_name, hour)

            if existing:
                correct_total = max(
                    existing['total_duration_seconds'] or 0,
                    duration_seconds
                )

                await conn.execute('''
                    UPDATE activity_sessions_hourly
                    SET total_duration_seconds = $1,
                        partial_base_seconds = $1,
                        session_count = session_count + 1,
                        last_end_time = $2,
                        role_ids = $3,
                        encrypted_username = $4
                    WHERE guild_id = $5 AND user_id = $6
                    AND activity_type = $7 AND display_name = $8
                    AND hour = $9
                ''',
                                   correct_total,
                                   end_time,
                                   role_ids or [],
                                   encrypted_username,
                                   guild_id, user_id,
                                   normalized_type, normalized_name,
                                   existing['hour']
                                   )

                activity_date = end_time.date()
                try:
                    await self.cog.db.log_daily_activity(
                        guild_id, user_id, activity_date, duration_seconds
                    )
                except Exception as e:
                    print(
                        f"[WARNING] Failed to log daily activity for user {user_id}: {e}")

                return True

            else:
                if duration_seconds >= 5:
                    await conn.execute('''
                        INSERT INTO activity_sessions_hourly
                        (hour, guild_id, user_id, activity_type, display_name,
                         session_count, total_duration_seconds, partial_base_seconds,
                         is_bot, role_ids, last_end_time, encrypted_username)
                        VALUES ($1, $2, $3, $4, $5, 1, $6, $6, $7, $8, $9, $10)
                        ON CONFLICT (guild_id, user_id, activity_type, display_name, hour)
                        DO UPDATE SET
                            total_duration_seconds = GREATEST(activity_sessions_hourly.total_duration_seconds, EXCLUDED.total_duration_seconds),
                            partial_base_seconds = GREATEST(activity_sessions_hourly.partial_base_seconds, EXCLUDED.partial_base_seconds),
                            session_count = activity_sessions_hourly.session_count + 1,
                            last_end_time = EXCLUDED.last_end_time,
                            role_ids = EXCLUDED.role_ids,
                            encrypted_username = EXCLUDED.encrypted_username
                    ''',
                                       hour, guild_id, user_id, normalized_type, normalized_name,
                                       duration_seconds, is_bot, role_ids or [], end_time,
                                       encrypted_username
                                       )

                if duration_seconds >= 60:
                    activity_date = end_time.date()
                    try:
                        await self.cog.db.log_daily_activity(
                            guild_id, user_id, activity_date, duration_seconds
                        )
                    except Exception as e:
                        print(
                            f"[WARNING] Failed to log daily activity for user {user_id}: {e}")

                return True

    async def save_all_partial_sessions(self):
        """Save all active partial sessions directly to PostgreSQL"""
        if not self.db_pool or not self.cog:
            return

        current_time = datetime.utcnow()
        saved_count = 0
        skipped_count = 0
        failed_count = 0

        if not self.cog.active_sessions:
            return

        for user_id, sessions in list(self.cog.active_sessions.items()):
            for session_key, session_data in list(sessions.items()):
                try:
                    result = await self.save_partial_session_to_postgresql(
                        guild_id=session_data['guild_id'],
                        user_id=user_id,
                        activity_type=session_data['activity_type'],
                        display_name=session_data['display_name'],
                        start_time=session_data['start_time'],
                        current_time=current_time,
                        is_bot=session_data['is_bot'],
                        role_ids=session_data['role_ids']
                    )
                    if result is True:
                        saved_count += 1
                    elif result is False:
                        skipped_count += 1
                except Exception as e:
                    failed_count += 1
                    print(
                        f"[ERROR] Error saving partial session for user {user_id}: {e}")

        if saved_count > 0 or skipped_count > 0 or failed_count > 0:
            timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            print(
                f"✅ Partial activity session save at {timestamp}: {saved_count} saved, {skipped_count} skipped, {failed_count} failed")

# =========================================================
# ACTIVITY DATABASE
# =========================================================


class ActivityDatabase:
    def __init__(self, bot=None):
        self.pool = None
        self.session_manager = None
        self.is_initialized = False
        self.bot = bot

    def _get_fernet(self):
        """Get fernet instance from DatabaseStats cog."""
        if self.bot:
            db_stats = self.bot.get_cog('DatabaseStats')
            if db_stats and hasattr(db_stats, 'fernet'):
                return db_stats.fernet
        return None

    async def _apply_bot_filter(self, query: str, params: List, guild_id: int, table_name: str = None) -> Tuple[str, List]:
        if not table_name or not self.bot:
            return query, params

        try:
            settings_cog = self.bot.get_cog("Settings")
            if not settings_cog:
                return query, params

            settings = await settings_cog.get_guild_settings(guild_id)
            bot_filter = settings.get('bot_filter', False)

            if not bot_filter:
                return query, params

            tables_with_bot_column = [
                'activity_sessions_hourly', 'daily_activity_log', 'activity_streaks']

            if table_name in tables_with_bot_column:
                condition = "is_bot = FALSE"
                query_upper = query.upper()
                where_pos = query_upper.find("WHERE")
                if where_pos != -1:
                    after_where = where_pos + 5
                    query = query[:after_where] + " " + \
                        condition + " AND" + query[after_where:]
                else:
                    group_by_pos = query_upper.find("GROUP BY")
                    if group_by_pos != -1:
                        insert_position = group_by_pos
                    else:
                        order_by_pos = query_upper.find("ORDER BY")
                        if order_by_pos != -1:
                            insert_position = order_by_pos
                        else:
                            insert_position = len(query)
                    query = query[:insert_position].rstrip(
                    ) + " WHERE " + condition + " " + query[insert_position:].lstrip()

        except Exception as e:
            print(f"[WARNING] Error applying bot filter: {e}")

        return query, params

    async def initialize(self, bot=None):
        if bot:
            self.bot = bot
        try:
            self.pool = await create_db_pool()

            async with self.pool.acquire() as conn:
                # Create table with encrypted_username column
                await conn.execute('''
                CREATE TABLE IF NOT EXISTS activity_sessions_hourly (
                    hour TIMESTAMPTZ NOT NULL,
                    guild_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    activity_type TEXT NOT NULL,
                    display_name TEXT NOT NULL DEFAULT 'Unknown',
                    session_count INT DEFAULT 0,
                    total_duration_seconds INT DEFAULT 0,
                    partial_base_seconds INT DEFAULT 0,
                    is_bot BOOLEAN DEFAULT FALSE,
                    role_ids BIGINT[] DEFAULT '{}',
                    last_end_time TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    encrypted_username TEXT,

                    PRIMARY KEY (guild_id, user_id, activity_type, display_name, hour)
                );
                ''')
                print("✅ activity_sessions_hourly table ready")

                # Add encrypted_username column if missing
                await conn.execute('''
                    ALTER TABLE activity_sessions_hourly 
                    ADD COLUMN IF NOT EXISTS encrypted_username TEXT
                ''')

                # Create daily_activity_log table
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS daily_activity_log (
                        id SERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        user_id BIGINT NOT NULL,
                        activity_date DATE NOT NULL,
                        has_activity BOOLEAN DEFAULT FALSE,
                        total_duration_seconds INTEGER DEFAULT 0,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        UNIQUE(guild_id, user_id, activity_date)
                    )
                ''')
                print("✅ daily_activity_log table ready")

                # Create activity_streaks table
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS activity_streaks (
                        id SERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        user_id BIGINT NOT NULL,
                        current_streak_days INTEGER DEFAULT 0,
                        best_streak_days INTEGER DEFAULT 0,
                        streak_start_date DATE,
                        last_activity_date DATE,
                        updated_at TIMESTAMPTZ DEFAULT NOW(),
                        UNIQUE(guild_id, user_id)
                    )
                ''')
                print("✅ activity_streaks table ready")

                # Create activity_streaks_by_name table for per-activity streaks
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS activity_streaks_by_name (
                        id SERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        user_id BIGINT NOT NULL,
                        activity_type TEXT NOT NULL,
                        display_name TEXT NOT NULL,
                        current_streak_days INTEGER DEFAULT 0,
                        best_streak_days INTEGER DEFAULT 0,
                        streak_start_date DATE,
                        last_activity_date DATE,
                        updated_at TIMESTAMPTZ DEFAULT NOW(),
                        UNIQUE(guild_id, user_id, activity_type, display_name)
                    )
                ''')
                print("✅ activity_streaks_by_name table ready")

                # Create indexes
                await conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_activity_hourly_guild_hour
                    ON activity_sessions_hourly(guild_id, hour DESC)
                ''')
                await conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_activity_hourly_user_hour
                    ON activity_sessions_hourly(user_id, hour DESC)
                ''')
                await conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_activity_hourly_guild_user_hour
                    ON activity_sessions_hourly(guild_id, user_id, hour DESC)
                ''')
                await conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_activity_hourly_role_ids
                    ON activity_sessions_hourly USING GIN(role_ids)
                ''')
                await conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_activity_hourly_is_bot
                    ON activity_sessions_hourly(is_bot)
                ''')
                await conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_activity_hourly_last_end_time
                    ON activity_sessions_hourly(last_end_time DESC)
                ''')
                await conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_daily_activity_log_guild_user_date
                    ON daily_activity_log(guild_id, user_id, activity_date DESC)
                ''')
                await conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_activity_streaks_guild_user
                    ON activity_streaks(guild_id, user_id)
                ''')
                await conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_activity_streaks_best
                    ON activity_streaks(guild_id, best_streak_days DESC)
                ''')
                await conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_activity_streaks_by_name_guild
                    ON activity_streaks_by_name(guild_id, activity_type, best_streak_days DESC)
                ''')
                await conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_activity_streaks_by_name_user
                    ON activity_streaks_by_name(guild_id, user_id, activity_type)
                ''')
                print("✅ All activity indexes created")

                # Create hypertable
                try:
                    await conn.execute("""
                        SELECT create_hypertable(
                            'activity_sessions_hourly',
                            'hour',
                            if_not_exists => TRUE,
                            chunk_time_interval => INTERVAL '7 days',
                            create_default_indexes => FALSE
                        )
                    """)
                    print("✅ Hypertable created for activity_sessions_hourly")
                except Exception as e:
                    print(f"[WARNING] Could not create hypertable: {e}")

            self.session_manager = SessionManager(
                self.pool, self.cog if hasattr(self, 'cog') else None)
            self.is_initialized = True
            return True

        except Exception as e:
            print(f"[ERROR] Database initialization failed: {e}")
            traceback.print_exc()
            raise DatabaseConnectionError(
                "Failed to initialize database", original=e)

    async def get_user_activity_stats(self, guild_id: int, user_id: int, start_time: datetime = None,
                                      end_time: datetime = None, days_back_equiv: int = 14,
                                      role_id: int = None, sort_by: str = "time") -> List[Dict]:
        if not self.pool:
            raise DatabaseConnectionError("No database pool available")

        # If end_time not provided, use current time
        if end_time is None:
            end_time = datetime.now(timezone.utc)

        async with self.pool.acquire() as conn:
            query = '''
                SELECT
                    display_name,
                    activity_type,
                    SUM(session_count) as session_count,
                    SUM(total_duration_seconds) as total_duration_seconds
                FROM activity_sessions_hourly
                WHERE guild_id = $1
                AND user_id = $2
            '''
            params = [guild_id, user_id]
            param_counter = 3

            if start_time is not None:
                query += f" AND hour >= ${param_counter}"
                params.append(start_time)
                param_counter += 1

            query += f" AND hour <= ${param_counter}"
            params.append(end_time)
            param_counter += 1

            if role_id:
                query += f" AND ${param_counter} = ANY(role_ids)"
                params.append(role_id)
                param_counter += 1

            query += " GROUP BY display_name, activity_type"
            query, params = await self._apply_bot_filter(query, params, guild_id, 'activity_sessions_hourly')

            try:
                results = await conn.fetch(query, *params)
                stats = [dict(row) for row in results]

                if sort_by == "sessions":
                    stats.sort(key=lambda x: x['session_count'], reverse=True)
                elif sort_by == "time":
                    stats.sort(
                        key=lambda x: x['total_duration_seconds'] or 0, reverse=True)

                return stats
            except Exception as e:
                print(f"[ERROR] Error in get_user_activity_stats: {e}")
                traceback.print_exc()
                raise DatabaseQueryError(
                    "Failed to fetch user activity stats", original=e)

    async def get_server_activity_stats(self, guild_id: int, start_time: datetime = None,
                                        end_time: datetime = None, days_back_equiv: int = 14,
                                        role_id: int = None, sort_by: str = "users") -> List[Dict]:
        if not self.pool:
            raise DatabaseConnectionError("No database pool available")

        # If end_time not provided, use current time
        if end_time is None:
            end_time = datetime.now(timezone.utc)

        async with self.pool.acquire() as conn:
            query = '''
                SELECT
                    ash.display_name,
                    ash.activity_type,
                    COUNT(DISTINCT ash.user_id) as user_count,
                    SUM(ash.total_duration_seconds) as total_duration_seconds,
                    SUM(ash.session_count) as session_count
                FROM activity_sessions_hourly ash
                WHERE ash.guild_id = $1
            '''
            params = [guild_id]
            param_counter = 2

            if start_time is not None:
                query += f" AND ash.hour >= ${param_counter}"
                params.append(start_time)
                param_counter += 1

            query += f" AND ash.hour <= ${param_counter}"
            params.append(end_time)
            param_counter += 1

            if role_id:
                query += f''' AND ash.user_id IN (
                    SELECT user_id FROM current_role_members
                    WHERE guild_id = $1 AND role_id = ${param_counter}
                )'''
                params.append(role_id)
                param_counter += 1

            query += " GROUP BY ash.display_name, ash.activity_type"
            query, params = await self._apply_bot_filter(query, params, guild_id, 'activity_sessions_hourly')

            try:
                results = await conn.fetch(query, *params)
                stats = [dict(row) for row in results]

                if sort_by == "users":
                    stats.sort(key=lambda x: x['user_count'], reverse=True)
                elif sort_by == "sessions":
                    stats.sort(key=lambda x: x['session_count'], reverse=True)
                elif sort_by == "time":
                    stats.sort(
                        key=lambda x: x['total_duration_seconds'] or 0, reverse=True)

                return stats
            except Exception as e:
                print(f"[ERROR] Error in get_server_activity_stats: {e}")
                traceback.print_exc()
                raise DatabaseQueryError(
                    "Failed to fetch server activity stats", original=e)

    async def get_server_total_activity_sessions(self, guild_id: int, start_time: datetime = None,
                                                 end_time: datetime = None, days_back_equiv: int = 14,
                                                 role_id: int = None) -> int:
        if not self.pool:
            return 0

        # If end_time not provided, use current time
        if end_time is None:
            end_time = datetime.now(timezone.utc)

        async with self.pool.acquire() as conn:
            query = '''
                SELECT COALESCE(SUM(session_count), 0) as total_sessions
                FROM activity_sessions_hourly
                WHERE guild_id = $1
            '''
            params = [guild_id]
            param_counter = 2

            if start_time is not None:
                query += f" AND hour >= ${param_counter}"
                params.append(start_time)
                param_counter += 1

            query += f" AND hour <= ${param_counter}"
            params.append(end_time)
            param_counter += 1

            if role_id:
                query += f" AND ${param_counter} = ANY(role_ids)"
                params.append(role_id)
                param_counter += 1

            query, params = await self._apply_bot_filter(query, params, guild_id, 'activity_sessions_hourly')

            row = await conn.fetchrow(query, *params)
            return row['total_sessions'] if row else 0

    async def get_user_total_activity_sessions(self, guild_id: int, user_id: int, start_time: datetime = None,
                                               end_time: datetime = None, days_back_equiv: int = 14) -> int:
        if not self.pool:
            return 0

        # If end_time not provided, use current time
        if end_time is None:
            end_time = datetime.now(timezone.utc)

        async with self.pool.acquire() as conn:
            query = '''
                SELECT COALESCE(SUM(session_count), 0) as total_sessions
                FROM activity_sessions_hourly
                WHERE guild_id = $1
                AND user_id = $2
            '''
            params = [guild_id, user_id]
            param_counter = 3

            if start_time is not None:
                query += f" AND hour >= ${param_counter}"
                params.append(start_time)
                param_counter += 1

            query += f" AND hour <= ${param_counter}"
            params.append(end_time)
            param_counter += 1

            query, params = await self._apply_bot_filter(query, params, guild_id, 'activity_sessions_hourly')

            row = await conn.fetchrow(query, *params)
            return row['total_sessions'] if row else 0

    async def get_leaderboard_stats(self, guild_id: int, category: str, start_time: datetime = None,
                                    end_time: datetime = None, days_back_equiv: int = 14,
                                    role_id: int = None, sort_by: str = "users") -> List[Dict]:
        if not self.pool:
            raise DatabaseConnectionError("No database pool available")

        # If end_time not provided, use current time
        if end_time is None:
            end_time = datetime.now(timezone.utc)

        async with self.pool.acquire() as conn:
            query = '''
                SELECT
                    ash.display_name,
                    ash.activity_type,
                    COUNT(DISTINCT ash.user_id) as user_count,
                    SUM(ash.total_duration_seconds) as total_duration_seconds,
                    SUM(ash.session_count) as session_count
                FROM activity_sessions_hourly ash
                WHERE ash.guild_id = $1
            '''
            params = [guild_id]
            param_counter = 2

            if start_time is not None:
                query += f" AND ash.hour >= ${param_counter}"
                params.append(start_time)
                param_counter += 1

            query += f" AND ash.hour <= ${param_counter}"
            params.append(end_time)
            param_counter += 1

            if category != "all":
                query += f" AND ash.activity_type = ${param_counter}"
                params.append(category)
                param_counter += 1

            if role_id:
                query += f''' AND ash.user_id IN (
                    SELECT user_id FROM current_role_members
                    WHERE guild_id = $1 AND role_id = ${param_counter}
                )'''
                params.append(role_id)
                param_counter += 1

            query, params = await self._apply_bot_filter(query, params, guild_id, 'activity_sessions_hourly')
            query += " GROUP BY ash.display_name, ash.activity_type"

            try:
                results = await conn.fetch(query, *params)
                stats = [dict(row) for row in results]

                if sort_by == "users":
                    stats.sort(key=lambda x: x['user_count'], reverse=True)
                elif sort_by == "sessions":
                    stats.sort(key=lambda x: x['session_count'], reverse=True)
                elif sort_by == "time":
                    stats.sort(
                        key=lambda x: x['total_duration_seconds'] or 0, reverse=True)

                return stats
            except Exception as e:
                print(f"[ERROR] Error in get_leaderboard_stats: {e}")
                traceback.print_exc()
                raise DatabaseQueryError(
                    "Failed to fetch leaderboard stats", original=e)

    async def get_user_leaderboard_stats(self, guild_id: int, user_id: int, category: str,
                                         start_time: datetime = None, end_time: datetime = None,
                                         days_back_equiv: int = 14, sort_by: str = "time") -> List[Dict]:
        """
        Get leaderboard-style stats for a specific user (top activities per category,
        sorted by time/sessions, for use in the per-user leaderboard view).
        """
        if not self.pool:
            raise DatabaseConnectionError("No database pool available")

        # If end_time not provided, use current time
        if end_time is None:
            end_time = datetime.now(timezone.utc)

        async with self.pool.acquire() as conn:
            query = '''
                SELECT
                    display_name,
                    activity_type,
                    SUM(session_count) as session_count,
                    SUM(total_duration_seconds) as total_duration_seconds
                FROM activity_sessions_hourly
                WHERE guild_id = $1
                AND user_id = $2
            '''
            params = [guild_id, user_id]
            param_counter = 3

            if start_time is not None:
                query += f" AND hour >= ${param_counter}"
                params.append(start_time)
                param_counter += 1

            query += f" AND hour <= ${param_counter}"
            params.append(end_time)
            param_counter += 1

            if category != "all":
                query += f" AND activity_type = ${param_counter}"
                params.append(category)
                param_counter += 1

            query, params = await self._apply_bot_filter(query, params, guild_id, 'activity_sessions_hourly')
            query += " GROUP BY display_name, activity_type"

            try:
                results = await conn.fetch(query, *params)
                stats = [dict(row) for row in results]

                if sort_by == "sessions":
                    stats.sort(key=lambda x: x['session_count'], reverse=True)
                else:
                    stats.sort(
                        key=lambda x: x['total_duration_seconds'] or 0, reverse=True)

                return stats
            except Exception as e:
                print(f"[ERROR] Error in get_user_leaderboard_stats: {e}")
                traceback.print_exc()
                raise DatabaseQueryError(
                    "Failed to fetch user leaderboard stats", original=e)

    async def get_activity_streak_stats(self, guild_id: int, role_id: int = None) -> List[Dict]:
        """
        Get the top activity by best streak per activity_type across the whole server.
        Returns one row per activity_type: the display_name with the highest best_streak_days.
        """
        if not self.pool:
            raise DatabaseConnectionError("No database pool available")

        async with self.pool.acquire() as conn:
            try:
                # Build role filter subquery if needed
                role_filter = ""
                params = [guild_id]
                param_counter = 2

                if role_id:
                    role_filter = f''' AND user_id IN (
                        SELECT user_id FROM current_role_members
                        WHERE guild_id = $1 AND role_id = ${param_counter}
                    )'''
                    params.append(role_id)
                    param_counter += 1

                query = f'''
                    SELECT DISTINCT ON (activity_type)
                        activity_type,
                        display_name,
                        best_streak_days
                    FROM activity_streaks_by_name
                    WHERE guild_id = $1
                    {role_filter}
                    AND best_streak_days > 0
                    ORDER BY activity_type, best_streak_days DESC, display_name
                '''

                results = await conn.fetch(query, *params)
                return [dict(row) for row in results]
            except Exception as e:
                print(f"[ERROR] Error in get_activity_streak_stats: {e}")
                traceback.print_exc()
                raise DatabaseQueryError(
                    "Failed to fetch activity streak stats", original=e)

    async def get_user_activity_streak_stats(self, guild_id: int, user_id: int) -> List[Dict]:
        """
        Get the top activity by best streak per activity_type for a specific user.
        Returns one row per activity_type: the display_name with the highest best_streak_days.
        """
        if not self.pool:
            raise DatabaseConnectionError("No database pool available")

        async with self.pool.acquire() as conn:
            try:
                query = '''
                    SELECT DISTINCT ON (activity_type)
                        activity_type,
                        display_name,
                        best_streak_days
                    FROM activity_streaks_by_name
                    WHERE guild_id = $1
                    AND user_id = $2
                    AND best_streak_days > 0
                    ORDER BY activity_type, best_streak_days DESC, display_name
                '''
                results = await conn.fetch(query, guild_id, user_id)
                return [dict(row) for row in results]
            except Exception as e:
                print(f"[ERROR] Error in get_user_activity_streak_stats: {e}")
                traceback.print_exc()
                raise DatabaseQueryError(
                    "Failed to fetch user activity streak stats", original=e)

    async def upsert_activity_streak_by_name(self, guild_id: int, user_id: int,
                                             activity_type: str, display_name: str,
                                             activity_date: date):
        """
        Called whenever a session ends to keep per-activity streaks up to date.
        Maintains current_streak_days and best_streak_days in activity_streaks_by_name.
        """
        if not self.pool:
            return

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                record = await conn.fetchrow('''
                    SELECT * FROM activity_streaks_by_name
                    WHERE guild_id = $1 AND user_id = $2
                    AND activity_type = $3 AND display_name = $4
                    FOR UPDATE
                ''', guild_id, user_id, activity_type, display_name)

                if not record:
                    await conn.execute('''
                        INSERT INTO activity_streaks_by_name
                        (guild_id, user_id, activity_type, display_name,
                         current_streak_days, best_streak_days,
                         streak_start_date, last_activity_date)
                        VALUES ($1, $2, $3, $4, 1, 1, $5, $5)
                        ON CONFLICT (guild_id, user_id, activity_type, display_name) DO NOTHING
                    ''', guild_id, user_id, activity_type, display_name, activity_date)
                    return

                last = record['last_activity_date']
                current_streak = record['current_streak_days']
                best_streak = record['best_streak_days']

                if last is None:
                    new_streak = 1
                    streak_start = activity_date
                elif (activity_date - last).days == 0:
                    # Same day — no change
                    return
                elif (activity_date - last).days == 1:
                    new_streak = current_streak + 1
                    streak_start = record['streak_start_date']
                else:
                    new_streak = 1
                    streak_start = activity_date

                new_best = max(best_streak, new_streak)

                await conn.execute('''
                    UPDATE activity_streaks_by_name
                    SET current_streak_days = $3,
                        best_streak_days = $4,
                        streak_start_date = $5,
                        last_activity_date = $6,
                        updated_at = NOW()
                    WHERE guild_id = $1 AND user_id = $2
                    AND activity_type = $7 AND display_name = $8
                ''', guild_id, user_id, new_streak, new_best,
                                   streak_start, activity_date,
                                   activity_type, display_name)

    async def get_user_activity_days_and_streak(self, guild_id: int, user_id: int, activity_name: str,
                                                activity_type: str, start_time: datetime = None,
                                                end_time: datetime = None, days_back_equiv: int = 14) -> Dict:
        if not self.pool:
            raise DatabaseConnectionError("No database pool available")

        # If end_time not provided, use current time
        if end_time is None:
            end_time = datetime.now(timezone.utc)

        async with self.pool.acquire() as conn:
            query = '''
                SELECT DISTINCT DATE(hour) as activity_date
                FROM activity_sessions_hourly
                WHERE guild_id = $1
                AND user_id = $2
                AND activity_type = $3
                AND display_name = $4
            '''
            params = [guild_id, user_id, activity_type, activity_name]
            param_counter = 5

            if start_time is not None:
                query += f" AND hour >= ${param_counter}"
                params.append(start_time)
                param_counter += 1

            query += f" AND hour <= ${param_counter}"
            params.append(end_time)
            param_counter += 1

            query, params = await self._apply_bot_filter(query, params, guild_id, 'activity_sessions_hourly')

            try:
                result = await conn.fetch(query, *params)
            except Exception as e:
                print(f"[ERROR] Error fetching activity dates: {e}")
                traceback.print_exc()
                raise DatabaseQueryError(
                    "Failed to fetch activity dates", original=e)

            dates = [row['activity_date'] for row in result]
            total_days = len(dates)

            highest_streak = 0
            current_streak = 0
            previous_date = None

            for current_date in dates:
                if previous_date is None:
                    current_streak = 1
                else:
                    days_diff = (current_date - previous_date).days
                    if days_diff == 1:
                        current_streak += 1
                    else:
                        highest_streak = max(highest_streak, current_streak)
                        current_streak = 1
                previous_date = current_date

            highest_streak = max(highest_streak, current_streak)

            return {
                'days_used': total_days,
                'highest_streak': highest_streak,
                'dates': dates
            }

    async def log_daily_activity(self, guild_id: int, user_id: int, activity_date: date, duration_seconds: int):
        if not self.pool:
            raise DatabaseConnectionError("No database pool available")

        async with self.pool.acquire() as conn:
            try:
                await conn.execute('''
                    INSERT INTO daily_activity_log
                    (guild_id, user_id, activity_date, has_activity, total_duration_seconds)
                    VALUES ($1::bigint, $2::bigint, $3::date, TRUE, $4::integer)
                    ON CONFLICT (guild_id, user_id, activity_date) DO UPDATE
                    SET has_activity = TRUE,
                        total_duration_seconds = daily_activity_log.total_duration_seconds + EXCLUDED.total_duration_seconds,
                        created_at = NOW()
                ''', guild_id, user_id, activity_date, duration_seconds)
            except Exception as e:
                print(f"[ERROR] Error logging daily activity: {e}")
                traceback.print_exc()
                raise DatabaseQueryError(
                    "Failed to log daily activity", original=e)

    async def update_streak_for_user(self, guild_id: int, user_id: int, check_date: date = None):
        if check_date is None:
            check_date = datetime.utcnow().date()

        if not self.pool:
            raise DatabaseConnectionError("No database pool available")

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                try:
                    streak_record = await conn.fetchrow('''
                        SELECT * FROM activity_streaks
                        WHERE guild_id = $1::bigint AND user_id = $2::bigint
                        FOR UPDATE
                    ''', guild_id, user_id)
                except Exception as e:
                    raise DatabaseQueryError(
                        "Failed to fetch streak record", original=e)

                if not streak_record:
                    try:
                        await conn.execute('''
                            INSERT INTO activity_streaks
                            (guild_id, user_id, current_streak_days, best_streak_days,
                            streak_start_date, last_activity_date)
                            VALUES ($1::bigint, $2::bigint, 0, 0, NULL, NULL)
                        ''', guild_id, user_id)
                    except asyncpg.UniqueViolationError:
                        streak_record = await conn.fetchrow('''
                            SELECT * FROM activity_streaks
                            WHERE guild_id = $1::bigint AND user_id = $2::bigint
                        ''', guild_id, user_id)
                    except Exception as e:
                        raise DatabaseQueryError(
                            "Failed to create streak record", original=e)

                if not streak_record:
                    try:
                        streak_record = await conn.fetchrow('''
                            SELECT * FROM activity_streaks
                            WHERE guild_id = $1::bigint AND user_id = $2::bigint
                        ''', guild_id, user_id)
                    except Exception as e:
                        raise DatabaseQueryError(
                            "Failed to fetch newly created streak record", original=e)

                yesterday = check_date - timedelta(days=1)

                try:
                    yesterday_activity = await conn.fetchrow('''
                        SELECT has_activity FROM daily_activity_log
                        WHERE guild_id = $1::bigint AND user_id = $2::bigint AND activity_date = $3::date
                    ''', guild_id, user_id, yesterday)
                except Exception as e:
                    raise DatabaseQueryError(
                        "Failed to fetch yesterday's activity", original=e)

                try:
                    today_activity = await conn.fetchrow('''
                        SELECT has_activity FROM daily_activity_log
                        WHERE guild_id = $1::bigint AND user_id = $2::bigint AND activity_date = $3::date
                    ''', guild_id, user_id, check_date)
                except Exception as e:
                    raise DatabaseQueryError(
                        "Failed to fetch today's activity", original=e)

                current_streak = streak_record['current_streak_days']
                best_streak = streak_record['best_streak_days']
                last_activity = streak_record['last_activity_date']

                if today_activity and today_activity['has_activity']:
                    if yesterday_activity and yesterday_activity['has_activity']:
                        if current_streak == 0:
                            current_streak = 2
                            streak_start = yesterday
                        else:
                            current_streak += 1
                    elif last_activity and (check_date - last_activity).days == 1:
                        current_streak += 1
                    else:
                        current_streak = 1
                        streak_start = check_date

                    if current_streak > best_streak:
                        best_streak = current_streak

                    try:
                        await conn.execute('''
                            UPDATE activity_streaks
                            SET current_streak_days = $3::integer,
                                best_streak_days = $4::integer,
                                streak_start_date = COALESCE($5::date, streak_start_date),
                                last_activity_date = $6::date,
                                updated_at = NOW()
                            WHERE guild_id = $1::bigint AND user_id = $2::bigint
                        ''', guild_id, user_id, current_streak, best_streak,
                                           streak_start if 'streak_start' in locals() else None, check_date)
                    except Exception as e:
                        raise DatabaseQueryError(
                            "Failed to update streak record", original=e)

                    return current_streak, best_streak

                elif current_streak > 0:
                    if last_activity and (check_date - last_activity).days > 1:
                        try:
                            await conn.execute('''
                                UPDATE activity_streaks
                                SET current_streak_days = 0,
                                    streak_start_date = NULL,
                                    updated_at = NOW()
                                WHERE guild_id = $1::bigint AND user_id = $2::bigint
                            ''', guild_id, user_id)
                        except Exception as e:
                            raise DatabaseQueryError(
                                "Failed to reset streak record", original=e)
                        return 0, best_streak

                return current_streak, best_streak

    async def get_user_streak_stats(self, guild_id: int, user_id: int) -> Dict:
        if not self.pool:
            raise DatabaseConnectionError("No database pool available")

        async with self.pool.acquire() as conn:
            try:
                streak_record = await conn.fetchrow('''
                    SELECT current_streak_days, best_streak_days,
                        streak_start_date, last_activity_date
                    FROM activity_streaks
                    WHERE guild_id = $1::bigint AND user_id = $2::bigint
                ''', guild_id, user_id)
            except Exception as e:
                raise DatabaseQueryError(
                    "Failed to fetch streak stats", original=e)

            if not streak_record:
                return {
                    'current_streak': 0,
                    'best_streak': 0,
                    'streak_start': None,
                    'last_activity': None,
                    'is_active_today': False
                }

            today = datetime.utcnow().date()
            try:
                today_activity = await conn.fetchrow('''
                    SELECT has_activity FROM daily_activity_log
                    WHERE guild_id = $1::bigint AND user_id = $2::bigint AND activity_date = $3::date
                ''', guild_id, user_id, today)
            except Exception:
                today_activity = None

            return {
                'current_streak': streak_record['current_streak_days'],
                'best_streak': streak_record['best_streak_days'],
                'streak_start': streak_record['streak_start_date'],
                'last_activity': streak_record['last_activity_date'],
                'is_active_today': today_activity['has_activity'] if today_activity else False
            }

    async def update_all_streaks(self, check_date: date = None):
        if check_date is None:
            check_date = datetime.utcnow().date()

        if not self.pool:
            raise DatabaseConnectionError("No database pool available")

        async with self.pool.acquire() as conn:
            try:
                users = await conn.fetch('''
                    SELECT DISTINCT guild_id, user_id
                    FROM daily_activity_log
                    WHERE activity_date >= $1::date - INTERVAL '30 days'
                ''', check_date)
            except Exception as e:
                raise DatabaseQueryError(
                    "Failed to fetch users for streak update", original=e)

            updated_count = 0
            failed_users = []

            for user in users:
                try:
                    await self.update_streak_for_user(user['guild_id'], user['user_id'], check_date)
                    updated_count += 1
                except DatabaseError as e:
                    failed_users.append({
                        'guild_id': user['guild_id'],
                        'user_id': user['user_id'],
                        'error': str(e)
                    })

            if failed_users and len(failed_users) > len(users) * 0.1:
                raise DatabaseQueryError(
                    f"Failed to update streaks for {len(failed_users)} users")

            print(f"✅ Updated streaks for {updated_count} users.")
            return updated_count


# =========================================================
# IMAGE GENERATION HELPERS
# =========================================================

async def _draw_name_and_avatar_on_image(image, draw, name: str, avatar_url: Optional[str]):
    """
    Shared helper: draws avatar (60x60 circle at 7,10) and name text
    into either a guild-style or user-style header slot.
    """
    avatar_x, avatar_y = 7, 10
    avatar_size = (60, 60)

    if avatar_url:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(avatar_url) as response:
                    avatar_data = await response.read()

            avatar_image = Image.open(io.BytesIO(avatar_data))
            avatar_image = avatar_image.resize(
                avatar_size, Image.Resampling.LANCZOS).convert('RGBA')

            mask = Image.new('L', avatar_size, 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse((0, 0, avatar_size[0], avatar_size[1]), fill=255)
            avatar_image.putalpha(mask)

            avatar_area = image.crop(
                (avatar_x, avatar_y, avatar_x +
                 avatar_size[0], avatar_y + avatar_size[1])
            ).convert('RGBA')

            avatar_with_bg = Image.new('RGBA', avatar_size, (0, 0, 0, 0))
            avatar_with_bg.paste(avatar_image, (0, 0), avatar_image)
            avatar_area.paste(avatar_with_bg, (0, 0), avatar_with_bg)
            image.paste(avatar_area.convert('RGB'), (avatar_x, avatar_y))
            avatar_image.close()
            del avatar_image, avatar_data
        except Exception as e:
            print(f"[WARNING] Could not add avatar: {e}")

    # Draw the name text
    text_start_x, text_start_y = 85, 30
    rect_center = (150, 30)
    rect_width, rect_height = 183, 35

    font_sizes = [40, 38, 36, 34, 32, 30, 28, 26, 24, 22, 20, 18, 16]
    chosen_text = name
    chosen_font = ImageFont.load_default()
    chosen_pos = (text_start_x, text_start_y)

    for font_size in font_sizes:
        try:
            font = ImageFont.truetype(
                BASE_DIR / "assets" / "fonts" / "HorndonD.ttf", font_size)
        except:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), name, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        text_x = text_start_x
        text_y = text_start_y - (text_height // 2)

        v_offset = 0
        if font_size <= 40:
            v_offset += 1
        if font_size <= 30:
            v_offset += 1
        if font_size <= 20:
            v_offset += 1
        if font_size <= 16:
            v_offset += 1
        text_y += v_offset

        rect_left = rect_center[0] - (rect_width // 2)
        rect_right = rect_center[0] + (rect_width // 2)
        rect_top = rect_center[1] - (rect_height // 2)
        rect_bottom = rect_center[1] + (rect_height // 2)

        fits_h = (text_x >= rect_left - 1) and (text_x +
                                                text_width <= rect_right + 1)
        fits_v = (text_y >= rect_top - 1) and (text_y +
                                               text_height <= rect_bottom + 1)

        if fits_h and fits_v:
            chosen_font = font
            chosen_pos = (text_x, text_y)
            break
    else:
        # Truncate fallback
        font = ImageFont.load_default()
        current_text = name
        rect_right = rect_center[0] + (rect_width // 2)
        while len(current_text) > 3:
            current_text = current_text[:-4] + "..."
            bbox = draw.textbbox((0, 0), current_text, font=font)
            if text_start_x + (bbox[2] - bbox[0]) <= rect_right:
                chosen_text = current_text
                break
        chosen_font = font
        chosen_pos = (text_start_x, text_start_y)

    stroke_width = 1
    for dx in [-stroke_width, 0, stroke_width]:
        for dy in [-stroke_width, 0, stroke_width]:
            if dx != 0 or dy != 0:
                draw.text((chosen_pos[0] + dx, chosen_pos[1] + dy),
                          chosen_text, font=chosen_font, fill="black")
    draw.text(chosen_pos, chosen_text, font=chosen_font, fill="white")


def _fit_text_to_activity_rect(draw, text, target_x, target_y,
                               rect_center_x, rect_center_y, rect_width, rect_height,
                               is_left_aligned=True):
    """Fit activity name/value text into a bounded rectangle, shrinking font as needed."""
    font_sizes = [24, 22, 20, 18, 16, 14, 12, 10, 8]

    for font_size in font_sizes:
        try:
            font = ImageFont.truetype(
                BASE_DIR / "assets" / "fonts" / "HorndonD.ttf", font_size)
        except:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        text_x = target_x if is_left_aligned else target_x - (text_width // 2)
        text_y = target_y - (text_height // 2)

        rect_left = rect_center_x - (rect_width // 2)
        rect_right = rect_center_x + (rect_width // 2)
        rect_top = rect_center_y - (rect_height // 2)
        rect_bottom = rect_center_y + (rect_height // 2)

        if (text_x >= rect_left - 1) and (text_x + text_width <= rect_right + 1) \
                and (text_y >= rect_top - 1) and (text_y + text_height <= rect_bottom + 1):
            return text, font, (text_x, text_y)

    # Truncate fallback
    font = ImageFont.load_default()
    current_text = text
    rect_right = rect_center_x + (rect_width // 2)
    while len(current_text) > 3:
        current_text = current_text[:-4] + "..."
        bbox = draw.textbbox((0, 0), current_text, font=font)
        text_x = target_x if is_left_aligned else target_x - \
            (bbox[2] - bbox[0]) // 2
        if text_x + (bbox[2] - bbox[0]) <= rect_right:
            return current_text, font, (text_x, target_y)
    return text[:3] + "...", font, (target_x, target_y)


def _draw_activity_grid(draw, activity_data: list, value_getter, type_positions: dict,
                        invisible_rectangles: list):
    """
    Generic helper to draw the 6-slot activity grid (playing/streaming/listening/
    watching/competing/custom) onto an already-opened image draw context.

    value_getter(activity_dict) -> str  — returns the value string to display.
    """
    activities_by_type: Dict[str, list] = {}
    for activity in activity_data:
        atype = activity.get('activity_type', 'unknown')
        if atype not in activities_by_type:
            activities_by_type[atype] = []
        activities_by_type[atype].append(activity)

    for activity_type, positions in type_positions.items():
        if activity_type not in activities_by_type or not activities_by_type[activity_type]:
            continue

        top = activities_by_type[activity_type][0]
        display_name = top['display_name'][:20]
        name_x, name_y = positions['name']
        value = value_getter(top)
        value_x, value_y = positions['value']

        rect_index = list(type_positions.keys()).index(activity_type) * 2
        name_rect_center, name_rect_width, name_rect_height = invisible_rectangles[rect_index]
        value_rect_center, value_rect_width, value_rect_height = invisible_rectangles[
            rect_index + 1]

        fitted_name, name_font, name_pos = _fit_text_to_activity_rect(
            draw, display_name, name_x, name_y,
            name_rect_center[0], name_rect_center[1],
            name_rect_width, name_rect_height, is_left_aligned=True
        )
        fitted_value, value_font, value_pos = _fit_text_to_activity_rect(
            draw, value, value_x, value_y,
            value_rect_center[0], value_rect_center[1],
            value_rect_width, value_rect_height, is_left_aligned=True
        )

        stroke_width = 1
        for dx in [-stroke_width, 0, stroke_width]:
            for dy in [-stroke_width, 0, stroke_width]:
                if dx != 0 or dy != 0:
                    draw.text((name_pos[0] + dx, name_pos[1] + dy),
                              fitted_name, font=name_font, fill="black")
        draw.text(name_pos, fitted_name, font=name_font, fill="white")

        for dx in [-stroke_width, 0, stroke_width]:
            for dy in [-stroke_width, 0, stroke_width]:
                if dx != 0 or dy != 0:
                    draw.text((value_pos[0] + dx, value_pos[1] + dy),
                              fitted_value, font=value_font, fill="black")
        draw.text(value_pos, fitted_value, font=value_font, fill="white")


# Shared layout constants used by server/streak images
_TYPE_POSITIONS = {
    'playing':   {'name': (20, 135),  'value': (20, 180)},
    'streaming': {'name': (20, 330),  'value': (20, 360)},
    'listening': {'name': (265, 135), 'value': (265, 180)},
    'watching':  {'name': (265, 330), 'value': (265, 360)},
    'competing': {'name': (512, 135), 'value': (512, 180)},
    'custom':    {'name': (512, 330), 'value': (512, 360)}
}

_INVISIBLE_RECTS = [
    ((130, 135), 220, 32), ((130, 180), 220, 32),
    ((130, 330), 220, 32), ((130, 360), 220, 32),
    ((370, 135), 220, 32), ((370, 180), 220, 32),
    ((370, 330), 220, 32), ((370, 360), 220, 32),
    ((620, 135), 220, 32), ((620, 180), 220, 32),
    ((620, 330), 220, 32), ((620, 360), 220, 32)
]


# =========================================================
# IMAGE GENERATION FUNCTIONS
# =========================================================


async def generate_user_activity_image(guild: discord.Guild, user: discord.Member, display_text: str,
                                       activity_data: list, streak_stats: dict, sort_by: str = "time"):
    try:
        template_path = BASE_DIR / "assets" / "images" / "activity user final png.png"
        image = Image.open(template_path)
        if image.mode != "RGB":
            image = image.convert("RGB")
        draw = ImageDraw.Draw(image)

        font_small, font_medium, font_large, font_larger, font_huge, font_giant = get_fonts()

        await _draw_name_and_avatar_on_image(image, draw, user.name, user.display_avatar.url)

        # Use display_text for time period
        draw_text_with_stroke(draw, (550, 38), datetime.now().strftime("%B %d, %Y"),
                              font_small, "white", "black", 1)
        draw_text_with_stroke(
            draw, (630, 457), display_text, font_small, "white", "black", 1)

        if activity_data and len(activity_data) > 0:
            activities_by_type = {
                'playing': [], 'listening': [], 'watching': [],
                'streaming': [], 'competing': [], 'custom': []
            }

            for activity in activity_data:
                activity_type = activity.get('activity_type', 'unknown')
                if activity_type in activities_by_type:
                    activities_by_type[activity_type].append(activity)

            for activity_type in activities_by_type:
                if sort_by == "sessions":
                    activities_by_type[activity_type].sort(
                        key=lambda x: x.get('session_count', 0), reverse=True)
                else:
                    activities_by_type[activity_type].sort(
                        key=lambda x: x.get('total_duration_seconds', 0), reverse=True)

            for activity_type, positions in _TYPE_POSITIONS.items():
                if activity_type not in activities_by_type or not activities_by_type[activity_type]:
                    continue

                top_activity = activities_by_type[activity_type][0]
                display_name = top_activity['display_name'][:20]
                name_x, name_y = positions['name']

                if sort_by == "sessions":
                    value = f"{top_activity.get('session_count', 0)}"
                else:
                    value = format_duration(
                        top_activity.get('total_duration_seconds', 0))

                value_x, value_y = positions['value']
                rect_index = list(_TYPE_POSITIONS.keys()
                                  ).index(activity_type) * 2
                name_rect_center, name_rect_w, name_rect_h = _INVISIBLE_RECTS[rect_index]
                value_rect_center, value_rect_w, value_rect_h = _INVISIBLE_RECTS[rect_index + 1]

                fitted_name, name_font, name_pos = _fit_text_to_activity_rect(
                    draw, display_name, name_x, name_y,
                    name_rect_center[0], name_rect_center[1], name_rect_w, name_rect_h)
                fitted_value, value_font, value_pos = _fit_text_to_activity_rect(
                    draw, value, value_x, value_y,
                    value_rect_center[0], value_rect_center[1], value_rect_w, value_rect_h)

                stroke_width = 1
                for dx in [-stroke_width, 0, stroke_width]:
                    for dy in [-stroke_width, 0, stroke_width]:
                        if dx != 0 or dy != 0:
                            draw.text((name_pos[0] + dx, name_pos[1] + dy),
                                      fitted_name, font=name_font, fill="black")
                draw.text(name_pos, fitted_name, font=name_font, fill="white")

                for dx in [-stroke_width, 0, stroke_width]:
                    for dy in [-stroke_width, 0, stroke_width]:
                        if dx != 0 or dy != 0:
                            draw.text((value_pos[0] + dx, value_pos[1] + dy),
                                      fitted_value, font=value_font, fill="black")
                draw.text(value_pos, fitted_value,
                          font=value_font, fill="white")

        img_bytes = io.BytesIO()
        image.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        gc.collect()
        return discord.File(img_bytes, filename="user_activity.png")

    except Exception as e:
        print(f"[ERROR] Failed to generate user activity image: {e}")
        traceback.print_exc()
        image = Image.new('RGB', (800, 600), color='#2F3136')
        draw = ImageDraw.Draw(image)
        font_small, font_medium, font_large, font_larger, font_huge, font_giant = get_fonts()
        draw_text_with_stroke(draw, (200, 250), "ERROR GENERATING IMAGE",
                              font_larger, "white", "black", 2)
        img_bytes = io.BytesIO()
        image.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return discord.File(img_bytes, filename="user_activity_error.png")


async def generate_server_activity_image(guild: discord.Guild, display_text: str, activity_data: list,
                                         role_id: str = None, sort_by: str = "users", db_pool=None):
    try:
        template_path = BASE_DIR / "assets" / "images" / "activity server final png.png"
        image = Image.open(template_path)
        if image.mode != "RGB":
            image = image.convert("RGB")
        draw = ImageDraw.Draw(image)

        font_small, font_medium, font_large, font_larger, font_huge, font_giant = get_fonts()

        icon_url = guild.icon.url if guild.icon else None
        await _draw_name_and_avatar_on_image(image, draw, guild.name, icon_url)

        role_text = "No Filter"
        if role_id and role_id != "none":
            try:
                role_id_int = int(role_id)
                role_name = None
                if db_pool:
                    async with db_pool.acquire() as conn:
                        row = await conn.fetchrow("""
                            SELECT role_name FROM current_role_members
                            WHERE role_id = $1 AND guild_id = $2
                            LIMIT 1
                        """, role_id_int, guild.id)
                        if row:
                            role_name = row['role_name']
                role_text = role_name if role_name else "Invalid Role"
            except:
                role_text = "Invalid Role"

        draw_text_with_stroke(draw, (65, 459), role_text,
                              font_small, "white", "black", 1)
        draw_text_with_stroke(draw, (550, 38), datetime.now().strftime("%B %d, %Y"),
                              font_small, "white", "black", 1)

        draw_text_with_stroke(
            draw, (630, 457), display_text, font_small, "white", "black", 1)

        if activity_data:
            activities_by_type: Dict[str, list] = {}
            for activity in activity_data:
                atype = activity.get('activity_type', 'unknown')
                if atype not in activities_by_type:
                    activities_by_type[atype] = []
                activities_by_type[atype].append(activity)

            for atype in activities_by_type:
                if sort_by == "users":
                    activities_by_type[atype].sort(
                        key=lambda x: x.get('user_count', 0), reverse=True)
                elif sort_by == "sessions":
                    activities_by_type[atype].sort(
                        key=lambda x: x.get('session_count', 0), reverse=True)
                else:
                    activities_by_type[atype].sort(
                        key=lambda x: x.get('total_duration_seconds', 0), reverse=True)

            def value_getter(top):
                if sort_by == "users":
                    return f"{top.get('user_count', 0)}"
                elif sort_by == "sessions":
                    return f"{top.get('session_count', 0)}"
                else:
                    return format_duration(top.get('total_duration_seconds', 0))

            # Repack into flat list with pre-sorted top entries
            flat = [activities_by_type[t][0]
                    for t in activities_by_type if activities_by_type[t]]
            _draw_activity_grid(draw, flat, value_getter,
                                _TYPE_POSITIONS, _INVISIBLE_RECTS)

        img_bytes = io.BytesIO()
        image.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        gc.collect()
        return discord.File(img_bytes, filename="server_activity.png")

    except Exception as e:
        print(f"[ERROR] Failed to generate server activity image: {e}")
        traceback.print_exc()
        raise


async def generate_activity_leaderboard_image(guild: discord.Guild, leaderboard_data: list,
                                              category: str, display_text: str, role_id: str = None,
                                              sort_by: str = "users", page: int = 0, db_pool=None,
                                              target_user: discord.Member = None):
    """
    Generate the activity leaderboard image.
    If target_user is provided, the header shows that user's name and avatar instead of the guild's.
    """
    try:
        template_path = BASE_DIR / "assets" / "images" / "leaderboards final png.png"
        try:
            image = Image.open(template_path)
        except FileNotFoundError:
            print(f"[WARNING] Template not found, creating blank image")
            image = Image.new('RGB', (800, 600), color='#2F3136')

        if image.mode != "RGB":
            image = image.convert("RGB")

        draw = ImageDraw.Draw(image)
        font_small, font_medium, font_large, font_larger, font_huge, font_giant = get_fonts()

        # Header: show user or guild depending on context
        if target_user is not None:
            header_name = target_user.name
            header_avatar_url = target_user.display_avatar.url
        else:
            header_name = guild.name
            header_avatar_url = guild.icon.url if guild.icon else None

        await _draw_name_and_avatar_on_image(image, draw, header_name, header_avatar_url)

        role_text = "No Filter"
        if role_id and role_id != "none":
            try:
                role_id_int = int(role_id)
                role_name = None
                if db_pool:
                    async with db_pool.acquire() as conn:
                        row = await conn.fetchrow("""
                            SELECT role_name FROM current_role_members
                            WHERE role_id = $1 AND guild_id = $2
                            LIMIT 1
                        """, role_id_int, guild.id)
                        if row:
                            role_name = row['role_name']
                role_text = role_name if role_name else "Invalid Role"
            except:
                role_text = "Invalid Role"

        draw_text_with_stroke(draw, (70, 424), role_text,
                              font_small, "white", "black", 1)

        draw_text_with_stroke(
            draw, (630, 422), display_text, font_small, "white", "black", 1)
        draw_text_with_stroke(draw, (550, 38), datetime.now().strftime("%B %d, %Y"),
                              font_small, "white", "black", 1)

        total_items = len(leaderboard_data)
        total_pages = max(
            1, (total_items + USERS_PER_PAGE - 1) // USERS_PER_PAGE)

        if page >= total_pages:
            page = total_pages - 1
        if page < 0:
            page = 0

        draw_text_with_stroke(
            draw, (400, 450), f"Page {page + 1}/{total_pages}", font_medium, "white", "black", 1)

        if leaderboard_data:
            start_idx = page * USERS_PER_PAGE
            end_idx = min(start_idx + USERS_PER_PAGE, len(leaderboard_data))
            page_data = leaderboard_data[start_idx:end_idx]

            image_width, _ = image.size

            if len(page_data) <= 5:
                positions = [(60, 100 + i * 65) for i in range(len(page_data))]
                box_width, box_height = 600, 40
            else:
                box_width, box_height = 280, 40
                box_spacing = 65
                start_y = 100
                total_box_width = (2 * box_width) + 15
                start_x = (image_width - total_box_width) // 2
                positions = [
                    (start_x + (i % 2) * (box_width + 15),
                     start_y + (i // 2) * box_spacing)
                    for i in range(len(page_data))
                ]

            for i, (activity_item, (box_x, box_y)) in enumerate(zip(page_data, positions)):
                global_rank = start_idx + i + 1

                draw_rounded_rectangle(draw, [box_x, box_y, box_x + box_width, box_y + box_height],
                                       radius=8, fill=(0, 0, 0, 220), outline=None)

                placement_width = 35

                if global_rank == 1:
                    placement_color = (255, 215, 0, 220)
                elif global_rank == 2:
                    placement_color = (192, 192, 192, 220)
                elif global_rank == 3:
                    placement_color = (205, 127, 50, 220)
                else:
                    placement_color = (93, 0, 136, 255)

                draw_rounded_rectangle(draw, [box_x, box_y, box_x + placement_width, box_y + box_height],
                                       radius=8, fill=placement_color, outline=None)

                display_name = activity_item['display_name']

                if target_user is not None:
                    # User leaderboard: sort by time or sessions (no user_count)
                    if sort_by == "sessions":
                        value_text = f"{format_user_count(activity_item.get('session_count', 0))} sessions"
                    else:
                        total_seconds = activity_item.get(
                            'total_duration_seconds', 0) or 0
                        value_text = format_duration(total_seconds)
                else:
                    if sort_by == "users":
                        value_text = f"{format_user_count(activity_item['user_count'])} users"
                    elif sort_by == "sessions":
                        value_text = f"{format_user_count(activity_item['session_count'])} sessions"
                    else:
                        total_seconds = activity_item.get(
                            'total_duration_seconds', 0) or 0
                        value_text = format_duration(total_seconds)

                rank_text = f"#{global_rank}"
                rank_bbox = draw.textbbox((0, 0), rank_text, font=font_medium)
                rank_width = rank_bbox[2] - rank_bbox[0]

                value_bbox = draw.textbbox(
                    (0, 0), value_text, font=font_medium)
                value_width = value_bbox[2] - value_bbox[0]

                available_name_width = box_width - placement_width - value_width - 20

                name_font = font_medium
                name_bbox = draw.textbbox((0, 0), display_name, font=name_font)
                name_width = name_bbox[2] - name_bbox[0]

                if name_width > available_name_width:
                    try:
                        smaller_font = ImageFont.truetype(font_medium.path, 16) if hasattr(
                            font_medium, 'path') else font_small
                        smaller_bbox = draw.textbbox(
                            (0, 0), display_name, font=smaller_font)
                        smaller_width = smaller_bbox[2] - smaller_bbox[0]

                        if smaller_width <= available_name_width:
                            name_font = smaller_font
                        else:
                            while len(display_name) > 3:
                                display_name = display_name[:-4] + "..."
                                truncated_bbox = draw.textbbox(
                                    (0, 0), display_name, font=name_font)
                                if (truncated_bbox[2] - truncated_bbox[0]) <= available_name_width:
                                    break
                    except:
                        while len(display_name) > 3:
                            display_name = display_name[:-4] + "..."
                            truncated_bbox = draw.textbbox(
                                (0, 0), display_name, font=name_font)
                            if (truncated_bbox[2] - truncated_bbox[0]) <= available_name_width:
                                break

                rank_height = rank_bbox[3] - rank_bbox[1]
                name_bbox = draw.textbbox((0, 0), display_name, font=name_font)
                name_height = name_bbox[3] - name_bbox[1]
                value_height = value_bbox[3] - value_bbox[1]

                rank_y = box_y + (box_height - rank_height) // 2
                name_y = box_y + (box_height - name_height) // 2
                value_y = box_y + (box_height - value_height) // 2

                rank_x = box_x + (placement_width - rank_width) // 2
                draw_text_with_stroke(draw, (rank_x, rank_y), rank_text,
                                      font_medium, "white", "black", 1)

                name_x = box_x + placement_width + 8
                draw_text_with_stroke(draw, (name_x, name_y), display_name,
                                      name_font, "white", "black", 1)

                value_x = box_x + box_width - value_width - 8
                draw_text_with_stroke(draw, (value_x, value_y), value_text,
                                      font_medium, "white", "black", 1)
        else:
            cx, cy = image.size[0] // 2, image.size[1] // 2
            draw_text_centered_with_stroke(
                draw, "NO DATA AVAILABLE", (cx, cy), font_giant, "white", "black", 3)

        img_bytes = io.BytesIO()
        image.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        gc.collect()
        return discord.File(img_bytes, filename="activity_leaderboard.png")

    except Exception as e:
        print(f"[ERROR] Failed to generate leaderboard image: {e}")
        traceback.print_exc()
        raise


async def generate_activity_streak_image(guild: discord.Guild, streak_data: list,
                                         role_id: str = None, db_pool=None,
                                         target_user: discord.Member = None):
    """
    Generate the activity streak image using the server activity template.
    Shows the top activity per category with its best streak (in days) instead of
    time/sessions/users.  If target_user is provided the header shows that user.
    """
    try:
        template_path = BASE_DIR / "assets" / "images" / "activity server final png.png"
        image = Image.open(template_path)
        if image.mode != "RGB":
            image = image.convert("RGB")
        draw = ImageDraw.Draw(image)

        font_small, font_medium, font_large, font_larger, font_huge, font_giant = get_fonts()

        # Header
        if target_user is not None:
            header_name = target_user.name
            header_avatar_url = target_user.display_avatar.url
        else:
            header_name = guild.name
            header_avatar_url = guild.icon.url if guild.icon else None

        await _draw_name_and_avatar_on_image(image, draw, header_name, header_avatar_url)

        # Role filter label
        role_text = "No Filter"
        if role_id and role_id != "none":
            try:
                role_id_int = int(role_id)
                role_name = None
                if db_pool:
                    async with db_pool.acquire() as conn:
                        row = await conn.fetchrow("""
                            SELECT role_name FROM current_role_members
                            WHERE role_id = $1 AND guild_id = $2
                            LIMIT 1
                        """, role_id_int, guild.id)
                        if row:
                            role_name = row['role_name']
                role_text = role_name if role_name else "Invalid Role"
            except:
                role_text = "Invalid Role"

        draw_text_with_stroke(draw, (65, 459), role_text,
                              font_small, "white", "black", 1)
        draw_text_with_stroke(draw, (550, 38), datetime.now().strftime("%B %d, %Y"),
                              font_small, "white", "black", 1)

        # Streak data is not time‑windowed, so no time period label here

        if streak_data:
            def streak_value_getter(row):
                days = row.get('best_streak_days', 0) or 0
                return f"{days} days"

            _draw_activity_grid(draw, streak_data, streak_value_getter,
                                _TYPE_POSITIONS, _INVISIBLE_RECTS)

        img_bytes = io.BytesIO()
        image.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        gc.collect()
        return discord.File(img_bytes, filename="activity_streak.png")

    except Exception as e:
        print(f"[ERROR] Failed to generate activity streak image: {e}")
        traceback.print_exc()
        raise


# =========================================================
# UI COMPONENTS
# =========================================================


class SortBySelect(discord.ui.Select):
    def __init__(self, command_type: str, current_value: str = "time"):
        if command_type == "user":
            options = [
                discord.SelectOption(label="By Sessions", value="sessions",
                                     description="Sort by session count",
                                     default=current_value == "sessions"),
                discord.SelectOption(label="By Time", value="time",
                                     description="Sort by total time spent",
                                     default=current_value == "time")
            ]
        elif command_type == "user_leaderboard":
            options = [
                discord.SelectOption(label="By Sessions", value="sessions",
                                     description="Sort by session count",
                                     default=current_value == "sessions"),
                discord.SelectOption(label="By Time", value="time",
                                     description="Sort by total time spent",
                                     default=current_value == "time")
            ]
        else:
            options = [
                discord.SelectOption(label="By Users", value="users",
                                     description="Sort by number of users",
                                     default=current_value == "users"),
                discord.SelectOption(label="By Sessions", value="sessions",
                                     description="Sort by session count",
                                     default=current_value == "sessions"),
                discord.SelectOption(label="By Time", value="time",
                                     description="Sort by total time spent",
                                     default=current_value == "time")
            ]
        super().__init__(placeholder="Sort by...",
                         options=options, custom_id="sort_by_select")

    async def callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False, thinking=False)
        view = self.view
        view.sort_by = self.values[0]
        await view.update_message(interaction)


class CategorySelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild, current_value: str = "all"):
        options = [
            discord.SelectOption(label="All Activities", value="all",
                                 description="Show all activity types", default=current_value == "all"),
            discord.SelectOption(label="Playing", value="playing",
                                 description="Game activities", default=current_value == "playing"),
            discord.SelectOption(label="Streaming", value="streaming",
                                 description="Streaming activities", default=current_value == "streaming"),
            discord.SelectOption(label="Listening", value="listening",
                                 description="Music activities", default=current_value == "listening"),
            discord.SelectOption(label="Watching", value="watching",
                                 description="Video activities", default=current_value == "watching"),
            discord.SelectOption(label="Competing", value="competing",
                                 description="Competitive activities", default=current_value == "competing"),
            discord.SelectOption(label="Custom", value="custom",
                                 description="Custom statuses", default=current_value == "custom")
        ]
        super().__init__(placeholder="Filter category...",
                         options=options, custom_id="category_select")

    async def callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False, thinking=False)
        view = self.view
        view.category = self.values[0]
        await view.update_message(interaction)


class RoleInputModal(discord.ui.Modal, title='Input Role ID'):
    role_id = discord.ui.TextInput(
        label='Enter Role ID or "none"',
        placeholder='e.g., 123456789012345678 or type "none"',
        min_length=1,
        max_length=30,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        view = self.view
        role_input = self.role_id.value.strip().lower()

        if role_input == "none":
            view.role_id = "none"
            await view.update_message(interaction)
            return

        try:
            role_id_int = int(role_input)
            role = interaction.guild.get_role(role_id_int)
            if role:
                view.role_id = str(role_id_int)
                await view.update_message(interaction)
            else:
                embed = discord.Embed(
                    title="Invalid Role ID",
                    description="Sorry! The role id you inputted is not valid, please try again.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
        except ValueError:
            embed = discord.Embed(
                title="Invalid Role ID",
                description="Sorry! The role id you inputted is not valid, please try again.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)


class TimeModal(discord.ui.Modal, title='Custom Time Period'):
    days = discord.ui.TextInput(
        label='Enter number of days',
        placeholder='e.g., 7, 14, 30, 90...',
        min_length=1,
        max_length=4,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            days = int(self.days.value)
            if days <= 0 or days > MAX_CUSTOM_DAYS:
                await interaction.response.send_message(
                    f"❌ Please enter a number between 1 and {MAX_CUSTOM_DAYS} days.", ephemeral=True)
                return
            await interaction.response.defer()
            view = self.view
            now = datetime.now(timezone.utc)
            view.start_time = now - timedelta(days=days)
            view.end_time = now
            view.days_back_equiv = days
            view.display_text = f"{days} days"
            view.using_server_default = False
            view.show_time_buttons = False
            view.page = 0
            await view.update_message(interaction)
        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number.", ephemeral=True)


class PrevButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary,
                         label="⬅️", custom_id="leaderboard_prev")

    async def callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False, thinking=False)
        view = self.view
        if view.page > 0:
            view.page -= 1
            await view.update_message(interaction)


class NextButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary,
                         label="➡️", custom_id="leaderboard_next")

    async def callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False, thinking=False)
        view = self.view
        view.page += 1
        await view.update_message(interaction)


class PageNumberButton(discord.ui.Button):
    def __init__(self, page: int = 0, total_pages: int = 1):
        super().__init__(style=discord.ButtonStyle.primary,
                         label=f"Page {page + 1}/{total_pages}",
                         custom_id="page_number", disabled=False)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        total_items = len(view.last_stats) if hasattr(
            view, 'last_stats') else 0
        total_pages = max(
            1, (total_items + USERS_PER_PAGE - 1) // USERS_PER_PAGE)
        modal = PageJumpModal(view, total_pages)
        await interaction.response.send_modal(modal)


class ActivityView(discord.ui.View):
    """
    Unified view for user, server, leaderboard, user_leaderboard, streak, and user_streak commands.

    command_type values:
      - "user"             : per-user activity stats (existing)
      - "server"           : server-wide activity stats (existing)
      - "leaderboard"      : server-wide ranked list (existing)
      - "user_leaderboard" : per-user ranked list (new)
      - "streak"           : server-wide streak per category (new)
      - "user_streak"      : per-user streak per category (new)
    """

    def __init__(self, cog, guild: discord.Guild, command_type: str,
                 start_time: datetime = None, end_time: datetime = None, days_back_equiv: int = 14,
                 display_text: str = "14 days", initial_role: str = "none",
                 target_user: discord.Member = None, initial_category: str = "all",
                 initial_sort: str = "time", page: int = 0, using_server_default: bool = True):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild = guild
        self.command_type = command_type
        self.start_time = start_time
        self.end_time = end_time if end_time else datetime.now(timezone.utc)
        self.days_back_equiv = days_back_equiv
        self.display_text = display_text
        self.role_id = initial_role
        self.target_user = target_user
        self.category = initial_category
        self.sort_by = initial_sort
        self.page = page
        self.show_time_buttons = False
        self.using_server_default = using_server_default
        self.last_stats = []
        self._update_components()

    def _update_components(self):
        self.clear_items()

        # Category filter: leaderboard types only
        if self.command_type in ("leaderboard", "user_leaderboard"):
            self.add_item(CategorySelect(self.guild, self.category))

        # Sort-by: everything except pure streak views
        if self.command_type in ("user", "server", "leaderboard", "user_leaderboard"):
            self.add_item(SortBySelect(self.command_type, self.sort_by))

        # Pagination: leaderboard types only
        if self.command_type in ("leaderboard", "user_leaderboard"):
            self.add_item(PrevButton())
            total_items = len(self.last_stats) if hasattr(
                self, 'last_stats') else 0
            total_pages = max(
                1, (total_items + USERS_PER_PAGE - 1) // USERS_PER_PAGE)
            self.add_item(PageNumberButton(self.page, total_pages))
            self.add_item(NextButton())

        # Role filter: server, leaderboard, streak (not user-specific commands)
        if self.command_type in ("server", "leaderboard", "streak"):
            role_button = discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label="Input Role Id",
                custom_id="input_role_id"
            )
            role_button.callback = self.role_button_callback
            self.add_item(role_button)

        # Refresh button: always
        refresh_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="🔄 Refresh",
            custom_id="refresh"
        )
        refresh_button.callback = self.refresh_callback
        self.add_item(refresh_button)

        # Time settings: all except pure streak (streaks are not time-windowed)
        if self.command_type not in ("streak", "user_streak"):
            time_settings_button = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="⏰ Time Settings",
                custom_id="time_settings"
            )
            time_settings_button.callback = self.time_settings_callback
            self.add_item(time_settings_button)

            if self.show_time_buttons:
                all_time_button = discord.ui.Button(
                    style=discord.ButtonStyle.primary if self.days_back_equiv == 999999 else discord.ButtonStyle.secondary,
                    label="All Time",
                    custom_id="all_time"
                )
                all_time_button.callback = self.all_time_callback
                self.add_item(all_time_button)

                for days in TIME_PERIODS:
                    days_button = discord.ui.Button(
                        style=discord.ButtonStyle.primary if self.days_back_equiv == days else discord.ButtonStyle.secondary,
                        label=f"{days} Days",
                        custom_id=f"days_{days}"
                    )
                    days_button.callback = self.create_days_callback(days)
                    self.add_item(days_button)

                custom_button = discord.ui.Button(
                    style=discord.ButtonStyle.success,
                    label=f"Custom ({self.days_back_equiv}d)" if self.days_back_equiv not in TIME_PERIODS and self.days_back_equiv != 999999 else "Custom",
                    custom_id="custom_days"
                )
                custom_button.callback = self.custom_days_callback
                self.add_item(custom_button)

    def create_days_callback(self, days: int):
        async def callback(interaction: discord.Interaction):
            await self.handle_button_click(interaction, days=days)
        return callback

    async def all_time_callback(self, interaction: discord.Interaction):
        await self.handle_button_click(interaction, days=999999)

    async def refresh_callback(self, interaction: discord.Interaction):
        await self.handle_button_click(interaction)

    async def time_settings_callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False, thinking=False)
        self.show_time_buttons = not self.show_time_buttons
        self._update_components()
        await interaction.edit_original_response(view=self)

    async def role_button_callback(self, interaction: discord.Interaction):
        modal = RoleInputModal()
        modal.view = self
        await interaction.response.send_modal(modal)

    async def custom_days_callback(self, interaction: discord.Interaction):
        modal = TimeModal()
        modal.view = self
        await interaction.response.send_modal(modal)

    async def handle_button_click(self, interaction: discord.Interaction, days: int = None):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False, thinking=False)
        if days is not None:
            now = datetime.now(timezone.utc)
            if days == 999999:
                self.start_time = None
                self.display_text = "All Time"
            else:
                self.start_time = now - timedelta(days=days)
                self.display_text = f"{days} days"
            self.end_time = now
            self.days_back_equiv = days
            self.using_server_default = False
            self.show_time_buttons = False
            self.page = 0
        await self.update_message(interaction)

    async def update_message(self, interaction: discord.Interaction):
        try:
            if self.command_type == "user":
                role_id_param = None
                if self.role_id != "none":
                    try:
                        role_id_param = int(self.role_id)
                    except ValueError:
                        pass

                stats = await self.cog.db.get_user_activity_stats(
                    self.guild.id, self.target_user.id, self.start_time, self.end_time, self.days_back_equiv, role_id_param, self.sort_by)
                streak_stats = await self.cog.db.get_user_streak_stats(
                    self.guild.id, self.target_user.id)
                file = await generate_user_activity_image(
                    self.guild, self.target_user, self.display_text, stats, streak_stats, self.sort_by)
                self._update_components()
                await interaction.edit_original_response(attachments=[file], view=self)

            elif self.command_type == "server":
                role_id_param = None
                if self.role_id != "none":
                    try:
                        role_id_param = int(self.role_id)
                    except ValueError:
                        pass

                stats = await self.cog.db.get_server_activity_stats(
                    self.guild.id, self.start_time, self.end_time, self.days_back_equiv, role_id_param, self.sort_by)
                file = await generate_server_activity_image(
                    self.guild, self.display_text, stats, self.role_id, self.sort_by)
                self._update_components()
                await interaction.edit_original_response(attachments=[file], view=self)

            elif self.command_type == "leaderboard":
                role_id_param = None
                if self.role_id != "none":
                    try:
                        role_id_param = int(self.role_id)
                    except ValueError:
                        pass

                stats = await self.cog.db.get_leaderboard_stats(
                    self.guild.id, self.category, self.start_time, self.end_time, self.days_back_equiv, role_id_param, self.sort_by)
                self.last_stats = stats

                total_pages = max(
                    1, (len(stats) + USERS_PER_PAGE - 1) // USERS_PER_PAGE)
                if self.page >= total_pages:
                    self.page = max(0, total_pages - 1)

                file = await generate_activity_leaderboard_image(
                    self.guild, stats, self.category, self.display_text,
                    self.role_id, self.sort_by, self.page)
                self._update_components()
                await interaction.edit_original_response(attachments=[file], view=self)

            elif self.command_type == "user_leaderboard":
                stats = await self.cog.db.get_user_leaderboard_stats(
                    self.guild.id, self.target_user.id, self.category, self.start_time, self.end_time, self.days_back_equiv, self.sort_by)
                self.last_stats = stats

                total_pages = max(
                    1, (len(stats) + USERS_PER_PAGE - 1) // USERS_PER_PAGE)
                if self.page >= total_pages:
                    self.page = max(0, total_pages - 1)

                file = await generate_activity_leaderboard_image(
                    self.guild, stats, self.category, self.display_text,
                    "none", self.sort_by, self.page,
                    target_user=self.target_user)
                self._update_components()
                await interaction.edit_original_response(attachments=[file], view=self)

            elif self.command_type == "streak":
                role_id_param = None
                if self.role_id != "none":
                    try:
                        role_id_param = int(self.role_id)
                    except ValueError:
                        pass

                stats = await self.cog.db.get_activity_streak_stats(
                    self.guild.id, role_id_param)
                file = await generate_activity_streak_image(
                    self.guild, stats, self.role_id,
                    db_pool=self.cog.db.pool)
                self._update_components()
                await interaction.edit_original_response(attachments=[file], view=self)

            elif self.command_type == "user_streak":
                stats = await self.cog.db.get_user_activity_streak_stats(
                    self.guild.id, self.target_user.id)
                file = await generate_activity_streak_image(
                    self.guild, stats, "none",
                    db_pool=self.cog.db.pool,
                    target_user=self.target_user)
                self._update_components()
                await interaction.edit_original_response(attachments=[file], view=self)

        except DatabaseError as e:
            print(f"[ERROR] Database error in update_message: {e}")
            embed = discord.Embed(
                title="❌ Database Error",
                description=f"An error occurred while fetching data: {e.message}",
                color=discord.Color.red()
            )
            await interaction.edit_original_response(embed=embed, view=None)
        except Exception as e:
            print(f"[ERROR] Unexpected error in update_message: {e}")
            traceback.print_exc()
            embed = discord.Embed(
                title="❌ Error",
                description="An unexpected error occurred.",
                color=discord.Color.red()
            )
            await interaction.edit_original_response(embed=embed, view=None)


class WhosView(discord.ui.View):
    def __init__(self, cog, guild: discord.Guild, activity_type: str, activity_name: str, page: int = 0):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild = guild
        self.activity_type = activity_type
        self.activity_name = activity_name
        self.page = page
        self.role_id = "none"
        self.users_per_page = 10
        self._update_components()

    def _update_components(self):
        self.clear_items()
        self.add_item(PrevButton())

        total_sessions = self.get_filtered_sessions_count()
        total_pages = max(
            1, (total_sessions + self.users_per_page - 1) // self.users_per_page)
        self.add_item(PageNumberButton(self.page, total_pages))
        self.add_item(NextButton())

        role_button = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="Input Role Id",
            custom_id="whos_input_role_id"
        )
        role_button.callback = self.role_button_callback
        self.add_item(role_button)

        refresh_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="🔄 Refresh",
            custom_id="whos_refresh"
        )
        refresh_button.callback = self.refresh_callback
        self.add_item(refresh_button)

    async def role_button_callback(self, interaction: discord.Interaction):
        modal = RoleInputModal()
        modal.view = self
        await interaction.response.send_modal(modal)

    async def refresh_callback(self, interaction: discord.Interaction):
        await self.update_message(interaction)

    def get_filtered_sessions_count(self):
        count = 0
        for user_id, sessions in self.cog.active_sessions.items():
            for session_key, session_data in sessions.items():
                if (session_data['display_name'].lower() == self.activity_name.lower() and
                    session_data['activity_type'] == self.activity_type and
                        session_data['guild_id'] == self.guild.id):
                    if self.role_id != "none":
                        try:
                            role_id_int = int(self.role_id)
                            member = self.guild.get_member(user_id)
                            if member and role_id_int in [role.id for role in member.roles]:
                                count += 1
                        except:
                            pass
                    else:
                        count += 1
        return count

    def get_filtered_sessions(self):
        current_time = datetime.utcnow()
        current_sessions = []

        for user_id, sessions in self.cog.active_sessions.items():
            for session_key, session_data in sessions.items():
                if (session_data['display_name'].lower() == self.activity_name.lower() and
                    session_data['activity_type'] == self.activity_type and
                        session_data['guild_id'] == self.guild.id):
                    member = self.guild.get_member(user_id)
                    if member:
                        if self.role_id != "none":
                            try:
                                role_id_int = int(self.role_id)
                                if role_id_int in [role.id for role in member.roles]:
                                    duration = current_time - \
                                        session_data['start_time']
                                    current_sessions.append((member, duration))
                            except:
                                pass
                        else:
                            duration = current_time - \
                                session_data['start_time']
                            current_sessions.append((member, duration))

        current_sessions.sort(key=lambda x: x[1], reverse=True)
        return current_sessions

    async def update_message(self, interaction: discord.Interaction):
        current_sessions = self.get_filtered_sessions()
        total_sessions = len(current_sessions)
        total_pages = max(
            1, (total_sessions + self.users_per_page - 1) // self.users_per_page)

        if self.page >= total_pages:
            self.page = total_pages - 1
        if self.page < 0:
            self.page = 0

        start_idx = self.page * self.users_per_page
        end_idx = min(start_idx + self.users_per_page, len(current_sessions))
        page_sessions = current_sessions[start_idx:end_idx]

        role_text = "No Filter"
        if self.role_id != "none":
            try:
                role_id_int = int(self.role_id)
                role_name = None
                db_cog = self.cog.bot.get_cog('DatabaseStats')
                if db_cog and db_cog.pool:
                    async with db_cog.pool.acquire() as conn:
                        row = await conn.fetchrow("""
                            SELECT role_name FROM current_role_members
                            WHERE role_id = $1 AND guild_id = $2
                            LIMIT 1
                        """, role_id_int, self.guild.id)
                        if row:
                            role_name = row['role_name']
                role_text = role_name if role_name else "Invalid Role"
            except:
                role_text = "Invalid Role"

        embed = discord.Embed(
            title=f"👀 Who's {self.activity_type.title()} {self.activity_name}",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )

        if role_text:
            embed.add_field(name="Role Filter", value=role_text, inline=False)

        if page_sessions:
            description = ""
            for i, (member, duration) in enumerate(page_sessions, 1):
                hours, remainder = divmod(int(duration.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                time_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m {seconds}s"
                description += f"{start_idx + i}. {member.mention} - **{time_str}**\n"

            embed.description = description
            embed.set_footer(
                text=f"Page {self.page + 1}/{total_pages} • Total: {total_sessions} users • Updated")
        else:
            embed.description = "No one is currently doing this activity."
            if role_text != "No Filter":
                embed.description += f"\n\n*Filtered by role: {role_text}*"
            embed.color = discord.Color.orange()
            embed.set_footer(text="No users found")

        for child in self.children:
            if isinstance(child, PrevButton):
                child.disabled = (self.page == 0 or total_pages <= 1)
            elif isinstance(child, NextButton):
                child.disabled = (self.page >= total_pages -
                                  1 or total_pages <= 1)
            elif isinstance(child, PageNumberButton):
                child.label = f"Page {self.page + 1}/{total_pages}"

        await interaction.edit_original_response(embed=embed, view=self)

    async def handle_button_click(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.update_message(interaction)


# =========================================================
# MAIN COG CLASS
# =========================================================


class ActivityTracker(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.db = ActivityDatabase(bot)
        self.active_sessions = {}  # user_id -> {session_key: session_data}
        self.user_activities = {}
        self.rate_limiter = get_rate_limiter()

        self.partial_save_loop.start()
        self.cleanup_loop.start()
        self.heartbeat_loop.start()

        self.startup_scan_task = None

    async def cog_load(self):
        if not self.bot.intents.presences:
            print(
                "[WARNING] Presence intent is disabled! on_presence_update will never fire.")
        if not self.bot.intents.members:
            print("[WARNING] Members intent is disabled! This may cause issues.")

        self.db.cog = self

        if self.db.session_manager:
            self.db.session_manager.cog = self

        await self.db.initialize(self.bot)

        self.startup_scan_task = asyncio.create_task(
            self._delayed_startup_scan())

    async def _delayed_startup_scan(self):
        print("⏳ ActivityTracker: Waiting 2 minutes before initial activity scan...")
        await asyncio.sleep(120)

        if not self.bot.is_ready():
            print("⏳ Bot not ready yet, waiting additional 30 seconds...")
            await asyncio.sleep(30)

        await self.scan_current_activities()

    async def scan_current_activities(self):
        """Scan for currently active sessions across all guilds."""
        print("🔄️ Scanning for currently active sessions across all guilds...")
        current_time = datetime.utcnow()
        sessions_found = 0

        for guild in self.bot.guilds:
            if not await self.rate_limiter.acquire(RateLimitType.API, timeout=30.0):
                print(f"  ⚠️ Rate limited for guild {guild.name}, waiting...")
                await asyncio.sleep(5)
                continue

            for member in guild.members:
                if member.bot:
                    continue

                if await self._is_privacy_mode_enabled(member.id, guild.id):
                    continue

                if sessions_found % 100 == 0 and sessions_found > 0:
                    await asyncio.sleep(0.1)

                for activity in member.activities:
                    activity_type = self.get_activity_type(activity)
                    display_name = self.get_activity_name(activity)

                    if not display_name or display_name == "Unknown":
                        continue

                    session_key = f"{guild.id}:{activity_type}:{display_name}"

                    if member.id not in self.active_sessions:
                        self.active_sessions[member.id] = {}

                    if session_key not in self.active_sessions[member.id]:
                        self.active_sessions[member.id][session_key] = {
                            'guild_id': guild.id,
                            'activity_type': activity_type,
                            'display_name': display_name,
                            'start_time': current_time,
                            'last_updated': current_time,
                            'is_bot': member.bot,
                            'role_ids': [role.id for role in member.roles]
                        }
                        sessions_found += 1
                        print(
                            f"  🎮 Tracking: {display_name} ({activity_type})")

            await asyncio.sleep(0.5)

        print(
            f"✅ Startup scan complete: {sessions_found} active sessions now being tracked "
            f"across {len(self.active_sessions)} users")

    def cog_unload(self):
        if self.startup_scan_task and not self.startup_scan_task.done():
            self.startup_scan_task.cancel()

        asyncio.create_task(self.save_all_active_sessions())

        self.partial_save_loop.cancel()
        self.cleanup_loop.cancel()
        self.heartbeat_loop.cancel()

    async def save_all_active_sessions(self):
        print("🔄️ Saving all active sessions before shutdown...")
        current_time = datetime.utcnow()
        saved_count = 0

        for user_id, sessions in list(self.active_sessions.items()):
            for session_key, session_data in list(sessions.items()):
                try:
                    await self.db.session_manager.end_session_to_postgresql(
                        guild_id=session_data['guild_id'],
                        user_id=user_id,
                        activity_type=session_data['activity_type'],
                        display_name=session_data['display_name'],
                        start_time=session_data['start_time'],
                        end_time=current_time,
                        is_bot=session_data['is_bot'],
                        role_ids=session_data['role_ids']
                    )
                    saved_count += 1
                except Exception as e:
                    print(f"[ERROR] Error saving session on shutdown: {e}")

        print(f"✅ Saved {saved_count} active sessions on shutdown")

    @tasks.loop(seconds=PARTIAL_SAVE_INTERVAL)
    async def partial_save_loop(self):
        if self.db.session_manager and self.db.is_initialized:
            try:
                await self.db.session_manager.save_all_partial_sessions()
            except Exception as e:
                print(f"[ERROR] Error in partial save loop: {e}")
                traceback.print_exc()

    @tasks.loop(minutes=1)
    async def heartbeat_loop(self):
        current_time = datetime.utcnow()
        for user_id, sessions in self.active_sessions.items():
            for session_key, session_data in sessions.items():
                session_data['last_updated'] = current_time

    @tasks.loop(minutes=5)
    async def cleanup_loop(self):
        try:
            current_time = datetime.utcnow()
            for user_id, sessions in list(self.active_sessions.items()):
                for session_key, session_data in list(sessions.items()):
                    if (current_time - session_data['last_updated']).total_seconds() > SESSION_THRESHOLD:
                        await self.end_session_cleanup(user_id, session_key, current_time)
        except Exception as e:
            print(f"[ERROR] Error in cleanup loop: {e}")
            traceback.print_exc()

    async def end_session_cleanup(self, user_id: int, session_key: str, end_time: datetime):
        if user_id in self.active_sessions and session_key in self.active_sessions[user_id]:
            session_data = self.active_sessions[user_id].pop(session_key)
            duration = (end_time - session_data['start_time']).total_seconds()

            if duration < 5:
                return

            print(
                f"🧹 Cleaning up stale session for {session_data['display_name']} (duration: {duration:.1f}s)")

            try:
                await self.db.session_manager.end_session_to_postgresql(
                    guild_id=session_data['guild_id'],
                    user_id=user_id,
                    activity_type=session_data['activity_type'],
                    display_name=session_data['display_name'],
                    start_time=session_data['start_time'],
                    end_time=end_time,
                    is_bot=session_data['is_bot'],
                    role_ids=session_data['role_ids']
                )
            except Exception as e:
                print(f"[ERROR] Error saving stale session: {e}")

    async def _get_stat_toggles(self, guild_id: int) -> Dict[str, bool]:
        db_cog = self.bot.get_cog('DatabaseStats')
        if db_cog:
            return await db_cog._get_stat_toggles(guild_id)
        return {'track_status_activity': False}

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        if before.bot:
            return

        if await self._is_privacy_mode_enabled(before.id, before.guild.id):
            return

        toggles = await self._get_stat_toggles(before.guild.id)
        if not toggles.get('track_status_activity'):
            return

        current_time = datetime.utcnow()

        def activity_key(act):
            name = self.get_activity_name(act)
            if name is None:
                return None
            return (act.type, name)

        before_activities = {}
        for a in before.activities:
            key = activity_key(a)
            if key is not None:
                before_activities[key] = a

        after_activities = {}
        for a in after.activities:
            key = activity_key(a)
            if key is not None:
                after_activities[key] = a

        for key, activity in before_activities.items():
            if key not in after_activities:
                await self.end_activity_session(before, activity, current_time)

        for key, activity in after_activities.items():
            if key not in before_activities:
                await self.start_activity_session(after, activity, current_time)

    async def start_activity_session(self, member: discord.Member, activity, start_time: datetime):
        toggles = await self._get_stat_toggles(member.guild.id)
        if not toggles.get('track_status_activity'):
            return
        user_id = member.id
        guild_id = member.guild.id

        if await self._is_privacy_mode_enabled(user_id, guild_id):
            return

        activity_type = self.get_activity_type(activity)
        display_name = self.get_activity_name(activity)

        if not display_name or display_name == "Unknown":
            return

        session_key = f"{guild_id}:{activity_type}:{display_name}"

        if user_id in self.active_sessions and session_key in self.active_sessions[user_id]:
            self.active_sessions[user_id][session_key]['last_updated'] = start_time
            self.active_sessions[user_id][session_key]['role_ids'] = [
                role.id for role in member.roles]
            return

        if user_id not in self.active_sessions:
            self.active_sessions[user_id] = {}

        self.active_sessions[user_id][session_key] = {
            'guild_id': guild_id,
            'activity_type': activity_type,
            'display_name': display_name,
            'start_time': start_time,
            'last_updated': start_time,
            'is_bot': member.bot,
            'role_ids': [role.id for role in member.roles]
        }

    async def end_activity_session(self, member: discord.Member, activity, end_time: datetime):
        toggles = await self._get_stat_toggles(member.guild.id)
        if not toggles.get('track_status_activity'):
            return
        user_id = member.id
        guild_id = member.guild.id

        if await self._is_privacy_mode_enabled(user_id, guild_id):
            return

        activity_type = self.get_activity_type(activity)
        display_name = self.get_activity_name(activity)

        if not display_name:
            return

        session_key = f"{guild_id}:{activity_type}:{display_name}"

        if user_id in self.active_sessions and session_key in self.active_sessions[user_id]:
            session_data = self.active_sessions[user_id].pop(session_key)

            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=timezone.utc)
            if session_data['start_time'].tzinfo is None:
                session_data['start_time'] = session_data['start_time'].replace(
                    tzinfo=timezone.utc)

            duration = (end_time - session_data['start_time']).total_seconds()

            if duration < 5:
                return

            try:
                await self.db.session_manager.end_session_to_postgresql(
                    guild_id=guild_id,
                    user_id=user_id,
                    activity_type=activity_type,
                    display_name=display_name,
                    start_time=session_data['start_time'],
                    end_time=end_time,
                    is_bot=member.bot,
                    role_ids=session_data['role_ids']
                )
            except Exception as e:
                print(f"[ERROR] Error saving ended session: {e}")

            # Update per-activity streak
            try:
                activity_date = end_time.date() if end_time.tzinfo else end_time.replace(
                    tzinfo=timezone.utc).date()
                await self.db.upsert_activity_streak_by_name(
                    guild_id, user_id, activity_type, display_name, activity_date)
            except Exception as e:
                print(
                    f"[WARNING] Failed to update activity streak by name: {e}")

    def get_activity_type(self, activity) -> str:
        if activity.type == discord.ActivityType.playing:
            return "playing"
        elif activity.type == discord.ActivityType.streaming:
            return "streaming"
        elif activity.type == discord.ActivityType.listening:
            return "listening"
        elif activity.type == discord.ActivityType.watching:
            return "watching"
        elif activity.type == discord.ActivityType.competing:
            return "competing"
        elif activity.type == discord.ActivityType.custom:
            return "custom"
        else:
            return "unknown"

    def get_activity_name(self, activity) -> Optional[str]:
        """
        Returns the display name for an activity, or None if it should be skipped.
        Skips ALL custom statuses — these are just user notes, not real activities.
        """
        if activity.type == discord.ActivityType.custom:
            return None

        if hasattr(activity, 'name') and activity.name:
            return activity.name
        elif hasattr(activity, 'details') and activity.details:
            return activity.details

        return "Unknown"

    async def scan_guild_activities(self, guild: discord.Guild) -> int:
        """Scan a specific guild for currently active activity sessions and start tracking them."""
        if not self.db.is_initialized:
            print(
                f"⚠️ Cannot scan activities for {guild.name} - database not initialized")
            return 0

        print(f"\n🎮 SCANNING ACTIVITY SESSIONS FOR GUILD: {guild.name}")

        current_time = datetime.utcnow()
        sessions_found = 0

        if not await self.rate_limiter.acquire(RateLimitType.API, timeout=30.0):
            print(f"  ⚠️ Rate limited for guild {guild.name}, waiting...")
            await asyncio.sleep(5)
            return 0

        for member in guild.members:
            if member.bot:
                continue

            if await self._is_privacy_mode_enabled(member.id, guild.id):
                continue

            if sessions_found % 100 == 0 and sessions_found > 0:
                await asyncio.sleep(0.1)

            for activity in member.activities:
                activity_type = self.get_activity_type(activity)
                display_name = self.get_activity_name(activity)

                if not display_name or display_name == "Unknown":
                    continue

                session_key = f"{guild.id}:{activity_type}:{display_name}"

                if member.id not in self.active_sessions:
                    self.active_sessions[member.id] = {}

                if session_key not in self.active_sessions[member.id]:
                    self.active_sessions[member.id][session_key] = {
                        'guild_id': guild.id,
                        'activity_type': activity_type,
                        'display_name': display_name,
                        'start_time': current_time,
                        'last_updated': current_time,
                        'is_bot': member.bot,
                        'role_ids': [role.id for role in member.roles]
                    }
                    sessions_found += 1

        print(
            f"✅ Found {sessions_found} active activity sessions in guild {guild.name}")
        return sessions_found

    async def _is_privacy_mode_enabled(self, user_id: int, guild_id: int) -> bool:
        """Check if a user has privacy mode enabled for a specific guild."""
        try:
            settings_cog = self.bot.get_cog("Settings")
            if not settings_cog:
                return False

            user_settings = await settings_cog.get_user_settings(user_id, guild_id)
            return user_settings.get('privacy_enabled', False)

        except Exception as e:
            print(
                f"⚠️ Privacy check error for user {user_id} in guild {guild_id}: {e}")
            return False

    # =========================================================
    # GET SERVER DEFAULT TIME RANGE
    # =========================================================

    async def get_server_default_time_range(self, guild_id: int) -> tuple:
        """Get the default time range from server settings. Returns (start_time, end_time, display_text, days_back_equiv)"""
        try:
            settings_cog = self.bot.get_cog('Settings')
            if not settings_cog:
                end = datetime.now(timezone.utc)
                start = end - timedelta(days=14)
                return (start, end, "14 days", 14)

            settings = await settings_cog.get_guild_settings(guild_id)
            mode = settings.get('default_time_mode', 'days_back')
            now = datetime.now(timezone.utc)

            if mode == 'all_time':
                return (None, now, "All Time", 999999)

            elif mode == 'days_back':
                days = settings.get('default_days_back') or 14
                start = now - timedelta(days=days)
                return (start, now, f"{days} days", days)

            elif mode == 'date_range':
                from_date = settings.get('default_from_date')
                to_date = settings.get('default_to_date')

                # Add timezone awareness guards
                if from_date is not None and from_date.tzinfo is None:
                    from_date = from_date.replace(tzinfo=timezone.utc)
                if to_date is not None and to_date.tzinfo is None:
                    to_date = to_date.replace(tzinfo=timezone.utc)

                end = to_date if to_date else now
                start = from_date if from_date else None
                from_str = from_date.strftime(
                    '%d-%m-%Y') if from_date else None
                to_str = to_date.strftime('%d-%m-%Y') if to_date else None
                if from_str and to_str:
                    display = f"Custom"
                elif from_str:
                    display = f"Custom"
                elif to_str:
                    display = f"Custom"
                else:
                    display = "Custom"
                days_back = max(1, (end - start).days) if start else 999999
                return (start, end, display, days_back)

            elif mode == 'rolling_window':
                rolling_type = settings.get('default_rolling_type')
                rolling_value = settings.get('default_rolling_value')

                if rolling_type == 'weekday' and rolling_value is not None:
                    days_since = (now.weekday() - rolling_value) % 7
                    if days_since == 0:
                        days_since = 7
                    start = (now - timedelta(days=days_since)).replace(
                        hour=0, minute=0, second=0, microsecond=0)
                    weekday_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday',
                                     'Friday', 'Saturday', 'Sunday']
                    display = f"Custom"
                    return (start, now, display, days_since)

                elif rolling_type == 'monthly' and rolling_value is not None:
                    import calendar
                    current_day = now.day
                    if current_day >= rolling_value:
                        try:
                            start = now.replace(day=rolling_value, hour=0, minute=0,
                                                second=0, microsecond=0)
                        except ValueError:
                            last_day = calendar.monthrange(
                                now.year, now.month)[1]
                            start = now.replace(day=last_day, hour=0, minute=0,
                                                second=0, microsecond=0)
                    else:
                        prev_month = now.month - 1 if now.month > 1 else 12
                        prev_year = now.year if now.month > 1 else now.year - 1
                        try:
                            start = now.replace(year=prev_year, month=prev_month,
                                                day=rolling_value, hour=0, minute=0,
                                                second=0, microsecond=0)
                        except ValueError:
                            last_day = calendar.monthrange(
                                prev_year, prev_month)[1]
                            start = now.replace(year=prev_year, month=prev_month,
                                                day=last_day, hour=0, minute=0,
                                                second=0, microsecond=0)
                    days_back = max(1, (now - start).days)
                    suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(
                        rolling_value % 10 if rolling_value % 100 not in (11, 12, 13) else 0, 'th')
                    display = f"Custom"
                    return (start, now, display, days_back)

            end = now - timedelta(days=0)
            start = now - timedelta(days=14)
            return (start, end, "14 days", 14)

        except Exception as e:
            import traceback
            traceback.print_exc()
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=14)
            return (start, end, "14 days", 14)

    # =========================================================
    # SHARED COMMAND HANDLER
    # =========================================================

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def _handle_activity_command(self, ctx_or_interaction, command_type: str, target_user=None,
                                       activity_type=None, activity_name=None, is_interaction=False):
        try:
            if is_interaction:
                await ctx_or_interaction.response.defer()
                user = ctx_or_interaction.user
                guild = ctx_or_interaction.guild
                send_method = ctx_or_interaction.followup.send
            else:
                user = ctx_or_interaction.author
                guild = ctx_or_interaction.guild
                try:
                    await ctx_or_interaction.message.delete()
                except:
                    pass
                send_method = ctx_or_interaction.send

            # Get retention alert once for all branches
            _db_stats = self.bot.get_cog('DatabaseStats')
            _retention_alert = await _db_stats.maybe_get_retention_alert(guild.id) if _db_stats else None

            if guild is None:
                msg = "❌ This command can only be used in a server."
                if is_interaction:
                    await ctx_or_interaction.followup.send(msg, ephemeral=True)
                else:
                    await send_method(msg, delete_after=5)
                return

            # Get server default time range
            start_time, end_time, display_text, days_back_equiv = await self.get_server_default_time_range(guild.id)

            # ---- user activity ----
            if command_type == "user":
                if target_user is None:
                    target_user = user

                view = ActivityView(self, guild, "user", start_time, end_time, days_back_equiv, display_text,
                                    "none", target_user, "all", "time", 0, using_server_default=True)
                stats = await self.db.get_user_activity_stats(guild.id, target_user.id, start_time, end_time, days_back_equiv, None, "time")
                streak_stats = await self.db.get_user_streak_stats(guild.id, target_user.id)
                file = await generate_user_activity_image(guild, target_user, display_text, stats, streak_stats, "time")
                await send_method(content=_retention_alert, file=file, view=view)

            # ---- server activity ----
            elif command_type == "server":
                view = ActivityView(self, guild, "server", start_time, end_time, days_back_equiv, display_text,
                                    "none", None, "all", "users", 0, using_server_default=True)
                stats = await self.db.get_server_activity_stats(guild.id, start_time, end_time, days_back_equiv, None, "users")
                file = await generate_server_activity_image(guild, display_text, stats, "none", "users")
                await send_method(content=_retention_alert, file=file, view=view)

            # ---- leaderboard (server or per-user) ----
            elif command_type == "leaderboard":
                if target_user is not None:
                    # Per-user leaderboard
                    view = ActivityView(self, guild, "user_leaderboard", start_time, end_time, days_back_equiv, display_text,
                                        "none", target_user, "all", "time", 0, using_server_default=True)
                    stats = await self.db.get_user_leaderboard_stats(
                        guild.id, target_user.id, "all", start_time, end_time, days_back_equiv, "time")
                    view.last_stats = stats
                    file = await generate_activity_leaderboard_image(
                        guild, stats, "all", display_text, "none", "time", 0,
                        target_user=target_user)
                else:
                    # Server leaderboard
                    view = ActivityView(self, guild, "leaderboard", start_time, end_time, days_back_equiv, display_text,
                                        "none", None, "all", "users", 0, using_server_default=True)
                    stats = await self.db.get_leaderboard_stats(guild.id, "all", start_time, end_time, days_back_equiv, None, "users")
                    view.last_stats = stats
                    file = await generate_activity_leaderboard_image(
                        guild, stats, "all", display_text, "none", "users", 0)
                await send_method(content=_retention_alert, file=file, view=view)

            # ---- streak (server or per-user) ----
            elif command_type == "streak":
                if target_user is not None:
                    # Per-user streak
                    view = ActivityView(self, guild, "user_streak", start_time, end_time, days_back_equiv, display_text,
                                        "none", target_user, "all", "time", 0, using_server_default=True)
                    stats = await self.db.get_user_activity_streak_stats(guild.id, target_user.id)
                    file = await generate_activity_streak_image(
                        guild, stats, "none",
                        db_pool=self.db.pool,
                        target_user=target_user)
                else:
                    # Server streak
                    view = ActivityView(self, guild, "streak", start_time, end_time, days_back_equiv, display_text,
                                        "none", None, "all", "users", 0, using_server_default=True)
                    stats = await self.db.get_activity_streak_stats(guild.id, None)
                    file = await generate_activity_streak_image(
                        guild, stats, "none",
                        db_pool=self.db.pool)
                await send_method(content=_retention_alert, file=file, view=view)

            # ---- whos ----
            elif command_type == "whos":
                if not activity_type or not activity_name:
                    if is_interaction:
                        await send_method("❌ Please provide activity type and name.", ephemeral=True)
                    else:
                        await send_method("❌ Usage: `aw <type> <name>` - e.g., `aw playing Minecraft`", delete_after=10)
                    return

                view = WhosView(self, guild, activity_type, activity_name, 0)
                current_time = datetime.utcnow()
                current_sessions = []

                for uid, sessions in self.active_sessions.items():
                    for session_key, session_data in sessions.items():
                        if (session_data['display_name'].lower() == activity_name.lower() and
                            session_data['activity_type'] == activity_type and
                                session_data['guild_id'] == guild.id):
                            member = guild.get_member(uid)
                            if member:
                                duration = current_time - \
                                    session_data['start_time']
                                current_sessions.append((member, duration))

                current_sessions.sort(key=lambda x: x[1], reverse=True)

                total_sessions = len(current_sessions)
                total_pages = max(
                    1, (total_sessions + view.users_per_page - 1) // view.users_per_page)
                page_sessions = current_sessions[:view.users_per_page]

                embed = discord.Embed(
                    title=f"👀 Who's {activity_type.title()} {activity_name}",
                    color=discord.Color.green(),
                    timestamp=datetime.utcnow()
                )

                if page_sessions:
                    description = ""
                    for i, (member, duration) in enumerate(page_sessions, 1):
                        hours, remainder = divmod(
                            int(duration.total_seconds()), 3600)
                        minutes, seconds = divmod(remainder, 60)
                        time_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m {seconds}s"
                        description += f"{i}. {member.mention} - **{time_str}**\n"
                    embed.description = description
                    embed.set_footer(
                        text=f"Page 1/{total_pages} • Total: {total_sessions} users • Updated")
                else:
                    embed.description = "No one is currently doing this activity."
                    embed.color = discord.Color.orange()
                    embed.set_footer(text="No users found")

                await send_method(content=_retention_alert, embed=embed, view=view)

        except Exception as e:
            print(f"[ERROR] Error in _handle_activity_command: {e}")
            traceback.print_exc()
            error_msg = "❌ An error occurred while processing your request."
            if is_interaction:
                try:
                    await ctx_or_interaction.followup.send(error_msg, ephemeral=True)
                except:
                    pass
            else:
                try:
                    await send_method(error_msg, delete_after=10)
                except:
                    pass

    # =========================================================
    # SHORTCUT COMMANDS
    # =========================================================

    @commands.command(name="au")
    async def activity_user_shortcut(self, ctx: commands.Context, user: discord.Member = None):
        await self._handle_activity_command(ctx, "user", target_user=user, is_interaction=False)

    @commands.command(name="as")
    async def activity_server_shortcut(self, ctx: commands.Context):
        await self._handle_activity_command(ctx, "server", is_interaction=False)

    @commands.command(name="al")
    async def activity_leaderboard_shortcut(self, ctx: commands.Context, user: discord.Member = None):
        await self._handle_activity_command(ctx, "leaderboard", target_user=user, is_interaction=False)

    @commands.command(name="aw")
    async def activity_whos_shortcut(self, ctx: commands.Context, activity_type: str, *, activity_name: str):
        await self._handle_activity_command(ctx, "whos", activity_type=activity_type,
                                            activity_name=activity_name, is_interaction=False)

    @commands.command(name="sas")
    async def activity_streak_shortcut(self, ctx: commands.Context, user: discord.Member = None):
        """Shortcut for activity streak. Usage: sas [user]"""
        await self._handle_activity_command(ctx, "streak", target_user=user, is_interaction=False)

    # =========================================================
    # PREFIX COMMAND GROUP
    # =========================================================

    @commands.group(name="status", invoke_without_command=True)
    async def status_group(self, ctx: commands.Context):
        await ctx.send(
            "Available commands:\n"
            "- `status activity user [user]` - Show user activity stats\n"
            "- `status activity server` - Show server activity stats\n"
            "- `status activity leaderboard [user]` - Show activity leaderboard (server or user)\n"
            "- `status activity whos <type> <name>` - See who's doing an activity\n"
            "- `status activity streak [user]` - Show activity streaks (server or user)\n\n"
            "Shortcuts:\n"
            "- `au [user]` - Activity user\n"
            "- `as` - Activity server\n"
            "- `al [user]` - Activity leaderboard\n"
            "- `aw <type> <name>` - Activity whos\n"
            "- `sas [user]` - Activity streak"
        )

    @status_group.group(name="activity", invoke_without_command=True)
    async def status_activity_group(self, ctx: commands.Context):
        await ctx.send(
            "Available activity commands:\n"
            "- `status activity user [user]` - Show user activity stats\n"
            "- `status activity server` - Show server activity stats\n"
            "- `status activity leaderboard [user]` - Show activity leaderboard (server or user)\n"
            "- `status activity whos <type> <name>` - See who's doing an activity\n"
            "- `status activity streak [user]` - Show activity streaks (server or user)\n\n"
            "Shortcuts:\n"
            "- `au [user]` - Activity user\n"
            "- `as` - Activity server\n"
            "- `al [user]` - Activity leaderboard\n"
            "- `aw <type> <name>` - Activity whos\n"
            "- `sas [user]` - Activity streak"
        )

    @status_activity_group.command(name="user")
    async def status_activity_user_prefix(self, ctx: commands.Context, user: discord.Member = None):
        await self._handle_activity_command(ctx, "user", target_user=user, is_interaction=False)

    @status_activity_group.command(name="server")
    async def status_activity_server_prefix(self, ctx: commands.Context):
        await self._handle_activity_command(ctx, "server", is_interaction=False)

    @status_activity_group.command(name="leaderboard")
    async def status_activity_leaderboard_prefix(self, ctx: commands.Context, user: discord.Member = None):
        """Show activity leaderboard. If a user is provided, shows that user's top activities."""
        await self._handle_activity_command(ctx, "leaderboard", target_user=user, is_interaction=False)

    @status_activity_group.command(name="whos")
    async def status_activity_whos_prefix(self, ctx: commands.Context, activity_type: str, *, activity_name: str):
        await self._handle_activity_command(ctx, "whos", activity_type=activity_type,
                                            activity_name=activity_name, is_interaction=False)

    @status_activity_group.command(name="streak")
    async def status_activity_streak_prefix(self, ctx: commands.Context, user: discord.Member = None):
        """Show activity streaks per category. If a user is provided, shows that user's streaks."""
        await self._handle_activity_command(ctx, "streak", target_user=user, is_interaction=False)

    # =========================================================
    # SLASH COMMAND GROUP
    # =========================================================

    status_group_slash = app_commands.Group(
        name="status", description="Status tracking commands")

    activity_subgroup = app_commands.Group(
        name="activity", description="Activity tracking commands", parent=status_group_slash)

    @activity_subgroup.command(name="user", description="View a user's activity statistics")
    @app_commands.describe(user="The user to check activity for")
    async def status_activity_user(self, interaction: discord.Interaction, user: discord.Member):
        await self._handle_activity_command(interaction, "user", target_user=user, is_interaction=True)

    @activity_subgroup.command(name="server", description="View server activity statistics")
    async def status_activity_server(self, interaction: discord.Interaction):
        await self._handle_activity_command(interaction, "server", is_interaction=True)

    @activity_subgroup.command(
        name="leaderboard",
        description="Show activity leaderboard for the server, or top activities for a specific user")
    @app_commands.describe(user="Optional: show leaderboard for this user instead of the server")
    async def status_activity_leaderboard(self, interaction: discord.Interaction,
                                          user: Optional[discord.Member] = None):
        await self._handle_activity_command(interaction, "leaderboard", target_user=user, is_interaction=True)

    @activity_subgroup.command(name="whos", description="See who's currently doing an activity")
    @app_commands.describe(activity_type="Type of activity", activity_name="Name of the activity")
    @app_commands.choices(activity_type=[
        app_commands.Choice(name="Playing", value="playing"),
        app_commands.Choice(name="Streaming", value="streaming"),
        app_commands.Choice(name="Listening", value="listening"),
        app_commands.Choice(name="Watching", value="watching"),
        app_commands.Choice(name="Competing", value="competing"),
        app_commands.Choice(name="Custom", value="custom")
    ])
    async def status_activity_whos(self, interaction: discord.Interaction,
                                   activity_type: str, activity_name: str):
        await self._handle_activity_command(interaction, "whos", activity_type=activity_type,
                                            activity_name=activity_name, is_interaction=True)

    @activity_subgroup.command(
        name="streak",
        description="Show top activity streaks per category for the server or a specific user")
    @app_commands.describe(user="Optional: show streaks for this user instead of the server")
    async def status_activity_streak(self, interaction: discord.Interaction,
                                     user: Optional[discord.Member] = None):
        await self._handle_activity_command(interaction, "streak", target_user=user, is_interaction=True)


# =========================================================
# SETUP
# =========================================================

async def setup(bot):
    await bot.add_cog(ActivityTracker(bot))
