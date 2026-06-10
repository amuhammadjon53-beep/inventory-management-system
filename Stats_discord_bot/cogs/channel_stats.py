import discord
from discord.ext import commands, tasks
from discord import app_commands
from collections import Counter
from datetime import datetime, timedelta, timezone
import time
import asyncio
import os
import re
from PIL import Image, ImageDraw, ImageFont
import io
import aiohttp
from typing import Tuple, List, Dict, Any, Optional
import traceback
from pilmoji import Pilmoji
from pathlib import Path
import unicodedata
from .ratelimiter import RateLimiter, RateLimitType, rate_limited, get_rate_limiter

BASE_DIR = Path(__file__).resolve().parent.parent


# USER VERIFICATION FUNCTION WITH RATE LIMITING (ONLY FOR FALLBACK)
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


async def get_user_info(guild: discord.Guild, user_id: int) -> Tuple[Optional[discord.Member], bool]:
    """
    Get user information and check if account exists.
    Returns: (member_object_or_None, account_exists)

    If member is None but account_exists is True, user left the guild but account still exists.
    If member is None and account_exists is False, account has been deleted.
    """
    try:
        # First try to get from cache (user is in the guild) - NO RATE LIMITING
        member = guild.get_member(user_id)
        if member:
            return member, True

        # Try to fetch the user from Discord API with rate limiting (only for users who left)
        try:
            user = await _fetch_user_limited(guild.bot, user_id)
            if user:
                # Account exists but user is not in the guild
                return None, True
            else:
                # User not found in Discord API = account deleted
                return None, False
        except Exception:
            # If there's an API error, be safe and assume account exists
            return None, True
    except Exception:
        # Any other error, be safe and assume account exists
        return None, True


# TEXT NORMALIZATION FUNCTION
def normalize_text(text: str) -> str:
    """
    Normalize Unicode text to ASCII-compatible form.
    """
    if not text:
        return text

    normalized = unicodedata.normalize('NFKD', text)
    ascii_text = normalized.encode('ascii', 'ignore').decode('ascii')

    if not ascii_text.strip():
        return text

    return ascii_text


# PERMISSION CHECK FUNCTION
async def check_command_permission(interaction_or_context, target_user_id: int = None) -> bool:
    """Check if user has permission to use the command based on guild settings."""
    if isinstance(interaction_or_context, discord.Interaction):
        user = interaction_or_context.user
        guild = interaction_or_context.guild
        bot = interaction_or_context.client
    elif isinstance(interaction_or_context, commands.Context):
        user = interaction_or_context.author
        guild = interaction_or_context.guild
        bot = interaction_or_context.bot
    else:
        return True

    if user.guild_permissions.administrator:
        return True

    settings_cog = bot.get_cog('Settings')
    if not settings_cog or not getattr(settings_cog, 'initialized', False):
        return True

    try:
        settings = await settings_cog.get_guild_settings(guild.id)
        permission_level = settings.get('permission_level', 'Default')

        if permission_level == 'All':
            return True
        elif permission_level == 'Default':
            return True
        elif permission_level == 'User Restriction':
            return True
        elif permission_level == 'Admin':
            return False
        elif permission_level == 'Moderator':
            return user.guild_permissions.manage_guild
        else:
            return True
    except Exception:
        return True


# IMAGE GENERATION FUNCTIONS

