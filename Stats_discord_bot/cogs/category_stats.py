import aiohttp
import os
import io
from PIL import Image, ImageDraw, ImageFont
import asyncio
import time
from datetime import datetime, timedelta, timezone
from collections import Counter
from discord import app_commands
from discord.ext import commands
import discord
from pathlib import Path
from typing import Optional, List, Dict, Any
import unicodedata
import re
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


async def get_user_info(bot, guild: discord.Guild, user_id: int) -> tuple:
    """
    Get user information and check if account exists.
    Returns: (member_object_or_None, username, account_exists)

    - If user is in guild: returns (member, name, True) - NO rate limiting
    - If user left but account exists: returns (None, name, True) - rate limited
    - If account deleted: returns (None, "[Deleted User]", False) - rate limited
    """
    try:
        # First try to get from cache (user is in the guild) - NO RATE LIMITING
        member = guild.get_member(user_id)
        if member:
            return member, member.name, True

        # User left the server - rate-limited fetch for fallback ONLY
        user = await _fetch_user_limited(bot, user_id)
        if user:
            return None, user.name, True
        else:
            return None, "[Deleted User]", False
    except Exception:
        return None, f"User {user_id}", True


# FORMAT

def format_voice_time(total_seconds):
    if total_seconds == 0:
        return "0s"

    days = total_seconds // (3600 * 24)
    hours = (total_seconds % (3600 * 24)) // 3600
    minutes = (total_seconds % 3600) // 60

    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    elif hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m"


def format_message_count(count):
    return f"{count:,}"


# FONTS

def get_fonts():
    try:
        custom_font_path = BASE_DIR / "assets" / "fonts" / "HorndonD.ttf"
        if os.path.exists(custom_font_path):
            font_small = ImageFont.truetype(custom_font_path, 16)
            font_medium = ImageFont.truetype(custom_font_path, 20)
            font_large = ImageFont.truetype(custom_font_path, 24)
            font_larger = ImageFont.truetype(custom_font_path, 30)
            font_huge = ImageFont.truetype(custom_font_path, 40)
            return font_small, font_medium, font_large, font_larger, font_huge
    except:
        pass

    try:
        font_small = ImageFont.truetype("arial.ttf", 16)
        font_medium = ImageFont.truetype("arial.ttf", 20)
        font_large = ImageFont.truetype("arial.ttf", 24)
        font_larger = ImageFont.truetype("arial.ttf", 30)
        font_huge = ImageFont.truetype("arial.ttf", 40)
        return font_small, font_medium, font_large, font_larger, font_huge
    except:
        try:
            font_small = ImageFont.truetype("Helvetica.ttf", 16)
            font_medium = ImageFont.truetype("Helvetica.ttf", 20)
            font_large = ImageFont.truetype("Helvetica.ttf", 24)
            font_larger = ImageFont.truetype("Helvetica.ttf", 30)
            font_huge = ImageFont.truetype("Helvetica.ttf", 40)
            return font_small, font_medium, font_large, font_larger, font_huge
        except:
            font_small = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_large = ImageFont.load_default()
            font_larger = ImageFont.load_default()
            font_huge = ImageFont.load_default()
            return font_small, font_medium, font_large, font_larger, font_huge


def get_horndon_font(size=40):
    custom_font_path = BASE_DIR / "assets" / "fonts" / "HorndonD.ttf"
    try:
        if os.path.exists(custom_font_path):
            return ImageFont.truetype(custom_font_path, size)
    except Exception as e:
        print(f"Warning: Could not load HorndonD font at size {size}: {e}")

    try:
        return ImageFont.truetype("arial.ttf", size)
    except:
        return ImageFont.load_default()


def get_regular_font(size=24):
    custom_font_path = BASE_DIR / "assets" / "fonts" / "HorndonD.ttf"
    try:
        if os.path.exists(custom_font_path):
            return ImageFont.truetype(custom_font_path, size)
    except Exception as e:
        print(f"Warning: Could not load HorndonD font at size {size}: {e}")

    try:
        return ImageFont.truetype("arial.ttf", size)
    except:
        return ImageFont.load_default()


def normalize_name(name: str) -> str:
    if not name or name.strip() == "":
        return "-"
    normalized = unicodedata.normalize('NFKD', name)
    ascii_only = normalized.encode('ascii', 'ignore').decode('ascii')
    return ascii_only if ascii_only.strip() != "" else "-"


# INVISIBLE RECTANGLE FUNCTIONS

def check_text_against_rectangle(draw, text, font, text_x, text_y, rect_left, rect_top, rect_right, rect_bottom):
    bbox = draw.textbbox((text_x, text_y), text, font=font)
    text_left = bbox[0]
    text_right = bbox[2]
    text_top = bbox[1]
    text_bottom = bbox[3]

    exceeds_width = (text_left < rect_left) or (text_right > rect_right)
    exceeds_height = (text_top < rect_top) or (text_bottom > rect_bottom)

    return exceeds_width or exceeds_height


