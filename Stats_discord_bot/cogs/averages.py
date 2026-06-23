import os
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta, timezone
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io
import textwrap
import aiohttp
from pathlib import Path
import asyncio
import gc
import re
from .ratelimiter import RateLimiter, RateLimitType, rate_limited, get_rate_limiter


BASE_DIR = Path(__file__).resolve().parent.parent


# PER DAY/WEEK/MONTH DROPDOWN MENU

class TimePeriodSelect(discord.ui.Select):
    def __init__(self, current_period: str = "day"):
        options = [
            discord.SelectOption(
                label="Per Day",
                value="day",
                description="Show averages per day (x/day)",
                emoji="📅",
                default=(current_period == "day")
            ),
            discord.SelectOption(
                label="Per Week",
                value="week",
                description="Show averages per week (x/week)",
                emoji="📆",
                default=(current_period == "week")
            ),
            discord.SelectOption(
                label="Per Month",
                value="month",
                description="Show averages per month (x/month)",
                emoji="🗓️",
                default=(current_period == "month")
            )
        ]

        super().__init__(
            placeholder="Select display format...",
            options=options,
            custom_id="time_period_select",
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if hasattr(view, 'selected_period'):
            view.selected_period = self.values[0]
            await interaction.response.defer()

            try:
                if hasattr(view, 'is_user_stats') and view.is_user_stats:
                    image_file = await view.cog.generate_user_stats_image(
                        interaction,
                        view.current_start_time,
                        view.current_end_time,
                        view.current_days_back_equiv,
                        view.user_id,
                        view.selected_period,
                        view.current_display_text
                    )
                else:
                    image_file = await view.cog.generate_server_stats_image(
                        interaction,
                        view.current_start_time,
                        view.current_end_time,
                        view.current_days_back_equiv,
                        view.selected_role_id,
                        view.selected_period,
                        view.current_display_text
                    )

                if interaction.response.is_done():
                    await interaction.edit_original_response(attachments=[image_file], view=view)
                else:
                    await interaction.response.edit_message(attachments=[image_file], view=view)

            except Exception as e:
                print(f"Error in time period select: {e}")
                await interaction.followup.send("❌ An error occurred while updating the image.", ephemeral=True)


# ROLE MODAL

class RoleIdModal(discord.ui.Modal, title='Input Role ID'):
    def __init__(self, cog_instance, start_time: datetime, end_time: datetime, days_back_equiv: int, display_text: str, selected_period: str = "day", view=None):
        super().__init__(timeout=300)
        self.cog = cog_instance
        self.start_time = start_time
        self.end_time = end_time
        self.days_back_equiv = days_back_equiv
        self.display_text = display_text
        self.selected_period = selected_period
        self.view = view

    role_id_input = discord.ui.TextInput(
        label='Enter Role ID or "none"',
        placeholder='e.g., 123456789012345678 or "none"',
        min_length=1,
        max_length=100,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            role_input = self.role_id_input.value.strip()

            if role_input.lower() == "none":
                role_id = "none"
                role_name = "No Filter"
            else:
                try:
                    role_id_int = int(role_input)
                    role = interaction.guild.get_role(role_id_int)
                    if not role:
                        embed = discord.Embed(
                            description="Sorry! The role id you inputted is not valid, please try again.",
                            color=discord.Color.red()
                        )
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                        return

                    role_id = str(role_id_int)

                    # Get role name from database
                    role_name = None
                    db_stats = self.cog.bot.get_cog('DatabaseStats')
                    if db_stats and db_stats.pool:
                        try:
                            async with db_stats.pool.acquire() as conn:
                                row = await conn.fetchrow("""
                                    SELECT role_name FROM current_role_members 
                                    WHERE role_id = $1 AND guild_id = $2 
                                    LIMIT 1
                                """, role_id_int, interaction.guild.id)
                                if row:
                                    role_name = row['role_name']
                        except:
                            pass

                    if not role_name:
                        role_name = role.name

                except ValueError:
                    embed = discord.Embed(
                        description="Sorry! The role id you inputted is not valid, please try again.",
                        color=discord.Color.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return

            await interaction.response.defer()

            if self.view:
                self.view.selected_role_id = role_id
                self.view.using_server_default = False
                self.view._update_buttons()
                image_file = await self.cog.generate_server_stats_image(
                    interaction,
                    self.start_time,
                    self.end_time,
                    self.days_back_equiv,
                    role_id,
                    self.selected_period,
                    self.display_text
                )
                await interaction.edit_original_response(attachments=[image_file], view=self.view)
            else:
                view = AverageServerStatsView(
                    self.cog,
                    self.start_time,
                    self.end_time,
                    self.days_back_equiv,
                    self.display_text,
                    role_id,
                    self.selected_period,
                    using_server_default=False
                )
                image_file = await self.cog.generate_server_stats_image(
                    interaction,
                    self.start_time,
                    self.end_time,
                    self.days_back_equiv,
                    role_id,
                    self.selected_period,
                    self.display_text
                )
                await interaction.edit_original_response(attachments=[image_file], view=view)

        except Exception as e:
            print(f"Error in role id modal submit: {e}")
            await interaction.followup.send("❌ An error occurred while updating the image.", ephemeral=True)

# TIME MODAL


class AverageTimeModal(discord.ui.Modal, title='Custom Time Period'):
    def __init__(self, cog_instance, start_time: datetime, end_time: datetime, days_back_equiv: int, display_text: str, selected_role_id: str = None, selected_period: str = "day", is_user_stats: bool = False, user_id: int = None, view=None):
        super().__init__(timeout=300)
        self.cog = cog_instance
        self.start_time = start_time
        self.end_time = end_time
        self.days_back_equiv = days_back_equiv
        self.display_text = display_text
        self.selected_role_id = selected_role_id
        self.selected_period = selected_period
        self.is_user_stats = is_user_stats
        self.user_id = user_id
        self.view = view

    days = discord.ui.TextInput(
        label='Enter number of days',
        placeholder='e.g., 7, 14, 30, 90, 2000...',
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

            # Determine display text based on days
            if days == 999999:
                new_display_text = "All Time"
                new_start_time = None
            else:
                new_display_text = f"{days} days"
                new_start_time = datetime.utcnow() - timedelta(days=days)

            new_end_time = datetime.utcnow()
            new_days_back_equiv = days

            await interaction.response.defer()

            if self.view:
                self.view.current_start_time = new_start_time
                self.view.current_end_time = new_end_time
                self.view.current_days_back_equiv = new_days_back_equiv
                self.view.current_display_text = new_display_text
                self.view.using_server_default = False
                self.view.show_time_buttons = False

                if self.is_user_stats:
                    image_file = await self.cog.generate_user_stats_image(interaction, new_start_time, new_end_time, new_days_back_equiv, self.user_id, self.selected_period, new_display_text)
                else:
                    image_file = await self.cog.generate_server_stats_image(interaction, new_start_time, new_end_time, new_days_back_equiv, self.selected_role_id, self.selected_period, new_display_text)

                self.view._update_buttons()
                await interaction.edit_original_response(attachments=[image_file], view=self.view)
            else:
                if self.is_user_stats:
                    image_file = await self.cog.generate_user_stats_image(interaction, new_start_time, new_end_time, new_days_back_equiv, self.user_id, self.selected_period, new_display_text)
                    view = AverageUserStatsView(
                        self.cog, new_start_time, new_end_time, new_days_back_equiv, new_display_text, self.user_id, self.selected_period, using_server_default=False)
                else:
                    image_file = await self.cog.generate_server_stats_image(interaction, new_start_time, new_end_time, new_days_back_equiv, self.selected_role_id, self.selected_period, new_display_text)
                    view = AverageServerStatsView(
                        self.cog, new_start_time, new_end_time, new_days_back_equiv, new_display_text, self.selected_role_id, self.selected_period, using_server_default=False)

                await interaction.edit_original_response(attachments=[image_file], view=view)

        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number.", ephemeral=True)
        except Exception as e:
            print(f"Error in average modal submit: {e}")
            await interaction.followup.send("❌ An error occurred while generating image.", ephemeral=True)


# SERVER STATS VIEW

class AverageServerStatsView(discord.ui.View):
    def __init__(self, cog_instance, start_time: datetime = None, end_time: datetime = None,
                 days_back_equiv: int = 30, display_text: str = "30 days", selected_role_id: str = None,
                 selected_period: str = "day", using_server_default: bool = True):
        super().__init__(timeout=600)
        self.cog = cog_instance
        self.current_start_time = start_time
        self.current_end_time = end_time if end_time else datetime.utcnow()
        self.current_days_back_equiv = days_back_equiv
        self.current_display_text = display_text
        self.selected_role_id = selected_role_id
        self.selected_period = selected_period
        self.show_time_buttons = False
        self.is_user_stats = False
        self.user_id = None
        self.using_server_default = using_server_default
        self._update_buttons()

    def _update_buttons(self):
        self.clear_items()

        self.add_item(TimePeriodSelect(self.selected_period))

        role_button = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="Input Role Id",
            custom_id="average_input_role_id"
        )
        role_button.callback = self.role_id_callback

        refresh_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="🔄 Refresh",
            custom_id="average_refresh"
        )
        refresh_button.callback = self.refresh_callback

        time_settings_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="⏰ Time Settings",
            custom_id="average_time_settings"
        )
        time_settings_button.callback = self.time_settings_callback

        self.add_item(role_button)
        self.add_item(refresh_button)
        self.add_item(time_settings_button)

        if self.show_time_buttons:
            all_time_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 999999 else discord.ButtonStyle.secondary,
                label="All Time",
                custom_id="average_all_time"
            )
            all_time_button.callback = self.all_time_callback
            self.add_item(all_time_button)

            days_7_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 7 else discord.ButtonStyle.secondary,
                label="7 Days",
                custom_id="average_days_7"
            )
            days_7_button.callback = self.days_7_callback

            days_14_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 14 else discord.ButtonStyle.secondary,
                label="14 Days",
                custom_id="average_days_14"
            )
            days_14_button.callback = self.days_14_callback

            days_30_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 30 else discord.ButtonStyle.secondary,
                label="30 Days",
                custom_id="average_days_30"
            )
            days_30_button.callback = self.days_30_callback

            # Use display text for custom button label
            custom_label = self.current_display_text if self.current_days_back_equiv not in [
                7, 14, 30, 999999] else "Custom"
            if len(custom_label) > 20:
                custom_label = custom_label[:17] + "..."
            custom_button = discord.ui.Button(
                style=discord.ButtonStyle.success,
                label=custom_label,
                custom_id="average_custom_days"
            )
            custom_button.callback = self.custom_days_callback

            self.add_item(days_7_button)
            self.add_item(days_14_button)
            self.add_item(days_30_button)
            self.add_item(custom_button)

    async def role_id_callback(self, interaction: discord.Interaction):
        try:
            modal = RoleIdModal(self.cog, self.current_start_time, self.current_end_time,
                                self.current_days_back_equiv, self.current_display_text,
                                self.selected_period, self)
            await interaction.response.send_modal(modal)
        except Exception as e:
            print(f"Error handling role id button: {e}")
            await interaction.followup.send("❌ An error occurred while opening role id modal.", ephemeral=True)

    async def days_7_callback(self, interaction: discord.Interaction):
        now = datetime.utcnow()
        self.current_start_time = now - timedelta(days=7)
        self.current_end_time = now
        self.current_days_back_equiv = 7
        self.current_display_text = "7 days"
        self.using_server_default = False
        self.show_time_buttons = False
        await self.update_message(interaction)

    async def days_14_callback(self, interaction: discord.Interaction):
        now = datetime.utcnow()
        self.current_start_time = now - timedelta(days=14)
        self.current_end_time = now
        self.current_days_back_equiv = 14
        self.current_display_text = "14 days"
        self.using_server_default = False
        self.show_time_buttons = False
        await self.update_message(interaction)

    async def days_30_callback(self, interaction: discord.Interaction):
        now = datetime.utcnow()
        self.current_start_time = now - timedelta(days=30)
        self.current_end_time = now
        self.current_days_back_equiv = 30
        self.current_display_text = "30 days"
        self.using_server_default = False
        self.show_time_buttons = False
        await self.update_message(interaction)

    async def all_time_callback(self, interaction: discord.Interaction):
        now = datetime.utcnow()
        self.current_start_time = None
        self.current_end_time = now
        self.current_days_back_equiv = 999999
        self.current_display_text = "All Time"
        self.using_server_default = False
        self.show_time_buttons = False
        await self.update_message(interaction)

    async def refresh_callback(self, interaction: discord.Interaction):
        await self.update_message(interaction)

    async def time_settings_callback(self, interaction: discord.Interaction):
        try:
            self.show_time_buttons = not self.show_time_buttons
            self._update_buttons()

            if interaction.response.is_done():
                await interaction.edit_original_response(view=self)
            else:
                await interaction.response.edit_message(view=self)

        except Exception as e:
            print(f"Error handling time settings: {e}")
            await interaction.followup.send("❌ An error occurred while updating time settings.", ephemeral=True)

    async def custom_days_callback(self, interaction: discord.Interaction):
        try:
            modal = AverageTimeModal(
                self.cog, self.current_start_time, self.current_end_time, self.current_days_back_equiv,
                self.current_display_text, self.selected_role_id, self.selected_period, False, None, self)
            await interaction.response.send_modal(modal)
        except Exception as e:
            print(f"Error handling custom days: {e}")
            await interaction.followup.send("❌ An error occurred while opening custom days modal.", ephemeral=True)

    async def update_message(self, interaction: discord.Interaction):
        try:
            image_file = await self.cog.generate_server_stats_image(
                interaction, self.current_start_time, self.current_end_time, self.current_days_back_equiv,
                self.selected_role_id, self.selected_period, self.current_display_text
            )
            self._update_buttons()

            if interaction.response.is_done():
                await interaction.edit_original_response(attachments=[image_file], view=self)
            else:
                await interaction.response.edit_message(attachments=[image_file], view=self)

        except Exception as e:
            print(f"Error updating average stats message: {e}")
            await interaction.followup.send("❌ An error occurred while updating the image.", ephemeral=True)


