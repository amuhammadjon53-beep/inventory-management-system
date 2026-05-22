import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncpg
import asyncio
from typing import Optional
import json
import os
import aiocron
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta
from .ratelimiter import RateLimiter, RateLimitType, rate_limited, get_rate_limiter


class Settings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pool = None
        self.initialized = False
        self.rate_limiter = get_rate_limiter()

        # Start initialization task like DatabaseStats does
        self.init_pools.start()

        # Start privacy cleanup cron job (runs every 5 minutes)
        self.privacy_cleanup_cron = aiocron.crontab(
            '*/5 * * * *', func=self.process_pending_privacy_deletions, tz=ZoneInfo('UTC'))

    @tasks.loop(count=1)
    async def init_pools(self):
        """Initialize database connection like DatabaseStats does"""
        # Wait for DatabaseStats cog to be ready
        for attempt in range(5):  # Try up to 5 times
            db_stats_cog = self.bot.get_cog("DatabaseStats")
            if db_stats_cog and hasattr(db_stats_cog, 'pool') and db_stats_cog.pool:
                self.pool = db_stats_cog.pool
                await self.initialize_settings_table()
                return
            await asyncio.sleep(2)  # Wait 2 seconds before retrying

        print("⚠️ Settings: DatabaseStats cog pool not available after waiting")

    async def initialize_settings_table(self):
        """Initialize the settings table"""
        if not self.pool:
            print("❌ Settings: No database pool available")
            self.initialized = False
            return

        try:
            async with self.pool.acquire() as conn:
                # Create settings table if not exists
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
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Create user settings table if not exists
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
                    # PostgreSQL doesn't have IF NOT EXISTS for columns until PG 9.6+
                    # So we need to check if column exists first
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
        """Get settings for a guild"""
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
        """Get default settings structure"""
        return {
            'guild_id': guild_id,
            'prefix': 's!',
            'timezone': 'UTC',
            'voice_states': ["self_mute", "self_deafen", "streaming", "video"],
            'permission_level': 'Default',
            'bot_filter': False,
            'dashboard_access_level': 'Member',
            'min_account_age_days': 3,
            'created_at': None
        }

    async def create_default_settings(self, guild_id: int):
        """Create default settings for a guild"""
        if not self.pool or not self.initialized:
            return await self.get_default_settings(guild_id)

        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO settings (guild_id, voice_states, min_account_age_days) 
                    VALUES ($1, ARRAY['self_mute', 'self_deafen', 'streaming', 'video'], 3)
                    ON CONFLICT (guild_id) DO NOTHING
                """, guild_id)

                # Return the newly created settings
                settings = await conn.fetchrow(
                    "SELECT * FROM settings WHERE guild_id = $1",
                    guild_id
                )
                return dict(settings) if settings else await self.get_default_settings(guild_id)

        except Exception as e:
            print(f"❌ Settings: Error creating settings: {e}")
            return await self.get_default_settings(guild_id)

    async def update_setting(self, guild_id: int, setting: str, value):
        """Update a specific setting for a guild"""
        if not self.pool or not self.initialized:
            print(f"❌ Settings: No connection to update {setting}")
            return False

        try:
            async with self.pool.acquire() as conn:
                # Ensure settings exist
                await self.create_default_settings(guild_id)

                # Update the setting
                await conn.execute(
                    f"UPDATE settings SET {setting} = $1 WHERE guild_id = $2",
                    value, guild_id
                )
                return True

        except Exception as e:
            print(f"❌ Settings: Error updating {setting}: {e}")
            return False

    async def get_user_settings(self, user_id: int, guild_id: int):
        """Get user settings for a specific guild"""
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
        """Update a specific user setting"""
        if not self.pool or not self.initialized:
            print(f"❌ Settings: No connection to update user {setting}")
            return False

        try:
            async with self.pool.acquire() as conn:
                # Get current setting
                current = await conn.fetchrow(
                    "SELECT privacy_enabled FROM user_settings WHERE user_id = $1 AND guild_id = $2",
                    user_id, guild_id
                )

                current_enabled = current['privacy_enabled'] if current else False

                # If turning ON privacy mode (value = True), add to pending deletions queue
                if value == True and not current_enabled:
                    # Mark as pending deletion
                    await conn.execute("""
                        INSERT INTO user_settings (user_id, guild_id, privacy_enabled, privacy_pending_delete, updated_at)
                        VALUES ($1, $2, $3, TRUE, CURRENT_TIMESTAMP)
                        ON CONFLICT (user_id, guild_id) 
                        DO UPDATE SET 
                            privacy_enabled = $3, 
                            privacy_pending_delete = TRUE,
                            updated_at = CURRENT_TIMESTAMP
                    """, user_id, guild_id, value)

                    # Add to pending deletions queue
                    await conn.execute("""
                        INSERT INTO privacy_pending_deletions (user_id, guild_id, requested_at)
                        VALUES ($1, $2, CURRENT_TIMESTAMP)
                        ON CONFLICT (user_id, guild_id) DO UPDATE
                        SET requested_at = CURRENT_TIMESTAMP, processed = FALSE, processed_at = NULL
                    """, user_id, guild_id)

                    print(
                        f"🔐 Privacy mode enabled for user {user_id} in guild {guild_id} - queued for deletion")
                else:
                    # Just update normally
                    await conn.execute("""
                        INSERT INTO user_settings (user_id, guild_id, privacy_enabled, updated_at)
                        VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
                        ON CONFLICT (user_id, guild_id) 
                        DO UPDATE SET privacy_enabled = $3, updated_at = CURRENT_TIMESTAMP
                    """, user_id, guild_id, value)

                    if value == False:
                        print(
                            f"🔓 Privacy mode disabled for user {user_id} in guild {guild_id}")

                return True

        except Exception as e:
            print(f"❌ Settings: Error updating user {setting}: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def process_pending_privacy_deletions(self):
        """Cron job that runs every 5 minutes to process pending privacy deletions"""
        if not self.pool or not self.initialized:
            return

        print(f"\n{'='*60}")
        print(
            f"🕒 Processing pending privacy deletions at {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"{'='*60}")

        try:
            async with self.pool.acquire() as conn:
                # Get all pending deletions
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

                # Get the ResetStats cog to use its database manager
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

                        # Delete all statistics for this user in this guild
                        result = await reset_cog.db_manager.delete_user_all(
                            guild_id=guild_id,
                            user_id=user_id,
                            channel_id=None,
                            category_id=None
                        )

                        # Mark as processed
                        await conn.execute("""
                            UPDATE privacy_pending_deletions
                            SET processed = TRUE, processed_at = CURRENT_TIMESTAMP
                            WHERE user_id = $1 AND guild_id = $2
                        """, user_id, guild_id)

                        # Clear the pending delete flag
                        await conn.execute("""
                            UPDATE user_settings
                            SET privacy_pending_delete = FALSE
                            WHERE user_id = $1 AND guild_id = $2
                        """, user_id, guild_id)

                        deleted_count += 1

                        # Format the result for logging
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
        """Check if user has permission to use settings command based on server permission level"""
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
        """Internal function to handle settings for both command types"""
        if not self.initialized:
            if is_interaction:
                await ctx_or_interaction.response.send_message("Settings system is initializing, please try again in a moment.", ephemeral=True)
            else:
                await ctx_or_interaction.send("Settings system is initializing, please try again in a moment.", delete_after=5)
            return

        # Get context parameters
        if is_interaction:
            user = ctx_or_interaction.user
            guild_id = ctx_or_interaction.guild_id
            send_method = ctx_or_interaction.response.send_message
        else:
            # Try to delete the command message
            try:
                await ctx_or_interaction.message.delete()
            except:
                pass
            user = ctx_or_interaction.author
            guild_id = ctx_or_interaction.guild.id
            send_method = ctx_or_interaction.send

        # Check permission based on server settings
        if not await self.check_settings_permission(ctx_or_interaction if is_interaction else type('obj', (object,), {'user': user, 'guild_id': guild_id, 'user.guild_permissions': user.guild_permissions})):
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
             "Set minimum account age to detect suspicious invites.")
        ]

        for setting_name, description in settings_list:
            embed.add_field(name=setting_name, value=description, inline=False)

        # Add the instruction at the bottom
        embed.add_field(
            name="‎",  # Invisible character for spacing
            value="**Choose a setting from the dropdown menu below**",
            inline=False
        )

        view = MainSettingsView(self, guild_id)

        if is_interaction:
            response = await ctx_or_interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            view.message = await ctx_or_interaction.original_response()
        else:
            msg = await ctx_or_interaction.send(embed=embed, view=view, delete_after=300)
            view.message = msg

    # =========================================================
    # INTERNAL FUNCTION FOR USER SETTINGS COMMAND
    # =========================================================
    @rate_limited(RateLimitType.MESSAGE, timeout=15.0)
    async def _handle_user_settings_command(self, ctx_or_interaction, is_interaction=False):
        """Internal function to handle user settings for both command types"""
        if not self.initialized:
            if is_interaction:
                await ctx_or_interaction.response.send_message("Settings system is initializing, please try again in a moment.", ephemeral=True)
            else:
                await ctx_or_interaction.send("Settings system is initializing, please try again in a moment.", delete_after=5)
            return

        # Get context parameters
        if is_interaction:
            user = ctx_or_interaction.user
            guild_id = ctx_or_interaction.guild_id
            user_id = user.id
            send_method = ctx_or_interaction.response.send_message
        else:
            # Try to delete the command message
            try:
                await ctx_or_interaction.message.delete()
            except:
                pass
            user = ctx_or_interaction.author
            guild_id = ctx_or_interaction.guild.id
            user_id = user.id
            send_method = ctx_or_interaction.send

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

        # Add the instruction at the bottom
        embed.add_field(
            name="‎",
            value="**Choose a setting from the dropdown menu below**",
            inline=False
        )

        view = UserSettingsView(self, guild_id, user_id)

        if is_interaction:
            response = await ctx_or_interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            view.message = await ctx_or_interaction.original_response()
        else:
            msg = await ctx_or_interaction.send(embed=embed, view=view, delete_after=300)
            view.message = msg

    # =========================================================
    # PREFIX COMMAND GROUP
    # =========================================================
    @commands.group(name="settings", invoke_without_command=True)
    async def settings_group_prefix(self, ctx: commands.Context):
        """Configure bot settings for your server via prefix command"""
        await self._handle_settings_command(ctx, is_interaction=False)

    # =========================================================
    # PREFIX COMMAND - SETTINGS SERVER
    # =========================================================
    @settings_group_prefix.command(name="server")
    async def settings_server_prefix(self, ctx: commands.Context):
        """Configure server settings"""
        await self._handle_settings_command(ctx, is_interaction=False)

    # =========================================================
    # PREFIX COMMAND - SETTINGS USER
    # =========================================================
    @settings_group_prefix.command(name="user")
    async def settings_user_prefix(self, ctx: commands.Context):
        """Configure your personal user settings"""
        await self._handle_user_settings_command(ctx, is_interaction=False)

    # =========================================================
    # SHORTCUT COMMAND - SET (SERVER SETTINGS)
    # =========================================================
    @commands.command(name="set")
    async def settings_shortcut(self, ctx: commands.Context):
        """Shortcut command for server settings"""
        await self._handle_settings_command(ctx, is_interaction=False)

    # =========================================================
    # SHORTCUT COMMAND - SETU (USER SETTINGS)
    # =========================================================
    @commands.command(name="setu")
    async def user_settings_shortcut(self, ctx: commands.Context):
        """Shortcut command for user settings"""
        await self._handle_user_settings_command(ctx, is_interaction=False)

    # =========================================================
    # SLASH COMMAND GROUP
    # =========================================================
    settings_group = app_commands.Group(
        name="settings",
        description="Configure bot settings"
    )

    # =========================================================
    # SLASH COMMAND - SETTINGS SERVER
    # =========================================================
    @settings_group.command(name="server", description="Configure bot settings for your server")
    async def settings_server_command(self, interaction: discord.Interaction):
        """Server settings command"""
        await self._handle_settings_command(interaction, is_interaction=True)

    # =========================================================
    # SLASH COMMAND - SETTINGS USER
    # =========================================================
    @settings_group.command(name="user", description="Configure your personal user settings.")
    async def settings_user_command(self, interaction: discord.Interaction):
        """User settings command"""
        await self._handle_user_settings_command(interaction, is_interaction=True)

    @settings_server_command.error
    async def settings_server_command_error(self, interaction: discord.Interaction, error):
        """Handle errors for the server settings command"""
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
        """Handle errors for the user settings command"""
        embed = discord.Embed(
            title="❌ Error",
            description=f"An error occurred: {str(error)}",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def cog_unload(self):
        """Clean up when cog is unloaded"""
        # The cron job will be automatically cleaned up
        pass


# MAIN SETTINGS VIEW
class MainSettingsView(discord.ui.View):
    def __init__(self, cog, guild_id):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.bot = cog.bot

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except:
            pass

    async def check_permission(self, interaction: discord.Interaction) -> bool:
        """Check if user has permission to access settings"""
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
        """Send permission error message"""
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
            discord.SelectOption(
                label="Timezone", value="timezone", description="Change server timezone"),
            discord.SelectOption(label="Voice States", value="voice_states",
                                 description="Configure voice state tracking"),
            discord.SelectOption(label="Bot Filter", value="bot_filter",
                                 description="Filter bots from statistics"),
            discord.SelectOption(label="Command Permission Access Level",
                                 value="permissions", description="Configure command permissions"),
            discord.SelectOption(label="Suspicious Invite Tracking",
                                 value="suspicious_invites", description="Configure suspicious invite detection")
        ]
    )
    async def settings_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        # Check permission
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

    async def show_main_menu(self, interaction: discord.Interaction):
        """Show main settings menu"""
        # Check permission
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return

        embed = discord.Embed(
            title="⚙️ Stats Settings Menu",
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
             "Set minimum account age to detect suspicious invites.")
        ]

        for setting_name, description in settings_list:
            embed.add_field(name=setting_name, value=description, inline=False)

        embed.add_field(
            name="‎",
            value="**Choose a setting from the dropdown menu below**",
            inline=False
        )

        view = MainSettingsView(self.cog, self.guild_id)
        await interaction.edit_original_response(embed=embed, view=view)

    async def show_prefix_menu(self, interaction: discord.Interaction):
        """Show prefix menu with proper response"""
        # Check permission
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return

        settings = await self.cog.get_guild_settings(self.guild_id)
        current_prefix = settings.get('prefix', 's!')

        embed = discord.Embed(
            title="⚙️ Prefix Menu",
            description=f"**This server's current prefix is:** `{current_prefix}`\n\nYou can change the prefix through the change prefix button below. The max limit for a prefix is 10 characters.",
            color=discord.Color.purple()
        )

        view = PrefixView(self.cog, self.guild_id)
        await interaction.edit_original_response(embed=embed, view=view)

    async def show_timezone_menu(self, interaction: discord.Interaction):
        """Show timezone menu with proper response"""
        # Check permission
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return

        settings = await self.cog.get_guild_settings(self.guild_id)
        current_timezone = settings.get('timezone', 'UTC')

        embed = discord.Embed(
            title="🌍 Timezone Menu",
            description=f"**This server's current timezone is:** `{current_timezone}`\n\nYou can change the timezone of the server by choosing from the options in the dropdown menu below.",
            color=discord.Color.purple()
        )

        view = TimezoneView(self.cog, self.guild_id)
        await interaction.edit_original_response(embed=embed, view=view)

    async def show_voice_states_menu(self, interaction: discord.Interaction):
        """Show voice states menu with proper response"""
        # Check permission
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
                "Choose the Voice States that you wish to be tracked in the server's voice activity through the dropdown menu below."
            ),
            color=discord.Color.purple()
        )

        view = VoiceStatesView(self.cog, self.guild_id, current_states)
        await interaction.edit_original_response(embed=embed, view=view)

    async def show_bot_filter_menu(self, interaction: discord.Interaction):
        """Show bot filter menu with proper response"""
        # Check permission
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return

        settings = await self.cog.get_guild_settings(self.guild_id)
        bot_filter = settings.get('bot_filter', False)

        status = "filtered out from" if bot_filter else "included in"
        button_text = "Include Bots" if bot_filter else "Filter Bots"

        embed = discord.Embed(
            title="🤖 Bot Filter Menu",
            description=f"**Bots are currently {status} statistics.**\n\n"
            f"You can {'include bots in' if bot_filter else 'filter out bots from'} statistics "
            f"through the **\"{button_text}\"** button below.",
            color=discord.Color.purple()
        )

        view = BotFilterView(self.cog, self.guild_id, bot_filter)
        await interaction.edit_original_response(embed=embed, view=view)

    async def show_permissions_menu(self, interaction: discord.Interaction):
        """Show permissions menu with proper response"""
        # Check permission
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
                "`All` - All members regardless of their permissions are allowed to use any command on the bot including sensitive commands like reset and blacklist.\n\n"
                "`Default` - The default access level that restricts or enables specific commands for users with specific permissions. All commands on the bot are usable by normal members except for blacklist and settings being accessible via manage server, and reset commands being accessible via administrator permissions.\n\n"
                "`User Restriction` - Mostly the same as Default except users can only use commands that have the user scope on their own account only.\n\n"
                "`Admin` - Only users with the administrator permission can use any commands on the bot.\n\n"
                "`Moderator` - Only users with the Manage Server permission can use any commands on the bot.\n\n"
                "You can change the permission level through the dropdown menu below."
            ),
            color=discord.Color.purple()
        )

        view = PermissionsView(self.cog, self.guild_id)
        await interaction.edit_original_response(embed=embed, view=view)

    async def show_suspicious_invites_menu(self, interaction: discord.Interaction):
        """Show suspicious invites menu with modal input"""
        # Check permission
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return

        settings = await self.cog.get_guild_settings(self.guild_id)
        current_days = settings.get('min_account_age_days', 3)

        embed = discord.Embed(
            title="⚠️ Suspicious Invite Tracking Menu",
            description=(
                "**What are Suspicious Invites?**\n\n"
                "Suspicious invites are detected when **either** the person inviting **OR** the person joining has an account that is too new.\n\n"
                "This helps protect your server from:\n"
                "• Raids using newly created accounts\n"
                "• Bot accounts joining via compromised invites\n"
                "• Invite spam from fresh accounts\n\n"
                f"**Current Setting:** `{current_days} day(s)`\n\n"
                "If an account is younger than this many days, any invite they send or use will be marked as **suspicious**.\n\n"
                "Set to `0` to disable suspicious invite detection entirely.\n\n"
                "**Click the button below to change this value.**"
            ),
            color=discord.Color.purple()
        )

        view = SuspiciousInvitesView(self.cog, self.guild_id, current_days)
        await interaction.edit_original_response(embed=embed, view=view)


# USER SETTINGS VIEW
class UserSettingsView(discord.ui.View):
    def __init__(self, cog, guild_id, user_id):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        self.bot = cog.bot

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except:
            pass

    @discord.ui.select(
        placeholder="Select a setting to configure...",
        options=[
            discord.SelectOption(label="Privacy Mode", value="privacy",
                                 description="Control your data privacy settings for this server")
        ]
    )
    async def user_settings_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        # Only allow the user who ran the command to interact
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
        """Show main user settings menu"""
        # Only allow the user who ran the command to interact
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
            name="‎",
            value="**Choose a setting from the dropdown menu below**",
            inline=False
        )

        view = UserSettingsView(self.cog, self.guild_id, self.user_id)
        await interaction.edit_original_response(embed=embed, view=view)

    async def show_privacy_menu(self, interaction: discord.Interaction):
        """Show privacy settings menu"""
        # Only allow the user who ran the command to interact
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


# PRIVACY VIEW
class PrivacyView(discord.ui.View):
    def __init__(self, cog, guild_id, user_id, privacy_enabled):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        self.bot = cog.bot
        self.privacy_enabled = privacy_enabled

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except:
            pass

    @discord.ui.button(label="Toggle Privacy Mode", style=discord.ButtonStyle.primary, emoji="🔒", row=0)
    async def toggle_privacy_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Only allow the user who ran the command to interact
        if interaction.user.id != self.user_id:
            embed = discord.Embed(
                title="❌ Permission Denied",
                description="You cannot change another user's privacy settings!",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer()

        # Toggle the privacy setting
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

            # Wait 2 seconds then show updated menu
            await asyncio.sleep(2)

            # Update the original message
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
            await interaction.followup.send("❌ Failed to update privacy settings. Please try again.", ephemeral=True)

    @discord.ui.button(label="↩ Back", style=discord.ButtonStyle.secondary, row=1)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Only allow the user who ran the command to interact
        if interaction.user.id != self.user_id:
            embed = discord.Embed(
                title="❌ Permission Denied",
                description="You cannot change another user's privacy settings!",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer()
        # Go back to main user settings menu
        view = UserSettingsView(self.cog, self.guild_id, self.user_id)
        await view.show_main_menu(interaction)


# PREFIX VIEW
class PrefixView(discord.ui.View):
    def __init__(self, cog, guild_id):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.bot = cog.bot

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except:
            pass

    async def check_permission(self, interaction: discord.Interaction) -> bool:
        """Check if user has permission to access settings"""
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
        """Send permission error message"""
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
        # Check permission
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return

        modal = PrefixModal(self.cog, self.guild_id, self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="↩ Back", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check permission
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return

        await interaction.response.defer()
        # Go back to main settings menu
        view = MainSettingsView(self.cog, self.guild_id)
        await view.show_main_menu(interaction)

    async def show_main_menu(self, interaction: discord.Interaction, view):
        """Helper to show main menu"""
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
            ("`Command Permission Access Levels`",
             "Choose from the 5 levels of permission access."),
            ("`Suspicious Invite Tracking`",
             "Set minimum account age to detect suspicious invites.")
        ]

        for setting_name, description in settings_list:
            embed.add_field(name=setting_name, value=description, inline=False)

        embed.add_field(
            name="‎",
            value="**Choose a setting from the dropdown menu below**",
            inline=False
        )

        await interaction.edit_original_response(embed=embed, view=view)


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
        # Check permission
        if not await self.parent_view.check_permission(interaction):
            await self.parent_view.send_permission_error(interaction)
            return

        await interaction.response.defer()

        new_prefix = self.prefix_input.value.strip()
        success = await self.cog.update_setting(self.guild_id, 'prefix', new_prefix)

        if success:
            # Show success message
            await interaction.followup.send(f"✅ Prefix has been changed to: `{new_prefix}`", ephemeral=True)

            # Wait 2 seconds then show updated menu
            await asyncio.sleep(2)

            # Get updated settings
            settings = await self.cog.get_guild_settings(self.guild_id)
            current_prefix = settings.get('prefix', 's!')

            # Update the original message
            embed = discord.Embed(
                title="⚙️ Prefix Menu",
                description=f"**This server's current prefix is:** `{current_prefix}`\n\nYou can change the prefix through the change prefix button below. The max limit for a prefix is 10 characters.",
                color=discord.Color.purple()
            )

            view = PrefixView(self.cog, self.guild_id)
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.followup.send("❌ Failed to update prefix. Please try again.", ephemeral=True)


# TIMEZONE VIEW
class TimezoneView(discord.ui.View):
    def __init__(self, cog, guild_id):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.bot = cog.bot
        self.selected_timezone = None

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except:
            pass

    async def check_permission(self, interaction: discord.Interaction) -> bool:
        """Check if user has permission to access settings"""
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
        """Send permission error message"""
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
                label="NZST (GMT+12)", value="NZST", description="New Zealand Standard Time")
        ]
    )
    async def timezone_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        # Check permission
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return

        await interaction.response.defer()
        # Store the selected value and enable Apply button
        self.selected_timezone = select.values[0]
        self.children[1].disabled = False  # Enable the Apply button

        # Update the select placeholder to show selected timezone
        select.placeholder = f"Selected: {self.selected_timezone}"

        # Update the view
        await interaction.edit_original_response(view=self)

    @discord.ui.button(label="Apply Changes", style=discord.ButtonStyle.success, disabled=True, row=1)
    async def apply_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check permission
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
            # Show success message
            await interaction.followup.send(f"✅ Timezone has been changed to: `{selected_timezone}`", ephemeral=True)

            # Wait 2 seconds then show updated menu
            await asyncio.sleep(2)

            # Get updated settings
            settings = await self.cog.get_guild_settings(self.guild_id)
            current_timezone = settings.get('timezone', 'UTC')

            # Update the original message
            embed = discord.Embed(
                title="🌍 Timezone Menu",
                description=f"**This server's current timezone is:** `{current_timezone}`\n\nYou can change the timezone of the server by choosing from the options in the dropdown menu below.",
                color=discord.Color.purple()
            )

            # Reset the view with updated placeholder
            view = TimezoneView(self.cog, self.guild_id)
            # Set placeholder to show current timezone
            view.children[0].placeholder = f"Selected: {current_timezone}"
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.followup.send("❌ Failed to update timezone. Please try again.", ephemeral=True)

    @discord.ui.button(label="↩ Back", style=discord.ButtonStyle.secondary, row=1)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check permission
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return

        await interaction.response.defer()
        # Go back to main settings menu
        view = MainSettingsView(self.cog, self.guild_id)
        await view.show_main_menu(interaction)


# VOICE STATES VIEW
class VoiceStatesView(discord.ui.View):
    def __init__(self, cog, guild_id, current_states=None):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.bot = cog.bot

        # Initialize with current states or empty list
        if current_states is None:
            current_states = []
        self.selected_states = current_states.copy()

        # Create select menu with proper defaults
        self.update_select_menu()

    def update_select_menu(self):
        """Update the select menu to show current selections"""
        # Clear existing children
        self.clear_items()

        # Voice state options with defaults
        voice_state_options = [
            discord.SelectOption(label="Afk", value="afk",
                                 description="User is in AFK channel",
                                 default="afk" in self.selected_states),
            discord.SelectOption(label="Self Mute", value="self_mute",
                                 description="User muted themselves",
                                 default="self_mute" in self.selected_states),
            discord.SelectOption(label="Self Deafen", value="self_deafen",
                                 description="User deafened themselves",
                                 default="self_deafen" in self.selected_states),
            discord.SelectOption(label="Server Mute", value="server_mute",
                                 description="User was muted by moderation",
                                 default="server_mute" in self.selected_states),
            discord.SelectOption(label="Server Deafen", value="server_deafen",
                                 description="User was deafened by moderation",
                                 default="server_deafen" in self.selected_states),
            discord.SelectOption(label="Streaming", value="streaming",
                                 description="User is streaming",
                                 default="streaming" in self.selected_states),
            discord.SelectOption(label="Video", value="video",
                                 description="User has video open",
                                 default="video" in self.selected_states),
            discord.SelectOption(label="Suppressed", value="suppressed",
                                 description="Stage audience member",
                                 default="suppressed" in self.selected_states)
        ]

        # Create the select menu
        select_menu = discord.ui.Select(
            placeholder="Select voice states to track...",
            options=voice_state_options,
            max_values=8
        )

        # Set the callback
        select_menu.callback = self.voice_states_select_callback

        # Add the select menu back
        self.add_item(select_menu)

        # Add Apply button (enabled if there are changes)
        apply_button = discord.ui.Button(
            label="Apply Changes",
            style=discord.ButtonStyle.success,
            # Disable if no states selected
            disabled=len(self.selected_states) == 0,
            row=1
        )
        apply_button.callback = self.apply_button_callback
        self.add_item(apply_button)

        # Add Back button
        back_button = discord.ui.Button(
            label="↩ Back",
            style=discord.ButtonStyle.secondary,
            row=1
        )
        back_button.callback = self.back_button_callback
        self.add_item(back_button)

        # Update placeholder based on current selections
        if self.selected_states:
            count = len(self.selected_states)
            self.children[0].placeholder = f"Selected {count} state{'s' if count != 1 else ''}"

    async def check_permission(self, interaction: discord.Interaction) -> bool:
        """Check if user has permission to access settings"""
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
        """Send permission error message"""
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

    async def voice_states_select_callback(self, interaction: discord.Interaction):
        # Check permission
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return

        await interaction.response.defer()

        # Update selected states from the select menu
        self.selected_states = self.children[0].values

        # Enable the Apply button
        self.children[1].disabled = len(self.selected_states) == 0

        # Update the select placeholder to show count
        if self.selected_states:
            count = len(self.selected_states)
            self.children[0].placeholder = f"Selected {count} state{'s' if count != 1 else ''}"
        else:
            self.children[0].placeholder = "Select voice states to track..."

        # Update the embed to show selected states
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
            "Choose the Voice States that you wish to be tracked in the server's voice activity through the dropdown menu above."
        )

        await interaction.edit_original_response(embed=embed, view=self)

    async def apply_button_callback(self, interaction: discord.Interaction):
        # Check permission
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return

        await interaction.response.defer()

        if not self.selected_states:
            await interaction.followup.send("Please select at least one voice state!", ephemeral=True)
            return

        success = await self.cog.update_setting(self.guild_id, 'voice_states', self.selected_states)

        if success:
            # Show success message
            await interaction.followup.send(f"✅ Voice states updated! Now tracking: {', '.join(self.selected_states)}", ephemeral=True)

            # Wait 2 seconds then show updated menu
            await asyncio.sleep(2)

            # Get updated settings
            settings = await self.cog.get_guild_settings(self.guild_id)
            current_states = settings.get('voice_states', [])

            # Update the original message
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
                    "Choose the Voice States that you wish to be tracked in the server's voice activity through the dropdown menu below."
                ),
                color=discord.Color.purple()
            )

            # Reset the view with updated selections
            view = VoiceStatesView(self.cog, self.guild_id, current_states)
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.followup.send("❌ Failed to update voice states. Please try again.", ephemeral=True)

    async def back_button_callback(self, interaction: discord.Interaction):
        # Check permission
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return

        await interaction.response.defer()
        # Go back to main settings menu
        view = MainSettingsView(self.cog, self.guild_id)
        await view.show_main_menu(interaction)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except:
            pass


# BOT FILTER VIEW
class BotFilterView(discord.ui.View):
    def __init__(self, cog, guild_id, bot_filter_enabled):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.bot = cog.bot
        self.bot_filter_enabled = bot_filter_enabled

        # Only show one button based on current setting
        if bot_filter_enabled:
            # Bots are filtered, show "Include Bots" button
            self.add_item(IncludeBotsButton())
        else:
            # Bots are included, show "Filter Bots" button
            self.add_item(FilterBotsButton())

        # Add back button
        self.add_item(BackButton())

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except:
            pass

    async def check_permission(self, interaction: discord.Interaction) -> bool:
        """Check if user has permission to access settings"""
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
        """Send permission error message"""
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
        # Check permission
        if not await self.view.check_permission(interaction):
            await self.view.send_permission_error(interaction)
            return

        await interaction.response.defer()

        cog = self.view.cog
        guild_id = self.view.guild_id

        success = await cog.update_setting(guild_id, 'bot_filter', True)

        if success:
            await interaction.followup.send("✅ Bots are now **filtered out** from statistics.", ephemeral=True)

            # Wait 2 seconds then show updated menu
            await asyncio.sleep(2)

            # Get updated settings
            settings = await cog.get_guild_settings(guild_id)
            bot_filter = settings.get('bot_filter', False)

            status = "filtered out from" if bot_filter else "included in"
            button_text = "Include Bots" if bot_filter else "Filter Bots"

            # Update the original message
            embed = discord.Embed(
                title="🤖 Bot Filter Menu",
                description=f"**Bots are currently {status} statistics.**\n\n"
                f"You can {'include bots in' if bot_filter else 'filter out bots from'} statistics "
                f"through the **\"{button_text}\"** button below.",
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
        # Check permission
        if not await self.view.check_permission(interaction):
            await self.view.send_permission_error(interaction)
            return

        await interaction.response.defer()

        cog = self.view.cog
        guild_id = self.view.guild_id

        success = await cog.update_setting(guild_id, 'bot_filter', False)

        if success:
            await interaction.followup.send("✅ Bots are now **included** in statistics.", ephemeral=True)

            # Wait 2 seconds then show updated menu
            await asyncio.sleep(2)

            # Get updated settings
            settings = await cog.get_guild_settings(guild_id)
            bot_filter = settings.get('bot_filter', False)

            status = "filtered out from" if bot_filter else "included in"
            button_text = "Include Bots" if bot_filter else "Filter Bots"

            # Update the original message
            embed = discord.Embed(
                title="🤖 Bot Filter Menu",
                description=f"**Bots are currently {status} statistics.**\n\n"
                f"You can {'include bots in' if bot_filter else 'filter out bots from'} statistics "
                f"through the **\"{button_text}\"** button below.",
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
        # Check permission
        if not await self.view.check_permission(interaction):
            await self.view.send_permission_error(interaction)
            return

        await interaction.response.defer()
        # Go back to main settings menu
        view = MainSettingsView(self.view.cog, self.view.guild_id)
        await view.show_main_menu(interaction)


# PERMISSIONS VIEW
class PermissionsView(discord.ui.View):
    def __init__(self, cog, guild_id):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.bot = cog.bot
        self.selected_level = None

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except:
            pass

    async def check_permission(self, interaction: discord.Interaction) -> bool:
        """Check if user has permission to access settings"""
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
        """Send permission error message"""
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
            discord.SelectOption(
                label="Default", value="Default", description="Default access level"),
            discord.SelectOption(label="User Restriction", value="User Restriction",
                                 description="Users can only use commands on themselves"),
            discord.SelectOption(label="Admin", value="Admin",
                                 description="Only administrators can use commands"),
            discord.SelectOption(label="Moderator", value="Moderator",
                                 description="Only users with Manage Server permission")
        ]
    )
    async def permissions_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        # Check permission
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return

        await interaction.response.defer()
        # Store selected level and enable Apply button
        self.selected_level = select.values[0]
        self.children[1].disabled = False  # Enable the Apply button

        # Update the select placeholder to show selected level
        select.placeholder = f"Selected: {self.selected_level}"

        # Update the view
        await interaction.edit_original_response(view=self)

    @discord.ui.button(label="Apply Changes", style=discord.ButtonStyle.success, disabled=True, row=1)
    async def apply_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check permission
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
            # Show success message
            await interaction.followup.send(f"✅ Permission level has been changed to: `{selected_level}`", ephemeral=True)

            # Wait 2 seconds then show updated menu
            await asyncio.sleep(2)

            # Get updated settings
            settings = await self.cog.get_guild_settings(self.guild_id)
            current_level = settings.get('permission_level', 'Default')

            # Update the original message
            embed = discord.Embed(
                title="🔐 Command Permission Access Levels Menu",
                description=(
                    f"**This server's permission level is currently set to:** `{current_level}`\n\n"
                    "**Permission Levels:**\n\n"
                    "`All` - All members regardless of their permissions are allowed to use any command on the bot.\n\n"
                    "`Default` - The default access level that restricts or enables specific commands for users with specific permissions.\n\n"
                    "`User Restriction` - Same as Default except users can only use user commands on their own account.\n\n"
                    "`Admin` - Only users with the administrator permission can use any commands on the bot.\n\n"
                    "`Moderator` - Only users with the Manage Server permission can use any commands on the bot.\n\n"
                    "You can change the permission level through the dropdown menu below."
                ),
                color=discord.Color.purple()
            )

            # Reset the view with updated placeholder
            view = PermissionsView(self.cog, self.guild_id)
            # Set placeholder to show current permission level
            view.children[0].placeholder = f"Selected: {current_level}"
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.followup.send("❌ Failed to update permission level. Please try again.", ephemeral=True)

    @discord.ui.button(label="↩ Back", style=discord.ButtonStyle.secondary, row=1)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check permission
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return

        await interaction.response.defer()
        # Go back to main settings menu
        view = MainSettingsView(self.cog, self.guild_id)
        await view.show_main_menu(interaction)


# SUSPICIOUS INVITES VIEW - USING MODAL INSTEAD OF DROPDOWN
class SuspiciousInvitesView(discord.ui.View):
    def __init__(self, cog, guild_id, current_days):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.bot = cog.bot
        self.current_days = current_days

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except:
            pass

    async def check_permission(self, interaction: discord.Interaction) -> bool:
        """Check if user has permission to access settings"""
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
        """Send permission error message"""
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

    @discord.ui.button(label="Change Minimum Account Age", style=discord.ButtonStyle.primary, emoji="⚠️", row=0)
    async def change_age_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check permission
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return

        modal = SuspiciousInvitesModal(
            self.cog, self.guild_id, self.current_days, self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="↩ Back", style=discord.ButtonStyle.secondary, row=1)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check permission
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return

        await interaction.response.defer()
        # Go back to main settings menu
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
        # Check permission
        if not await self.parent_view.check_permission(interaction):
            await self.parent_view.send_permission_error(interaction)
            return

        await interaction.response.defer()

        try:
            days = int(self.days_input.value.strip())

            if days < 0:
                await interaction.followup.send("❌ Days cannot be negative! Please enter 0 or a positive number.", ephemeral=True)
                return

            if days > 365:
                await interaction.followup.send("❌ Days cannot exceed 365! Please enter a number between 0 and 365.", ephemeral=True)
                return

        except ValueError:
            await interaction.followup.send("❌ Please enter a valid number!", ephemeral=True)
            return

        success = await self.cog.update_setting(self.guild_id, 'min_account_age_days', days)

        if success:
            if days == 0:
                await interaction.followup.send("✅ Suspicious invite detection has been **disabled**. No invites will be marked as suspicious.", ephemeral=True)
            else:
                await interaction.followup.send(f"✅ Minimum account age set to **{days} day{'s' if days != 1 else ''}**. Invites will be marked as suspicious if either the inviter or new member has an account younger than this.", ephemeral=True)

            # Wait 2 seconds then show updated menu
            await asyncio.sleep(2)

            # Get updated settings
            settings = await self.cog.get_guild_settings(self.guild_id)
            current_days = settings.get('min_account_age_days', 3)

            # Update the original message
            embed = discord.Embed(
                title="⚠️ Suspicious Invite Tracking Menu",
                description=(
                    "**What are Suspicious Invites?**\n\n"
                    "Suspicious invites are detected when **either** the person inviting **OR** the person joining has an account that is too new.\n\n"
                    "This helps protect your server from:\n"
                    "• Raids using newly created accounts\n"
                    "• Bot accounts joining via compromised invites\n"
                    "• Invite spam from fresh accounts\n\n"
                    f"**Current Setting:** `{current_days} day{'s' if current_days != 1 else ''}`\n\n"
                    "If an account is younger than this many days, any invite they send or use will be marked as **suspicious**.\n\n"
                    "Set to `0` to disable suspicious invite detection entirely.\n\n"
                    "**Click the button below to change this value.**"
                ),
                color=discord.Color.purple()
            )

            # Reset the view with updated current days
            view = SuspiciousInvitesView(self.cog, self.guild_id, current_days)
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.followup.send("❌ Failed to update suspicious invite settings. Please try again.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Settings(bot))
