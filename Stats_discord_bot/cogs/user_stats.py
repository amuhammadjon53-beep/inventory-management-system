import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
import aiohttp
import io
from PIL import Image, ImageDraw, ImageFont
from pilmoji import Pilmoji
from pilmoji.source import AppleEmojiSource
import os
import asyncio
import traceback
import time
import logging
from pathlib import Path
from zoneinfo import ZoneInfo
import datetime as dt
from datetime import datetime, timedelta, date, timezone
from .ratelimiter import RateLimiter, RateLimitType, rate_limited, get_rate_limiter
import gc

BASE_DIR = Path(__file__).resolve().parent.parent

logger = logging.getLogger(__name__)


def ensure_aware(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# TEXT CENTERING

def draw_text_centered(pilmoji_instance, text, position, font, fill, max_width=None):
    draw = pilmoji_instance.draw
    center_x, center_y = position
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = center_x - (text_width // 2)
    y = center_y - (text_height // 2)

    if max_width and text_width > max_width:
        while text_width > max_width and len(text) > 1:
            text = text[:-1]
            bbox = draw.textbbox((0, 0), text + "...", font=font)
            text_width = bbox[2] - bbox[0]
        text = text + "..."

    pilmoji_instance.text((x, y), text, fill=fill, font=font)

# FORMATTING


def format_voice_time(total_seconds):
    if total_seconds < 60:
        return f"{int(total_seconds)}s"
    elif total_seconds < 3600:
        minutes = int(total_seconds // 60)
        seconds = int(total_seconds % 60)
        return f"{minutes}m {seconds}s"
    elif total_seconds < 86400:
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        return f"{hours}h {minutes}m"
    else:
        days = int(total_seconds // 86400)
        hours = int((total_seconds % 86400) // 3600)
        return f"{days}d {hours}h"


def format_voice_hours_per_hour(voice_hours_per_hour):
    seconds_per_hour = voice_hours_per_hour * 3600

    if seconds_per_hour < 60:
        return f"{seconds_per_hour:.2f}s"
    else:
        time_str = format_voice_time(seconds_per_hour)
        return f"{time_str}"


# UNICODE NORMALIZATION

def normalize_text(text):
    import unicodedata
    normalized = unicodedata.normalize('NFKD', str(text))
    ascii_only = normalized.encode('ascii', 'ignore').decode('ascii')
    return ascii_only if ascii_only else text


# TIME MODAL

class UserStatsTimeModal(discord.ui.Modal, title='Custom Time Period'):
    def __init__(self, cog_instance, guild, member):
        super().__init__(timeout=300)
        self.cog = cog_instance
        self.guild = guild
        self.member = member

    days = discord.ui.TextInput(
        label='Enter number of days (1-2000)',
        placeholder='e.g., 7, 14, 30, 90, 365...',
        min_length=1,
        max_length=4,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            days = int(self.days.value)
            if days <= 0 or days > 2000:
                await interaction.response.send_message("❌ Please enter a number between 1 and 2000 days.", ephemeral=True)
                return

            await interaction.response.defer()

            # Check if user has permission to view this member's stats
            permission_error = await self.cog.check_user_permission(interaction.user, self.member, self.guild)
            if permission_error:
                await interaction.followup.send(embed=permission_error, ephemeral=True)
                return

            blacklist_error = await self.cog.check_blacklist_and_get_error(self.guild, self.member)
            if blacklist_error:
                await interaction.followup.send(blacklist_error, ephemeral=True)
                return

            # For custom days, we use days_back mode
            start_time = datetime.utcnow() - timedelta(days=days)
            end_time = datetime.utcnow()
            display_text = f"{days} days"
            days_back_equiv = days

            image_buffer = await self.cog._generate_user_stats_image(self.guild, self.member, start_time=start_time, end_time=end_time, display_text=display_text, days_back_equiv=days_back_equiv)

            view = UserStatsView(self.cog, self.guild,
                                 self.member, start_time=start_time, end_time=end_time, display_text=display_text, days_back_equiv=days_back_equiv)
            file = discord.File(image_buffer, filename="user_stats.png")

            await interaction.edit_original_response(attachments=[file], view=view)

        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in user stats modal submit: {e}")
            await interaction.followup.send("❌ An error occurred while updating stats.", ephemeral=True)


# MAIN VIEW

class UserStatsView(discord.ui.View):
    def __init__(self, cog_instance, guild: discord.Guild, member: discord.Member, start_time: datetime = None, end_time: datetime = None, display_text: str = None, days_back_equiv: int = None):
        super().__init__(timeout=600)
        self.cog = cog_instance
        self.guild = guild
        self.member = member
        self.current_start_time = start_time
        self.current_end_time = end_time
        self.current_display_text = display_text
        self.current_days_back_equiv = days_back_equiv
        self.show_time_buttons = False
        self.using_server_default = (
            start_time is None and end_time is None and display_text is None and days_back_equiv is None)
        self._update_buttons()

    # BUTTON LOGIC

    def _update_buttons(self):
        self.clear_items()

        refresh_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="🔄 Refresh",
            custom_id="user_stats_refresh",
            row=0
        )
        refresh_button.callback = self.refresh_callback
        self.add_item(refresh_button)

        time_settings_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="⏰ Time Settings",
            custom_id="user_stats_time_settings",
            row=0
        )
        time_settings_button.callback = self.time_settings_callback
        self.add_item(time_settings_button)

        if self.show_time_buttons:
            all_time_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 999999 else discord.ButtonStyle.secondary,
                label="All Time",
                custom_id="user_stats_all_time",
                row=1
            )
            all_time_button.callback = self.all_time_callback
            self.add_item(all_time_button)

            days_7_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 7 else discord.ButtonStyle.secondary,
                label="7 Days",
                custom_id="user_stats_days_7",
                row=1
            )
            days_7_button.callback = self.days_7_callback
            self.add_item(days_7_button)

            days_14_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 14 else discord.ButtonStyle.secondary,
                label="14 Days",
                custom_id="user_stats_days_14",
                row=1
            )
            days_14_button.callback = self.days_14_callback
            self.add_item(days_14_button)

            days_30_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 30 else discord.ButtonStyle.secondary,
                label="30 Days",
                custom_id="user_stats_days_30",
                row=1
            )
            days_30_button.callback = self.days_30_callback
            self.add_item(days_30_button)

            custom_button = discord.ui.Button(
                style=discord.ButtonStyle.success,
                label=f"Custom ({self.current_days_back_equiv}d)" if self.current_days_back_equiv not in [
                    7, 14, 30, 999999] else "Custom",
                custom_id="user_stats_custom_days",
                row=1
            )
            custom_button.callback = self.custom_days_callback
            self.add_item(custom_button)

    async def refresh_callback(self, interaction: discord.Interaction):
        await self.handle_button_click(interaction, refresh=True)

    async def time_settings_callback(self, interaction: discord.Interaction):
        try:
            self.show_time_buttons = not self.show_time_buttons
            self._update_buttons()
            await interaction.response.edit_message(view=self)
        except Exception as e:
            logger.error(f"Error handling time settings: {e}")
            await interaction.response.send_message("❌ An error occurred while updating time settings.", ephemeral=True)

    async def all_time_callback(self, interaction: discord.Interaction):
        await self.handle_button_click(interaction, days_back_equiv=999999, start_time=None, end_time=datetime.utcnow(), display_text="All Time")

    async def days_7_callback(self, interaction: discord.Interaction):
        now = datetime.utcnow()
        await self.handle_button_click(interaction, days_back_equiv=7, start_time=now - timedelta(days=7), end_time=now, display_text="7 days")

    async def days_14_callback(self, interaction: discord.Interaction):
        now = datetime.utcnow()
        await self.handle_button_click(interaction, days_back_equiv=14, start_time=now - timedelta(days=14), end_time=now, display_text="14 days")

    async def days_30_callback(self, interaction: discord.Interaction):
        now = datetime.utcnow()
        await self.handle_button_click(interaction, days_back_equiv=30, start_time=now - timedelta(days=30), end_time=now, display_text="30 days")

    async def custom_days_callback(self, interaction: discord.Interaction):
        modal = UserStatsTimeModal(self.cog, self.guild, self.member)
        await interaction.response.send_modal(modal)

    async def handle_button_click(self, interaction: discord.Interaction, refresh: bool = False, start_time: datetime = None, end_time: datetime = None, display_text: str = None, days_back_equiv: int = None):
        try:
            await interaction.response.defer()

            if start_time is not None:
                self.current_start_time = start_time
                self.current_end_time = end_time
                self.current_display_text = display_text
                self.current_days_back_equiv = days_back_equiv
                self.using_server_default = False
                self.show_time_buttons = False

            # Check if user has permission to view this member's stats
            permission_error = await self.cog.check_user_permission(interaction.user, self.member, self.guild)
            if permission_error:
                await interaction.followup.send(embed=permission_error, ephemeral=True)
                try:
                    await interaction.message.delete()
                except:
                    pass
                return

            blacklist_error = await self.cog.check_blacklist_and_get_error(self.guild, self.member)
            if blacklist_error:
                await interaction.followup.send(blacklist_error, ephemeral=True)
                try:
                    await interaction.message.delete()
                except:
                    pass
                return

            image_buffer = await self.cog._generate_user_stats_image(self.guild, self.member, self.current_start_time if not self.using_server_default else None, self.current_end_time if not self.using_server_default else None, self.current_display_text if not self.using_server_default else None, self.current_days_back_equiv if not self.using_server_default else None)

            self._update_buttons()
            file = discord.File(image_buffer, filename="user_stats.png")
            await interaction.edit_original_response(attachments=[file], view=self)

        except Exception as e:
            logger.error(f"Error handling button click: {e}")
            await interaction.followup.send("❌ An error occurred while updating the stats.", ephemeral=True)


# INITIALIZATION

class UserStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_user_stats_sessions = {}
        self.emoji_source = AppleEmojiSource
        self.rate_limiter = get_rate_limiter()

    user_group = app_commands.Group(
        name="user",
        description="User statistics commands"
    )

    # PERMISSION CHECKING

    async def check_user_permission(self, user: discord.Member, target_member: discord.Member, guild: discord.Guild) -> discord.Embed:
        """
        Check if user has permission to view target member's stats
        Returns None if allowed, error embed if not allowed
        """
        try:
            # Get settings cog
            settings_cog = self.bot.get_cog('Settings')
            if not settings_cog:
                # If settings cog not available, use default permissions
                return None

            # Get guild settings
            settings = await settings_cog.get_guild_settings(guild.id)
            permission_level = settings.get('permission_level', 'Default')

            # Always allow if user has administrator permission
            if user.guild_permissions.administrator:
                return None

            # Check based on permission level
            if permission_level == 'All':
                # All users can view anyone's stats
                return None

            elif permission_level == 'Default':
                # Default - anyone can view anyone's stats
                return None

            elif permission_level == 'User Restriction':
                # User can only view their own stats
                if user.id != target_member.id:
                    embed = discord.Embed(
                        title="❌ Permission Denied",
                        description="Sorry! You can only use this command on yourself.",
                        color=discord.Color.red()
                    )
                    return embed
                return None

            elif permission_level == 'Admin':
                # Only administrators can use the command
                embed = discord.Embed(
                    title="❌ Permission Denied",
                    description="Sorry! You need the `Administrator` permission to access this command.",
                    color=discord.Color.red()
                )
                return embed

            elif permission_level == 'Moderator':
                # Only users with Manage Server permission can use the command
                if not user.guild_permissions.manage_guild:
                    embed = discord.Embed(
                        title="❌ Permission Denied",
                        description="Sorry! You need the `Manage Server` permission to access this command.",
                        color=discord.Color.red()
                    )
                    return embed
                return None

            # Default fallback
            return None

        except Exception as e:
            logger.error(f"Error checking user permission: {e}")
            # On error, allow access
            return None

    # ERROR HANDLING

    async def check_blacklist_and_get_error(self, guild: discord.Guild, member: discord.Member) -> str:
        try:
            db_cog = self.bot.get_cog('DatabaseStats')
            if not db_cog:
                return "❌ Database system not available."

            guild_id = guild.id

            if await db_cog.is_user_or_roles_blacklisted(guild_id, member.id):
                return "❌ This user is blacklisted from statistics tracking."

            return None
        except Exception as e:
            logger.error(f"Error checking blacklist: {e}")
            return "❌ Error checking blacklist status."

    # NEW METHOD: GET SERVER DEFAULT TIME RANGE
    async def get_server_default_time_range(self, guild: discord.Guild) -> tuple:
        try:
            settings_cog = self.bot.get_cog('Settings')
            if not settings_cog:
                end = datetime.utcnow()
                start = end - timedelta(days=14)
                return (start, end, "14 days", 14)

            settings = await settings_cog.get_guild_settings(guild.id)
            mode = settings.get('default_time_mode', 'days_back')
            now = datetime.now(timezone.utc)  # ← MAKE THIS AWARE

            if mode == 'all_time':
                return (None, now, "All Time", 999999)

            elif mode == 'days_back':
                days = settings.get('default_days_back') or 14
                start = now - timedelta(days=days)
                return (start, now, f"{days} days", days)

            elif mode == 'date_range':
                from_date = settings.get('default_from_date')
                to_date = settings.get('default_to_date')

                # Ensure both are timezone-aware
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
                    display = f"Custom"
                    return (start, now, display, days_back)

                # rolling_window configured but type/value missing — fall through to default
                end = now
                start = now - timedelta(days=14)
                return (start, end, "14 days", 14)

            # Unknown mode fallback
            end = now
            start = now - timedelta(days=14)
            return (start, end, "14 days", 14)

        except Exception as e:
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=14)
            return (start, end, "14 days", 14)

    # QUERY FUNCTIONS

    async def get_channel_name(self, guild: discord.Guild, channel_id: int) -> str:
        try:
            db_cog = self.bot.get_cog('DatabaseStats')
            if not db_cog:
                if not guild:
                    return f"#{channel_id}"

                channel = guild.get_channel(channel_id)
                if channel:
                    name = channel.name
                    name = normalize_text(name)
                    if len(name) > 12:
                        name = name[:10] + ".."
                    return f"#{name}"
                return f"#{channel_id}"

            display_name = db_cog._get_channel_display_name(
                guild.id, channel_id, 'channel')

            if display_name.startswith('#'):
                display_name = display_name[1:]

            display_name = normalize_text(display_name)

            if len(display_name) > 12:
                display_name = display_name[:10] + ".."

            return f"#{display_name}"

        except Exception as e:
            logger.error(f"Error getting channel name: {e}")
            return f"#{channel_id}"

    async def _get_user_stats_data(self, guild: discord.Guild, member: discord.Member, start_time: datetime = None, end_time: datetime = None, days_back_equiv: int = 14):
        blacklist_error = await self.check_blacklist_and_get_error(guild, member)
        if blacklist_error:
            return {"error": blacklist_error}

        db_cog = self.bot.get_cog('DatabaseStats')
        if not db_cog:
            return {"error": "Database system not available."}

        max_wait = 30
        wait_time = 0
        wait_interval = 0.5

        while not db_cog.db_connected and wait_time < max_wait:
            await asyncio.sleep(wait_interval)
            wait_time += wait_interval

        if not db_cog.db_connected:
            return {"error": "Database not connected. Please try again in a moment."}

        if not db_cog.pool:
            return {"error": "Database pool not available."}

        try:
            # For "All Time" (start_time is None)
            use_all_time = (start_time is None)

            # If end_time is not provided, use current time
            if end_time is None:
                end_time = datetime.utcnow()

            # Initialize variables with default values
            message_rank = 0
            voice_rank = 0
            total_message_users = 0
            total_voice_users = 0
            global_first_seen = None
            global_last_seen = None

            # ===== MESSAGE RANK USING HOURLY AGGREGATED TABLE =====
            try:
                async with db_cog.pool.acquire() as conn:
                    if start_time is None:
                        query = '''
                            SELECT user_id, SUM(message_count) as message_count,
                                   MIN(hour) as first_seen, MAX(hour) as last_seen
                            FROM message_tracking_hourly
                            WHERE guild_id = $1 
                            AND is_bot = FALSE
                            GROUP BY user_id
                            HAVING SUM(message_count) > 0
                            ORDER BY message_count DESC
                        '''
                        rows = await conn.fetch(query, guild.id)
                    else:
                        query = '''
                            SELECT user_id, SUM(message_count) as message_count,
                                   MIN(hour) as first_seen, MAX(hour) as last_seen
                            FROM message_tracking_hourly
                            WHERE guild_id = $1 
                            AND is_bot = FALSE
                            AND hour >= $2
                            AND hour <= $3
                            GROUP BY user_id
                            HAVING SUM(message_count) > 0
                            ORDER BY message_count DESC
                        '''
                        rows = await conn.fetch(query, guild.id, start_time, end_time)

                    total_message_users = len(rows)
                    message_rank = 0

                    for idx, row in enumerate(rows, 1):
                        user_id = row['user_id']
                        if user_id == member.id:
                            message_rank = idx

                        # Track global min/max for All Time mode
                        if use_all_time:
                            if global_first_seen is None or row['first_seen'] < global_first_seen:
                                global_first_seen = row['first_seen']
                            if global_last_seen is None or row['last_seen'] > global_last_seen:
                                global_last_seen = row['last_seen']
            except Exception as e:
                logger.error(f"Error getting message rank: {e}")
                message_rank = 0
                total_message_users = 0

            # ===== VOICE RANK =====
            try:
                async with db_cog.pool.acquire() as conn:
                    if start_time is None:
                        query = '''
                            SELECT 
                                user_id,
                                COALESCE(SUM(total_seconds), 0) as total_seconds,
                                MIN(hour) as first_seen,
                                MAX(hour) as last_seen
                            FROM voice_session_history_hourly
                            WHERE guild_id = $1
                            GROUP BY user_id
                            HAVING SUM(total_seconds) > 0
                            ORDER BY total_seconds DESC
                        '''
                        rows = await conn.fetch(query, guild.id)
                    else:
                        start_time_aware = ensure_aware(start_time)
                        end_time_aware = ensure_aware(end_time)
                        query = '''
                            SELECT 
                                user_id,
                                COALESCE(SUM(total_seconds), 0) as total_seconds,
                                MIN(hour) as first_seen,
                                MAX(hour) as last_seen
                            FROM voice_session_history_hourly
                            WHERE guild_id = $1
                            AND hour >= $2
                            AND hour <= $3
                            GROUP BY user_id
                            HAVING SUM(total_seconds) > 0
                            ORDER BY total_seconds DESC
                        '''
                        rows = await conn.fetch(query, guild.id, start_time_aware, end_time_aware)

                    total_voice_users = len(rows)
                    voice_rank = 0

                    # Track global min/max for voice in All Time mode
                    if use_all_time:
                        for row in rows:
                            if global_first_seen is None or row['first_seen'] < global_first_seen:
                                global_first_seen = row['first_seen']
                            if global_last_seen is None or row['last_seen'] > global_last_seen:
                                global_last_seen = row['last_seen']

                    for idx, row in enumerate(rows, 1):
                        if int(row['user_id']) == int(member.id):
                            voice_rank = idx
                            break

            except Exception as e:
                logger.error(f"Error getting voice rank: {e}")
                voice_rank = 0
                total_voice_users = 0

            # ===== GET TOP USERS BY MESSAGES FOR LEADERBOARD =====
            messages_leaderboard_data = []
            try:
                async with db_cog.pool.acquire() as conn:
                    if start_time is None:
                        query = '''
                            SELECT user_id, SUM(message_count) as message_count
                            FROM message_tracking_hourly
                            WHERE guild_id = $1
                            AND is_bot = FALSE
                            GROUP BY user_id
                            HAVING SUM(message_count) > 0
                            ORDER BY message_count DESC
                            LIMIT 3
                        '''
                        rows = await conn.fetch(query, guild.id)
                    else:
                        query = '''
                            SELECT user_id, SUM(message_count) as message_count
                            FROM message_tracking_hourly
                            WHERE guild_id = $1
                            AND hour >= $2
                            AND hour <= $3
                            AND is_bot = FALSE
                            GROUP BY user_id
                            HAVING SUM(message_count) > 0
                            ORDER BY message_count DESC
                            LIMIT 3
                        '''
                        rows = await conn.fetch(query, guild.id, start_time, end_time)
                    messages_leaderboard_data = [dict(row) for row in rows]
            except Exception as e:
                logger.error(f"Error getting messages leaderboard: {e}")
                messages_leaderboard_data = []

            # ===== GET TOP USERS BY VOICE FOR LEADERBOARD =====
            voice_leaderboard_data = []
            try:
                async with db_cog.pool.acquire() as conn:
                    if start_time is None:
                        query = '''
                            SELECT user_id, SUM(total_seconds) as total_seconds
                            FROM voice_session_history_hourly
                            WHERE guild_id = $1
                            GROUP BY user_id
                            HAVING SUM(total_seconds) > 0
                            ORDER BY total_seconds DESC
                            LIMIT 3
                        '''
                        rows = await conn.fetch(query, guild.id)
                    else:
                        query = '''
                            SELECT user_id, SUM(total_seconds) as total_seconds
                            FROM voice_session_history_hourly
                            WHERE guild_id = $1
                            AND hour >= $2
                            AND hour <= $3
                            GROUP BY user_id
                            HAVING SUM(total_seconds) > 0
                            ORDER BY total_seconds DESC
                            LIMIT 3
                        '''
                        rows = await conn.fetch(query, guild.id, start_time, end_time)
                    voice_leaderboard_data = [dict(row) for row in rows]
            except Exception as e:
                logger.error(f"Error getting voice leaderboard: {e}")
                voice_leaderboard_data = []

            # ===== USER TOTAL MESSAGES =====
            total_messages_data = await db_cog.q_user_total_messages(
                guild_id=guild.id,
                user_id=member.id,
                role_filter_ids=None,
                start_time=start_time,
                end_time=end_time
            )
            total_messages = total_messages_data.get(
                'total_messages', 0) if total_messages_data else 0

            # ===== USER TOTAL VOICE =====
            total_voice_data = await db_cog.q_user_total_voice(
                guild_id=guild.id,
                user_id=member.id,
                role_filter_ids=None,
                start_time=start_time,
                end_time=end_time
            )
            total_voice_seconds = total_voice_data.get(
                'total_seconds', 0) if total_voice_data else 0

            # ===== USER TOP TEXT CHANNELS =====
            top_text_channels_raw = await db_cog.q_user_top3_text_channels(
                guild_id=guild.id,
                user_id=member.id,
                role_filter_ids=None,
                start_time=start_time,
                end_time=end_time
            )
            top_text_channels_raw = top_text_channels_raw if top_text_channels_raw else []

            # ===== USER TOP VOICE CHANNELS =====
            top_voice_channels_raw = await db_cog.q_user_top3_voice_channels(
                guild_id=guild.id,
                user_id=member.id,
                role_filter_ids=None,
                start_time=start_time,
                end_time=end_time
            )
            top_voice_channels_raw = top_voice_channels_raw if top_voice_channels_raw else []

            # Format text channels
            top_text_channels = []
            for channel_data in top_text_channels_raw[:3]:
                channel_id = channel_data.get('channel_id')
                if channel_id:
                    channel_name = await self.get_channel_name(guild, channel_id)
                    top_text_channels.append({
                        'channel_id': channel_id,
                        'channel_name': channel_name,
                        'activity_count': channel_data.get('message_count', 0) or 0
                    })

            # Format voice channels
            top_voice_channels = []
            for channel_data in top_voice_channels_raw[:3]:
                channel_id = channel_data.get('channel_id')
                if channel_id:
                    channel_name = await self.get_channel_name(guild, channel_id)

                    activity_count = channel_data.get('total_seconds', 0) or 0
                    top_voice_channels.append({
                        'channel_id': channel_id,
                        'channel_name': channel_name,
                        'activity_count': activity_count
                    })

            # Calculate hourly rates
            if use_all_time and global_first_seen and global_last_seen:
                # Calculate total hours between first and last seen data
                total_hours = (global_last_seen -
                               global_first_seen).total_seconds() / 3600
                total_hours = max(total_hours, 0.01)  # Avoid division by zero
                messages_per_hour = total_messages / total_hours if total_hours > 0 else 0
                total_voice_hours = total_voice_seconds / 3600
                voice_hours_per_hour = total_voice_hours / total_hours if total_hours > 0 else 0
            elif not use_all_time and start_time:
                total_hours = (end_time - start_time).total_seconds() / 3600
                total_hours = max(total_hours, 0.01)
                messages_per_hour = total_messages / total_hours if total_hours > 0 else 0
                total_voice_hours = total_voice_seconds / 3600
                voice_hours_per_hour = total_voice_hours / total_hours if total_hours > 0 else 0
            else:
                messages_per_hour = 0
                voice_hours_per_hour = 0

            # ===== MESSAGE PERIOD DATA =====
            message_periods_data = {}
            if use_all_time and global_last_seen:
                # For All Time, calculate periods relative to the last seen date
                for period_days in [1, 5, 10, 20, 30]:
                    period_end = global_last_seen
                    period_start = global_last_seen - \
                        timedelta(days=period_days)

                    # Ensure we don't go before the first seen date
                    if global_first_seen and period_start < global_first_seen:
                        period_start = global_first_seen

                    period_data = await db_cog.q_user_total_messages(
                        guild_id=guild.id,
                        user_id=member.id,
                        role_filter_ids=None,
                        start_time=period_start,
                        end_time=period_end
                    )
                    message_periods_data[f'{period_days}d'] = period_data.get(
                        'total_messages', 0) if period_data else 0
            elif not use_all_time and start_time:
                for period_days in [1, 5, 10, 20, 30]:
                    # Use days_back_equiv to check if period exceeds the main range
                    if period_days > days_back_equiv:
                        message_periods_data[f'{period_days}d'] = 0
                        continue
                    period_end = end_time
                    period_start = end_time - timedelta(days=period_days)

                    if period_start < start_time:
                        period_start = start_time

                    period_data = await db_cog.q_user_total_messages(
                        guild_id=guild.id,
                        user_id=member.id,
                        role_filter_ids=None,
                        start_time=period_start,
                        end_time=period_end
                    )
                    message_periods_data[f'{period_days}d'] = period_data.get(
                        'total_messages', 0) if period_data else 0
            else:
                message_periods_data = {f'{d}d': 0 for d in [1, 5, 10, 20, 30]}

            # ===== VOICE PERIOD DATA =====
            voice_periods_data = {}
            if use_all_time and global_last_seen:
                # For All Time, calculate periods relative to the last seen date
                for period_days in [1, 5, 10, 20, 30]:
                    period_end = global_last_seen
                    period_start = global_last_seen - \
                        timedelta(days=period_days)

                    # Ensure we don't go before the first seen date
                    if global_first_seen and period_start < global_first_seen:
                        period_start = global_first_seen

                    period_data = await db_cog.q_user_total_voice(
                        guild_id=guild.id,
                        user_id=member.id,
                        role_filter_ids=None,
                        start_time=period_start,
                        end_time=period_end
                    )
                    voice_periods_data[f'{period_days}d'] = period_data.get(
                        'total_seconds', 0) if period_data else 0
            elif not use_all_time and start_time:
                for period_days in [1, 5, 10, 20, 30]:
                    if period_days > days_back_equiv:
                        voice_periods_data[f'{period_days}d'] = 0
                        continue
                    period_end = end_time
                    period_start = end_time - timedelta(days=period_days)

                    if period_start < start_time:
                        period_start = start_time

                    period_data = await db_cog.q_user_total_voice(
                        guild_id=guild.id,
                        user_id=member.id,
                        role_filter_ids=None,
                        start_time=period_start,
                        end_time=period_end
                    )
                    voice_periods_data[f'{period_days}d'] = period_data.get(
                        'total_seconds', 0) if period_data else 0
            else:
                voice_periods_data = {f'{d}d': 0 for d in [1, 5, 10, 20, 30]}

            result = {
                'total_messages': total_messages or 0,
                'total_voice_seconds': total_voice_seconds or 0,
                'message_rank': message_rank or 0,
                'voice_rank': voice_rank or 0,
                'total_message_users': total_message_users or 0,
                'total_voice_users': total_voice_users or 0,
                'messages_per_hour': messages_per_hour or 0,
                'voice_hours_per_hour': voice_hours_per_hour or 0,
                'top_text_channels': top_text_channels or [],
                'top_voice_channels': top_voice_channels or [],
                'message_periods': message_periods_data or {},
                'voice_periods': voice_periods_data or {},
                'success': True,
                'use_all_time': use_all_time
            }

            return result

        except Exception as e:
            logger.error(f"Error getting user stats data: {e}")
            traceback.print_exc()
            return {"error": f"Database error: {str(e)}"}

    # IMAGE GENERATION

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=25.0)
    async def _generate_user_stats_image(self, guild: discord.Guild, member: discord.Member, start_time: datetime = None, end_time: datetime = None, display_text: str = None, days_back_equiv: int = None):
        # If no time parameters provided, use server default
        if start_time is None and end_time is None and display_text is None and days_back_equiv is None:
            start_time, end_time, display_text, days_back_equiv = await self.get_server_default_time_range(guild)

        data = await self._get_user_stats_data(guild, member, start_time, end_time, days_back_equiv)

        if "error" in data:
            image = Image.new('RGB', (800, 800), color='#2C2F33')

            with Pilmoji(image, source=self.emoji_source) as pilmoji:
                draw = pilmoji.draw
                try:
                    font_paths = [
                        BASE_DIR / "assets" / "fonts" / "HorndonD.ttf"]
                    font_loaded = False
                    for font_path in font_paths:
                        if os.path.exists(font_path):
                            try:
                                error_font = ImageFont.truetype(font_path, 30)
                                font_loaded = True
                                break
                            except:
                                continue

                    if not font_loaded:
                        error_font = ImageFont.load_default()
                except:
                    error_font = ImageFont.load_default()

                error_text = data["error"]
                if len(error_text) > 50:
                    lines = [error_text[i:i+50]
                             for i in range(0, len(error_text), 50)]
                    for i, line in enumerate(lines):
                        draw_text_centered(
                            pilmoji, line, (400, 350 + (i * 40)), error_font, "white")
                else:
                    draw_text_centered(
                        pilmoji, error_text, (400, 400), error_font, "white")

            image_buffer = io.BytesIO()
            image.save(image_buffer, format='PNG')
            image_buffer.seek(0)
            return image_buffer

        template_path = BASE_DIR / "assets" / "images" / "user stats final png.png"
        if not os.path.exists(template_path):
            logger.error(f"Template image not found at: {template_path}")
            image = Image.new('RGB', (800, 800), color='black')
            with Pilmoji(image, source=self.emoji_source) as pilmoji:
                font = ImageFont.load_default()
                draw_text_centered(
                    pilmoji, "Template image not found", (400, 400), font, "white")
        else:
            try:
                image = Image.open(template_path)
            except Exception as e:
                logger.error(f"Error loading template image: {e}")
                image = Image.new('RGB', (800, 800), color='black')
                with Pilmoji(image, source=self.emoji_source) as pilmoji:
                    font = ImageFont.load_default()
                    draw_text_centered(
                        pilmoji, "Error loading template", (400, 400), font, "white")
                image_buffer = io.BytesIO()
                image.save(image_buffer, format='PNG')
                image_buffer.seek(0)
                return image_buffer

        pilmoji = Pilmoji(image, source=self.emoji_source)
        draw = pilmoji.draw

        # FONTS

        try:
            font_paths = [
                BASE_DIR / "assets" / "fonts" / "HorndonD.ttf"]

            font_loaded = False
            for font_path in font_paths:
                if os.path.exists(font_path):
                    try:
                        font_horndon_tiny = ImageFont.truetype(font_path, 8)
                        font_horndon_extra_small = ImageFont.truetype(
                            font_path, 10)
                        font_horndon_small = ImageFont.truetype(font_path, 12)
                        font_horndon_medium_small = ImageFont.truetype(
                            font_path, 14)
                        font_horndon_medium = ImageFont.truetype(font_path, 16)
                        font_horndon_large = ImageFont.truetype(font_path, 18)
                        font_horndon_larger = ImageFont.truetype(font_path, 20)
                        font_horndon_xlarge = ImageFont.truetype(font_path, 22)
                        font_horndon_xxlarge = ImageFont.truetype(
                            font_path, 24)
                        font_horndon_huge = ImageFont.truetype(font_path, 30)
                        font_horndon_giant = ImageFont.truetype(font_path, 40)
                        font_horndon_massive = ImageFont.truetype(
                            font_path, 50)
                        font_loaded = True
                        break
                    except:
                        continue

            if not font_loaded:
                font_horndon_tiny = ImageFont.load_default()
                font_horndon_extra_small = ImageFont.load_default()
                font_horndon_small = ImageFont.load_default()
                font_horndon_medium_small = ImageFont.load_default()
                font_horndon_medium = ImageFont.load_default()
                font_horndon_large = ImageFont.load_default()
                font_horndon_larger = ImageFont.load_default()
                font_horndon_xlarge = ImageFont.load_default()
                font_horndon_xxlarge = ImageFont.load_default()
                font_horndon_huge = ImageFont.load_default()
                font_horndon_giant = ImageFont.load_default()
                font_horndon_massive = ImageFont.load_default()

        except Exception as e:
            logger.error(f"Error loading fonts: {e}")
            font_horndon_tiny = ImageFont.load_default()
            font_horndon_extra_small = ImageFont.load_default()
            font_horndon_small = ImageFont.load_default()
            font_horndon_medium_small = ImageFont.load_default()
            font_horndon_medium = ImageFont.load_default()
            font_horndon_large = ImageFont.load_default()
            font_horndon_larger = ImageFont.load_default()
            font_horndon_xlarge = ImageFont.load_default()
            font_horndon_xxlarge = ImageFont.load_default()
            font_horndon_huge = ImageFont.load_default()
            font_horndon_giant = ImageFont.load_default()
            font_horndon_massive = ImageFont.load_default()

        # INVISIBLE RECTANGLE FUNCTIONS

        def check_text_against_rectangle(text, font, text_x, text_y, rect_center_x, rect_center_y, rect_width, rect_height):
            rect_left = rect_center_x - (rect_width // 2)
            rect_right = rect_center_x + (rect_width // 2)
            rect_top = rect_center_y - (rect_height // 2)
            rect_bottom = rect_center_y + (rect_height // 2)

            bbox = draw.textbbox((text_x, text_y), text, font=font)
            text_left = bbox[0]
            text_right = bbox[2]
            text_top = bbox[1]
            text_bottom = bbox[3]
            exceeds_width = (text_left < rect_left) or (
                text_right > rect_right)
            exceeds_height = (text_top < rect_top) or (
                text_bottom > rect_bottom)

            return exceeds_width or exceeds_height

        def fit_text_to_rectangle(text, text_center_x, text_center_y, rect_center_x, rect_center_y, rect_width, rect_height, is_channel=False, is_username=False):
            if is_username:
                font_sizes = [34, 32, 30, 28, 26, 24, 22, 20, 18, 16, 14]
            elif is_channel:
                font_sizes = [24, 22, 20, 18, 16, 14, 12, 10, 8]
            else:
                font_sizes = [24, 22, 20, 18, 16, 14, 12, 10, 8]

            for font_size in font_sizes:
                try:
                    font = ImageFont.truetype(font_paths[0], font_size) if os.path.exists(
                        font_paths[0]) else ImageFont.load_default()
                except:
                    font = ImageFont.load_default()

                bbox = draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                text_x = text_center_x - (text_width // 2)
                text_y = text_center_y - (text_height // 2)

                vertical_offset = 0

                if is_username:
                    if font_size <= 30:
                        vertical_offset += 1
                    if font_size <= 20:
                        vertical_offset += 1
                    if font_size <= 16:
                        vertical_offset += 1
                elif is_channel:
                    if font_size <= 20:
                        vertical_offset += 1
                    if font_size <= 16:
                        vertical_offset += 1
                else:
                    if font_size <= 12:
                        vertical_offset += 1

                text_y += vertical_offset

                if not check_text_against_rectangle(text, font, text_x, text_y, rect_center_x, rect_center_y, rect_width, rect_height):
                    return text, font, (text_x, text_y)

            smallest_font = font_sizes[-1]
            try:
                font = ImageFont.truetype(font_paths[0], smallest_font) if os.path.exists(
                    font_paths[0]) else ImageFont.load_default()
            except:
                font = ImageFont.load_default()

            truncated_text = text
            while len(truncated_text) > 3:
                truncated_text = truncated_text[:-4] + "..."
                bbox = draw.textbbox((0, 0), truncated_text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]

                text_x = text_center_x - (text_width // 2)
                text_y = text_center_y - (text_height // 2)

                vertical_offset = 0
                if is_username:
                    if smallest_font <= 30:
                        vertical_offset += 1
                    if smallest_font <= 20:
                        vertical_offset += 1
                    if smallest_font <= 16:
                        vertical_offset += 1
                elif is_channel:
                    if smallest_font <= 20:
                        vertical_offset += 1
                    if smallest_font <= 16:
                        vertical_offset += 1
                else:
                    if smallest_font <= 12:
                        vertical_offset += 1

                text_y += vertical_offset

                if not check_text_against_rectangle(truncated_text, font, text_x, text_y, rect_center_x, rect_center_y, rect_width, rect_height):
                    return truncated_text, font, (text_x, text_y)

            return "", font, (text_center_x, text_center_y)

        # INVISIBLE RECTANGLE SIZES AND POSITIONS

        text_channel_rectangles = [
            {"center": (70, 508), "width": 120, "height": 50},
            {"center": (70, 560), "width": 120, "height": 50},
            {"center": (70, 620), "width": 120, "height": 50}
        ]

        voice_channel_rectangles = [
            {"center": (330, 508), "width": 120, "height": 50},
            {"center": (330, 560), "width": 120, "height": 50},
            {"center": (330, 720), "width": 120, "height": 50}
        ]

        username_rectangle = {"center": (160, 35), "width": 183, "height": 35}

        # USER PROFILE PICTURE AND NAME

        member_name = f"{member.name}" if isinstance(
            member, discord.Member) else member.name

        member_name = normalize_text(member_name)

        try:
            if member.avatar:
                avatar_url = member.avatar.url
                async with aiohttp.ClientSession() as session:
                    async with session.get(avatar_url) as response:
                        avatar_data = await response.read()

                avatar_image = Image.open(io.BytesIO(avatar_data))

                avatar_size = (60, 60)
                avatar_image = avatar_image.resize(
                    avatar_size, Image.Resampling.LANCZOS).convert('RGBA')

                mask = Image.new('L', avatar_size, 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.ellipse(
                    (0, 0, avatar_size[0], avatar_size[1]), fill=255)
                avatar_image.putalpha(mask)

                avatar_x = 7
                avatar_y = 25 - 20

                avatar_area = image.crop(
                    (avatar_x, avatar_y, avatar_x + avatar_size[0], avatar_y + avatar_size[1])).convert('RGBA')

                avatar_with_bg = Image.new('RGBA', avatar_size, (0, 0, 0, 0))
                avatar_with_bg.paste(avatar_image, (0, 0), avatar_image)

                avatar_area.paste(avatar_with_bg, (0, 0), avatar_with_bg)
                image.paste(avatar_area.convert('RGB'), (avatar_x, avatar_y))

                avatar_image.close()
                del avatar_image
                del avatar_data

                username_text_center = (150, 25)

                fitted_text, username_font, username_pos = fit_text_to_rectangle(
                    member_name,
                    username_text_center[0],
                    username_text_center[1],
                    username_rectangle["center"][0],
                    username_rectangle["center"][1],
                    username_rectangle["width"],
                    username_rectangle["height"],
                    is_channel=False,
                    is_username=True
                )

                pilmoji.text(username_pos, fitted_text,
                             fill="white", font=username_font)

            else:
                username_text_center = (91, 27)

                fitted_text, username_font, username_pos = fit_text_to_rectangle(
                    member_name,
                    username_text_center[0],
                    username_text_center[1],
                    username_rectangle["center"][0],
                    username_rectangle["center"][1],
                    username_rectangle["width"],
                    username_rectangle["height"],
                    is_channel=False,
                    is_username=True
                )

                pilmoji.text(username_pos, fitted_text,
                             fill="white", font=username_font)

        except Exception as e:
            logger.error(f"Could not add member avatar: {e}")
            username_text_center = (91, 27)

            fitted_text, username_font, username_pos = fit_text_to_rectangle(
                member_name,
                username_text_center[0],
                username_text_center[1],
                username_rectangle["center"][0],
                username_rectangle["center"][1],
                username_rectangle["width"],
                username_rectangle["height"],
                is_channel=False,
                is_username=True
            )
            pilmoji.text(username_pos, fitted_text,
                         fill="white", font=username_font)

        # CREATED ON
        current_date = datetime.now().strftime("%B %d, %Y")
        draw_text_centered(pilmoji, current_date, (605, 45),
                           font_horndon_medium, "white", max_width=150)

        # TIME PERIOD
        draw_text_centered(pilmoji, display_text, (147, 713),
                           font_horndon_medium, "white", max_width=100)

        # RANKS
        messages_rank_text = f"#{data['message_rank']}" if data['message_rank'] > 0 else "-"
        draw_text_centered(pilmoji, messages_rank_text, (190, 155),
                           font_horndon_xlarge, "white", max_width=150)

        # Voice rank
        voice_rank_text = f"#{data['voice_rank']}" if data['voice_rank'] > 0 else "-"
        draw_text_centered(pilmoji, voice_rank_text, (190, 215),
                           font_horndon_xlarge, "white", max_width=150)

        # TOTALS
        total_messages_text = str(
            data['total_messages']) if data['total_messages'] > 0 else "0"
        draw_text_centered(pilmoji, total_messages_text, (450, 155),
                           font_horndon_xlarge, "white", max_width=150)

        # Total voice time
        if data['total_voice_seconds'] > 0:
            voice_time_text = format_voice_time(data['total_voice_seconds'])
        else:
            voice_time_text = "0s"
        draw_text_centered(pilmoji, voice_time_text, (450, 215),
                           font_horndon_xlarge, "white", max_width=150)

        # HOURLY RATES
        messages_per_hour_text = f"{data['messages_per_hour']:.2f}" if data['messages_per_hour'] > 0 else "0.00"
        if data['voice_hours_per_hour'] > 0:
            voice_per_hour_text = format_voice_hours_per_hour(
                data['voice_hours_per_hour'])
        else:
            voice_per_hour_text = "0s"

        draw_text_centered(pilmoji, messages_per_hour_text, (130, 340),
                           font_horndon_huge, "white", max_width=150)
        draw_text_centered(pilmoji, voice_per_hour_text, (385, 340),
                           font_horndon_huge, "white", max_width=150)

        # TEXT CHANNELS
        text_channel_positions = [(65, 500), (65, 555), (65, 610)]
        text_message_positions = [(190, 500), (190, 555), (190, 610)]

        for i in range(3):
            text_pos = text_channel_positions[i]
            rect_info = text_channel_rectangles[i]

            if i < len(data['top_text_channels']):
                channel = data['top_text_channels'][i]
                channel_name = channel.get(
                    'channel_name', f"#{channel.get('channel_id', '?')}")

                if channel_name.startswith('#'):
                    display_name = channel_name
                else:
                    display_name = f"#{channel_name}"

                # Use placeholder if channel name is empty
                if not display_name or display_name.strip() == "#":
                    display_name = "-"

                fitted_text, channel_font, final_pos = fit_text_to_rectangle(
                    display_name,
                    text_pos[0],
                    text_pos[1],
                    rect_info["center"][0],
                    rect_info["center"][1],
                    rect_info["width"],
                    rect_info["height"],
                    is_channel=True
                )

                if fitted_text:
                    pilmoji.text(final_pos, fitted_text,
                                 fill="white", font=channel_font)
                else:
                    placeholder_font = font_horndon_xlarge
                    bbox = draw.textbbox((0, 0), "-", font=placeholder_font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    placeholder_x = text_pos[0] - (text_width // 2)
                    placeholder_y = text_pos[1] - (text_height // 2)
                    pilmoji.text((placeholder_x, placeholder_y), "-",
                                 fill="white", font=placeholder_font)

                draw_text_centered(pilmoji, str(channel.get('activity_count', 0) or 0),
                                   text_message_positions[i], font_horndon_xlarge, "white", max_width=80)
            else:
                placeholder_font = font_horndon_xlarge
                bbox = draw.textbbox((0, 0), "-", font=placeholder_font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                placeholder_x = text_pos[0] - (text_width // 2)
                placeholder_y = text_pos[1] - (text_height // 2)
                pilmoji.text((placeholder_x, placeholder_y), "-",
                             fill="white", font=placeholder_font)

                draw_text_centered(pilmoji, "0", text_message_positions[i],
                                   font_horndon_xlarge, "white", max_width=80)

        # VOICE CHANNELS
        voice_channel_positions = [(325, 500), (325, 555), (325, 610)]
        voice_time_positions = [(455, 500), (455, 555), (455, 610)]

        for i in range(3):
            text_pos = voice_channel_positions[i]
            rect_info = voice_channel_rectangles[i]

            if i < len(data['top_voice_channels']):
                channel = data['top_voice_channels'][i]
                channel_name = channel.get(
                    'channel_name', f"#{channel.get('channel_id', '?')}")

                if channel_name.startswith('#'):
                    display_name = channel_name[1:]
                else:
                    display_name = channel_name

                # Use placeholder if channel name is empty
                if not display_name or display_name.strip() == "":
                    display_name = "-"

                fitted_text, channel_font, final_pos = fit_text_to_rectangle(
                    display_name,
                    text_pos[0],
                    text_pos[1],
                    rect_info["center"][0],
                    rect_info["center"][1],
                    rect_info["width"],
                    rect_info["height"],
                    is_channel=True
                )

                if fitted_text:
                    pilmoji.text(final_pos, fitted_text,
                                 fill="white", font=channel_font)
                else:
                    placeholder_font = font_horndon_xlarge
                    bbox = draw.textbbox((0, 0), "-", font=placeholder_font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    placeholder_x = text_pos[0] - (text_width // 2)
                    placeholder_y = text_pos[1] - (text_height // 2)
                    pilmoji.text((placeholder_x, placeholder_y), "-",
                                 fill="white", font=placeholder_font)

                seconds = channel.get('activity_count', 0) or 0
                if seconds > 0:
                    time_text = format_voice_time(seconds)
                else:
                    time_text = "0s"
                draw_text_centered(pilmoji, time_text, voice_time_positions[i],
                                   font_horndon_xlarge, "white", max_width=80)
            else:
                placeholder_font = font_horndon_xlarge
                bbox = draw.textbbox((0, 0), "-", font=placeholder_font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                placeholder_x = text_pos[0] - (text_width // 2)
                placeholder_y = text_pos[1] - (text_height // 2)
                pilmoji.text((placeholder_x, placeholder_y), "-",
                             fill="white", font=placeholder_font)

                draw_text_centered(pilmoji, "0s", voice_time_positions[i],
                                   font_horndon_xlarge, "white", max_width=80)

        # MESSAGES OVER TIME
        message_time_positions = {
            '1d': (675, 155),
            '5d': (675, 215),
            '10d': (675, 270),
            '20d': (675, 323),
            '30d': (675, 375)
        }

        for period, position in message_time_positions.items():
            count = data['message_periods'].get(period, 0) or 0
            draw_text_centered(pilmoji, str(count), position,
                               font_horndon_xlarge, "white", max_width=80)

        # VOICE TIME OVER TIME
        voice_time_positions = {
            '1d': (675, 475),
            '5d': (675, 533),
            '10d': (675, 590),
            '20d': (675, 643),
            '30d': (675, 695)
        }

        for period, position in voice_time_positions.items():
            seconds = data['voice_periods'].get(period, 0) or 0
            if seconds > 0:
                voice_time_formatted = format_voice_time(seconds)
            else:
                voice_time_formatted = "0s"
            draw_text_centered(pilmoji, voice_time_formatted, position,
                               font_horndon_xlarge, "white", max_width=80)

        # SERVER NAME AND ICON
        server_name = normalize_text(guild.name)

        try:
            if guild.icon:
                icon_url = guild.icon.url
                async with aiohttp.ClientSession() as session:
                    async with session.get(icon_url) as response:
                        icon_data = await response.read()

                icon_image = Image.open(io.BytesIO(icon_data))
                icon_size = (20, 20)
                icon_image = icon_image.resize(
                    icon_size, Image.Resampling.LANCZOS).convert('RGBA')

                mask = Image.new('L', icon_size, 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.ellipse((0, 0, icon_size[0], icon_size[1]), fill=255)
                icon_image.putalpha(mask)

                bbox = draw.textbbox((0, 0), server_name,
                                     font=font_horndon_medium)
                text_width = bbox[2] - bbox[0]

                icon_x = 375 - (text_width // 2) - 25
                icon_y = 75 - 10

                icon_area = image.crop((int(icon_x), int(icon_y), int(
                    icon_x) + icon_size[0], int(icon_y) + icon_size[1])).convert('RGBA')

                icon_with_bg = Image.new('RGBA', icon_size, (0, 0, 0, 0))
                icon_with_bg.paste(icon_image, (0, 0), icon_image)

                icon_area.paste(icon_with_bg, (0, 0), icon_with_bg)

                image.paste(icon_area.convert('RGB'),
                            (int(icon_x), int(icon_y)))

                text_x = 375 - (text_width // 2)
                text_y = 75 - 10

                stroke_width = 1
                for dx in [-stroke_width, 0, stroke_width]:
                    for dy in [-stroke_width, 0, stroke_width]:
                        if dx != 0 or dy != 0:
                            pilmoji.text((text_x + dx, text_y + dy), server_name,
                                         fill="black", font=font_horndon_medium)

                pilmoji.text((text_x, text_y), server_name,
                             fill="white", font=font_horndon_medium)

            else:
                text_y = 78
                text_x = 375

                bbox = draw.textbbox((0, 0), server_name,
                                     font=font_horndon_medium)
                text_width = bbox[2] - bbox[0]
                text_x = 375 - (text_width // 2)

                stroke_width = 1
                for dx in [-stroke_width, 0, stroke_width]:
                    for dy in [-stroke_width, 0, stroke_width]:
                        if dx != 0 or dy != 0:
                            pilmoji.text((text_x + dx, text_y + dy), server_name,
                                         fill="black", font=font_horndon_medium)

                pilmoji.text((text_x, text_y), server_name,
                             fill="white", font=font_horndon_medium)

        except Exception as e:
            logger.error(f"Could not add server icon: {e}")
            text_y = 78
            text_x = 375

            bbox = draw.textbbox((0, 0), server_name, font=font_horndon_medium)
            text_width = bbox[2] - bbox[0]
            text_x = 375 - (text_width // 2)

            stroke_width = 1
            for dx in [-stroke_width, 0, stroke_width]:
                for dy in [-stroke_width, 0, stroke_width]:
                    if dx != 0 or dy != 0:
                        pilmoji.text((text_x + dx, text_y + dy), server_name,
                                     fill="black", font=font_horndon_medium)

            pilmoji.text((text_x, text_y), server_name,
                         fill="white", font=font_horndon_medium)

        pilmoji.close()

        gc.collect()

        image_buffer = io.BytesIO()
        image.save(image_buffer, format='PNG')
        image_buffer.seek(0)

        return image_buffer

    # =========================================================
    # INTERNAL FUNCTION FOR BOTH COMMANDS
    # =========================================================
    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def _handle_user_stats_command(self, ctx_or_interaction, member=None, is_interaction=False):
        """Internal function to handle user stats for both command types"""
        try:
            # Get context parameters
            if is_interaction:
                user = ctx_or_interaction.user
                guild = ctx_or_interaction.guild
            else:
                user = ctx_or_interaction.author
                guild = ctx_or_interaction.guild
                # Try to delete the command message
                try:
                    await ctx_or_interaction.message.delete()
                except:
                    pass

            # Handle member parameter
            if member is None:
                member = user

            if guild is None:
                if is_interaction:
                    await ctx_or_interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
                else:
                    await ctx_or_interaction.send("❌ This command can only be used in a server.", delete_after=5)
                return

            # Check if user has permission to view this member's stats
            permission_error = await self.check_user_permission(user, member, guild)
            if permission_error:
                if is_interaction:
                    await ctx_or_interaction.response.send_message(embed=permission_error, ephemeral=True)
                else:
                    await ctx_or_interaction.send(embed=permission_error, delete_after=10)
                return

            # Check blacklist
            blacklist_error = await self.check_blacklist_and_get_error(guild, member)
            if blacklist_error:
                if is_interaction:
                    await ctx_or_interaction.response.send_message(blacklist_error, ephemeral=True)
                else:
                    await ctx_or_interaction.send(blacklist_error, delete_after=10)
                return

            # Use None to indicate server default, which will fetch from settings
            start_time = None
            end_time = None
            display_text = None
            days_back_equiv = None

            # IMPORTANT FIX: Properly defer the interaction
            if is_interaction:
                # Check if we can defer the response
                if not ctx_or_interaction.response.is_done():
                    await ctx_or_interaction.response.defer(thinking=True)

            # Generate stats image (will use server default since all params are None)
            try:
                image_buffer = await self._generate_user_stats_image(guild, member, start_time=start_time, end_time=end_time, display_text=display_text, days_back_equiv=days_back_equiv)
            except asyncio.TimeoutError:
                if is_interaction:
                    await ctx_or_interaction.followup.send("⚠️ The stats generation is taking longer than expected. Please try again in a moment.", ephemeral=True)
                else:
                    await ctx_or_interaction.send("⚠️ The stats generation is taking longer than expected. Please try again in a moment.", delete_after=10)
                return
            except Exception as e:
                logger.error(f"Error generating image: {e}")
                if is_interaction:
                    await ctx_or_interaction.followup.send("❌ An error occurred while generating stats image.", ephemeral=True)
                else:
                    await ctx_or_interaction.send("❌ An error occurred while generating stats image.", delete_after=10)
                return

            file = discord.File(image_buffer, filename="user_stats.png")

            # Create view with None params to indicate using server default
            view = UserStatsView(self, guild, member, start_time=start_time, end_time=end_time,
                                 display_text=display_text, days_back_equiv=days_back_equiv)

            # Send the image
            if is_interaction:
                # When we defer with thinking=True, we need to use followup.send
                # edit_original_response doesn't support file attachments
                msg = await ctx_or_interaction.followup.send(file=file, view=view)
            else:
                msg = await ctx_or_interaction.send(file=file, view=view, delete_after=300)

            # Store session
            self.active_user_stats_sessions[msg.id] = {
                'guild_id': guild.id,
                'user_id': member.id,
                'current_start_time': None,
                'current_end_time': None,
                'current_display_text': None,
                'current_days_back_equiv': None,
                'view': view,
                'created_at': time.time()
            }

        except discord.errors.NotFound as e:
            # Interaction timed out - this is expected for long operations
            logger.warning(f"Interaction not found (likely timed out): {e}")
            if is_interaction:
                try:
                    # Try to send a followup message if possible
                    await ctx_or_interaction.followup.send("⚠️ The command took too long to process. Please try again.", ephemeral=True)
                except:
                    pass
        except Exception as e:
            logger.error(f"Error in _handle_user_stats_command: {e}")
            traceback.print_exc()
            if is_interaction:
                try:
                    if not ctx_or_interaction.response.is_done():
                        await ctx_or_interaction.response.send_message("❌ An error occurred while generating stats image.", ephemeral=True)
                    else:
                        await ctx_or_interaction.followup.send("❌ An error occurred while generating stats image.", ephemeral=True)
                except:
                    pass
            else:
                try:
                    await ctx_or_interaction.send("❌ An error occurred while generating stats image.", delete_after=10)
                except:
                    pass

    # =========================================================
    # SHORTCUT COMMAND - u
    # =========================================================
    @commands.command(name="u")
    async def user_stats_shortcut(self, ctx: commands.Context, member: discord.Member = None):
        """Shortcut command for user stats - same as user stats"""
        await self._handle_user_stats_command(ctx, member, is_interaction=False)

    # =========================================================
    # USER GROUP COMMANDS
    # =========================================================

    @commands.group(name="user", invoke_without_command=True)
    async def user_group_prefix(self, ctx: commands.Context):
        """User statistics commands"""
        await ctx.send("Available commands:\n- `user stats [member]` - Show user statistics\n- `u [member]` - Shortcut for user stats")

    @user_group_prefix.command(name="stats")
    async def user_stats_prefix(self, ctx: commands.Context, member: discord.Member = None):
        """Display user stats via prefix command"""
        await self._handle_user_stats_command(ctx, member, is_interaction=False)

    # =========================================================
    # SLASH COMMAND
    # =========================================================
    @user_group.command(name="stats", description="Display the stats of a user")
    @app_commands.describe(member="Choose which member's stats to view")
    async def user_stats(self, interaction: discord.Interaction, member: discord.Member = None):
        """Display user stats via slash command"""
        try:
            await self._handle_user_stats_command(interaction, member, is_interaction=True)
        except discord.errors.NotFound:
            # Interaction timed out - ignore as the handler already tries to recover
            logger.warning(
                f"User stats command interaction timed out for {interaction.user}")
        except Exception as e:
            logger.error(f"Unexpected error in user_stats slash command: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ An error occurred while processing your request.", ephemeral=True)
                else:
                    await interaction.followup.send("❌ An error occurred while processing your request.", ephemeral=True)
            except:
                pass

    # CLEANUP

    @tasks.loop(minutes=5)
    async def cleanup_sessions(self):
        current_time = time.time()

        keys_to_remove = []
        for message_id, session in list(self.active_user_stats_sessions.items()):
            if current_time - session.get('created_at', current_time) > 3600:
                keys_to_remove.append(message_id)

        for key in keys_to_remove:
            del self.active_user_stats_sessions[key]

    async def cog_load(self):
        if not self.cleanup_sessions.is_running():
            self.cleanup_sessions.start()

    async def cog_unload(self):
        self.cleanup_sessions.cancel()


# SETUP

async def setup(bot):
    await bot.add_cog(UserStats(bot))
