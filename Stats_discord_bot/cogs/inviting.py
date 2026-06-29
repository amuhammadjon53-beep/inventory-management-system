import json
import aiohttp
import io
from PIL import Image, ImageDraw, ImageFont
from typing import Optional, List, Tuple, Dict, Any
import os
import asyncpg
from datetime import datetime, timedelta, timezone
from discord import app_commands
from discord.ext import commands
import discord
from pathlib import Path
import pytz
from .ratelimiter import RateLimiter, RateLimitType, rate_limited, get_rate_limiter
import gc
from discord.ext import tasks

# CONFIGURATION

BASE_DIR = Path(__file__).resolve().parent.parent


class InviteConfig:

    USERS_PER_PAGE = 10
    MAX_ROLES_IN_SELECT = 25
    DEFAULT_DAYS_BACK = 30
    TIME_PERIODS = [7, 14, 30]
    MAX_CUSTOM_DAYS = 2000
    TEMPLATE_PATH = BASE_DIR / "assets" / "images" / "leaderboards final png.png"
    FONT_PATH = BASE_DIR / "assets" / "fonts" / "HorndonD.ttf"


# PAGE JUMP MODAL
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


# HELPER FUNCTIONS

async def check_user_exists(bot, user_id: int) -> bool:
    """
    Check if a Discord user exists (account is not deleted).
    Returns True if user exists, False if account is deleted.
    """
    try:
        user = await bot.fetch_user(user_id)
        return user is not None
    except discord.NotFound:
        return False
    except discord.HTTPException:
        return True
    except Exception:
        return True


async def get_user_display_info(bot, guild: discord.Guild, user_id: int,
                                check_exists: bool = True) -> Dict[str, Any]:
    """
    Get display information for a user, handling deleted accounts.
    Returns dict with 'name', 'is_deleted', and optionally 'member' if in guild.
    """
    user_info = {
        'name': '[Deleted User]',
        'is_deleted': True,
        'member': None
    }

    try:
        if check_exists:
            user_exists = await check_user_exists(bot, user_id)
            if not user_exists:
                return user_info

        member = guild.get_member(user_id)
        if member:
            user_info.update({
                'name': member.name,
                'is_deleted': False,
                'member': member
            })
            return user_info

        try:
            # This fetch_user call will be rate-limited by the check_user_exists function above
            # No need for additional rate limiting here
            user = await bot.fetch_user(user_id)
            user_info.update({
                'name': user.name,
                'is_deleted': False,
                'member': None
            })
        except discord.NotFound:
            return user_info
        except Exception:
            user_info.update({
                'name': f'User {user_id}',
                'is_deleted': False,
                'member': None
            })

    except Exception as e:
        print(f"⚠️ Error getting user info for ID {user_id}: {e}")
        user_info.update({
            'name': f'User {user_id}',
            'is_deleted': False,
            'member': None
        })

    return user_info


# PERMISSION CHECK FUNCTIONS