async def generate_channel_stats_image(guild: discord.Guild, channel: discord.TextChannel, channel_data: dict, display_text: str, role_id: str = None, role_name: str = None):

    template_path = BASE_DIR / "assets" / \
        "images" / "text channel stats final png.png"
    try:
        image = Image.open(template_path)
    except FileNotFoundError:
        image = Image.new('RGB', (800, 600), color='#2F3136')

    draw = ImageDraw.Draw(image)

    # Fonts
    try:
        font_paths = [BASE_DIR / "assets" / "fonts" / "HorndonD.ttf"]
        font_loaded = False

        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    font_horndon_16 = ImageFont.truetype(str(font_path), 16)
                    font_horndon_20 = ImageFont.truetype(str(font_path), 20)
                    font_horndon_24 = ImageFont.truetype(str(font_path), 24)
                    font_horndon_36 = ImageFont.truetype(str(font_path), 36)

                    font_small = font_horndon_16
                    font_medium = font_horndon_20
                    font_large = font_horndon_24
                    font_huge = font_horndon_36

                    font_loaded = True
                    break
                except Exception as e:
                    print(f"Error loading font: {e}")
                    continue

        if not font_loaded:
            font_small = ImageFont.truetype("arial.ttf", 16)
            font_medium = ImageFont.truetype("arial.ttf", 20)
            font_large = ImageFont.truetype("arial.ttf", 24)
            font_huge = ImageFont.truetype("arial.ttf", 36)

    except Exception as e:
        print(f"Font error: {e}")
        font_small = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_large = ImageFont.load_default()
        font_huge = ImageFont.load_default()

    # Helper functions
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

        exceeds_width = (text_left < rect_left) or (text_right > rect_right)
        exceeds_height = (text_top < rect_top) or (text_bottom > rect_bottom)

        return exceeds_width or exceeds_height

    def fit_text_to_position(text, text_x, text_y, rect_center_x, rect_center_y, rect_width, rect_height, text_type="username"):
        if text_type == "channel_name":
            font_sizes = [40, 36, 32, 28, 24, 20, 16, 14, 12, 10, 8]
        else:
            font_sizes = [24, 22, 20, 18, 16, 14, 12, 10, 8]

        for idx, font_size in enumerate(font_sizes):
            try:
                font = ImageFont.truetype(font_paths[0], font_size) if os.path.exists(
                    font_paths[0]) else ImageFont.load_default()
            except:
                font = ImageFont.load_default()

            if text_type == "channel_name":
                vertical_offset = idx
            else:
                vertical_offset = idx // 2

            adjusted_y = text_y + vertical_offset

            if not check_text_against_rectangle(text, font, text_x, adjusted_y, rect_center_x, rect_center_y, rect_width, rect_height):
                return text, font, (text_x, adjusted_y), font_size

        smallest_font = font_sizes[-1]
        try:
            font = ImageFont.truetype(font_paths[0], smallest_font) if os.path.exists(
                font_paths[0]) else ImageFont.load_default()
        except:
            font = ImageFont.load_default()

        truncated_text = text
        while len(truncated_text) > 3:
            truncated_text = truncated_text[:-4] + "..."
            if text_type == "channel_name":
                vertical_offset = len(font_sizes) - 1
            else:
                vertical_offset = (len(font_sizes) - 1) // 2

            adjusted_y = text_y + vertical_offset

            if not check_text_against_rectangle(truncated_text, font, text_x, adjusted_y, rect_center_x, rect_center_y, rect_width, rect_height):
                return truncated_text, font, (text_x, adjusted_y), smallest_font

        if text_type == "channel_name":
            vertical_offset = len(font_sizes) - 1
        else:
            vertical_offset = (len(font_sizes) - 1) // 2

        final_text = text[:3] + "..." if len(text) > 3 else text
        return final_text, font, (text_x, text_y + vertical_offset), smallest_font

    def draw_text_with_stroke_and_emoji(pilmoji, text, position, font, fill="white", stroke_fill="black", stroke_width=1):
        x, y = position
        for dx in [-stroke_width, 0, stroke_width]:
            for dy in [-stroke_width, 0, stroke_width]:
                if dx != 0 or dy != 0:
                    pilmoji.text((x + dx, y + dy), text,
                                 fill=stroke_fill, font=font)
        pilmoji.text((x, y), text, fill=fill, font=font)

    # Rectangle coordinates
    channel_name_rect = {"center": (135, 30), "width": 245, "height": 45}
    username_rectangles = [
        {"center": (330, 165), "width": 122, "height": 45},
        {"center": (330, 220), "width": 122, "height": 45},
        {"center": (330, 270), "width": 122, "height": 45},
        {"center": (330, 325), "width": 122, "height": 45},
        {"center": (330, 375), "width": 122, "height": 45}
    ]

    # Channel name
    channel_name = f"#{channel.name}"
    channel_name_normalized = normalize_text(channel_name)

    fitted_channel_name, channel_name_font, channel_name_pos, _ = fit_text_to_position(
        channel_name_normalized, 30, 7,
        channel_name_rect["center"][0], channel_name_rect["center"][1],
        channel_name_rect["width"], channel_name_rect["height"],
        text_type="channel_name"
    )

    with Pilmoji(image) as pilmoji:
        draw_text_with_stroke_and_emoji(
            pilmoji, fitted_channel_name, channel_name_pos, channel_name_font)

    # Server name and icon
    server_name = guild.name
    server_name_normalized = normalize_text(server_name)

    try:
        if guild.icon:
            icon_url = guild.icon.url
            async with aiohttp.ClientSession() as session:
                async with session.get(icon_url) as response:
                    icon_data = await response.read()

            icon_image = Image.open(io.BytesIO(icon_data))
            icon_image = icon_image.resize((20, 20), Image.Resampling.LANCZOS)

            bbox = draw.textbbox(
                (0, 0), server_name_normalized, font=font_medium)
            text_width = bbox[2] - bbox[0]
            icon_x = 375 - (text_width // 2) - 29
            icon_y = 75 - 10
            image.paste(icon_image, (int(icon_x), int(icon_y)))

            text_x = 375 - (text_width // 2)
            with Pilmoji(image) as pilmoji:
                for dx in [-1, 0, 1]:
                    for dy in [-1, 0, 1]:
                        if dx != 0 or dy != 0:
                            pilmoji.text(
                                (text_x + dx, 75 - 13 + dy), server_name_normalized, fill="black", font=font_medium)
                pilmoji.text((text_x, 75 - 13), server_name_normalized,
                             fill="white", font=font_medium)
        else:
            bbox = draw.textbbox(
                (0, 0), server_name_normalized, font=font_medium)
            text_width = bbox[2] - bbox[0]
            text_x = 375 - (text_width // 2)
            with Pilmoji(image) as pilmoji:
                for dx in [-1, 0, 1]:
                    for dy in [-1, 0, 1]:
                        if dx != 0 or dy != 0:
                            pilmoji.text(
                                (text_x + dx, 75 + dy), server_name_normalized, fill="black", font=font_medium)
                pilmoji.text((text_x, 75), server_name_normalized,
                             fill="white", font=font_medium)
    except Exception as e:
        print(f"Could not add server icon: {e}")
        bbox = draw.textbbox((0, 0), server_name_normalized, font=font_medium)
        text_width = bbox[2] - bbox[0]
        text_x = 375 - (text_width // 2)
        with Pilmoji(image) as pilmoji:
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if dx != 0 or dy != 0:
                        pilmoji.text(
                            (text_x + dx, 75 + dy), server_name_normalized, fill="black", font=font_medium)
            pilmoji.text((text_x, 75), server_name_normalized,
                         fill="white", font=font_medium)

    # Stats numbers
    total_messages = channel_data.get('total', 0)
    total_hours = 24
    # Parse days from display_text for per-hour calculation
    if display_text != "All Time":
        days_match = re.search(r'(\d+)', display_text)
        if days_match:
            days = int(days_match.group(1))
            total_hours = days * 24
    messages_per_hour = total_messages / total_hours if total_hours > 0 else 0

    with Pilmoji(image) as pilmoji:
        messages_per_hour_text = f"{messages_per_hour:.1f}"
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx != 0 or dy != 0:
                    pilmoji.text(
                        (105 + dx, 155 + dy), messages_per_hour_text, fill="black", font=font_huge)
        pilmoji.text((105, 155), messages_per_hour_text,
                     fill="white", font=font_huge)

        total_messages_text = f"{total_messages:,}"
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx != 0 or dy != 0:
                    pilmoji.text(
                        (105 + dx, 315 + dy), total_messages_text, fill="black", font=font_huge)
        pilmoji.text((105, 315), total_messages_text,
                     fill="white", font=font_huge)

    # Role filter
    role_text = role_name if role_name else "No Filter"
    with Pilmoji(image) as pilmoji:
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx != 0 or dy != 0:
                    pilmoji.text((70 + dx, 424 + dy), role_text,
                                 fill="black", font=font_small)
        pilmoji.text((70, 424), role_text, fill="white", font=font_small)

    # Time period - use display_text
    time_period_text = display_text
    with Pilmoji(image) as pilmoji:
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx != 0 or dy != 0:
                    pilmoji.text((630 + dx, 422 + dy), time_period_text,
                                 fill="black", font=font_small)
        pilmoji.text((630, 422), time_period_text,
                     fill="white", font=font_small)

    # Date
    current_date = datetime.now().strftime("%B %d, %Y")
    with Pilmoji(image) as pilmoji:
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx != 0 or dy != 0:
                    pilmoji.text((550 + dx, 38 + dy), current_date,
                                 fill="black", font=font_small)
        pilmoji.text((550, 38), current_date, fill="white", font=font_small)

    # Top 5 users
    top_users = channel_data.get('users', Counter()).most_common(5)
    user_positions = [(275, 150), (275, 205), (275, 255),
                      (275, 315), (275, 365)]
    message_positions = [(405, 150), (405, 205),
                         (405, 255), (405, 315), (405, 365)]

    with Pilmoji(image) as pilmoji:
        for i, ((user_id, count), (user_x, user_y), (msg_x, msg_y)) in enumerate(zip(top_users, user_positions, message_positions)):
            try:
                member, account_exists = await get_user_info(guild, int(user_id))

                if not account_exists:
                    username = "[Deleted User]"
                elif member:
                    username = normalize_text(member.name)
                else:
                    username = f"User {user_id}"
            except (ValueError, TypeError):
                username = "[Invalid User]"

            if not username or username.strip() == "":
                username = "-"

            rect_info = username_rectangles[i]

            fitted_username, username_font, username_pos, _ = fit_text_to_position(
                username, user_x, user_y,
                rect_info["center"][0], rect_info["center"][1],
                rect_info["width"], rect_info["height"],
                text_type="username"
            )

            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if dx != 0 or dy != 0:
                        pilmoji.text((username_pos[0] + dx, username_pos[1] + dy),
                                     fitted_username, fill="black", font=username_font)
            pilmoji.text(username_pos, fitted_username,
                         fill="white", font=username_font)

            count_text = f"{count:,}"
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if dx != 0 or dy != 0:
                        pilmoji.text((msg_x + dx, msg_y + dy),
                                     count_text, fill="black", font=font_large)
            pilmoji.text((msg_x, msg_y), count_text,
                         fill="white", font=font_large)

    # Timeseries
    timeseries_data = channel_data.get('timeseries', {})
    time_positions = {1: (645, 150), 5: (645, 210), 10: (
        645, 260), 20: (645, 315), 30: (645, 365)}

    with Pilmoji(image) as pilmoji:
        for days, position in time_positions.items():
            count = timeseries_data.get(f'{days}d', 0)
            count_text = f"{count:,}"
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if dx != 0 or dy != 0:
                        pilmoji.text(
                            (position[0] + dx, position[1] + dy), count_text, fill="black", font=font_large)
            pilmoji.text(position, count_text,
                         fill="white", font=font_large)

    img_bytes = io.BytesIO()
    image.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    return img_bytes


def format_voice_time(seconds):
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        minutes = seconds // 60
        remaining_seconds = seconds % 60
        return f"{int(minutes)}m {int(remaining_seconds)}s"
    elif seconds < 86400:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{int(hours)}h {int(minutes)}m"
    else:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        return f"{int(days)}d {int(hours)}h"


def format_voice_per_hour(seconds):
    if seconds < 60:
        return f"{seconds:.2f}s"
    elif seconds < 3600:
        minutes = seconds // 60
        remaining_seconds = seconds % 60
        return f"{int(minutes)}m {int(remaining_seconds)}s"
    elif seconds < 86400:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{int(hours)}h {int(minutes)}m"
    else:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        return f"{int(days)}d {int(hours)}h"


async def generate_voice_stats_image(guild: discord.Guild, channel: discord.VoiceChannel, voice_data: dict, display_text: str, role_id: str = None, role_name: str = None):

    template_path = BASE_DIR / "assets" / "images" / \
        "voice channel stats final png.png"
    try:
        image = Image.open(template_path)
    except FileNotFoundError:
        image = Image.new('RGB', (800, 600), color='#2F3136')

    draw = ImageDraw.Draw(image)

    # Fonts
    try:
        font_paths = [BASE_DIR / "assets" / "fonts" / "HorndonD.ttf"]
        font_loaded = False

        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    font_horndon_16 = ImageFont.truetype(str(font_path), 16)
                    font_horndon_20 = ImageFont.truetype(str(font_path), 20)
                    font_horndon_24 = ImageFont.truetype(str(font_path), 24)
                    font_horndon_36 = ImageFont.truetype(str(font_path), 36)

                    font_small = font_horndon_16
                    font_medium = font_horndon_20
                    font_large = font_horndon_24
                    font_huge = font_horndon_36

                    font_loaded = True
                    break
                except Exception as e:
                    print(f"Error loading font: {e}")
                    continue

        if not font_loaded:
            font_small = ImageFont.truetype("arial.ttf", 16)
            font_medium = ImageFont.truetype("arial.ttf", 20)
            font_large = ImageFont.truetype("arial.ttf", 24)
            font_huge = ImageFont.truetype("arial.ttf", 36)

    except Exception as e:
        print(f"Font error: {e}")
        font_small = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_large = ImageFont.load_default()
        font_huge = ImageFont.load_default()

    # Helper functions
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

        exceeds_width = (text_left < rect_left) or (text_right > rect_right)
        exceeds_height = (text_top < rect_top) or (text_bottom > rect_bottom)

        return exceeds_width or exceeds_height

    def fit_text_to_position(text, text_x, text_y, rect_center_x, rect_center_y, rect_width, rect_height, text_type="username"):
        if text_type == "channel_name":
            font_sizes = [40, 36, 32, 28, 24, 20, 16, 14, 12, 10, 8]
        else:
            font_sizes = [24, 22, 20, 18, 16, 14, 12, 10, 8]

        for idx, font_size in enumerate(font_sizes):
            try:
                font = ImageFont.truetype(font_paths[0], font_size) if os.path.exists(
                    font_paths[0]) else ImageFont.load_default()
            except:
                font = ImageFont.load_default()

            if text_type == "channel_name":
                vertical_offset = idx
            else:
                vertical_offset = idx // 2

            adjusted_y = text_y + vertical_offset

            if not check_text_against_rectangle(text, font, text_x, adjusted_y, rect_center_x, rect_center_y, rect_width, rect_height):
                return text, font, (text_x, adjusted_y), font_size

        smallest_font = font_sizes[-1]
        try:
            font = ImageFont.truetype(font_paths[0], smallest_font) if os.path.exists(
                font_paths[0]) else ImageFont.load_default()
        except:
            font = ImageFont.load_default()

        truncated_text = text
        while len(truncated_text) > 3:
            truncated_text = truncated_text[:-4] + "..."
            if text_type == "channel_name":
                vertical_offset = len(font_sizes) - 1
            else:
                vertical_offset = (len(font_sizes) - 1) // 2

            adjusted_y = text_y + vertical_offset

            if not check_text_against_rectangle(truncated_text, font, text_x, adjusted_y, rect_center_x, rect_center_y, rect_width, rect_height):
                return truncated_text, font, (text_x, adjusted_y), smallest_font

        if text_type == "channel_name":
            vertical_offset = len(font_sizes) - 1
        else:
            vertical_offset = (len(font_sizes) - 1) // 2

        final_text = text[:3] + "..." if len(text) > 3 else text
        return final_text, font, (text_x, text_y + vertical_offset), smallest_font

    def draw_text_with_stroke_and_emoji(pilmoji, text, position, font, fill="white", stroke_fill="black", stroke_width=1):
        x, y = position
        for dx in [-stroke_width, 0, stroke_width]:
            for dy in [-stroke_width, 0, stroke_width]:
                if dx != 0 or dy != 0:
                    pilmoji.text((x + dx, y + dy), text,
                                 fill=stroke_fill, font=font)
        pilmoji.text((x, y), text, fill=fill, font=font)

    # Rectangle coordinates
    channel_name_rect = {"center": (135, 30), "width": 245, "height": 45}
    username_rectangles = [
        {"center": (330, 165), "width": 122, "height": 45},
        {"center": (330, 220), "width": 122, "height": 45},
        {"center": (330, 270), "width": 122, "height": 45},
        {"center": (330, 325), "width": 122, "height": 45},
        {"center": (330, 375), "width": 122, "height": 45}
    ]

    # Channel name
    channel_name = f"#{channel.name}"
    channel_name_normalized = normalize_text(channel_name)

    fitted_channel_name, channel_name_font, channel_name_pos, _ = fit_text_to_position(
        channel_name_normalized, 30, 7,
        channel_name_rect["center"][0], channel_name_rect["center"][1],
        channel_name_rect["width"], channel_name_rect["height"],
        text_type="channel_name"
    )

    with Pilmoji(image) as pilmoji:
        draw_text_with_stroke_and_emoji(
            pilmoji, fitted_channel_name, channel_name_pos, channel_name_font)

    # Server name and icon
    server_name = guild.name
    server_name_normalized = normalize_text(server_name)

    try:
        if guild.icon:
            icon_url = guild.icon.url
            async with aiohttp.ClientSession() as session:
                async with session.get(icon_url) as response:
                    icon_data = await response.read()

            icon_image = Image.open(io.BytesIO(icon_data))
            icon_image = icon_image.resize((20, 20), Image.Resampling.LANCZOS)

            bbox = draw.textbbox(
                (0, 0), server_name_normalized, font=font_medium)
            text_width = bbox[2] - bbox[0]
            icon_x = 375 - (text_width // 2) - 29
            icon_y = 75 - 10
            image.paste(icon_image, (int(icon_x), int(icon_y)))

            text_x = 375 - (text_width // 2)
            with Pilmoji(image) as pilmoji:
                for dx in [-1, 0, 1]:
                    for dy in [-1, 0, 1]:
                        if dx != 0 or dy != 0:
                            pilmoji.text(
                                (text_x + dx, 75 - 13 + dy), server_name_normalized, fill="black", font=font_medium)
                pilmoji.text((text_x, 75 - 13), server_name_normalized,
                             fill="white", font=font_medium)
        else:
            bbox = draw.textbbox(
                (0, 0), server_name_normalized, font=font_medium)
            text_width = bbox[2] - bbox[0]
            text_x = 375 - (text_width // 2)
            with Pilmoji(image) as pilmoji:
                for dx in [-1, 0, 1]:
                    for dy in [-1, 0, 1]:
                        if dx != 0 or dy != 0:
                            pilmoji.text(
                                (text_x + dx, 75 + dy), server_name_normalized, fill="black", font=font_medium)
                pilmoji.text((text_x, 75), server_name_normalized,
                             fill="white", font=font_medium)
    except Exception as e:
        print(f"Could not add server icon: {e}")
        bbox = draw.textbbox((0, 0), server_name_normalized, font=font_medium)
        text_width = bbox[2] - bbox[0]
        text_x = 375 - (text_width // 2)
        with Pilmoji(image) as pilmoji:
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if dx != 0 or dy != 0:
                        pilmoji.text(
                            (text_x + dx, 75 + dy), server_name_normalized, fill="black", font=font_medium)
            pilmoji.text((text_x, 75), server_name_normalized,
                         fill="white", font=font_medium)

    # Stats numbers
    total_seconds = voice_data.get('total_seconds', 0)
    total_hours = 24
    # Parse days from display_text for per-hour calculation
    if display_text != "All Time":
        days_match = re.search(r'(\d+)', display_text)
        if days_match:
            days = int(days_match.group(1))
            total_hours = days * 24
    voice_per_hour = total_seconds / total_hours if total_hours > 0 else 0

    voice_per_hour_text = format_voice_per_hour(voice_per_hour)
    with Pilmoji(image) as pilmoji:
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx != 0 or dy != 0:
                    pilmoji.text(
                        (105 + dx, 155 + dy), voice_per_hour_text, fill="black", font=font_huge)
        pilmoji.text((105, 155), voice_per_hour_text,
                     fill="white", font=font_huge)

    total_voice_text = format_voice_time(total_seconds)
    with Pilmoji(image) as pilmoji:
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx != 0 or dy != 0:
                    pilmoji.text((105 + dx, 315 + dy),
                                 total_voice_text, fill="black", font=font_huge)
        pilmoji.text((105, 315), total_voice_text,
                     fill="white", font=font_huge)

    # Role filter
    role_text = role_name if role_name else "No Filter"
    with Pilmoji(image) as pilmoji:
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx != 0 or dy != 0:
                    pilmoji.text((70 + dx, 424 + dy), role_text,
                                 fill="black", font=font_small)
        pilmoji.text((70, 424), role_text, fill="white", font=font_small)

    # Time period - use display_text
    time_period_text = display_text
    with Pilmoji(image) as pilmoji:
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx != 0 or dy != 0:
                    pilmoji.text((630 + dx, 422 + dy), time_period_text,
                                 fill="black", font=font_small)
        pilmoji.text((630, 422), time_period_text,
                     fill="white", font=font_small)

    # Date
    current_date = datetime.now().strftime("%B %d, %Y")
    with Pilmoji(image) as pilmoji:
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx != 0 or dy != 0:
                    pilmoji.text((550 + dx, 38 + dy), current_date,
                                 fill="black", font=font_small)
        pilmoji.text((550, 38), current_date, fill="white", font=font_small)

    # Top 5 users
    top_users = voice_data.get('users', Counter()).most_common(5)
    user_positions = [(275, 150), (275, 205), (275, 255),
                      (275, 315), (275, 365)]
    time_positions = [(405, 150), (405, 205), (405, 255),
                      (405, 315), (405, 365)]

    with Pilmoji(image) as pilmoji:
        for i, ((user_id, user_seconds), (user_x, user_y), (time_x, time_y)) in enumerate(zip(top_users, user_positions, time_positions)):
            try:
                member, account_exists = await get_user_info(guild, int(user_id))

                if not account_exists:
                    username = "[Deleted User]"
                elif member:
                    username = normalize_text(member.name)
                else:
                    username = f"User {user_id}"
            except (ValueError, TypeError):
                username = "[Invalid User]"

            if not username or username.strip() == "":
                username = "-"

            rect_info = username_rectangles[i]

            fitted_username, username_font, username_pos, _ = fit_text_to_position(
                username, user_x, user_y,
                rect_info["center"][0], rect_info["center"][1],
                rect_info["width"], rect_info["height"],
                text_type="username"
            )

            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if dx != 0 or dy != 0:
                        pilmoji.text((username_pos[0] + dx, username_pos[1] + dy),
                                     fitted_username, fill="black", font=username_font)
            pilmoji.text(username_pos, fitted_username,
                         fill="white", font=username_font)

            voice_time_text = format_voice_time(user_seconds)
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if dx != 0 or dy != 0:
                        pilmoji.text((time_x + dx, time_y + dy),
                                     voice_time_text, fill="black", font=font_large)
            pilmoji.text((time_x, time_y), voice_time_text,
                         fill="white", font=font_large)

    # Timeseries
    timeseries_data = voice_data.get('timeseries', {})
    time_positions_dict = {1: (645, 150), 5: (645, 210), 10: (
        645, 260), 20: (645, 315), 30: (645, 365)}

    with Pilmoji(image) as pilmoji:
        for days, position in time_positions_dict.items():
            seconds = timeseries_data.get(str(days), 0)
            voice_time_text = format_voice_time(seconds)
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if dx != 0 or dy != 0:
                        pilmoji.text(
                            (position[0] + dx, position[1] + dy), voice_time_text, fill="black", font=font_large)
            pilmoji.text(position, voice_time_text,
                         fill="white", font=font_large)

    img_bytes = io.BytesIO()
    image.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    return img_bytes


# STATS TYPE SELECT MENU

class StatsTypeSelectMenu(discord.ui.Select):
    def __init__(self, current_type: str = "messages"):
        options = [
            discord.SelectOption(label="Messages", value="messages",
                                 description="View message statistics", emoji="💬", default=(current_type == "messages")),
            discord.SelectOption(label="Voice Activity", value="voice",
                                 description="View voice activity statistics", emoji="🔊", default=(current_type == "voice"))
        ]
        super().__init__(placeholder="Select stats type...", options=options,
                         custom_id="stats_type_select", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        if not self.values:
            await interaction.response.send_message("❌ No value selected.", ephemeral=True)
            return

        view = self.view
        view.stats_type = self.values[0]
        view.selected_role_id = None
        view.show_time_buttons = False

        await interaction.response.defer()

        if view.stats_type == "messages":
            channel_data = await view.cog._get_channel_stats_from_db(view.guild, view.channel, view.current_start_time, view.current_end_time, view.current_days_back_equiv, view.selected_role_id)
            if channel_data is None:
                channel_data = {'total': 0, 'users': Counter(
                ), 'timeseries': {}, 'timestamp': time.time()}
            img_bytes = await generate_channel_stats_image(view.guild, view.channel, channel_data, view.current_display_text, view.selected_role_id)
            filename = "channel_stats.png"
        else:
            voice_data = await view.cog._get_voice_stats_from_db(view.guild, view.channel, view.current_start_time, view.current_end_time, view.current_days_back_equiv, view.selected_role_id)
            if voice_data is None:
                voice_data = {'total_seconds': 0, 'users': Counter(
                ), 'timeseries': {}, 'timestamp': time.time()}
            img_bytes = await generate_voice_stats_image(view.guild, view.channel, voice_data, view.current_display_text, view.selected_role_id)
            filename = "voice_stats.png"

        view._update_buttons()
        file = discord.File(img_bytes, filename=filename)
        await interaction.edit_original_response(attachments=[file], view=view)


# ROLE ID MODAL

class RoleIdModal(discord.ui.Modal, title='Input Role ID'):
    def __init__(self, cog_instance, original_message_id, guild, channel, stats_type, view):
        super().__init__(timeout=300)
        self.cog = cog_instance
        self.original_message_id = original_message_id
        self.guild = guild
        self.channel = channel
        self.stats_type = stats_type
        self.view = view

    role_id = discord.ui.TextInput(
        label='Enter Role ID', placeholder='e.g., 123456789012345678', min_length=1, max_length=20, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            role_id_input = self.role_id.value.strip()

            if role_id_input.lower() == "none" or role_id_input.lower() == "clear":
                role_id = None
            else:
                try:
                    role_id = str(int(role_id_input))
                    role = self.guild.get_role(int(role_id))
                    if not role:
                        embed = discord.Embed(
                            title="❌ Error", description="Sorry! The role id you inputted is not valid, please try again.", color=discord.Color.red())
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                        return
                except ValueError:
                    embed = discord.Embed(
                        title="❌ Error", description="Sorry! The role id you inputted is not valid, please try again.", color=discord.Color.red())
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return

            await interaction.response.defer()

            if self.view:
                self.view.selected_role_id = role_id
                self.view.show_time_buttons = False

                # Get role name from database
                role_name = None
                if self.view.selected_role_id:
                    db_stats = self.cog.bot.get_cog('DatabaseStats')
                    if db_stats and db_stats.pool:
                        try:
                            async with db_stats.pool.acquire() as conn:
                                row = await conn.fetchrow("SELECT role_name FROM current_role_members WHERE role_id = $1 AND guild_id = $2 LIMIT 1", int(self.view.selected_role_id), self.guild.id)
                                if row:
                                    role_name = row['role_name']
                        except:
                            pass

                if self.stats_type == "messages":
                    channel_data = await self.cog._get_channel_stats_from_db(self.guild, self.channel, self.view.current_start_time, self.view.current_end_time, self.view.current_days_back_equiv, self.view.selected_role_id)
                    if channel_data is None:
                        channel_data = {'total': 0, 'users': Counter(
                        ), 'timeseries': {}, 'timestamp': time.time()}
                    img_bytes = await generate_channel_stats_image(self.guild, self.channel, channel_data, self.view.current_display_text, self.view.selected_role_id, role_name)
                    filename = "channel_stats.png"
                else:
                    voice_data = await self.cog._get_voice_stats_from_db(self.guild, self.channel, self.view.current_start_time, self.view.current_end_time, self.view.current_days_back_equiv, self.view.selected_role_id)
                    if voice_data is None:
                        voice_data = {'total_seconds': 0, 'users': Counter(
                        ), 'timeseries': {}, 'timestamp': time.time()}
                    img_bytes = await generate_voice_stats_image(self.guild, self.channel, voice_data, self.view.current_display_text, self.view.selected_role_id, role_name)
                    filename = "voice_stats.png"

                self.view._update_buttons()
                file = discord.File(img_bytes, filename=filename)

                try:
                    original_message = await interaction.channel.fetch_message(self.original_message_id)
                    if original_message:
                        await original_message.edit(attachments=[file], view=self.view)
                    else:
                        await interaction.followup.send(file=file, view=self.view)
                except discord.NotFound:
                    await interaction.followup.send(file=file, view=self.view)

            else:
                await interaction.followup.send("❌ Could not find session view.", ephemeral=True)

        except Exception as e:
            print(f"Error in role ID modal submit: {e}")
            traceback.print_exc()
            await interaction.followup.send("❌ An error occurred while updating stats.", ephemeral=True)


# TIME MODAL

class ChannelTimeModal(discord.ui.Modal, title='Custom Time Period'):
    def __init__(self, cog_instance, original_message_id, guild, channel, view):
        super().__init__(timeout=300)
        self.cog = cog_instance
        self.original_message_id = original_message_id
        self.guild = guild
        self.channel = channel
        self.view = view

    days = discord.ui.TextInput(label='Enter number of days',
                                placeholder='e.g., 7, 14, 30, 90...', min_length=1, max_length=4, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            days = int(self.days.value)
            if days <= 0 or days > 2000:
                await interaction.response.send_message("❌ Please enter a number between 1 and 2000 days.", ephemeral=True)
                return

            await interaction.response.defer()

            if self.view:
                now = datetime.utcnow()
                self.view.current_start_time = now - timedelta(days=days)
                self.view.current_end_time = now
                self.view.current_days_back_equiv = days
                self.view.current_display_text = f"{days} days"
                self.view.using_server_default = False
                self.view.show_time_buttons = False
                await self.view.update_chart(interaction)
            else:
                await interaction.followup.send("❌ Could not find session view.", ephemeral=True)

        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number.", ephemeral=True)
        except Exception as e:
            print(f"Error in channel modal submit: {e}")
            traceback.print_exc()
            await interaction.followup.send("❌ An error occurred while updating stats.", ephemeral=True)


# MAIN VIEW

class ChannelStatsView(discord.ui.View):
    def __init__(self, cog_instance, guild: discord.Guild, channel, start_time: datetime = None, end_time: datetime = None,
                 days_back_equiv: int = 14, display_text: str = "14 days", stats_type: str = "messages",
                 selected_role_id: str = None, using_server_default: bool = True):
        super().__init__(timeout=600)
        self.cog = cog_instance
        self.guild = guild
        self.channel = channel
        self.current_start_time = start_time
        self.current_end_time = end_time if end_time else datetime.utcnow()
        self.current_days_back_equiv = days_back_equiv
        self.current_display_text = display_text
        self.stats_type = stats_type
        self.selected_role_id = selected_role_id
        self.show_time_buttons = False
        self.using_server_default = using_server_default
        self._update_buttons()

    async def update_chart(self, interaction: discord.Interaction):
        """Update the chart for the current view"""
        try:
            role_name = None
            if self.selected_role_id and self.selected_role_id != "none":
                db_stats = self.cog.bot.get_cog('DatabaseStats')
                if db_stats and db_stats.pool:
                    try:
                        async with db_stats.pool.acquire() as conn:
                            row = await conn.fetchrow("SELECT role_name FROM current_role_members WHERE role_id = $1 AND guild_id = $2 LIMIT 1", int(self.selected_role_id), self.guild.id)
                            if row:
                                role_name = row['role_name']
                    except:
                        pass

            if self.stats_type == "messages":
                channel_data = await self.cog._get_channel_stats_from_db(self.guild, self.channel, self.current_start_time, self.current_end_time, self.current_days_back_equiv, self.selected_role_id)
                if channel_data is None:
                    channel_data = {'total': 0, 'users': Counter(
                    ), 'timeseries': {}, 'timestamp': time.time()}
                img_bytes = await generate_channel_stats_image(self.guild, self.channel, channel_data, self.current_display_text, self.selected_role_id, role_name)
                filename = "channel_stats.png"
            else:
                voice_data = await self.cog._get_voice_stats_from_db(self.guild, self.channel, self.current_start_time, self.current_end_time, self.current_days_back_equiv, self.selected_role_id)
                if voice_data is None:
                    voice_data = {'total_seconds': 0, 'users': Counter(
                    ), 'timeseries': {}, 'timestamp': time.time()}
                img_bytes = await generate_voice_stats_image(self.guild, self.channel, voice_data, self.current_display_text, self.selected_role_id, role_name)
                filename = "voice_stats.png"

            self._update_buttons()
            file = discord.File(img_bytes, filename=filename)

            if interaction:
                await interaction.edit_original_response(attachments=[file], view=self)

        except Exception as e:
            print(f"Error updating chart: {e}")
            traceback.print_exc()
            if interaction:
                await interaction.followup.send("❌ An error occurred while updating the stats.", ephemeral=True)

    def _update_buttons(self):
        self.clear_items()

        stats_type_select = StatsTypeSelectMenu(self.stats_type)
        self.add_item(stats_type_select)

        role_button = discord.ui.Button(style=discord.ButtonStyle.primary,
                                        label="Input Role ID" if not self.selected_role_id else f"Role: {self.selected_role_id[:10]}...", custom_id="role_id_button", row=1)
        role_button.callback = self.role_id_callback
        self.add_item(role_button)

        refresh_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="🔄 Refresh", custom_id="channel_refresh", row=1)
        refresh_button.callback = self.refresh_callback
        self.add_item(refresh_button)

        time_settings_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary, label="⏰ Time Settings", custom_id="channel_time_settings", row=1)
        time_settings_button.callback = self.time_settings_callback
        self.add_item(time_settings_button)

        if self.show_time_buttons:
            all_time_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 999999 else discord.ButtonStyle.secondary,
                label="All Time", custom_id="channel_all_time", row=2)
            all_time_button.callback = self.all_time_callback
            self.add_item(all_time_button)

            days_7_button = discord.ui.Button(style=discord.ButtonStyle.primary if self.current_days_back_equiv ==
                                              7 else discord.ButtonStyle.secondary, label="7 Days", custom_id="channel_days_7", row=2)
            days_7_button.callback = self.days_7_callback
            self.add_item(days_7_button)

            days_14_button = discord.ui.Button(style=discord.ButtonStyle.primary if self.current_days_back_equiv ==
                                               14 else discord.ButtonStyle.secondary, label="14 Days", custom_id="channel_days_14", row=2)
            days_14_button.callback = self.days_14_callback
            self.add_item(days_14_button)

            days_30_button = discord.ui.Button(style=discord.ButtonStyle.primary if self.current_days_back_equiv ==
                                               30 else discord.ButtonStyle.secondary, label="30 Days", custom_id="channel_days_30", row=2)
            days_30_button.callback = self.days_30_callback
            self.add_item(days_30_button)

            custom_button = discord.ui.Button(style=discord.ButtonStyle.success, label=f"Custom ({self.current_days_back_equiv}d)" if self.current_days_back_equiv not in [
                                              7, 14, 30, 999999] else "Custom", custom_id="channel_custom_days", row=2)
            custom_button.callback = self.custom_days_callback
            self.add_item(custom_button)

    async def role_id_callback(self, interaction: discord.Interaction):
        modal = RoleIdModal(self.cog, interaction.message.id,
                            self.guild, self.channel, self.stats_type, self)
        await interaction.response.send_modal(modal)

    async def refresh_callback(self, interaction: discord.Interaction):
        await self.handle_button_click(interaction, refresh=True)

    async def time_settings_callback(self, interaction: discord.Interaction):
        await self.handle_time_settings(interaction)

    async def all_time_callback(self, interaction: discord.Interaction):
        now = datetime.utcnow()
        await self.handle_button_click(interaction, days_back_equiv=999999, start_time=None, end_time=now, display_text="All Time")

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
        modal = ChannelTimeModal(
            self.cog, interaction.message.id, self.guild, self.channel, self)
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
                self.current_display_text = display_text
                self.using_server_default = False
                self.show_time_buttons = False

            await self.update_chart(interaction)

        except Exception as e:
            print(f"Error handling button click: {e}")
            traceback.print_exc()
            await interaction.followup.send("❌ An error occurred while updating the stats.", ephemeral=True)

    async def handle_time_settings(self, interaction: discord.Interaction):
        try:
            self.show_time_buttons = not self.show_time_buttons
            self._update_buttons()
            await interaction.response.edit_message(view=self)
        except Exception as e:
            print(f"Error handling time settings: {e}")
            await interaction.response.send_message("❌ An error occurred while updating time settings.", ephemeral=True)


# INITIALIZATION
class ChannelCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_sessions = {}
        self.rate_limiter = get_rate_limiter()

    # GET SERVER DEFAULT TIME RANGE
    # GET SERVER DEFAULT TIME RANGE
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

    async def _get_channel_stats_from_db(self, guild: discord.Guild, channel: discord.TextChannel, start_time: datetime = None, end_time: datetime = None, days_back_equiv: int = 14, role_id: str = None) -> Optional[Dict[str, Any]]:
        db_cog = self.bot.get_cog('DatabaseStats')
        if not db_cog:
            print("❌ DatabaseStats cog not found")
            return None

        try:
            role_ids = None
            if role_id and role_id != "none":
                role_ids = [int(role_id)]

            all_messages = await db_cog.q_channel_total_messages(
                guild_id=int(guild.id), channel_id=channel.id, role_filter_ids=role_ids,
                start_time=start_time, end_time=end_time
            )

            top_users_data = await db_cog.q_channel_top5_users_messages(
                guild_id=int(guild.id), channel_id=channel.id, role_filter_ids=role_ids,
                start_time=start_time, end_time=end_time
            )

            user_counts = Counter()
            for user_data in top_users_data:
                if isinstance(user_data, dict) and 'user_id' in user_data:
                    user_counts[str(user_data['user_id'])] = user_data.get(
                        'message_count', 0)

            timeseries_data = await db_cog.q_channel_timeseries_messages_1d_5d_10d_20d_30d(
                guild_id=int(guild.id), channel_id=channel.id, role_filter_ids=role_ids,
                start_time=start_time, end_time=end_time
            )

            return {
                'total': all_messages.get('total_messages', 0),
                'users': user_counts,
                'timeseries': timeseries_data,
                'timestamp': time.time()
            }
        except Exception as e:
            print(f"❌ Error getting channel stats: {e}")
            traceback.print_exc()
            return None

    async def _get_voice_stats_from_db(self, guild: discord.Guild, channel: discord.VoiceChannel, start_time: datetime = None, end_time: datetime = None, days_back_equiv: int = 14, role_id: str = None) -> Optional[Dict[str, Any]]:
        db_cog = self.bot.get_cog('DatabaseStats')
        if not db_cog:
            print("❌ DatabaseStats cog not found")
            return None

        try:
            role_ids = None
            if role_id and role_id != "none":
                role_ids = [int(role_id)]

            channel_voice_stats = await db_cog.q_channel_total_voice(
                guild_id=guild.id, channel_id=channel.id, role_filter_ids=role_ids,
                start_time=start_time, end_time=end_time
            )

            top_users_data = await db_cog.q_channel_top5_users_voice(
                guild_id=guild.id, channel_id=channel.id, role_filter_ids=role_ids,
                start_time=start_time, end_time=end_time
            )

            user_counts = Counter()
            for user_data in top_users_data:
                if isinstance(user_data, dict) and 'user_id' in user_data:
                    user_counts[str(user_data['user_id'])] = user_data.get(
                        'total_seconds', 0)

            timeseries_data = await db_cog.q_channel_timeseries_voice_1d_5d_10d_20d_30d(
                guild_id=guild.id, channel_id=channel.id, role_filter_ids=role_ids,
                start_time=start_time, end_time=end_time
            )

            timeseries_dict = {}
            if timeseries_data:
                timeseries_dict = {
                    '1': timeseries_data.get('1d', 0),
                    '5': timeseries_data.get('5d', 0),
                    '10': timeseries_data.get('10d', 0),
                    '20': timeseries_data.get('20d', 0),
                    '30': timeseries_data.get('30d', 0)
                }

            return {
                'total_seconds': channel_voice_stats.get('total_seconds', 0),
                'users': user_counts,
                'timeseries': timeseries_dict,
                'timestamp': time.time()
            }
        except Exception as e:
            print(f"❌ Error getting voice stats: {e}")
            traceback.print_exc()
            return None

    @rate_limited(RateLimitType.MESSAGE, timeout=30.0)
    async def _handle_channel_stats_command(self, ctx_or_interaction, channel=None, is_interaction=False):
        try:
            if is_interaction:
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

            if guild is None:
                if is_interaction:
                    await ctx_or_interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
                else:
                    await ctx_or_interaction.send("❌ This command can only be used in a server.", delete_after=5)
                return

            has_permission = await check_command_permission(ctx_or_interaction if is_interaction else ctx_or_interaction)
            if not has_permission:
                embed = discord.Embed(
                    title="❌ Permission Denied", description="Sorry! You don't have permission to access this command.", color=discord.Color.red())
                if is_interaction:
                    await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    await ctx_or_interaction.send(embed=embed, delete_after=10)
                return

            if channel is None:
                if is_interaction:
                    channel = ctx_or_interaction.channel
                else:
                    channel = ctx_or_interaction.channel
                if not isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
                    if is_interaction:
                        await ctx_or_interaction.response.send_message("❌ This command only works in text or voice channels.", ephemeral=True)
                    else:
                        await ctx_or_interaction.send("❌ This command only works in text or voice channels.", delete_after=5)
                    return

            if not isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
                if is_interaction:
                    await ctx_or_interaction.response.send_message("❌ Please select a text or voice channel.", ephemeral=True)
                else:
                    await ctx_or_interaction.send("❌ Please select a text or voice channel.", delete_after=5)
                return

            db_cog = self.bot.get_cog('DatabaseStats')
            if not db_cog:
                if is_interaction:
                    await ctx_or_interaction.response.send_message("❌ Database system is not available. Please try again later.", ephemeral=True)
                else:
                    await ctx_or_interaction.send("❌ Database system is not available. Please try again later.", delete_after=10)
                return

            if is_interaction:
                await ctx_or_interaction.response.defer()

            # Get server default time range
            start_time, end_time, display_text, days_back_equiv = await self.get_server_default_time_range(guild.id)

            if isinstance(channel, discord.TextChannel):
                channel_data = await self._get_channel_stats_from_db(guild, channel, start_time, end_time, days_back_equiv)
                if channel_data is None:
                    channel_data = {'total': 0, 'users': Counter(
                    ), 'timeseries': {}, 'timestamp': time.time()}
                img_bytes = await generate_channel_stats_image(guild, channel, channel_data, display_text)
                filename = "channel_stats.png"
                stats_type = "messages"
            else:
                voice_data = await self._get_voice_stats_from_db(guild, channel, start_time, end_time, days_back_equiv)
                if voice_data is None:
                    voice_data = {'total_seconds': 0, 'users': Counter(
                    ), 'timeseries': {}, 'timestamp': time.time()}
                img_bytes = await generate_voice_stats_image(guild, channel, voice_data, display_text)
                filename = "voice_stats.png"
                stats_type = "voice"

            view = ChannelStatsView(
                self, guild, channel, start_time=start_time, end_time=end_time,
                days_back_equiv=days_back_equiv, display_text=display_text,
                stats_type=stats_type, using_server_default=True)
            file = discord.File(img_bytes, filename=filename)

            if is_interaction:
                msg = await send_method(file=file, view=view)
            else:
                msg = await send_method(file=file, view=view, delete_after=300)

            self.active_sessions[msg.id] = {
                'guild_id': guild.id, 'user_id': user.id, 'channel_id': channel.id,
                'current_start_time': start_time, 'current_end_time': end_time,
                'current_days_back_equiv': days_back_equiv, 'current_display_text': display_text,
                'selected_role_id': None, 'stats_type': stats_type,
                'view': view, 'created_at': time.time()
            }
        except Exception as e:
            print(f"Error in _handle_channel_stats_command: {e}")
            traceback.print_exc()
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

    @commands.command(name="ch")
    async def channel_stats_shortcut(self, ctx: commands.Context, *, channel_input: str = None):
        guild = ctx.guild
        if channel_input:
            channel = None
            if channel_input.startswith('<#') and channel_input.endswith('>'):
                try:
                    channel_id = int(channel_input[2:-1])
                    channel = guild.get_channel(channel_id)
                except:
                    pass
            if channel is None:
                try:
                    channel_id = int(channel_input)
                    channel = guild.get_channel(channel_id)
                except:
                    pass
            if channel is None:
                for guild_channel in guild.channels:
                    if isinstance(guild_channel, (discord.TextChannel, discord.VoiceChannel)):
                        if guild_channel.name.lower() == channel_input.lower():
                            channel = guild_channel
                            break
            if channel is None:
                await ctx.send("❌ Could not find the specified channel.", delete_after=5)
                return
        else:
            channel = ctx.channel
            if not isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
                await ctx.send("❌ This command only works in text or voice channels.", delete_after=5)
                return
        await self._handle_channel_stats_command(ctx, channel, is_interaction=False)

    @commands.group(name="channel", invoke_without_command=True)
    async def channel_group_prefix(self, ctx: commands.Context):
        await ctx.send("Available commands:\n- `channel stats [channel]` - Show channel statistics (defaults to current channel)\n- `ch [channel]` - Shortcut for channel stats")

    @channel_group_prefix.command(name="stats")
    async def channel_stats_prefix(self, ctx: commands.Context, *, channel_input: str = None):
        guild = ctx.guild
        if channel_input:
            channel = None
            if channel_input.startswith('<#') and channel_input.endswith('>'):
                try:
                    channel_id = int(channel_input[2:-1])
                    channel = guild.get_channel(channel_id)
                except:
                    pass
            if channel is None:
                try:
                    channel_id = int(channel_input)
                    channel = guild.get_channel(channel_id)
                except:
                    pass
            if channel is None:
                for guild_channel in guild.channels:
                    if isinstance(guild_channel, (discord.TextChannel, discord.VoiceChannel)):
                        if guild_channel.name.lower() == channel_input.lower():
                            channel = guild_channel
                            break
            if channel is None:
                await ctx.send("❌ Could not find the specified channel.", delete_after=5)
                return
        else:
            channel = ctx.channel
            if not isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
                await ctx.send("❌ This command only works in text or voice channels.", delete_after=5)
                return
        await self._handle_channel_stats_command(ctx, channel, is_interaction=False)

    channel_group = app_commands.Group(
        name="channel", description="channel related commands")

    @channel_group.command(name="stats", description="Get message or voice activity stats for a channel.")
    @app_commands.describe(channel="Select a channel to get stats for (optional, defaults to current channel)")
    async def channel_stats(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel = None):
        if channel is None:
            channel = interaction.channel
            if not isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
                await interaction.response.send_message("❌ This command only works in text or voice channels.", ephemeral=True)
                return
        await self._handle_channel_stats_command(interaction, channel, is_interaction=True)

    @tasks.loop(minutes=5)
    async def cleanup_sessions(self):
        current_time = time.time()
        keys_to_remove = []
        for message_id, session in self.active_sessions.items():
            if current_time - session.get('created_at', current_time) > 3600:
                keys_to_remove.append(message_id)
        for key in keys_to_remove:
            del self.active_sessions[key]

    async def cog_load(self):
        self.cleanup_sessions.start()

    async def cog_unload(self):
        self.cleanup_sessions.cancel()


async def setup(bot):
    await bot.add_cog(ChannelCommands(bot))
