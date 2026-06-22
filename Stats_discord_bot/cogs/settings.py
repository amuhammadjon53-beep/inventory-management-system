import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncpg
import asyncio
from typing import Optional
import os
import aiocron
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta
from .ratelimiter import RateLimiter, RateLimitType, rate_limited, get_rate_limiter


# ============================================================
# MODULE-LEVEL HELPERS
# ============================================================

def get_ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return 'th'
    return {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')


def format_time_period_display(settings: dict) -> str:
    """Return a human-readable string for the current time period setting."""
    mode = settings.get('default_time_mode', 'days_back')
    if mode == 'all_time':
        return "All Time"
    elif mode == 'days_back':
        days = settings.get('default_days_back') or 14
        return f"Last {days} days"
    elif mode == 'date_range':
        from_date = settings.get('default_from_date')
        to_date = settings.get('default_to_date')
        from_str = from_date.strftime('%d-%m-%Y') if from_date else None
        to_str = to_date.strftime('%d-%m-%Y') if to_date else None
        if from_str and to_str:
            return f"{from_str} to {to_str}"
        elif from_str:
            return f"From {from_str} to now"
        elif to_str:
            return f"From the beginning to {to_str}"
        return "Date Range (not fully configured)"
    elif mode == 'rolling_window':
        rolling_type = settings.get('default_rolling_type')
        rolling_value = settings.get('default_rolling_value')
        if rolling_type == 'weekday' and rolling_value is not None:
            weekday_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday',
                             'Friday', 'Saturday', 'Sunday']
            day_name = weekday_names[rolling_value] if 0 <= rolling_value <= 6 else 'Unknown'
            return f"Rolling window — every {day_name}"
        elif rolling_type == 'monthly' and rolling_value is not None:
            return f"Rolling window — {rolling_value}{get_ordinal(rolling_value)} of each month"
        return "Rolling Window (not fully configured)"
    return "Last 14 days"


def parse_weekday(s: str) -> Optional[int]:
    """Parse a weekday name or number (0=Monday … 6=Sunday). Returns None if invalid."""
    s = s.strip().lower()
    mapping = {
        'monday': 0, 'mon': 0, '0': 0,
        'tuesday': 1, 'tue': 1, '1': 1,
        'wednesday': 2, 'wed': 2, '2': 2,
        'thursday': 3, 'thu': 3, '3': 3,
        'friday': 4, 'fri': 4, '4': 4,
        'saturday': 5, 'sat': 5, '5': 5,
        'sunday': 6, 'sun': 6, '6': 6,
    }
    return mapping.get(s)


def parse_date_string(s: str) -> Optional[datetime]:
    """Parse a date string in DD-MM-YYYY format. Returns None if invalid."""
    try:
        return datetime.strptime(s.strip(), '%d-%m-%Y')
    except ValueError:
        return None


# Stat toggle metadata: key -> (display_label, description, default)
STAT_TOGGLE_META = {
    'track_messages': (
        'Messages',
        'Track how many messages each user sends, including character counts, attachments, and embeds.',
        True,
    ),
    'track_voice': (
        'Voice',
        'Track time users spend in voice channels, including session counts and state flags (mute, deafen, stream, video).',
        True,
    ),
    'track_invites': (
        'Invites',
        'Track which invite links are used when members join, and detect suspicious invites based on account age.',
        True,
    ),
    'track_mentions': (
        'Mentions',
        'Track when users mention each other in messages, including who was mentioned and by whom.',
        False,
    ),
    'track_emojis': (
        'Emojis',
        'Track emoji usage in messages and reactions, including both custom and standard Unicode emojis.',
        False,
    ),
    'track_status_activity': (
        'Status Activity',
        'Track game and application activity sessions when users show a Rich Presence status.',
        False,
    ),
    'track_member_growth': (
        'Member Growth',
        'Track when members join and leave the server to build a timeline of server growth.',
        False,
    ),
    'track_role_growth': (
        'Role Growth',
        'Track when roles are assigned to or removed from members over time.',
        False,
    ),
}


# ============================================================
# SETTINGS COG
# ============================================================

