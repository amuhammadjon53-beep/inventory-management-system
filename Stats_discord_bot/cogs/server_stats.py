import discord
from discord.ext import commands
from discord import app_commands
from datetime import timedelta, datetime, timezone
import time
import asyncio
from PIL import Image, ImageDraw, ImageFont
import io
import aiohttp
import os
from dotenv import load_dotenv
from pilmoji import Pilmoji
import traceback
from pathlib import Path
import unicodedata
from .ratelimiter import RateLimiter, RateLimitType, rate_limited, get_rate_limiter
import gc
from discord.ext import tasks

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv()


def format_time(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}m {secs}s"
    elif seconds < 86400:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"
    else:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        return f"{days}d {hours}h"


def format_message_count(count):
    count = int(count)
    if count >= 1000000:
        return f"{count/1000000:.1f}M"
    elif count >= 1000:
        return f"{count/1000:.1f}K"
    else:
        return str(count)


def draw_text_centered(draw, text, position, font, fill, max_width=None):
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = position[0] - text_width // 2
    y = position[1] - text_height // 2

    if max_width and text_width > max_width:
        while text_width > max_width and len(text) > 1:
            text = text[:-1]
            bbox = draw.textbbox((0, 0), text + "...", font=font)
            text_width = bbox[2] - bbox[0]
        text = text + "..."

    draw.text((x, y), text, fill=fill, font=font)


