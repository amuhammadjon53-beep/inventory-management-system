from .ratelimiter import RateLimiter, RateLimitType, rate_limited, get_rate_limiter
import numpy as np
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import discord
from discord.ext import commands
from discord import app_commands
import asyncpg
import asyncio
from datetime import datetime, timedelta
import io
import os
from typing import Optional, Dict, List, Tuple, Set, Any, Union
from dotenv import load_dotenv
import aiohttp
import json
from datetime import timezone
from datetime import datetime, timedelta, date
import traceback
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from pilmoji import Pilmoji
import matplotlib
import unicodedata
import pytz
import gc
import scipy
matplotlib.use('Agg')


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


# DRAWING FUNCTIONS

def draw_text_with_stroke(draw, position, text, font, text_color, stroke_color, stroke_width):

    x, y = position

    for dx in range(-stroke_width, stroke_width + 1):
        for dy in range(-stroke_width, stroke_width + 1):
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, font=font, fill=stroke_color)

    draw.text((x, y), text, font=font, fill=text_color)


def draw_text_with_stroke_and_emoji(pilmoji_draw, position, text, font, text_color, stroke_color, stroke_width):

    x, y = position

    temp_draw = pilmoji_draw._draw

    for dx in range(-stroke_width, stroke_width + 1):
        for dy in range(-stroke_width, stroke_width + 1):
            if dx != 0 or dy != 0:
                pilmoji_draw.text((x + dx, y + dy), text, font=font,
                                  fill=stroke_color, emoji_position_offset=(0, 0))

    pilmoji_draw.text((x, y), text, font=font, fill=text_color,
                      emoji_position_offset=(0, 0))