class Settings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pool = None
        self.initialized = False
        self.rate_limiter = get_rate_limiter()

        self.init_pools.start()

        self.privacy_cleanup_cron = aiocron.crontab(
            '*/5 * * * *', func=self.process_pending_privacy_deletions, tz=ZoneInfo('UTC'))

    @tasks.loop(count=1)
    async def init_pools(self):
        """Initialize database connection like DatabaseStats does."""
        for attempt in range(5):
            db_stats_cog = self.bot.get_cog("DatabaseStats")
            if db_stats_cog and hasattr(db_stats_cog, 'pool') and db_stats_cog.pool:
                self.pool = db_stats_cog.pool
                await self.initialize_settings_table()
                return
            await asyncio.sleep(2)

        print("⚠️ Settings: DatabaseStats cog pool not available after waiting")

    async def initialize_settings_table(self):
        """Initialize the settings table."""
        if not self.pool:
            print("❌ Settings: No database pool available")
            self.initialized = False
            return

        try:
            async with self.pool.acquire() as conn:
                # Create settings table (matches initialize_database schema)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS settings (
                        guild_id BIGINT PRIMARY KEY,
                        prefix TEXT DEFAULT 's!',
                        timezone TEXT DEFAULT 'UTC',
                        voice_states TEXT[] DEFAULT '{"self_mute", "self_deafen", "streaming", "video"}',
                        permission_level TEXT DEFAULT 'Default',
                        bot_filter BOOLEAN DEFAULT TRUE,
                        dashboard_access_level TEXT DEFAULT 'Member',
                        min_account_age_days INT DEFAULT 3,
                        default_time_mode TEXT DEFAULT 'days_back'
                            CHECK (default_time_mode IN ('all_time', 'days_back', 'date_range', 'rolling_window')),
                        default_days_back INT DEFAULT 14,
                        default_from_date TIMESTAMPTZ DEFAULT NULL,
                        default_to_date TIMESTAMPTZ DEFAULT NULL,
                        default_rolling_type TEXT DEFAULT NULL,
                        default_rolling_value INT DEFAULT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        track_messages BOOLEAN DEFAULT TRUE,
                        track_voice BOOLEAN DEFAULT TRUE,
                        track_emojis BOOLEAN DEFAULT FALSE,
                        track_invites BOOLEAN DEFAULT TRUE,
                        track_status_activity BOOLEAN DEFAULT FALSE,
                        track_mentions BOOLEAN DEFAULT FALSE,
                        track_member_growth BOOLEAN DEFAULT FALSE,
                        track_role_growth BOOLEAN DEFAULT FALSE
                    )
                """)

                # ALTER TABLE — add all columns that may be missing on existing installations
                settings_alter_queries = [
                    "ALTER TABLE settings ADD COLUMN IF NOT EXISTS default_time_mode TEXT DEFAULT 'days_back'",
                    "ALTER TABLE settings ADD COLUMN IF NOT EXISTS default_days_back INT DEFAULT 14",
                    "ALTER TABLE settings ADD COLUMN IF NOT EXISTS default_from_date TIMESTAMPTZ DEFAULT NULL",
                    "ALTER TABLE settings ADD COLUMN IF NOT EXISTS default_to_date TIMESTAMPTZ DEFAULT NULL",
                    "ALTER TABLE settings ADD COLUMN IF NOT EXISTS default_rolling_type TEXT DEFAULT NULL",
                    "ALTER TABLE settings ADD COLUMN IF NOT EXISTS default_rolling_value INT DEFAULT NULL",
                    "ALTER TABLE settings ADD COLUMN IF NOT EXISTS track_messages BOOLEAN DEFAULT TRUE",
                    "ALTER TABLE settings ADD COLUMN IF NOT EXISTS track_voice BOOLEAN DEFAULT TRUE",
                    "ALTER TABLE settings ADD COLUMN IF NOT EXISTS track_emojis BOOLEAN DEFAULT FALSE",
                    "ALTER TABLE settings ADD COLUMN IF NOT EXISTS track_invites BOOLEAN DEFAULT TRUE",
                    "ALTER TABLE settings ADD COLUMN IF NOT EXISTS track_status_activity BOOLEAN DEFAULT FALSE",
                    "ALTER TABLE settings ADD COLUMN IF NOT EXISTS track_mentions BOOLEAN DEFAULT FALSE",
                    "ALTER TABLE settings ADD COLUMN IF NOT EXISTS track_member_growth BOOLEAN DEFAULT FALSE",
                    "ALTER TABLE settings ADD COLUMN IF NOT EXISTS track_role_growth BOOLEAN DEFAULT FALSE",
                ]
                for query in settings_alter_queries:
                    try:
                        await conn.execute(query)
                    except Exception:
                        pass  # Column already exists

                # Add CHECK constraint safely if it doesn't exist yet
                try:
                    await conn.execute("""
                        DO $$
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1 FROM information_schema.check_constraints
                                WHERE constraint_name = 'valid_time_mode'
                            ) THEN
                                ALTER TABLE settings
                                ADD CONSTRAINT valid_time_mode
                                CHECK (default_time_mode IN (
                                    'all_time', 'days_back', 'date_range', 'rolling_window'
                                ));
                            END IF;
                        END
                        $$;
                    """)
                except Exception:
                    pass

                # Create user settings table
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS user_settings (
                        user_id BIGINT,
                        guild_id BIGINT,
                        privacy_enabled BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (user_id, guild_id)
                    )
                """)

                # Add privacy_pending_delete column if it doesn't exist
                try:
                    await conn.execute("""
                        ALTER TABLE user_settings
                        ADD COLUMN IF NOT EXISTS privacy_pending_delete BOOLEAN DEFAULT FALSE
                    """)
                    print(
                        "✅ Added privacy_pending_delete column to user_settings table")
                except Exception as e:
                    column_exists = await conn.fetchval("""
                        SELECT EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_name = 'user_settings'
                            AND column_name = 'privacy_pending_delete'
                        )
                    """)
                    if not column_exists:
                        await conn.execute("""
                            ALTER TABLE user_settings
                            ADD COLUMN privacy_pending_delete BOOLEAN DEFAULT FALSE
                        """)
                        print(
                            "✅ Added privacy_pending_delete column to user_settings table")

                # Create pending deletions table
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS privacy_pending_deletions (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        guild_id BIGINT NOT NULL,
                        requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        processed BOOLEAN DEFAULT FALSE,
                        processed_at TIMESTAMP,
                        UNIQUE(user_id, guild_id)
                    )
                """)

                print("✅ Settings Tables verified/created")
                self.initialized = True
                print("✅ Settings cog fully initialized")

        except Exception as e:
            print(f"❌ Settings: Error initializing table: {e}")
            import traceback
            traceback.print_exc()
            self.initialized = False

    async def get_guild_settings(self, guild_id: int):
        """Get settings for a guild."""
        if not self.pool or not self.initialized:
            return await self.get_default_settings(guild_id)

        try:
            async with self.pool.acquire() as conn:
                settings = await conn.fetchrow(
                    "SELECT * FROM settings WHERE guild_id = $1",
                    guild_id
                )
                if not settings:
                    return await self.create_default_settings(guild_id)
                return dict(settings)
        except Exception as e:
            print(f"❌ Settings: Error getting settings: {e}")
            return await self.get_default_settings(guild_id)

    async def get_default_settings(self, guild_id: int):
        """Get default settings structure (fallback when DB is unavailable)."""
        return {
            'guild_id': guild_id,
            'prefix': 's!',
            'timezone': 'UTC',
            'voice_states': ["self_mute", "self_deafen", "streaming", "video"],
            'permission_level': 'Default',
            'bot_filter': False,
            'dashboard_access_level': 'Member',
            'min_account_age_days': 3,
            'created_at': None,
            'default_time_mode': 'days_back',
            'default_days_back': 14,
            'default_from_date': None,
            'default_to_date': None,
            'default_rolling_type': None,
            'default_rolling_value': None,
            'track_messages': True,
            'track_voice': True,
            'track_emojis': False,
            'track_invites': True,
            'track_status_activity': False,
            'track_mentions': False,
            'track_member_growth': False,
            'track_role_growth': False,
        }

    async def create_default_settings(self, guild_id: int):
        """Create default settings for a guild."""
        if not self.pool or not self.initialized:
            return await self.get_default_settings(guild_id)

        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO settings (guild_id, voice_states, min_account_age_days)
                    VALUES ($1, ARRAY['self_mute', 'self_deafen', 'streaming', 'video'], 3)
                    ON CONFLICT (guild_id) DO NOTHING
                """, guild_id)

                settings = await conn.fetchrow(
                    "SELECT * FROM settings WHERE guild_id = $1",
                    guild_id
                )
                return dict(settings) if settings else await self.get_default_settings(guild_id)
        except Exception as e:
            print(f"❌ Settings: Error creating settings: {e}")
            return await self.get_default_settings(guild_id)

    async def update_setting(self, guild_id: int, setting: str, value):
        """Update a specific setting for a guild."""
        if not self.pool or not self.initialized:
            print(f"❌ Settings: No connection to update {setting}")
            return False

        try:
            async with self.pool.acquire() as conn:
                await self.create_default_settings(guild_id)
                await conn.execute(
                    f"UPDATE settings SET {setting} = $1 WHERE guild_id = $2",
                    value, guild_id
                )
                # Invalidate the stat toggle cache in DatabaseStats cog if relevant
                if setting.startswith('track_'):
                    db_cog = self.bot.get_cog('DatabaseStats')
                    if db_cog and hasattr(db_cog, '_invalidate_stat_toggle_cache'):
                        db_cog._invalidate_stat_toggle_cache(guild_id)
                return True
        except Exception as e:
            print(f"❌ Settings: Error updating {setting}: {e}")
            return False

    async def update_stat_toggles(self, guild_id: int, toggles: dict) -> bool:
        """Update multiple stat toggle columns at once."""
        if not self.pool or not self.initialized:
            return False

        # Only allow known toggle keys
        allowed = set(STAT_TOGGLE_META.keys())
        safe = {k: v for k, v in toggles.items() if k in allowed}
        if not safe:
            return False

        set_clauses = ', '.join(f"{k} = ${i+2}" for i, k in enumerate(safe))
        values = list(safe.values())

        try:
            async with self.pool.acquire() as conn:
                await self.create_default_settings(guild_id)
                await conn.execute(
                    f"UPDATE settings SET {set_clauses} WHERE guild_id = $1",
                    guild_id, *values
                )
                db_cog = self.bot.get_cog('DatabaseStats')
                if db_cog and hasattr(db_cog, '_invalidate_stat_toggle_cache'):
                    db_cog._invalidate_stat_toggle_cache(guild_id)
                return True
        except Exception as e:
            print(f"❌ Settings: Error updating stat toggles: {e}")
            return False

    async def update_time_period_setting(
        self,
        guild_id: int,
        mode: str,
        days_back: Optional[int] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        rolling_type: Optional[str] = None,
        rolling_value: Optional[int] = None,
    ) -> bool:
        """Update all time period columns for a guild in one query."""
        if not self.pool or not self.initialized:
            print("❌ Settings: No connection to update time period")
            return False

        try:
            async with self.pool.acquire() as conn:
                await self.create_default_settings(guild_id)
                await conn.execute("""
                    UPDATE settings SET
                        default_time_mode   = $1,
                        default_days_back   = $2,
                        default_from_date   = $3,
                        default_to_date     = $4,
                        default_rolling_type  = $5,
                        default_rolling_value = $6
                    WHERE guild_id = $7
                """, mode, days_back, from_date, to_date, rolling_type, rolling_value, guild_id)
                return True
        except Exception as e:
            print(f"❌ Settings: Error updating time period: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def get_user_settings(self, user_id: int, guild_id: int):
        """Get user settings for a specific guild."""
        if not self.pool or not self.initialized:
            return {'privacy_enabled': False}

        try:
            async with self.pool.acquire() as conn:
                settings = await conn.fetchrow(
                    "SELECT * FROM user_settings WHERE user_id = $1 AND guild_id = $2",
                    user_id, guild_id
                )
                if not settings:
                    return {'privacy_enabled': False}
                return dict(settings)
        except Exception as e:
            print(f"❌ Settings: Error getting user settings: {e}")
            return {'privacy_enabled': False}

    async def update_user_setting(self, user_id: int, guild_id: int, setting: str, value):
        """Update a specific user setting."""
        if not self.pool or not self.initialized:
            print(f"❌ Settings: No connection to update user {setting}")
            return False

        try:
            async with self.pool.acquire() as conn:
                current = await conn.fetchrow(
                    "SELECT privacy_enabled FROM user_settings WHERE user_id = $1 AND guild_id = $2",
                    user_id, guild_id
                )
                current_enabled = current['privacy_enabled'] if current else False

                if value is True and not current_enabled:
                    await conn.execute("""
                        INSERT INTO user_settings (user_id, guild_id, privacy_enabled, privacy_pending_delete, updated_at)
                        VALUES ($1, $2, $3, TRUE, CURRENT_TIMESTAMP)
                        ON CONFLICT (user_id, guild_id)
                        DO UPDATE SET
                            privacy_enabled = $3,
                            privacy_pending_delete = TRUE,
                            updated_at = CURRENT_TIMESTAMP
                    """, user_id, guild_id, value)

                    await conn.execute("""
                        INSERT INTO privacy_pending_deletions (user_id, guild_id, requested_at)
                        VALUES ($1, $2, CURRENT_TIMESTAMP)
                        ON CONFLICT (user_id, guild_id) DO UPDATE
                        SET requested_at = CURRENT_TIMESTAMP, processed = FALSE, processed_at = NULL
                    """, user_id, guild_id)

                    print(
                        f"🔐 Privacy mode enabled for user {user_id} in guild {guild_id} — queued for deletion")
                else:
                    await conn.execute("""
                        INSERT INTO user_settings (user_id, guild_id, privacy_enabled, updated_at)
                        VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
                        ON CONFLICT (user_id, guild_id)
                        DO UPDATE SET privacy_enabled = $3, updated_at = CURRENT_TIMESTAMP
                    """, user_id, guild_id, value)

                    if value is False:
                        print(
                            f"🔓 Privacy mode disabled for user {user_id} in guild {guild_id}")

                return True
        except Exception as e:
            print(f"❌ Settings: Error updating user {setting}: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def process_pending_privacy_deletions(self):
        """Cron job that runs every 5 minutes to process pending privacy deletions."""
        if not self.pool or not self.initialized:
            return

        print(f"\n{'='*60}")
        print(
            f"🕒 Processing pending privacy deletions at {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"{'='*60}")

        try:
            async with self.pool.acquire() as conn:
                pending = await conn.fetch("""
                    SELECT user_id, guild_id, requested_at
                    FROM privacy_pending_deletions
                    WHERE processed = FALSE
                    ORDER BY requested_at ASC
                """)

                if not pending:
                    print("✅ No pending privacy deletions")
                    return

                print(f"📊 Found {len(pending)} pending deletion requests")

                reset_cog = self.bot.get_cog("ResetStats")
                if not reset_cog or not reset_cog.db_manager:
                    print(
                        "❌ Cannot delete stats: ResetStats cog or db_manager not available")
                    return

                deleted_count = 0
                failed_count = 0

                for record in pending:
                    user_id = record['user_id']
                    guild_id = record['guild_id']

                    try:
                        print(
                            f"  🗑️ Deleting stats for user {user_id} in guild {guild_id}")

                        result = await reset_cog.db_manager.delete_user_all(
                            guild_id=guild_id,
                            user_id=user_id,
                            channel_id=None,
                            category_id=None
                        )

                        await conn.execute("""
                            UPDATE privacy_pending_deletions
                            SET processed = TRUE, processed_at = CURRENT_TIMESTAMP
                            WHERE user_id = $1 AND guild_id = $2
                        """, user_id, guild_id)

                        await conn.execute("""
                            UPDATE user_settings
                            SET privacy_pending_delete = FALSE
                            WHERE user_id = $1 AND guild_id = $2
                        """, user_id, guild_id)

                        deleted_count += 1

                        if isinstance(result, dict):
                            total_deleted = 0
                            for table, count in result.items():
                                count_str = str(count).split()[0]
                                if count_str.isdigit():
                                    total_deleted += int(count_str)
                            print(f"    ✅ Deleted {total_deleted} records")
                        else:
                            print(f"    ✅ Deletion complete")

                    except Exception as e:
                        failed_count += 1
                        print(
                            f"    ❌ Failed to delete stats for user {user_id} in guild {guild_id}: {e}")
                        import traceback
                        traceback.print_exc()

                print(
                    f"\n✅ Privacy deletion complete: {deleted_count} succeeded, {failed_count} failed")
                print(f"{'='*60}\n")

        except Exception as e:
            print(f"❌ Error processing pending privacy deletions: {e}")
            import traceback
            traceback.print_exc()

    async def check_settings_permission(self, interaction: discord.Interaction) -> bool:
        """Check if user has permission to use settings command based on server permission level."""
        if interaction.user.guild_permissions.administrator:
            return True

        settings = await self.get_guild_settings(interaction.guild_id)
        permission_level = settings.get('permission_level', 'Default')

        if permission_level == 'All':
            return True
        elif permission_level == 'Admin':
            return interaction.user.guild_permissions.administrator
        elif permission_level == 'Moderator':
            return interaction.user.guild_permissions.manage_guild
        elif permission_level == 'Default':
            return interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild
        elif permission_level == 'User Restriction':
            return interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild

        return interaction.user.guild_permissions.administrator

    # =========================================================
    # INTERNAL FUNCTION FOR BOTH COMMANDS
    # =========================================================
    @rate_limited(RateLimitType.MESSAGE, timeout=15.0)
    async def _handle_settings_command(self, ctx_or_interaction, is_interaction=False):
        """Internal function to handle settings for both command types."""
        if not self.initialized:
            if is_interaction:
                await ctx_or_interaction.response.send_message(
                    "Settings system is initializing, please try again in a moment.", ephemeral=True)
            else:
                await ctx_or_interaction.send(
                    "Settings system is initializing, please try again in a moment.", delete_after=5)
            return

        if is_interaction:
            user = ctx_or_interaction.user
            guild_id = ctx_or_interaction.guild_id
        else:
            try:
                await ctx_or_interaction.message.delete()
            except Exception:
                pass
            user = ctx_or_interaction.author
            guild_id = ctx_or_interaction.guild.id

        if not await self.check_settings_permission(ctx_or_interaction if is_interaction else type(
            'obj', (object,), {
                'user': user,
                'guild_id': guild_id,
                'user.guild_permissions': user.guild_permissions
            }
        )):
            settings = await self.get_guild_settings(guild_id)
            permission_level = settings.get('permission_level', 'Default')

            if permission_level == 'Admin':
                required_permission = "Administrator"
            elif permission_level == 'Moderator':
                required_permission = "Manage Server"
            elif permission_level in ['Default', 'User Restriction']:
                required_permission = "Administrator or Manage Server"
            else:
                required_permission = "Administrator"

            embed = discord.Embed(
                title="❌ Permission Denied",
                description=f"Sorry! You need the `{required_permission}` permission to access this command.",
                color=discord.Color.red()
            )

            if is_interaction:
                await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await ctx_or_interaction.send(embed=embed, delete_after=10)
            return

        await self.create_default_settings(guild_id)

        embed = discord.Embed(
            title="📊 Stats Settings Menu",
            description="These are all the general settings in the bot.",
            color=discord.Color.purple()
        )

        settings_list = [
            ("`Prefix`", "Change the bot's prefix."),
            ("`Timezone`", "Change the timezone of the server."),
            ("`Voice States`", "Filter out different types of voice states."),
            ("`Bot Filter`", "Filter out bots from being tracked in statistics."),
            ("`Command Permission Access Level`",
             "Choose from the 5 levels of permission access."),
            ("`Suspicious Invite Tracking`",
             "Set minimum account age to detect suspicious invites."),
            ("`Stat Toggles`",
             "Enable or disable specific stat types being tracked on this server."),
            ("`Time Period`", "Change the default time period that commands on the bot use."),
        ]

        for setting_name, description in settings_list:
            embed.add_field(name=setting_name, value=description, inline=False)

        embed.add_field(
            name="‎",
            value="**Choose a setting from the dropdown menu below**",
            inline=False
        )

        view = MainSettingsView(self, guild_id)

        if is_interaction:
            await ctx_or_interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            view.message = await ctx_or_interaction.original_response()
        else:
            msg = await ctx_or_interaction.send(embed=embed, view=view, delete_after=300)
            view.message = msg

    # =========================================================
    # INTERNAL FUNCTION FOR USER SETTINGS COMMAND
    # =========================================================
    @rate_limited(RateLimitType.MESSAGE, timeout=15.0)
    async def _handle_user_settings_command(self, ctx_or_interaction, is_interaction=False):
        """Internal function to handle user settings for both command types."""
        if not self.initialized:
            if is_interaction:
                await ctx_or_interaction.response.send_message(
                    "Settings system is initializing, please try again in a moment.", ephemeral=True)
            else:
                await ctx_or_interaction.send(
                    "Settings system is initializing, please try again in a moment.", delete_after=5)
            return

        if is_interaction:
            user = ctx_or_interaction.user
            guild_id = ctx_or_interaction.guild_id
            user_id = user.id
        else:
            try:
                await ctx_or_interaction.message.delete()
            except Exception:
                pass
            user = ctx_or_interaction.author
            guild_id = ctx_or_interaction.guild.id
            user_id = user.id

        embed = discord.Embed(
            title="⚙️ User Settings",
            description="These are all the personal user settings on the bot.",
            color=discord.Color.purple()
        )

        settings_list = [
            ("`Privacy Mode`", "Control whether the bot tracks your data on this server.")
        ]

        for setting_name, description in settings_list:
            embed.add_field(name=setting_name, value=description, inline=False)

        embed.add_field(
            name="‎",
            value="**Choose a setting from the dropdown menu below**",
            inline=False
        )

        view = UserSettingsView(self, guild_id, user_id)

        if is_interaction:
            await ctx_or_interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            view.message = await ctx_or_interaction.original_response()
        else:
            msg = await ctx_or_interaction.send(embed=embed, view=view, delete_after=300)
            view.message = msg

    # =========================================================
    # PREFIX COMMAND GROUP
    # =========================================================
    @commands.group(name="settings", invoke_without_command=True)
    async def settings_group_prefix(self, ctx: commands.Context):
        """Configure bot settings for your server via prefix command."""
        await self._handle_settings_command(ctx, is_interaction=False)

    @settings_group_prefix.command(name="server")
    async def settings_server_prefix(self, ctx: commands.Context):
        """Configure server settings."""
        await self._handle_settings_command(ctx, is_interaction=False)

    @settings_group_prefix.command(name="user")
    async def settings_user_prefix(self, ctx: commands.Context):
        """Configure your personal user settings."""
        await self._handle_user_settings_command(ctx, is_interaction=False)

    @commands.command(name="set")
    async def settings_shortcut(self, ctx: commands.Context):
        """Shortcut command for server settings."""
        await self._handle_settings_command(ctx, is_interaction=False)

    @commands.command(name="setu")
    async def user_settings_shortcut(self, ctx: commands.Context):
        """Shortcut command for user settings."""
        await self._handle_user_settings_command(ctx, is_interaction=False)

    # =========================================================
    # SLASH COMMAND GROUP
    # =========================================================
    settings_group = app_commands.Group(
        name="settings",
        description="Configure bot settings"
    )

    @settings_group.command(name="server", description="Configure bot settings for your server")
    async def settings_server_command(self, interaction: discord.Interaction):
        """Server settings command."""
        await self._handle_settings_command(interaction, is_interaction=True)

    @settings_group.command(name="user", description="Configure your personal user settings.")
    async def settings_user_command(self, interaction: discord.Interaction):
        """User settings command."""
        await self._handle_user_settings_command(interaction, is_interaction=True)

    @settings_server_command.error
    async def settings_server_command_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingPermissions):
            embed = discord.Embed(
                title="❌ Permission Denied",
                description="Sorry! You need the `Administrator` permission to access this command.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            embed = discord.Embed(
                title="❌ Error",
                description=f"An error occurred: {str(error)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @settings_user_command.error
    async def settings_user_command_error(self, interaction: discord.Interaction, error):
        embed = discord.Embed(
            title="❌ Error",
            description=f"An error occurred: {str(error)}",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def cog_unload(self):
        pass


# ============================================================
# MAIN SETTINGS VIEW
# ============================================================

class MainSettingsView(discord.ui.View):
    def __init__(self, cog, guild_id):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.bot = cog.bot
        self.message = None

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except Exception:
            pass

    async def check_permission(self, interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        settings = await self.cog.get_guild_settings(self.guild_id)
        permission_level = settings.get('permission_level', 'Default')
        if permission_level == 'All':
            return True
        elif permission_level == 'Admin':
            return interaction.user.guild_permissions.administrator
        elif permission_level == 'Moderator':
            return interaction.user.guild_permissions.manage_guild
        elif permission_level == 'Default':
            return interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild
        elif permission_level == 'User Restriction':
            return interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild
        return False

    async def send_permission_error(self, interaction: discord.Interaction):
        settings = await self.cog.get_guild_settings(self.guild_id)
        permission_level = settings.get('permission_level', 'Default')
        if permission_level == 'Admin':
            required_permission = "Administrator"
        elif permission_level == 'Moderator':
            required_permission = "Manage Server"
        elif permission_level in ['Default', 'User Restriction']:
            required_permission = "Administrator or Manage Server"
        else:
            required_permission = "Administrator"
        embed = discord.Embed(
            title="❌ Permission Denied",
            description=f"Sorry! You need the `{required_permission}` permission to access this command.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.select(
        placeholder="Select a setting to configure...",
        options=[
            discord.SelectOption(label="Prefix", value="prefix",
                                 description="Change the bot's prefix"),
            discord.SelectOption(label="Timezone", value="timezone",
                                 description="Change server timezone"),
            discord.SelectOption(label="Voice States", value="voice_states",
                                 description="Configure voice state tracking"),
            discord.SelectOption(label="Bot Filter", value="bot_filter",
                                 description="Filter bots from statistics"),
            discord.SelectOption(label="Command Permission Access Level", value="permissions",
                                 description="Configure command permissions"),
            discord.SelectOption(label="Suspicious Invite Tracking", value="suspicious_invites",
                                 description="Configure suspicious invite detection"),
            discord.SelectOption(label="Stat Toggles", value="stat_toggles",
                                 description="Enable or disable specific stat types"),
            discord.SelectOption(label="Time Period", value="time_period",
                                 description="Change the default time period that commands use"),
        ]
    )
    async def settings_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return

        await interaction.response.defer()
        setting_type = select.values[0]

        if setting_type == "prefix":
            await self.show_prefix_menu(interaction)
        elif setting_type == "timezone":
            await self.show_timezone_menu(interaction)
        elif setting_type == "voice_states":
            await self.show_voice_states_menu(interaction)
        elif setting_type == "bot_filter":
            await self.show_bot_filter_menu(interaction)
        elif setting_type == "permissions":
            await self.show_permissions_menu(interaction)
        elif setting_type == "suspicious_invites":
            await self.show_suspicious_invites_menu(interaction)
        elif setting_type == "stat_toggles":
            await self.show_stat_toggles_menu(interaction)
        elif setting_type == "time_period":
            await self.show_time_period_menu(interaction)

    async def show_main_menu(self, interaction: discord.Interaction):
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return

        embed = discord.Embed(
            title="📊 Stats Settings Menu",
            description="These are all the general settings in the bot.",
            color=discord.Color.purple()
        )
        settings_list = [
            ("`Prefix`", "Change the bot's prefix."),
            ("`Timezone`", "Change the timezone of the server."),
            ("`Voice States`", "Filter out different types of voice states."),
            ("`Bot Filter`", "Filter out bots from being tracked in statistics."),
            ("`Command Permission Access Level`",
             "Choose from the 5 levels of permission access."),
            ("`Suspicious Invite Tracking`",
             "Set minimum account age to detect suspicious invites."),
            ("`Stat Toggles`",
             "Enable or disable specific stat types being tracked on this server."),
            ("`Time Period`", "Change the default time period that commands on the bot use."),
        ]
        for setting_name, description in settings_list:
            embed.add_field(name=setting_name, value=description, inline=False)
        embed.add_field(
            name="‎", value="**Choose a setting from the dropdown menu below**", inline=False)

        view = MainSettingsView(self.cog, self.guild_id)
        await interaction.edit_original_response(embed=embed, view=view)

    async def show_prefix_menu(self, interaction: discord.Interaction):
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return
        settings = await self.cog.get_guild_settings(self.guild_id)
        current_prefix = settings.get('prefix', 's!')
        embed = discord.Embed(
            title="⚙️ Prefix Menu",
            description=(
                f"**This server's current prefix is:** `{current_prefix}`\n\n"
                "You can change the prefix through the change prefix button below. "
                "The max limit for a prefix is 10 characters."
            ),
            color=discord.Color.purple()
        )
        view = PrefixView(self.cog, self.guild_id)
        await interaction.edit_original_response(embed=embed, view=view)

    async def show_timezone_menu(self, interaction: discord.Interaction):
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return
        settings = await self.cog.get_guild_settings(self.guild_id)
        current_timezone = settings.get('timezone', 'UTC')
        embed = discord.Embed(
            title="🌍 Timezone Menu",
            description=(
                f"**This server's current timezone is:** `{current_timezone}`\n\n"
                "You can change the timezone of the server by choosing from the options in the dropdown menu below."
            ),
            color=discord.Color.purple()
        )
        view = TimezoneView(self.cog, self.guild_id)
        await interaction.edit_original_response(embed=embed, view=view)

    async def show_voice_states_menu(self, interaction: discord.Interaction):
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return
        settings = await self.cog.get_guild_settings(self.guild_id)
        current_states = settings.get('voice_states', [])
        embed = discord.Embed(
            title="🔊 Voice States Menu",
            description=(
                "**Voice Activity tracking on the Stats bot is split into 8 different states:**\n\n"
                "`Afk` - A user is in the afk voice channel.\n"
                "`Self Mute` - A user muted themself.\n"
                "`Self deafen` - A user deafened themself.\n"
                "`Server Mute` - A user has been muted forcibly through moderation.\n"
                "`Server deafen` - A user has been deafened forcibly through moderation.\n"
                "`Streaming` - A user is streaming.\n"
                "`Video` - A user has their video open.\n"
                "`Suppressed` - Audience members in a stage channel that aren't allowed to speak.\n\n"
                f"**The server's current Voice States that are being tracked are:**\n"
                f"{', '.join(f'`{state}`' for state in current_states)
                   if current_states else '`None`'}\n\n"
                "Choose the Voice States that you wish to be tracked in the server's voice activity "
                "through the dropdown menu below."
            ),
            color=discord.Color.purple()
        )
        view = VoiceStatesView(self.cog, self.guild_id, current_states)
        await interaction.edit_original_response(embed=embed, view=view)

    async def show_bot_filter_menu(self, interaction: discord.Interaction):
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return
        settings = await self.cog.get_guild_settings(self.guild_id)
        bot_filter = settings.get('bot_filter', False)
        status = "filtered out from" if bot_filter else "included in"
        button_text = "Include Bots" if bot_filter else "Filter Bots"
        embed = discord.Embed(
            title="🤖 Bot Filter Menu",
            description=(
                f"**Bots are currently {status} statistics.**\n\n"
                f"You can {'include bots in' if bot_filter else 'filter out bots from'} statistics "
                f"through the **\"{button_text}\"** button below."
            ),
            color=discord.Color.purple()
        )
        view = BotFilterView(self.cog, self.guild_id, bot_filter)
        await interaction.edit_original_response(embed=embed, view=view)

    async def show_permissions_menu(self, interaction: discord.Interaction):
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return
        settings = await self.cog.get_guild_settings(self.guild_id)
        current_level = settings.get('permission_level', 'Default')
        embed = discord.Embed(
            title="🔐 Command Permission Access Levels Menu",
            description=(
                f"**This server's permission level is currently set to:** `{current_level}`\n\n"
                "**Permission Levels:**\n\n"
                "`All` - All members regardless of their permissions are allowed to use any command on the bot "
                "including sensitive commands like reset and blacklist.\n\n"
                "`Default` - The default access level that restricts or enables specific commands for users with "
                "specific permissions. All commands on the bot are usable by normal members except for blacklist "
                "and settings being accessible via manage server, and reset commands being accessible via "
                "administrator permissions.\n\n"
                "`User Restriction` - Mostly the same as Default except users can only use commands that have "
                "the user scope on their own account only.\n\n"
                "`Admin` - Only users with the administrator permission can use any commands on the bot.\n\n"
                "`Moderator` - Only users with the Manage Server permission can use any commands on the bot.\n\n"
                "You can change the permission level through the dropdown menu below."
            ),
            color=discord.Color.purple()
        )
        view = PermissionsView(self.cog, self.guild_id)
        await interaction.edit_original_response(embed=embed, view=view)

    async def show_suspicious_invites_menu(self, interaction: discord.Interaction):
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return
        settings = await self.cog.get_guild_settings(self.guild_id)
        current_days = settings.get('min_account_age_days', 3)
        embed = discord.Embed(
            title="⚠️ Suspicious Invite Tracking Menu",
            description=(
                "**What are Suspicious Invites?**\n\n"
                "Suspicious invites are detected when **either** the person inviting **OR** the person joining "
                "has an account that is too new.\n\n"
                "This helps protect your server from:\n"
                "• Raids using newly created accounts\n"
                "• Bot accounts joining via compromised invites\n"
                "• Invite spam from fresh accounts\n\n"
                f"**Current Setting:** `{current_days} day(s)`\n\n"
                "If an account is younger than this many days, any invite they send or use will be marked as "
                "**suspicious**.\n\n"
                "Set to `0` to disable suspicious invite detection entirely.\n\n"
                "**Click the button below to change this value.**"
            ),
            color=discord.Color.purple()
        )
        view = SuspiciousInvitesView(self.cog, self.guild_id, current_days)
        await interaction.edit_original_response(embed=embed, view=view)

    async def show_stat_toggles_menu(self, interaction: discord.Interaction):
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return
        settings = await self.cog.get_guild_settings(self.guild_id)
        view = StatTogglesView(self.cog, self.guild_id, settings)
        await interaction.edit_original_response(embed=view.build_embed(), view=view)

    async def show_time_period_menu(self, interaction: discord.Interaction):
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return
        settings = await self.cog.get_guild_settings(self.guild_id)
        view = TimePeriodView(self.cog, self.guild_id, settings)
        await interaction.edit_original_response(embed=view.build_selection_embed(), view=view)


# ============================================================
# USER SETTINGS VIEW
# ============================================================

class UserSettingsView(discord.ui.View):
    def __init__(self, cog, guild_id, user_id):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        self.bot = cog.bot
        self.message = None

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except Exception:
            pass

    @discord.ui.select(
        placeholder="Select a setting to configure...",
        options=[
            discord.SelectOption(label="Privacy Mode", value="privacy",
                                 description="Control your data privacy settings for this server")
        ]
    )
    async def user_settings_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.user.id != self.user_id:
            embed = discord.Embed(
                title="❌ Permission Denied",
                description="You cannot change another user's privacy settings!",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer()
        setting_type = select.values[0]
        if setting_type == "privacy":
            await self.show_privacy_menu(interaction)

    async def show_main_menu(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            embed = discord.Embed(
                title="❌ Permission Denied",
                description="You cannot change another user's privacy settings!",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="🔒 User Privacy Settings",
            description="These are all the personal user settings on the bot.",
            color=discord.Color.purple()
        )
        settings_list = [
            ("`Privacy Mode`", "Control whether the bot tracks your data on this server.")
        ]
        for setting_name, description in settings_list:
            embed.add_field(name=setting_name, value=description, inline=False)
        embed.add_field(
            name="‎", value="**Choose a setting from the dropdown menu below**", inline=False)

        view = UserSettingsView(self.cog, self.guild_id, self.user_id)
        await interaction.edit_original_response(embed=embed, view=view)

    async def show_privacy_menu(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            embed = discord.Embed(
                title="❌ Permission Denied",
                description="You cannot change another user's privacy settings!",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        user_settings = await self.cog.get_user_settings(self.user_id, self.guild_id)
        privacy_enabled = user_settings.get('privacy_enabled', False)
        embed = discord.Embed(
            title="🔒 Privacy Mode Settings",
            description=(
                "**Your Privacy Matters to Us**\n\n"
                "We value your privacy and give you full control over your data. "
                "When Privacy Mode is enabled:\n\n"
                "• **All data** the bot has collected about you on this server will be **deleted**\n"
                "• You will be **excluded from any future tracking** on this server\n\n"
                f"**Current Status:** `{'ENABLED' if privacy_enabled else 'DISABLED'}`\n\n"
                "Use the button below to turn privacy mode on/off.\n\n"
                "*Note: This setting only applies to this specific server.*"
            ),
            color=discord.Color.green() if privacy_enabled else discord.Color.red()
        )
        view = PrivacyView(self.cog, self.guild_id,
                           self.user_id, privacy_enabled)
        await interaction.edit_original_response(embed=embed, view=view)


# ============================================================
# PRIVACY VIEW
# ============================================================

class PrivacyView(discord.ui.View):
    def __init__(self, cog, guild_id, user_id, privacy_enabled):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        self.bot = cog.bot
        self.privacy_enabled = privacy_enabled
        self.message = None

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except Exception:
            pass

    @discord.ui.button(label="Toggle Privacy Mode", style=discord.ButtonStyle.primary, emoji="🔒", row=0)
    async def toggle_privacy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            embed = discord.Embed(
                title="❌ Permission Denied",
                description="You cannot change another user's privacy settings!",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer()
        new_value = not self.privacy_enabled
        success = await self.cog.update_user_setting(self.user_id, self.guild_id, 'privacy_enabled', new_value)

        if success:
            if new_value:
                await interaction.followup.send(
                    "🔒 **Privacy Mode ENABLED**\n\n"
                    "• Your data will be deleted from this server\n"
                    "• The deletion will be processed within the next 5 minutes\n"
                    "• You will no longer be tracked on this server\n"
                    "• This change may take a few moments to process",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "🔓 **Privacy Mode DISABLED**\n\n"
                    "• You will now be tracked on this server again\n"
                    "• New data will be collected moving forward\n"
                    "*Note: Previously deleted data cannot be recovered*",
                    ephemeral=True
                )

            await asyncio.sleep(2)
            user_settings = await self.cog.get_user_settings(self.user_id, self.guild_id)
            privacy_enabled = user_settings.get('privacy_enabled', False)
            embed = discord.Embed(
                title="🔒 Privacy Mode Settings",
                description=(
                    "**Your Privacy Matters to Us**\n\n"
                    "We value your privacy and give you full control over your data. "
                    "When Privacy Mode is enabled:\n\n"
                    "• **All data** the bot has collected about you on this server will be **deleted**\n"
                    "• You will be **excluded from any future tracking** on this server\n\n"
                    f"**Current Status:** `{'ENABLED' if privacy_enabled else 'DISABLED'}`\n\n"
                    "Use the button below to turn privacy mode on/off.\n\n"
                    "*Note: This setting only applies to this specific server.*"
                ),
                color=discord.Color.green() if privacy_enabled else discord.Color.red()
            )
            view = PrivacyView(self.cog, self.guild_id,
                               self.user_id, privacy_enabled)
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.followup.send(
                "❌ Failed to update privacy settings. Please try again.", ephemeral=True)

    @discord.ui.button(label="↩ Back", style=discord.ButtonStyle.secondary, row=1)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            embed = discord.Embed(
                title="❌ Permission Denied",
                description="You cannot change another user's privacy settings!",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer()
        view = UserSettingsView(self.cog, self.guild_id, self.user_id)
        await view.show_main_menu(interaction)


# ============================================================
# PREFIX VIEW + MODAL
# ============================================================

class PrefixView(discord.ui.View):
    def __init__(self, cog, guild_id):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.bot = cog.bot
        self.message = None

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except Exception:
            pass

    async def check_permission(self, interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        settings = await self.cog.get_guild_settings(self.guild_id)
        permission_level = settings.get('permission_level', 'Default')
        if permission_level == 'All':
            return True
        elif permission_level == 'Admin':
            return interaction.user.guild_permissions.administrator
        elif permission_level == 'Moderator':
            return interaction.user.guild_permissions.manage_guild
        elif permission_level in ('Default', 'User Restriction'):
            return interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild
        return False

    async def send_permission_error(self, interaction: discord.Interaction):
        settings = await self.cog.get_guild_settings(self.guild_id)
        permission_level = settings.get('permission_level', 'Default')
        if permission_level == 'Admin':
            required_permission = "Administrator"
        elif permission_level == 'Moderator':
            required_permission = "Manage Server"
        elif permission_level in ['Default', 'User Restriction']:
            required_permission = "Administrator or Manage Server"
        else:
            required_permission = "Administrator"
        embed = discord.Embed(
            title="❌ Permission Denied",
            description=f"Sorry! You need the `{required_permission}` permission to access this command.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Change Prefix", style=discord.ButtonStyle.primary, emoji="⚙️")
    async def change_prefix_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return
        modal = PrefixModal(self.cog, self.guild_id, self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="↩ Back", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return
        await interaction.response.defer()
        view = MainSettingsView(self.cog, self.guild_id)
        await view.show_main_menu(interaction)


class PrefixModal(discord.ui.Modal, title="Change Prefix"):
    def __init__(self, cog, guild_id, parent_view):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.parent_view = parent_view
        self.prefix_input = discord.ui.TextInput(
            label="New Prefix",
            placeholder="Enter new prefix (max 10 characters)",
            max_length=10,
            required=True
        )
        self.add_item(self.prefix_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not await self.parent_view.check_permission(interaction):
            await self.parent_view.send_permission_error(interaction)
            return
        await interaction.response.defer()
        new_prefix = self.prefix_input.value.strip()
        success = await self.cog.update_setting(self.guild_id, 'prefix', new_prefix)
        if success:
            await interaction.followup.send(f"✅ Prefix has been changed to: `{new_prefix}`", ephemeral=True)
            await asyncio.sleep(2)
            settings = await self.cog.get_guild_settings(self.guild_id)
            current_prefix = settings.get('prefix', 's!')
            embed = discord.Embed(
                title="⚙️ Prefix Menu",
                description=(
                    f"**This server's current prefix is:** `{current_prefix}`\n\n"
                    "You can change the prefix through the change prefix button below. "
                    "The max limit for a prefix is 10 characters."
                ),
                color=discord.Color.purple()
            )
            view = PrefixView(self.cog, self.guild_id)
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.followup.send("❌ Failed to update prefix. Please try again.", ephemeral=True)


# ============================================================
# TIMEZONE VIEW
# ============================================================

class TimezoneView(discord.ui.View):
    def __init__(self, cog, guild_id):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.bot = cog.bot
        self.selected_timezone = None
        self.message = None

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except Exception:
            pass

    async def check_permission(self, interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        settings = await self.cog.get_guild_settings(self.guild_id)
        permission_level = settings.get('permission_level', 'Default')
        if permission_level == 'All':
            return True
        elif permission_level == 'Admin':
            return interaction.user.guild_permissions.administrator
        elif permission_level == 'Moderator':
            return interaction.user.guild_permissions.manage_guild
        elif permission_level in ('Default', 'User Restriction'):
            return interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild
        return False

    async def send_permission_error(self, interaction: discord.Interaction):
        settings = await self.cog.get_guild_settings(self.guild_id)
        permission_level = settings.get('permission_level', 'Default')
        if permission_level == 'Admin':
            required_permission = "Administrator"
        elif permission_level == 'Moderator':
            required_permission = "Manage Server"
        elif permission_level in ['Default', 'User Restriction']:
            required_permission = "Administrator or Manage Server"
        else:
            required_permission = "Administrator"
        embed = discord.Embed(
            title="❌ Permission Denied",
            description=f"Sorry! You need the `{required_permission}` permission to access this command.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.select(
        placeholder="Select a timezone...",
        options=[
            discord.SelectOption(
                label="UTC (GMT+0)", value="UTC", description="Coordinated Universal Time"),
            discord.SelectOption(
                label="EST (GMT-5)", value="EST", description="Eastern Standard Time"),
            discord.SelectOption(
                label="PST (GMT-8)", value="PST", description="Pacific Standard Time"),
            discord.SelectOption(
                label="CST (GMT-6)", value="CST", description="Central Standard Time"),
            discord.SelectOption(
                label="MST (GMT-7)", value="MST", description="Mountain Standard Time"),
            discord.SelectOption(
                label="GMT (GMT+0)", value="GMT", description="Greenwich Mean Time"),
            discord.SelectOption(
                label="CET (GMT+1)", value="CET", description="Central European Time"),
            discord.SelectOption(
                label="EET (GMT+2)", value="EET", description="Eastern European Time"),
            discord.SelectOption(
                label="IST (GMT+5:30)", value="IST", description="Indian Standard Time"),
            discord.SelectOption(
                label="JST (GMT+9)", value="JST", description="Japan Standard Time"),
            discord.SelectOption(
                label="AEST (GMT+10)", value="AEST", description="Australian Eastern Time"),
            discord.SelectOption(
                label="NZST (GMT+12)", value="NZST", description="New Zealand Standard Time"),
        ]
    )
    async def timezone_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return
        await interaction.response.defer()
        self.selected_timezone = select.values[0]
        self.children[1].disabled = False
        select.placeholder = f"Selected: {self.selected_timezone}"
        await interaction.edit_original_response(view=self)

    @discord.ui.button(label="Apply Changes", style=discord.ButtonStyle.success, disabled=True, row=1)
    async def apply_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return
        await interaction.response.defer()
        if not self.selected_timezone:
            await interaction.followup.send("Please select a timezone first!", ephemeral=True)
            return
        selected_timezone = self.selected_timezone
        success = await self.cog.update_setting(self.guild_id, 'timezone', selected_timezone)
        if success:
            await interaction.followup.send(f"✅ Timezone has been changed to: `{selected_timezone}`", ephemeral=True)
            await asyncio.sleep(2)
            settings = await self.cog.get_guild_settings(self.guild_id)
            current_timezone = settings.get('timezone', 'UTC')
            embed = discord.Embed(
                title="🌍 Timezone Menu",
                description=(
                    f"**This server's current timezone is:** `{current_timezone}`\n\n"
                    "You can change the timezone of the server by choosing from the options in the dropdown menu below."
                ),
                color=discord.Color.purple()
            )
            view = TimezoneView(self.cog, self.guild_id)
            view.children[0].placeholder = f"Selected: {current_timezone}"
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.followup.send("❌ Failed to update timezone. Please try again.", ephemeral=True)

    @discord.ui.button(label="↩ Back", style=discord.ButtonStyle.secondary, row=1)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return
        await interaction.response.defer()
        view = MainSettingsView(self.cog, self.guild_id)
        await view.show_main_menu(interaction)


# ============================================================
# VOICE STATES VIEW
# ============================================================

class VoiceStatesView(discord.ui.View):
    def __init__(self, cog, guild_id, current_states=None):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.bot = cog.bot
        self.message = None
        self.selected_states = (current_states or []).copy()
        self.update_select_menu()

    def update_select_menu(self):
        self.clear_items()
        voice_state_options = [
            discord.SelectOption(label="Afk", value="afk", description="User is in AFK channel",
                                 default="afk" in self.selected_states),
            discord.SelectOption(label="Self Mute", value="self_mute", description="User muted themselves",
                                 default="self_mute" in self.selected_states),
            discord.SelectOption(label="Self Deafen", value="self_deafen", description="User deafened themselves",
                                 default="self_deafen" in self.selected_states),
            discord.SelectOption(label="Server Mute", value="server_mute", description="User was muted by moderation",
                                 default="server_mute" in self.selected_states),
            discord.SelectOption(label="Server Deafen", value="server_deafen",
                                 description="User was deafened by moderation",
                                 default="server_deafen" in self.selected_states),
            discord.SelectOption(label="Streaming", value="streaming", description="User is streaming",
                                 default="streaming" in self.selected_states),
            discord.SelectOption(label="Video", value="video", description="User has video open",
                                 default="video" in self.selected_states),
            discord.SelectOption(label="Suppressed", value="suppressed", description="Stage audience member",
                                 default="suppressed" in self.selected_states),
        ]
        select_menu = discord.ui.Select(
            placeholder="Select voice states to track...",
            options=voice_state_options,
            max_values=8
        )
        select_menu.callback = self.voice_states_select_callback
        self.add_item(select_menu)

        apply_button = discord.ui.Button(
            label="Apply Changes",
            style=discord.ButtonStyle.success,
            disabled=len(self.selected_states) == 0,
            row=1
        )
        apply_button.callback = self.apply_button_callback
        self.add_item(apply_button)

        back_button = discord.ui.Button(
            label="↩ Back", style=discord.ButtonStyle.secondary, row=1)
        back_button.callback = self.back_button_callback
        self.add_item(back_button)

        if self.selected_states:
            count = len(self.selected_states)
            self.children[0].placeholder = f"Selected {count} state{'s' if count != 1 else ''}"

    async def check_permission(self, interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        settings = await self.cog.get_guild_settings(self.guild_id)
        permission_level = settings.get('permission_level', 'Default')
        if permission_level == 'All':
            return True
        elif permission_level == 'Admin':
            return interaction.user.guild_permissions.administrator
        elif permission_level == 'Moderator':
            return interaction.user.guild_permissions.manage_guild
        elif permission_level in ('Default', 'User Restriction'):
            return interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild
        return False

    async def send_permission_error(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="❌ Permission Denied",
            description="You do not have permission to change this setting.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def voice_states_select_callback(self, interaction: discord.Interaction):
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return
        await interaction.response.defer()
        self.selected_states = self.children[0].values
        self.children[1].disabled = len(self.selected_states) == 0
        if self.selected_states:
            count = len(self.selected_states)
            self.children[0].placeholder = f"Selected {count} state{'s' if count != 1 else ''}"
        else:
            self.children[0].placeholder = "Select voice states to track..."
        selected_text = ", ".join(
            f"`{state}`" for state in self.selected_states) if self.selected_states else "None"
        embed = interaction.message.embeds[0]
        embed.description = (
            "**Voice Activity tracking on the Stats bot is split into 8 different states:**\n\n"
            "`Afk` - A user is in the afk voice channel.\n"
            "`Self Mute` - A user muted themself.\n"
            "`Self deafen` - A user deafened themself.\n"
            "`Server Mute` - A user has been muted forcibly through moderation.\n"
            "`Server deafen` - A user has been deafened forcibly through moderation.\n"
            "`Streaming` - A user is streaming.\n"
            "`Video` - A user has their video open.\n"
            "`Suppressed` - Audience members in a stage channel that aren't allowed to speak.\n\n"
            f"**Selected Voice States to track:**\n{selected_text}\n\n"
            "Choose the Voice States that you wish to be tracked in the server's voice activity "
            "through the dropdown menu above."
        )
        await interaction.edit_original_response(embed=embed, view=self)

    async def apply_button_callback(self, interaction: discord.Interaction):
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return
        await interaction.response.defer()
        if not self.selected_states:
            await interaction.followup.send("Please select at least one voice state!", ephemeral=True)
            return
        success = await self.cog.update_setting(self.guild_id, 'voice_states', self.selected_states)
        if success:
            await interaction.followup.send(
                f"✅ Voice states updated! Now tracking: {', '.join(self.selected_states)}", ephemeral=True)
            await asyncio.sleep(2)
            settings = await self.cog.get_guild_settings(self.guild_id)
            current_states = settings.get('voice_states', [])
            embed = discord.Embed(
                title="🔊 Voice States Menu",
                description=(
                    "**Voice Activity tracking on the Stats bot is split into 8 different states:**\n\n"
                    "`Afk` - A user is in the afk voice channel.\n"
                    "`Self Mute` - A user muted themself.\n"
                    "`Self deafen` - A user deafened themself.\n"
                    "`Server Mute` - A user has been muted forcibly through moderation.\n"
                    "`Server deafen` - A user has been deafened forcibly through moderation.\n"
                    "`Streaming` - A user is streaming.\n"
                    "`Video` - A user has their video open.\n"
                    "`Suppressed` - Audience members in a stage channel that aren't allowed to speak.\n\n"
                    f"**The server's current Voice States that are being tracked are:**\n"
                    f"{', '.join(f'`{state}`' for state in current_states)
                       if current_states else '`None`'}\n\n"
                    "Choose the Voice States that you wish to be tracked in the server's voice activity "
                    "through the dropdown menu below."
                ),
                color=discord.Color.purple()
            )
            view = VoiceStatesView(self.cog, self.guild_id, current_states)
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.followup.send("❌ Failed to update voice states. Please try again.", ephemeral=True)

    async def back_button_callback(self, interaction: discord.Interaction):
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return
        await interaction.response.defer()
        view = MainSettingsView(self.cog, self.guild_id)
        await view.show_main_menu(interaction)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except Exception:
            pass


# ============================================================
# BOT FILTER VIEW
# ============================================================

class BotFilterView(discord.ui.View):
    def __init__(self, cog, guild_id, bot_filter_enabled):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.bot = cog.bot
        self.bot_filter_enabled = bot_filter_enabled
        self.message = None

        if bot_filter_enabled:
            self.add_item(IncludeBotsButton())
        else:
            self.add_item(FilterBotsButton())
        self.add_item(BackButton())

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except Exception:
            pass

    async def check_permission(self, interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        settings = await self.cog.get_guild_settings(self.guild_id)
        permission_level = settings.get('permission_level', 'Default')
        if permission_level == 'All':
            return True
        elif permission_level == 'Admin':
            return interaction.user.guild_permissions.administrator
        elif permission_level == 'Moderator':
            return interaction.user.guild_permissions.manage_guild
        elif permission_level in ('Default', 'User Restriction'):
            return interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild
        return False

    async def send_permission_error(self, interaction: discord.Interaction):
        settings = await self.cog.get_guild_settings(self.guild_id)
        permission_level = settings.get('permission_level', 'Default')
        if permission_level == 'Admin':
            required_permission = "Administrator"
        elif permission_level == 'Moderator':
            required_permission = "Manage Server"
        elif permission_level in ['Default', 'User Restriction']:
            required_permission = "Administrator or Manage Server"
        else:
            required_permission = "Administrator"
        embed = discord.Embed(
            title="❌ Permission Denied",
            description=f"Sorry! You need the `{required_permission}` permission to access this command.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class FilterBotsButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Filter Bots", style=discord.ButtonStyle.danger, emoji="🤖", row=0)

    async def callback(self, interaction: discord.Interaction):
        if not await self.view.check_permission(interaction):
            await self.view.send_permission_error(interaction)
            return
        await interaction.response.defer()
        cog = self.view.cog
        guild_id = self.view.guild_id
        success = await cog.update_setting(guild_id, 'bot_filter', True)
        if success:
            await interaction.followup.send("✅ Bots are now **filtered out** from statistics.", ephemeral=True)
            await asyncio.sleep(2)
            settings = await cog.get_guild_settings(guild_id)
            bot_filter = settings.get('bot_filter', False)
            status = "filtered out from" if bot_filter else "included in"
            button_text = "Include Bots" if bot_filter else "Filter Bots"
            embed = discord.Embed(
                title="🤖 Bot Filter Menu",
                description=(
                    f"**Bots are currently {status} statistics.**\n\n"
                    f"You can {'include bots in' if bot_filter else 'filter out bots from'} statistics "
                    f"through the **\"{button_text}\"** button below."
                ),
                color=discord.Color.purple()
            )
            view = BotFilterView(cog, guild_id, bot_filter)
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.followup.send("❌ Failed to update bot filter. Please try again.", ephemeral=True)


class IncludeBotsButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Include Bots",
                         style=discord.ButtonStyle.success, emoji="🤖", row=0)

    async def callback(self, interaction: discord.Interaction):
        if not await self.view.check_permission(interaction):
            await self.view.send_permission_error(interaction)
            return
        await interaction.response.defer()
        cog = self.view.cog
        guild_id = self.view.guild_id
        success = await cog.update_setting(guild_id, 'bot_filter', False)
        if success:
            await interaction.followup.send("✅ Bots are now **included** in statistics.", ephemeral=True)
            await asyncio.sleep(2)
            settings = await cog.get_guild_settings(guild_id)
            bot_filter = settings.get('bot_filter', False)
            status = "filtered out from" if bot_filter else "included in"
            button_text = "Include Bots" if bot_filter else "Filter Bots"
            embed = discord.Embed(
                title="🤖 Bot Filter Menu",
                description=(
                    f"**Bots are currently {status} statistics.**\n\n"
                    f"You can {'include bots in' if bot_filter else 'filter out bots from'} statistics "
                    f"through the **\"{button_text}\"** button below."
                ),
                color=discord.Color.purple()
            )
            view = BotFilterView(cog, guild_id, bot_filter)
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.followup.send("❌ Failed to update bot filter. Please try again.", ephemeral=True)


class BackButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="↩ Back", style=discord.ButtonStyle.secondary, row=1)

    async def callback(self, interaction: discord.Interaction):
        if not await self.view.check_permission(interaction):
            await self.view.send_permission_error(interaction)
            return
        await interaction.response.defer()
        view = MainSettingsView(self.view.cog, self.view.guild_id)
        await view.show_main_menu(interaction)


# ============================================================
# PERMISSIONS VIEW
# ============================================================

class PermissionsView(discord.ui.View):
    def __init__(self, cog, guild_id):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.bot = cog.bot
        self.selected_level = None
        self.message = None

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except Exception:
            pass

    async def check_permission(self, interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        settings = await self.cog.get_guild_settings(self.guild_id)
        permission_level = settings.get('permission_level', 'Default')
        if permission_level == 'All':
            return True
        elif permission_level == 'Admin':
            return interaction.user.guild_permissions.administrator
        elif permission_level == 'Moderator':
            return interaction.user.guild_permissions.manage_guild
        elif permission_level in ('Default', 'User Restriction'):
            return interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild
        return False

    async def send_permission_error(self, interaction: discord.Interaction):
        settings = await self.cog.get_guild_settings(self.guild_id)
        permission_level = settings.get('permission_level', 'Default')
        if permission_level == 'Admin':
            required_permission = "Administrator"
        elif permission_level == 'Moderator':
            required_permission = "Manage Server"
        elif permission_level in ['Default', 'User Restriction']:
            required_permission = "Administrator or Manage Server"
        else:
            required_permission = "Administrator"
        embed = discord.Embed(
            title="❌ Permission Denied",
            description=f"Sorry! You need the `{required_permission}` permission to access this command.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.select(
        placeholder="Select permission level...",
        options=[
            discord.SelectOption(label="All", value="All",
                                 description="All members can use any command"),
            discord.SelectOption(label="Default", value="Default",
                                 description="Default access level"),
            discord.SelectOption(label="User Restriction", value="User Restriction",
                                 description="Users can only use commands on themselves"),
            discord.SelectOption(label="Admin", value="Admin",
                                 description="Only administrators can use commands"),
            discord.SelectOption(label="Moderator", value="Moderator",
                                 description="Only users with Manage Server permission"),
        ]
    )
    async def permissions_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return
        await interaction.response.defer()
        self.selected_level = select.values[0]
        self.children[1].disabled = False
        select.placeholder = f"Selected: {self.selected_level}"
        await interaction.edit_original_response(view=self)

    @discord.ui.button(label="Apply Changes", style=discord.ButtonStyle.success, disabled=True, row=1)
    async def apply_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return
        await interaction.response.defer()
        if not self.selected_level:
            await interaction.followup.send("Please select a permission level first!", ephemeral=True)
            return
        selected_level = self.selected_level
        success = await self.cog.update_setting(self.guild_id, 'permission_level', selected_level)
        if success:
            await interaction.followup.send(
                f"✅ Permission level has been changed to: `{selected_level}`", ephemeral=True)
            await asyncio.sleep(2)
            settings = await self.cog.get_guild_settings(self.guild_id)
            current_level = settings.get('permission_level', 'Default')
            embed = discord.Embed(
                title="🔐 Command Permission Access Levels Menu",
                description=(
                    f"**This server's permission level is currently set to:** `{current_level}`\n\n"
                    "**Permission Levels:**\n\n"
                    "`All` - All members regardless of their permissions are allowed to use any command on the bot.\n\n"
                    "`Default` - The default access level that restricts or enables specific commands for users "
                    "with specific permissions.\n\n"
                    "`User Restriction` - Same as Default except users can only use user commands on their own "
                    "account.\n\n"
                    "`Admin` - Only users with the administrator permission can use any commands on the bot.\n\n"
                    "`Moderator` - Only users with the Manage Server permission can use any commands on the bot.\n\n"
                    "You can change the permission level through the dropdown menu below."
                ),
                color=discord.Color.purple()
            )
            view = PermissionsView(self.cog, self.guild_id)
            view.children[0].placeholder = f"Selected: {current_level}"
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.followup.send(
                "❌ Failed to update permission level. Please try again.", ephemeral=True)

    @discord.ui.button(label="↩ Back", style=discord.ButtonStyle.secondary, row=1)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return
        await interaction.response.defer()
        view = MainSettingsView(self.cog, self.guild_id)
        await view.show_main_menu(interaction)


# ============================================================
# SUSPICIOUS INVITES VIEW + MODAL
# ============================================================

class SuspiciousInvitesView(discord.ui.View):
    def __init__(self, cog, guild_id, current_days):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.bot = cog.bot
        self.current_days = current_days
        self.message = None

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except Exception:
            pass

    async def check_permission(self, interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        settings = await self.cog.get_guild_settings(self.guild_id)
        permission_level = settings.get('permission_level', 'Default')
        if permission_level == 'All':
            return True
        elif permission_level == 'Admin':
            return interaction.user.guild_permissions.administrator
        elif permission_level == 'Moderator':
            return interaction.user.guild_permissions.manage_guild
        elif permission_level in ('Default', 'User Restriction'):
            return interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_guild
        return False

    async def send_permission_error(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="❌ Permission Denied",
            description="You do not have permission to change this setting.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Change Minimum Account Age", style=discord.ButtonStyle.primary, emoji="⚠️", row=0)
    async def change_age_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return
        modal = SuspiciousInvitesModal(
            self.cog, self.guild_id, self.current_days, self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="↩ Back", style=discord.ButtonStyle.secondary, row=1)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return
        await interaction.response.defer()
        view = MainSettingsView(self.cog, self.guild_id)
        await view.show_main_menu(interaction)


class SuspiciousInvitesModal(discord.ui.Modal, title="Change Minimum Account Age"):
    def __init__(self, cog, guild_id, current_days, parent_view):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.parent_view = parent_view
        self.days_input = discord.ui.TextInput(
            label="Minimum Account Age (Days)",
            placeholder=f"Current value: {current_days} days. Enter 0 to disable.",
            default=str(current_days),
            required=True,
            min_length=1,
            max_length=3
        )
        self.add_item(self.days_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not await self.parent_view.check_permission(interaction):
            await self.parent_view.send_permission_error(interaction)
            return
        await interaction.response.defer()
        try:
            days = int(self.days_input.value.strip())
            if days < 0:
                await interaction.followup.send(
                    "❌ Days cannot be negative! Please enter 0 or a positive number.", ephemeral=True)
                return
            if days > 365:
                await interaction.followup.send(
                    "❌ Days cannot exceed 365! Please enter a number between 0 and 365.", ephemeral=True)
                return
        except ValueError:
            await interaction.followup.send("❌ Please enter a valid number!", ephemeral=True)
            return

        success = await self.cog.update_setting(self.guild_id, 'min_account_age_days', days)
        if success:
            if days == 0:
                await interaction.followup.send(
                    "✅ Suspicious invite detection has been **disabled**.", ephemeral=True)
            else:
                await interaction.followup.send(
                    f"✅ Minimum account age set to **{days} day{'s' if days != 1 else ''}**.", ephemeral=True)
            await asyncio.sleep(2)
            settings = await self.cog.get_guild_settings(self.guild_id)
            current_days = settings.get('min_account_age_days', 3)
            embed = discord.Embed(
                title="⚠️ Suspicious Invite Tracking Menu",
                description=(
                    "**What are Suspicious Invites?**\n\n"
                    "Suspicious invites are detected when **either** the person inviting **OR** the person joining "
                    "has an account that is too new.\n\n"
                    "This helps protect your server from:\n"
                    "• Raids using newly created accounts\n"
                    "• Bot accounts joining via compromised invites\n"
                    "• Invite spam from fresh accounts\n\n"
                    f"**Current Setting:** `{current_days} day{'s' if current_days != 1 else ''}`\n\n"
                    "If an account is younger than this many days, any invite they send or use will be marked as "
                    "**suspicious**.\n\n"
                    "Set to `0` to disable suspicious invite detection entirely.\n\n"
                    "**Click the button below to change this value.**"
                ),
                color=discord.Color.purple()
            )
            view = SuspiciousInvitesView(self.cog, self.guild_id, current_days)
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.followup.send(
                "❌ Failed to update suspicious invite settings. Please try again.", ephemeral=True)


# ============================================================
# STAT TOGGLES VIEW
# ============================================================

class StatTogglesView(discord.ui.View):
    def __init__(self, cog, guild_id, settings):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.settings = settings
        self.message = None

        # Build selected_toggles from current settings
        self.selected_toggles = [
            key for key, (label, desc, default) in STAT_TOGGLE_META.items()
            if settings.get(key, default)
        ]

        self._rebuild()

    def _rebuild(self):
        self.clear_items()

        options = []
        for key, (label, desc, default) in STAT_TOGGLE_META.items():
            # Truncate description to 100 chars (Discord limit)
            short_desc = desc[:97] + '...' if len(desc) > 100 else desc
            options.append(discord.SelectOption(
                label=label,
                value=key,
                description=short_desc,
                default=key in self.selected_toggles,
            ))

        select_menu = discord.ui.Select(
            placeholder="Select stat types to track...",
            options=options,
            min_values=0,
            max_values=len(options),
        )
        select_menu.callback = self._select_callback
        self.add_item(select_menu)

        apply_btn = discord.ui.Button(
            label="Apply Changes",
            style=discord.ButtonStyle.success,
            row=1,
        )
        apply_btn.callback = self._apply_callback
        self.add_item(apply_btn)

        back_btn = discord.ui.Button(
            label="↩ Back",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        back_btn.callback = self._back_callback
        self.add_item(back_btn)

        # Update placeholder to reflect count
        count = len(self.selected_toggles)
        self.children[0].placeholder = (
            f"Selected {count} stat type{'s' if count != 1 else ''}"
            if count else "Select stat types to track..."
        )

    def build_embed(self) -> discord.Embed:
        enabled = self.selected_toggles

        lines = []
        for key, (label, desc, default) in STAT_TOGGLE_META.items():
            status = "Enabled" if key in enabled else "Disabled"
            lines.append(f"**{label}** — {status}\n{desc}")

        currently = ', '.join(
            STAT_TOGGLE_META[k][0] for k in enabled
        ) if enabled else 'None'

        embed = discord.Embed(
            title="📈 Stat Toggles",
            description=(
                "Choose which stat types the bot actively tracks on this server. "
                "Disabling a stat type stops new data being collected for it — "
                "existing data is not deleted.\n\n"
                + '\n\n'.join(lines)
                + f"\n\n**Currently enabled:** {currently}\n\n"
                "Select from the dropdown below, then press **Apply Changes**."
            ),
            color=discord.Color.purple(),
        )
        return embed

    async def check_permission(self, interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        settings = await self.cog.get_guild_settings(self.guild_id)
        permission_level = settings.get('permission_level', 'Default')
        if permission_level == 'All':
            return True
        elif permission_level == 'Admin':
            return interaction.user.guild_permissions.administrator
        elif permission_level == 'Moderator':
            return interaction.user.guild_permissions.manage_guild
        elif permission_level in ('Default', 'User Restriction'):
            return (interaction.user.guild_permissions.administrator
                    or interaction.user.guild_permissions.manage_guild)
        return False

    async def send_permission_error(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="❌ Permission Denied",
            description="You do not have permission to change this setting.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _select_callback(self, interaction: discord.Interaction):
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return
        await interaction.response.defer()
        self.selected_toggles = list(self.children[0].values)
        self._rebuild()
        await interaction.edit_original_response(embed=self.build_embed(), view=self)

    async def _apply_callback(self, interaction: discord.Interaction):
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return
        await interaction.response.defer()

        # Build the full dict of all toggle keys -> bool
        toggles = {key: (key in self.selected_toggles)
                   for key in STAT_TOGGLE_META}
        success = await self.cog.update_stat_toggles(self.guild_id, toggles)

        if success:
            enabled_names = [STAT_TOGGLE_META[k][0]
                             for k in self.selected_toggles]
            enabled_str = ', '.join(
                f'`{n}`' for n in enabled_names) if enabled_names else '`None`'
            await interaction.followup.send(
                f"✅ Stat tracking updated. Now enabled: {enabled_str}", ephemeral=True)
            await asyncio.sleep(2)
            updated_settings = await self.cog.get_guild_settings(self.guild_id)
            view = StatTogglesView(self.cog, self.guild_id, updated_settings)
            await interaction.edit_original_response(embed=view.build_embed(), view=view)
        else:
            await interaction.followup.send(
                "❌ Failed to update stat toggles. Please try again.", ephemeral=True)

    async def _back_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view = MainSettingsView(self.cog, self.guild_id)
        await view.show_main_menu(interaction)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except Exception:
            pass


# ============================================================
# TIME PERIOD VIEW
# ============================================================

class TimePeriodView(discord.ui.View):
    def __init__(self, cog, guild_id, settings, pending_mode=None, pending_data=None):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.settings = settings
        self.pending_mode = pending_mode
        self.pending_data = pending_data or {}
        self.message = None

        if pending_mode is None:
            self._add_selection_buttons()
        else:
            self._add_confirmation_buttons()

    def _add_selection_buttons(self):
        btn_all_time = discord.ui.Button(
            label="All Time", style=discord.ButtonStyle.secondary, row=0)
        btn_all_time.callback = self._all_time_callback
        self.add_item(btn_all_time)

        btn_days_back = discord.ui.Button(
            label="Days Back", style=discord.ButtonStyle.secondary, row=0)
        btn_days_back.callback = self._days_back_callback
        self.add_item(btn_days_back)

        btn_date_range = discord.ui.Button(
            label="Date Range", style=discord.ButtonStyle.secondary, row=1)
        btn_date_range.callback = self._date_range_callback
        self.add_item(btn_date_range)

        btn_rolling = discord.ui.Button(
            label="Rolling Window", style=discord.ButtonStyle.secondary, row=1)
        btn_rolling.callback = self._rolling_window_callback
        self.add_item(btn_rolling)

        btn_back = discord.ui.Button(
            label="↩ Back", style=discord.ButtonStyle.secondary, row=2)
        btn_back.callback = self._back_callback
        self.add_item(btn_back)

    def _add_confirmation_buttons(self):
        btn_apply = discord.ui.Button(
            label="Apply", style=discord.ButtonStyle.success, row=0)
        btn_apply.callback = self._apply_callback
        self.add_item(btn_apply)

        btn_cancel = discord.ui.Button(
            label="Cancel", style=discord.ButtonStyle.secondary, row=0)
        btn_cancel.callback = self._cancel_callback
        self.add_item(btn_cancel)

    async def check_permission(self, interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        guild_settings = await self.cog.get_guild_settings(self.guild_id)
        permission_level = guild_settings.get('permission_level', 'Default')
        if permission_level == 'All':
            return True
        elif permission_level == 'Admin':
            return interaction.user.guild_permissions.administrator
        elif permission_level == 'Moderator':
            return interaction.user.guild_permissions.manage_guild
        elif permission_level in ('Default', 'User Restriction'):
            return (interaction.user.guild_permissions.administrator
                    or interaction.user.guild_permissions.manage_guild)
        return False

    async def send_permission_error(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="❌ Permission Denied",
            description="You do not have permission to change this setting.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    def build_selection_embed(self) -> discord.Embed:
        current = format_time_period_display(self.settings)
        embed = discord.Embed(
            title="Time Period Settings",
            description=(
                f"**Current Setting:** `{current}`\n\n\n"
                "**All Time**\n"
                "Shows all data with no time filter applied.\n\n"
                "**Days Back**\n"
                "Shows data from the last X days. For example, setting 30 days shows only data "
                "collected within the past 30 days.\n\n"
                "**Date Range**\n"
                "Shows data between a from date and a to date. The to date is optional — leaving it "
                "blank shows data from the from date up to now. You can also enter just a to date "
                "to show everything up to that point.\n\n"
                "**Rolling Window**\n"
                "Shows data within a recurring window. Set either a day of the week (e.g. every "
                "Monday resets the window through to the following Monday) or a day of the month "
                "(e.g. the 1st of each month starts a new window).\n\n\n"
                "Select a type below to update the server default."
            ),
            color=discord.Color.purple()
        )
        return embed

    def _format_pending_display(self) -> str:
        mode = self.pending_mode
        data = self.pending_data
        if mode == 'all_time':
            return "All Time"
        elif mode == 'days_back':
            return f"Last {data.get('days_back')} days"
        elif mode == 'date_range':
            from_d = data.get('from_date')
            to_d = data.get('to_date')
            from_str = from_d.strftime('%d-%m-%Y') if from_d else None
            to_str = to_d.strftime('%d-%m-%Y') if to_d else None
            if from_str and to_str:
                return f"{from_str} to {to_str}"
            elif from_str:
                return f"From {from_str} to now"
            else:
                return f"From the beginning to {to_str}"
        elif mode == 'rolling_window':
            rolling_type = data.get('rolling_type')
            rolling_value = data.get('rolling_value')
            if rolling_type == 'weekday':
                names = ['Monday', 'Tuesday', 'Wednesday',
                         'Thursday', 'Friday', 'Saturday', 'Sunday']
                return f"Rolling window — every {names[rolling_value]}"
            else:
                return f"Rolling window — {rolling_value}{get_ordinal(rolling_value)} of each month"
        return "Unknown"

    def build_confirmation_embed(self) -> discord.Embed:
        current = format_time_period_display(self.settings)
        pending = self._format_pending_display()
        embed = discord.Embed(
            title="Time Period Settings — Confirm Change",
            description=(
                f"**Current Setting:** `{current}`\n"
                f"**New Setting:** `{pending}`\n\n"
                "Press **Apply** to save this change, or **Cancel** to go back."
            ),
            color=discord.Color.purple()
        )
        return embed

    async def _all_time_callback(self, interaction: discord.Interaction):
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return
        await interaction.response.defer()
        confirm_view = TimePeriodView(
            self.cog, self.guild_id, self.settings,
            pending_mode='all_time', pending_data={}
        )
        await interaction.edit_original_response(
            embed=confirm_view.build_confirmation_embed(), view=confirm_view)

    async def _days_back_callback(self, interaction: discord.Interaction):
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return
        modal = DaysBackModal(self.cog, self.guild_id, self.settings)
        await interaction.response.send_modal(modal)

    async def _date_range_callback(self, interaction: discord.Interaction):
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return
        modal = DateRangePeriodModal(self.cog, self.guild_id, self.settings)
        await interaction.response.send_modal(modal)

    async def _rolling_window_callback(self, interaction: discord.Interaction):
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return
        modal = RollingWindowModal(self.cog, self.guild_id, self.settings)
        await interaction.response.send_modal(modal)

    async def _apply_callback(self, interaction: discord.Interaction):
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return
        await interaction.response.defer()

        data = self.pending_data
        success = await self.cog.update_time_period_setting(
            guild_id=self.guild_id,
            mode=self.pending_mode,
            days_back=data.get('days_back'),
            from_date=data.get('from_date'),
            to_date=data.get('to_date'),
            rolling_type=data.get('rolling_type'),
            rolling_value=data.get('rolling_value'),
        )

        if success:
            await interaction.followup.send("✅ Time period setting updated.", ephemeral=True)
            await asyncio.sleep(1)
            updated_settings = await self.cog.get_guild_settings(self.guild_id)
            selection_view = TimePeriodView(
                self.cog, self.guild_id, updated_settings)
            await interaction.edit_original_response(
                embed=selection_view.build_selection_embed(), view=selection_view)
        else:
            await interaction.followup.send(
                "❌ Failed to update the time period setting. Please try again.", ephemeral=True)

    async def _cancel_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        selection_view = TimePeriodView(self.cog, self.guild_id, self.settings)
        await interaction.edit_original_response(
            embed=selection_view.build_selection_embed(), view=selection_view)

    async def _back_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view = MainSettingsView(self.cog, self.guild_id)
        await view.show_main_menu(interaction)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except Exception:
            pass


# ============================================================
# TIME PERIOD MODALS
# ============================================================

class DaysBackModal(discord.ui.Modal, title="Set Days Back"):
    def __init__(self, cog, guild_id, settings):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.settings = settings

        self.days_input = discord.ui.TextInput(
            label="Number of Days",
            placeholder="e.g. 14, 30, 90",
            required=True,
            max_length=4
        )
        self.add_item(self.days_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        raw = self.days_input.value.strip()

        if not raw.isdigit():
            await interaction.followup.send(
                "Please enter a valid whole number.", ephemeral=True)
            return

        days = int(raw)
        if days < 1 or days > 3650:
            await interaction.followup.send(
                "Days must be between 1 and 3650.", ephemeral=True)
            return

        confirm_view = TimePeriodView(
            self.cog, self.guild_id, self.settings,
            pending_mode='days_back', pending_data={'days_back': days}
        )
        await interaction.edit_original_response(
            embed=confirm_view.build_confirmation_embed(), view=confirm_view)


class DateRangePeriodModal(discord.ui.Modal, title="Set Date Range"):
    def __init__(self, cog, guild_id, settings):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.settings = settings

        self.from_date_input = discord.ui.TextInput(
            label="From Date (DD-MM-YYYY)",
            placeholder="e.g. 01-01-2024 — leave blank for the beginning of data",
            required=False,
            max_length=10
        )
        self.to_date_input = discord.ui.TextInput(
            label="To Date (DD-MM-YYYY)",
            placeholder="e.g. 31-12-2024 — leave blank for up to now",
            required=False,
            max_length=10
        )
        self.add_item(self.from_date_input)
        self.add_item(self.to_date_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        from_raw = self.from_date_input.value.strip()
        to_raw = self.to_date_input.value.strip()

        if not from_raw and not to_raw:
            await interaction.followup.send(
                "Please enter at least one date.", ephemeral=True)
            return

        from_date = None
        to_date = None

        if from_raw:
            from_date = parse_date_string(from_raw)
            if from_date is None:
                await interaction.followup.send(
                    "Invalid from date. Use the format DD-MM-YYYY (e.g. 01-01-2024).",
                    ephemeral=True)
                return

        if to_raw:
            to_date = parse_date_string(to_raw)
            if to_date is None:
                await interaction.followup.send(
                    "Invalid to date. Use the format DD-MM-YYYY (e.g. 31-12-2024).",
                    ephemeral=True)
                return

        if from_date and to_date and from_date >= to_date:
            await interaction.followup.send(
                "The from date must be earlier than the to date.", ephemeral=True)
            return

        confirm_view = TimePeriodView(
            self.cog, self.guild_id, self.settings,
            pending_mode='date_range',
            pending_data={'from_date': from_date, 'to_date': to_date}
        )
        await interaction.edit_original_response(
            embed=confirm_view.build_confirmation_embed(), view=confirm_view)


class RollingWindowModal(discord.ui.Modal, title="Set Rolling Window"):
    def __init__(self, cog, guild_id, settings):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.settings = settings

        self.weekday_input = discord.ui.TextInput(
            label="Day of Week",
            placeholder="e.g. Monday, Wednesday — or 0 (Mon) through 6 (Sun). Fill ONE field only.",
            required=False,
            max_length=20
        )
        self.day_of_month_input = discord.ui.TextInput(
            label="Day of Month",
            placeholder="e.g. 1, 15, 28 — fill ONE field only, not both",
            required=False,
            max_length=2
        )
        self.add_item(self.weekday_input)
        self.add_item(self.day_of_month_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        weekday_raw = self.weekday_input.value.strip()
        dom_raw = self.day_of_month_input.value.strip()

        if weekday_raw and dom_raw:
            embed = discord.Embed(
                title="Invalid Input",
                description=(
                    "Please fill in only **one** field — either Day of Week or Day of Month, not both.\n\n"
                    "Go back and try again."
                ),
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if not weekday_raw and not dom_raw:
            await interaction.followup.send(
                "Please fill in at least one field.", ephemeral=True)
            return

        if weekday_raw:
            weekday = parse_weekday(weekday_raw)
            if weekday is None:
                await interaction.followup.send(
                    "Invalid day of week. Enter a name such as Monday or Wednesday, "
                    "or a number from 0 (Monday) to 6 (Sunday).",
                    ephemeral=True)
                return
            pending_data = {'rolling_type': 'weekday',
                            'rolling_value': weekday}
        else:
            if not dom_raw.isdigit():
                await interaction.followup.send(
                    "Day of month must be a whole number between 1 and 31.", ephemeral=True)
                return
            dom = int(dom_raw)
            if dom < 1 or dom > 31:
                await interaction.followup.send(
                    "Day of month must be between 1 and 31.", ephemeral=True)
                return
            pending_data = {'rolling_type': 'monthly', 'rolling_value': dom}

        confirm_view = TimePeriodView(
            self.cog, self.guild_id, self.settings,
            pending_mode='rolling_window', pending_data=pending_data
        )
        await interaction.edit_original_response(
            embed=confirm_view.build_confirmation_embed(), view=confirm_view)


# ============================================================
# SETUP
# ============================================================

async def setup(bot):
    await bot.add_cog(Settings(bot))