# USER STATS VIEW

class AverageUserStatsView(discord.ui.View):
    def __init__(self, cog_instance, start_time: datetime = None, end_time: datetime = None,
                 days_back_equiv: int = 30, display_text: str = "30 days", user_id: int = None,
                 selected_period: str = "day", using_server_default: bool = True):
        super().__init__(timeout=600)
        self.cog = cog_instance
        self.current_start_time = start_time
        self.current_end_time = end_time if end_time else datetime.utcnow()
        self.current_days_back_equiv = days_back_equiv
        self.current_display_text = display_text
        self.user_id = user_id
        self.selected_period = selected_period
        self.show_time_buttons = False
        self.is_user_stats = True
        self.selected_role_id = None
        self.using_server_default = using_server_default
        self._update_buttons()

    def _update_buttons(self):
        self.clear_items()

        self.add_item(TimePeriodSelect(self.selected_period))

        refresh_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="🔄 Refresh",
            custom_id="average_refresh"
        )
        refresh_button.callback = self.refresh_callback

        time_settings_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="⏰ Time Settings",
            custom_id="average_time_settings"
        )
        time_settings_button.callback = self.time_settings_callback

        self.add_item(refresh_button)
        self.add_item(time_settings_button)

        if self.show_time_buttons:
            all_time_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 999999 else discord.ButtonStyle.secondary,
                label="All Time",
                custom_id="average_all_time"
            )
            all_time_button.callback = self.all_time_callback
            self.add_item(all_time_button)

            days_7_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 7 else discord.ButtonStyle.secondary,
                label="7 Days",
                custom_id="average_days_7"
            )
            days_7_button.callback = self.days_7_callback

            days_14_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 14 else discord.ButtonStyle.secondary,
                label="14 Days",
                custom_id="average_days_14"
            )
            days_14_button.callback = self.days_14_callback

            days_30_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 30 else discord.ButtonStyle.secondary,
                label="30 Days",
                custom_id="average_days_30"
            )
            days_30_button.callback = self.days_30_callback

            # Use display text for custom button label
            custom_label = self.current_display_text if self.current_days_back_equiv not in [
                7, 14, 30, 999999] else "Custom"
            if len(custom_label) > 20:
                custom_label = custom_label[:17] + "..."
            custom_button = discord.ui.Button(
                style=discord.ButtonStyle.success,
                label=custom_label,
                custom_id="average_custom_days"
            )
            custom_button.callback = self.custom_days_callback

            self.add_item(days_7_button)
            self.add_item(days_14_button)
            self.add_item(days_30_button)
            self.add_item(custom_button)

    async def days_7_callback(self, interaction: discord.Interaction):
        now = datetime.utcnow()
        self.current_start_time = now - timedelta(days=7)
        self.current_end_time = now
        self.current_days_back_equiv = 7
        self.current_display_text = "7 days"
        self.using_server_default = False
        self.show_time_buttons = False
        await self.update_message(interaction)

    async def days_14_callback(self, interaction: discord.Interaction):
        now = datetime.utcnow()
        self.current_start_time = now - timedelta(days=14)
        self.current_end_time = now
        self.current_days_back_equiv = 14
        self.current_display_text = "14 days"
        self.using_server_default = False
        self.show_time_buttons = False
        await self.update_message(interaction)

    async def days_30_callback(self, interaction: discord.Interaction):
        now = datetime.utcnow()
        self.current_start_time = now - timedelta(days=30)
        self.current_end_time = now
        self.current_days_back_equiv = 30
        self.current_display_text = "30 days"
        self.using_server_default = False
        self.show_time_buttons = False
        await self.update_message(interaction)

    async def all_time_callback(self, interaction: discord.Interaction):
        now = datetime.utcnow()
        self.current_start_time = None
        self.current_end_time = now
        self.current_days_back_equiv = 999999
        self.current_display_text = "All Time"
        self.using_server_default = False
        self.show_time_buttons = False
        await self.update_message(interaction)

    async def refresh_callback(self, interaction: discord.Interaction):
        await self.update_message(interaction)

    async def time_settings_callback(self, interaction: discord.Interaction):
        try:
            self.show_time_buttons = not self.show_time_buttons
            self._update_buttons()

            if interaction.response.is_done():
                await interaction.edit_original_response(view=self)
            else:
                await interaction.response.edit_message(view=self)

        except Exception as e:
            print(f"Error handling time settings: {e}")
            await interaction.followup.send("❌ An error occurred while updating time settings.", ephemeral=True)

    async def custom_days_callback(self, interaction: discord.Interaction):
        try:
            modal = AverageTimeModal(
                self.cog, self.current_start_time, self.current_end_time, self.current_days_back_equiv,
                self.current_display_text, None, self.selected_period, True, self.user_id, self)
            await interaction.response.send_modal(modal)
        except Exception as e:
            print(f"Error handling custom days: {e}")
            await interaction.followup.send("❌ An error occurred while opening custom days modal.", ephemeral=True)

    async def update_message(self, interaction: discord.Interaction):
        try:
            image_file = await self.cog.generate_user_stats_image(
                interaction, self.current_start_time, self.current_end_time, self.current_days_back_equiv,
                self.user_id, self.selected_period, self.current_display_text
            )
            self._update_buttons()

            if interaction.response.is_done():
                await interaction.edit_original_response(attachments=[image_file], view=self)
            else:
                await interaction.response.edit_message(attachments=[image_file], view=self)

        except Exception as e:
            print(f"Error updating average stats message: {e}")
            await interaction.followup.send("❌ An error occurred while updating the image.", ephemeral=True)


