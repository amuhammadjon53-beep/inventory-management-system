import os
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta, timezone
import matplotlib.pyplot as plt
import numpy as np
from io import BytesIO
import asyncio
from PIL import Image, ImageDraw, ImageFont
import aiohttp
import io
from pathlib import Path
from .ratelimiter import RateLimiter, RateLimitType, rate_limited, get_rate_limiter
import gc

BASE_DIR = Path(__file__).resolve().parent.parent


# INITIALIZATION

class TimezoneDistribution(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_sessions = {}
        self.background_image_path = BASE_DIR / "assets" / \
            "images" / "timezone chart final png.png"
        self.font_path = BASE_DIR / "assets" / "fonts" / "HorndonD.ttf"
        self.rate_limiter = get_rate_limiter()

    # Helper methods to get other cogs
    def get_db_cog(self):
        return self.bot.get_cog('DatabaseStats')

    def get_settings_cog(self):
        return self.bot.get_cog('Settings')

    # PERMISSION CHECKING
    async def check_permission(self, interaction: discord.Interaction) -> bool:
        """Check if user has permission to use the command based on server settings"""
        if interaction.user.guild_permissions.administrator:
            return True

        settings_cog = self.get_settings_cog()
        if not settings_cog:
            # If settings cog not available, default to admin only
            return interaction.user.guild_permissions.administrator

        try:
            settings = await settings_cog.get_guild_settings(interaction.guild_id)
            permission_level = settings.get('permission_level', 'Default')

            if permission_level == 'All':
                return True
            elif permission_level == 'Admin':
                return interaction.user.guild_permissions.administrator
            elif permission_level == 'Moderator':
                return interaction.user.guild_permissions.manage_guild
            elif permission_level == 'Default':
                return True  # Anyone can use by default
            elif permission_level == 'User Restriction':
                return True  # Anyone can use by default

            return True  # Default to allowing if settings not found
        except Exception as e:
            print(f"⚠️ Error checking permission: {e}")
            return interaction.user.guild_permissions.administrator

    async def send_permission_error(self, interaction: discord.Interaction):
        """Send permission error message"""
        settings_cog = self.get_settings_cog()

        if not settings_cog:
            required_permission = "Administrator"
        else:
            try:
                settings = await settings_cog.get_guild_settings(interaction.guild_id)
                permission_level = settings.get('permission_level', 'Default')

                if permission_level == 'Admin':
                    required_permission = "Administrator"
                elif permission_level == 'Moderator':
                    required_permission = "Manage Server"
                elif permission_level in ['Default', 'User Restriction']:
                    required_permission = "Administrator"  # Show admin since default allows all
                else:
                    required_permission = "Administrator"
            except:
                required_permission = "Administrator"

        embed = discord.Embed(
            title="❌ Permission Denied",
            description=f"Sorry! You need the `{required_permission}` permission to access this command.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # GET SERVER DEFAULT DAYS
    async def get_server_default_days(self, guild_id: int) -> tuple:
        """Get the default days back from server settings. Returns (days_back, display_text)"""
        try:
            settings_cog = self.get_settings_cog()
            if not settings_cog:
                return (30, "30 days")

            settings = await settings_cog.get_guild_settings(guild_id)
            mode = settings.get('default_time_mode', 'days_back')

            if mode == 'all_time':
                return (999999, "All Time")
            elif mode == 'days_back':
                days = settings.get('default_days_back') or 30
                return (days, f"{days} days")
            elif mode == 'date_range':
                from_date = settings.get('date_range_from')
                to_date = settings.get('date_range_to')

                if from_date:
                    try:
                        from_date_obj = datetime.fromisoformat(from_date)
                        now = datetime.now()
                        days_diff = (now - from_date_obj).days

                        if to_date:
                            to_date_obj = datetime.fromisoformat(to_date)
                            display = f"{from_date_obj.strftime('%m-%d-%Y')} → {to_date_obj.strftime('%m-%d-%Y')}"
                        else:
                            display = f"{from_date_obj.strftime('%m-%d-%Y')} → now"

                        return (days_diff, display)
                    except:
                        return (30, "Custom")
                else:
                    return (30, "Custom")
            elif mode == 'rolling_window':
                window_type = settings.get('rolling_window_type', 'week')

                if window_type == 'week':
                    weekday = settings.get('rolling_weekday', 0)  # 0 = Monday
                    weekday_names = ['Monday', 'Tuesday', 'Wednesday',
                                     'Thursday', 'Friday', 'Saturday', 'Sunday']
                    weekday_name = weekday_names[weekday] if 0 <= weekday < 7 else 'Monday'

                    now = datetime.now()
                    days_since = (now.weekday() - weekday) % 7
                    if days_since == 0:
                        days_since = 7

                    return (days_since, f"Since last {weekday_name}")
                elif window_type == 'month':
                    day_of_month = settings.get('rolling_month_day', 1)
                    now = datetime.now()

                    if now.day >= day_of_month:
                        days_since = now.day - day_of_month
                    else:
                        # Go back to previous month
                        from datetime import date
                        prev_month = date(now.year, now.month,
                                          1) - timedelta(days=1)
                        days_in_prev_month = prev_month.day
                        days_since = days_in_prev_month - day_of_month + now.day

                    if days_since == 0:
                        days_since = 30  # Approximate, for display purposes

                    # Format day with ordinal suffix
                    if 11 <= day_of_month <= 13:
                        suffix = "th"
                    else:
                        suffix = {1: "st", 2: "nd", 3: "rd"}.get(
                            day_of_month % 10, "th")

                    return (days_since, f"Since the {day_of_month}{suffix}")
                else:
                    return (30, "30 days")
            else:
                return (30, "Custom")

        except Exception as e:
            print(f"Error getting server default days: {e}")
            return (30, "30 days")

    # INTERNAL FUNCTION FOR BOTH COMMANDS
    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def _handle_distribution_command(self, ctx_or_interaction, is_interaction=False):
        """Internal function to handle distribution for both command types"""
        try:
            # Get context parameters
            if is_interaction:
                user = ctx_or_interaction.user
                guild = ctx_or_interaction.guild
                send_method = ctx_or_interaction.followup.send
            else:
                user = ctx_or_interaction.author
                guild = ctx_or_interaction.guild
                # Try to delete the command message
                try:
                    await ctx_or_interaction.message.delete()
                except:
                    pass
                send_method = ctx_or_interaction.send

            if guild is None:
                if is_interaction:
                    await ctx_or_interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
                else:
                    await ctx_or_interaction.send("❌ This command can only be used in a server.", delete_after=5)
                return

            # Check permission first
            if is_interaction:
                # For slash commands, use the permission check method
                if not await self.check_permission(ctx_or_interaction):
                    await self.send_permission_error(ctx_or_interaction)
                    return
                await ctx_or_interaction.response.defer()
            else:
                # For prefix commands, check permissions differently
                settings_cog = self.get_settings_cog()
                if not settings_cog:
                    # If settings cog not available, default to admin only
                    if not user.guild_permissions.administrator:
                        embed = discord.Embed(
                            title="❌ Permission Denied",
                            description="Sorry! You need the `Administrator` permission to access this command.",
                            color=discord.Color.red()
                        )
                        await ctx_or_interaction.send(embed=embed, delete_after=10)
                        return
                else:
                    try:
                        settings = await settings_cog.get_guild_settings(guild.id)
                        permission_level = settings.get(
                            'permission_level', 'Default')

                        if permission_level == 'All':
                            pass  # All users can use
                        elif permission_level == 'Admin':
                            if not user.guild_permissions.administrator:
                                embed = discord.Embed(
                                    title="❌ Permission Denied",
                                    description="Sorry! You need the `Administrator` permission to access this command.",
                                    color=discord.Color.red()
                                )
                                await ctx_or_interaction.send(embed=embed, delete_after=10)
                                return
                        elif permission_level == 'Moderator':
                            if not user.guild_permissions.manage_guild:
                                embed = discord.Embed(
                                    title="❌ Permission Denied",
                                    description="Sorry! You need the `Manage Server` permission to access this command.",
                                    color=discord.Color.red()
                                )
                                await ctx_or_interaction.send(embed=embed, delete_after=10)
                                return
                        elif permission_level in ['Default', 'User Restriction']:
                            pass  # Anyone can use by default
                    except Exception as e:
                        print(
                            f"⚠️ Error checking permission for prefix command: {e}")
                        # Default to admin only on error
                        if not user.guild_permissions.administrator:
                            embed = discord.Embed(
                                title="❌ Permission Denied",
                                description="Sorry! You need the `Administrator` permission to access this command.",
                                color=discord.Color.red()
                            )
                            await ctx_or_interaction.send(embed=embed, delete_after=10)
                            return

            db_cog = self.get_db_cog()
            if not db_cog:
                error_msg = "❌ Database connection not available. Please make sure the DatabaseStats cog is loaded."
                if is_interaction:
                    await ctx_or_interaction.followup.send(error_msg, ephemeral=True)
                else:
                    await ctx_or_interaction.send(error_msg, delete_after=10)
                return

            # Get timezone from settings
            timezone = await self.get_guild_timezone(guild.id)

            # Get server default days and display text
            default_days, display_text = await self.get_server_default_days(guild.id)

            view = self.TimezoneActivityView(
                self,
                guild,
                timezone=timezone,  # Use timezone from settings
                activity_type="Messages",
                days_back=default_days,
                display_text=display_text,  # Pass display_text
                using_server_default=True
            )

            chart_buffer = await view.generate_chart()
            file = discord.File(chart_buffer, filename="timezone_activity.png")

            msg = await send_method(file=file, view=view)

            self.active_sessions[msg.id] = {
                'guild_id': guild.id,
                'user_id': user.id,
                'timezone': timezone,
                'activity_type': "Messages",
                'current_days': default_days,
                'current_display_text': display_text,
                'view': view
            }

        except Exception as e:
            print(f"❌ Error in _handle_distribution_command: {e}")
            import traceback
            traceback.print_exc()
            error_msg = "❌ An error occurred while generating the activity chart. Please try again later."
            if is_interaction:
                try:
                    await ctx_or_interaction.followup.send(error_msg, ephemeral=True)
                except:
                    pass
            else:
                try:
                    await ctx_or_interaction.send(error_msg, delete_after=10)
                except:
                    pass

    # SHORTCUT COMMAND - d
    @commands.command(name="d")
    async def distribution_shortcut(self, ctx: commands.Context):
        """Shortcut command for distribution - same as distribution command"""
        await self._handle_distribution_command(ctx, is_interaction=False)

    # PREFIX COMMAND GROUP
    @commands.group(name="distribution", invoke_without_command=True)
    async def distribution_group_prefix(self, ctx: commands.Context):
        """Get per hour statistic distribution in the server"""
        await self._handle_distribution_command(ctx, is_interaction=False)

    # QUERY FUNCTION - UPDATED TO USE AGGREGATED TABLES WITH ALL TIME SUPPORT
    async def get_hourly_activity_data(self, guild_id: int, activity_type: str, days_back: int = 30, role_filter_ids=None):
        """Get hourly activity data using aggregated tables"""
        try:
            db_cog = self.get_db_cog()
            if not db_cog:
                print("⚠️ DatabaseStats cog not initialized")
                return [0] * 24

            # Ensure role_filter_ids is properly formatted
            if role_filter_ids is not None:
                # If it's a list, filter out None values
                if isinstance(role_filter_ids, list):
                    role_filter_ids = [
                        rid for rid in role_filter_ids if rid is not None]
                    if not role_filter_ids:
                        role_filter_ids = None
                # If it's a single integer, convert to list
                elif isinstance(role_filter_ids, int):
                    role_filter_ids = [role_filter_ids]
                # If it's empty string or other falsy value, set to None
                elif not role_filter_ids:
                    role_filter_ids = None

            # Handle All Time (days_back == 999999) - pass None for days_back to get all data
            if days_back == 999999:
                result = await db_cog.q_server_activity_distribution(
                    guild_id=guild_id,
                    days_back=None,  # Pass None for all time
                    role_filter_ids=role_filter_ids,
                    timezone_str='UTC'
                )
            else:
                result = await db_cog.q_server_activity_distribution(
                    guild_id=guild_id,
                    days_back=days_back,
                    role_filter_ids=role_filter_ids,
                    timezone_str='UTC'
                )

            if activity_type == "Messages":
                messages_data = result.get('messages', {})
                # Ensure all 24 hours are included
                hourly_data = [messages_data.get(
                    f'hour_{i}', 0) for i in range(24)]

                return hourly_data

            elif activity_type == "Voice Activity":
                voice_data = result.get('voice', {})
                # Ensure all 24 hours are included
                hourly_data = [voice_data.get(
                    f'hour_{i}', 0) for i in range(24)]
                return hourly_data

            elif activity_type == "Activities":
                activities_data = result.get('activities', {})
                # Ensure all 24 hours are included
                hourly_data = [activities_data.get(
                    f'hour_{i}', 0) for i in range(24)]
                return hourly_data

            else:
                return [0] * 24

        except Exception as e:
            print(f"❌ Error in get_hourly_activity_data: {e}")
            import traceback
            traceback.print_exc()
            return [0] * 24

    # TIMEZONE OFFSETS

    def apply_timezone_offset(self, hourly_data: list, timezone: str):
        timezone_offsets = {
            "UTC": 0, "GMT": 0,
            "EST": -5, "PST": -8, "CST": -6, "MST": -7,
            "CET": 1, "EET": 2, "IST": 5.5, "JST": 9,
            "AEST": 10, "NZST": 12
        }

        offset = timezone_offsets.get(timezone, 0)
        offset_hours = int(offset)

        shifted_data = [0] * 24
        for i in range(24):
            new_index = (i - offset_hours) % 24
            shifted_data[new_index] = hourly_data[i]

        return shifted_data

    # GET TIMEZONE FROM SETTINGS
    async def get_guild_timezone(self, guild_id: int) -> str:
        """Get timezone from settings for a guild"""
        settings_cog = self.get_settings_cog()
        if not settings_cog:
            return "UTC"

        try:
            settings = await settings_cog.get_guild_settings(guild_id)
            return settings.get('timezone', 'UTC')
        except Exception as e:
            print(f"⚠️ Error getting timezone for guild {guild_id}: {e}")
            return "UTC"

    # ACTIVITY LEVELS LOGIC

    def categorize_activity_levels(self, hourly_data: list):
        total_activity = sum(hourly_data)
        if total_activity == 0:
            return [("Low Activity", 0)] * 24

        avg_activity = total_activity / 24

        activity_levels = []
        peak_threshold = avg_activity * 2.0
        high_threshold = avg_activity * 1.5
        medium_threshold = avg_activity * 0.8

        for hour_activity in hourly_data:
            if hour_activity >= peak_threshold:
                activity_levels.append(("Peak Activity", hour_activity))
            elif hour_activity >= high_threshold:
                activity_levels.append(("High Activity", hour_activity))
            elif hour_activity >= medium_threshold:
                activity_levels.append(("Medium Activity", hour_activity))
            else:
                activity_levels.append(("Low Activity", hour_activity))

        return activity_levels

    # DRAWING FUNCTIONS

    def draw_text_with_stroke(self, draw, position, text, font, fill_color, stroke_color, stroke_width):
        x, y = position

        for dx in range(-stroke_width, stroke_width + 1):
            for dy in range(-stroke_width, stroke_width + 1):
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), text,
                              font=font, fill=stroke_color)

        draw.text((x, y), text, font=font, fill=fill_color)

    async def create_clock_pie_chart(self, activity_levels: list, timezone: str, activity_type: str, guild: discord.Guild, display_text: str, role_filter_name: str = None):
        try:
            background = Image.open(self.background_image_path).convert('RGBA')
            image = background.copy()
            draw = ImageDraw.Draw(image)

            try:
                font_huge = ImageFont.truetype(self.font_path, 40)
                font_large = ImageFont.truetype(self.font_path, 24)
                font_medium = ImageFont.truetype(self.font_path, 20)
                font_small = ImageFont.truetype(self.font_path, 16)
                font_clock = ImageFont.truetype(self.font_path, 16)
            except Exception as font_error:
                print(f"Font loading error: {font_error}")
                font_huge = ImageFont.load_default()
                font_large = ImageFont.load_default()
                font_medium = ImageFont.load_default()
                font_small = ImageFont.load_default()
                font_clock = ImageFont.load_default()

            def draw_text_with_stroke_fixed(draw, position, text, font, fill, stroke_fill, stroke_width):
                x, y = position
                for dx in [-stroke_width, 0, stroke_width]:
                    for dy in [-stroke_width, 0, stroke_width]:
                        if dx != 0 or dy != 0:
                            draw.text((x + dx, y + dy), text,
                                      font=font, fill=stroke_fill)

                draw.text((x, y), text, font=font, fill=fill)

            def fit_text_to_rectangle(text, text_start_x, text_start_y, rect_center_x, rect_center_y, rect_width, rect_height, is_username=False):
                font_paths = [self.font_path] if os.path.exists(
                    self.font_path) else []

                rect_left = rect_center_x - (rect_width // 2)
                rect_right = rect_center_x + (rect_width // 2)
                rect_top = rect_center_y - (rect_height // 2)
                rect_bottom = rect_center_y + (rect_height // 2)

                font_sizes = [40, 38, 36, 34, 32,
                              30, 28, 26, 24, 22, 20, 18, 16]

                for font_size in font_sizes:
                    try:
                        font = ImageFont.truetype(
                            font_paths[0], font_size) if font_paths else ImageFont.load_default()
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
                    font = ImageFont.truetype(
                        font_paths[0], smallest_font) if font_paths else ImageFont.load_default()
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

            avatar_x, avatar_y = 7, 10
            avatar_size = (60, 60)

            text_start_x = 85
            text_start_y = 30

            username_rectangle = {"center": (
                150, 30), "width": 183, "height": 35}

            try:
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

                    avatar_area = image.crop(
                        (avatar_x, avatar_y, avatar_x +
                         avatar_size[0], avatar_y + avatar_size[1])
                    ).convert('RGBA')

                    icon_with_bg = Image.new('RGBA', avatar_size, (0, 0, 0, 0))
                    icon_with_bg.paste(icon_image, (0, 0), icon_image)
                    avatar_area.paste(icon_with_bg, (0, 0), icon_with_bg)
                    image.paste(avatar_area.convert(
                        'RGB'), (avatar_x, avatar_y))
                    icon_image.close()
                    del icon_image
                    del icon_data

            except Exception as e:
                print(f"❌ Could not load server icon: {e}")

            server_name = guild.name
            fitted_text, text_font, text_pos = fit_text_to_rectangle(
                server_name,
                text_start_x,
                text_start_y,
                username_rectangle["center"][0],
                username_rectangle["center"][1],
                username_rectangle["width"],
                username_rectangle["height"],
                is_username=True
            )

            if fitted_text and text_font:
                draw_text_with_stroke_fixed(draw, text_pos, fitted_text, text_font,
                                            "white", "black", 1)
            else:
                draw_text_with_stroke_fixed(draw, (text_start_x, text_start_y), server_name,
                                            font_huge, "white", "black", 1)

            draw_text_with_stroke_fixed(draw, (560, 38), datetime.now().strftime("%B %d, %Y"),
                                        font_small, "white", "black", 1)

            # Use the passed display_text instead of days_back
            draw_text_with_stroke_fixed(
                draw, (105, 423), display_text, font_medium, "white", "black", 1)

            if role_filter_name:
                role_filter_text = f"Filter: {role_filter_name}"
                draw_text_with_stroke_fixed(
                    draw, (105, 450), role_filter_text, font_medium, "white", "black", 1)

            colors = {
                "Peak Activity": (255, 215, 0, 255),
                "High Activity": (255, 107, 107, 255),
                "Medium Activity": (81, 207, 102, 255),
                "Low Activity": (134, 142, 150, 255)
            }

            center_x, center_y = 380, 240
            radius = 180

            clock_layer = Image.new('RGBA', image.size, (0, 0, 0, 0))
            clock_draw = ImageDraw.Draw(clock_layer)

            for i, (category, _) in enumerate(activity_levels):
                start_angle = i * 15 - 90
                end_angle = (i + 1) * 15 - 90

                color = colors[category]

                clock_draw.pieslice([center_x - radius, center_y - radius,
                                     center_x + radius, center_y + radius],
                                    start_angle, end_angle, fill=color, outline="white", width=1)

            inner_radius = 10
            clock_draw.ellipse([center_x - inner_radius, center_y - inner_radius,
                                center_x + inner_radius, center_y + inner_radius],
                               fill=(0, 0, 0, 255))

            # Get timezone offset for hour labels
            timezone_offsets = {
                "UTC": 0, "GMT": 0,
                "EST": -5, "PST": -8, "CST": -6, "MST": -7,
                "CET": 1, "EET": 2, "IST": 5.5, "JST": 9,
                "AEST": 10, "NZST": 12
            }
            offset = timezone_offsets.get(timezone, 0)
            offset_hours = int(offset)

            number_radius = radius + 15

            for i in range(24):
                angle = np.radians(i * 15 - 90)

                x = center_x + number_radius * np.cos(angle)
                y = center_y + number_radius * np.sin(angle)

                # Calculate the hour number based on timezone offset
                # Show 1-24 instead of 0-23 for readability
                hour_number = ((i + offset_hours) % 24) + 1

                try:
                    bbox = clock_draw.textbbox(
                        (0, 0), str(hour_number), font=font_clock)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    text_x = x - text_width / 2
                    text_y = y - text_height / 2
                except:
                    text_x = x - 8
                    text_y = y - 8

                draw_text_with_stroke_fixed(clock_draw, (text_x, text_y), str(hour_number),
                                            font_clock, "white", "black", 2)

            image = Image.alpha_composite(image, clock_layer)

            buffer = BytesIO()
            image.save(buffer, format='PNG')
            buffer.seek(0)
            gc.collect()

            return buffer

        except Exception as e:
            print(f"Error creating Pillow chart: {e}")
            import traceback
            traceback.print_exc()
            return self.create_clock_pie_chart_fallback(activity_levels, timezone, activity_type, display_text, role_filter_name)

    def create_clock_pie_chart_fallback(self, activity_levels: list, timezone: str, activity_type: str, display_text: str, role_filter_name: str = None):
        plt.style.use('default')
        fig, ax = plt.subplots(
            figsize=(10, 10), subplot_kw=dict(projection='polar'))

        colors = {
            "Peak Activity": "#FFD700",
            "High Activity": "#FF6B6B",
            "Medium Activity": "#51CF66",
            "Low Activity": "#868E96"
        }

        theta = np.linspace(0, 2*np.pi, 24, endpoint=False)
        width = 2*np.pi / 24

        for i, (category, _) in enumerate(activity_levels):
            color = colors[category]
            ax.bar(theta[i], 1, width=width, bottom=0, color=color,
                   alpha=1.0, edgecolor='white', linewidth=1)

        # Add title with time period info
        title = f"{activity_type} Distribution - {display_text}"
        if role_filter_name:
            title += f" (Filter: {role_filter_name})"
        ax.set_title(title, pad=20, fontsize=12)

        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)
        ax.set_ylim(0, 1)
        ax.set_yticklabels([])
        ax.grid(False)
        ax.spines['polar'].set_visible(False)

        buffer = BytesIO()
        plt.savefig(buffer, format='png', bbox_inches='tight',
                    dpi=100, transparent=False, facecolor='white')
        buffer.seek(0)
        plt.close()
        gc.collect()

        return buffer

    # TIME MODAL

    class TimezoneTimeModal(discord.ui.Modal, title='Custom Time Period'):
        def __init__(self, cog_instance, guild, view):
            super().__init__(timeout=300)
            self.cog = cog_instance
            self.guild = guild
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

                await interaction.response.defer(ephemeral=False)

                if self.view:
                    self.view.current_days = days
                    # Update display text
                    self.view.current_display_text = f"{days} days"
                    self.view.using_server_default = False
                    await self.view.update_message(interaction)
                else:
                    await interaction.followup.send("❌ Could not update chart.", ephemeral=True)

            except ValueError:
                await interaction.response.send_message("❌ Please enter a valid number.", ephemeral=True)
            except Exception as e:
                print(f"Error in timezone modal submit: {e}")
                await interaction.followup.send("❌ An error occurred while updating stats.", ephemeral=True)

    class RoleFilterModal(discord.ui.Modal, title='Input Role ID'):
        def __init__(self, cog_instance, guild, view):
            super().__init__(timeout=300)
            self.cog = cog_instance
            self.guild = guild
            self.view = view

        role_id = discord.ui.TextInput(
            label='Enter Role ID or "none"',
            placeholder='e.g., 123456789012345678 or "none"',
            min_length=1,
            max_length=20,
            required=True
        )

        async def on_submit(self, interaction: discord.Interaction):
            try:
                role_input = self.role_id.value.strip().lower()

                if role_input == "none":
                    role_name = "No Filter"
                    role_filter_ids = None
                else:
                    try:
                        role_id = int(role_input)
                        role = self.guild.get_role(role_id)

                        if role is None:
                            embed = discord.Embed(
                                title="❌ Invalid Role ID",
                                description="Sorry! The role id you inputted is not valid, please try again.",
                                color=discord.Color.red()
                            )
                            await interaction.response.send_message(embed=embed, ephemeral=True)
                            return

                        role_name = role.name
                        role_filter_ids = [role_id]
                    except ValueError:
                        embed = discord.Embed(
                            title="❌ Invalid Input",
                            description="Please enter a valid role ID number or 'none'.",
                            color=discord.Color.red()
                        )
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                        return

                await interaction.response.defer(ephemeral=False)

                if self.view:
                    self.view.role_filter_ids = role_filter_ids
                    self.view.role_filter_name = role_name
                    await self.view.update_message(interaction)
                else:
                    await interaction.followup.send("❌ Could not update chart.", ephemeral=True)

            except Exception as e:
                print(f"Error in role filter modal submit: {e}")
                embed = discord.Embed(
                    title="❌ Error",
                    description="An error occurred while processing your request.",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)

    # ACTIVITY TYPE DROPDOWN MENU

    class ActivityTypeSelect(discord.ui.Select):
        def __init__(self, current_type: str = "Messages"):
            options = [
                discord.SelectOption(
                    label="Messages",
                    description="Message activity distribution",
                    value="Messages",
                    default=(current_type == "Messages")
                ),
                discord.SelectOption(
                    label="Voice Activity",
                    description="Voice time distribution",
                    value="Voice Activity",
                    default=(current_type == "Voice Activity")
                ),
                discord.SelectOption(
                    label="Activities",
                    description="General activity distribution",
                    value="Activities",
                    default=(current_type == "Activities")
                )
            ]

            super().__init__(
                placeholder="Select activity type...",
                options=options,
                custom_id="activity_type_select"
            )

        async def callback(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=False, thinking=False)
            view = self.view
            view.activity_type = self.values[0]
            await view.update_message(interaction)

    # MAIN VIEW

    class TimezoneActivityView(discord.ui.View):
        def __init__(self, cog, guild: discord.Guild, timezone: str = "UTC", activity_type: str = "Messages", days_back: int = 30, display_text: str = "30 days", using_server_default: bool = True):
            super().__init__(timeout=600)
            self.cog = cog
            self.guild = guild
            self.timezone = timezone
            self.activity_type = activity_type
            self.current_days = days_back
            self.current_display_text = display_text  # Store display text
            self.show_time_buttons = False
            self.role_filter_ids = None
            self.role_filter_name = None
            self.using_server_default = using_server_default
            self._update_buttons()

        def _update_buttons(self):
            self.clear_items()

            self.add_item(
                TimezoneDistribution.ActivityTypeSelect(self.activity_type))

            refresh_button = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="🔄",
                custom_id="timezone_refresh"
            )
            refresh_button.callback = self.refresh_callback

            time_settings_button = discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label="⏰ Time Settings",
                custom_id="timezone_time_settings"
            )
            time_settings_button.callback = self.time_settings_callback

            role_filter_button = discord.ui.Button(
                style=discord.ButtonStyle.primary,
                label="Input Role Id",
                custom_id="timezone_role_filter"
            )
            role_filter_button.callback = self.role_filter_callback

            self.add_item(refresh_button)
            self.add_item(time_settings_button)
            self.add_item(role_filter_button)

            if self.show_time_buttons:
                all_time_button = discord.ui.Button(
                    style=discord.ButtonStyle.primary if self.current_days == 999999 else discord.ButtonStyle.secondary,
                    label="All Time",
                    custom_id="timezone_all_time"
                )
                all_time_button.callback = self.all_time_callback
                self.add_item(all_time_button)

                days_7_button = discord.ui.Button(
                    style=discord.ButtonStyle.primary if self.current_days == 7 else discord.ButtonStyle.secondary,
                    label="7 Days",
                    custom_id="timezone_days_7"
                )
                days_7_button.callback = self.days_7_callback
                self.add_item(days_7_button)

                days_14_button = discord.ui.Button(
                    style=discord.ButtonStyle.primary if self.current_days == 14 else discord.ButtonStyle.secondary,
                    label="14 Days",
                    custom_id="timezone_days_14"
                )
                days_14_button.callback = self.days_14_callback
                self.add_item(days_14_button)

                days_30_button = discord.ui.Button(
                    style=discord.ButtonStyle.primary if self.current_days == 30 else discord.ButtonStyle.secondary,
                    label="30 Days",
                    custom_id="timezone_days_30"
                )
                days_30_button.callback = self.days_30_callback
                self.add_item(days_30_button)

                days_90_button = discord.ui.Button(
                    style=discord.ButtonStyle.primary if self.current_days == 90 else discord.ButtonStyle.secondary,
                    label="90 Days",
                    custom_id="timezone_days_90"
                )
                days_90_button.callback = self.days_90_callback
                self.add_item(days_90_button)

                # Use display text for custom button label
                custom_label = self.current_display_text if self.current_days not in [
                    7, 14, 30, 90, 999999] else "Custom"
                if len(custom_label) > 20:
                    custom_label = custom_label[:17] + "..."
                custom_button = discord.ui.Button(
                    style=discord.ButtonStyle.success,
                    label=custom_label,
                    custom_id="timezone_custom_days"
                )
                custom_button.callback = self.custom_days_callback
                self.add_item(custom_button)

        async def refresh_callback(self, interaction: discord.Interaction):
            await self.handle_refresh(interaction)

        async def time_settings_callback(self, interaction: discord.Interaction):
            await self.handle_time_settings(interaction)

        async def role_filter_callback(self, interaction: discord.Interaction):
            await self.handle_role_filter(interaction)

        async def all_time_callback(self, interaction: discord.Interaction):
            await self.handle_time_period_change(interaction, 999999, "All Time")

        async def days_7_callback(self, interaction: discord.Interaction):
            await self.handle_time_period_change(interaction, 7, "7 days")

        async def days_14_callback(self, interaction: discord.Interaction):
            await self.handle_time_period_change(interaction, 14, "14 days")

        async def days_30_callback(self, interaction: discord.Interaction):
            await self.handle_time_period_change(interaction, 30, "30 days")

        async def days_90_callback(self, interaction: discord.Interaction):
            await self.handle_time_period_change(interaction, 90, "90 days")

        async def custom_days_callback(self, interaction: discord.Interaction):
            await self.handle_custom_days(interaction)

        async def handle_refresh(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=False, thinking=False)
            await self.update_message(interaction)

        async def handle_time_settings(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=False, thinking=False)
            self.show_time_buttons = not self.show_time_buttons
            self._update_buttons()
            await interaction.edit_original_response(view=self)

        async def handle_role_filter(self, interaction: discord.Interaction):
            modal = TimezoneDistribution.RoleFilterModal(
                self.cog, self.guild, self)
            await interaction.response.send_modal(modal)

        async def handle_time_period_change(self, interaction: discord.Interaction, days: int, display_text: str = None):
            await interaction.response.defer(ephemeral=False, thinking=False)
            self.current_days = days
            if display_text is not None:
                self.current_display_text = display_text
            self.using_server_default = False
            self.show_time_buttons = False
            await self.update_message(interaction)

        async def handle_custom_days(self, interaction: discord.Interaction):
            modal = TimezoneDistribution.TimezoneTimeModal(
                self.cog, self.guild, self)
            await interaction.response.send_modal(modal)

        async def generate_chart(self):
            # Use stored display_text for the chart
            hourly_data = await self.cog.get_hourly_activity_data(
                self.guild.id,
                self.activity_type,
                self.current_days,
                self.role_filter_ids
            )
            timezone_data = self.cog.apply_timezone_offset(
                hourly_data, self.timezone)
            activity_levels = self.cog.categorize_activity_levels(
                timezone_data)
            chart_buffer = await self.cog.create_clock_pie_chart(
                activity_levels, self.timezone, self.activity_type, self.guild, self.current_display_text, self.role_filter_name
            )
            return chart_buffer

        async def update_message(self, interaction: discord.Interaction):
            try:
                chart_buffer = await self.generate_chart()
                self._update_buttons()

                file = discord.File(
                    chart_buffer, filename="timezone_activity.png")

                if interaction.response.is_done():
                    await interaction.edit_original_response(attachments=[file], view=self)
                else:
                    await interaction.response.edit_message(attachments=[file], view=self)

            except Exception as e:
                print(f"❌ Error updating timezone activity message: {e}")
                try:
                    if not interaction.response.is_done():
                        await interaction.response.send_message("❌ An error occurred while updating the activity chart.", ephemeral=True)
                    else:
                        await interaction.followup.send("❌ An error occurred while updating the activity chart.", ephemeral=True)
                except:
                    pass

    # SLASH COMMAND

    @app_commands.command(name="distribution", description="Get per hour statistic distribution in the server.")
    async def timezone_activity_distribution(self, interaction: discord.Interaction):
        # Check permission first
        if not await self.check_permission(interaction):
            await self.send_permission_error(interaction)
            return

        await self._handle_distribution_command(interaction, is_interaction=True)

    async def cog_unload(self):
        self.active_sessions.clear()
        print("TimezoneDistribution cog: Cleaned up active sessions")


# SETUP

async def setup(bot):
    await bot.add_cog(TimezoneDistribution(bot))