def fit_server_name(draw, text, text_x, text_y, rect_center_x, rect_center_y, rect_width, rect_height):
    rect_left = rect_center_x - (rect_width // 2)
    rect_right = rect_center_x + (rect_width // 2)
    rect_top = rect_center_y - (rect_height // 2)
    rect_bottom = rect_center_y + (rect_height // 2)

    font_sizes = [40, 38, 36, 34, 32, 30, 28,
                  26, 24, 22, 20, 18, 16, 14, 12, 10, 8]

    for idx, font_size in enumerate(font_sizes):
        font = get_horndon_font(font_size)

        vertical_offset = idx
        adjusted_y = text_y + vertical_offset

        if not check_text_against_rectangle(draw, text, font, text_x, adjusted_y,
                                            rect_left, rect_top, rect_right, rect_bottom):
            return text, font, (text_x, adjusted_y), font_size

    smallest_font = font_sizes[-1]
    font = get_horndon_font(smallest_font)

    truncated_text = text
    while len(truncated_text) > 3:
        truncated_text = truncated_text[:-4] + "..."

        vertical_offset = len(font_sizes) - 1
        adjusted_y = text_y + vertical_offset

        if not check_text_against_rectangle(draw, truncated_text, font, text_x, adjusted_y,
                                            rect_left, rect_top, rect_right, rect_bottom):
            return truncated_text, font, (text_x, adjusted_y), smallest_font

    vertical_offset = len(font_sizes) - 1
    final_text = text[:3] + "..." if len(text) > 3 else text
    return final_text, font, (text_x, text_y + vertical_offset), smallest_font


def fit_regular_text(draw, text, text_x, text_y, rect_center_x, rect_center_y, rect_width, rect_height):
    rect_left = rect_center_x - (rect_width // 2)
    rect_right = rect_center_x + (rect_width // 2)
    rect_top = rect_center_y - (rect_height // 2)
    rect_bottom = rect_center_y + (rect_height // 2)

    font_sizes = [24, 22, 20, 18, 16, 14, 12, 10, 8]

    for idx, font_size in enumerate(font_sizes):
        font = get_regular_font(font_size)

        vertical_offset = idx // 2
        adjusted_y = text_y + vertical_offset

        if not check_text_against_rectangle(draw, text, font, text_x, adjusted_y,
                                            rect_left, rect_top, rect_right, rect_bottom):
            return text, font, (text_x, adjusted_y), font_size

    smallest_font = font_sizes[-1]
    font = get_regular_font(smallest_font)

    truncated_text = text
    while len(truncated_text) > 3:
        truncated_text = truncated_text[:-4] + "..."

        vertical_offset = len(font_sizes) // 2
        adjusted_y = text_y + vertical_offset

        if not check_text_against_rectangle(draw, truncated_text, font, text_x, adjusted_y,
                                            rect_left, rect_top, rect_right, rect_bottom):
            return truncated_text, font, (text_x, adjusted_y), smallest_font

    vertical_offset = len(font_sizes) // 2
    final_text = text[:3] + "..." if len(text) > 3 else text
    return final_text, font, (text_x, text_y + vertical_offset), smallest_font


def draw_text_with_stroke(draw, text, position, font, fill="white", stroke_fill="black", stroke_width=1):
    x, y = position

    for dx in [-stroke_width, 0, stroke_width]:
        for dy in [-stroke_width, 0, stroke_width]:
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, fill=stroke_fill, font=font)

    draw.text((x, y), text, fill=fill, font=font)


# IMAGE GENERATION

async def generate_category_message_stats_image(bot: commands.Bot, guild: discord.Guild, category: discord.CategoryChannel, message_data: dict, display_text: str, role_id: str = None, role_name: str = None):
    template_path = BASE_DIR / "assets" / "images" / \
        "category message stats final png.png"
    try:
        image = Image.open(template_path)
    except FileNotFoundError:
        image = Image.new('RGB', (800, 600), color='#2F3136')

    if image.mode != "RGB":
        image = image.convert("RGB")

    draw = ImageDraw.Draw(image)

    font_small, font_medium, font_large, font_larger, font_huge = get_fonts()

    server_name_rect = {"center": (135, 30), "width": 245, "height": 45}

    username_rectangles = [
        {"center": (20 + 52, 320 + 17), "width": 125, "height": 50},
        {"center": (20 + 52, 375 + 17), "width": 125, "height": 50},
        {"center": (20 + 52, 430 + 17), "width": 125, "height": 50},
        {"center": (20 + 52, 485 + 17), "width": 125, "height": 50},
        {"center": (20 + 52, 535 + 17), "width": 125, "height": 50}
    ]

    channel_name_rectangles = [
        {"center": (280 + 52, 320 + 17), "width": 125, "height": 50},
        {"center": (280 + 52, 375 + 17), "width": 125, "height": 50},
        {"center": (280 + 52, 430 + 17), "width": 125, "height": 50},
        {"center": (280 + 52, 485 + 17), "width": 125, "height": 50},
        {"center": (280 + 52, 535 + 17), "width": 125, "height": 50},
    ]

    normalized_category_name = normalize_name(category.name)
    fitted_server_name, server_name_font, server_name_pos, server_font_size = fit_server_name(
        draw,
        normalized_category_name,
        30,
        7,
        server_name_rect["center"][0],
        server_name_rect["center"][1],
        server_name_rect["width"],
        server_name_rect["height"]
    )

    draw_text_with_stroke(
        draw, fitted_server_name, server_name_pos, server_name_font
    )

    try:
        if guild.icon:
            icon_url = guild.icon.url
            async with aiohttp.ClientSession() as session:
                async with session.get(icon_url) as response:
                    icon_data = await response.read()

            icon_image = Image.open(io.BytesIO(icon_data))

            icon_size = (20, 20)
            icon_image = icon_image.resize(icon_size, Image.Resampling.LANCZOS)

            guild_name = normalize_name(guild.name)
            bbox = draw.textbbox((0, 0), guild_name, font=font_medium)
            text_width = bbox[2] - bbox[0]

            icon_x = 375 - (text_width // 2) - 29
            icon_y = 75 - 10

            image.paste(icon_image, (int(icon_x), int(icon_y)))

            text_x = 375 - (text_width // 2)
            draw_text_with_stroke(
                draw, guild_name, (text_x, 75 - 13), font_medium
            )

        else:
            guild_name = normalize_name(guild.name)
            bbox = draw.textbbox((0, 0), guild_name, font=font_medium)
            text_width = bbox[2] - bbox[0]
            text_x = 375 - (text_width // 2)
            draw_text_with_stroke(
                draw, guild_name, (text_x, 75 - 13), font_medium
            )

    except Exception as e:
        print(f"❌ Could not add server icon: {e}")
        guild_name = normalize_name(guild.name)
        bbox = draw.textbbox((0, 0), guild_name, font=font_medium)
        text_width = bbox[2] - bbox[0]
        text_x = 375 - (text_width // 2)
        draw_text_with_stroke(
            draw, guild_name, (text_x, 75 - 13), font_medium
        )

    text_channels = [ch for ch in category.channels if isinstance(
        ch, discord.TextChannel)]
    channels_count = len(text_channels)

    draw_text_with_stroke(
        draw, str(channels_count), (125, 160), font_huge
    )

    total_messages = message_data.get('total_messages', 0) or 0
    draw_text_with_stroke(
        draw, format_message_count(total_messages), (380, 160), font_huge
    )

    current_date = datetime.now().strftime("%B %d, %Y")
    draw_text_with_stroke(
        draw, current_date, (550, 40), font_small
    )

    # ROLE FILTER - USE DATABASE ROLE NAME
    role_text = role_name if role_name else "No Filter"

    draw_text_with_stroke(
        draw, role_text, (590, 420), font_small
    )

    time_period_text = display_text

    draw_text_with_stroke(
        draw, time_period_text, (635, 458), font_small
    )

    top_users = message_data.get('users', Counter()).most_common(5)

    user_positions = [
        (20, 320), (20, 375), (20, 430), (20, 485), (20, 535)
    ]
    message_positions = [
        (195, 320), (195, 375), (195, 430), (195, 485), (195, 535)
    ]

    for i, ((user_id, message_count), (user_x, user_y), (msg_x, msg_y)) in enumerate(zip(top_users, user_positions, message_positions)):
        member, username_raw, account_exists = await get_user_info(bot, guild, int(user_id))

        if not account_exists:
            username = "[Deleted User]"
        else:
            username = normalize_name(username_raw)

        if i < len(username_rectangles):
            rect_info = username_rectangles[i]

            fitted_username, username_font, username_pos, username_font_size = fit_regular_text(
                draw,
                username,
                user_x,
                user_y,
                rect_info["center"][0],
                rect_info["center"][1],
                rect_info["width"],
                rect_info["height"],
            )

            draw_text_with_stroke(
                draw, fitted_username, username_pos, username_font
            )

        count_text = format_message_count(message_count or 0)
        draw_text_with_stroke(
            draw, count_text, (msg_x, msg_y), font_large
        )

    top_channels = message_data.get('channels', Counter()).most_common(5)

    channel_positions = [
        (280, 320), (280, 375), (280, 430), (280, 485), (280, 535)
    ]
    channel_message_positions = [
        (450, 320), (450, 375), (450, 430), (450, 485), (450, 535)
    ]

    for i, ((channel_id, message_count), (chan_x, chan_y), (msg_x, msg_y)) in enumerate(zip(top_channels, channel_positions, channel_message_positions)):
        channel = guild.get_channel(int(channel_id))
        if channel:
            if isinstance(channel, discord.TextChannel):
                channel_name = f"#{normalize_name(channel.name)}"
            elif isinstance(channel, discord.VoiceChannel):
                channel_name = f"{normalize_name(channel.name)}"
            elif isinstance(channel, discord.StageChannel):
                channel_name = f"{normalize_name(channel.name)}"
            else:
                channel_name = normalize_name(channel.name)
        else:
            channel_name = f"[Deleted Channel]"

        if i < len(channel_name_rectangles):
            rect_info = channel_name_rectangles[i]

            fitted_channel_name, channel_font, channel_pos, channel_font_size = fit_regular_text(
                draw,
                channel_name,
                chan_x,
                chan_y,
                rect_info["center"][0],
                rect_info["center"][1],
                rect_info["width"],
                rect_info["height"],
            )

            draw_text_with_stroke(
                draw, fitted_channel_name, channel_pos, channel_font
            )
        elif i == 0:
            draw_text_with_stroke(
                draw, channel_name, (chan_x, chan_y), font_large
            )

        count_text = format_message_count(message_count or 0)
        draw_text_with_stroke(
            draw, count_text, (msg_x, msg_y), font_large
        )

    messages_over_days = {}
    daily_data = message_data.get('daily', Counter())
    for days in [1, 5, 10, 20, 30]:
        messages_over_days[days] = daily_data.get(days, 0)

    time_positions = {
        1: (670, 155),
        5: (670, 210),
        10: (670, 265),
        20: (670, 315),
        30: (670, 365)
    }

    for days, (x, y) in time_positions.items():
        message_count = messages_over_days.get(days, 0) or 0
        count_text = format_message_count(message_count)

        draw_text_with_stroke(
            draw, count_text, (x, y), font_large
        )

    img_bytes = io.BytesIO()
    image.save(img_bytes, format='PNG')
    img_bytes.seek(0)

    return img_bytes


async def generate_category_voice_stats_image(bot: commands.Bot, guild: discord.Guild, category: discord.CategoryChannel, voice_data: dict, display_text: str, role_id: str = None, role_name: str = None):
    template_path = BASE_DIR / "assets" / "images" / \
        "category voice stats final png.png"
    try:
        image = Image.open(template_path)
    except FileNotFoundError:
        image = Image.new('RGB', (800, 600), color='#2F3136')

    draw = ImageDraw.Draw(image)

    font_small, font_medium, font_large, font_larger, font_huge = get_fonts()

    server_name_rect = {"center": (135, 30), "width": 245, "height": 45}

    username_rectangles = [
        {"center": (20 + 52, 320 + 17), "width": 125, "height": 50},
        {"center": (20 + 52, 375 + 17), "width": 125, "height": 50},
        {"center": (20 + 52, 430 + 17), "width": 125, "height": 50},
        {"center": (20 + 52, 485 + 17), "width": 125, "height": 50},
        {"center": (20 + 52, 535 + 17), "width": 125, "height": 50}
    ]

    channel_name_rectangles = [
        {"center": (280 + 52, 320 + 17), "width": 125, "height": 50},
        {"center": (280 + 52, 375 + 17), "width": 125, "height": 50},
        {"center": (280 + 52, 430 + 17), "width": 125, "height": 50},
        {"center": (280 + 52, 485 + 17), "width": 125, "height": 50},
        {"center": (280 + 52, 535 + 17), "width": 125, "height": 50},
    ]

    normalized_category_name = normalize_name(category.name)
    fitted_server_name, server_name_font, server_name_pos, server_font_size = fit_server_name(
        draw,
        normalized_category_name,
        30,
        7,
        server_name_rect["center"][0],
        server_name_rect["center"][1],
        server_name_rect["width"],
        server_name_rect["height"]
    )

    draw_text_with_stroke(
        draw, fitted_server_name, server_name_pos, server_name_font
    )

    try:
        if guild.icon:
            icon_url = guild.icon.url
            async with aiohttp.ClientSession() as session:
                async with session.get(icon_url) as response:
                    icon_data = await response.read()

            icon_image = Image.open(io.BytesIO(icon_data))

            icon_size = (20, 20)
            icon_image = icon_image.resize(icon_size, Image.Resampling.LANCZOS)

            guild_name = normalize_name(guild.name)
            bbox = draw.textbbox((0, 0), guild_name, font=font_medium)
            text_width = bbox[2] - bbox[0]

            icon_x = 375 - (text_width // 2) - 29
            icon_y = 75 - 10

            image.paste(icon_image, (int(icon_x), int(icon_y)))

            text_x = 375 - (text_width // 2)
            draw_text_with_stroke(
                draw, guild_name, (text_x, 75 - 13), font_medium
            )

        else:
            guild_name = normalize_name(guild.name)
            bbox = draw.textbbox((0, 0), guild_name, font=font_medium)
            text_width = bbox[2] - bbox[0]
            text_x = 375 - (text_width // 2)
            draw_text_with_stroke(
                draw, guild_name, (text_x, 75 - 13), font_medium
            )

    except Exception as e:
        print(f"❌ Could not add server icon: {e}")
        guild_name = normalize_name(guild.name)
        bbox = draw.textbbox((0, 0), guild_name, font=font_medium)
        text_width = bbox[2] - bbox[0]
        text_x = 375 - (text_width // 2)
        draw_text_with_stroke(
            draw, guild_name, (text_x, 75 - 13), font_medium
        )

    voice_channels = [ch for ch in category.channels if isinstance(
        ch, discord.VoiceChannel)]
    channels_count = len(voice_channels)

    draw_text_with_stroke(
        draw, str(channels_count), (125, 160), font_huge
    )

    total_seconds = voice_data.get('total_seconds', 0) or 0
    total_voice_text = format_voice_time(total_seconds)

    draw_text_with_stroke(
        draw, total_voice_text, (380, 160), font_huge
    )

    current_date = datetime.now().strftime("%B %d, %Y")

    draw_text_with_stroke(
        draw, current_date, (550, 40), font_small
    )

    # ROLE FILTER - USE DATABASE ROLE NAME
    role_text = role_name if role_name else "No Filter"

    draw_text_with_stroke(
        draw, role_text, (590, 420), font_small
    )

    time_period_text = display_text

    draw_text_with_stroke(
        draw, time_period_text, (635, 458), font_small
    )

    top_users = voice_data.get('users', Counter()).most_common(5)
    user_positions = [
        (20, 320), (20, 375), (20, 430), (20, 485), (20, 535)
    ]
    voice_time_positions = [
        (195, 320), (195, 375), (195, 430), (195, 485), (195, 535)
    ]

    for i, ((user_id, user_seconds), (user_x, user_y), (time_x, time_y)) in enumerate(zip(top_users, user_positions, voice_time_positions)):
        member, username_raw, account_exists = await get_user_info(bot, guild, int(user_id))

        if not account_exists:
            username = "[Deleted User]"
        else:
            username = normalize_name(username_raw)

        if i < len(username_rectangles):
            rect_info = username_rectangles[i]

            fitted_username, username_font, username_pos, username_font_size = fit_regular_text(
                draw,
                username,
                user_x,
                user_y,
                rect_info["center"][0],
                rect_info["center"][1],
                rect_info["width"],
                rect_info["height"],
            )

            draw_text_with_stroke(
                draw, fitted_username, username_pos, username_font
            )

        voice_time_text = format_voice_time(user_seconds or 0)
        draw_text_with_stroke(
            draw, voice_time_text, (time_x, time_y), font_large
        )

    top_channels = voice_data.get('channels', Counter()).most_common(5)

    channel_positions = [
        (280, 320), (280, 375), (280, 430), (280, 485), (280, 535)
    ]
    channel_voice_positions = [
        (450, 320), (450, 375), (450, 430), (450, 485), (450, 535)
    ]

    for i, ((channel_id, channel_seconds), (chan_x, chan_y), (time_x, time_y)) in enumerate(zip(top_channels, channel_positions, channel_voice_positions)):
        channel = guild.get_channel(int(channel_id))
        if channel:
            if isinstance(channel, discord.VoiceChannel):
                channel_name = f"🔊{normalize_name(channel.name)}"
            elif isinstance(channel, discord.StageChannel):
                channel_name = f"🎤{normalize_name(channel.name)}"
            else:
                channel_name = normalize_name(channel.name)
        else:
            channel_name = f"[Deleted Channel]"

        if i < len(channel_name_rectangles):
            rect_info = channel_name_rectangles[i]

            fitted_channel_name, channel_font, channel_pos, channel_font_size = fit_regular_text(
                draw,
                channel_name,
                chan_x,
                chan_y,
                rect_info["center"][0],
                rect_info["center"][1],
                rect_info["width"],
                rect_info["height"],
            )

            draw_text_with_stroke(
                draw, fitted_channel_name, channel_pos, channel_font
            )
        elif i == 0:
            draw_text_with_stroke(
                draw, channel_name, (chan_x, chan_y), font_large
            )

        voice_time_text = format_voice_time(channel_seconds or 0)
        draw_text_with_stroke(
            draw, voice_time_text, (time_x, time_y), font_large
        )

    voice_time_over_days = {}
    daily_data = voice_data.get('daily', Counter())
    for days in [1, 5, 10, 20, 30]:
        voice_time_over_days[days] = daily_data.get(days, 0)

    time_positions = {
        1: (670, 155),
        5: (670, 210),
        10: (670, 265),
        20: (670, 315),
        30: (670, 365)
    }

    for days, (x, y) in time_positions.items():
        seconds = voice_time_over_days.get(days, 0) or 0
        voice_time_text = format_voice_time(seconds)

        draw_text_with_stroke(
            draw, voice_time_text, (x, y), font_large
        )

    img_bytes = io.BytesIO()
    image.save(img_bytes, format='PNG')
    img_bytes.seek(0)

    return img_bytes


# STATS TYPE SELECT MENU

class StatsTypeSelectMenu(discord.ui.Select):
    def __init__(self, current_stats_type: str = "messages"):
        options = [
            discord.SelectOption(
                label="Messages",
                value="messages",
                description="Show message activity stats",
                emoji="💬",
                default=(current_stats_type == "messages")
            ),
            discord.SelectOption(
                label="Voice Activity",
                value="voice",
                description="Show voice activity stats",
                emoji="🎤",
                default=(current_stats_type == "voice")
            )
        ]

        super().__init__(
            placeholder="Select statistics type...",
            options=options,
            custom_id="stats_type_select",
            min_values=1,
            max_values=1,
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        if not self.values:
            await interaction.response.send_message("❌ No statistics type selected.", ephemeral=True)
            return

        view = self.view
        view.stats_type = self.values[0]
        view.selected_role_id = None

        await interaction.response.defer()

        now = datetime.utcnow()
        view.current_start_time = now - timedelta(days=14)
        view.current_end_time = now
        view.current_days_back_equiv = 14
        view.current_display_text = "14 days"
        view.using_server_default = False

        view._update_buttons()

        if view.stats_type == "messages":
            category_data = await view.cog._get_category_message_stats(
                view.guild, view.category, view.current_start_time, view.current_end_time, view.current_days_back_equiv, None
            )
            if category_data is None:
                category_data = {
                    'total_messages': 0,
                    'channels': Counter(),
                    'users': Counter(),
                    'daily': Counter(),
                    'timestamp': time.time()
                }
            img_bytes = await generate_category_message_stats_image(
                view.cog.bot, view.guild, view.category, category_data, view.current_display_text, None
            )
        else:
            category_data = await view.cog._get_category_voice_stats(
                view.guild, view.category, view.current_start_time, view.current_end_time, view.current_days_back_equiv, None
            )
            if category_data is None:
                category_data = {
                    'total_seconds': 0,
                    'channels': Counter(),
                    'users': Counter(),
                    'daily': Counter(),
                    'timestamp': time.time()
                }
            img_bytes = await generate_category_voice_stats_image(
                view.cog.bot, view.guild, view.category, category_data, view.current_display_text, None
            )

        file = discord.File(
            img_bytes,
            filename=f"category_{view.stats_type}_stats.png"
        )
        await interaction.edit_original_response(attachments=[file], view=view)


# ROLE ID MODAL

class CategoryRoleIDModal(discord.ui.Modal, title='Input Role ID'):
    def __init__(self, cog_instance, original_message_id, guild, category, stats_type, view):
        super().__init__(timeout=300)
        self.cog = cog_instance
        self.original_message_id = original_message_id
        self.guild = guild
        self.category = category
        self.stats_type = stats_type
        self.view = view

    role_id = discord.ui.TextInput(
        label='Enter Role ID',
        placeholder='e.g., 123456789012345678 or "none" to remove filter',
        min_length=3,
        max_length=20,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            role_id = self.role_id.value.strip()

            if role_id.lower() == "none" or role_id.lower() == "clear":
                role_id = None
            else:
                try:
                    role_id_int = int(role_id)
                    role = self.guild.get_role(role_id_int)

                    if role is None:
                        embed = discord.Embed(
                            title="❌ Invalid Role ID",
                            description="Sorry! The role id you inputted is not valid, please try again.",
                            color=discord.Color.red()
                        )
                        await interaction.response.send_message(embed=embed, ephemeral=True)
                        return

                    role_id = str(role_id_int)
                except ValueError:
                    embed = discord.Embed(
                        title="❌ Invalid Role ID",
                        description="Please enter a valid numeric role ID.",
                        color=discord.Color.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return

            await interaction.response.defer()

            # Get role name from database
            role_name = None
            if role_id:
                db_stats = self.cog.bot.get_cog('DatabaseStats')
                if db_stats and db_stats.pool:
                    try:
                        async with db_stats.pool.acquire() as conn:
                            row = await conn.fetchrow("""
                                SELECT role_name FROM current_role_members 
                                WHERE role_id = $1 AND guild_id = $2 
                                LIMIT 1
                            """, int(role_id), self.guild.id)
                            if row:
                                role_name = row['role_name']
                    except:
                        pass

            if self.view:
                self.view.selected_role_id = role_id
                self.view.using_server_default = False

                if self.stats_type == "messages":
                    category_data = await self.cog._get_category_message_stats(
                        self.guild, self.category, self.view.current_start_time, self.view.current_end_time, self.view.current_days_back_equiv, role_id
                    )
                    if category_data is None:
                        category_data = {
                            'total_messages': 0,
                            'channels': Counter(),
                            'users': Counter(),
                            'daily': Counter(),
                            'timestamp': time.time()
                        }
                    img_bytes = await generate_category_message_stats_image(
                        self.cog.bot, self.guild, self.category, category_data, self.view.current_display_text, role_id, role_name
                    )
                else:
                    category_data = await self.cog._get_category_voice_stats(
                        self.guild, self.category, self.view.current_start_time, self.view.current_end_time, self.view.current_days_back_equiv, role_id
                    )
                    if category_data is None:
                        category_data = {
                            'total_seconds': 0,
                            'channels': Counter(),
                            'users': Counter(),
                            'daily': Counter(),
                            'timestamp': time.time()
                        }
                    img_bytes = await generate_category_voice_stats_image(
                        self.cog.bot, self.guild, self.category, category_data, self.view.current_display_text, role_id, role_name
                    )

                self.view._update_buttons()
                file = discord.File(
                    img_bytes,
                    filename=f"category_{self.stats_type}_stats.png"
                )

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
            print(f"Error in role ID modal: {e}")
            await interaction.followup.send("❌ An error occurred.", ephemeral=True)


# TIME MODAL

class CategoryStatsTimeModal(discord.ui.Modal, title='Custom Time Period'):
    def __init__(self, cog_instance, original_message_id, guild, category, stats_type, view):
        super().__init__(timeout=300)
        self.cog = cog_instance
        self.original_message_id = original_message_id
        self.guild = guild
        self.category = category
        self.stats_type = stats_type
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

            await interaction.response.defer()

            if self.view:
                now = datetime.utcnow()
                self.view.current_start_time = now - timedelta(days=days)
                self.view.current_end_time = now
                self.view.current_days_back_equiv = days
                self.view.current_display_text = f"{days} days"
                self.view.using_server_default = False
                self.view.show_time_buttons = False

                if self.stats_type == "messages":
                    category_data = await self.cog._get_category_message_stats(
                        self.guild, self.category, self.view.current_start_time, self.view.current_end_time, self.view.current_days_back_equiv, self.view.selected_role_id
                    )
                    if category_data is None:
                        category_data = {
                            'total_messages': 0,
                            'channels': Counter(),
                            'users': Counter(),
                            'daily': Counter(),
                            'timestamp': time.time()
                        }
                    img_bytes = await generate_category_message_stats_image(
                        self.cog.bot, self.guild, self.category, category_data, self.view.current_display_text, self.view.selected_role_id
                    )
                else:
                    category_data = await self.cog._get_category_voice_stats(
                        self.guild, self.category, self.view.current_start_time, self.view.current_end_time, self.view.current_days_back_equiv, self.view.selected_role_id
                    )
                    if category_data is None:
                        category_data = {
                            'total_seconds': 0,
                            'channels': Counter(),
                            'users': Counter(),
                            'daily': Counter(),
                            'timestamp': time.time()
                        }
                    img_bytes = await generate_category_voice_stats_image(
                        self.cog.bot, self.guild, self.category, category_data, self.view.current_display_text, self.view.selected_role_id
                    )

                self.view._update_buttons()
                file = discord.File(
                    img_bytes,
                    filename=f"category_{self.stats_type}_stats.png"
                )

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

        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number.", ephemeral=True)
        except Exception as e:
            print(f"Error in time modal: {e}")
            await interaction.followup.send("❌ An error occurred.", ephemeral=True)


# MAIN VIEW

class CategoryStatsView(discord.ui.View):
    def __init__(self, cog_instance, guild: discord.Guild, category: discord.CategoryChannel,
                 start_time: datetime = None, end_time: datetime = None, days_back_equiv: int = 14,
                 display_text: str = "14 days", stats_type: str = "messages", selected_role_id: str = None,
                 using_server_default: bool = True):
        super().__init__(timeout=600)
        self.cog = cog_instance
        self.guild = guild
        self.category = category
        self.current_start_time = start_time
        self.current_end_time = end_time if end_time else datetime.utcnow()
        self.current_days_back_equiv = days_back_equiv
        self.current_display_text = display_text
        self.stats_type = stats_type
        self.selected_role_id = selected_role_id
        self.show_time_buttons = False
        self.using_server_default = using_server_default
        self._update_buttons()

    def _update_buttons(self):
        self.clear_items()

        self.add_item(StatsTypeSelectMenu(self.stats_type))

        input_role_button = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="Input Role ID",
            custom_id=f"category_input_role",
            row=1
        )
        refresh_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="🔄 Refresh",
            custom_id=f"category_stats_refresh",
            row=1
        )
        time_settings_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="⏰ Time Settings",
            custom_id=f"category_stats_time_settings",
            row=1
        )

        input_role_button.callback = self.input_role_callback
        refresh_button.callback = self.refresh_callback
        time_settings_button.callback = self.time_settings_callback

        self.add_item(input_role_button)
        self.add_item(refresh_button)
        self.add_item(time_settings_button)

        if self.show_time_buttons:
            all_time_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 999999 else discord.ButtonStyle.secondary,
                label="All Time",
                custom_id=f"category_all_time",
                row=2
            )
            all_time_button.callback = self.all_time_callback
            self.add_item(all_time_button)

            days_7_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 7 else discord.ButtonStyle.secondary,
                label="7 Days",
                custom_id=f"category_days_7",
                row=2
            )
            days_14_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 14 else discord.ButtonStyle.secondary,
                label="14 Days",
                custom_id=f"category_days_14",
                row=2
            )
            days_30_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 30 else discord.ButtonStyle.secondary,
                label="30 Days",
                custom_id=f"category_days_30",
                row=2
            )
            custom_button = discord.ui.Button(
                style=discord.ButtonStyle.success,
                label=f"Custom ({self.current_days_back_equiv}d)" if self.current_days_back_equiv not in [
                    7, 14, 30, 999999] else "Custom",
                custom_id=f"category_custom_days",
                row=2
            )

            days_7_button.callback = self.days_7_callback
            days_14_button.callback = self.days_14_callback
            days_30_button.callback = self.days_30_callback
            custom_button.callback = self.custom_days_callback

            self.add_item(days_7_button)
            self.add_item(days_14_button)
            self.add_item(days_30_button)
            self.add_item(custom_button)

    async def input_role_callback(self, interaction: discord.Interaction):
        modal = CategoryRoleIDModal(
            self.cog, interaction.message.id, self.guild, self.category, self.stats_type, self
        )
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
        modal = CategoryStatsTimeModal(
            self.cog, interaction.message.id, self.guild, self.category, self.stats_type, self
        )
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

            # Get role name from database
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
                            """, int(self.selected_role_id), self.guild.id)
                            if row:
                                role_name = row['role_name']
                    except:
                        pass

            if self.stats_type == 'messages':
                category_data = await self.cog._get_category_message_stats(
                    self.guild, self.category, self.current_start_time, self.current_end_time, self.current_days_back_equiv, self.selected_role_id
                )
                if category_data is None:
                    category_data = {
                        'total_messages': 0,
                        'channels': Counter(),
                        'users': Counter(),
                        'daily': Counter(),
                        'timestamp': time.time()
                    }
                img_bytes = await generate_category_message_stats_image(
                    self.cog.bot, self.guild, self.category, category_data, self.current_display_text, self.selected_role_id, role_name
                )
            else:
                category_data = await self.cog._get_category_voice_stats(
                    self.guild, self.category, self.current_start_time, self.current_end_time, self.current_days_back_equiv, self.selected_role_id
                )
                if category_data is None:
                    category_data = {
                        'total_seconds': 0,
                        'channels': Counter(),
                        'users': Counter(),
                        'daily': Counter(),
                        'timestamp': time.time()
                    }
                img_bytes = await generate_category_voice_stats_image(
                    self.cog.bot, self.guild, self.category, category_data, self.current_display_text, self.selected_role_id, role_name
                )

            self._update_buttons()
            file = discord.File(
                img_bytes,
                filename=f"category_{self.stats_type}_stats.png"
            )
            await interaction.edit_original_response(attachments=[file], view=self)

            sessions_dict = self.cog.active_category_sessions[self.stats_type]
            if interaction.message and interaction.message.id in sessions_dict:
                sessions_dict[interaction.message.id]['current_start_time'] = self.current_start_time
                sessions_dict[interaction.message.id]['current_end_time'] = self.current_end_time
                sessions_dict[interaction.message.id]['current_days_back_equiv'] = self.current_days_back_equiv
                sessions_dict[interaction.message.id]['current_display_text'] = self.current_display_text
                sessions_dict[interaction.message.id]['selected_role_id'] = self.selected_role_id

        except Exception as e:
            print(f"Error handling button click: {e}")
            import traceback
            traceback.print_exc()
            await interaction.followup.send("❌ An error occurred while updating the stats.", ephemeral=True)

    async def handle_time_settings(self, interaction: discord.Interaction):
        try:
            self.show_time_buttons = not self.show_time_buttons
            self._update_buttons()
            await interaction.response.edit_message(view=self)
        except Exception as e:
            print(f"Error handling time settings: {e}")
            try:
                await interaction.followup.send("❌ An error occurred while updating time settings.", ephemeral=True)
            except:
                pass


class CategoryStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_category_sessions = {
            "messages": {},
            "voice": {}
        }
        self.rate_limiter = get_rate_limiter()

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

    # PERMISSION CHECK FUNCTION
    async def check_permission(self, ctx_or_interaction, command_name: str = "category stats") -> bool:
        """Check if user has permission to use the command based on server settings"""

        # Extract user and guild based on context type
        if isinstance(ctx_or_interaction, commands.Context):
            user = ctx_or_interaction.author
            guild = ctx_or_interaction.guild
        else:
            user = ctx_or_interaction.user
            guild = ctx_or_interaction.guild

        # Users with administrator permission can always use the command
        if user.guild_permissions.administrator:
            return True

        # Get settings from Settings cog
        settings_cog = self.bot.get_cog('Settings')
        if not settings_cog:
            # If no settings cog, allow by default
            return True

        try:
            # Get guild settings
            settings = await settings_cog.get_guild_settings(guild.id)
            permission_level = settings.get('permission_level', 'Default')

            # Check based on permission level
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

            return True

        except Exception as e:
            print(f"Error checking permissions: {e}")
            return True

    # QUERY FUNCTIONS - UPDATED TO USE HOURLY AGGREGATED TABLES
    async def _get_category_message_stats(self, guild: discord.Guild, category: discord.CategoryChannel,
                                          start_time: datetime = None, end_time: datetime = None,
                                          days_back_equiv: int = 14, role_id: str = None) -> Optional[Dict[str, Any]]:
        db_cog = self.bot.get_cog('DatabaseStats')
        if not db_cog:
            print("❌ DatabaseStats cog not found")
            return None

        try:
            role_ids = None
            if role_id and role_id != "none":
                role_ids = [int(role_id)]

            if end_time is None:
                end_time = datetime.utcnow()

            # Get channel count (still uses static method)
            channel_count_data = await db_cog.q_category_channel_count(
                guild_id=guild.id,
                category_id=category.id
            )

            category_data = {
                'total_messages': 0,
                'channels': Counter(),
                'users': Counter(),
                'daily': Counter(),
            }

            # Get total messages using hourly aggregated table
            total_stats = await db_cog.q_category_total_messages(
                guild_id=guild.id,
                category_id=category.id,
                role_filter_ids=role_ids,
                start_time=start_time,
                end_time=end_time
            )

            category_data['total_messages'] = total_stats.get(
                'total_messages', 0)

            # Get top text channels using hourly aggregated table
            top_channels = await db_cog.q_category_top5_text_channels(
                guild_id=guild.id,
                category_id=category.id,
                role_filter_ids=role_ids,
                start_time=start_time,
                end_time=end_time
            )

            for channel in top_channels:
                if channel.get('message_count', 0) > 0:
                    category_data['channels'][str(
                        channel['channel_id'])] = channel['message_count']

            # Get top users by messages using hourly aggregated table
            top_users = await db_cog.q_category_top5_users_messages(
                guild_id=guild.id,
                category_id=category.id,
                role_filter_ids=role_ids,
                start_time=start_time,
                end_time=end_time
            )

            for user in top_users:
                if user.get('message_count', 0) > 0:
                    category_data['users'][str(
                        user['user_id'])] = user['message_count']

            # Get timeseries data using hourly aggregated table
            timeseries_data = await db_cog.q_category_timeseries_messages(
                guild_id=guild.id,
                category_id=category.id,
                days=[1, 5, 10, 20, 30],
                role_filter_ids=role_ids,
                start_time=start_time,
                end_time=end_time
            )

            for days_str, count in timeseries_data.items():
                days = int(days_str.replace('d', ''))
                category_data['daily'][days] = count

            category_data['timestamp'] = time.time()
            return category_data

        except Exception as e:
            print(f"❌ Error getting category message stats: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def _get_category_voice_stats(self, guild: discord.Guild, category: discord.CategoryChannel,
                                        start_time: datetime = None, end_time: datetime = None,
                                        days_back_equiv: int = 14, role_id: str = None) -> Optional[Dict[str, Any]]:
        db_cog = self.bot.get_cog('DatabaseStats')
        if not db_cog:
            print("❌ DatabaseStats cog not found")
            return None

        try:
            role_ids = None
            if role_id and role_id != "none":
                role_ids = [int(role_id)]

            if end_time is None:
                end_time = datetime.utcnow()

            category_data = {
                'total_seconds': 0,
                'channels': Counter(),
                'users': Counter(),
                'daily': Counter(),
            }

            # Get total voice using hourly aggregated table
            total_stats = await db_cog.q_category_total_voice(
                guild_id=guild.id,
                category_id=category.id,
                role_filter_ids=role_ids,
                start_time=start_time,
                end_time=end_time
            )

            category_data['total_seconds'] = total_stats.get(
                'total_seconds', 0)

            # Get top voice channels using hourly aggregated table
            top_channels = await db_cog.q_category_top5_voice_channels(
                guild_id=guild.id,
                category_id=category.id,
                role_filter_ids=role_ids,
                start_time=start_time,
                end_time=end_time
            )

            for channel in top_channels:
                if channel.get('total_seconds', 0) > 0:
                    category_data['channels'][str(
                        channel['channel_id'])] = channel['total_seconds']

            # Get top users by voice using hourly aggregated table
            top_users = await db_cog.q_category_top5_users_voice(
                guild_id=guild.id,
                category_id=category.id,
                role_filter_ids=role_ids,
                start_time=start_time,
                end_time=end_time
            )

            for user in top_users:
                if user.get('total_seconds', 0) > 0:
                    category_data['users'][str(
                        user['user_id'])] = user['total_seconds']

            # Get timeseries data using hourly aggregated table
            timeseries_data = await db_cog.q_category_timeseries_voice(
                guild_id=guild.id,
                category_id=category.id,
                days=[1, 5, 10, 20, 30],
                role_filter_ids=role_ids,
                start_time=start_time,
                end_time=end_time
            )

            for days_str, seconds in timeseries_data.items():
                days = int(days_str.replace('d', ''))
                category_data['daily'][days] = seconds

            category_data['timestamp'] = time.time()
            return category_data

        except Exception as e:
            print(f"❌ Error getting category voice stats: {e}")
            import traceback
            traceback.print_exc()
            return None

    # =========================================================
    # INTERNAL FUNCTION FOR BOTH COMMANDS
    # =========================================================
    @rate_limited(RateLimitType.MESSAGE, timeout=30.0)
    async def _handle_category_stats_command(self, ctx_or_interaction, category_id: str = None, is_interaction=False):
        """Internal function to handle category stats for both command types"""
        try:
            # Get context parameters
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

            # Check permissions
            has_permission = await self.check_permission(ctx_or_interaction)
            if not has_permission:
                settings_cog = self.bot.get_cog('Settings')
                if settings_cog:
                    settings = await settings_cog.get_guild_settings(guild.id)
                    permission_level = settings.get(
                        'permission_level', 'Default')

                    if permission_level == 'Admin':
                        embed = discord.Embed(
                            title="❌ Permission Denied",
                            description="Sorry! You need the `Administrator` permission to access this command.",
                            color=discord.Color.red()
                        )
                    elif permission_level == 'Moderator':
                        embed = discord.Embed(
                            title="❌ Permission Denied",
                            description="Sorry! You need the `Manage Server` permission to access this command.",
                            color=discord.Color.red()
                        )
                    else:
                        embed = discord.Embed(
                            title="❌ Permission Denied",
                            description="Sorry! You don't have permission to access this command.",
                            color=discord.Color.red()
                        )
                else:
                    embed = discord.Embed(
                        title="❌ Permission Denied",
                        description="Sorry! You don't have permission to access this command.",
                        color=discord.Color.red()
                    )

                if is_interaction:
                    await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    await ctx_or_interaction.send(embed=embed, delete_after=10)
                return

            # Handle category parameter
            if category_id is None:
                if is_interaction:
                    await ctx_or_interaction.response.send_message("❌ Please specify a category or category ID.", ephemeral=True)
                else:
                    await ctx_or_interaction.send("❌ Please specify a category or category ID.", delete_after=5)
                return

            # Try to find the category
            category = None
            try:
                category_id_int = int(category_id)
                category = guild.get_channel(category_id_int)

                if category is None or not isinstance(category, discord.CategoryChannel):
                    for cat in guild.categories:
                        if str(cat.id) == category_id or cat.name.lower() == category_id.lower():
                            category = cat
                            break
            except ValueError:
                for cat in guild.categories:
                    if cat.name.lower() == category_id.lower():
                        category = cat
                        break

            if category is None or not isinstance(category, discord.CategoryChannel):
                if is_interaction:
                    await ctx_or_interaction.response.send_message("❌ Category not found. Please provide a valid category ID or name.", ephemeral=True)
                else:
                    await ctx_or_interaction.send("❌ Category not found. Please provide a valid category ID or name.", delete_after=5)
                return

            if is_interaction:
                await ctx_or_interaction.response.defer()

            # Get server default time range
            start_time, end_time, display_text, days_back_equiv = await self.get_server_default_time_range(guild.id)

            stats_type = "messages"

            if stats_type == "messages":
                category_data = await self._get_category_message_stats(guild, category, start_time, end_time, days_back_equiv)
                if category_data is None:
                    category_data = {
                        'total_messages': 0,
                        'channels': Counter(),
                        'users': Counter(),
                        'daily': Counter(),
                        'timestamp': time.time()
                    }
                img_bytes = await generate_category_message_stats_image(self.bot, guild, category, category_data, display_text)
            else:
                category_data = await self._get_category_voice_stats(guild, category, start_time, end_time, days_back_equiv)
                if category_data is None:
                    category_data = {
                        'total_seconds': 0,
                        'channels': Counter(),
                        'users': Counter(),
                        'daily': Counter(),
                        'timestamp': time.time()
                    }
                img_bytes = await generate_category_voice_stats_image(self.bot, guild, category, category_data, display_text)

            view = CategoryStatsView(
                self, guild, category, start_time=start_time, end_time=end_time,
                days_back_equiv=days_back_equiv, display_text=display_text,
                stats_type=stats_type, using_server_default=True
            )

            file = discord.File(img_bytes, filename="category_stats.png")

            if is_interaction:
                msg = await send_method(file=file, view=view)
            else:
                msg = await send_method(file=file, view=view, delete_after=300)

            self.active_category_sessions[stats_type][msg.id] = {
                'guild_id': guild.id,
                'user_id': user.id,
                'category_id': category.id,
                'current_start_time': start_time,
                'current_end_time': end_time,
                'current_days_back_equiv': days_back_equiv,
                'current_display_text': display_text,
                'selected_role_id': None,
                'view': view
            }

        except Exception as e:
            print(f"Error in _handle_category_stats_command: {e}")
            import traceback
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

    # =========================================================
    # SHORTCUT COMMAND - ca
    # =========================================================
    @commands.command(name="ca")
    async def category_stats_shortcut(self, ctx: commands.Context, *, category_id: str = None):
        """Shortcut command for category stats - same as category stats"""
        await self._handle_category_stats_command(ctx, category_id, is_interaction=False)

    # =========================================================
    # CATEGORY GROUP PREFIX COMMANDS
    # =========================================================

    @commands.group(name="category", invoke_without_command=True)
    async def category_group_prefix(self, ctx: commands.Context):
        """Category statistics commands"""
        await ctx.send("Available commands:\n- `category stats <category_id>` - Show category statistics\n- `ca <category_id>` - Shortcut for category stats")

    @category_group_prefix.command(name="stats")
    async def category_stats_prefix(self, ctx: commands.Context, *, category_id: str = None):
        """Display category stats via prefix command"""
        await self._handle_category_stats_command(ctx, category_id, is_interaction=False)

    # =========================================================
    # SLASH COMMAND
    # =========================================================
    category_group = app_commands.Group(
        name="category",
        description="category related commands"
    )

    @category_group.command(
        name="stats",
        description="Get message or voice activity stats for a category."
    )
    @discord.app_commands.describe(
        category="Select a category to get stats for"
    )
    async def category_stats(self, interaction: discord.Interaction, category: discord.CategoryChannel):
        await self._handle_category_stats_command(interaction, str(category.id), is_interaction=True)


# SETUP

async def setup(bot):
    await bot.add_cog(CategoryStats(bot))