async def check_command_permission(interaction: discord.Interaction, command_name: str, target_user: Optional[discord.Member] = None) -> bool:
    """
    Check if user has permission to use command based on server settings.
    Returns True if allowed, False if not allowed.
    """
    try:
        guild = interaction.guild
        user = interaction.user

        # Users with administrator permission can always use commands
        if user.guild_permissions.administrator:
            return True

        # Get settings cog
        settings_cog = interaction.client.get_cog('Settings')
        if not settings_cog:
            # If settings cog not available, use default permissions
            return True

        # Get guild settings
        settings = await settings_cog.get_guild_settings(guild.id)
        permission_level = settings.get('permission_level', 'Default')

        # Check permission levels
        if permission_level == 'All':
            return True

        elif permission_level == 'Default':
            # Default Discord permissions apply
            return True

        elif permission_level == 'User Restriction':
            # User can only use commands on themselves
            if target_user and target_user.id != user.id:
                embed = discord.Embed(
                    title="❌ Permission Denied",
                    description="Sorry! You can only use this command on yourself.",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return False
            return True

        elif permission_level == 'Admin':
            # Only users with administrator permission
            if not user.guild_permissions.administrator:
                embed = discord.Embed(
                    title="❌ Permission Denied",
                    description="Sorry! You need the `Administrator` permission to access this command.",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return False
            return True

        elif permission_level == 'Moderator':
            # Only users with manage_guild permission
            if not user.guild_permissions.manage_guild:
                embed = discord.Embed(
                    title="❌ Permission Denied",
                    description="Sorry! You need the `Manage Server` permission to access this command.",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return False
            return True

        return True

    except Exception as e:
        print(f"Error checking permission: {e}")
        return True


# TIMEZONE HELPER FUNCTIONS

async def get_guild_timezone(guild_id: int) -> pytz.timezone:
    """
    Get timezone for guild from settings.
    Defaults to UTC if not set or invalid.
    """
    try:
        settings_cog = discord.utils.get(
            discord.Client.get_cog, name='Settings')
        if settings_cog:
            settings = await settings_cog.get_guild_settings(guild_id)
            tz_str = settings.get('timezone', 'UTC')

            # Map common timezone abbreviations
            tz_mapping = {
                'EST': 'America/New_York',
                'PST': 'America/Los_Angeles',
                'CST': 'America/Chicago',
                'MST': 'America/Denver',
                'GMT': 'Europe/London',
                'CET': 'Europe/Paris',
                'EET': 'Europe/Athens',
                'IST': 'Asia/Kolkata',
                'JST': 'Asia/Tokyo',
                'AEST': 'Australia/Sydney',
                'NZST': 'Pacific/Auckland'
            }

            if tz_str in tz_mapping:
                tz_str = tz_mapping[tz_str]

            return pytz.timezone(tz_str)
    except:
        pass

    return pytz.UTC


async def convert_utc_to_guild_time(utc_time: datetime, guild_id: int) -> datetime:
    """
    Convert UTC time to guild's local timezone.
    """
    if not utc_time:
        return utc_time

    try:
        guild_tz = await get_guild_timezone(guild_id)

        if utc_time.tzinfo is None:
            utc_time = utc_time.replace(tzinfo=pytz.UTC)

        return utc_time.astimezone(guild_tz)
    except:
        return utc_time


def format_datetime_for_display(dt: datetime, guild_id: int = None) -> str:
    """
    Format datetime for display, optionally converting to guild timezone.
    """
    if not dt:
        return "Unknown"

    try:
        if guild_id:
            dt = convert_utc_to_guild_time(dt, guild_id)

        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        if isinstance(dt, datetime):
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        return str(dt)


# FONTS

def get_fonts():

    try:
        custom_font_path = InviteConfig.FONT_PATH
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
        try:
            font_small = ImageFont.truetype("Helvetica.ttf", 16)
            font_medium = ImageFont.truetype("Helvetica.ttf", 20)
            font_large = ImageFont.truetype("Helvetica.ttf", 24)
            font_larger = ImageFont.truetype("Helvetica.ttf", 30)
            font_huge = ImageFont.truetype("Helvetica.ttf", 40)
            font_giant = ImageFont.truetype("Helvetica.ttf", 60)
            return font_small, font_medium, font_large, font_larger, font_huge, font_giant
        except:
            font_small = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_large = ImageFont.load_default()
            font_larger = ImageFont.load_default()
            font_huge = ImageFont.load_default()
            font_giant = ImageFont.load_default()
            return font_small, font_medium, font_large, font_larger, font_huge, font_giant


# DRAWING FUNCTIONS

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
    draw.pieslice([x2 - radius * 2, y1, x2, y1 + radius * 2],
                  270, 360, fill=fill, outline=outline)
    draw.pieslice([x1, y2 - radius * 2, x1 + radius * 2, y2],
                  90, 180, fill=fill, outline=outline)
    draw.pieslice([x2 - radius * 2, y2 - radius * 2, x2, y2],
                  0, 90, fill=fill, outline=outline)


# IMAGE GENERATION

async def generate_invite_leaderboard_image(
    bot,
    guild: discord.Guild,
    leaderboard_data: list,
    display_text: str,
    role_id: str = None,
    role_name: str = None,
    invite_type_filter: str = "all",
    page: int = 0
):

    template_path = InviteConfig.TEMPLATE_PATH
    try:
        image = Image.open(template_path)
    except FileNotFoundError:
        image = Image.new('RGB', (800, 600), color='#2F3136')

    if image.mode != "RGB":
        image = image.convert("RGB")

    draw = ImageDraw.Draw(image)
    font_small, font_medium, font_large, font_larger, font_huge, font_giant = get_fonts()

    def fit_text_to_rectangle(text, text_start_x, text_start_y, rect_center_x, rect_center_y, rect_width, rect_height, is_username=False):

        font_paths = [
            BASE_DIR / "assets" / "fonts" / "HorndonD.ttf"]

        initial_font_size = 40

        rect_left = rect_center_x - (rect_width // 2)
        rect_right = rect_center_x + (rect_width // 2)
        rect_top = rect_center_y - (rect_height // 2)
        rect_bottom = rect_center_y + (rect_height // 2)

        font_sizes = [40, 38, 36, 34, 32, 30, 28, 26, 24, 22, 20, 18, 16]

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

    avatar_x, avatar_y = 7, 10
    avatar_size = (60, 60)

    text_start_x = 85
    text_start_y = 30

    username_rectangle = {"center": (150, 30), "width": 183, "height": 35}

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
            image.paste(avatar_area.convert('RGB'), (avatar_x, avatar_y))
            icon_image.close()
            del icon_image
            del icon_data

    except Exception as e:
        print(f"❌ Could not add server icon: {e}")

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

        stroke_width = 1
        for dx in [-stroke_width, 0, stroke_width]:
            for dy in [-stroke_width, 0, stroke_width]:
                if dx != 0 or dy != 0:
                    draw.text((text_pos[0] + dx, text_pos[1] + dy),
                              fitted_text, font=text_font, fill="black")

        draw.text(text_pos, fitted_text, font=text_font, fill="white")
    else:

        draw_text_with_stroke(draw, (text_start_x, text_start_y), server_name,
                              font_huge, "white", "black", 2)

    # USE DATABASE ROLE NAME INSTEAD OF DISCORD API
    role_text = role_name if role_name else "No Filter"
    draw_text_with_stroke(draw, (70, 424), role_text,
                          font_small, "white", "black", 1)

    # Use display_text for time period
    draw_text_with_stroke(
        draw, (630, 422), display_text, font_small, "white", "black", 1)
    draw_text_with_stroke(draw, (550, 38), datetime.now().strftime(
        "%B %d, %Y"), font_small, "white", "black", 1)

    if leaderboard_data:
        total_users = len(leaderboard_data)
        users_per_page = InviteConfig.USERS_PER_PAGE
        total_pages = (total_users + users_per_page - 1) // users_per_page
        draw_text_with_stroke(
            draw, (400, 450), f"Page {page + 1}/{total_pages}", font_medium, "white", "black", 1)
    else:
        total_pages = 1

    if leaderboard_data:
        display_data = []

        for user_data in leaderboard_data:
            user_id = user_data['user_id']

            user_info = await get_user_display_info(bot, guild, int(user_id))

            name = user_info['name']
            # Use display_invites from the query result
            invite_count = user_data.get(
                'display_invites', user_data.get('valid_invites', 0))

            display_data.append((name, invite_count))

        start_idx = page * InviteConfig.USERS_PER_PAGE
        end_idx = min(start_idx + InviteConfig.USERS_PER_PAGE,
                      len(display_data))
        page_data = display_data[start_idx:end_idx]

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

        for i, ((name, invite_count), (box_x, box_y)) in enumerate(zip(page_data, positions)):
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

            # Display invite count with appropriate label based on filter
            filter_labels = {
                'all': "invites",
                'valid': "valid invites",
                'suspicious': "suspicious invites",
                'left': "left invites"
            }
            label = filter_labels.get(invite_type_filter, "invites")
            value_text = f"{invite_count:,} {label}"

            rank_text = f"#{global_rank}"
            rank_bbox = draw.textbbox((0, 0), rank_text, font=font_medium)
            rank_width = rank_bbox[2] - rank_bbox[0]

            value_bbox = draw.textbbox((0, 0), value_text, font=font_medium)
            value_width = value_bbox[2] - value_bbox[0]

            available_name_width = box_width - placement_width - value_width - 20

            display_name = name
            name_bbox = draw.textbbox((0, 0), display_name, font=font_medium)
            name_width = name_bbox[2] - name_bbox[0]

            if name_width > available_name_width:
                try:
                    smaller_font = ImageFont.truetype(font_medium.path, size=16) if hasattr(
                        font_medium, 'path') else font_small
                    smaller_bbox = draw.textbbox(
                        (0, 0), display_name, font=smaller_font)
                    smaller_width = smaller_bbox[2] - smaller_bbox[0]

                    if smaller_width <= available_name_width:
                        name_font = smaller_font
                    else:
                        name_font = font_medium
                        while len(display_name) > 3:
                            display_name = display_name[:-4] + "..."
                            truncated_bbox = draw.textbbox(
                                (0, 0), display_name, font=name_font)
                            truncated_width = truncated_bbox[2] - \
                                truncated_bbox[0]
                            if truncated_width <= available_name_width:
                                break
                except:
                    name_font = font_medium
                    while len(display_name) > 3:
                        display_name = display_name[:-4] + "..."
                        truncated_bbox = draw.textbbox(
                            (0, 0), display_name, font=name_font)
                        truncated_width = truncated_bbox[2] - truncated_bbox[0]
                        if truncated_width <= available_name_width:
                            break
            else:
                name_font = font_medium

            rank_height = rank_bbox[3] - rank_bbox[1]
            name_height = name_bbox[3] - name_bbox[1] if name_font == font_medium else draw.textbbox(
                (0, 0), display_name, font=name_font)[3] - draw.textbbox((0, 0), display_name, font=name_font)[1]
            value_height = value_bbox[3] - value_bbox[1]

            rank_y = box_y + (box_height - rank_height) // 2
            name_y = box_y + (box_height - name_height) // 2
            value_y = box_y + (box_height - value_height) // 2

            rank_x = box_x + (placement_width - rank_width) // 2
            draw_text_with_stroke(draw, (rank_x, rank_y),
                                  rank_text, font_medium, "white", "black", 1)

            name_x = box_x + placement_width + 8
            draw_text_with_stroke(draw, (name_x, name_y),
                                  display_name, name_font, "white", "black", 1)

            value_x = box_x + box_width - value_width - 8
            draw_text_with_stroke(draw, (value_x, value_y),
                                  value_text, font_medium, "white", "black", 1)
    else:
        cx, cy = image.size[0] // 2, image.size[1] // 2
        draw_text_centered_with_stroke(
            draw, "NO DATA AVAILABLE", (cx, cy), font_giant, "white", "black", 3)

    img_bytes = io.BytesIO()
    image.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    gc.collect()
    return img_bytes


# MODAL CLASSES

class InviteLeaderboardTimeModal(discord.ui.Modal, title='Custom Time Period'):
    def __init__(self, cog_instance, current_view):
        super().__init__(timeout=300)
        self.cog = cog_instance
        self.current_view = current_view

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
            if days <= 0 or days > InviteConfig.MAX_CUSTOM_DAYS:
                await interaction.response.send_message(f"❌ Please enter a number between 1 and {InviteConfig.MAX_CUSTOM_DAYS} days.", ephemeral=True)
                return

            await interaction.response.defer(thinking=True)

            now = datetime.utcnow()
            self.current_view.current_start_time = now - timedelta(days=days)
            self.current_view.current_end_time = now
            self.current_view.current_days_back_equiv = days
            self.current_view.current_display_text = f"{days} days"
            self.current_view.using_server_default = False
            self.current_view.show_time_buttons = False
            self.current_view.page = 0
            self.current_view._update_buttons()

            img_bytes = await self.current_view.generate_image()

            try:
                file = discord.File(
                    img_bytes, filename="invite_leaderboard.png")
                await interaction.edit_original_response(attachments=[file], view=self.current_view)
            except Exception as e:
                print(f"Error editing original response: {e}")
                file = discord.File(
                    img_bytes, filename="invite_leaderboard.png")
                await interaction.followup.edit_message(interaction.message.id, attachments=[file], view=self.current_view)

        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number.", ephemeral=True)
        except Exception as e:
            print(f"Error in invite modal submit: {e}")
            await interaction.followup.send("❌ An error occurred while updating the leaderboard.", ephemeral=True)


class InviteRoleInputModal(discord.ui.Modal, title='Filter By Role'):
    def __init__(self, cog_instance, current_view):
        super().__init__(timeout=300)
        self.cog = cog_instance
        self.current_view = current_view

    role_id = discord.ui.TextInput(
        label='Enter Role ID',
        placeholder='e.g., 123456789012345678 or "none" for no filter',
        min_length=1,
        max_length=20,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        role_id_input = self.role_id.value.strip().lower()

        if role_id_input == "none":
            self.current_view.selected_role_id = "none"
        else:
            try:
                role_id_int = int(role_id_input)
                role = self.current_view.guild.get_role(role_id_int)
                if role:
                    self.current_view.selected_role_id = str(role_id_int)
                else:
                    embed = discord.Embed(
                        title="❌ Invalid Role ID",
                        description="Sorry! The role id you inputted is not valid, please try again.",
                        color=discord.Color.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
            except ValueError:
                embed = discord.Embed(
                    title="❌ Invalid Role ID",
                    description="Sorry! The role id you inputted is not valid, please try again.",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

        await interaction.response.defer(ephemeral=False, thinking=False)
        self.current_view.page = 0
        await self.current_view.update_message(interaction)


# INVITE TYPE FILTER DROPDOWN

class InviteTypeFilterSelect(discord.ui.Select):
    def __init__(self, current_value: str = "all"):
        self.current_value = current_value

        options = [
            discord.SelectOption(
                label="All Invites",
                value="all",
                description="Show all types of invites",
                emoji="📊",
                default=current_value == "all"
            ),
            discord.SelectOption(
                label="Valid Invites",
                value="valid",
                description="Only valid invites (users who stayed)",
                emoji="✅",
                default=current_value == "valid"
            ),
            discord.SelectOption(
                label="Suspicious Invites",
                value="suspicious",
                description="Invites marked as suspicious (new accounts)",
                emoji="⚠️",
                default=current_value == "suspicious"
            ),
            discord.SelectOption(
                label="Left Invites",
                value="left",
                description="Users who joined and then left",
                emoji="👋",
                default=current_value == "left"
            )
        ]

        super().__init__(
            placeholder="Filter by invite type...",
            options=options,
            custom_id="invite_type_filter",
            row=2
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False, thinking=False)

        view = self.view
        view.current_invite_type = self.values[0]
        view.page = 0
        view._update_buttons()
        await view.update_message(interaction)


# PAGINATION BUTTONS

class InvitePrevButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary,
                         emoji=discord.PartialEmoji(name="arrowleft", id=1521149181207777331), custom_id="invite_prev")

    async def callback(self, interaction: discord.Interaction):

        if self.disabled:
            await interaction.response.defer(ephemeral=True, thinking=False)
            return

        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False, thinking=False)

        view = self.view
        if view.page > 0:
            view.page -= 1
            await view.update_message(interaction)


class InviteNextButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary,
                         emoji=discord.PartialEmoji(name="arrowright", id=1521149211373076501), custom_id="invite_next")

    async def callback(self, interaction: discord.Interaction):

        if self.disabled:
            await interaction.response.defer(ephemeral=True, thinking=False)
            return

        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False, thinking=False)

        view = self.view
        view.page += 1
        await view.update_message(interaction)


class InvitePageIndicator(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label="Page 1/1",
                         custom_id="invite_page", disabled=False)

    async def callback(self, interaction: discord.Interaction):
        view = self.view

        # Get total pages
        leaderboard_data = await view.cog._get_invite_leaderboard_data(
            view.guild, view.current_start_time, view.current_end_time, view.current_days_back_equiv, view.selected_role_id, view.current_invite_type
        )
        total_users = len(leaderboard_data)
        total_pages = max(
            1, (total_users + InviteConfig.USERS_PER_PAGE - 1) // InviteConfig.USERS_PER_PAGE)

        modal = PageJumpModal(view, total_pages)
        await interaction.response.send_modal(modal)


class InviteRoleInputButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label="Filter By Role",
                         custom_id="invite_role_input", row=3)

    async def callback(self, interaction: discord.Interaction):
        if interaction.response.is_done():
            return

        modal = InviteRoleInputModal(self.view.cog, self.view)
        await interaction.response.send_modal(modal)


# INVITE LEADERBOARD VIEW

class InviteLeaderboardView(discord.ui.View):
    def __init__(self, cog_instance, guild: discord.Guild, start_time: datetime = None, end_time: datetime = None,
                 days_back_equiv: int = InviteConfig.DEFAULT_DAYS_BACK, display_text: str = f"{InviteConfig.DEFAULT_DAYS_BACK} days",
                 page: int = 0, selected_role_id: str = None, invite_type_filter: str = "all", using_server_default: bool = True):
        super().__init__(timeout=600)
        self.cog = cog_instance
        self.guild = guild
        self.current_start_time = start_time
        self.current_end_time = end_time
        self.current_days_back_equiv = days_back_equiv
        self.current_display_text = display_text
        self.page = page
        self.selected_role_id = selected_role_id
        self.current_invite_type = invite_type_filter
        self.using_server_default = using_server_default
        self.show_time_buttons = False
        self._update_buttons()

    def _update_buttons(self):

        self.clear_items()

        self.add_item(InvitePrevButton())
        self.add_item(InvitePageIndicator())
        self.add_item(InviteNextButton())
        self.add_item(InviteRoleInputButton())
        self.add_item(InviteTypeFilterSelect(self.current_invite_type))

        refresh_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=discord.PartialEmoji(name="refresh", id=1518249841505861743),
            custom_id="invite_refresh",
            row=3
        )
        refresh_button.callback = self.refresh_callback

        time_settings_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=discord.PartialEmoji(name="clockk", id=1518249803069259867),
            custom_id="invite_time_settings",
            row=3
        )
        time_settings_button.callback = self.time_settings_callback

        self.add_item(refresh_button)
        self.add_item(time_settings_button)

        if self.show_time_buttons:
            row = 4
            all_time_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 999999 else discord.ButtonStyle.secondary,
                label="All Time",
                custom_id="invite_all_time",
                row=row
            )
            all_time_button.callback = self.all_time_callback
            self.add_item(all_time_button)

            for days in InviteConfig.TIME_PERIODS:
                days_button = discord.ui.Button(
                    style=discord.ButtonStyle.primary if self.current_days_back_equiv == days else discord.ButtonStyle.secondary,
                    label=f"{days} Days",
                    custom_id=f"invite_days_{days}",
                    row=row
                )
                days_button.callback = self.create_days_callback(days)
                self.add_item(days_button)

            custom_button = discord.ui.Button(
                style=discord.ButtonStyle.success if self.current_days_back_equiv not in InviteConfig.TIME_PERIODS and self.current_days_back_equiv != 999999 else discord.ButtonStyle.secondary,
                label=f"Custom ({self.current_days_back_equiv}d)" if self.current_days_back_equiv not in InviteConfig.TIME_PERIODS and self.current_days_back_equiv != 999999 else "Custom",
                custom_id="invite_custom_days",
                row=row
            )
            custom_button.callback = self.custom_days_callback
            self.add_item(custom_button)

    def create_days_callback(self, days: int):
        async def callback(interaction: discord.Interaction):
            now = datetime.utcnow()
            await self.handle_time_period_change(interaction, days, now - timedelta(days=days), now, f"{days} days")
        return callback

    async def all_time_callback(self, interaction: discord.Interaction):
        now = datetime.utcnow()
        await self.handle_time_period_change(interaction, 999999, None, now, "All Time")

    async def refresh_callback(self, interaction: discord.Interaction):
        await self.handle_refresh(interaction)

    async def time_settings_callback(self, interaction: discord.Interaction):
        await self.handle_time_settings(interaction)

    async def custom_days_callback(self, interaction: discord.Interaction):
        modal = InviteLeaderboardTimeModal(self.cog, self)
        await interaction.response.send_modal(modal)

    async def handle_refresh(self, interaction: discord.Interaction):

        if interaction.response.is_done():
            return

        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False, thinking=False)

        await self.update_message(interaction)

    async def handle_time_settings(self, interaction: discord.Interaction):

        if interaction.response.is_done():
            return

        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False, thinking=False)

        self.show_time_buttons = not self.show_time_buttons
        self._update_buttons()
        await interaction.edit_original_response(view=self)

    async def handle_time_period_change(self, interaction: discord.Interaction, days_back_equiv: int, start_time: datetime, end_time: datetime, display_text: str):

        if interaction.response.is_done():
            return

        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False, thinking=False)

        self.current_start_time = start_time
        self.current_end_time = end_time
        self.current_days_back_equiv = days_back_equiv
        self.current_display_text = display_text
        self.using_server_default = False
        self.show_time_buttons = False
        self.page = 0

        await self.update_message(interaction)

    async def generate_image(self):
        # Get role name from database instead of Discord API
        role_name = None
        if self.selected_role_id and self.selected_role_id != "none":
            db_stats = self.cog.db_stats
            if db_stats and db_stats.pool:
                try:
                    async with db_stats.pool.acquire() as conn:
                        row = await conn.fetchrow("""
                            SELECT role_name FROM current_role_members 
                            WHERE role_id = $1 AND guild_id = $2 
                            LIMIT 1
                        """, int(self.selected_role_id), self.guild.id)
                        if row:
                            role_name = row['role_name']
                except Exception as e:
                    print(f"Error getting role name from DB: {e}")

        leaderboard_data = await self.cog._get_invite_leaderboard_data(
            self.guild,
            self.current_start_time,
            self.current_end_time,
            self.current_days_back_equiv,
            self.selected_role_id,
            self.current_invite_type
        )

        return await generate_invite_leaderboard_image(
            bot=self.cog.bot,
            guild=self.guild,
            leaderboard_data=leaderboard_data,
            display_text=self.current_display_text,
            role_id=self.selected_role_id,
            role_name=role_name,
            invite_type_filter=self.current_invite_type,
            page=self.page
        )

    async def update_message(self, interaction: discord.Interaction):

        try:
            leaderboard_data = await self.cog._get_invite_leaderboard_data(
                self.guild,
                self.current_start_time,
                self.current_end_time,
                self.current_days_back_equiv,
                self.selected_role_id,
                self.current_invite_type
            )
            total_users = len(leaderboard_data)
            total_pages = max(
                1, (total_users + InviteConfig.USERS_PER_PAGE - 1) // InviteConfig.USERS_PER_PAGE)

            if self.page >= total_pages:
                self.page = max(0, total_pages - 1)
            img_bytes = await self.generate_image()

            for child in self.children:
                if isinstance(child, InvitePageIndicator):
                    child.label = f"Page {self.page + 1}/{total_pages}"
                elif isinstance(child, InvitePrevButton):
                    child.disabled = (self.page == 0 or total_pages <= 1)
                elif isinstance(child, InviteNextButton):
                    child.disabled = (
                        self.page >= total_pages - 1 or total_pages <= 1)
                elif isinstance(child, InviteTypeFilterSelect):
                    # Update the select's default values
                    for option in child.options:
                        option.default = (
                            option.value == self.current_invite_type)

            file = discord.File(img_bytes, filename="invite_leaderboard.png")

            if interaction.response.is_done():
                await interaction.edit_original_response(attachments=[file], view=self)
            else:
                await interaction.response.edit_message(attachments=[file], view=self)

        except Exception as e:
            print(f"Error updating invite leaderboard message: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ An error occurred while updating the leaderboard.", ephemeral=True)
                else:
                    await interaction.followup.send("❌ An error occurred while updating the leaderboard.", ephemeral=True)
            except:
                pass


# PERMISSION CHECK FOR PREFIX COMMANDS
async def check_prefix_command_permission(ctx: commands.Context, target_user: Optional[discord.Member] = None) -> bool:
    """
    Check if user has permission to use prefix command based on server settings.
    Returns True if allowed, False if not allowed.
    """
    try:
        guild = ctx.guild
        user = ctx.author

        # Users with administrator permission can always use commands
        if user.guild_permissions.administrator:
            return True

        # Get settings cog
        settings_cog = ctx.bot.get_cog('Settings')
        if not settings_cog:
            # If settings cog not available, use default permissions
            return True

        # Get guild settings
        settings = await settings_cog.get_guild_settings(guild.id)
        permission_level = settings.get('permission_level', 'Default')

        # Check permission levels
        if permission_level == 'All':
            return True

        elif permission_level == 'Default':
            # Default Discord permissions apply
            return True

        elif permission_level == 'User Restriction':
            # User can only use commands on themselves
            if target_user and target_user.id != user.id:
                embed = discord.Embed(
                    title="❌ Permission Denied",
                    description="Sorry! You can only use this command on yourself.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed, delete_after=10)
                return False
            return True

        elif permission_level == 'Admin':
            # Only users with administrator permission
            if not user.guild_permissions.administrator:
                embed = discord.Embed(
                    title="❌ Permission Denied",
                    description="Sorry! You need the `Administrator` permission to access this command.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed, delete_after=10)
                return False
            return True

        elif permission_level == 'Moderator':
            # Only users with manage_guild permission
            if not user.guild_permissions.manage_guild:
                embed = discord.Embed(
                    title="❌ Permission Denied",
                    description="Sorry! You need the `Manage Server` permission to access this command.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed, delete_after=10)
                return False
            return True

        return True

    except Exception as e:
        print(f"Error checking permission: {e}")
        return True


# MAIN CLASS

class Invites(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.initialized = False
        self.db_stats = None
        self.active_views = {}
        self.rate_limiter = get_rate_limiter()
        self.user_cache = {}  # Cache for fetched users
        # Start cache cleanup task
        self.clean_cache_task.start()

    def cog_unload(self):
        """Cancel the cache cleanup task when cog is unloaded"""
        self.clean_cache_task.cancel()
        self.active_views.clear()

    @tasks.loop(hours=1)
    async def clean_cache_task(self):
        """Periodically clean the user cache to prevent memory bloat"""
        self.user_cache.clear()
        gc.collect()

    @rate_limited(RateLimitType.API, timeout=1.0)
    async def _fetch_user_with_rate_limit(self, user_id: int):
        """Fetch user globally with rate limiting. Only used as fallback."""
        # Check cache first
        if user_id in self.user_cache:
            return self.user_cache[user_id]

        try:
            user = await self.bot.fetch_user(user_id)
            self.user_cache[user_id] = user
            return user
        except discord.NotFound:
            return None
        except discord.HTTPException as e:
            print(f"Failed to fetch user {user_id}: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error fetching user {user_id}: {e}")
            return None

    async def cog_load(self):

        self.db_stats = self.bot.get_cog('DatabaseStats')
        self.initialized = True

    # NEW METHOD: GET SERVER DEFAULT TIME RANGE
    # NEW METHOD: GET SERVER DEFAULT TIME RANGE
    async def get_server_default_time_range(self, guild: discord.Guild) -> tuple:
        """Get the default time range from server settings. Returns (start_time, end_time, display_text, days_back_equiv)"""
        try:
            settings_cog = self.bot.get_cog('Settings')
            if not settings_cog:
                end = datetime.now(timezone.utc)
                start = end - timedelta(days=InviteConfig.DEFAULT_DAYS_BACK)
                return (start, end, f"{InviteConfig.DEFAULT_DAYS_BACK} days", InviteConfig.DEFAULT_DAYS_BACK)

            settings = await settings_cog.get_guild_settings(guild.id)
            mode = settings.get('default_time_mode', 'days_back')
            now = datetime.now(timezone.utc)

            if mode == 'all_time':
                return (None, now, "All Time", 999999)

            elif mode == 'days_back':
                days = settings.get(
                    'default_days_back') or InviteConfig.DEFAULT_DAYS_BACK
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
            start = now - timedelta(days=InviteConfig.DEFAULT_DAYS_BACK)
            return (start, end, f"{InviteConfig.DEFAULT_DAYS_BACK} days", InviteConfig.DEFAULT_DAYS_BACK)

        except Exception as e:
            import traceback
            traceback.print_exc()
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=InviteConfig.DEFAULT_DAYS_BACK)
            return (start, end, f"{InviteConfig.DEFAULT_DAYS_BACK} days", InviteConfig.DEFAULT_DAYS_BACK)

    async def _get_invite_leaderboard_data(self, guild: discord.Guild, start_time: datetime = None, end_time: datetime = None,
                                           days_back_equiv: int = InviteConfig.DEFAULT_DAYS_BACK, role_id: str = None, invite_type_filter: str = "all"):

        if not self.db_stats or not self.db_stats.pool:
            print("⚠️ DatabaseStats not available for invite leaderboard")
            return []

        try:
            role_filter_ids = None
            if role_id and role_id != "none":
                role = guild.get_role(int(role_id))
                if role:
                    role_filter_ids = [role.id]

            leaderboard_data = await self.db_stats.q_invite_leaderboard(
                guild_id=guild.id,
                limit=100,
                role_filter_ids=role_filter_ids,
                start_time=start_time,
                end_time=end_time,
                invite_type_filter=invite_type_filter
            )

            return leaderboard_data

        except Exception as e:
            print(f"❌ Error getting invite leaderboard: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def get_user_invite_stats(self, guild_id: int, user_id: int, start_time: datetime = None, end_time: datetime = None):

        if not self.db_stats:
            return None

        try:
            return await self.db_stats.q_user_invite_stats(
                guild_id=guild_id,
                user_id=user_id,
                start_time=start_time,
                end_time=end_time
            )
        except Exception as e:
            print(f"Error getting user invite stats: {e}")
            return None

    async def get_inviter_for_user(self, guild_id: int, user_id: int):

        if not self.db_stats or not self.db_stats.pool:
            return None

        try:
            async with self.db_stats.pool.acquire() as conn:

                debug_rows = await conn.fetch('''
                    SELECT inviter_id, invite_code, invite_type, created_at
                    FROM invite_tracking
                    WHERE guild_id = $1 AND invitee_id = $2
                    ORDER BY created_at DESC
                    LIMIT 5
                ''', guild_id, user_id)

                row = await conn.fetchrow('''
                    SELECT 
                        inviter_id, 
                        invite_code, 
                        created_at, 
                        invite_type
                    FROM invite_tracking
                    WHERE guild_id = $1 
                    AND invitee_id = $2
                    AND invite_type = 'valid'
                    ORDER BY created_at DESC
                    LIMIT 1
                ''', guild_id, user_id)

                if row:
                    return {
                        'inviter_id': row['inviter_id'],
                        'invite_code': row['invite_code'],
                        'invite_time': row['created_at'],
                        'invite_type': row['invite_type']
                    }

                row = await conn.fetchrow('''
                    SELECT 
                        inviter_id, 
                        invite_code, 
                        created_at, 
                        invite_type
                    FROM invite_tracking
                    WHERE guild_id = $1 
                    AND invitee_id = $2
                    ORDER BY created_at DESC
                    LIMIT 1
                ''', guild_id, user_id)

                if row:
                    return {
                        'inviter_id': row['inviter_id'],
                        'invite_code': row['invite_code'],
                        'invite_time': row['created_at'],
                        'invite_type': row['invite_type']
                    }

                return None

        except Exception as e:
            print(f"Error getting inviter for user: {e}")
            return None

    # =========================================================
    # INTERNAL FUNCTION FOR INVITE STATS
    # =========================================================
    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def _handle_invite_stats_command(self, ctx_or_interaction, user=None, is_interaction=False):
        """Internal function to handle invite stats for both command types"""
        try:
            # Get context parameters
            if is_interaction:
                sender = ctx_or_interaction.user
                guild = ctx_or_interaction.guild
                send_method = ctx_or_interaction.followup.send
                defer_method = ctx_or_interaction.response.defer
            else:
                sender = ctx_or_interaction.author
                guild = ctx_or_interaction.guild
                send_method = ctx_or_interaction.send
                defer_method = None

            # Handle user parameter
            if user is None:
                user = sender

            if guild is None:
                if is_interaction:
                    await ctx_or_interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
                else:
                    await ctx_or_interaction.send("❌ This command can only be used in a server.", delete_after=5)
                return

            # Check permission - USE CORRECT FUNCTION BASED ON COMMAND TYPE
            if is_interaction:
                # For slash commands, use check_command_permission
                if not await check_command_permission(ctx_or_interaction, "invite_stats", target_user=user):
                    return
            else:
                # For prefix commands, use check_prefix_command_permission
                if not await check_prefix_command_permission(ctx_or_interaction, target_user=user):
                    return

            if is_interaction:
                await defer_method(thinking=True)

            if not self.db_stats or not self.db_stats.pool:
                if is_interaction:
                    await send_method("❌ Database not available. Please try again later.")
                else:
                    await send_method("❌ Database not available. Please try again later.", delete_after=10)
                return

            try:
                start_time, end_time, _, _ = await self.get_server_default_time_range(guild)
                stats = await self.get_user_invite_stats(guild.id, user.id, start_time, end_time)

                if not stats:
                    if is_interaction:
                        await send_method("❌ No invite statistics found for this user.")
                    else:
                        await send_method("❌ No invite statistics found for this user.", delete_after=10)
                    return

                embed = discord.Embed(
                    title=f"📊 Invite Statistics - {user.display_name}",
                    color=discord.Color.blue()
                )
                embed.set_thumbnail(url=user.display_avatar.url)

                embed.add_field(
                    name="Total Invites",
                    value=f"```{stats.get('total_invites', 0):,}```",
                    inline=True
                )
                embed.add_field(
                    name="✅ Valid Invites",
                    value=f"```{stats.get('valid_invites', 0):,}```",
                    inline=True
                )
                embed.add_field(
                    name="⚠️ Suspicious Invites",
                    value=f"```{stats.get('suspicious_invites', 0):,}```",
                    inline=True
                )

                if stats.get('left_invites', 0) > 0:
                    embed.add_field(
                        name="👋 Users Left",
                        value=f"```{stats.get('left_invites', 0):,}```",
                        inline=True
                    )

                if stats.get('percentage_valid', 0) > 0:
                    embed.add_field(
                        name="🎯 Valid Invite Rate",
                        value=f"```{stats.get('percentage_valid', 0):.1f}%```",
                        inline=True
                    )

                if is_interaction:
                    await send_method(embed=embed)
                else:
                    await send_method(embed=embed, delete_after=30)

            except Exception as e:
                print(f"❌ Error getting invite stats: {e}")
                if is_interaction:
                    await send_method("❌ An error occurred while fetching invite statistics.")
                else:
                    await send_method("❌ An error occurred while fetching invite statistics.", delete_after=10)

        except Exception as e:
            print(f"Error in _handle_invite_stats_command: {e}")

    # =========================================================
    # INTERNAL FUNCTION FOR INVITER
    # =========================================================
    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def _handle_inviter_command(self, ctx_or_interaction, user=None, is_interaction=False):
        """Internal function to handle inviter for both command types"""
        try:
            # Get context parameters
            if is_interaction:
                sender = ctx_or_interaction.user
                guild = ctx_or_interaction.guild
                send_method = ctx_or_interaction.followup.send
                defer_method = ctx_or_interaction.response.defer
            else:
                sender = ctx_or_interaction.author
                guild = ctx_or_interaction.guild
                send_method = ctx_or_interaction.send
                defer_method = None

            # Handle user parameter
            if user is None:
                user = sender

            if guild is None:
                if is_interaction:
                    await ctx_or_interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
                else:
                    await ctx_or_interaction.send("❌ This command can only be used in a server.", delete_after=5)
                return

            # Check permission - USE CORRECT FUNCTION BASED ON COMMAND TYPE
            if is_interaction:
                # For slash commands, use check_command_permission
                if not await check_command_permission(ctx_or_interaction, "inviter", target_user=user):
                    return
            else:
                # For prefix commands, use check_prefix_command_permission
                if not await check_prefix_command_permission(ctx_or_interaction, target_user=user):
                    return

            if is_interaction:
                await defer_method(thinking=True)

            if not self.db_stats or not self.db_stats.pool:
                if is_interaction:
                    await send_method("❌ Database not available. Please try again later.")
                else:
                    await send_method("❌ Database not available. Please try again later.", delete_after=10)
                return

            # Use the rate-limited fetch for user display info
            # Override the global get_user_display_info to use our rate-limited version
            async def get_user_display_info_limited(bot, guild, user_id, check_exists=True):
                user_info = {
                    'name': '[Deleted User]',
                    'is_deleted': True,
                    'member': None
                }

                try:
                    member = guild.get_member(user_id)
                    if member:
                        user_info.update({
                            'name': member.name,
                            'is_deleted': False,
                            'member': member
                        })
                        return user_info

                    # Use rate-limited fetch
                    user = await self._fetch_user_with_rate_limit(user_id)
                    if user:
                        user_info.update({
                            'name': user.name,
                            'is_deleted': False,
                            'member': None
                        })
                    else:
                        user_info.update({
                            'name': f'User {user_id}',
                            'is_deleted': False,
                            'member': None
                        })

                except Exception as e:
                    print(f"⚠️ Error getting user info for ID {user_id}: {e}")
                    user_info.update({
                        'name': f'User {user_id}',
                        'is_deleted': False,
                        'member': None
                    })

                return user_info

            inviter_info = await self.get_inviter_for_user(guild.id, user.id)

            user_info = await get_user_display_info_limited(self.bot, guild, user.id)
            invited_user_display = user_info['name']

            if not inviter_info:
                embed = discord.Embed(
                    title="❌ Inviter Not Found",
                    description=f"Could not find who invited {invited_user_display}.\n\nThis could be because:\n• The user joined before invite tracking was enabled\n• The invite was deleted before tracking",
                    color=discord.Color.orange()
                )
                if is_interaction:
                    await send_method(embed=embed)
                else:
                    await send_method(embed=embed, delete_after=30)
                return

            inviter_id = inviter_info.get('inviter_id')
            invite_type = inviter_info.get('invite_type', 'valid')

            if inviter_id == 0:
                embed = discord.Embed(
                    title="❌ Unknown Inviter",
                    description=f"**{invited_user_display}** was invited by an unknown user.\n\nThis usually happens when:\n• The inviter left the server before tracking\n• The invite was created before tracking started\n• It was a vanity URL invite",
                    color=discord.Color.orange()
                )
                if is_interaction:
                    await send_method(embed=embed)
                else:
                    await send_method(embed=embed, delete_after=30)
                return

            inviter_info_display = await get_user_display_info_limited(self.bot, guild, inviter_id)
            inviter_display = inviter_info_display['name']

            if inviter_info_display['member']:
                inviter = inviter_info_display['member']
                embed = discord.Embed(
                    title="👥 Inviter Found",
                    description=f"**{invited_user_display}** was invited by **{inviter.mention}**",
                    color=discord.Color.green()
                )
                embed.set_thumbnail(url=user.display_avatar.url)
                embed.add_field(
                    name="Invited User",
                    value=invited_user_display,
                    inline=True
                )
                embed.add_field(
                    name="Inviter",
                    value=inviter.mention,
                    inline=True
                )

                if inviter_info.get('invite_code') and inviter_info['invite_code'] not in ["unknown", "left"]:
                    embed.add_field(
                        name="Invite Code",
                        value=f"`{inviter_info['invite_code']}`",
                        inline=False
                    )

                if inviter_info.get('invite_time'):
                    # Convert to guild timezone
                    invite_time = await convert_utc_to_guild_time(inviter_info['invite_time'], guild.id)
                    if isinstance(invite_time, datetime):
                        invite_time_str = invite_time.strftime(
                            "%Y-%m-%d %H:%M:%S")
                    else:
                        invite_time_str = str(invite_time)
                    embed.add_field(
                        name="Invite Time",
                        value=f"`{invite_time_str}`",
                        inline=False
                    )
                if invite_type == 'suspicious':
                    embed.add_field(
                        name="⚠️ Warning",
                        value="This invite was marked as suspicious (new account detected)",
                        inline=False
                    )
                    embed.color = discord.Color.orange()
                elif invite_type == 'left':
                    embed.add_field(
                        name="📝 Note",
                        value="The invited user has left the server",
                        inline=False
                    )
                    embed.color = discord.Color.blue()
                elif invite_type == 'unknown':
                    embed.add_field(
                        name="📝 Note",
                        value="Invite source could not be determined",
                        inline=False
                    )
                    embed.color = discord.Color.greyple()

            else:
                embed = discord.Embed(
                    title="👥 Inviter Found",
                    description=f"**{invited_user_display}** was invited by **{inviter_display}**",
                    color=discord.Color.blue()
                )
                embed.set_thumbnail(url=user.display_avatar.url)
                embed.add_field(
                    name="Invited User",
                    value=invited_user_display,
                    inline=True
                )
                embed.add_field(
                    name="Inviter",
                    value=inviter_display,
                    inline=True
                )

                if invite_type == 'suspicious':
                    embed.add_field(
                        name="⚠️ Warning",
                        value="This invite was marked as suspicious",
                        inline=False
                    )
                    embed.color = discord.Color.orange()

            if is_interaction:
                await send_method(embed=embed)
            else:
                await send_method(embed=embed, delete_after=30)

        except Exception as e:
            print(f"Error in _handle_inviter_command: {e}")

    # =========================================================
    # INTERNAL FUNCTION FOR INVITE LEADERBOARD
    # =========================================================
    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def _handle_invite_leaderboard_command(self, ctx_or_interaction, is_interaction=False):
        """Internal function to handle invite leaderboard for both command types"""
        try:
            # Get context parameters
            if is_interaction:
                guild = ctx_or_interaction.guild
                send_method = ctx_or_interaction.followup.send
                defer_method = ctx_or_interaction.response.defer
            else:
                guild = ctx_or_interaction.guild
                send_method = ctx_or_interaction.send
                defer_method = None

            if guild is None:
                if is_interaction:
                    await ctx_or_interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
                else:
                    await ctx_or_interaction.send("❌ This command can only be used in a server.", delete_after=5)
                return

            # Check permission - USE CORRECT FUNCTION BASED ON COMMAND TYPE
            if is_interaction:
                # For slash commands, use check_command_permission
                if not await check_command_permission(ctx_or_interaction, "invite_leaderboard"):
                    return
            else:
                # For prefix commands, use check_prefix_command_permission
                if not await check_prefix_command_permission(ctx_or_interaction):
                    return

            if is_interaction:
                await defer_method()
            else:
                # Try to delete the command message for prefix
                try:
                    await ctx_or_interaction.message.delete()
                except:
                    pass

            # Get server default time range
            start_time, end_time, display_text, days_back_equiv = await self.get_server_default_time_range(guild)

            leaderboard_data = await self._get_invite_leaderboard_data(guild, start_time, end_time, days_back_equiv)

            img_bytes = await generate_invite_leaderboard_image(
                bot=self.bot,
                guild=guild,
                leaderboard_data=leaderboard_data,
                display_text=display_text,
                page=0
            )

            file = discord.File(img_bytes, filename="invite_leaderboard.png")

            view = InviteLeaderboardView(
                self, guild, start_time=start_time, end_time=end_time, days_back_equiv=days_back_equiv, display_text=display_text, using_server_default=True
            )

            retention_alert_text = await self.db_stats.maybe_get_retention_alert(guild.id) if self.db_stats else None

            msg = await send_method(content=retention_alert_text, file=file, view=view)

            # Store the view
            self.active_views[msg.id] = view

        except Exception as e:
            print(f"Error in _handle_invite_leaderboard_command: {e}")
    # =========================================================
    # SHORTCUT COMMANDS
    # =========================================================

    @commands.command(name="is")
    async def invite_stats_shortcut(self, ctx: commands.Context, member: discord.Member = None):
        """Shortcut command for invite stats - same as invite stats"""
        await self._handle_invite_stats_command(ctx, member, is_interaction=False)

    @commands.command(name="ir")
    async def inviter_shortcut(self, ctx: commands.Context, member: discord.Member = None):
        """Shortcut command for inviter - same as inviter"""
        await self._handle_inviter_command(ctx, member, is_interaction=False)

    @commands.command(name="il")
    async def invite_leaderboard_shortcut(self, ctx: commands.Context):
        """Shortcut command for invite leaderboard - same as invite leaderboard"""
        await self._handle_invite_leaderboard_command(ctx, is_interaction=False)

    # =========================================================
    # PREFIX COMMAND GROUP
    # =========================================================
    @commands.group(name="invite", invoke_without_command=True)
    async def invite_group_prefix(self, ctx: commands.Context):
        """Invite tracking commands"""
        await ctx.send("Available commands:\n- `invite stats [member]` - Show invite statistics for a user\n- `invite leaderboard` - Show invite leaderboard\n- `inviter [member]` - Find out who invited a user\n\nShortcuts:\n- `is [member]` - Invite stats shortcut\n- `ir [member]` - Inviter shortcut\n- `il` - Invite leaderboard shortcut")

    @invite_group_prefix.command(name="stats")
    async def invite_stats_prefix(self, ctx: commands.Context, member: discord.Member = None):
        """Show invite statistics for a user via prefix command"""
        await self._handle_invite_stats_command(ctx, member, is_interaction=False)

    @invite_group_prefix.command(name="leaderboard")
    async def invite_leaderboard_prefix(self, ctx: commands.Context):
        """Show invite leaderboard via prefix command"""
        await self._handle_invite_leaderboard_command(ctx, is_interaction=False)

    # =========================================================
    # PREFIX COMMAND - INVITER (STANDALONE)
    # =========================================================
    @commands.command(name="inviter")
    async def inviter_prefix(self, ctx: commands.Context, member: discord.Member = None):
        """Find out who invited a user via prefix command"""
        await self._handle_inviter_command(ctx, member, is_interaction=False)

    # =========================================================
    # SLASH COMMANDS
    # =========================================================
    invite_group = app_commands.Group(
        name="invite",
        description="Invite tracking commands"
    )

    @invite_group.command(name="stats", description="Show invite statistics for a user")
    @app_commands.describe(user="The user to check invite stats for")
    async def invite_stats(self, interaction: discord.Interaction, user: discord.Member = None):
        await self._handle_invite_stats_command(interaction, user, is_interaction=True)

    @app_commands.command(name="inviter", description="Find out who invited a user")
    @app_commands.describe(user="The user to check inviter for")
    async def inviter_command(self, interaction: discord.Interaction, user: discord.Member = None):
        await self._handle_inviter_command(interaction, user, is_interaction=True)

    @invite_group.command(name="leaderboard", description="Show invite leaderboard")
    async def invite_leaderboard(self, interaction: discord.Interaction):
        await self._handle_invite_leaderboard_command(interaction, is_interaction=True)


async def setup(bot):
    await bot.add_cog(Invites(bot))