async def create_message_stats_image(guild, stats_data, display_text, role_id=None, role_name=None):
    template_path = BASE_DIR / "assets" / "images" / \
        "server stats messages final png.png"
    try:
        image = Image.open(template_path)
    except FileNotFoundError:
        image = Image.new('RGB', (800, 800), color='#2C2F33')

    draw = ImageDraw.Draw(image)

    # FONTS
    try:
        font_paths = [BASE_DIR / "assets" / "fonts" / "HorndonD.ttf"]
        font_loaded = False

        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    # Load HorndonD at all required sizes
                    font_horndon_8 = ImageFont.truetype(str(font_path), 8)
                    font_horndon_10 = ImageFont.truetype(str(font_path), 10)
                    font_horndon_12 = ImageFont.truetype(str(font_path), 12)
                    font_horndon_14 = ImageFont.truetype(str(font_path), 14)
                    font_horndon_16 = ImageFont.truetype(str(font_path), 16)
                    font_horndon_18 = ImageFont.truetype(str(font_path), 18)
                    font_horndon_20 = ImageFont.truetype(str(font_path), 20)
                    font_horndon_22 = ImageFont.truetype(str(font_path), 22)
                    font_horndon_24 = ImageFont.truetype(str(font_path), 24)
                    font_horndon_26 = ImageFont.truetype(str(font_path), 26)
                    font_horndon_28 = ImageFont.truetype(str(font_path), 28)
                    font_horndon_30 = ImageFont.truetype(str(font_path), 30)
                    font_horndon_32 = ImageFont.truetype(str(font_path), 32)
                    font_horndon_34 = ImageFont.truetype(str(font_path), 34)
                    font_horndon_36 = ImageFont.truetype(str(font_path), 36)
                    font_horndon_40 = ImageFont.truetype(str(font_path), 40)

                    # Assign ALL font variables to use HorndonD
                    font_small = font_horndon_16
                    font_medium = font_horndon_20
                    font_large = font_horndon_24
                    font_larger = font_horndon_30
                    font_huge = font_horndon_40
                    font_horndon_medium = font_horndon_20
                    arial_small = font_horndon_16  # Use HorndonD instead of Arial

                    font_loaded = True
                    break

                except Exception as e:
                    print(f"Error loading HorndonD font at {font_path}: {e}")
                    continue

        if not font_loaded:
            # Fallback to system fonts if HorndonD not found
            try:
                font_small = ImageFont.truetype("arial.ttf", 16)
                font_medium = ImageFont.truetype("arial.ttf", 20)
                font_large = ImageFont.truetype("arial.ttf", 24)
                font_larger = ImageFont.truetype("arial.ttf", 30)
                font_huge = ImageFont.truetype("arial.ttf", 40)
                font_horndon_medium = ImageFont.truetype("arial.ttf", 20)
                arial_small = ImageFont.truetype("arial.ttf", 16)

                # Set fallback for horndon variables
                font_horndon_8 = ImageFont.truetype("arial.ttf", 8)
                font_horndon_10 = ImageFont.truetype("arial.ttf", 10)
                font_horndon_12 = ImageFont.truetype("arial.ttf", 12)
                font_horndon_14 = ImageFont.truetype("arial.ttf", 14)
                font_horndon_16 = ImageFont.truetype("arial.ttf", 16)
                font_horndon_18 = ImageFont.truetype("arial.ttf", 18)
                font_horndon_20 = ImageFont.truetype("arial.ttf", 20)
                font_horndon_22 = ImageFont.truetype("arial.ttf", 22)
                font_horndon_24 = ImageFont.truetype("arial.ttf", 24)
                font_horndon_26 = ImageFont.truetype("arial.ttf", 26)
                font_horndon_28 = ImageFont.truetype("arial.ttf", 28)
                font_horndon_30 = ImageFont.truetype("arial.ttf", 30)
                font_horndon_32 = ImageFont.truetype("arial.ttf", 32)
                font_horndon_34 = ImageFont.truetype("arial.ttf", 34)
                font_horndon_36 = ImageFont.truetype("arial.ttf", 36)
                font_horndon_40 = ImageFont.truetype("arial.ttf", 40)
            except:
                # Ultimate fallback to default font
                font_small = ImageFont.load_default()
                font_medium = ImageFont.load_default()
                font_large = ImageFont.load_default()
                font_larger = ImageFont.load_default()
                font_huge = ImageFont.load_default()
                font_horndon_medium = ImageFont.load_default()
                arial_small = ImageFont.load_default()
                font_horndon_8 = ImageFont.load_default()
                font_horndon_10 = ImageFont.load_default()
                font_horndon_12 = ImageFont.load_default()
                font_horndon_14 = ImageFont.load_default()
                font_horndon_16 = ImageFont.load_default()
                font_horndon_18 = ImageFont.load_default()
                font_horndon_20 = ImageFont.load_default()
                font_horndon_22 = ImageFont.load_default()
                font_horndon_24 = ImageFont.load_default()
                font_horndon_26 = ImageFont.load_default()
                font_horndon_28 = ImageFont.load_default()
                font_horndon_30 = ImageFont.load_default()
                font_horndon_32 = ImageFont.load_default()
                font_horndon_34 = ImageFont.load_default()
                font_horndon_36 = ImageFont.load_default()
                font_horndon_40 = ImageFont.load_default()

    except Exception as e:
        print(f"Unexpected font error: {e}")
        # Ultimate fallback to default font for everything
        font_small = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_large = ImageFont.load_default()
        font_larger = ImageFont.load_default()
        font_huge = ImageFont.load_default()
        font_horndon_medium = ImageFont.load_default()
        arial_small = ImageFont.load_default()
        font_horndon_8 = ImageFont.load_default()
        font_horndon_10 = ImageFont.load_default()
        font_horndon_12 = ImageFont.load_default()
        font_horndon_14 = ImageFont.load_default()
        font_horndon_16 = ImageFont.load_default()
        font_horndon_18 = ImageFont.load_default()
        font_horndon_20 = ImageFont.load_default()
        font_horndon_22 = ImageFont.load_default()
        font_horndon_24 = ImageFont.load_default()
        font_horndon_26 = ImageFont.load_default()
        font_horndon_28 = ImageFont.load_default()
        font_horndon_30 = ImageFont.load_default()
        font_horndon_32 = ImageFont.load_default()
        font_horndon_34 = ImageFont.load_default()
        font_horndon_36 = ImageFont.load_default()
        font_horndon_40 = ImageFont.load_default()

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

    def fit_text_to_rectangle(text, text_center_x, text_center_y, rect_center_x, rect_center_y, rect_width, rect_height, is_channel=False, is_username=False):
        normalized_text = unicodedata.normalize('NFKD', text)
        ascii_text = normalized_text.encode('ascii', 'ignore').decode('ascii')
        text = ascii_text if ascii_text else text

        if is_username:
            font_sizes = [26, 24, 22, 20, 18, 16]
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
                if font_size <= 26:
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
                if smallest_font <= 26:
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

        if len(text) > 3:
            final_text = text[:3] + "..."
        elif text:
            final_text = text
        else:
            final_text = "-"

        bbox = draw.textbbox((0, 0), final_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        text_x = text_center_x - (text_width // 2)
        text_y = text_center_y - (text_height // 2)

        vertical_offset = 0
        if is_channel and smallest_font <= 20:
            vertical_offset += 1
        if is_channel and smallest_font <= 16:
            vertical_offset += 1
        text_y += vertical_offset

        return final_text, font, (text_x, text_y)

    text_channel_rectangles_left = [
        {"center": (70, 325), "width": 120, "height": 50},
        {"center": (70, 380), "width": 120, "height": 50},
        {"center": (70, 435), "width": 120, "height": 50}
    ]

    text_channel_rectangles_right = [
        {"center": (325, 325), "width": 120, "height": 50},
        {"center": (325, 380), "width": 120, "height": 50},
        {"center": (325, 435), "width": 120, "height": 50}
    ]

    server_name_rectangle = {"center": (150, 30), "width": 183, "height": 35}

    with Pilmoji(image) as pilmoji:
        server_name = guild.name
        normalized_server_name = unicodedata.normalize('NFKD', server_name)
        ascii_server_name = normalized_server_name.encode(
            'ascii', 'ignore').decode('ascii')
        server_name = ascii_server_name if ascii_server_name else server_name

        try:
            if guild.icon:
                icon_url = guild.icon.url
                async with aiohttp.ClientSession() as session:
                    async with session.get(icon_url) as response:
                        icon_data = await response.read()

                icon_image = Image.open(io.BytesIO(icon_data))
                icon_size = (60, 60)
                icon_image = icon_image.resize(
                    icon_size, Image.Resampling.LANCZOS).convert('RGBA')

                mask = Image.new('L', icon_size, 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.ellipse((0, 0, icon_size[0], icon_size[1]), fill=255)
                icon_image.putalpha(mask)

                icon_x = 7
                icon_y = 25 - 20

                icon_area = image.crop(
                    (icon_x, icon_y, icon_x + icon_size[0], icon_y + icon_size[1])).convert('RGBA')
                icon_with_bg = Image.new('RGBA', icon_size, (0, 0, 0, 0))
                icon_with_bg.paste(icon_image, (0, 0), icon_image)
                icon_area.paste(icon_with_bg, (0, 0), icon_with_bg)
                image.paste(icon_area.convert('RGB'), (icon_x, icon_y))
                icon_image.close()
                del icon_image
                del icon_data

                server_name_font_sizes = [
                    40, 38, 36, 34, 32, 30, 28, 26, 24, 22, 20, 18, 16]

                fitted_text = server_name
                server_name_font = None
                final_pos = None

                rect_center_x = server_name_rectangle["center"][0]
                rect_center_y = server_name_rectangle["center"][1]
                rect_width = server_name_rectangle["width"]
                rect_height = server_name_rectangle["height"]

                text_start_x = 75
                text_start_y = 25

                for font_size in server_name_font_sizes:
                    try:
                        font = ImageFont.truetype(font_paths[0], font_size) if os.path.exists(
                            font_paths[0]) else ImageFont.load_default()
                    except:
                        font = ImageFont.load_default()

                    bbox = draw.textbbox((0, 0), server_name, font=font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]

                    text_x = text_start_x
                    text_y = text_start_y - \
                        (text_height // 2)

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

                    if not check_text_against_rectangle(server_name, font, text_x, text_y,
                                                        rect_center_x, rect_center_y,
                                                        rect_width, rect_height):
                        fitted_text = server_name
                        server_name_font = font
                        final_pos = (text_x, text_y)
                        break

                if not server_name_font:
                    smallest_font = server_name_font_sizes[-1]
                    try:
                        server_name_font = ImageFont.truetype(font_paths[0], smallest_font) if os.path.exists(
                            font_paths[0]) else ImageFont.load_default()
                    except:
                        server_name_font = ImageFont.load_default()

                    rect_left = rect_center_x - (rect_width // 2)
                    rect_right = rect_center_x + (rect_width // 2)

                    truncated_text = server_name
                    for i in range(len(server_name)):

                        test_text = server_name[:len(server_name)-i] + "..."
                        bbox = draw.textbbox(
                            (0, 0), test_text, font=server_name_font)
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

                        if (text_x >= rect_left) and ((text_x + text_width) <= rect_right):
                            fitted_text = test_text
                            final_pos = (text_x, text_y)
                            break

                    if not final_pos:
                        if len(server_name) > 3:
                            fitted_text = server_name[:3] + "..."
                        elif server_name:
                            fitted_text = server_name
                        else:
                            fitted_text = "-"

                        bbox = draw.textbbox(
                            (0, 0), fitted_text, font=server_name_font)
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

                        final_pos = (text_x, text_y)

                if fitted_text and final_pos:
                    stroke_width = 1
                    for dx in [-stroke_width, 0, stroke_width]:
                        for dy in [-stroke_width, 0, stroke_width]:
                            if dx != 0 or dy != 0:
                                pilmoji.text((final_pos[0] + dx, final_pos[1] + dy),
                                             fitted_text, "black", server_name_font,
                                             emoji_position_offset=(0, 0))

                    pilmoji.text(final_pos, fitted_text, "white", server_name_font,
                                 emoji_position_offset=(0, 0))

            else:

                server_name_font_sizes = [
                    40, 38, 36, 34, 32, 30, 28, 26, 24, 22, 20, 18, 16]

                fitted_text = server_name
                server_name_font = None
                final_pos = None

                rect_center_x = server_name_rectangle["center"][0]
                rect_center_y = server_name_rectangle["center"][1]
                rect_width = server_name_rectangle["width"]
                rect_height = server_name_rectangle["height"]

                text_start_x = 75
                text_start_y = 25

                for font_size in server_name_font_sizes:
                    try:
                        font = ImageFont.truetype(font_paths[0], font_size) if os.path.exists(
                            font_paths[0]) else ImageFont.load_default()
                    except:
                        font = ImageFont.load_default()

                    bbox = draw.textbbox((0, 0), server_name, font=font)
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

                    if not check_text_against_rectangle(server_name, font, text_x, text_y,
                                                        rect_center_x, rect_center_y,
                                                        rect_width, rect_height):
                        fitted_text = server_name
                        server_name_font = font
                        final_pos = (text_x, text_y)
                        break

                if not server_name_font:
                    smallest_font = server_name_font_sizes[-1]
                    try:
                        server_name_font = ImageFont.truetype(font_paths[0], smallest_font) if os.path.exists(
                            font_paths[0]) else ImageFont.load_default()
                    except:
                        server_name_font = ImageFont.load_default()

                    rect_left = rect_center_x - (rect_width // 2)
                    rect_right = rect_center_x + (rect_width // 2)

                    truncated_text = server_name
                    for i in range(len(server_name)):

                        test_text = server_name[:len(server_name)-i] + "..."
                        bbox = draw.textbbox(
                            (0, 0), test_text, font=server_name_font)
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

                        if (text_x >= rect_left) and ((text_x + text_width) <= rect_right):
                            fitted_text = test_text
                            final_pos = (text_x, text_y)
                            break

                    if not final_pos:
                        if len(server_name) > 3:
                            fitted_text = server_name[:3] + "..."
                        elif server_name:
                            fitted_text = server_name
                        else:
                            fitted_text = "-"

                        bbox = draw.textbbox(
                            (0, 0), fitted_text, font=server_name_font)
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

                        final_pos = (text_x, text_y)

                if fitted_text and final_pos:
                    stroke_width = 1
                    for dx in [-stroke_width, 0, stroke_width]:
                        for dy in [-stroke_width, 0, stroke_width]:
                            if dx != 0 or dy != 0:
                                pilmoji.text((final_pos[0] + dx, final_pos[1] + dy),
                                             fitted_text, "black", server_name_font,
                                             emoji_position_offset=(0, 0))

                    pilmoji.text(final_pos, fitted_text, "white", server_name_font,
                                 emoji_position_offset=(0, 0))

        except Exception as e:
            print(f"Error with server icon/name: {e}")

            server_name_font_sizes = [40, 38, 36, 34,
                                      32, 30, 28, 26, 24, 22, 20, 18, 16]

            fitted_text = server_name
            server_name_font = None
            final_pos = None

            rect_center_x = server_name_rectangle["center"][0]
            rect_center_y = server_name_rectangle["center"][1]
            rect_width = server_name_rectangle["width"]
            rect_height = server_name_rectangle["height"]

            text_start_x = 75
            text_start_y = 25

            for font_size in server_name_font_sizes:
                try:
                    font = ImageFont.truetype(font_paths[0], font_size) if os.path.exists(
                        font_paths[0]) else ImageFont.load_default()
                except:
                    font = ImageFont.load_default()

                bbox = draw.textbbox((0, 0), server_name, font=font)
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

                if not check_text_against_rectangle(server_name, font, text_x, text_y,
                                                    rect_center_x, rect_center_y,
                                                    rect_width, rect_height):
                    fitted_text = server_name
                    server_name_font = font
                    final_pos = (text_x, text_y)
                    break

            if not server_name_font:
                smallest_font = server_name_font_sizes[-1]
                try:
                    server_name_font = ImageFont.truetype(font_paths[0], smallest_font) if os.path.exists(
                        font_paths[0]) else ImageFont.load_default()
                except:
                    server_name_font = ImageFont.load_default()

                rect_left = rect_center_x - (rect_width // 2)
                rect_right = rect_center_x + (rect_width // 2)

                for i in range(len(server_name)):

                    test_text = server_name[:len(server_name)-i] + "..."
                    bbox = draw.textbbox(
                        (0, 0), test_text, font=server_name_font)
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

                    if (text_x >= rect_left) and ((text_x + text_width) <= rect_right):
                        fitted_text = test_text
                        final_pos = (text_x, text_y)
                        break

                if not final_pos:
                    if len(server_name) > 3:
                        fitted_text = server_name[:3] + "..."
                    elif server_name:
                        fitted_text = server_name
                    else:
                        fitted_text = "-"

                    bbox = draw.textbbox(
                        (0, 0), fitted_text, font=server_name_font)
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

                    final_pos = (text_x, text_y)

            if fitted_text and final_pos:
                stroke_width = 1
                for dx in [-stroke_width, 0, stroke_width]:
                    for dy in [-stroke_width, 0, stroke_width]:
                        if dx != 0 or dy != 0:
                            pilmoji.text((final_pos[0] + dx, final_pos[1] + dy),
                                         fitted_text, "black", server_name_font,
                                         emoji_position_offset=(0, 0))

                pilmoji.text(final_pos, fitted_text, "white", server_name_font,
                             emoji_position_offset=(0, 0))

        current_date = datetime.now().strftime("%B %d, %Y")
        stroke_width = 1
        for dx in [-stroke_width, 0, stroke_width]:
            for dy in [-stroke_width, 0, stroke_width]:
                if dx != 0 or dy != 0:
                    draw_text_centered(draw, current_date, (605 + dx, 45 + dy),
                                       font_small, "black", max_width=150)

        draw_text_centered(draw, current_date, (605, 45),
                           font_small, "white", max_width=150)

        # Use the passed display_text
        stroke_width = 1
        for dx in [-stroke_width, 0, stroke_width]:
            for dy in [-stroke_width, 0, stroke_width]:
                if dx != 0 or dy != 0:
                    draw_text_centered(draw, display_text, (665 + dx, 420 + dy),
                                       font_small, "black", max_width=100)

        draw_text_centered(draw, display_text, (665, 420),
                           font_small, "white", max_width=100)

        # USE THE PASSED role_name INSTEAD OF DISCORD API
        role_text = role_name if role_name else "No Filter"

        stroke_width = 1
        for dx in [-stroke_width, 0, stroke_width]:
            for dy in [-stroke_width, 0, stroke_width]:
                if dx != 0 or dy != 0:
                    draw_text_centered(draw, role_text, (613 + dx, 455 + dy),
                                       font_small, "black", max_width=150)

        draw_text_centered(draw, role_text, (613, 455),
                           font_small, "white", max_width=150)

        total_messages = stats_data.get('total_messages', 0)
        total_messages_text = format_message_count(total_messages)
        stroke_width = 1
        for dx in [-stroke_width, 0, stroke_width]:
            for dy in [-stroke_width, 0, stroke_width]:
                if dx != 0 or dy != 0:
                    draw_text_centered(draw, total_messages_text, (390 + dx, 175 + dy),
                                       font_huge, "black", max_width=100)

        draw_text_centered(draw, total_messages_text, (390, 175),
                           font_huge, "white", max_width=100)

        active_users = stats_data.get('active_message_users', 0)
        active_users_text = str(active_users)
        stroke_width = 1
        for dx in [-stroke_width, 0, stroke_width]:
            for dy in [-stroke_width, 0, stroke_width]:
                if dx != 0 or dy != 0:
                    draw_text_centered(draw, active_users_text, (130 + dx, 175 + dy),
                                       font_huge, "black", max_width=100)

        draw_text_centered(draw, active_users_text, (130, 175),
                           font_huge, "white", max_width=100)

        messages_over_time = stats_data.get('messages_over_time', {})
        message_time_positions = {
            1: (675, 160),
            5: (675, 215),
            10: (675, 270),
            20: (675, 320),
            30: (675, 370)
        }

        for days, pos in message_time_positions.items():
            count = messages_over_time.get(
                days, messages_over_time.get(f'{days}d', 0))
            count_text = format_message_count(count)

            stroke_width = 1
            for dx in [-stroke_width, 0, stroke_width]:
                for dy in [-stroke_width, 0, stroke_width]:
                    if dx != 0 or dy != 0:
                        draw_text_centered(draw, count_text, (pos[0] + dx, pos[1] + dy),
                                           font_large, "black", max_width=80)

            draw_text_centered(draw, count_text, pos,
                               font_large, "white", max_width=80)

        top_users_messages = stats_data.get('top_users_messages', [])
        user_msg_positions = [(65, 325), (65, 380), (65, 435)]
        user_msg_count_positions = [(190, 325), (190, 380), (190, 435)]

        for i in range(3):
            if i < len(top_users_messages):
                user_data = top_users_messages[i]
                username = user_data.get('name', 'Unknown')
                messages = user_data.get('messages', 0)

                rect_info = text_channel_rectangles_left[i]
                fitted_text, user_font, user_pos = fit_text_to_rectangle(
                    username,
                    user_msg_positions[i][0],
                    user_msg_positions[i][1],
                    rect_info["center"][0],
                    rect_info["center"][1],
                    rect_info["width"],
                    rect_info["height"],
                    is_channel=False,
                    is_username=True
                )

                if fitted_text:
                    stroke_width = 1
                    for dx in [-stroke_width, 0, stroke_width]:
                        for dy in [-stroke_width, 0, stroke_width]:
                            if dx != 0 or dy != 0:
                                pilmoji.text((user_pos[0] + dx, user_pos[1] + dy),
                                             fitted_text, "black", user_font,
                                             emoji_position_offset=(0, 0))

                    pilmoji.text(user_pos, fitted_text, "white", user_font,
                                 emoji_position_offset=(0, 0))

                messages_text = format_message_count(messages)
                stroke_width = 1
                for dx in [-stroke_width, 0, stroke_width]:
                    for dy in [-stroke_width, 0, stroke_width]:
                        if dx != 0 or dy != 0:
                            draw_text_centered(draw, messages_text,
                                               (user_msg_count_positions[i][0] + dx,
                                                user_msg_count_positions[i][1] + dy),
                                               font_large, "black", max_width=80)

                draw_text_centered(draw, messages_text, user_msg_count_positions[i],
                                   font_large, "white", max_width=80)
            else:
                stroke_width = 1
                placeholder = "-"
                for dx in [-stroke_width, 0, stroke_width]:
                    for dy in [-stroke_width, 0, stroke_width]:
                        if dx != 0 or dy != 0:
                            draw_text_centered(draw, placeholder,
                                               (user_msg_positions[i][0] + dx,
                                                user_msg_positions[i][1] + dy),
                                               font_large, "black", max_width=120)

                draw_text_centered(draw, placeholder, user_msg_positions[i],
                                   font_large, "white", max_width=120)

                stroke_width = 1
                zero_str = "0"
                for dx in [-stroke_width, 0, stroke_width]:
                    for dy in [-stroke_width, 0, stroke_width]:
                        if dx != 0 or dy != 0:
                            draw_text_centered(draw, zero_str,
                                               (user_msg_count_positions[i][0] + dx,
                                                user_msg_count_positions[i][1] + dy),
                                               font_large, "black", max_width=80)

                draw_text_centered(draw, zero_str, user_msg_count_positions[i],
                                   font_large, "white", max_width=80)

        top_text_channels = stats_data.get('top_text_channels', [])
        text_channel_positions = [(325, 325), (325, 380), (325, 435)]
        text_channel_msg_positions = [(450, 325), (450, 380), (450, 435)]

        for i in range(3):
            text_pos = text_channel_positions[i]
            rect_info = text_channel_rectangles_right[i]

            if i < len(top_text_channels):
                channel_data = top_text_channels[i]
                channel_name = channel_data.get('name', '[deleted channel]')
                messages = channel_data.get('messages', 0)

                fitted_text, channel_font, final_pos = fit_text_to_rectangle(
                    channel_name,
                    text_pos[0],
                    text_pos[1],
                    rect_info["center"][0],
                    rect_info["center"][1],
                    rect_info["width"],
                    rect_info["height"],
                    is_channel=True
                )

                if fitted_text:
                    stroke_width = 1
                    for dx in [-stroke_width, 0, stroke_width]:
                        for dy in [-stroke_width, 0, stroke_width]:
                            if dx != 0 or dy != 0:
                                pilmoji.text((final_pos[0] + dx, final_pos[1] + dy),
                                             fitted_text, "black", channel_font,
                                             emoji_position_offset=(0, 0))

                    pilmoji.text(final_pos, fitted_text, "white", channel_font,
                                 emoji_position_offset=(0, 0))

                messages_text = format_message_count(messages)
                stroke_width = 1
                for dx in [-stroke_width, 0, stroke_width]:
                    for dy in [-stroke_width, 0, stroke_width]:
                        if dx != 0 or dy != 0:
                            draw_text_centered(draw, messages_text,
                                               (text_channel_msg_positions[i][0] + dx,
                                                text_channel_msg_positions[i][1] + dy),
                                               font_large, "black", max_width=80)

                draw_text_centered(draw, messages_text, text_channel_msg_positions[i],
                                   font_large, "white", max_width=80)
            else:
                placeholder_font = font_large
                bbox = draw.textbbox((0, 0), "-", font=placeholder_font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                placeholder_x = text_pos[0] - (text_width // 2)
                placeholder_y = text_pos[1] - (text_height // 2)

                stroke_width = 1
                for dx in [-stroke_width, 0, stroke_width]:
                    for dy in [-stroke_width, 0, stroke_width]:
                        if dx != 0 or dy != 0:
                            draw.text((placeholder_x + dx, placeholder_y + dy), "-",
                                      fill="black", font=placeholder_font)

                draw.text((placeholder_x, placeholder_y), "-",
                          fill="white", font=placeholder_font)

                stroke_width = 1
                zero_str = "0"
                for dx in [-stroke_width, 0, stroke_width]:
                    for dy in [-stroke_width, 0, stroke_width]:
                        if dx != 0 or dy != 0:
                            draw_text_centered(draw, zero_str,
                                               (text_channel_msg_positions[i][0] + dx,
                                                text_channel_msg_positions[i][1] + dy),
                                               font_large, "black", max_width=80)

                draw_text_centered(draw, zero_str, text_channel_msg_positions[i],
                                   font_large, "white", max_width=80)
    gc.collect()

    return image


async def create_voice_stats_image(guild, stats_data, display_text, role_id=None, role_name=None):
    template_path = BASE_DIR / "assets" / \
        "images" / "server stats voice final png.png"
    try:
        image = Image.open(template_path)
    except FileNotFoundError:
        image = Image.new('RGB', (800, 800), color='#2C2F33')

    draw = ImageDraw.Draw(image)

    # FONTS
    try:
        font_paths = [BASE_DIR / "assets" / "fonts" / "HorndonD.ttf"]
        font_loaded = False

        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    # Load HorndonD at all required sizes
                    font_horndon_8 = ImageFont.truetype(str(font_path), 8)
                    font_horndon_10 = ImageFont.truetype(str(font_path), 10)
                    font_horndon_12 = ImageFont.truetype(str(font_path), 12)
                    font_horndon_14 = ImageFont.truetype(str(font_path), 14)
                    font_horndon_16 = ImageFont.truetype(str(font_path), 16)
                    font_horndon_18 = ImageFont.truetype(str(font_path), 18)
                    font_horndon_20 = ImageFont.truetype(str(font_path), 20)
                    font_horndon_22 = ImageFont.truetype(str(font_path), 22)
                    font_horndon_24 = ImageFont.truetype(str(font_path), 24)
                    font_horndon_26 = ImageFont.truetype(str(font_path), 26)
                    font_horndon_28 = ImageFont.truetype(str(font_path), 28)
                    font_horndon_30 = ImageFont.truetype(str(font_path), 30)
                    font_horndon_32 = ImageFont.truetype(str(font_path), 32)
                    font_horndon_34 = ImageFont.truetype(str(font_path), 34)
                    font_horndon_36 = ImageFont.truetype(str(font_path), 36)
                    font_horndon_40 = ImageFont.truetype(str(font_path), 40)

                    # Assign ALL font variables to use HorndonD
                    font_small = font_horndon_16
                    font_medium = font_horndon_20
                    font_large = font_horndon_24
                    font_larger = font_horndon_30
                    font_huge = font_horndon_40
                    font_horndon_medium = font_horndon_20
                    arial_small = font_horndon_16  # Use HorndonD instead of Arial

                    font_loaded = True
                    break

                except Exception as e:
                    print(f"Error loading HorndonD font at {font_path}: {e}")
                    continue

        if not font_loaded:
            # Fallback to system fonts if HorndonD not found
            try:
                font_small = ImageFont.truetype("arial.ttf", 16)
                font_medium = ImageFont.truetype("arial.ttf", 20)
                font_large = ImageFont.truetype("arial.ttf", 24)
                font_larger = ImageFont.truetype("arial.ttf", 30)
                font_huge = ImageFont.truetype("arial.ttf", 40)
                font_horndon_medium = ImageFont.truetype("arial.ttf", 20)
                arial_small = ImageFont.truetype("arial.ttf", 16)

                # Set fallback for horndon variables
                font_horndon_8 = ImageFont.truetype("arial.ttf", 8)
                font_horndon_10 = ImageFont.truetype("arial.ttf", 10)
                font_horndon_12 = ImageFont.truetype("arial.ttf", 12)
                font_horndon_14 = ImageFont.truetype("arial.ttf", 14)
                font_horndon_16 = ImageFont.truetype("arial.ttf", 16)
                font_horndon_18 = ImageFont.truetype("arial.ttf", 18)
                font_horndon_20 = ImageFont.truetype("arial.ttf", 20)
                font_horndon_22 = ImageFont.truetype("arial.ttf", 22)
                font_horndon_24 = ImageFont.truetype("arial.ttf", 24)
                font_horndon_26 = ImageFont.truetype("arial.ttf", 26)
                font_horndon_28 = ImageFont.truetype("arial.ttf", 28)
                font_horndon_30 = ImageFont.truetype("arial.ttf", 30)
                font_horndon_32 = ImageFont.truetype("arial.ttf", 32)
                font_horndon_34 = ImageFont.truetype("arial.ttf", 34)
                font_horndon_36 = ImageFont.truetype("arial.ttf", 36)
                font_horndon_40 = ImageFont.truetype("arial.ttf", 40)
            except:
                # Ultimate fallback to default font
                font_small = ImageFont.load_default()
                font_medium = ImageFont.load_default()
                font_large = ImageFont.load_default()
                font_larger = ImageFont.load_default()
                font_huge = ImageFont.load_default()
                font_horndon_medium = ImageFont.load_default()
                arial_small = ImageFont.load_default()
                font_horndon_8 = ImageFont.load_default()
                font_horndon_10 = ImageFont.load_default()
                font_horndon_12 = ImageFont.load_default()
                font_horndon_14 = ImageFont.load_default()
                font_horndon_16 = ImageFont.load_default()
                font_horndon_18 = ImageFont.load_default()
                font_horndon_20 = ImageFont.load_default()
                font_horndon_22 = ImageFont.load_default()
                font_horndon_24 = ImageFont.load_default()
                font_horndon_26 = ImageFont.load_default()
                font_horndon_28 = ImageFont.load_default()
                font_horndon_30 = ImageFont.load_default()
                font_horndon_32 = ImageFont.load_default()
                font_horndon_34 = ImageFont.load_default()
                font_horndon_36 = ImageFont.load_default()
                font_horndon_40 = ImageFont.load_default()

    except Exception as e:
        print(f"Unexpected font error: {e}")
        # Ultimate fallback to default font for everything
        font_small = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_large = ImageFont.load_default()
        font_larger = ImageFont.load_default()
        font_huge = ImageFont.load_default()
        font_horndon_medium = ImageFont.load_default()
        arial_small = ImageFont.load_default()
        font_horndon_8 = ImageFont.load_default()
        font_horndon_10 = ImageFont.load_default()
        font_horndon_12 = ImageFont.load_default()
        font_horndon_14 = ImageFont.load_default()
        font_horndon_16 = ImageFont.load_default()
        font_horndon_18 = ImageFont.load_default()
        font_horndon_20 = ImageFont.load_default()
        font_horndon_22 = ImageFont.load_default()
        font_horndon_24 = ImageFont.load_default()
        font_horndon_26 = ImageFont.load_default()
        font_horndon_28 = ImageFont.load_default()
        font_horndon_30 = ImageFont.load_default()
        font_horndon_32 = ImageFont.load_default()
        font_horndon_34 = ImageFont.load_default()
        font_horndon_36 = ImageFont.load_default()
        font_horndon_40 = ImageFont.load_default()

    def format_number_with_suffix(num):
        """Format a number with K, M suffix (e.g., 1300 -> 1.3K, 1100000 -> 1.1M)"""
        num = int(num)
        if num >= 1000000:
            return f"{num/1000000:.1f}M"
        elif num >= 1000:
            return f"{num/1000:.1f}K"
        else:
            return str(num)

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

    def fit_text_to_rectangle(text, text_center_x, text_center_y, rect_center_x, rect_center_y, rect_width, rect_height, is_channel=False, is_username=False):
        normalized_text = unicodedata.normalize('NFKD', text)
        ascii_text = normalized_text.encode('ascii', 'ignore').decode('ascii')
        text = ascii_text if ascii_text else text

        if is_username:
            font_sizes = [26, 24, 22, 20, 18, 16]
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
                if font_size <= 26:
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
                if smallest_font <= 26:
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

        if len(text) > 3:
            final_text = text[:3] + "..."
        elif text:
            final_text = text
        else:
            final_text = "-"

        bbox = draw.textbbox((0, 0), final_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        text_x = text_center_x - (text_width // 2)
        text_y = text_center_y - (text_height // 2)

        vertical_offset = 0
        if is_channel and smallest_font <= 20:
            vertical_offset += 1
        if is_channel and smallest_font <= 16:
            vertical_offset += 1
        text_y += vertical_offset

        return final_text, font, (text_x, text_y)

    text_channel_rectangles_left = [
        {"center": (70, 325), "width": 120, "height": 50},
        {"center": (70, 380), "width": 120, "height": 50},
        {"center": (70, 435), "width": 120, "height": 50}
    ]

    text_channel_rectangles_right = [
        {"center": (325, 325), "width": 120, "height": 50},
        {"center": (325, 380), "width": 120, "height": 50},
        {"center": (325, 435), "width": 120, "height": 50}
    ]

    server_name_rectangle = {"center": (150, 30), "width": 183, "height": 35}

    with Pilmoji(image) as pilmoji:
        server_name = guild.name
        normalized_server_name = unicodedata.normalize('NFKD', server_name)
        ascii_server_name = normalized_server_name.encode(
            'ascii', 'ignore').decode('ascii')
        server_name = ascii_server_name if ascii_server_name else server_name

        try:
            if guild.icon:
                icon_url = guild.icon.url
                async with aiohttp.ClientSession() as session:
                    async with session.get(icon_url) as response:
                        icon_data = await response.read()

                icon_image = Image.open(io.BytesIO(icon_data))
                icon_size = (60, 60)
                icon_image = icon_image.resize(
                    icon_size, Image.Resampling.LANCZOS).convert('RGBA')

                mask = Image.new('L', icon_size, 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.ellipse((0, 0, icon_size[0], icon_size[1]), fill=255)
                icon_image.putalpha(mask)

                icon_x = 7
                icon_y = 25 - 20

                icon_area = image.crop(
                    (icon_x, icon_y, icon_x + icon_size[0], icon_y + icon_size[1])).convert('RGBA')
                icon_with_bg = Image.new('RGBA', icon_size, (0, 0, 0, 0))
                icon_with_bg.paste(icon_image, (0, 0), icon_image)
                icon_area.paste(icon_with_bg, (0, 0), icon_with_bg)
                image.paste(icon_area.convert('RGB'), (icon_x, icon_y))
                icon_image.close()
                del icon_image
                del icon_data

                server_name_font_sizes = [
                    40, 38, 36, 34, 32, 30, 28, 26, 24, 22, 20, 18, 16]

                fitted_text = server_name
                server_name_font = None
                final_pos = None

                rect_center_x = server_name_rectangle["center"][0]
                rect_center_y = server_name_rectangle["center"][1]
                rect_width = server_name_rectangle["width"]
                rect_height = server_name_rectangle["height"]

                text_start_x = 75
                text_start_y = 25

                for font_size in server_name_font_sizes:
                    try:
                        font = ImageFont.truetype(font_paths[0], font_size) if os.path.exists(
                            font_paths[0]) else ImageFont.load_default()
                    except:
                        font = ImageFont.load_default()

                    bbox = draw.textbbox((0, 0), server_name, font=font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]

                    text_x = text_start_x
                    text_y = text_start_y - \
                        (text_height // 2)

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

                    if not check_text_against_rectangle(server_name, font, text_x, text_y,
                                                        rect_center_x, rect_center_y,
                                                        rect_width, rect_height):
                        fitted_text = server_name
                        server_name_font = font
                        final_pos = (text_x, text_y)
                        break

                if not server_name_font:
                    smallest_font = server_name_font_sizes[-1]
                    try:
                        server_name_font = ImageFont.truetype(font_paths[0], smallest_font) if os.path.exists(
                            font_paths[0]) else ImageFont.load_default()
                    except:
                        server_name_font = ImageFont.load_default()

                    rect_left = rect_center_x - (rect_width // 2)
                    rect_right = rect_center_x + (rect_width // 2)

                    truncated_text = server_name
                    for i in range(len(server_name)):

                        test_text = server_name[:len(server_name)-i] + "..."
                        bbox = draw.textbbox(
                            (0, 0), test_text, font=server_name_font)
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

                        if (text_x >= rect_left) and ((text_x + text_width) <= rect_right):
                            fitted_text = test_text
                            final_pos = (text_x, text_y)
                            break

                    if not final_pos:
                        if len(server_name) > 3:
                            fitted_text = server_name[:3] + "..."
                        elif server_name:
                            fitted_text = server_name
                        else:
                            fitted_text = "-"

                        bbox = draw.textbbox(
                            (0, 0), fitted_text, font=server_name_font)
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

                        final_pos = (text_x, text_y)

                if fitted_text and final_pos:
                    stroke_width = 1
                    for dx in [-stroke_width, 0, stroke_width]:
                        for dy in [-stroke_width, 0, stroke_width]:
                            if dx != 0 or dy != 0:
                                pilmoji.text((final_pos[0] + dx, final_pos[1] + dy),
                                             fitted_text, "black", server_name_font,
                                             emoji_position_offset=(0, 0))

                    pilmoji.text(final_pos, fitted_text, "white", server_name_font,
                                 emoji_position_offset=(0, 0))

            else:

                server_name_font_sizes = [
                    40, 38, 36, 34, 32, 30, 28, 26, 24, 22, 20, 18, 16]

                fitted_text = server_name
                server_name_font = None
                final_pos = None

                rect_center_x = server_name_rectangle["center"][0]
                rect_center_y = server_name_rectangle["center"][1]
                rect_width = server_name_rectangle["width"]
                rect_height = server_name_rectangle["height"]

                text_start_x = 75
                text_start_y = 25

                for font_size in server_name_font_sizes:
                    try:
                        font = ImageFont.truetype(font_paths[0], font_size) if os.path.exists(
                            font_paths[0]) else ImageFont.load_default()
                    except:
                        font = ImageFont.load_default()

                    bbox = draw.textbbox((0, 0), server_name, font=font)
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

                    if not check_text_against_rectangle(server_name, font, text_x, text_y,
                                                        rect_center_x, rect_center_y,
                                                        rect_width, rect_height):
                        fitted_text = server_name
                        server_name_font = font
                        final_pos = (text_x, text_y)
                        break

                if not server_name_font:
                    smallest_font = server_name_font_sizes[-1]
                    try:
                        server_name_font = ImageFont.truetype(font_paths[0], smallest_font) if os.path.exists(
                            font_paths[0]) else ImageFont.load_default()
                    except:
                        server_name_font = ImageFont.load_default()

                    rect_left = rect_center_x - (rect_width // 2)
                    rect_right = rect_center_x + (rect_width // 2)

                    truncated_text = server_name
                    for i in range(len(server_name)):

                        test_text = server_name[:len(server_name)-i] + "..."
                        bbox = draw.textbbox(
                            (0, 0), test_text, font=server_name_font)
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

                        if (text_x >= rect_left) and ((text_x + text_width) <= rect_right):
                            fitted_text = test_text
                            final_pos = (text_x, text_y)
                            break

                    if not final_pos:
                        if len(server_name) > 3:
                            fitted_text = server_name[:3] + "..."
                        elif server_name:
                            fitted_text = server_name
                        else:
                            fitted_text = "-"

                        bbox = draw.textbbox(
                            (0, 0), fitted_text, font=server_name_font)
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

                        final_pos = (text_x, text_y)

                if fitted_text and final_pos:
                    stroke_width = 1
                    for dx in [-stroke_width, 0, stroke_width]:
                        for dy in [-stroke_width, 0, stroke_width]:
                            if dx != 0 or dy != 0:
                                pilmoji.text((final_pos[0] + dx, final_pos[1] + dy),
                                             fitted_text, "black", server_name_font,
                                             emoji_position_offset=(0, 0))

                    pilmoji.text(final_pos, fitted_text, "white", server_name_font,
                                 emoji_position_offset=(0, 0))

        except Exception as e:
            print(f"Error with server icon/name: {e}")

            server_name_font_sizes = [40, 38, 36, 34,
                                      32, 30, 28, 26, 24, 22, 20, 18, 16]

            fitted_text = server_name
            server_name_font = None
            final_pos = None

            rect_center_x = server_name_rectangle["center"][0]
            rect_center_y = server_name_rectangle["center"][1]
            rect_width = server_name_rectangle["width"]
            rect_height = server_name_rectangle["height"]

            text_start_x = 75
            text_start_y = 25

            for font_size in server_name_font_sizes:
                try:
                    font = ImageFont.truetype(font_paths[0], font_size) if os.path.exists(
                        font_paths[0]) else ImageFont.load_default()
                except:
                    font = ImageFont.load_default()

                bbox = draw.textbbox((0, 0), server_name, font=font)
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

                if not check_text_against_rectangle(server_name, font, text_x, text_y,
                                                    rect_center_x, rect_center_y,
                                                    rect_width, rect_height):
                    fitted_text = server_name
                    server_name_font = font
                    final_pos = (text_x, text_y)
                    break

            if not server_name_font:
                smallest_font = server_name_font_sizes[-1]
                try:
                    server_name_font = ImageFont.truetype(font_paths[0], smallest_font) if os.path.exists(
                        font_paths[0]) else ImageFont.load_default()
                except:
                    server_name_font = ImageFont.load_default()

                rect_left = rect_center_x - (rect_width // 2)
                rect_right = rect_center_x + (rect_width // 2)

                for i in range(len(server_name)):

                    test_text = server_name[:len(server_name)-i] + "..."
                    bbox = draw.textbbox(
                        (0, 0), test_text, font=server_name_font)
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

                    if (text_x >= rect_left) and ((text_x + text_width) <= rect_right):
                        fitted_text = test_text
                        final_pos = (text_x, text_y)
                        break

                if not final_pos:
                    if len(server_name) > 3:
                        fitted_text = server_name[:3] + "..."
                    elif server_name:
                        fitted_text = server_name
                    else:
                        fitted_text = "-"

                    bbox = draw.textbbox(
                        (0, 0), fitted_text, font=server_name_font)
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

                    final_pos = (text_x, text_y)

            if fitted_text and final_pos:
                stroke_width = 1
                for dx in [-stroke_width, 0, stroke_width]:
                    for dy in [-stroke_width, 0, stroke_width]:
                        if dx != 0 or dy != 0:
                            pilmoji.text((final_pos[0] + dx, final_pos[1] + dy),
                                         fitted_text, "black", server_name_font,
                                         emoji_position_offset=(0, 0))

                pilmoji.text(final_pos, fitted_text, "white", server_name_font,
                             emoji_position_offset=(0, 0))

        current_date = datetime.now().strftime("%B %d, %Y")
        stroke_width = 1
        for dx in [-stroke_width, 0, stroke_width]:
            for dy in [-stroke_width, 0, stroke_width]:
                if dx != 0 or dy != 0:
                    draw_text_centered(draw, current_date, (605 + dx, 45 + dy),
                                       font_small, "black")

        draw_text_centered(draw, current_date, (605, 45),
                           font_small, "white")

        # Use the passed display_text
        stroke_width = 1
        for dx in [-stroke_width, 0, stroke_width]:
            for dy in [-stroke_width, 0, stroke_width]:
                if dx != 0 or dy != 0:
                    draw_text_centered(draw, display_text, (665 + dx, 420 + dy),
                                       font_small, "black")

        draw_text_centered(draw, display_text, (665, 420),
                           font_small, "white")

        # USE THE PASSED role_name INSTEAD OF DISCORD API
        role_text = role_name if role_name else "No Filter"

        stroke_width = 1
        for dx in [-stroke_width, 0, stroke_width]:
            for dy in [-stroke_width, 0, stroke_width]:
                if dx != 0 or dy != 0:
                    draw_text_centered(draw, role_text, (613 + dx, 455 + dy),
                                       font_small, "black")

        draw_text_centered(draw, role_text, (613, 455),
                           font_small, "white")

        total_seconds = stats_data.get('total_seconds', 0)
        total_voice_text = format_time(total_seconds)
        stroke_width = 1
        for dx in [-stroke_width, 0, stroke_width]:
            for dy in [-stroke_width, 0, stroke_width]:
                if dx != 0 or dy != 0:
                    draw_text_centered(draw, total_voice_text, (390 + dx, 175 + dy),
                                       font_huge, "black")

        draw_text_centered(draw, total_voice_text, (390, 175),
                           font_huge, "white")

        # Format active users with K/M suffix
        active_users = stats_data.get('active_voice_users', 0)
        active_users_text = format_number_with_suffix(active_users)
        stroke_width = 1
        for dx in [-stroke_width, 0, stroke_width]:
            for dy in [-stroke_width, 0, stroke_width]:
                if dx != 0 or dy != 0:
                    draw_text_centered(draw, active_users_text, (130 + dx, 175 + dy),
                                       font_huge, "black")

        draw_text_centered(draw, active_users_text, (130, 175),
                           font_huge, "white")

        voice_over_time = stats_data.get('voice_over_time', {})
        voice_time_positions = {
            1: (675, 160),
            5: (675, 215),
            10: (675, 270),
            20: (675, 320),
            30: (675, 370)
        }

        for days, pos in voice_time_positions.items():
            seconds = voice_over_time.get(
                days, voice_over_time.get(f'{days}d', 0))
            voice_time_text = format_time(seconds)

            stroke_width = 1
            for dx in [-stroke_width, 0, stroke_width]:
                for dy in [-stroke_width, 0, stroke_width]:
                    if dx != 0 or dy != 0:
                        draw_text_centered(draw, voice_time_text, (pos[0] + dx, pos[1] + dy),
                                           font_large, "black")

            draw_text_centered(draw, voice_time_text, pos,
                               font_large, "white")

        top_users_voice = stats_data.get('top_users_voice', [])
        user_voice_positions = [(65, 325), (65, 380), (65, 435)]
        user_voice_time_positions = [(190, 325), (190, 380), (190, 435)]

        for i in range(3):
            if i < len(top_users_voice):
                user_data = top_users_voice[i]
                username = user_data.get('name', 'Unknown')
                voice_time = user_data.get('voice_time', 0)

                rect_info = text_channel_rectangles_left[i]
                fitted_text, user_font, user_pos = fit_text_to_rectangle(
                    username,
                    user_voice_positions[i][0],
                    user_voice_positions[i][1],
                    rect_info["center"][0],
                    rect_info["center"][1],
                    rect_info["width"],
                    rect_info["height"],
                    is_channel=False,
                    is_username=True
                )

                if fitted_text:
                    stroke_width = 1
                    for dx in [-stroke_width, 0, stroke_width]:
                        for dy in [-stroke_width, 0, stroke_width]:
                            if dx != 0 or dy != 0:
                                pilmoji.text((user_pos[0] + dx, user_pos[1] + dy),
                                             fitted_text, "black", user_font,
                                             emoji_position_offset=(0, 0))

                    pilmoji.text(user_pos, fitted_text, "white", user_font,
                                 emoji_position_offset=(0, 0))

                voice_time_text = format_time(voice_time)
                stroke_width = 1
                for dx in [-stroke_width, 0, stroke_width]:
                    for dy in [-stroke_width, 0, stroke_width]:
                        if dx != 0 or dy != 0:
                            draw_text_centered(draw, voice_time_text,
                                               (user_voice_time_positions[i][0] + dx,
                                                user_voice_time_positions[i][1] + dy),
                                               font_large, "black")

                draw_text_centered(draw, voice_time_text, user_voice_time_positions[i],
                                   font_large, "white")
            else:
                stroke_width = 1
                placeholder = "-"
                for dx in [-stroke_width, 0, stroke_width]:
                    for dy in [-stroke_width, 0, stroke_width]:
                        if dx != 0 or dy != 0:
                            draw_text_centered(draw, placeholder,
                                               (user_voice_positions[i][0] + dx,
                                                user_voice_positions[i][1] + dy),
                                               font_large, "black")

                draw_text_centered(draw, placeholder, user_voice_positions[i],
                                   font_large, "white")

                stroke_width = 1
                zero_str = "0s"
                for dx in [-stroke_width, 0, stroke_width]:
                    for dy in [-stroke_width, 0, stroke_width]:
                        if dx != 0 or dy != 0:
                            draw_text_centered(draw, zero_str,
                                               (user_voice_time_positions[i][0] + dx,
                                                user_voice_time_positions[i][1] + dy),
                                               font_large, "black")

                draw_text_centered(draw, zero_str, user_voice_time_positions[i],
                                   font_large, "white")

        top_voice_channels = stats_data.get('top_voice_channels', [])
        voice_channel_positions = [(325, 325), (325, 380), (325, 435)]
        voice_channel_time_positions = [(450, 325), (450, 380), (450, 435)]

        for i in range(3):
            text_pos = voice_channel_positions[i]
            rect_info = text_channel_rectangles_right[i]

            if i < len(top_voice_channels):
                channel_data = top_voice_channels[i]
                channel_name = channel_data.get('name', '[deleted channel]')
                voice_time = channel_data.get('voice_time', 0)

                fitted_text, channel_font, final_pos = fit_text_to_rectangle(
                    channel_name,
                    text_pos[0],
                    text_pos[1],
                    rect_info["center"][0],
                    rect_info["center"][1],
                    rect_info["width"],
                    rect_info["height"],
                    is_channel=True
                )

                if fitted_text:
                    stroke_width = 1
                    for dx in [-stroke_width, 0, stroke_width]:
                        for dy in [-stroke_width, 0, stroke_width]:
                            if dx != 0 or dy != 0:
                                pilmoji.text((final_pos[0] + dx, final_pos[1] + dy),
                                             fitted_text, "black", channel_font,
                                             emoji_position_offset=(0, 0))

                    pilmoji.text(final_pos, fitted_text, "white", channel_font,
                                 emoji_position_offset=(0, 0))

                time_text = format_time(voice_time)
                stroke_width = 1
                for dx in [-stroke_width, 0, stroke_width]:
                    for dy in [-stroke_width, 0, stroke_width]:
                        if dx != 0 or dy != 0:
                            draw_text_centered(draw, time_text,
                                               (voice_channel_time_positions[i][0] + dx,
                                                voice_channel_time_positions[i][1] + dy),
                                               font_large, "black")

                draw_text_centered(draw, time_text, voice_channel_time_positions[i],
                                   font_large, "white")
            else:
                placeholder_font = font_large
                bbox = draw.textbbox((0, 0), "-", font=placeholder_font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                placeholder_x = text_pos[0] - (text_width // 2)
                placeholder_y = text_pos[1] - (text_height // 2)

                stroke_width = 1
                for dx in [-stroke_width, 0, stroke_width]:
                    for dy in [-stroke_width, 0, stroke_width]:
                        if dx != 0 or dy != 0:
                            draw.text((placeholder_x + dx, placeholder_y + dy), "-",
                                      fill="black", font=placeholder_font)

                draw.text((placeholder_x, placeholder_y), "-",
                          fill="white", font=placeholder_font)

                stroke_width = 1
                zero_str = "0s"
                for dx in [-stroke_width, 0, stroke_width]:
                    for dy in [-stroke_width, 0, stroke_width]:
                        if dx != 0 or dy != 0:
                            draw_text_centered(draw, zero_str,
                                               (voice_channel_time_positions[i][0] + dx,
                                                voice_channel_time_positions[i][1] + dy),
                                               font_large, "black")

                draw_text_centered(draw, zero_str, voice_channel_time_positions[i],
                                   font_large, "white")
    gc.collect()

    return image


class ServerRoleModal(discord.ui.Modal, title='Input Role ID'):
    def __init__(self, cog_instance, original_message_id, guild, view):
        super().__init__(timeout=300)
        self.cog = cog_instance
        self.original_message_id = original_message_id
        self.guild = guild
        self.view = view

    role_id = discord.ui.TextInput(
        label='Enter Role ID',
        placeholder='e.g., 123456789012345678',
        min_length=1,
        max_length=20,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            role_id_str = self.role_id.value.strip()

            try:
                role_id_int = int(role_id_str)
            except ValueError:
                embed = discord.Embed(
                    title="❌ Invalid Role ID",
                    description="Sorry! The role ID you inputted is not valid, please try again.",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            # Get role name from database instead of Discord API
            role_name = None
            db_cog = self.cog._get_db_cog()
            if db_cog and hasattr(db_cog, 'get_role_name_from_db'):
                role_name = await db_cog.get_role_name_from_db(self.guild.id, role_id_int)

            if not role_name:
                embed = discord.Embed(
                    title="❌ Role Not Found",
                    description="Sorry! The role ID you inputted is not valid, please try again.",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            await interaction.response.defer()

            if self.view:
                self.view.selected_role_id = role_id_str
                self.view.using_server_default = False
                stats_data = await self.cog.get_server_stats(
                    self.guild.id, self.view.current_days, self.view.selected_role_id, self.view.current_stat_type
                )
                if stats_data:
                    # Use view's stored display_text
                    if self.view.current_stat_type == "message":
                        image_stats_data = await self.cog._convert_to_message_format_async(
                            stats_data, self.guild)
                        image = await create_message_stats_image(self.guild, image_stats_data, self.view.current_display_text, self.view.selected_role_id, role_name)
                    else:
                        image_stats_data = await self.cog._convert_to_voice_format_async(
                            stats_data, self.guild)
                        image = await create_voice_stats_image(self.guild, image_stats_data, self.view.current_display_text, self.view.selected_role_id, role_name)

                    img_bytes = io.BytesIO()
                    image.save(img_bytes, format='PNG')
                    img_bytes.seek(0)

                    file = discord.File(img_bytes, filename='server_stats.png')
                    self.view._update_buttons()
                    await interaction.edit_original_response(attachments=[file], view=self.view)
                else:
                    await interaction.edit_original_response(content="❌ Error generating stats image", view=self.view)

        except Exception as e:
            print(f"Error in role modal submit: {e}")
            traceback.print_exc()
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while processing your request.",
                color=discord.Color.red()
            )
            try:
                await interaction.response.send_message(embed=embed, ephemeral=True)
            except:
                try:
                    await interaction.followup.send(embed=embed, ephemeral=True)
                except:
                    pass


class ServerTimeModal(discord.ui.Modal, title='Custom Time Period'):
    def __init__(self, cog_instance, original_message_id, guild, view):
        super().__init__(timeout=300)
        self.cog = cog_instance
        self.original_message_id = original_message_id
        self.guild = guild
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

            if self.view:
                self.view.current_days = days
                # Update display text
                self.view.current_display_text = f"{days} days"
                self.view.show_time_buttons = False
                self.view.using_server_default = False
                self.view._update_buttons()

                # Get role name from database if a role is selected
                role_name = None
                if self.view.selected_role_id and self.view.selected_role_id != "none":
                    db_cog = self.cog._get_db_cog()
                    if db_cog and hasattr(db_cog, 'get_role_name_from_db'):
                        role_name = await db_cog.get_role_name_from_db(self.guild.id, int(self.view.selected_role_id))

                stats_data = await self.cog.get_server_stats(self.guild.id, days, self.view.selected_role_id, self.view.current_stat_type)
                if stats_data:
                    if self.view.current_stat_type == "message":
                        image_stats_data = await self.cog._convert_to_message_format_async(
                            stats_data, self.guild)
                        image = await create_message_stats_image(self.guild, image_stats_data, self.view.current_display_text, self.view.selected_role_id, role_name)
                    else:
                        image_stats_data = await self.cog._convert_to_voice_format_async(
                            stats_data, self.guild)
                        image = await create_voice_stats_image(self.guild, image_stats_data, self.view.current_display_text, self.view.selected_role_id, role_name)

                    img_bytes = io.BytesIO()
                    image.save(img_bytes, format='PNG')
                    img_bytes.seek(0)

                    file = discord.File(img_bytes, filename='server_stats.png')
                    await interaction.edit_original_response(attachments=[file], view=self.view)
                else:
                    await interaction.edit_original_response(content="❌ Error generating stats image", view=self.view)

        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number.", ephemeral=True)
        except Exception as e:
            print(f"Error in server modal submit: {e}")
            try:
                await interaction.edit_original_response(content="❌ An error occurred while updating stats.", view=None)
            except:
                await interaction.response.send_message("❌ An error occurred while updating stats.", ephemeral=True)


class ServerStatsView(discord.ui.View):
    def __init__(self, cog_instance, guild: discord.Guild, days_back: int, display_text: str, start_time: datetime = None, end_time: datetime = None, days_back_equiv: int = None, selected_role_id: str = None, stat_type: str = "message", using_server_default: bool = True):
        super().__init__(timeout=600)
        self.cog = cog_instance
        self.guild = guild
        self.current_days = days_back  # Keep for backward compatibility
        self.current_display_text = display_text
        self.current_start_time = start_time
        self.current_end_time = end_time
        self.current_days_back_equiv = days_back_equiv if days_back_equiv is not None else days_back
        self.selected_role_id = selected_role_id
        self.current_stat_type = stat_type
        self.show_time_buttons = False
        self.using_server_default = using_server_default
        self._update_buttons()

    def _update_buttons(self):
        self.clear_items()

        stat_type_select = discord.ui.Select(
            placeholder=f"Select Stats Type: {self.current_stat_type.capitalize()}",
            options=[
                discord.SelectOption(
                    label="Message Stats", value="message", description="View message statistics"),
                discord.SelectOption(
                    label="Voice Activity", value="voice", description="View voice activity statistics")
            ],
            custom_id="stat_type_select",
            row=0
        )
        stat_type_select.callback = self.stat_type_callback
        self.add_item(stat_type_select)

        role_button = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label="Input Role Id",
            custom_id="server_input_role",
            row=1
        )
        role_button.callback = self.input_role_callback
        self.add_item(role_button)

        refresh_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="🔄 Refresh",
            custom_id="server_refresh",
            row=1
        )
        refresh_button.callback = self.refresh_callback
        self.add_item(refresh_button)

        time_settings_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="⏰ Time Settings" if not self.show_time_buttons else "⏰ Hide Settings",
            custom_id="server_time_settings",
            row=2
        )
        time_settings_button.callback = self.time_settings_callback
        self.add_item(time_settings_button)

        if self.show_time_buttons:
            all_time_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 999999 else discord.ButtonStyle.secondary,
                label="All Time",
                custom_id="server_all_time",
                row=3
            )
            all_time_button.callback = self.all_time_callback
            self.add_item(all_time_button)

            days_7_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 7 else discord.ButtonStyle.secondary,
                label="7 Days",
                custom_id="server_days_7",
                row=3
            )
            days_7_button.callback = self.days_7_callback
            self.add_item(days_7_button)

            days_14_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 14 else discord.ButtonStyle.secondary,
                label="14 Days",
                custom_id="server_days_14",
                row=3
            )
            days_14_button.callback = self.days_14_callback
            self.add_item(days_14_button)

            days_30_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 30 else discord.ButtonStyle.secondary,
                label="30 Days",
                custom_id="server_days_30",
                row=3
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
                custom_id="server_custom_days",
                row=3
            )
            custom_button.callback = self.custom_days_callback
            self.add_item(custom_button)

    async def stat_type_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.current_stat_type = interaction.data['values'][0]
        await self.handle_button_click(interaction, refresh=True)

    async def input_role_callback(self, interaction: discord.Interaction):
        modal = ServerRoleModal(
            self.cog, interaction.message.id, self.guild, self)
        await interaction.response.send_modal(modal)

    async def refresh_callback(self, interaction: discord.Interaction):
        await self.handle_button_click(interaction, refresh=True)

    async def time_settings_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.show_time_buttons = not self.show_time_buttons
        self._update_buttons()
        await interaction.edit_original_response(view=self)

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
        modal = ServerTimeModal(
            self.cog, interaction.message.id, self.guild, self)
        await interaction.response.send_modal(modal)

    async def handle_button_click(self, interaction: discord.Interaction, refresh: bool = False, days_back_equiv: int = None, start_time: datetime = None, end_time: datetime = None, display_text: str = None):
        try:
            if interaction.response.is_done():
                await interaction.followup.edit_message(interaction.message.id)
            else:
                await interaction.response.defer()

            if days_back_equiv is not None:
                self.current_days = days_back_equiv
                self.current_days_back_equiv = days_back_equiv
                self.current_start_time = start_time
                self.current_end_time = end_time
                self.show_time_buttons = False
                self.using_server_default = False

            if display_text is not None:
                self.current_display_text = display_text

            # Get role name from database if a role is selected
            role_name = None
            if self.selected_role_id and self.selected_role_id != "none":
                db_cog = self.cog._get_db_cog()
                if db_cog and hasattr(db_cog, 'get_role_name_from_db'):
                    role_name = await db_cog.get_role_name_from_db(self.guild.id, int(self.selected_role_id))

            stats_data = await self.cog.get_server_stats(
                self.guild.id, self.current_start_time, self.current_end_time, self.current_days_back_equiv, self.selected_role_id, self.current_stat_type
            )
            if not stats_data:
                await interaction.followup.send("❌ Error retrieving server statistics", ephemeral=True)
                return

            if self.current_stat_type == "message":
                image_stats_data = await self.cog._convert_to_message_format_async(
                    stats_data, self.guild
                )
                image = await create_message_stats_image(
                    self.guild, image_stats_data, self.current_display_text, self.selected_role_id, role_name
                )
            else:
                image_stats_data = await self.cog._convert_to_voice_format_async(
                    stats_data, self.guild
                )
                image = await create_voice_stats_image(
                    self.guild, image_stats_data, self.current_display_text, self.selected_role_id, role_name
                )

            self._update_buttons()
            img_bytes = io.BytesIO()
            image.save(img_bytes, format='PNG')
            img_bytes.seek(0)

            file = discord.File(img_bytes, filename="server_stats.png")
            await interaction.edit_original_response(attachments=[file], view=self)

        except Exception as e:
            print(f"Error handling button click: {e}")
            traceback.print_exc()
            try:
                await interaction.followup.send("❌ An error occurred while updating the stats.", ephemeral=True)
            except:
                pass


class ServerStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_sessions = {}
        self.rate_limiter = get_rate_limiter()
        self.user_cache = {}  # Cache for fetched users to avoid repeated API calls
        # Start cache cleanup task
        self.clean_cache_task.start()

    def cog_unload(self):
        """Cancel the cache cleanup task when cog is unloaded"""
        self.clean_cache_task.cancel()

    @tasks.loop(hours=1)
    async def clean_cache_task(self):
        """Periodically clean the user cache to prevent memory bloat"""
        self.user_cache.clear()
        gc.collect()

    @rate_limited(RateLimitType.API, timeout=1.0)  # 1 second per request
    async def _fetch_user_with_rate_limit(self, user_id: int):
        """Fetch user globally with rate limiting. Only used as fallback."""
        # Check cache first
        if user_id in self.user_cache:
            return self.user_cache[user_id]

        try:
            user = await self.bot.fetch_user(user_id)
            # Cache the user
            self.user_cache[user_id] = user
            return user
        except discord.NotFound:
            print(f"User {user_id} not found (account may be deleted)")
            return None
        except discord.HTTPException as e:
            print(f"Failed to fetch user {user_id}: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error fetching user {user_id}: {e}")
            return None

    server_group = app_commands.Group(
        name="server",
        description="server statistics commands"
    )

    # NEW METHOD: GET SERVER DEFAULT TIME RANGE
    async def get_server_default_time_range(self, guild: discord.Guild) -> tuple:
        """Get the default time range from server settings. Returns (start_time, end_time, display_text, days_back_equiv)"""
        try:
            settings_cog = self.bot.get_cog('Settings')
            if not settings_cog:
                end = datetime.utcnow()
                start = end - timedelta(days=14)
                return (start, end, "14 days", 14)

            settings = await settings_cog.get_guild_settings(guild.id)
            mode = settings.get('default_time_mode', 'days_back')
            now = datetime.utcnow()

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
            end = datetime.utcnow()
            start = end - timedelta(days=14)
            return (start, end, "14 days", 14)

    async def check_permission(self, interaction: discord.Interaction) -> bool:
        """Check if user has permission to use the command based on guild settings."""
        try:
            # Get settings cog
            settings_cog = self.bot.get_cog('Settings')
            if not settings_cog or not settings_cog.initialized:
                # If settings cog not available, allow all
                return True

            # Get guild settings
            settings = await settings_cog.get_guild_settings(interaction.guild_id)
            permission_level = settings.get('permission_level', 'Default')

            # Always allow users with administrator permission
            if interaction.user.guild_permissions.administrator:
                return True

            # Check permission level
            if permission_level == 'All':
                return True
            elif permission_level == 'Default':
                # For server stats, allow by default since there's no user parameter
                return True
            elif permission_level == 'User Restriction':
                # Server stats doesn't have a user parameter, so allow
                return True
            elif permission_level == 'Admin':
                # Only administrators allowed
                return interaction.user.guild_permissions.administrator
            elif permission_level == 'Moderator':
                # Only users with Manage Server permission
                return interaction.user.guild_permissions.manage_guild
            else:
                # Default fallback
                return True

        except Exception as e:
            print(f"Error checking permission: {e}")
            # Default to allowing if there's an error
            return True

    def _get_db_cog(self):
        return self.bot.get_cog('DatabaseStats')

    async def _convert_to_message_format_async(self, stats_data_db, guild):
        """Async version of _convert_to_message_format that can fetch user data"""
        stats_data_image = {
            'total_messages': stats_data_db.get('total_messages', 0),
            'active_message_users': stats_data_db.get('unique_users', 0),
            'messages_over_time': stats_data_db.get('messages_over_time', {}),
            'top_users_messages': [],
            'top_text_channels': []
        }

        top_users_messages = stats_data_db.get('top_users_messages', [])

        for i in range(3):
            if i < len(top_users_messages):
                user_data = top_users_messages[i]
                user_id = user_data.get('user_id')
                message_count = user_data.get('message_count', 0)

                if user_id:
                    try:
                        user_id_int = int(user_id)
                        member = guild.get_member(user_id_int)

                        if member:
                            # Still in server - use guild member name
                            normalized_username = unicodedata.normalize(
                                'NFKD', member.name)
                            ascii_username = normalized_username.encode(
                                'ascii', 'ignore').decode('ascii')
                            username = ascii_username if ascii_username else member.name
                        else:
                            # Left the server - fetch global name with rate limiting
                            user = await self._fetch_user_with_rate_limit(user_id_int)
                            if user:
                                normalized_username = unicodedata.normalize(
                                    'NFKD', user.name)
                                ascii_username = normalized_username.encode(
                                    'ascii', 'ignore').decode('ascii')
                                username = ascii_username if ascii_username else user.name
                            else:
                                username = f"User {user_id_int}"
                    except (ValueError, TypeError):
                        username = f"User {user_id}"
                else:
                    username = "-"
                    message_count = 0
            else:
                username = "-"
                message_count = 0

            stats_data_image['top_users_messages'].append({
                'name': username,
                'messages': message_count,
                'rank': i + 1
            })

        top_text_channels = stats_data_db.get('top_text_channels', [])

        for i in range(3):
            if i < len(top_text_channels):
                channel_data = top_text_channels[i]
                channel_id = channel_data.get('channel_id', 0)
                if channel_id:
                    try:
                        channel_id_int = int(channel_id)
                        channel = guild.get_channel(channel_id_int)
                        if channel:
                            normalized_channel_name = unicodedata.normalize(
                                'NFKD', channel.name)
                            ascii_channel_name = normalized_channel_name.encode(
                                'ascii', 'ignore').decode('ascii')
                            channel_name = ascii_channel_name if ascii_channel_name else channel.name
                        else:
                            channel_name = "[deleted channel]"
                    except (ValueError, TypeError):
                        channel_name = "[deleted channel]"
                else:
                    channel_name = "-"

                messages = channel_data.get('message_count', 0)
            else:
                channel_name = "-"
                messages = 0

            stats_data_image['top_text_channels'].append({
                'name': channel_name,
                'messages': messages,
                'rank': i + 1
            })

        return stats_data_image

    async def _convert_to_voice_format_async(self, stats_data_db, guild):
        """Async version of _convert_to_voice_format that can fetch user data"""
        stats_data_image = {
            'total_seconds': stats_data_db.get('total_seconds', 0),
            'active_voice_users': stats_data_db.get('unique_users', 0),
            'voice_over_time': stats_data_db.get('voice_over_time', {}),
            'top_users_voice': [],
            'top_voice_channels': []
        }

        top_users_voice = stats_data_db.get('top_users_voice', [])

        for i in range(3):
            if i < len(top_users_voice):
                user_data = top_users_voice[i]
                user_id = user_data.get('user_id', 0)
                voice_seconds = user_data.get('total_seconds', 0)

                try:
                    user_id_int = int(user_id)
                    member = guild.get_member(user_id_int)

                    if member:
                        # Still in server - use guild member name
                        normalized_username = unicodedata.normalize(
                            'NFKD', member.name)
                        ascii_username = normalized_username.encode(
                            'ascii', 'ignore').decode('ascii')
                        username = ascii_username if ascii_username else member.name
                    else:
                        # Left the server - fetch global name with rate limiting
                        user = await self._fetch_user_with_rate_limit(user_id_int)
                        if user:
                            normalized_username = unicodedata.normalize(
                                'NFKD', user.name)
                            ascii_username = normalized_username.encode(
                                'ascii', 'ignore').decode('ascii')
                            username = ascii_username if ascii_username else user.name
                        else:
                            username = f"User {user_id_int}"
                except (ValueError, TypeError):
                    username = f"User {user_id}"
            else:
                username = "-"
                voice_seconds = 0

            stats_data_image['top_users_voice'].append({
                'name': username,
                'voice_time': voice_seconds,
                'rank': i + 1
            })

        top_voice_channels = stats_data_db.get('top_voice_channels', [])

        for i in range(3):
            if i < len(top_voice_channels):
                channel_data = top_voice_channels[i]
                channel_id = channel_data.get('channel_id', 0)
                if channel_id:
                    try:
                        channel_id_int = int(channel_id)
                        channel = guild.get_channel(channel_id_int)
                        if channel:
                            normalized_channel_name = unicodedata.normalize(
                                'NFKD', channel.name)
                            ascii_channel_name = normalized_channel_name.encode(
                                'ascii', 'ignore').decode('ascii')
                            channel_name = ascii_channel_name if ascii_channel_name else channel.name
                        else:
                            channel_name = "[deleted channel]"
                    except (ValueError, TypeError):
                        channel_name = "[deleted channel]"
                else:
                    channel_name = "-"

                voice_time = channel_data.get('total_seconds', 0)
            else:
                channel_name = "-"
                voice_time = 0

            stats_data_image['top_voice_channels'].append({
                'name': channel_name,
                'voice_time': voice_time,
                'rank': i + 1
            })

        return stats_data_image

    async def get_server_stats(self, guild_id: int, start_time: datetime = None, end_time: datetime = None, days_back_equiv: int = 30, role_id: str = None, stat_type: str = "message"):
        """Get server statistics using aggregated tables"""
        db_cog = self._get_db_cog()
        if not db_cog:
            print("DatabaseStats cog not found")
            return None

        try:
            role_ids = None
            if role_id and role_id != "none":
                try:
                    role_ids = [int(role_id)]

                except (ValueError, TypeError):
                    role_ids = None
                    print(f"Invalid role_id: {role_id}")

            # If end_time not provided, use current time
            if end_time is None:
                end_time = datetime.now(timezone.utc)

            stats_data = {
                'total_messages': 0,
                'total_seconds': 0,
                'unique_users': 0,
                'messages_over_time': {},
                'voice_over_time': {},
                'top_users_messages': [],
                'top_users_voice': [],
                'top_text_channels': [],
                'top_voice_channels': []
            }

            if stat_type == "message":

                messages_result = await db_cog.q_server_total_messages(
                    guild_id=guild_id,
                    role_filter_ids=role_ids,
                    start_time=start_time,
                    end_time=end_time
                )
                stats_data['total_messages'] = messages_result.get(
                    'total_messages', 0)
                stats_data['unique_users'] = messages_result.get(
                    'unique_users', 0)

                messages_over_time = await db_cog.q_server_timeseries_messages_1d_5d_10d_20d_30d(
                    guild_id=guild_id,
                    role_filter_ids=role_ids,
                    start_time=start_time,
                    end_time=end_time
                )

                stats_data['messages_over_time'] = messages_over_time

                top_users_messages = await db_cog.q_server_top3_users_messages(
                    guild_id=guild_id,
                    role_filter_ids=role_ids,
                    start_time=start_time,
                    end_time=end_time
                )
                stats_data['top_users_messages'] = top_users_messages

                top_text_channels = await db_cog.q_server_top3_text_channels(
                    guild_id=guild_id,
                    role_filter_ids=role_ids,
                    start_time=start_time,
                    end_time=end_time
                )

                stats_data['top_text_channels'] = top_text_channels

            else:  # voice stats

                voice_result = await db_cog.q_server_total_voice(
                    guild_id=guild_id,
                    role_filter_ids=role_ids,
                    start_time=start_time,
                    end_time=end_time
                )

                stats_data['total_seconds'] = voice_result.get(
                    'total_seconds', 0)
                stats_data['unique_users'] = voice_result.get(
                    'unique_users', 0)

                voice_over_time = await db_cog.q_server_timeseries_voice_1d_5d_10d_20d_30d(
                    guild_id=guild_id,
                    role_filter_ids=role_ids,
                    start_time=start_time,
                    end_time=end_time
                )
                stats_data['voice_over_time'] = voice_over_time

                top_users_voice = await db_cog.q_server_top3_users_voice(
                    guild_id=guild_id,
                    role_filter_ids=role_ids,
                    start_time=start_time,
                    end_time=end_time
                )
                stats_data['top_users_voice'] = top_users_voice

                top_voice_channels = await db_cog.q_server_top3_voice_channels(
                    guild_id=guild_id,
                    role_filter_ids=role_ids,
                    start_time=start_time,
                    end_time=end_time
                )

                stats_data['top_voice_channels'] = top_voice_channels

            stats_data['timestamp'] = end_time.isoformat()

            return stats_data

        except Exception as e:
            print(f"❌ Error getting server stats: {e}")
            traceback.print_exc()
            return None

    # =========================================================
    # INTERNAL FUNCTION FOR BOTH COMMANDS
    # =========================================================
    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def _handle_server_stats_command(self, ctx_or_interaction, is_interaction=False):
        """Internal function to handle server stats for both command types"""
        try:
            # Get context parameters
            if is_interaction:
                user = ctx_or_interaction.user
                guild = ctx_or_interaction.guild
                send_method = ctx_or_interaction.followup.send
                original_message = None
            else:
                user = ctx_or_interaction.author
                guild = ctx_or_interaction.guild
                # Try to delete the command message
                try:
                    await ctx_or_interaction.message.delete()
                except:
                    pass
                send_method = ctx_or_interaction.send
                original_message = await ctx_or_interaction.original_response() if hasattr(ctx_or_interaction, 'original_response') else None

            if guild is None:
                if is_interaction:
                    await ctx_or_interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
                else:
                    await ctx_or_interaction.send("❌ This command can only be used in a server.", delete_after=5)
                return

            # Check permission before processing
            has_permission = await self.check_permission(ctx_or_interaction) if is_interaction else await self.check_permission_for_prefix(user, guild)
            if not has_permission:
                # Get settings to determine required permission
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

            if is_interaction:
                await ctx_or_interaction.response.defer()

            # Get server default time range
            start_time, end_time, display_text, days_back_equiv = await self.get_server_default_time_range(guild)

            # Get stats data using the time range
            stats_data = await self.get_server_stats(guild.id, start_time, end_time, days_back_equiv, None, "message")
            if not stats_data:
                if is_interaction:
                    await ctx_or_interaction.followup.send("❌ Error retrieving server statistics from database.")
                else:
                    await ctx_or_interaction.send("❌ Error retrieving server statistics from database.", delete_after=10)
                return

            # Generate stats image (no role filter on initial load)
            image_stats_data = await self._convert_to_message_format_async(
                stats_data, guild)
            image = await create_message_stats_image(guild, image_stats_data, display_text)

            img_bytes = io.BytesIO()
            image.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            file = discord.File(img_bytes, filename='server_stats.png')

            # Create view with time range parameters
            view = ServerStatsView(
                self, guild, days_back=days_back_equiv, display_text=display_text,
                start_time=start_time, end_time=end_time, days_back_equiv=days_back_equiv,
                stat_type="message", using_server_default=True)

            # Send the image
            if is_interaction:
                msg = await send_method(file=file, view=view)
            else:
                msg = await send_method(file=file, view=view, delete_after=300)

            # Store session
            self.active_sessions[msg.id] = {
                'guild_id': guild.id,
                'user_id': user.id,
                'current_start_time': start_time,
                'current_end_time': end_time,
                'current_display_text': display_text,
                'current_days_back_equiv': days_back_equiv,
                'selected_role_id': None,
                'stat_type': "message",
                'view': view,
                'message': msg
            }

        except Exception as e:
            print(f"Error in _handle_server_stats_command: {e}")
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

    async def check_permission_for_prefix(self, user: discord.Member, guild: discord.Guild) -> bool:
        """Check if user has permission to use the prefix command based on guild settings."""
        try:
            # Get settings cog
            settings_cog = self.bot.get_cog('Settings')
            if not settings_cog or not settings_cog.initialized:
                # If settings cog not available, allow all
                return True

            # Get guild settings
            settings = await settings_cog.get_guild_settings(guild.id)
            permission_level = settings.get('permission_level', 'Default')

            # Always allow users with administrator permission
            if user.guild_permissions.administrator:
                return True

            # Check permission level
            if permission_level == 'All':
                return True
            elif permission_level == 'Default':
                # For server stats, allow by default since there's no user parameter
                return True
            elif permission_level == 'User Restriction':
                # Server stats doesn't have a user parameter, so allow
                return True
            elif permission_level == 'Admin':
                # Only administrators allowed
                return user.guild_permissions.administrator
            elif permission_level == 'Moderator':
                # Only users with Manage Server permission
                return user.guild_permissions.manage_guild
            else:
                # Default fallback
                return True

        except Exception as e:
            print(f"Error checking permission for prefix: {e}")
            # Default to allowing if there's an error
            return True

    # =========================================================
    # SHORTCUT COMMAND - s
    # =========================================================
    @commands.command(name="s")
    async def server_stats_shortcut(self, ctx: commands.Context):
        """Shortcut command for server stats - same as server stats"""
        await self._handle_server_stats_command(ctx, is_interaction=False)

    # =========================================================
    # SERVER GROUP COMMANDS (PREFIX)
    # =========================================================

    @commands.group(name="server", invoke_without_command=True)
    async def server_group_prefix(self, ctx: commands.Context):
        """Server statistics commands"""
        await ctx.send("Available commands:\n- `server stats` - Show server statistics\n- `s` - Shortcut for server stats")

    @server_group_prefix.command(name="stats")
    async def server_stats_prefix(self, ctx: commands.Context):
        """Display server stats via prefix command"""
        await self._handle_server_stats_command(ctx, is_interaction=False)

    # =========================================================
    # SLASH COMMAND
    # =========================================================
    @server_group.command(name="stats", description="Display the stats of the server")
    async def server_stats(self, interaction: discord.Interaction):
        await self._handle_server_stats_command(interaction, is_interaction=True)

    @server_stats.error
    async def server_stats_error(self, interaction: discord.Interaction, error):
        """Handle errors for the server stats command"""
        if isinstance(error, app_commands.errors.CheckFailure):
            embed = discord.Embed(
                title="❌ Permission Denied",
                description="Sorry! You don't have permission to access this command.",
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


async def setup(bot):
    await bot.add_cog(ServerStats(bot))