# INITIALIZATION

class AverageStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_cog = None
        self.activity_cog = None
        self.settings_cog = None
        self.current_guild = None
        self.active_sessions = {}
        self.rate_limiter = get_rate_limiter()

        self.font_path = BASE_DIR / "assets" / "fonts" / "HorndonD.ttf"
        self.server_background_path = BASE_DIR / "assets" / \
            "images" / "averages server final png.png"
        self.user_background_path = BASE_DIR / "assets" / \
            "images" / "averages user final png.png"

        # POSITIONS
        self.SERVER_UI_POSITIONS = {
            'avatar': {'x': 7, 'y': 10, 'size': (60, 60)},
            'text_start': {'x': 75, 'y': 30},
            'username_rectangle': {'center': (120, 30), 'width': 183, 'height': 35}
        }

        self.COMPATIBILITY_UI_POSITIONS = {
            'avatar': {'x': 7, 'y': 7, 'size': (60, 60)},
            'text_start': {'x': 75, 'y': 27},
            'username_rectangle': {'center': (130, 27), 'width': 183, 'height': 35}
        }

    async def cog_load(self):
        self.db_cog = self.bot.get_cog('DatabaseStats')
        self.activity_cog = self.bot.get_cog('ActivityTracker')
        if not self.db_cog:
            print(
                "❌ DatabaseStats cog not found! AverageStats requires DatabaseStats to function.")
        if not self.activity_cog:
            print(
                "⚠️ ActivityTracker cog not found! Activity stats will not work properly.")

    # GET SERVER DEFAULT TIME RANGE
    # GET SERVER DEFAULT TIME RANGE
    async def get_server_default_time_range(self, guild_id: int) -> tuple:
        """Get the default time range from server settings. Returns (start_time, end_time, display_text, days_back_equiv)"""
        try:
            settings_cog = self.bot.get_cog('Settings')
            if not settings_cog:
                end = datetime.now(timezone.utc)
                start = end - timedelta(days=30)
                return (start, end, "30 days", 30)

            settings = await settings_cog.get_guild_settings(guild_id)
            mode = settings.get('default_time_mode', 'days_back')
            now = datetime.now(timezone.utc)

            if mode == 'all_time':
                return (None, now, "All Time", 999999)

            elif mode == 'days_back':
                days = settings.get('default_days_back') or 30
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
            start = now - timedelta(days=30)
            return (start, end, "30 days", 30)

        except Exception as e:
            import traceback
            traceback.print_exc()
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=30)
            return (start, end, "30 days", 30)

    # =========================================================
    # INTERNAL FUNCTION FOR BOTH USER COMMAND TYPES
    # =========================================================
    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def _handle_user_stats_command(self, ctx_or_interaction, user=None, is_interaction=False):
        """Internal function to handle user stats for both command types"""
        try:
            # Get context parameters
            if is_interaction:
                interaction = ctx_or_interaction
                author = interaction.user
                guild = interaction.guild
                send_method = interaction.followup.send
                original_message = None
            else:
                ctx = ctx_or_interaction
                author = ctx.author
                guild = ctx.guild
                try:
                    await ctx.message.delete()
                except:
                    pass
                send_method = ctx.send
                original_message = None

            # Handle user parameter
            if user is None:
                user = author

            if guild is None:
                if is_interaction:
                    await ctx_or_interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
                else:
                    await ctx_or_interaction.send("❌ This command can only be used in a server.", delete_after=5)
                return

            # Check permission
            if not await self.check_command_permission(ctx_or_interaction if is_interaction else None, author, user.id):
                if is_interaction:
                    await self.send_permission_error(ctx_or_interaction, user.id)
                else:
                    embed = discord.Embed(
                        title="❌ Permission Denied",
                        description="Sorry! You don't have permission to use this command.",
                        color=discord.Color.red()
                    )
                    await ctx_or_interaction.send(embed=embed, delete_after=10)
                return

            if not self.db_cog:
                self.db_cog = self.bot.get_cog('DatabaseStats')
                if not self.db_cog:
                    if is_interaction:
                        await ctx_or_interaction.followup.send(
                            "❌ DatabaseStats cog is not loaded. AverageStats requires DatabaseStats to function.",
                            ephemeral=True
                        )
                    else:
                        await ctx_or_interaction.send(
                            "❌ DatabaseStats cog is not loaded. AverageStats requires DatabaseStats to function.",
                            delete_after=10
                        )
                    return

            # Get server default time range
            start_time, end_time, display_text, days_back_equiv = await self.get_server_default_time_range(guild.id)
            period = "day"

            if is_interaction:
                await ctx_or_interaction.response.defer()

            # Generate stats image
            try:
                if is_interaction:
                    image_file = await self.generate_user_stats_image(ctx_or_interaction, start_time, end_time, days_back_equiv, user.id, period, display_text)
                else:
                    # Create a mock interaction for context
                    class MockInteraction:
                        def __init__(self, guild, author):
                            self.guild = guild
                            self.user = author
                            self.response = type('obj', (object,), {
                                                 'is_done': lambda: False})()

                    mock_interaction = MockInteraction(guild, author)
                    image_file = await self.generate_user_stats_image(mock_interaction, start_time, end_time, days_back_equiv, user.id, period, display_text)

                view = AverageUserStatsView(
                    self, start_time, end_time, days_back_equiv, display_text, user.id, period, using_server_default=True)

                # Send the image
                retention_alert_text = await self.db_cog.maybe_get_retention_alert(guild.id) if self.db_cog else None
                if is_interaction:
                    msg = await send_method(content=retention_alert_text, file=image_file, view=view)
                else:
                    msg = await send_method(content=retention_alert_text, file=image_file, view=view, delete_after=300)

            except Exception as e:
                print(f"Error generating user stats image: {e}")
                if is_interaction:
                    await ctx_or_interaction.followup.send(
                        "❌ An error occurred while generating statistics image. Please try again later.",
                        ephemeral=True
                    )
                else:
                    await ctx_or_interaction.send(
                        "❌ An error occurred while generating statistics image. Please try again later.",
                        delete_after=10
                    )

        except Exception as e:
            print(f"Error in _handle_user_stats_command: {e}")
            if is_interaction:
                try:
                    await ctx_or_interaction.followup.send("❌ An error occurred while generating stats image.", ephemeral=True)
                except:
                    pass
            else:
                try:
                    await ctx_or_interaction.send("❌ An error occurred while generating stats image.", delete_after=10)
                except:
                    pass

    # =========================================================
    # INTERNAL FUNCTION FOR BOTH SERVER COMMAND TYPES
    # =========================================================
    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def _handle_server_stats_command(self, ctx_or_interaction, is_interaction=False):
        """Internal function to handle server stats for both command types"""
        try:
            # Get context parameters
            if is_interaction:
                interaction = ctx_or_interaction
                author = interaction.user
                guild = interaction.guild
                send_method = interaction.followup.send
            else:
                ctx = ctx_or_interaction
                author = ctx.author
                guild = ctx.guild
                try:
                    await ctx.message.delete()
                except:
                    pass
                send_method = ctx.send

            if guild is None:
                if is_interaction:
                    await ctx_or_interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
                else:
                    await ctx_or_interaction.send("❌ This command can only be used in a server.", delete_after=5)
                return

            # Check permission
            if not await self.check_command_permission(ctx_or_interaction if is_interaction else None, author):
                if is_interaction:
                    await self.send_permission_error(ctx_or_interaction)
                else:
                    embed = discord.Embed(
                        title="❌ Permission Denied",
                        description="Sorry! You don't have permission to use this command.",
                        color=discord.Color.red()
                    )
                    await ctx_or_interaction.send(embed=embed, delete_after=10)
                return

            if not self.db_cog:
                self.db_cog = self.bot.get_cog('DatabaseStats')
                if not self.db_cog:
                    if is_interaction:
                        await ctx_or_interaction.followup.send(
                            "❌ DatabaseStats cog is not loaded. AverageStats requires DatabaseStats to function.",
                            ephemeral=True
                        )
                    else:
                        await ctx_or_interaction.send(
                            "❌ DatabaseStats cog is not loaded. AverageStats requires DatabaseStats to function.",
                            delete_after=10
                        )
                    return

            # Get server default time range
            start_time, end_time, display_text, days_back_equiv = await self.get_server_default_time_range(guild.id)
            role_id = None
            period = "day"

            if is_interaction:
                await ctx_or_interaction.response.defer()

            # Generate stats image
            try:
                if is_interaction:
                    image_file = await self.generate_server_stats_image(ctx_or_interaction, start_time, end_time, days_back_equiv, role_id, period, display_text)
                else:
                    # Create a mock interaction for context
                    class MockInteraction:
                        def __init__(self, guild, author):
                            self.guild = guild
                            self.user = author
                            self.response = type('obj', (object,), {
                                                 'is_done': lambda: False})()

                    mock_interaction = MockInteraction(guild, author)
                    image_file = await self.generate_server_stats_image(mock_interaction, start_time, end_time, days_back_equiv, role_id, period, display_text)

                view = AverageServerStatsView(
                    self, start_time, end_time, days_back_equiv, display_text, role_id, period, using_server_default=True)

                # Send the image
                retention_alert_text = await self.db_cog.maybe_get_retention_alert(guild.id) if self.db_cog else None
                if is_interaction:
                    msg = await send_method(content=retention_alert_text, file=image_file, view=view)
                else:
                    msg = await send_method(content=retention_alert_text, file=image_file, view=view, delete_after=300)

            except Exception as e:
                print(f"Error generating server stats image: {e}")
                if is_interaction:
                    await ctx_or_interaction.followup.send(
                        "❌ An error occurred while generating statistics image. Please try again later.",
                        ephemeral=True
                    )
                else:
                    await ctx_or_interaction.send(
                        "❌ An error occurred while generating statistics image. Please try again later.",
                        delete_after=10
                    )

        except Exception as e:
            print(f"Error in _handle_server_stats_command: {e}")
            if is_interaction:
                try:
                    await ctx_or_interaction.followup.send("❌ An error occurred while generating stats image.", ephemeral=True)
                except:
                    pass
            else:
                try:
                    await ctx_or_interaction.send("❌ An error occurred while generating stats image.", delete_after=10)
                except:
                    pass

    # =========================================================
    # SHORTCUT COMMANDS
    # =========================================================
    @commands.command(name="avs")
    async def average_server_shortcut(self, ctx: commands.Context):
        """Shortcut command for average server stats - same as average server"""
        await self._handle_server_stats_command(ctx, is_interaction=False)

    @commands.command(name="avu")
    async def average_user_shortcut(self, ctx: commands.Context, user: discord.User = None):
        """Shortcut command for average user stats - same as average user"""
        await self._handle_user_stats_command(ctx, user, is_interaction=False)

    # =========================================================
    # PREFIX COMMAND GROUP
    # =========================================================
    @commands.group(name="average", invoke_without_command=True)
    async def average_group_prefix(self, ctx: commands.Context):
        """Average statistics commands"""
        await ctx.send("Available commands:\n- `average server` - Show average statistics for the server\n- `average user [user]` - Show average statistics for a user\n- `avs` - Shortcut for average server\n- `avu [user]` - Shortcut for average user")

    @average_group_prefix.command(name="server")
    async def average_server_prefix(self, ctx: commands.Context):
        """Show average statistics for the server via prefix command"""
        await self._handle_server_stats_command(ctx, is_interaction=False)

    @average_group_prefix.command(name="user")
    async def average_user_prefix(self, ctx: commands.Context, user: discord.User = None):
        """Show average statistics for a specific user via prefix command"""
        await self._handle_user_stats_command(ctx, user, is_interaction=False)

    # PERMISSION CHECK FUNCTIONS
    async def _get_settings_cog(self):
        """Get settings cog with retry mechanism"""
        if not self.settings_cog:
            self.settings_cog = self.bot.get_cog('Settings')
            if not self.settings_cog:
                await asyncio.sleep(0.5)
                self.settings_cog = self.bot.get_cog('Settings')
        return self.settings_cog

    async def check_command_permission(self, interaction: discord.Interaction, user: discord.Member = None, target_user_id: int = None) -> bool:
        """Check if user has permission to use average commands based on server settings"""
        if user is None and interaction:
            user = interaction.user

        # Users with administrator permission always have access
        if user.guild_permissions.administrator:
            return True

        # Try to get settings cog
        settings_cog = await self._get_settings_cog()

        if settings_cog:
            try:
                settings = await settings_cog.get_guild_settings(user.guild.id)
                permission_level = settings.get('permission_level', 'Default')
            except Exception as e:
                print(f"Error getting settings: {e}")
                permission_level = 'Default'
        else:
            print("⚠️ Settings cog not available, using default permissions")
            permission_level = 'Default'

        # Check based on permission level
        if permission_level == 'All':
            return True
        elif permission_level == 'Admin':
            return user.guild_permissions.administrator
        elif permission_level == 'Moderator':
            return user.guild_permissions.manage_guild
        elif permission_level == 'Default':
            return True
        elif permission_level == 'User Restriction':
            if target_user_id:
                return user.id == target_user_id
            return True

        return True

    async def send_permission_error(self, interaction: discord.Interaction, target_user_id: int = None):
        """Send appropriate permission error message"""
        settings_cog = await self._get_settings_cog()

        if settings_cog:
            try:
                settings = await settings_cog.get_guild_settings(interaction.guild.id)
                permission_level = settings.get('permission_level', 'Default')
            except Exception as e:
                print(f"Error getting settings for error message: {e}")
                permission_level = 'Default'
        else:
            permission_level = 'Default'

        if permission_level == 'User Restriction' and target_user_id and interaction.user.id != target_user_id:
            embed = discord.Embed(
                title="❌ Permission Denied",
                description="Sorry! You can only use this command on yourself.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            if permission_level == 'Admin':
                required_permission = "Administrator"
            elif permission_level == 'Moderator':
                required_permission = "Manage Server"
            elif permission_level == 'Default':
                required_permission = "Administrator or Manage Server"
            else:
                required_permission = "Administrator"

            embed = discord.Embed(
                title="❌ Permission Denied",
                description=f"Sorry! You need the `{required_permission}` permission to access this command.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _filter_members_by_role(self, guild: discord.Guild, role_id: str):
        if role_id == "none" or not role_id:
            return None

        role = guild.get_role(int(role_id))
        if not role:
            return None

        return [str(member.id) for member in role.members]

    # FORMAT
    def _format_number_for_period(self, daily_average: float, period: str) -> str:
        if period == "day":
            return f"{daily_average:.1f}/day"
        elif period == "week":
            return f"{(daily_average * 7):.1f}/week"
        elif period == "month":
            return f"{(daily_average * 30):.1f}/month"
        return f"{daily_average:.1f}/day"

    # IMAGE HELPER FUNCTIONS
    def _draw_text_with_stroke(self, draw, position, text, font, fill_color, stroke_color, stroke_width=2, max_width=None):
        current_font = font
        text_width = draw.textlength(text, font=current_font)

        if max_width and text_width > max_width:
            font_size = int(font.size * 0.9)
            while font_size > 10 and text_width > max_width:
                try:
                    current_font = ImageFont.truetype(
                        self.font_path, font_size)
                    text_width = draw.textlength(text, font=current_font)
                    font_size = int(font_size * 0.9)
                except:
                    break

        x, y = position

        for dx in [-stroke_width, 0, stroke_width]:
            for dy in [-stroke_width, 0, stroke_width]:
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), text,
                              font=current_font, fill=stroke_color)

        draw.text((x, y), text, font=current_font, fill=fill_color)
        return current_font

    def _fit_text_to_rectangle(self, draw, text, text_start_x, text_start_y, rect_center_x, rect_center_y, rect_width, rect_height, is_username=False):
        font_paths = [self.font_path]
        font_sizes = [32, 30, 28, 26, 24, 22, 20, 18, 17, 16, 15, 14, 13]

        rect_left = rect_center_x - (rect_width // 2)
        rect_right = rect_center_x + (rect_width // 2)
        rect_top = rect_center_y - (rect_height // 2)
        rect_bottom = rect_center_y + (rect_height // 2)

        for font_size in font_sizes:
            try:
                font = ImageFont.truetype(font_paths[0], font_size) if os.path.exists(
                    font_paths[0]) else ImageFont.load_default()
            except:
                font = ImageFont.load_default()

            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

            text_x = text_start_x
            text_y = text_start_y - (text_height // 2)

            vertical_offset = 0
            if font_size <= 40:
                vertical_offset += 1
            if font_size <= 30:
                vertical_offset += 1
            if font_size <= 20:
                vertical_offset += 1
            if font_size <= 16:
                vertical_offset += 1
            text_y += vertical_offset

            text_fits_horizontally = (
                text_x >= rect_left - 1) and (text_x + text_width <= rect_right + 1)
            text_fits_vertically = (
                text_y >= rect_top - 1) and (text_y + text_height <= rect_bottom + 1)

            if text_fits_horizontally and text_fits_vertically:
                return text, font, (text_x, text_y)

        smallest_font = 16
        try:
            font = ImageFont.truetype(font_paths[0], smallest_font) if os.path.exists(
                font_paths[0]) else ImageFont.load_default()
        except:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        text_x = text_start_x
        text_y = text_start_y - (text_height // 2)

        vertical_offset = 0
        if smallest_font <= 40:
            vertical_offset += 1
        if smallest_font <= 30:
            vertical_offset += 1
        if smallest_font <= 20:
            vertical_offset += 1
        if smallest_font <= 16:
            vertical_offset += 1
        text_y += vertical_offset

        text_fits_horizontally = (
            text_x >= rect_left - 1) and (text_x + text_width <= rect_right + 1)
        text_fits_vertically = (
            text_y >= rect_top - 1) and (text_y + text_height <= rect_bottom + 1)

        if text_fits_horizontally and text_fits_vertically:
            return text, font, (text_x, text_y)

        current_text = text
        while len(current_text) > 3:
            current_text = current_text[:-4] + "..."
            bbox = draw.textbbox((0, 0), current_text, font=font)
            text_width = bbox[2] - bbox[0]

            text_x = text_start_x
            text_y = text_start_y - (text_height // 2)
            text_y += vertical_offset

            if (text_x >= rect_left - 1) and (text_x + text_width <= rect_right + 1):
                return current_text, font, (text_x, text_y)

        if len(text) > 3:
            final_text = text[:3] + "..."
        else:
            final_text = text

        bbox = draw.textbbox((0, 0), final_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        text_x = text_start_x
        text_y = text_start_y - (text_height // 2)
        text_y += vertical_offset

        return final_text, font, (text_x, text_y)

    async def _add_profile_pic_and_name(self, image, draw, interaction, target_name, is_user_stats, user=None):
        if is_user_stats:
            positions = self.COMPATIBILITY_UI_POSITIONS
        else:
            positions = self.SERVER_UI_POSITIONS

        avatar_x, avatar_y = positions['avatar']['x'], positions['avatar']['y']
        avatar_size = positions['avatar']['size']

        text_start_x = positions['text_start']['x']
        text_start_y = positions['text_start']['y']

        username_rectangle = positions['username_rectangle']

        # PROFILE PICTURE
        try:
            if is_user_stats and user and user.avatar:
                icon_url = user.avatar.url
            elif not is_user_stats and interaction.guild.icon:
                icon_url = interaction.guild.icon.url
            else:
                icon_url = None

            if icon_url:
                async with aiohttp.ClientSession() as session:
                    async with session.get(icon_url) as response:
                        icon_data = await response.read()

                icon_image = Image.open(io.BytesIO(icon_data))
                icon_image = icon_image.resize(
                    avatar_size, Image.Resampling.LANCZOS).convert('RGBA')

                mask = Image.new('L', avatar_size, 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.ellipse(
                    (0, 0, avatar_size[0], avatar_size[1]), fill=255)
                icon_image.putalpha(mask)

                avatar_area = image.crop(
                    (avatar_x, avatar_y, avatar_x +
                     avatar_size[0], avatar_y + avatar_size[1])
                ).convert('RGBA')

                icon_with_bg = Image.new('RGBA', avatar_size, (0, 0, 0, 0))
                icon_with_bg.paste(icon_image, (0, 0), icon_image)
                avatar_area.paste(icon_with_bg, (0, 0), icon_with_bg)
                image.paste(avatar_area.convert('RGB'), (avatar_x, avatar_y))
                icon_image.close()
                del icon_image
                del icon_data

        except Exception as e:
            print(f"Could not add profile icon: {e}")

        fitted_text, text_font, text_pos = self._fit_text_to_rectangle(
            draw,
            target_name,
            text_start_x,
            text_start_y,
            username_rectangle["center"][0],
            username_rectangle["center"][1],
            username_rectangle["width"],
            username_rectangle["height"],
            is_username=True
        )

        if fitted_text and text_font:
            stroke_width = 1
            for dx in [-stroke_width, 0, stroke_width]:
                for dy in [-stroke_width, 0, stroke_width]:
                    if dx != 0 or dy != 0:
                        draw.text((text_pos[0] + dx, text_pos[1] + dy),
                                  fitted_text, font=text_font, fill="black")
            draw.text(text_pos, fitted_text, font=text_font, fill="white")
        else:
            try:
                font_huge = ImageFont.truetype(self.font_path, 40) if os.path.exists(
                    self.font_path) else ImageFont.load_default()
            except:
                font_huge = ImageFont.load_default()
            draw.text((text_start_x, text_start_y),
                      target_name, font=font_huge, fill="white")
            gc.collect()

    # QUERY FUNCTIONS
    async def generate_server_stats_image(self, interaction: discord.Interaction, start_time: datetime = None, end_time: datetime = None,
                                          days_back_equiv: int = 30, role_id: str = None, period: str = "day", display_text: str = None) -> discord.File:
        guild_id = interaction.guild.id
        self.current_guild = interaction.guild
        now = datetime.utcnow()

        # Use the provided display_text, or create from days_back_equiv
        if display_text is None:
            if days_back_equiv == 999999:
                display_text = "All Time"
            else:
                display_text = f"{days_back_equiv} days"

        role_filter_ids = None
        if role_id and role_id != "none":
            role_filter_ids = await self._filter_members_by_role(interaction.guild, role_id)
            if role_filter_ids:
                role_filter_ids = [int(uid) for uid in role_filter_ids]

        # Get role name from database for display
        role_name = None
        if role_id and role_id != "none":
            db_stats = self.db_cog
            if db_stats and db_stats.pool:
                try:
                    async with db_stats.pool.acquire() as conn:
                        row = await conn.fetchrow("""
                            SELECT role_name FROM current_role_members 
                            WHERE role_id = $1 AND guild_id = $2 
                            LIMIT 1
                        """, int(role_id), guild_id)
                        if row:
                            role_name = row['role_name']
                except:
                    pass

        try:
            # Calculate effective days for averaging (for All Time, we need to get the actual date range from data)
            effective_days = days_back_equiv
            if days_back_equiv == 999999:
                # For All Time, calculate based on actual data range
                try:
                    async with self.db_cog.pool.acquire() as conn:
                        # Get the oldest recorded date for this guild
                        oldest = await conn.fetchval("""
                            SELECT MIN(hour) FROM activity_sessions_hourly 
                            WHERE guild_id = $1
                        """, guild_id)
                        if oldest:
                            effective_days = max(1, (now - oldest).days)
                except:
                    pass

            # Messages - using hourly aggregated table
            messages_result = await self.db_cog.q_server_total_messages(
                guild_id=guild_id,
                role_filter_ids=role_filter_ids,
                start_time=start_time,
                end_time=end_time
            )
            total_messages = messages_result.get('total_messages', 0)
            avg_messages_per_day = total_messages / \
                effective_days if effective_days > 0 else 0

            # Emojis - using hourly aggregated table
            emojis_result = await self.db_cog.q_emoji_server_leaderboard(
                guild_id=guild_id,
                role_filter_ids=role_filter_ids,
                start_time=start_time,
                end_time=end_time,
                limit=100
            )
            total_emojis = sum(emoji['usage_count'] for emoji in emojis_result)
            avg_emojis_per_day = total_emojis / effective_days if effective_days > 0 else 0

            # Voice - using hourly aggregated table
            voice_result = await self.db_cog.q_server_total_voice(
                guild_id=guild_id,
                role_filter_ids=role_filter_ids,
                start_time=start_time,
                end_time=end_time
            )
            total_voice_minutes = voice_result.get('total_seconds', 0) / 60
            avg_voice_per_day = total_voice_minutes / \
                effective_days if effective_days > 0 else 0

            # Invites - using static table
            invites_result = await self.db_cog.q_invite_leaderboard(
                guild_id=guild_id,
                role_filter_ids=role_filter_ids,
                start_time=start_time,
                end_time=end_time,
                limit=100
            )
            total_invites = sum(invite['valid_invites']
                                for invite in invites_result)
            avg_invites_per_day = total_invites / effective_days if effective_days > 0 else 0

            # Activities - using ActivityTracker's helper
            activity_cog = self.bot.get_cog('ActivityTracker')
            if activity_cog and activity_cog.db:
                role_id_int = int(
                    role_id) if role_id and role_id != "none" else None
                total_activities = await activity_cog.db.get_server_total_activity_sessions(
                    guild_id=guild_id,
                    start_time=start_time,
                    end_time=end_time,
                    role_id=role_id_int
                )
            else:
                total_activities = 0
            avg_activities_per_day = total_activities / \
                effective_days if effective_days > 0 else 0

            return await self._create_stats_image(
                interaction=interaction,
                display_text=display_text,
                period=period,
                messages_avg=avg_messages_per_day,
                total_messages=total_messages,
                voice_avg=avg_voice_per_day,
                total_voice=total_voice_minutes,
                emoji_avg=avg_emojis_per_day,
                total_emojis=total_emojis,
                invite_avg=avg_invites_per_day,
                total_invites=total_invites,
                activity_avg=avg_activities_per_day,
                total_activities=total_activities,
                is_user_stats=False,
                role_id=role_id,
                role_name=role_name
            )

        except Exception as e:
            print(f"Error generating server stats image: {e}")
            import traceback
            traceback.print_exc()
            return await self._create_error_image(interaction)

    async def generate_user_stats_image(self, interaction: discord.Interaction, start_time: datetime = None, end_time: datetime = None,
                                        days_back_equiv: int = 30, user_id: int = None, period: str = "day", display_text: str = None) -> discord.File:
        guild_id = interaction.guild.id
        self.current_guild = interaction.guild
        now = datetime.utcnow()

        # Use the provided display_text, or create from days_back_equiv
        if display_text is None:
            if days_back_equiv == 999999:
                display_text = "All Time"
            else:
                display_text = f"{days_back_equiv} days"

        try:
            # Calculate effective days for All Time
            effective_days = days_back_equiv
            if days_back_equiv == 999999:
                # For All Time, calculate based on actual data range
                try:
                    async with self.db_cog.pool.acquire() as conn:
                        # Get the oldest recorded date for this user in this guild
                        oldest = await conn.fetchval("""
                            SELECT MIN(hour) FROM activity_sessions_hourly 
                            WHERE guild_id = $1 AND user_id = $2
                        """, guild_id, user_id)
                        if oldest:
                            effective_days = max(1, (now - oldest).days)
                except:
                    pass

            # Messages - using hourly aggregated table
            messages_result = await self.db_cog.q_user_total_messages(
                guild_id=guild_id,
                user_id=user_id,
                start_time=start_time,
                end_time=end_time
            )
            total_messages = messages_result.get('total_messages', 0)
            avg_messages_per_day = total_messages / \
                effective_days if effective_days > 0 else 0

            # Emojis - using hourly aggregated table
            user_emojis = await self.db_cog.q_user_top_emojis(
                guild_id=guild_id,
                user_id=user_id,
                limit=100,
                start_time=start_time,
                end_time=end_time
            )
            total_emojis = sum(emoji['usage_count'] for emoji in user_emojis)
            avg_emojis_per_day = total_emojis / effective_days if effective_days > 0 else 0

            # Voice - using hourly aggregated table
            voice_result = await self.db_cog.q_user_total_voice(
                guild_id=guild_id,
                user_id=user_id,
                start_time=start_time,
                end_time=end_time
            )
            total_voice_minutes = voice_result.get('total_seconds', 0) / 60
            avg_voice_per_day = total_voice_minutes / \
                effective_days if effective_days > 0 else 0

            # Invites - using static table
            invites_result = await self.db_cog.q_user_invite_stats(
                guild_id=guild_id,
                user_id=user_id,
                start_time=start_time,
                end_time=end_time
            )
            total_invites = invites_result.get('valid_invites', 0)
            avg_invites_per_day = total_invites / effective_days if effective_days > 0 else 0

            # Activities - using ActivityTracker's helper
            activity_cog = self.bot.get_cog('ActivityTracker')
            if activity_cog and activity_cog.db:
                total_activities = await activity_cog.db.get_user_total_activity_sessions(
                    guild_id=guild_id,
                    user_id=user_id,
                    start_time=start_time,
                    end_time=end_time
                )
            else:
                total_activities = 0
            avg_activities_per_day = total_activities / \
                effective_days if effective_days > 0 else 0

            user = interaction.guild.get_member(user_id)
            username = user.name if user else f"User {user_id}"

            return await self._create_stats_image(
                interaction=interaction,
                display_text=display_text,
                period=period,
                messages_avg=avg_messages_per_day,
                total_messages=total_messages,
                voice_avg=avg_voice_per_day,
                total_voice=total_voice_minutes,
                emoji_avg=avg_emojis_per_day,
                total_emojis=total_emojis,
                invite_avg=avg_invites_per_day,
                total_invites=total_invites,
                activity_avg=avg_activities_per_day,
                total_activities=total_activities,
                is_user_stats=True,
                user_id=user_id,
                username=username
            )

        except Exception as e:
            print(f"Error generating user stats image: {e}")
            import traceback
            traceback.print_exc()
            return await self._create_error_image(interaction)

    # IMAGE GENERATION
    async def _create_stats_image(self, interaction: discord.Interaction, display_text: str, period: str,
                                  messages_avg: float, total_messages: int,
                                  voice_avg: float, total_voice: float,
                                  emoji_avg: float, total_emojis: int,
                                  invite_avg: float, total_invites: int,
                                  activity_avg: float, total_activities: int,
                                  is_user_stats: bool = False,
                                  user_id: int = None,
                                  username: str = "",
                                  role_id: str = None,
                                  role_name: str = None) -> discord.File:
        try:
            background_path = self.user_background_path if is_user_stats else self.server_background_path
            image = Image.open(background_path)
            draw = ImageDraw.Draw(image)

            try:
                font_huge = ImageFont.truetype(self.font_path, 40)
                font_medium = ImageFont.truetype(self.font_path, 30)
                font_small = ImageFont.truetype(self.font_path, 16)
            except Exception as font_error:
                print(f"Font loading error: {font_error}")
                font_huge = ImageFont.load_default()
                font_medium = ImageFont.load_default()
                font_small = ImageFont.load_default()

            if is_user_stats:
                target_name = username
                user_obj = interaction.guild.get_member(user_id)
            else:
                target_name = interaction.guild.name
                user_obj = None

            await self._add_profile_pic_and_name(
                image, draw, interaction, target_name, is_user_stats, user_obj
            )

            # ROLE FILTER
            if is_user_stats:
                role_text = ""
            else:
                role_text = role_name if role_name else "No Filter"

            self._draw_text_with_stroke(draw, (70, 424), role_text,
                                        font_small, "white", "black", 1)

            # Time period - use display_text directly
            self._draw_text_with_stroke(
                draw, (630, 424), display_text, font_small, "white", "black", 1)
            self._draw_text_with_stroke(draw, (550, 38), datetime.now().strftime(
                "%B %d, %Y"), font_small, "white", "black", 1)

            # Format numbers based on period
            messages_formatted = self._format_number_for_period(
                messages_avg, period)
            voice_formatted = self._format_number_for_period(voice_avg, period)
            emoji_formatted = self._format_number_for_period(emoji_avg, period)
            invite_formatted = self._format_number_for_period(
                invite_avg, period)
            activity_formatted = self._format_number_for_period(
                activity_avg, period)

            # Messages
            self._draw_text_with_stroke(
                draw, (25, 130), messages_formatted, font_medium, "white", "black", max_width=200)
            self._draw_text_with_stroke(
                draw, (25, 165), f"{total_messages:,}", font_medium, "white", "black", max_width=200)

            # Voice
            self._draw_text_with_stroke(
                draw, (270, 130), voice_formatted, font_medium, "white", "black", max_width=200)
            self._draw_text_with_stroke(
                draw, (270, 165), f"{total_voice:.0f}", font_medium, "white", "black", max_width=200)

            # Emojis
            self._draw_text_with_stroke(
                draw, (515, 130), emoji_formatted, font_medium, "white", "black", max_width=200)
            self._draw_text_with_stroke(
                draw, (515, 165), f"{total_emojis:,}", font_medium, "white", "black", max_width=200)

            # Invites
            self._draw_text_with_stroke(
                draw, (100, 285), invite_formatted, font_medium, "white", "black", max_width=200)
            self._draw_text_with_stroke(
                draw, (100, 335), f"{total_invites:,}", font_medium, "white", "black", max_width=200)

            # Activities
            self._draw_text_with_stroke(
                draw, (405, 285), activity_formatted, font_medium, "white", "black", max_width=200)
            self._draw_text_with_stroke(
                draw, (405, 335), f"{total_activities:,}", font_medium, "white", "black", max_width=200)

            img_bytes = io.BytesIO()
            image.save(img_bytes, format='PNG')
            img_bytes.seek(0)

            filename = f"{'user' if is_user_stats else 'server'}_average_stats_{interaction.guild.id}.png"
            gc.collect()
            return discord.File(img_bytes, filename=filename)

        except Exception as e:
            print(f"Error creating image: {e}")
            import traceback
            traceback.print_exc()
            return await self._create_error_image(interaction)

    async def _create_error_image(self, interaction: discord.Interaction) -> discord.File:
        image = Image.new('RGB', (800, 600), color='blue')
        draw = ImageDraw.Draw(image)
        draw.text((50, 50), "Error generating statistics image", fill='white')

        img_bytes = io.BytesIO()
        image.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        gc.collect()
        return discord.File(img_bytes, filename="error.png")

    # COMMANDS
    average = app_commands.Group(
        name="average", description="Average statistics commands")

    @average.command(name="server", description="Show average statistics for the server")
    async def average_server(self, interaction: discord.Interaction):
        if not await self.check_command_permission(interaction):
            await self.send_permission_error(interaction)
            return

        await interaction.response.defer()

        if not self.db_cog:
            self.db_cog = self.bot.get_cog('DatabaseStats')
            if not self.db_cog:
                await interaction.followup.send(
                    "❌ DatabaseStats cog is not loaded. AverageStats requires DatabaseStats to function.",
                    ephemeral=True
                )
                return

        try:
            # Get server default time range
            start_time, end_time, display_text, days_back_equiv = await self.get_server_default_time_range(interaction.guild.id)
            image_file = await self.generate_server_stats_image(interaction, start_time, end_time, days_back_equiv, None, "day", display_text)
            view = AverageServerStatsView(
                self, start_time, end_time, days_back_equiv, display_text, None, "day", using_server_default=True)
            retention_alert_text = await self.db_cog.maybe_get_retention_alert(interaction.guild.id) if self.db_cog else None
            await interaction.followup.send(content=retention_alert_text, file=image_file, view=view)
        except Exception as e:
            print(f"Error in average server command: {e}")
            await interaction.followup.send(
                "❌ An error occurred while generating statistics image. Please try again later.",
                ephemeral=True
            )

    @average.command(name="user", description="Show average statistics for a specific user")
    @app_commands.describe(user="The user to show statistics for")
    async def average_user(self, interaction: discord.Interaction, user: discord.User):
        member = interaction.guild.get_member(user.id) or user

        if not await self.check_command_permission(interaction, member, user.id):
            await self.send_permission_error(interaction, user.id)
            return

        await interaction.response.defer()

        if not self.db_cog:
            self.db_cog = self.bot.get_cog('DatabaseStats')
            if not self.db_cog:
                await interaction.followup.send(
                    "❌ DatabaseStats cog is not loaded. AverageStats requires DatabaseStats to function.",
                    ephemeral=True
                )
                return

        try:
            # Get server default time range
            start_time, end_time, display_text, days_back_equiv = await self.get_server_default_time_range(interaction.guild.id)
            image_file = await self.generate_user_stats_image(interaction, start_time, end_time, days_back_equiv, user.id, "day", display_text)
            view = AverageUserStatsView(
                self, start_time, end_time, days_back_equiv, display_text, user.id, "day", using_server_default=True)
            retention_alert_text = await self.db_cog.maybe_get_retention_alert(interaction.guild.id) if self.db_cog else None
            await interaction.followup.send(content=retention_alert_text, file=image_file, view=view)
        except Exception as e:
            print(f"Error in average user command: {e}")
            await interaction.followup.send(
                "❌ An error occurred while generating statistics image. Please try again later.",
                ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(AverageStats(bot))