# PAGE JUMP MODAL
class PageJumpModal(discord.ui.Modal, title='Jump to Interval'):
    def __init__(self, view, total_intervals):
        super().__init__(timeout=60)
        self.view = view
        self.total_intervals = total_intervals

        self.interval_number = discord.ui.TextInput(
            label=f'Enter interval number (1-{total_intervals})',
            placeholder=f'1 to {total_intervals}',
            min_length=1,
            max_length=4,
            required=True
        )
        self.add_item(self.interval_number)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            interval = int(self.interval_number.value) - 1

            if interval < 0 or interval >= self.total_intervals:
                embed = discord.Embed(
                    title="❌ Invalid Interval",
                    description=f"Interval {interval + 1} does not exist. Please enter a number between 1 and {self.total_intervals}.",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            await interaction.response.defer()
            # For charts, interval selection doesn't make sense, but we'll keep for consistency
            await self.view.update_chart(interaction)

        except ValueError:
            embed = discord.Embed(
                title="❌ Invalid Input",
                description="Please enter a valid interval number.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


# ROLE INPUT MODAL

class RoleInputModal(discord.ui.Modal, title='Input Role ID'):
    def __init__(self, view):
        super().__init__(timeout=300)
        self.view = view

    role_id = discord.ui.TextInput(
        label='Enter Role ID or "none" for no filter',
        placeholder='e.g., 123456789012345678 or "none"',
        min_length=3,
        max_length=30,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            role_input = self.role_id.value.strip()

            if role_input.lower() == "none":
                self.view.selected_role_id = "none"
                await interaction.response.defer()
                await self.view.update_chart(interaction)
                return

            try:
                role_id_int = int(role_input)
            except ValueError:
                embed = discord.Embed(
                    description="❌ Please enter a valid role ID number or 'none'.",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            guild = self.view.guild
            if not guild:
                embed = discord.Embed(
                    description="❌ Could not find guild information.",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            role = guild.get_role(role_id_int)
            if not role:
                embed = discord.Embed(
                    description="❌ Sorry! The role id you inputted is not valid, please try again.",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            self.view.selected_role_id = str(role_id_int)
            await interaction.response.defer()
            await self.view.update_chart(interaction)

        except Exception as e:
            print(f"Error in role input modal submit: {e}")
            embed = discord.Embed(
                description="❌ An error occurred while processing your request.",
                color=discord.Color.red()
            )
            try:
                await interaction.response.send_message(embed=embed, ephemeral=True)
            except:
                pass


# TIME SETTINGS MODAL

class ChartTimeModal(discord.ui.Modal, title='Custom Time Period'):
    def __init__(self, view):
        super().__init__(timeout=300)
        self.view = view

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
            if days <= 0 or days > 2000:
                await interaction.response.send_message("❌ Please enter a number between 1 and 2000 days.", ephemeral=True)
                return

            await interaction.response.defer()
            now = datetime.now(pytz.UTC)
            self.view.current_start_time = now - timedelta(days=days)
            self.view.current_end_time = now
            self.view.current_days_back_equiv = days
            self.view.current_display_text = f"{days} days"
            self.view.using_server_default = False
            self.view.show_time_buttons = False
            await self.view.update_chart(interaction)

        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number.", ephemeral=True)
        except Exception as e:
            print(f"Error in chart modal submit: {e}")
            await interaction.followup.send("❌ An error occurred while updating chart.", ephemeral=True)


# CHART SELECT MENU

class ChartSelectMenu(discord.ui.Select):
    def __init__(self, options: List[str], current_selection: str):
        select_options = []

        for option in options:
            select_options.append(
                discord.SelectOption(
                    label=option,
                    value=option.lower().replace(' ', '_'),
                    emoji="📊",
                    default=(option.lower().replace(
                        ' ', '_') == current_selection)
                )
            )

        super().__init__(
            placeholder="Select chart type...",
            options=select_options,
            custom_id="chart_type_select",
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        view.current_selection = self.values[0]
        await interaction.response.defer()
        await view.update_chart(interaction)


# MAIN CHART VIEW

class ChartView(discord.ui.View):
    def __init__(self, cog, chart_type: str, target_id: int, guild_id: int, start_time: datetime = None,
                 end_time: datetime = None, days_back_equiv: int = 14, display_text: str = "14 days",
                 role_id: Optional[str] = None, ctx=None, using_server_default: bool = True):
        super().__init__(timeout=600)
        self.cog = cog
        self.chart_type = chart_type
        self.target_id = int(target_id)
        self.guild_id = int(guild_id)
        self.current_start_time = start_time
        self.current_end_time = end_time if end_time else datetime.now(
            pytz.UTC)
        self.current_days_back_equiv = int(days_back_equiv)
        self.current_display_text = display_text
        self.selected_role_id = role_id
        self.show_time_buttons = False
        self.guild = cog.bot.get_guild(self.guild_id)
        self.ctx = ctx
        self.message = None
        self.using_server_default = using_server_default

        if chart_type == "user" or chart_type == "server":
            self.chart_options = ["Messages", "Voice Activity", "Invites"]
            self.current_selection = "messages"
        else:
            self.chart_options = ["Messages", "Voice Activity"]
            self.current_selection = "messages"

        self._update_buttons()

    async def _safe_edit_response(self, interaction: discord.Interaction, **kwargs):
        try:
            await interaction.edit_original_response(**kwargs)
        except discord.NotFound:
            try:
                await interaction.followup.send(**kwargs, ephemeral=True)
            except:
                pass
        except Exception as e:
            print(f"Error in _safe_edit_response: {e}")

    async def _safe_send_or_edit(self, content=None, file=None, view=None):
        """Handle both interaction and context-based messages"""
        if self.message:
            try:
                await self.message.edit(content=content, attachments=[file] if file else [], view=view)
            except Exception as e:
                print(f"Error editing message: {e}")
        elif self.ctx:
            try:
                self.message = await self.ctx.send(content=content, file=file, view=view)
            except Exception as e:
                print(f"Error sending message: {e}")

    def _update_buttons(self):
        self.clear_items()

        chart_select = ChartSelectMenu(
            self.chart_options, self.current_selection)
        self.add_item(chart_select)

        if self.chart_type != "user":
            role_button = discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label="Input Role Id",
                custom_id="chart_role_input",
                row=1
            )
            role_button.callback = self.role_input_callback
            self.add_item(role_button)

        refresh_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="🔄 Refresh",
            custom_id="chart_refresh",
            row=2
        )
        refresh_button.callback = self.refresh_callback
        self.add_item(refresh_button)

        time_settings_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="⏰ Time Settings",
            custom_id="chart_time_settings",
            row=2
        )
        time_settings_button.callback = self.time_settings_callback
        self.add_item(time_settings_button)

        if self.show_time_buttons:
            all_time_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 999999 else discord.ButtonStyle.secondary,
                label="All Time",
                custom_id="chart_all_time"
            )
            all_time_button.callback = self.all_time_callback
            self.add_item(all_time_button)

            days_7_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 7 else discord.ButtonStyle.secondary,
                label="7 Days",
                custom_id="chart_days_7"
            )
            days_7_button.callback = self.days_7_callback
            self.add_item(days_7_button)

            days_14_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 14 else discord.ButtonStyle.secondary,
                label="14 Days",
                custom_id="chart_days_14"
            )
            days_14_button.callback = self.days_14_callback
            self.add_item(days_14_button)

            days_30_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 30 else discord.ButtonStyle.secondary,
                label="30 Days",
                custom_id="chart_days_30"
            )
            days_30_button.callback = self.days_30_callback
            self.add_item(days_30_button)

            # Use display text for custom button label
            custom_label = self.current_display_text if self.current_days_back_equiv not in [
                7, 14, 30, 999999] else "Custom"
            if len(custom_label) > 20:
                custom_label = custom_label[:17] + "..."
            custom_button = discord.ui.Button(
                style=discord.ButtonStyle.success,
                label=custom_label,
                custom_id="chart_custom_days"
            )
            custom_button.callback = self.custom_days_callback
            self.add_item(custom_button)

    async def role_input_callback(self, interaction: discord.Interaction):
        if not self.guild:
            embed = discord.Embed(
                description="❌ Could not find guild information.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        modal = RoleInputModal(self)
        await interaction.response.send_modal(modal)

    async def refresh_callback(self, interaction: discord.Interaction):
        await self.handle_button_click(interaction, refresh=True)

    async def time_settings_callback(self, interaction: discord.Interaction):
        await self.handle_time_settings(interaction)

    async def all_time_callback(self, interaction: discord.Interaction):
        now = datetime.now(pytz.UTC)
        await self.handle_button_click(interaction, days_back_equiv=999999, start_time=None, end_time=now, display_text="All Time")

    async def days_7_callback(self, interaction: discord.Interaction):
        now = datetime.now(pytz.UTC)
        await self.handle_button_click(interaction, days_back_equiv=7, start_time=now - timedelta(days=7), end_time=now, display_text="7 days")

    async def days_14_callback(self, interaction: discord.Interaction):
        now = datetime.now(pytz.UTC)
        await self.handle_button_click(interaction, days_back_equiv=14, start_time=now - timedelta(days=14), end_time=now, display_text="14 days")

    async def days_30_callback(self, interaction: discord.Interaction):
        now = datetime.now(pytz.UTC)
        await self.handle_button_click(interaction, days_back_equiv=30, start_time=now - timedelta(days=30), end_time=now, display_text="30 days")

    async def custom_days_callback(self, interaction: discord.Interaction):
        if not self.guild:
            await interaction.response.send_message("❌ Could not find guild information.", ephemeral=True)
            return

        modal = ChartTimeModal(self)
        await interaction.response.send_modal(modal)

    async def handle_button_click(self, interaction: discord.Interaction, refresh: bool = False,
                                  days_back_equiv: int = None, start_time: datetime = None,
                                  end_time: datetime = None, display_text: str = None):
        try:
            await interaction.response.defer()
            if days_back_equiv is not None:
                self.current_start_time = start_time
                self.current_end_time = end_time
                self.current_days_back_equiv = days_back_equiv
                self.using_server_default = False
                self.show_time_buttons = False
            if display_text is not None:
                self.current_display_text = display_text
            await self.update_chart(interaction)
        except Exception as e:
            print(f"Error handling button click: {e}")
            try:
                await interaction.followup.send("❌ An error occurred while updating the chart.", ephemeral=True)
            except:
                pass

    async def handle_time_settings(self, interaction: discord.Interaction):
        try:
            self.show_time_buttons = not self.show_time_buttons
            self._update_buttons()
            await interaction.response.edit_message(view=self)
        except Exception as e:
            print(f"Error handling time settings: {e}")
            try:
                await interaction.response.send_message("❌ An error occurred while updating time settings.", ephemeral=True)
            except:
                pass

    async def update_chart(self, interaction: discord.Interaction = None):
        """Update chart, handling both interaction and context-based calls"""

        try:
            data = await self.fetch_chart_data()

            if not data:
                if interaction:
                    await self._safe_edit_response(interaction, content="❌ No data available for the selected parameters", view=self)
                else:
                    await self._safe_send_or_edit(content="❌ No data available for the selected parameters", view=self)
                return

            if data.get('error'):
                print(f"Step 3: Data has error: {data['error']}")
                if interaction:
                    await self._safe_edit_response(interaction, content=f"❌ {data['error']}", view=self)
                else:
                    await self._safe_send_or_edit(content=f"❌ {data['error']}", view=self)
                return

            settings_cog = self.cog.bot.get_cog('Settings')
            guild_timezone = 'UTC'
            if settings_cog:
                settings = await settings_cog.get_guild_settings(self.guild_id)
                guild_timezone = settings.get('timezone', 'UTC')

            role_name = None
            if self.selected_role_id and self.selected_role_id != "none":
                db_stats = self.cog.bot.get_cog('DatabaseStats')
                if db_stats and db_stats.pool:
                    try:
                        async with db_stats.pool.acquire() as conn:
                            row = await conn.fetchrow("""
                                SELECT role_name FROM current_role_members 
                                WHERE role_id = $1 AND guild_id = $2 
                                LIMIT 1
                            """, int(self.selected_role_id), self.guild_id)
                            if row:
                                role_name = row['role_name']

                    except Exception as e:
                        print(f"Step 7 ERROR getting role: {e}")
                        traceback.print_exc()

            result = self.cog.generate_professional_chart(
                data, self.current_selection, guild_timezone)

            # Unpack safely
            if isinstance(result, tuple) and len(result) == 3:
                chart_img, timestamps, y_labels = result

            else:
                print(f"Step 10 ERROR: Unexpected result format: {result}")
                raise ValueError(
                    f"generate_professional_chart returned {type(result)} instead of tuple")

            label = self.create_label(data)

            final_image_bytes = await self.cog.draw_chart_on_template(
                chart_img, label, self.current_display_text, self.selected_role_id,
                role_name, timestamps, y_labels, self.current_selection, self.chart_type, self.target_id, self.guild_id)

            file = discord.File(final_image_bytes, filename='chart.png')
            self._update_buttons()

            if interaction:
                await self._safe_edit_response(interaction, content=None, attachments=[file], view=self)
            else:
                await self._safe_send_or_edit(file=file, view=self)

        except Exception as e:
            print(f"\n❌❌❌ ERROR IN UPDATE_CHART: {e}")
            print(f"Error type: {type(e)}")
            traceback.print_exc()
            print("❌❌❌ END ERROR\n")
            try:
                if interaction:
                    await self._safe_edit_response(interaction, content="❌ Error generating chart", view=self)
                else:
                    await self._safe_send_or_edit(content="❌ Error generating chart", view=self)
            except:
                pass

    def create_label(self, data: Dict) -> str:

        chart_type = self.current_selection
        if chart_type == "messages":
            total = data.get('total', 0)
            return f"🔵 Messages {total}"
        elif chart_type == "voice_activity":
            total = data.get('total', 0)
            return f"🔴 Voice Activity {self.cog.format_duration_dynamic(total)}"
        elif chart_type == "invites":
            total = data.get('total', 0)
            return f"🟢 Invites {total}"
        return "🟢 Chart"

    async def fetch_chart_data(self) -> Dict:
        """Fetch chart data using aggregated tables"""
        chart_type = self.current_selection

        # Get timezone from settings
        settings_cog = self.cog.bot.get_cog('Settings')
        if settings_cog:
            settings = await settings_cog.get_guild_settings(self.guild_id)
            tz_str = settings.get('timezone', 'UTC')
            try:
                tz = pytz.timezone(tz_str)
            except:
                tz = pytz.UTC
        else:
            tz = pytz.UTC

        # Use timezone for end time
        if self.current_end_time:
            end_time = self.current_end_time
        else:
            end_time = datetime.now(tz)

        start_time = self.current_start_time

        # Convert to naive UTC for database queries
        end_time_naive = end_time.replace(
            tzinfo=None) if end_time.tzinfo else end_time
        start_time_naive = start_time.replace(
            tzinfo=None) if start_time else None

        role_filter_ids = None
        if self.selected_role_id and self.selected_role_id != "none":
            try:
                role_filter_ids = [int(self.selected_role_id)]
            except ValueError:
                role_filter_ids = None

        db_stats = self.cog.bot.get_cog('DatabaseStats')
        if not db_stats:
            return {'error': 'Database system not available'}

        guild = self.cog.bot.get_guild(self.guild_id)
        if not guild:
            return {'error': 'Guild not found'}

        try:
            # Determine intervals based on days
            days_back_equiv = self.current_days_back_equiv
            if days_back_equiv == 999999:
                # Get the actual date range for All Time
                # First, try to get the min and max dates from the database
                min_date = None
                max_date = None

                try:
                    async with db_stats.pool.acquire() as conn:
                        # Get earliest recorded date for this guild (or user if user chart)
                        if self.chart_type == "user":
                            earliest = await conn.fetchval("""
                                SELECT MIN(hour) FROM activity_sessions_hourly 
                                WHERE guild_id = $1 AND user_id = $2
                            """, self.guild_id, self.target_id)
                        else:
                            earliest = await conn.fetchval("""
                                SELECT MIN(hour) FROM activity_sessions_hourly 
                                WHERE guild_id = $1
                            """, self.guild_id)

                        if earliest:
                            min_date = earliest.replace(tzinfo=None)
                            max_date = end_time_naive

                            # Calculate total days range
                            total_days_range = (max_date - min_date).days
                            if total_days_range <= 0:
                                total_days_range = 30

                            # Set intervals based on total range
                            if total_days_range <= 30:
                                intervals = total_days_range
                                time_delta = timedelta(days=1)
                            elif total_days_range <= 180:
                                intervals = total_days_range // 7
                                time_delta = timedelta(days=7)
                            else:
                                intervals = total_days_range // 30
                                time_delta = timedelta(days=30)

                            # Cap intervals at reasonable number
                            intervals = min(intervals, 60)
                        else:
                            intervals = 30
                            time_delta = timedelta(days=30)
                except Exception as e:
                    print(f"Error getting date range for All Time: {e}")
                    intervals = 30
                    time_delta = timedelta(days=30)

            elif days_back_equiv <= 2:
                intervals = 24 * days_back_equiv
                time_delta = timedelta(hours=1)
            elif days_back_equiv <= 30:
                intervals = days_back_equiv
                time_delta = timedelta(days=1)
            elif days_back_equiv <= 180:
                intervals = days_back_equiv // 7
                time_delta = timedelta(days=7)
            else:
                intervals = days_back_equiv // 30
                time_delta = timedelta(days=30)

            points = []
            total = 0

            for i in range(intervals):
                if start_time_naive is None:
                    # For All Time, use the calculated min_date as reference
                    if min_date:
                        interval_end = max_date - time_delta * i
                        interval_start = max_date - time_delta * (i + 1)
                        if interval_start < min_date:
                            interval_start = min_date
                    else:
                        interval_end = end_time_naive - time_delta * i
                        interval_start = end_time_naive - time_delta * (i + 1)
                else:
                    interval_end = end_time_naive - time_delta * i
                    interval_start = end_time_naive - time_delta * (i + 1)

                    # Ensure we don't go before start_time
                    if interval_start < start_time_naive:
                        interval_start = start_time_naive

                # Create date object for display
                if days_back_equiv == 999999:
                    date_obj = interval_start.date()
                elif days_back_equiv <= 2:
                    date_obj = interval_start
                else:
                    date_obj = interval_start.date()

                if self.chart_type == "user":
                    if chart_type == "messages":
                        result = await db_stats.q_user_total_messages(
                            guild_id=self.guild_id,
                            user_id=self.target_id,
                            role_filter_ids=role_filter_ids,
                            start_time=interval_start,
                            end_time=interval_end
                        )
                        count = result.get('total_messages', 0)
                        points.append({'date': date_obj, 'count': count})
                        total += count

                    elif chart_type == "voice_activity":
                        result = await db_stats.q_user_total_voice(
                            guild_id=self.guild_id,
                            user_id=self.target_id,
                            role_filter_ids=role_filter_ids,
                            start_time=interval_start,
                            end_time=interval_end
                        )
                        seconds = result.get('total_seconds', 0)
                        points.append(
                            {'date': date_obj, 'total_seconds': seconds})
                        total += seconds

                    elif chart_type == "invites":
                        result = await db_stats.q_user_invite_stats(
                            guild_id=self.guild_id,
                            user_id=self.target_id,
                            start_time=interval_start,
                            end_time=interval_end
                        )
                        count = result.get('total_invites', 0)
                        points.append({'date': date_obj, 'count': count})
                        total += count

                elif self.chart_type == "server":
                    if chart_type == "messages":
                        result = await db_stats.q_server_total_messages(
                            guild_id=self.guild_id,
                            role_filter_ids=role_filter_ids,
                            start_time=interval_start,
                            end_time=interval_end
                        )
                        count = result.get('total_messages', 0)
                        points.append({'date': date_obj, 'count': count})
                        total += count

                    elif chart_type == "voice_activity":
                        result = await db_stats.q_server_total_voice(
                            guild_id=self.guild_id,
                            role_filter_ids=role_filter_ids,
                            start_time=interval_start,
                            end_time=interval_end
                        )
                        seconds = result.get('total_seconds', 0)
                        points.append(
                            {'date': date_obj, 'total_seconds': seconds})
                        total += seconds

                    elif chart_type == "invites":
                        leaderboard = await db_stats.q_invite_leaderboard(
                            guild_id=self.guild_id,
                            limit=100,
                            role_filter_ids=role_filter_ids,
                            start_time=interval_start,
                            end_time=interval_end
                        )
                        count = sum(item.get('valid_invites', 0)
                                    for item in leaderboard)
                        points.append({'date': date_obj, 'count': count})
                        total += count

                elif self.chart_type == "channel":
                    if chart_type == "messages":
                        result = await db_stats.q_channel_total_messages(
                            guild_id=self.guild_id,
                            channel_id=self.target_id,
                            role_filter_ids=role_filter_ids,
                            start_time=interval_start,
                            end_time=interval_end
                        )
                        count = result.get('total_messages', 0)
                        points.append({'date': date_obj, 'count': count})
                        total += count

                    elif chart_type == "voice_activity":
                        result = await db_stats.q_channel_total_voice(
                            guild_id=self.guild_id,
                            channel_id=self.target_id,
                            role_filter_ids=role_filter_ids,
                            start_time=interval_start,
                            end_time=interval_end
                        )
                        seconds = result.get('total_seconds', 0)
                        points.append(
                            {'date': date_obj, 'total_seconds': seconds})
                        total += seconds

                elif self.chart_type == "category":
                    if chart_type == "messages":
                        result = await db_stats.q_category_total_messages(
                            guild_id=self.guild_id,
                            category_id=self.target_id,
                            role_filter_ids=role_filter_ids,
                            start_time=interval_start,
                            end_time=interval_end
                        )
                        count = result.get('total_messages', 0)
                        points.append({'date': date_obj, 'count': count})
                        total += count

                    elif chart_type == "voice_activity":
                        result = await db_stats.q_category_total_voice(
                            guild_id=self.guild_id,
                            category_id=self.target_id,
                            role_filter_ids=role_filter_ids,
                            start_time=interval_start,
                            end_time=interval_end
                        )
                        seconds = result.get('total_seconds', 0)
                        points.append(
                            {'date': date_obj, 'total_seconds': seconds})
                        total += seconds

            points.sort(key=lambda x: x['date'])
            return {'points': points, 'total': total}

        except Exception as e:
            print(f"Error fetching chart data: {e}")
            traceback.print_exc()
            return {'points': [], 'total': 0, 'error': str(e)}


class ChartSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.rate_limiter = get_rate_limiter()

    async def cog_load(self):

        try:
            print("✅ Chart cog loaded")
        except Exception as e:
            print(f"❌ ChartSystem: Setup failed: {e}")

    async def cog_unload(self):

        print("✅ ChartSystem: Unloaded")

    def _ensure_int(self, value: Any) -> Optional[int]:

        if value is None:
            return None
        if isinstance(value, int):
            return value
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    async def is_user_or_roles_blacklisted(self, guild_id: int, guild: discord.Guild, user_id: int) -> bool:

        db_stats = self.bot.get_cog('DatabaseStats')
        if not db_stats:
            return False

        try:
            return await db_stats.is_user_or_roles_blacklisted(guild_id, user_id)
        except Exception as e:
            print(f"⚠️ Error checking user blacklist via DatabaseStats: {e}")
            return False

    # GET SERVER DEFAULT TIME RANGE
    async def get_server_default_time_range(self, guild_id: int) -> tuple:
        """Get the default time range from server settings. Returns (start_time, end_time, display_text, days_back_equiv)"""
        try:
            settings_cog = self.bot.get_cog('Settings')
            if not settings_cog:
                end = datetime.now(pytz.UTC)
                start = end - timedelta(days=14)
                return (start, end, "14 days", 14)

            settings = await settings_cog.get_guild_settings(guild_id)
            mode = settings.get('default_time_mode', 'days_back')
            now = datetime.now(pytz.UTC)

            if mode == 'all_time':
                return (None, now, "All Time", 999999)

            elif mode == 'days_back':
                days = settings.get('default_days_back') or 14
                start = now - timedelta(days=days)
                return (start, now, f"{days} days", days)

            elif mode == 'date_range':
                from_date = settings.get('default_from_date')
                to_date = settings.get('default_to_date')
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
                    display = f"Since the {rolling_value}{suffix}"
                    return (start, now, display, days_back)

            end = now - timedelta(days=0)
            start = now - timedelta(days=14)
            return (start, end, "14 days", 14)

        except Exception as e:
            import traceback
            traceback.print_exc()
            end = datetime.now(pytz.UTC)
            start = end - timedelta(days=14)
            return (start, end, "14 days", 14)

    # PERMISSION CHECKING METHODS
    async def check_permission(self, interaction: discord.Interaction, target_user_id: Optional[int] = None) -> bool:
        """Check if user has permission to use chart commands based on settings"""
        if interaction.user.guild_permissions.administrator:
            return True

        settings_cog = self.bot.get_cog('Settings')
        if not settings_cog:
            return True

        settings = await settings_cog.get_guild_settings(interaction.guild_id)
        permission_level = settings.get('permission_level', 'Default')

        if permission_level == 'All':
            return True
        elif permission_level == 'Default':
            return True
        elif permission_level == 'User Restriction':
            if target_user_id is not None:
                return interaction.user.id == target_user_id
            return True
        elif permission_level == 'Admin':
            return interaction.user.guild_permissions.administrator
        elif permission_level == 'Moderator':
            return interaction.user.guild_permissions.manage_guild
        else:
            return True

    def check_permission_prefix(self, ctx: commands.Context, target_user_id: Optional[int] = None) -> bool:
        """Check if user has permission to use chart commands for prefix commands"""
        if ctx.author.guild_permissions.administrator:
            return True

        return True

    async def send_permission_error(self, interaction: discord.Interaction, target_user_id: Optional[int] = None):
        """Send appropriate permission error message"""
        settings_cog = self.bot.get_cog('Settings')
        if not settings_cog:
            embed = discord.Embed(
                description="❌ An error occurred while checking permissions.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False

        settings = await settings_cog.get_guild_settings(interaction.guild_id)
        permission_level = settings.get('permission_level', 'Default')

        if permission_level == 'User Restriction' and target_user_id is not None and interaction.user.id != target_user_id:
            embed = discord.Embed(
                description="❌ Sorry! You can only use this command on yourself.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        elif permission_level == 'Admin':
            embed = discord.Embed(
                description="❌ Sorry! You need the `Administrator` permission to access this command.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        elif permission_level == 'Moderator':
            embed = discord.Embed(
                description="❌ Sorry! You need the `Manage Server` permission to access this command.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False

        return True

    # CHART GENERATION METHODS

    def generate_dynamic_timestamps(self, data_points: List[Dict], guild_timezone: str = 'UTC') -> List[str]:
        if not data_points or len(data_points) < 2:
            return [f"Day {i+1}" for i in range(8)]

        dates = [row['date'] for row in data_points if 'date' in row]
        if not dates:
            return [f"Day {i+1}" for i in range(8)]

        # Convert all dates to datetime for consistent handling
        datetime_dates = []
        for d in dates:
            if isinstance(d, date) and not isinstance(d, datetime):
                dt = datetime(d.year, d.month, d.day)
                datetime_dates.append(dt)
            else:
                datetime_dates.append(d)

        start_time = min(datetime_dates)
        end_time = max(datetime_dates)
        delta = end_time - start_time
        total_days = delta.days + (delta.seconds / 86400)

        if total_days <= 2:
            timestamps = []
            if total_days <= 1:
                hours = [0, 3, 6, 9, 12, 15, 18, 21]
                for hour in hours:
                    display_time = start_time + timedelta(hours=hour)
                    timestamps.append(f"{display_time.hour:02d}:00")
            else:
                hours = [0, 6, 12, 18, 24, 30, 36, 42]
                for hour in hours:
                    display_time = start_time + timedelta(hours=hour)
                    if hour < 24:
                        timestamps.append(f"{display_time.hour:02d}:00")
                    else:
                        timestamps.append(f"{display_time.hour:02d}:00")
            return timestamps

        elif total_days <= 30:
            fmt = "%b %d"
        elif total_days <= 180:
            fmt = "Week %W"
        else:
            fmt = "%b %Y"

        timestamps = []
        for i in range(8):
            t = start_time + (delta * (i / 7))
            if fmt == "Week %W":
                week_num = t.isocalendar()[1]
                timestamps.append(f"Week {week_num}")
            else:
                timestamps.append(t.strftime(fmt))

        return timestamps

    def get_timestamp_x_positions(self) -> List[int]:

        x_start = 65
        x_end = 650
        interval = (x_end - x_start) / 7
        return [int(x_start + interval * i) for i in range(8)]

    def generate_professional_chart(self, data: Dict, chart_type: str, guild_timezone: str = 'UTC') -> Tuple[Image.Image, List[str], List[Tuple[float, str]]]:

        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(6, 2.5), dpi=300,
                               facecolor=(0, 0, 0, 0))
        ax.set_axis_off()

        colors = {
            'messages': '#4287f5',
            'voice_activity': '#FF5C8D',
            'invites': '#b700ff'
        }

        timestamps = []
        y_labels = []

        if chart_type in ['messages', 'voice_activity', 'invites']:
            points = data.get('points', [])
            if points and len(points) > 1:
                points.sort(key=lambda x: x['date'])
                dates = [row['date'] for row in points]

                if chart_type == 'messages' or chart_type == 'invites':
                    values = [float(row['count']) for row in points]
                else:
                    values = [float(row['total_seconds']) for row in points]

                dates_numeric = [mdates.date2num(date) for date in dates]

                max_value = max(values) if values else 1

                y_label_values = [
                    max_value,
                    max_value * 0.75,
                    max_value * 0.5,
                    max_value * 0.25,
                    0
                ]

                y_labels = []
                for value in y_label_values:
                    if value >= 1000:
                        if value % 1000 == 0:
                            label = f"{int(value/1000)}k"
                        else:
                            label = f"{value/1000:.1f}k"
                    else:
                        label = str(int(value))
                    y_labels.append((value, label))

                timestamps = self.generate_dynamic_timestamps(
                    points, guild_timezone)

                if len(dates_numeric) > 1:
                    x_smooth = np.linspace(
                        min(dates_numeric), max(dates_numeric), 500)
                    y_smooth = np.interp(x_smooth, dates_numeric, values)

                    from scipy.ndimage import gaussian_filter1d
                    y_smooth = gaussian_filter1d(y_smooth, sigma=2)

                    color = colors.get(chart_type, '#4287f5')
                    ax.plot(x_smooth, y_smooth, linewidth=4, color=color,
                            solid_capstyle='round', antialiased=True)
                else:
                    color = colors.get(chart_type, '#4287f5')
                    ax.plot(dates_numeric, values, 'o',
                            markersize=3, color=color, alpha=0.7)
            else:
                timestamps = [f"Day {i+1}" for i in range(8)]
                y_labels = [
                    (100, "100"),
                    (75, "75"),
                    (50, "50"),
                    (25, "25"),
                    (0, "0")
                ]

        buf = io.BytesIO()
        plt.savefig(buf, format='png', transparent=True,
                    bbox_inches='tight', pad_inches=0, dpi=300)
        buf.seek(0)
        chart_img = Image.open(buf)
        plt.close(fig)

        return chart_img, timestamps, y_labels

    # FORMAT

    def format_number(self, num: float) -> str:

        if num >= 1000:
            if num % 1000 == 0:
                return f"{int(num/1000)}k"
            else:
                return f"{num/1000:.1f}k"
        return str(int(num))

    def format_duration_dynamic(self, seconds: int) -> str:

        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            minutes = seconds // 60
            remaining_seconds = seconds % 60
            if remaining_seconds > 0:
                return f"{minutes}m {remaining_seconds}s"
            else:
                return f"{minutes}m"
        elif seconds < 86400:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            if minutes > 0:
                return f"{hours}h {minutes}m"
            else:
                return f"{hours}h"
        else:
            days = seconds // 86400
            hours = (seconds % 86400) // 3600
            if hours > 0:
                return f"{days}d {hours}h"
            else:
                return f"{days}d"

    async def draw_header_info(self, template: Image.Image, chart_type: str, target_id: int, guild_id: int) -> Image.Image:

        draw = ImageDraw.Draw(template)

        avatar_x, avatar_y = 10, 10
        avatar_size = (52, 52)

        text_start_x = 70
        text_start_y = 28

        username_rectangle = {"center": (133, 35), "width": 183, "height": 35}

        settings_cog = self.bot.get_cog('Settings')
        current_timezone = 'UTC'
        if settings_cog:
            settings = await settings_cog.get_guild_settings(guild_id)
            current_timezone = settings.get('timezone', 'UTC')

        try:
            tz = pytz.timezone(current_timezone)
            current_date = datetime.now(tz).strftime("%B %d, %Y")
        except:
            current_date = datetime.now().strftime("%B %d, %Y")

        try:
            horndon_font = ImageFont.truetype(
                BASE_DIR / "assets" / "fonts" / "HorndonD.ttf", 16)
        except:
            horndon_font = ImageFont.load_default()

        draw_text_with_stroke(draw, (570, 38), current_date,
                              horndon_font, "white", "black", 2)

        guild = self.bot.get_guild(int(guild_id))
        if not guild:
            return template

        def fit_text_to_rectangle(text, text_start_x, text_start_y, rect_center_x, rect_center_y, rect_width, rect_height):
            font_paths = [
                BASE_DIR / "assets" / "fonts" / "HorndonD.ttf",
            ]

            font_sizes = [32, 30, 28, 26, 24, 22, 20,
                          18, 16]

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
                if font_size == 32:
                    vertical_offset += 1
                if font_size <= 30:
                    vertical_offset += 1
                if font_size <= 28:
                    vertical_offset += 1
                if font_size <= 26:
                    vertical_offset += 1
                if font_size <= 24:
                    vertical_offset += 1
                if font_size <= 22:
                    vertical_offset += 1
                if font_size <= 20:
                    vertical_offset += 1
                if font_size <= 18:
                    vertical_offset += 1
                if font_size <= 16:
                    vertical_offset += 1
                text_y += vertical_offset

                text_fits_horizontally = (
                    text_x + text_width + 5 <= rect_right + 1)
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
            if smallest_font == 32:
                vertical_offset += 1
            if smallest_font <= 30:
                vertical_offset += 1
            if smallest_font <= 28:
                vertical_offset += 1
            if smallest_font <= 26:
                vertical_offset += 1
            if smallest_font <= 24:
                vertical_offset += 1
            if smallest_font <= 22:
                vertical_offset += 1
            if smallest_font <= 20:
                vertical_offset += 1
            if smallest_font <= 18:
                vertical_offset += 1
            if smallest_font <= 16:
                vertical_offset += 1
            text_y += vertical_offset

            text_fits_horizontally = (
                text_x + text_width + 5 <= rect_right + 1)
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

                if (text_x + text_width + 5 <= rect_right + 1):
                    return current_text, font, (text_x, text_y)

            if len(text) > 3:
                final_text = text[:3] + "..."
            else:
                final_text = text

            return final_text, font, (text_x, text_y)

        target_name = guild.name
        use_server_icon = True
        target_member = None

        if chart_type == "server":
            target_name = guild.name
            use_server_icon = True

        elif chart_type == "channel":
            channel = guild.get_channel(int(target_id))
            if channel:
                target_name = f"#{channel.name}"
            use_server_icon = True

        elif chart_type == "category":
            category = guild.get_channel(int(target_id))
            if category:
                target_name = category.name
            use_server_icon = True

        elif chart_type == "user":
            member = guild.get_member(int(target_id))
            if member:
                target_name = member.name
                target_member = member
                use_server_icon = False
            else:
                target_name = f"User {target_id}"
                use_server_icon = True

        normalized_name = unicodedata.normalize('NFKD', target_name)
        ascii_name = normalized_name.encode('ascii', 'ignore').decode('ascii')
        if not ascii_name:
            ascii_name = target_name

        try:
            if use_server_icon:
                if guild.icon:
                    icon_url = guild.icon.url
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

                    avatar_area = template.crop(
                        (avatar_x, avatar_y, avatar_x +
                         avatar_size[0], avatar_y + avatar_size[1])
                    ).convert('RGBA')

                    icon_with_bg = Image.new('RGBA', avatar_size, (0, 0, 0, 0))
                    icon_with_bg.paste(icon_image, (0, 0), icon_image)
                    avatar_area.paste(icon_with_bg, (0, 0), icon_with_bg)
                    template.paste(avatar_area.convert(
                        'RGB'), (avatar_x, avatar_y))
                    icon_image.close()
                    del icon_image
                    del icon_data
            else:
                if target_member and target_member.avatar:
                    icon_url = target_member.avatar.url
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

                    avatar_area = template.crop(
                        (avatar_x, avatar_y, avatar_x +
                         avatar_size[0], avatar_y + avatar_size[1])
                    ).convert('RGBA')

                    icon_with_bg = Image.new('RGBA', avatar_size, (0, 0, 0, 0))
                    icon_with_bg.paste(icon_image, (0, 0), icon_image)
                    avatar_area.paste(icon_with_bg, (0, 0), icon_with_bg)
                    template.paste(avatar_area.convert(
                        'RGB'), (avatar_x, avatar_y))
                    icon_image.close()
                    del icon_image
                    del icon_data
                else:
                    if guild.icon:
                        icon_url = guild.icon.url
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

                        avatar_area = template.crop(
                            (avatar_x, avatar_y, avatar_x +
                             avatar_size[0], avatar_y + avatar_size[1])
                        ).convert('RGBA')

                        icon_with_bg = Image.new(
                            'RGBA', avatar_size, (0, 0, 0, 0))
                        icon_with_bg.paste(icon_image, (0, 0), icon_image)
                        avatar_area.paste(icon_with_bg, (0, 0), icon_with_bg)
                        template.paste(avatar_area.convert(
                            'RGB'), (avatar_x, avatar_y))
                        icon_image.close()
                        del icon_image
                        del icon_data

        except Exception as e:
            print(f"❌ Could not add profile picture: {e}")

        fitted_text, text_font, text_pos = fit_text_to_rectangle(
            ascii_name,
            text_start_x,
            text_start_y,
            username_rectangle["center"][0],
            username_rectangle["center"][1],
            username_rectangle["width"],
            username_rectangle["height"]
        )

        if fitted_text and text_font:
            with Pilmoji(template) as pilmoji:
                stroke_width = 1
                for dx in [-stroke_width, 0, stroke_width]:
                    for dy in [-stroke_width, 0, stroke_width]:
                        if dx != 0 or dy != 0:
                            pilmoji.text((text_pos[0] + dx, text_pos[1] + dy),
                                         fitted_text, font=text_font, fill="black")

                pilmoji.text(text_pos, fitted_text,
                             font=text_font, fill="white")
        else:
            try:
                fallback_font = ImageFont.truetype(
                    BASE_DIR / "assets" / "fonts" / "HorndonD.ttf", 32)
            except:
                fallback_font = ImageFont.load_default()

            with Pilmoji(template) as pilmoji:
                pilmoji.text((text_start_x, text_start_y),
                             ascii_name, font=fallback_font, fill="white")

        return template

    async def draw_chart_on_template(self, chart_img: Image.Image, label_text: str, display_text: str,
                                     role_id: Optional[str], role_name: Optional[str], timestamps: List[str],
                                     y_labels: List[Tuple[float, str]], chart_type: str,
                                     target_type: str, target_id: int, guild_id: int) -> io.BytesIO:

        template_paths = {
            'messages': BASE_DIR / "assets" / "images" / "charts messages final png.png",
            'voice_activity': BASE_DIR / "assets" / "images" / "charts voice final png.png",
            'invites': BASE_DIR / "assets" / "images" / "charts invites final png.png"
        }

        template_path = template_paths.get(chart_type)

        try:
            template = Image.open(template_path).convert("RGBA")
        except FileNotFoundError:
            template = Image.new('RGBA', (1200, 700), (47, 49, 54, 255))
            print(
                f"⚠️ Template not found at {template_path}, using fallback background")

        chart_width = 644
        chart_height = 250
        chart_img = chart_img.resize(
            (chart_width, chart_height), Image.Resampling.LANCZOS)
        template.paste(chart_img, (38, 170), chart_img)

        try:
            template = await self.draw_header_info(template, target_type, int(target_id), int(guild_id))
        except Exception as e:
            print(f"⚠️ Error drawing header: {e}")
            pass

        draw = ImageDraw.Draw(template)

        try:
            horndon_font = ImageFont.truetype(
                BASE_DIR / "assets" / "fonts" / "HorndonD.ttf", 16)
            horndon_small_font = ImageFont.truetype(
                BASE_DIR / "assets" / "fonts" / "HorndonD.ttf", 12)
        except:
            horndon_font = ImageFont.load_default()
            horndon_small_font = ImageFont.load_default()

        text_color = "white"
        shadow_color = "black"

        # TIME PERIOD - Use display_text
        draw_text_with_stroke(draw, (133, 93), display_text,
                              horndon_font, text_color, shadow_color, 1)

        # ROLE FILTER - USE DATABASE ROLE NAME
        role_text = role_name if role_name else "No Filter"

        with Pilmoji(template) as pilmoji:
            stroke_width = 1
            for dx in [-stroke_width, 0, stroke_width]:
                for dy in [-stroke_width, 0, stroke_width]:
                    if dx != 0 or dy != 0:
                        pilmoji.text((333 + dx, 95 + dy), role_text,
                                     font=horndon_font, fill=shadow_color)

            pilmoji.text((333, 95), role_text,
                         font=horndon_font, fill=text_color)

        total_value = "0"
        if "Messages" in label_text:
            total_value = label_text.split(
                "Messages ")[1] if "Messages " in label_text else "0"
            draw_text_with_stroke(draw, (623, 95), total_value, horndon_font,
                                  text_color, shadow_color, 1)
        elif "Voice Activity" in label_text:
            total_value = label_text.split("Voice Activity ")[
                1] if "Voice Activity " in label_text else "0"
            draw_text_with_stroke(draw, (655, 95), total_value, horndon_font,
                                  text_color, shadow_color, 1)
        elif "Invites" in label_text:
            total_value = label_text.split(
                "Invites ")[1] if "Invites " in label_text else "0"
            draw_text_with_stroke(draw, (600, 95), total_value, horndon_font,
                                  text_color, shadow_color, 1)

        if timestamps and len(timestamps) == 8:
            x_positions = self.get_timestamp_x_positions()
            timestamp_y_position = 430

            for i, (timestamp, x_pos) in enumerate(zip(timestamps, x_positions)):
                bbox = draw.textbbox(
                    (0, 0), timestamp, font=horndon_small_font)
                text_width = bbox[2] - bbox[0]
                centered_x = x_pos - (text_width // 2)

                draw_text_with_stroke(draw, (centered_x, timestamp_y_position),
                                      timestamp, horndon_small_font, text_color, shadow_color, 1)

        y_label_positions = [
            (27, 145),
            (27, 215),
            (27, 280),
            (27, 351),
            (30, 410)
        ]

        for (x, y), (value, label) in zip(y_label_positions, y_labels):
            draw_text_with_stroke(draw, (x, y), label,
                                  horndon_small_font, text_color, shadow_color, 1)

        output = io.BytesIO()
        template.save(output, format='PNG')
        output.seek(0)
        gc.collect()
        return output

    # =========================================================
    # INTERNAL FUNCTION FOR BOTH COMMANDS
    # =========================================================
    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def _handle_chart_command(self, ctx_or_interaction, chart_type: str, target=None, is_interaction=False):
        """Internal function to handle chart commands for both command types"""
        try:
            if is_interaction:
                user = ctx_or_interaction.user
                guild = ctx_or_interaction.guild
                send_method = ctx_or_interaction.followup.send
                defer_method = ctx_or_interaction.response.defer
            else:
                user = ctx_or_interaction.author
                guild = ctx_or_interaction.guild
                try:
                    await ctx_or_interaction.message.delete()
                except:
                    pass
                send_method = ctx_or_interaction.send
                defer_method = None

            if guild is None:
                if is_interaction:
                    await ctx_or_interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
                else:
                    await ctx_or_interaction.send("❌ This command can only be used in a server.", delete_after=5)
                return

            # Determine target based on chart type
            target_id = None
            if chart_type == "server":
                target_id = guild.id
            elif chart_type == "user":
                if target is None:
                    target_id = user.id
                elif isinstance(target, discord.User) or isinstance(target, discord.Member):
                    target_id = target.id
                elif isinstance(target, int):
                    target_id = target
                else:
                    if is_interaction:
                        await ctx_or_interaction.response.send_message("❌ Invalid user specified.", ephemeral=True)
                    else:
                        await ctx_or_interaction.send("❌ Invalid user specified.", delete_after=5)
                    return
            elif chart_type == "channel":
                if target is None:
                    if hasattr(ctx_or_interaction, 'channel'):
                        target_id = ctx_or_interaction.channel.id
                    else:
                        if is_interaction:
                            await ctx_or_interaction.response.send_message("❌ Please specify a channel or use this command in a channel.", ephemeral=True)
                        else:
                            await ctx_or_interaction.send("❌ Please specify a channel or use this command in a channel.", delete_after=5)
                        return
                elif isinstance(target, discord.TextChannel):
                    target_id = target.id
                elif isinstance(target, int):
                    target_id = target
                else:
                    if is_interaction:
                        await ctx_or_interaction.response.send_message("❌ Invalid channel specified.", ephemeral=True)
                    else:
                        await ctx_or_interaction.send("❌ Invalid channel specified.", delete_after=5)
                    return
            elif chart_type == "category":
                if target is None:
                    if hasattr(ctx_or_interaction, 'channel') and ctx_or_interaction.channel.category:
                        target_id = ctx_or_interaction.channel.category.id
                    else:
                        if is_interaction:
                            await ctx_or_interaction.response.send_message("❌ Please specify a category or use this command in a categorized channel.", ephemeral=True)
                        else:
                            await ctx_or_interaction.send("❌ Please specify a category or use this command in a categorized channel.", delete_after=5)
                        return
                elif isinstance(target, discord.CategoryChannel):
                    target_id = target.id
                elif isinstance(target, int):
                    target_id = target
                else:
                    if is_interaction:
                        await ctx_or_interaction.response.send_message("❌ Invalid category specified.", ephemeral=True)
                    else:
                        await ctx_or_interaction.send("❌ Invalid category specified.", delete_after=5)
                    return

            # Check permissions
            if chart_type == "user":
                if is_interaction:
                    if not await self.check_permission(ctx_or_interaction, target_user_id=target_id):
                        await self.send_permission_error(ctx_or_interaction, target_user_id=target_id)
                        return
                else:
                    if not self.check_permission_prefix(ctx_or_interaction, target_user_id=target_id):
                        embed = discord.Embed(
                            description="❌ Sorry! You don't have permission to use this command.",
                            color=discord.Color.red()
                        )
                        await ctx_or_interaction.send(embed=embed, delete_after=10)
                        return
            else:
                if is_interaction and not await self.check_permission(ctx_or_interaction):
                    await self.send_permission_error(ctx_or_interaction)
                    return

            # Check blacklist for user commands
            if chart_type == "user":
                db_stats = self.bot.get_cog('DatabaseStats')
                if db_stats:
                    if await db_stats.is_user_or_roles_blacklisted(int(guild.id), int(target_id)):
                        if is_interaction:
                            await ctx_or_interaction.followup.send("❌ This user is blacklisted and cannot be tracked.", ephemeral=True)
                        else:
                            await ctx_or_interaction.send("❌ This user is blacklisted and cannot be tracked.", delete_after=5)
                        return

            if is_interaction:
                await defer_method()

            # Get server default time range
            start_time, end_time, display_text, days_back_equiv = await self.get_server_default_time_range(guild.id)

            # Create view with time range parameters
            view = ChartView(self, chart_type, int(target_id), int(guild.id),
                             start_time=start_time, end_time=end_time,
                             days_back_equiv=days_back_equiv, display_text=display_text,
                             ctx=ctx_or_interaction if not is_interaction else None, using_server_default=True)

            # Initial chart generation
            await view.update_chart(ctx_or_interaction if is_interaction else None)

        except Exception as e:
            print(f"Error in _handle_chart_command: {e}")
            traceback.print_exc()
            if is_interaction:
                try:
                    await ctx_or_interaction.followup.send("❌ An error occurred while generating chart.", ephemeral=True)
                except:
                    pass
            else:
                try:
                    await ctx_or_interaction.send("❌ An error occurred while generating chart.", delete_after=10)
                except:
                    pass

    # =========================================================
    # SHORTCUT COMMANDS
    # =========================================================
    @commands.command(name="cu")
    async def chart_user_shortcut(self, ctx: commands.Context, user: Optional[discord.User] = None):
        """Shortcut command for user chart - same as chart user"""
        await self._handle_chart_command(ctx, "user", user, is_interaction=False)

    @commands.command(name="cs")
    async def chart_server_shortcut(self, ctx: commands.Context):
        """Shortcut command for server chart - same as chart server"""
        await self._handle_chart_command(ctx, "server", None, is_interaction=False)

    @commands.command(name="cch")
    async def chart_channel_shortcut(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Shortcut command for channel chart - same as chart channel"""
        await self._handle_chart_command(ctx, "channel", channel, is_interaction=False)

    @commands.command(name="cca")
    async def chart_category_shortcut(self, ctx: commands.Context, category: Optional[discord.CategoryChannel] = None):
        """Shortcut command for category chart - same as chart category"""
        await self._handle_chart_command(ctx, "category", category, is_interaction=False)

    # =========================================================
    # PREFIX COMMAND GROUP
    # =========================================================
    @commands.group(name="chart", invoke_without_command=True)
    async def chart_group_prefix(self, ctx: commands.Context):
        """Generate activity charts"""
        await ctx.send("Available commands:\n- `chart user [user]` - Generate user activity charts\n- `chart server` - Generate server-wide charts\n- `chart channel [channel]` - Generate channel-specific charts\n- `chart category [category]` - Generate category-specific charts\n\nShortcuts:\n- `cu [user]` - User chart shortcut\n- `cs` - Server chart shortcut\n- `cch [channel]` - Channel chart shortcut\n- `cca [category]` - Category chart shortcut")

    @chart_group_prefix.command(name="user")
    async def chart_user_prefix(self, ctx: commands.Context, user: Optional[discord.User] = None):
        """Generate user activity charts via prefix command"""
        await self._handle_chart_command(ctx, "user", user, is_interaction=False)

    @chart_group_prefix.command(name="server")
    async def chart_server_prefix(self, ctx: commands.Context):
        """Generate server-wide charts via prefix command"""
        await self._handle_chart_command(ctx, "server", None, is_interaction=False)

    @chart_group_prefix.command(name="channel")
    async def chart_channel_prefix(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Generate channel-specific charts via prefix command"""
        await self._handle_chart_command(ctx, "channel", channel, is_interaction=False)

    @chart_group_prefix.command(name="category")
    async def chart_category_prefix(self, ctx: commands.Context, category: Optional[discord.CategoryChannel] = None):
        """Generate category-specific charts via prefix command"""
        await self._handle_chart_command(ctx, "category", category, is_interaction=False)

    # =========================================================
    # SLASH COMMANDS
    # =========================================================
    chart_group = app_commands.Group(
        name="chart", description="Generate activity charts")

    @chart_group.command(name="user", description="Generate user activity charts")
    async def chart_user(self, interaction: discord.Interaction, user: discord.User):

        # Check permissions
        if not await self.check_permission(interaction, target_user_id=user.id):
            await self.send_permission_error(interaction, target_user_id=user.id)
            return

        await interaction.response.defer()

        db_stats = self.bot.get_cog('DatabaseStats')
        if db_stats:
            if await db_stats.is_user_or_roles_blacklisted(int(interaction.guild.id), int(user.id)):
                await interaction.followup.send("❌ This user is blacklisted and cannot be tracked.", ephemeral=True)
                return

        # Get server default time range
        start_time, end_time, display_text, days_back_equiv = await self.get_server_default_time_range(interaction.guild.id)

        view = ChartView(self, "user", int(user.id), int(interaction.guild.id),
                         start_time=start_time, end_time=end_time,
                         days_back_equiv=days_back_equiv, display_text=display_text,
                         using_server_default=True)
        await view.update_chart(interaction)

    @chart_group.command(name="server", description="Generate server-wide charts")
    async def chart_server(self, interaction: discord.Interaction):

        # Check permissions
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return

        await interaction.response.defer()

        # Get server default time range
        start_time, end_time, display_text, days_back_equiv = await self.get_server_default_time_range(interaction.guild.id)

        view = ChartView(self, "server", int(interaction.guild.id), int(interaction.guild.id),
                         start_time=start_time, end_time=end_time,
                         days_back_equiv=days_back_equiv, display_text=display_text,
                         using_server_default=True)
        await view.update_chart(interaction)

    @chart_group.command(name="channel", description="Generate channel-specific charts")
    async def chart_channel(self, interaction: discord.Interaction, channel: Union[discord.TextChannel, discord.VoiceChannel]):
        """
        Generate charts for a specific channel (text or voice)
        """
        # Check permissions
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return

        await interaction.response.defer()

        # Get server default time range
        start_time, end_time, display_text, days_back_equiv = await self.get_server_default_time_range(interaction.guild.id)

        view = ChartView(self, "channel", int(channel.id), int(interaction.guild.id),
                         start_time=start_time, end_time=end_time,
                         days_back_equiv=days_back_equiv, display_text=display_text,
                         using_server_default=True)
        await view.update_chart(interaction)

    @chart_group.command(name="category", description="Generate category-specific charts")
    async def chart_category(self, interaction: discord.Interaction, category: discord.CategoryChannel):

        # Check permissions
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return

        await interaction.response.defer()

        # Get server default time range
        start_time, end_time, display_text, days_back_equiv = await self.get_server_default_time_range(interaction.guild.id)

        view = ChartView(self, "category", int(category.id), int(interaction.guild.id),
                         start_time=start_time, end_time=end_time,
                         days_back_equiv=days_back_equiv, display_text=display_text,
                         using_server_default=True)
        await view.update_chart(interaction)


async def setup(bot):
    await bot.add_cog(ChartSystem(bot))
