import discord
from discord.ext import commands
from discord import app_commands
from collections import Counter, defaultdict
from datetime import timedelta, datetime, timezone
import time
import asyncio
import os
from PIL import Image, ImageDraw, ImageFont
import io
import aiohttp
import random
import traceback
from typing import List, Dict, Any, Optional, Set, Tuple, Union
import logging
import re
from pathlib import Path
import unicodedata
from .ratelimiter import RateLimiter, RateLimitType, rate_limited, get_rate_limiter
import gc
from discord.ext import tasks


logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    USERS_PER_PAGE = 10
    MAX_ROLES_IN_SELECT = 25

    TEMPLATE_PATH = BASE_DIR / "assets" / "images" / "leaderboards final png.png"
    FONT_PATH = BASE_DIR / "assets" / "fonts" / "HorndonD.ttf"

    DEFAULT_DAYS_BACK = 14
    TIME_PERIODS = [7, 14, 30]
    MAX_CUSTOM_DAYS = 2000

    IMAGE_WIDTH = 800
    IMAGE_HEIGHT = 600

    COLORS = {
        'gold': (255, 215, 0, 220),
        'silver': (192, 192, 192, 220),
        'bronze': (205, 127, 50, 220),
        'default': (93, 0, 136, 255),
        'background': (0, 0, 0, 220),
        'text_white': "white",
        'stroke_black': "black"
    }


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


class UnicodeNormalizer:
    @staticmethod
    def normalize_text(text: str) -> str:
        if not text:
            return ""
        normalized = unicodedata.normalize('NFKD', text)
        ascii_safe = normalized.encode('ascii', 'ignore').decode('ascii')
        return ascii_safe if ascii_safe else text[:10]


def format_voice_time(seconds):
    """Format voice time exactly like in channel stats"""
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


class ImageGenerator:
    @staticmethod
    def get_fonts():
        try:
            custom_font_path = Config.FONT_PATH
            if os.path.exists(custom_font_path):
                font_small = ImageFont.truetype(custom_font_path, 16)
                font_medium = ImageFont.truetype(custom_font_path, 20)
                font_large = ImageFont.truetype(custom_font_path, 24)
                font_larger = ImageFont.truetype(custom_font_path, 30)
                font_huge = ImageFont.truetype(custom_font_path, 40)
                font_giant = ImageFont.truetype(custom_font_path, 60)
                return font_small, font_medium, font_large, font_larger, font_huge, font_giant
        except Exception as e:
            logger.warning(f"Failed to load custom font: {e}")

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

    @staticmethod
    def draw_text_with_stroke(draw, position, text, font, fill, stroke_fill, stroke_width):
        x, y = position
        for dx in [-stroke_width, 0, stroke_width]:
            for dy in [-stroke_width, 0, stroke_width]:
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), text,
                              font=font, fill=stroke_fill)
        draw.text((x, y), text, font=font, fill=fill)

    @staticmethod
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
                        ImageGenerator.draw_text_with_stroke(
                            draw, (x, y), text, smaller_font, fill, stroke_fill, stroke_width)
                        return
                except:
                    continue
        ImageGenerator.draw_text_with_stroke(
            draw, (x, y), text, font, fill, stroke_fill, stroke_width)

    @staticmethod
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

    @staticmethod
    async def load_icon_from_url(url):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        icon_data = await response.read()
                        return Image.open(io.BytesIO(icon_data))
        except Exception as e:
            logger.warning(f"Failed to load icon from URL: {e}")
        return None

    @staticmethod
    async def get_name_from_db(pool, item_id: int, item_type: str, guild_id: int = None, guild=None) -> str:
        """Get name from discord_channels table"""
        if not pool:
            return None

        try:
            async with pool.acquire() as conn:
                query = """
                    SELECT channel_name, channel_type 
                    FROM discord_channels 
                    WHERE channel_id = $1
                """
                params = [item_id]

                if guild_id:
                    query += " AND guild_id = $2"
                    params.append(guild_id)

                row = await conn.fetchrow(query, *params)

                if row:
                    channel_name = row['channel_name']
                    channel_type = row['channel_type']

                    if item_type == 'text_channel':
                        return f"#{channel_name}"
                    elif item_type == 'voice_channel':
                        return f"🔊 {channel_name}"
                    elif item_type == 'category':
                        return channel_name
                    else:
                        return channel_name
                else:
                    return None

        except Exception as e:
            print(f"💥 DB error resolving {item_type} {item_id}: {e}")
            return None

    @staticmethod
    async def format_leaderboard_data(guild, leaderboard_data, leaderboard_type, pool=None, cog=None):
        """Format leaderboard data with proper names using fetch_user fallback for left users"""
        formatted_data = []

        bot = None
        if hasattr(guild, '_state') and hasattr(guild._state, '_get_client'):
            bot = guild._state._get_client()

        for item_id, value in leaderboard_data:
            name = None

            try:
                if isinstance(item_id, str) and item_id.isdigit():
                    item_id = int(item_id)

                if leaderboard_type in ['top_text_users', 'top_voice_users', 'channel_text', 'channel_voice',
                                        'top_users_messages', 'top_users_voice',
                                        'category_top_users_messages', 'category_top_users_voice']:
                    member = guild.get_member(item_id)
                    if member:
                        name = str(member)
                    elif cog and hasattr(cog, '_fetch_user_with_rate_limit'):
                        user = await cog._fetch_user_with_rate_limit(item_id)
                        if user:
                            name = user.name
                        else:
                            name = f"User {item_id}"
                    elif bot:
                        user = bot.get_user(item_id)
                        if user:
                            name = user.name
                        else:
                            name = f"User {item_id}"
                    else:
                        name = f"User {item_id}"

                elif leaderboard_type in ['top_text_channels', 'category_top_text_channels']:
                    if pool:
                        db_name = await ImageGenerator.get_name_from_db(pool, item_id, 'text_channel', guild.id, guild)
                        if db_name:
                            name = db_name
                        else:
                            name = f"Unknown Channel ({item_id})"
                    else:
                        name = f"Channel {item_id}"

                elif leaderboard_type in ['top_voice_channels', 'category_top_voice_channels']:
                    if pool:
                        db_name = await ImageGenerator.get_name_from_db(pool, item_id, 'voice_channel', guild.id, guild)
                        if db_name:
                            name = db_name
                        else:
                            name = f"Unknown Voice Channel ({item_id})"
                    else:
                        name = f"Voice Channel {item_id}"

                elif leaderboard_type in ['top_message_categories']:
                    if pool:
                        db_name = await ImageGenerator.get_name_from_db(pool, item_id, 'category', guild.id, guild)
                        if db_name:
                            name = f"📁 {db_name}"
                        else:
                            name = f"Unknown Category ({item_id})"
                    else:
                        name = f"Category {item_id}"

                elif leaderboard_type in ['top_voice_categories']:
                    if pool:
                        db_name = await ImageGenerator.get_name_from_db(pool, item_id, 'category', guild.id, guild)
                        if db_name:
                            name = f"🔊 {db_name}"
                        else:
                            name = f"Unknown Category ({item_id})"
                    else:
                        name = f"Category {item_id}"

                elif leaderboard_type in ['top_roles_messages', 'top_roles_voice', 'top_roles_invites',
                                          'role_messages', 'role_voice', 'role_invites',
                                          'category_role_messages', 'category_role_voice', 'category_role_invites',
                                          'channel_role_messages', 'channel_role_voice', 'channel_role_invites']:
                    async with pool.acquire() as conn:
                        row = await conn.fetchrow("""
                            SELECT role_name FROM current_role_members 
                            WHERE role_id = $1 AND guild_id = $2 
                            LIMIT 1
                        """, item_id, guild.id)
                        if row:
                            name = f"@{row['role_name']}"
                        else:
                            name = f"Deleted Role ({item_id})"

                if not name:
                    name = f"Unknown ({item_id})"

            except Exception as e:
                print(f"      -> 💥 Error: {e}")
                name = f"Unknown ({item_id})"

            normalized_name = UnicodeNormalizer.normalize_text(name)
            formatted_data.append((normalized_name, value))

        return formatted_data

    @staticmethod
    def truncate_text_for_width(draw, text, font, max_width, ellipsis="..."):
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]

        if text_width <= max_width:
            return text, font

        try:
            if hasattr(font, 'path'):
                for size in range(font.size - 2, 12, -2):
                    smaller_font = ImageFont.truetype(font.path, size)
                    smaller_bbox = draw.textbbox(
                        (0, 0), text, font=smaller_font)
                    smaller_width = smaller_bbox[2] - smaller_bbox[0]

                    if smaller_width <= max_width:
                        return text, smaller_font
        except:
            pass

        truncated_text = text
        while len(truncated_text) > 3:
            truncated_text = truncated_text[:-4] + ellipsis
            truncated_bbox = draw.textbbox((0, 0), truncated_text, font=font)
            truncated_width = truncated_bbox[2] - truncated_bbox[0]

            if truncated_width <= max_width:
                return truncated_text, font

        return text[:3] + ellipsis, font

    @staticmethod
    async def add_server_profile_pic_and_name(image, guild, target_name, leaderboard_type, font_huge):
        draw = ImageDraw.Draw(image)

        def fit_text_to_rectangle(text, text_start_x, text_start_y, rect_center_x, rect_center_y, rect_width, rect_height, is_username=False):
            font_paths = [BASE_DIR / "assets" / "fonts" / "HorndonD.ttf"]

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
                    (avatar_x, avatar_y, avatar_x + avatar_size[0], avatar_y + avatar_size[1])).convert('RGBA')

                icon_with_bg = Image.new('RGBA', avatar_size, (0, 0, 0, 0))
                icon_with_bg.paste(icon_image, (0, 0), icon_image)
                avatar_area.paste(icon_with_bg, (0, 0), icon_with_bg)
                image.paste(avatar_area.convert('RGB'), (avatar_x, avatar_y))
                icon_image.close()
                del icon_image
                del icon_data

        except Exception as e:
            logger.error(f"Could not add server icon: {e}")

        normalized_target_name = UnicodeNormalizer.normalize_text(target_name)

        fitted_text, text_font, text_pos = fit_text_to_rectangle(
            normalized_target_name,
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
            draw.text((text_start_x, text_start_y),
                      normalized_target_name, font=font_huge, fill="white")


# IMAGE GENERATION FUNCTIONS

async def generate_message_leaderboard_image(
    guild: discord.Guild,
    leaderboard_data: list,
    target_name: str,
    display_text: str,
    role_id: str = None,
    role_name: str = None,
    total_value: int = None,
    page: int = 0,
    pool=None,
    data_type: str = "users",
    cog=None
):
    template_path = Config.TEMPLATE_PATH
    try:
        image = Image.open(template_path)
    except FileNotFoundError:
        image = Image.new('RGB', (Config.IMAGE_WIDTH,
                          Config.IMAGE_HEIGHT), color='#2F3136')

    if image.mode != "RGB":
        image = image.convert("RGB")

    draw = ImageDraw.Draw(image)
    font_small, font_medium, font_large, font_larger, font_huge, font_giant = ImageGenerator.get_fonts()

    await ImageGenerator.add_server_profile_pic_and_name(image, guild, target_name, "messages", font_huge)

    role_text = role_name if role_name else "No Filter"
    ImageGenerator.draw_text_with_stroke(
        draw, (70, 424), role_text, font_small, "white", "black", 1)

    ImageGenerator.draw_text_with_stroke(
        draw, (630, 422), display_text, font_small, "white", "black", 1)
    ImageGenerator.draw_text_with_stroke(draw, (550, 38), datetime.now().strftime(
        "%B %d, %Y"), font_small, "white", "black", 1)

    if leaderboard_data:
        total_users = len(leaderboard_data)
        users_per_page = Config.USERS_PER_PAGE
        total_pages = (total_users + users_per_page - 1) // users_per_page
        ImageGenerator.draw_text_with_stroke(
            draw, (400, 450), f"Page {page + 1}/{total_pages}", font_medium, "white", "black", 1)
    else:
        total_pages = 1

    if data_type == "users":
        lb_type = "top_users_messages"
    elif data_type == "channels":
        lb_type = "top_text_channels"
    elif data_type == "categories":
        lb_type = "top_message_categories"
    elif data_type == "roles":
        lb_type = "top_roles_messages"
    else:
        lb_type = "top_users_messages"

    if leaderboard_data:
        display_data = await ImageGenerator.format_leaderboard_data(
            guild, leaderboard_data, lb_type, pool, cog
        )

        start_idx = page * Config.USERS_PER_PAGE
        end_idx = min(start_idx + Config.USERS_PER_PAGE, len(display_data))
        page_data = display_data[start_idx:end_idx]

        image_width = image.size[0]

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

        for i, ((name, value), (box_x, box_y)) in enumerate(zip(page_data, positions)):
            global_rank = start_idx + i + 1

            ImageGenerator.draw_rounded_rectangle(draw, [box_x, box_y, box_x + box_width, box_y + box_height],
                                                  radius=8, fill=Config.COLORS['background'], outline=None)

            placement_width = 35
            if global_rank == 1:
                placement_color = Config.COLORS['gold']
            elif global_rank == 2:
                placement_color = Config.COLORS['silver']
            elif global_rank == 3:
                placement_color = Config.COLORS['bronze']
            else:
                placement_color = Config.COLORS['default']

            ImageGenerator.draw_rounded_rectangle(draw, [box_x, box_y, box_x + placement_width, box_y + box_height],
                                                  radius=8, fill=placement_color, outline=None)

            value_text = f"{value:,}"

            if total_value and total_value > 0:
                perc = (value / total_value) * 100
                value_text += f" ({perc:.1f}%)"

            rank_text = f"#{global_rank}"
            rank_bbox = draw.textbbox((0, 0), rank_text, font=font_medium)
            rank_width = rank_bbox[2] - rank_bbox[0]

            value_bbox = draw.textbbox((0, 0), value_text, font=font_medium)
            value_width = value_bbox[2] - value_bbox[0]

            available_name_width = box_width - placement_width - value_width - 20

            display_name = name
            name_font = font_medium

            display_name, name_font = ImageGenerator.truncate_text_for_width(
                draw, display_name, name_font, available_name_width)

            rank_height = rank_bbox[3] - rank_bbox[1]
            name_bbox = draw.textbbox((0, 0), display_name, font=name_font)
            name_height = name_bbox[3] - name_bbox[1]
            value_height = value_bbox[3] - value_bbox[0]

            rank_y = box_y + (box_height - rank_height) // 2
            name_y = box_y + (box_height - name_height) // 2
            value_y = box_y + (box_height - value_height) // 2

            rank_x = box_x + (placement_width - rank_width) // 2
            ImageGenerator.draw_text_with_stroke(
                draw, (rank_x, rank_y), rank_text, font_medium, "white", "black", 1)

            name_x = box_x + placement_width + 8
            ImageGenerator.draw_text_with_stroke(
                draw, (name_x, name_y), display_name, name_font, "white", "black", 1)

            value_x = box_x + box_width - value_width - 8
            ImageGenerator.draw_text_with_stroke(
                draw, (value_x, value_y), value_text, font_medium, "white", "black", 1)
    else:
        cx, cy = image.size[0] // 2, image.size[1] // 2
        ImageGenerator.draw_text_centered_with_stroke(
            draw, "NO DATA AVAILABLE", (cx, cy), font_giant, "white", "black", 3)

    img_bytes = io.BytesIO()
    image.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    gc.collect()
    return img_bytes


async def generate_voice_leaderboard_image(
    guild: discord.Guild,
    leaderboard_data: list,
    target_name: str,
    display_text: str,
    role_id: str = None,
    role_name: str = None,
    total_value: int = None,
    page: int = 0,
    pool=None,
    data_type: str = "users",
    cog=None
):
    template_path = Config.TEMPLATE_PATH
    try:
        image = Image.open(template_path)
    except FileNotFoundError:
        image = Image.new('RGB', (Config.IMAGE_WIDTH,
                          Config.IMAGE_HEIGHT), color='#2F3136')

    if image.mode != "RGB":
        image = image.convert("RGB")

    draw = ImageDraw.Draw(image)
    font_small, font_medium, font_large, font_larger, font_huge, font_giant = ImageGenerator.get_fonts()

    await ImageGenerator.add_server_profile_pic_and_name(image, guild, target_name, "voice", font_huge)

    role_text = role_name if role_name else "No Filter"
    ImageGenerator.draw_text_with_stroke(
        draw, (70, 424), role_text, font_small, "white", "black", 1)

    ImageGenerator.draw_text_with_stroke(
        draw, (630, 422), display_text, font_small, "white", "black", 1)
    ImageGenerator.draw_text_with_stroke(draw, (550, 38), datetime.now().strftime(
        "%B %d, %Y"), font_small, "white", "black", 1)

    if leaderboard_data:
        total_users = len(leaderboard_data)
        users_per_page = Config.USERS_PER_PAGE
        total_pages = (total_users + users_per_page - 1) // users_per_page
        ImageGenerator.draw_text_with_stroke(
            draw, (400, 450), f"Page {page + 1}/{total_pages}", font_medium, "white", "black", 1)
    else:
        total_pages = 1

    if data_type == "users":
        lb_type = "top_users_voice"
    elif data_type == "channels":
        lb_type = "top_voice_channels"
    elif data_type == "categories":
        lb_type = "top_voice_categories"
    elif data_type == "roles":
        lb_type = "top_roles_voice"
    else:
        lb_type = "top_users_voice"

    if leaderboard_data:
        display_data = await ImageGenerator.format_leaderboard_data(
            guild, leaderboard_data, lb_type, pool, cog
        )

        start_idx = page * Config.USERS_PER_PAGE
        end_idx = min(start_idx + Config.USERS_PER_PAGE, len(display_data))
        page_data = display_data[start_idx:end_idx]

        image_width = image.size[0]

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

        for i, ((name, value), (box_x, box_y)) in enumerate(zip(page_data, positions)):
            global_rank = start_idx + i + 1

            ImageGenerator.draw_rounded_rectangle(draw, [box_x, box_y, box_x + box_width, box_y + box_height],
                                                  radius=8, fill=Config.COLORS['background'], outline=None)

            placement_width = 35
            if global_rank == 1:
                placement_color = Config.COLORS['gold']
            elif global_rank == 2:
                placement_color = Config.COLORS['silver']
            elif global_rank == 3:
                placement_color = Config.COLORS['bronze']
            else:
                placement_color = Config.COLORS['default']

            ImageGenerator.draw_rounded_rectangle(draw, [box_x, box_y, box_x + placement_width, box_y + box_height],
                                                  radius=8, fill=placement_color, outline=None)

            value_text = format_voice_time(value)

            rank_text = f"#{global_rank}"
            rank_bbox = draw.textbbox((0, 0), rank_text, font=font_medium)
            rank_width = rank_bbox[2] - rank_bbox[0]

            value_bbox = draw.textbbox((0, 0), value_text, font=font_medium)
            value_width = value_bbox[2] - value_bbox[0]

            available_name_width = box_width - placement_width - value_width - 20

            display_name = name
            name_font = font_medium

            display_name, name_font = ImageGenerator.truncate_text_for_width(
                draw, display_name, name_font, available_name_width)

            rank_height = rank_bbox[3] - rank_bbox[1]
            name_bbox = draw.textbbox((0, 0), display_name, font=name_font)
            name_height = name_bbox[3] - name_bbox[1]
            value_height = value_bbox[3] - value_bbox[0]

            rank_y = box_y + (box_height - rank_height) // 2
            name_y = box_y + (box_height - name_height) // 2
            value_y = box_y + (box_height - value_height) // 2

            rank_x = box_x + (placement_width - rank_width) // 2
            ImageGenerator.draw_text_with_stroke(
                draw, (rank_x, rank_y), rank_text, font_medium, "white", "black", 1)

            name_x = box_x + placement_width + 8
            ImageGenerator.draw_text_with_stroke(
                draw, (name_x, name_y), display_name, name_font, "white", "black", 1)

            value_x = box_x + box_width - value_width - 8
            ImageGenerator.draw_text_with_stroke(
                draw, (value_x, value_y), value_text, font_medium, "white", "black", 1)
    else:
        cx, cy = image.size[0] // 2, image.size[1] // 2
        ImageGenerator.draw_text_centered_with_stroke(
            draw, "NO DATA AVAILABLE", (cx, cy), font_giant, "white", "black", 3)

    img_bytes = io.BytesIO()
    image.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    gc.collect()
    return img_bytes


async def generate_invite_leaderboard_image(
    guild: discord.Guild,
    leaderboard_data: list,
    target_name: str,
    display_text: str,
    role_id: str = None,
    role_name: str = None,
    total_value: int = None,
    page: int = 0,
    pool=None,
    data_type: str = "roles",
    cog=None
):
    template_path = Config.TEMPLATE_PATH
    try:
        image = Image.open(template_path)
    except FileNotFoundError:
        image = Image.new('RGB', (Config.IMAGE_WIDTH,
                          Config.IMAGE_HEIGHT), color='#2F3136')

    if image.mode != "RGB":
        image = image.convert("RGB")

    draw = ImageDraw.Draw(image)
    font_small, font_medium, font_large, font_larger, font_huge, font_giant = ImageGenerator.get_fonts()

    await ImageGenerator.add_server_profile_pic_and_name(image, guild, target_name, "invites", font_huge)

    role_text = role_name if role_name else "No Filter"
    ImageGenerator.draw_text_with_stroke(
        draw, (70, 424), role_text, font_small, "white", "black", 1)

    ImageGenerator.draw_text_with_stroke(
        draw, (630, 422), display_text, font_small, "white", "black", 1)
    ImageGenerator.draw_text_with_stroke(draw, (550, 38), datetime.now().strftime(
        "%B %d, %Y"), font_small, "white", "black", 1)

    if leaderboard_data:
        total_users = len(leaderboard_data)
        users_per_page = Config.USERS_PER_PAGE
        total_pages = (total_users + users_per_page - 1) // users_per_page
        ImageGenerator.draw_text_with_stroke(
            draw, (400, 450), f"Page {page + 1}/{total_pages}", font_medium, "white", "black", 1)
    else:
        total_pages = 1

    if leaderboard_data:
        display_data = await ImageGenerator.format_leaderboard_data(
            guild, leaderboard_data, "top_roles_invites", pool, cog
        )

        start_idx = page * Config.USERS_PER_PAGE
        end_idx = min(start_idx + Config.USERS_PER_PAGE, len(display_data))
        page_data = display_data[start_idx:end_idx]

        image_width = image.size[0]

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

        for i, ((name, value), (box_x, box_y)) in enumerate(zip(page_data, positions)):
            global_rank = start_idx + i + 1

            ImageGenerator.draw_rounded_rectangle(draw, [box_x, box_y, box_x + box_width, box_y + box_height],
                                                  radius=8, fill=Config.COLORS['background'], outline=None)

            placement_width = 35
            if global_rank == 1:
                placement_color = Config.COLORS['gold']
            elif global_rank == 2:
                placement_color = Config.COLORS['silver']
            elif global_rank == 3:
                placement_color = Config.COLORS['bronze']
            else:
                placement_color = Config.COLORS['default']

            ImageGenerator.draw_rounded_rectangle(draw, [box_x, box_y, box_x + placement_width, box_y + box_height],
                                                  radius=8, fill=placement_color, outline=None)

            value_text = f"{value:,}"

            rank_text = f"#{global_rank}"
            rank_bbox = draw.textbbox((0, 0), rank_text, font=font_medium)
            rank_width = rank_bbox[2] - rank_bbox[0]

            value_bbox = draw.textbbox((0, 0), value_text, font=font_medium)
            value_width = value_bbox[2] - value_bbox[0]

            available_name_width = box_width - placement_width - value_width - 20

            display_name = name
            name_font = font_medium

            display_name, name_font = ImageGenerator.truncate_text_for_width(
                draw, display_name, name_font, available_name_width)

            rank_height = rank_bbox[3] - rank_bbox[1]
            name_bbox = draw.textbbox((0, 0), display_name, font=name_font)
            name_height = name_bbox[3] - name_bbox[1]
            value_height = value_bbox[3] - value_bbox[0]

            rank_y = box_y + (box_height - rank_height) // 2
            name_y = box_y + (box_height - name_height) // 2
            value_y = box_y + (box_height - value_height) // 2

            rank_x = box_x + (placement_width - rank_width) // 2
            ImageGenerator.draw_text_with_stroke(
                draw, (rank_x, rank_y), rank_text, font_medium, "white", "black", 1)

            name_x = box_x + placement_width + 8
            ImageGenerator.draw_text_with_stroke(
                draw, (name_x, name_y), display_name, name_font, "white", "black", 1)

            value_x = box_x + box_width - value_width - 8
            ImageGenerator.draw_text_with_stroke(
                draw, (value_x, value_y), value_text, font_medium, "white", "black", 1)
    else:
        cx, cy = image.size[0] // 2, image.size[1] // 2
        ImageGenerator.draw_text_centered_with_stroke(
            draw, "NO DATA AVAILABLE", (cx, cy), font_giant, "white", "black", 3)

    img_bytes = io.BytesIO()
    image.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    gc.collect()
    return img_bytes

# WRAPPER FUNCTIONS


async def generate_server_leaderboard_image(guild: discord.Guild, leaderboard_data: list,
                                            leaderboard_type: str, display_text: str, role_id: str = None,
                                            total_value: int = None, user_count: int = 10, page: int = 0,
                                            is_real_time: bool = False, pool=None, cog=None):

    if leaderboard_type in ['top_users_voice', 'top_voice_channels', 'top_voice_categories']:
        return await generate_voice_leaderboard_image(
            guild=guild,
            leaderboard_data=leaderboard_data,
            target_name=UnicodeNormalizer.normalize_text(guild.name),
            display_text=display_text,
            role_id=role_id,
            total_value=total_value,
            page=page,
            pool=pool,
            cog=cog
        )
    else:
        return await generate_message_leaderboard_image(
            guild=guild,
            leaderboard_data=leaderboard_data,
            target_name=UnicodeNormalizer.normalize_text(guild.name),
            display_text=display_text,
            role_id=role_id,
            total_value=total_value,
            page=page,
            pool=pool,
            cog=cog
        )


async def generate_category_leaderboard_image(guild: discord.Guild, category: discord.CategoryChannel,
                                              leaderboard_data: list, leaderboard_type: str,
                                              display_text: str, role_id: str = None, total_value: int = None,
                                              user_count: int = 10, page: int = 0, is_real_time: bool = False, pool=None, cog=None):

    target_name = UnicodeNormalizer.normalize_text(
        category.name if category else "[Deleted Category]")

    if leaderboard_type in ['top_users_voice', 'top_voice_channels']:
        return await generate_voice_leaderboard_image(
            guild=guild,
            leaderboard_data=leaderboard_data,
            target_name=target_name,
            display_text=display_text,
            role_id=role_id,
            total_value=total_value,
            page=page,
            pool=pool,
            cog=cog
        )
    else:
        return await generate_message_leaderboard_image(
            guild=guild,
            leaderboard_data=leaderboard_data,
            target_name=target_name,
            display_text=display_text,
            role_id=role_id,
            total_value=total_value,
            page=page,
            pool=pool,
            cog=cog
        )


async def generate_channel_leaderboard_image(guild: discord.Guild, channel: discord.abc.GuildChannel,
                                             leaderboard_data: list, leaderboard_type: str,
                                             display_text: str, role_id: str = None,
                                             total_value: int = None, user_count: int = 10, page: int = 0,
                                             is_real_time: bool = False, pool=None, cog=None):

    if channel:
        if isinstance(channel, discord.TextChannel):
            channel_name = f"#{UnicodeNormalizer.normalize_text(channel.name)}"
        elif isinstance(channel, discord.VoiceChannel):
            channel_name = f"🔊{UnicodeNormalizer.normalize_text(channel.name)}"
        else:
            channel_name = UnicodeNormalizer.normalize_text(channel.name)
    else:
        channel_name = "[Deleted Channel]"

    if leaderboard_type in ['top_voice_users', 'channel_voice']:
        return await generate_voice_leaderboard_image(
            guild=guild,
            leaderboard_data=leaderboard_data,
            target_name=channel_name,
            display_text=display_text,
            role_id=role_id,
            total_value=total_value,
            page=page,
            pool=pool,
            cog=cog
        )
    else:
        return await generate_message_leaderboard_image(
            guild=guild,
            leaderboard_data=leaderboard_data,
            target_name=channel_name,
            display_text=display_text,
            role_id=role_id,
            total_value=total_value,
            page=page,
            pool=pool,
            cog=cog
        )


async def generate_role_leaderboard_image(guild: discord.Guild, leaderboard_data: list,
                                          leaderboard_type: str, display_text: str,
                                          channel: discord.abc.GuildChannel = None,
                                          category: discord.CategoryChannel = None,
                                          role_id: str = None, total_value: int = None,
                                          user_count: int = 10, page: int = 0, is_real_time: bool = False, pool=None, cog=None):

    target_name = UnicodeNormalizer.normalize_text(guild.name)

    if channel:
        if isinstance(channel, discord.TextChannel):
            target_name = f"#{UnicodeNormalizer.normalize_text(channel.name)}"
        elif isinstance(channel, discord.VoiceChannel):
            target_name = f"🔊{UnicodeNormalizer.normalize_text(channel.name)}"
        else:
            target_name = UnicodeNormalizer.normalize_text(channel.name)
    elif category:
        target_name = UnicodeNormalizer.normalize_text(category.name)

    if 'voice' in leaderboard_type:
        return await generate_voice_leaderboard_image(
            guild=guild,
            leaderboard_data=leaderboard_data,
            target_name=target_name,
            display_text=display_text,
            role_id=role_id,
            total_value=total_value,
            page=page,
            pool=pool,
            data_type="roles",
            cog=cog
        )
    elif 'invites' in leaderboard_type:
        return await generate_invite_leaderboard_image(
            guild=guild,
            leaderboard_data=leaderboard_data,
            target_name=target_name,
            display_text=display_text,
            role_id=role_id,
            total_value=total_value,
            page=page,
            pool=pool,
            data_type="roles",
            cog=cog
        )
    else:
        return await generate_message_leaderboard_image(
            guild=guild,
            leaderboard_data=leaderboard_data,
            target_name=target_name,
            display_text=display_text,
            role_id=role_id,
            total_value=total_value,
            page=page,
            pool=pool,
            data_type="roles",
            cog=cog
        )


# TIME MODALS

class ChannelLeaderboardTimeModal(discord.ui.Modal, title='Custom Time Period'):
    def __init__(self, cog_instance, original_message_id, guild, channel, leaderboard_type):
        super().__init__(timeout=300)
        self.cog = cog_instance
        self.original_message_id = original_message_id
        self.guild = guild
        self.channel = channel
        self.leaderboard_type = leaderboard_type

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
            if days <= 0 or days > Config.MAX_CUSTOM_DAYS:
                await interaction.response.send_message(f"❌ Please enter a number between 1 and {Config.MAX_CUSTOM_DAYS} days.", ephemeral=True)
                return

            await interaction.response.defer()

            view = self.cog.active_views.get(self.original_message_id)
            if not view:
                await interaction.followup.send("❌ Could not find the leaderboard view. Please try the command again.", ephemeral=True)
                return

            now = datetime.utcnow()
            view.current_start_time = now - timedelta(days=days)
            view.current_end_time = now
            view.current_days_back_equiv = days
            view.current_display_text = f"{days} days"
            view.using_server_default = False
            view.show_time_buttons = False
            view.page = 0

            try:
                original_message = await interaction.channel.fetch_message(self.original_message_id)
                if original_message:
                    if isinstance(self.channel, discord.TextChannel):
                        leaderboard_data = await self.cog.get_channel_text_leaderboard(
                            self.guild, self.channel, view.current_start_time, view.current_end_time, view.selected_role_id
                        )
                    elif isinstance(self.channel, discord.VoiceChannel):
                        if self.leaderboard_type == "top_voice_users":
                            leaderboard_data = await self.cog.get_channel_voice_leaderboard(
                                self.guild, self.channel, view.current_start_time, view.current_end_time, view.selected_role_id
                            )
                        else:
                            leaderboard_data = await self.cog.get_channel_text_leaderboard(
                                self.guild, self.channel, view.current_start_time, view.current_end_time, view.selected_role_id
                            )
                    else:
                        leaderboard_data = []

                    total_items = len(leaderboard_data)
                    total_pages = max(
                        1, (total_items + Config.USERS_PER_PAGE - 1) // Config.USERS_PER_PAGE)

                    if view.page >= total_pages:
                        view.page = max(0, total_pages - 1)

                    img_bytes = await view.generate_image()

                    for child in view.children:
                        if isinstance(child, PageIndicator):
                            child.label = f"Page {view.page + 1}/{total_pages}"
                        elif isinstance(child, PrevButton):
                            child.disabled = (
                                view.page == 0 or total_pages <= 1)
                        elif isinstance(child, NextButton):
                            child.disabled = (
                                view.page >= total_pages - 1 or total_pages <= 1)

                    view._update_buttons()

                    file = discord.File(
                        img_bytes, filename="channel_leaderboard.png")
                    await original_message.edit(attachments=[file], view=view)
                else:
                    await interaction.followup.send("❌ Could not find the original message.", ephemeral=True)
            except discord.NotFound:
                await interaction.followup.send("❌ The original message was not found. Please try the command again.", ephemeral=True)

        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in channel modal submit: {e}")
            traceback.print_exc()
            await interaction.followup.send("❌ An error occurred while updating the leaderboard.", ephemeral=True)


class ServerLeaderboardTimeModal(discord.ui.Modal, title='Custom Time Period'):
    def __init__(self, cog_instance, original_message_id, guild):
        super().__init__(timeout=300)
        self.cog = cog_instance
        self.original_message_id = original_message_id
        self.guild = guild

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
            if days <= 0 or days > Config.MAX_CUSTOM_DAYS:
                await interaction.response.send_message(f"❌ Please enter a number between 1 and {Config.MAX_CUSTOM_DAYS} days.", ephemeral=True)
                return

            await interaction.response.defer()

            view = self.cog.active_views.get(self.original_message_id)
            if not view:
                await interaction.followup.send("❌ Could not find the leaderboard view. Please try the command again.", ephemeral=True)
                return

            now = datetime.utcnow()
            view.current_start_time = now - timedelta(days=days)
            view.current_end_time = now
            view.current_days_back_equiv = days
            view.current_display_text = f"{days} days"
            view.using_server_default = False
            view.show_time_buttons = False
            view.page = 0

            try:
                original_message = await interaction.channel.fetch_message(self.original_message_id)
                if original_message:
                    if view.leaderboard_type in ["top_users_voice", "top_voice_channels", "top_voice_categories"]:
                        data = await self.cog.get_server_voice_data(self.guild, view.current_start_time, view.current_end_time, view.selected_role_id)
                        leaderboard_data = data.get("users", []) if view.leaderboard_type == "top_users_voice" else \
                            data.get("channels", []) if view.leaderboard_type in ["top_voice_channels"] else \
                            data.get("voice_categories", [])
                    else:
                        data = await self.cog.get_server_message_data(self.guild, view.current_start_time, view.current_end_time, view.selected_role_id)
                        leaderboard_data = data.get("users", []) if view.leaderboard_type == "top_users_messages" else \
                            data.get("channels", []) if view.leaderboard_type == "top_text_channels" else \
                            data.get("message_categories", [])

                    total_items = len(leaderboard_data)
                    total_pages = max(
                        1, (total_items + Config.USERS_PER_PAGE - 1) // Config.USERS_PER_PAGE)

                    if view.page >= total_pages:
                        view.page = max(0, total_pages - 1)

                    img_bytes = await view.generate_image()

                    for child in view.children:
                        if isinstance(child, PageIndicator):
                            child.label = f"Page {view.page + 1}/{total_pages}"
                        elif isinstance(child, PrevButton):
                            child.disabled = (
                                view.page == 0 or total_pages <= 1)
                        elif isinstance(child, NextButton):
                            child.disabled = (
                                view.page >= total_pages - 1 or total_pages <= 1)

                    view._update_buttons()

                    file = discord.File(
                        img_bytes, filename="server_leaderboard.png")
                    await original_message.edit(attachments=[file], view=view)
                else:
                    await interaction.followup.send("❌ Could not find the original message.", ephemeral=True)
            except discord.NotFound:
                await interaction.followup.send("❌ The original message was not found. Please try the command again.", ephemeral=True)

        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in server modal submit: {e}")
            traceback.print_exc()
            await interaction.followup.send("❌ An error occurred while updating the leaderboard.", ephemeral=True)


class CategoryLeaderboardTimeModal(discord.ui.Modal, title='Custom Time Period'):
    def __init__(self, cog_instance, original_message_id, guild, category):
        super().__init__(timeout=300)
        self.cog = cog_instance
        self.original_message_id = original_message_id
        self.guild = guild
        self.category = category

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
            if days <= 0 or days > Config.MAX_CUSTOM_DAYS:
                await interaction.response.send_message(f"❌ Please enter a number between 1 and {Config.MAX_CUSTOM_DAYS} days.", ephemeral=True)
                return

            await interaction.response.defer()

            view = self.cog.active_views.get(self.original_message_id)
            if not view:
                await interaction.followup.send("❌ Could not find the leaderboard view. Please try the command again.", ephemeral=True)
                return

            now = datetime.utcnow()
            view.current_start_time = now - timedelta(days=days)
            view.current_end_time = now
            view.current_days_back_equiv = days
            view.current_display_text = f"{days} days"
            view.using_server_default = False
            view.show_time_buttons = False
            view.page = 0

            try:
                original_message = await interaction.channel.fetch_message(self.original_message_id)
                if original_message:
                    data = await self.cog.get_category_data(self.guild, self.category, view.current_start_time, view.current_end_time,
                                                            view.leaderboard_type, view.selected_role_id)

                    if view.leaderboard_type in ["top_users_messages", "top_users_voice"]:
                        leaderboard_data = data.get("users", [])
                    else:
                        leaderboard_data = data.get("channels", [])

                    total_items = len(leaderboard_data)
                    total_pages = max(
                        1, (total_items + Config.USERS_PER_PAGE - 1) // Config.USERS_PER_PAGE)

                    if view.page >= total_pages:
                        view.page = max(0, total_pages - 1)

                    img_bytes = await view.generate_image()

                    for child in view.children:
                        if isinstance(child, PageIndicator):
                            child.label = f"Page {view.page + 1}/{total_pages}"
                        elif isinstance(child, PrevButton):
                            child.disabled = (
                                view.page == 0 or total_pages <= 1)
                        elif isinstance(child, NextButton):
                            child.disabled = (
                                view.page >= total_pages - 1 or total_pages <= 1)

                    view._update_buttons()

                    file = discord.File(
                        img_bytes, filename="category_leaderboard.png")
                    await original_message.edit(attachments=[file], view=view)
                else:
                    await interaction.followup.send("❌ Could not find the original message.", ephemeral=True)
            except discord.NotFound:
                await interaction.followup.send("❌ The original message was not found. Please try the command again.", ephemeral=True)

        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in category modal submit: {e}")
            traceback.print_exc()
            await interaction.followup.send("❌ An error occurred while updating the leaderboard.", ephemeral=True)


class RoleLeaderboardTimeModal(discord.ui.Modal, title='Custom Time Period'):
    def __init__(self, cog_instance, original_message_id, guild, target=None):
        super().__init__(timeout=300)
        self.cog = cog_instance
        self.original_message_id = original_message_id
        self.guild = guild
        self.target = target

        self.channel = target if isinstance(
            target, (discord.TextChannel, discord.VoiceChannel)) else None
        self.category = target if isinstance(
            target, discord.CategoryChannel) else None

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
            if days <= 0 or days > Config.MAX_CUSTOM_DAYS:
                await interaction.response.send_message(f"❌ Please enter a number between 1 and {Config.MAX_CUSTOM_DAYS} days.", ephemeral=True)
                return

            await interaction.response.defer()

            view = self.cog.active_views.get(self.original_message_id)
            if not view:
                await interaction.followup.send("❌ Could not find the leaderboard view. Please try the command again.", ephemeral=True)
                return

            now = datetime.utcnow()
            view.current_start_time = now - timedelta(days=days)
            view.current_end_time = now
            view.current_days_back_equiv = days
            view.current_display_text = f"{days} days"
            view.using_server_default = False
            view.show_time_buttons = False
            view.page = 0

            try:
                original_message = await interaction.channel.fetch_message(self.original_message_id)
                if original_message:
                    leaderboard_data = await self.cog.get_role_leaderboard_data(
                        self.guild, view.current_start_time, view.current_end_time, view.leaderboard_type,
                        self.channel, self.category, view.selected_role_id
                    )

                    total_items = len(leaderboard_data)
                    total_pages = max(
                        1, (total_items + Config.USERS_PER_PAGE - 1) // Config.USERS_PER_PAGE)

                    if view.page >= total_pages:
                        view.page = max(0, total_pages - 1)

                    img_bytes = await view.generate_image()

                    for child in view.children:
                        if isinstance(child, PageIndicator):
                            child.label = f"Page {view.page + 1}/{total_pages}"
                        elif isinstance(child, PrevButton):
                            child.disabled = (
                                view.page == 0 or total_pages <= 1)
                        elif isinstance(child, NextButton):
                            child.disabled = (
                                view.page >= total_pages - 1 or total_pages <= 1)

                    view._update_buttons()

                    file = discord.File(
                        img_bytes, filename="role_leaderboard.png")
                    await original_message.edit(attachments=[file], view=view)
                else:
                    await interaction.followup.send("❌ Could not find the original message.", ephemeral=True)
            except discord.NotFound:
                await interaction.followup.send("❌ The original message was not found. Please try the command again.", ephemeral=True)

        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in role modal submit: {e}")
            traceback.print_exc()
            await interaction.followup.send("❌ An error occurred while updating the leaderboard.", ephemeral=True)


class RoleIdModal(discord.ui.Modal, title='Filter By Role'):
    def __init__(self, cog_instance, original_message_id, guild):
        super().__init__(timeout=300)
        self.cog = cog_instance
        self.original_message_id = original_message_id
        self.guild = guild

    role_id = discord.ui.TextInput(
        label='Enter Role ID',
        placeholder='e.g., 123456789012345678',
        min_length=17,
        max_length=20,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            role_id_value = self.role_id.value.strip()

            try:
                role_id_int = int(role_id_value)
            except ValueError:
                embed = discord.Embed(
                    title="❌ Invalid Role ID",
                    description="Please enter a valid numeric Role ID.",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            role = self.guild.get_role(role_id_int)

            if not role:
                embed = discord.Embed(
                    title="❌ Invalid Role ID",
                    description="The role ID you inputted is not valid in this server. Please try again.",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            await interaction.response.defer(ephemeral=False, thinking=True)

            view = self.cog.active_views.get(self.original_message_id)
            if view:
                view.selected_role_id = role_id_value
                view.page = 0
                await view.update_message(interaction)
            else:
                await interaction.followup.send("❌ Could not find the leaderboard view. Please try the command again.", ephemeral=True)

        except Exception as e:
            logger.error(f"Error in role ID modal submit: {e}")
            traceback.print_exc()
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while processing the role ID.",
                color=discord.Color.red()
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)


class RoleIdButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary,
                         label="Filter By Role", custom_id="input_role_id")

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if hasattr(view, 'guild'):
            modal = RoleIdModal(view.cog, interaction.message.id, view.guild)
            await interaction.response.send_modal(modal)


class PrevButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary,
                         emoji=discord.PartialEmoji(name="arrowleft", id=1521149181207777331), custom_id="leaderboard_prev")

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


class NextButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary,
                         emoji=discord.PartialEmoji(name="arrowright", id=1521149211373076501), custom_id="leaderboard_next")

    async def callback(self, interaction: discord.Interaction):
        if self.disabled:
            await interaction.response.defer(ephemeral=True, thinking=False)
            return

        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False, thinking=False)

        view = self.view
        view.page += 1
        await view.update_message(interaction)


class PageIndicator(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary,
                         label="Page 1/1", custom_id="leaderboard_page", disabled=False)

    async def callback(self, interaction: discord.Interaction):
        view = self.view

        if hasattr(view, 'get_total_pages'):
            total_pages = await view.get_total_pages()
        else:
            if hasattr(view, 'leaderboard_type'):
                if view.leaderboard_type in ["top_users_voice", "top_voice_channels", "top_voice_categories"]:
                    data = await view.cog.get_server_voice_data(view.guild, view.current_start_time, view.current_end_time, view.selected_role_id)
                else:
                    data = await view.cog.get_server_message_data(view.guild, view.current_start_time, view.current_end_time, view.selected_role_id)

                if view.leaderboard_type == "top_users_messages" or view.leaderboard_type == "top_users_voice":
                    leaderboard_data = data.get("users", [])
                elif view.leaderboard_type == "top_text_channels" or view.leaderboard_type == "top_voice_channels":
                    leaderboard_data = data.get("channels", [])
                else:
                    leaderboard_data = data.get("message_categories", [
                    ]) if view.leaderboard_type == "top_message_categories" else data.get("voice_categories", [])

                total_pages = max(
                    1, (len(leaderboard_data) + Config.USERS_PER_PAGE - 1) // Config.USERS_PER_PAGE)
            else:
                total_pages = 1

        modal = PageJumpModal(view, total_pages)
        await interaction.response.send_modal(modal)


class ChannelLeaderboardTypeSelect(discord.ui.Select):
    def __init__(self, current_type: str, channel_type: str):
        options = []

        if channel_type == "text":
            options = [
                discord.SelectOption(label="Top Message Users", value="top_text_users",
                                     description="Users with most messages", emoji="💬"),
            ]
        elif channel_type == "voice":
            options = [
                discord.SelectOption(label="Top Voice Users", value="top_voice_users",
                                     description="Users with most voice time", emoji="🎤"),
                discord.SelectOption(label="Top Message Users", value="top_text_users",
                                     description="Users with most messages", emoji="💬"),
            ]

        for option in options:
            option.default = (option.value == current_type)

        super().__init__(placeholder="Select leaderboard type...",
                         options=options, custom_id="channel_leaderboard_type")

    async def callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False, thinking=False)

        view = self.view
        view.leaderboard_type = self.values[0]
        view.page = 0
        await view.update_message(interaction)


class ServerLeaderboardTypeSelect(discord.ui.Select):
    def __init__(self, current_type: str):
        options = [
            discord.SelectOption(label="Top Message Users", value="top_users_messages",
                                 description="Users with most messages", emoji="💬"),
            discord.SelectOption(label="Top Voice Users", value="top_users_voice",
                                 description="Users with most voice time", emoji="🎤"),
            discord.SelectOption(label="Top Text Channels", value="top_text_channels",
                                 description="Most active text channels", emoji="📝"),
            discord.SelectOption(label="Top Voice Channels", value="top_voice_channels",
                                 description="Most active voice channels", emoji="🔊"),
            discord.SelectOption(label="Top Message Categories", value="top_message_categories",
                                 description="Most active message categories", emoji="📁"),
            discord.SelectOption(label="Top Voice Categories", value="top_voice_categories",
                                 description="Most active voice categories", emoji="🔊"),
        ]

        for option in options:
            option.default = (option.value == current_type)

        super().__init__(placeholder="Select leaderboard type...",
                         options=options, custom_id="server_leaderboard_type")

    async def callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False, thinking=False)

        view = self.view
        view.leaderboard_type = self.values[0]
        view.page = 0
        await view.update_message(interaction)


class CategoryLeaderboardTypeSelect(discord.ui.Select):
    def __init__(self, current_type: str):
        options = [
            discord.SelectOption(label="Top Text Channels", value="top_text_channels",
                                 description="Most active text channels", emoji="📝"),
            discord.SelectOption(label="Top Voice Channels", value="top_voice_channels",
                                 description="Most active voice channels", emoji="🔊"),
            discord.SelectOption(label="Top Message Users", value="top_users_messages",
                                 description="Users with most messages", emoji="💬"),
            discord.SelectOption(label="Top Voice Users", value="top_users_voice",
                                 description="Users with most voice time", emoji="🎤"),
        ]

        for option in options:
            option.default = (option.value == current_type)

        super().__init__(placeholder="Select leaderboard type...",
                         options=options, custom_id="category_leaderboard_type")

    async def callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False, thinking=False)

        view = self.view
        view.leaderboard_type = self.values[0]
        view.page = 0
        await view.update_message(interaction)


class RoleLeaderboardTypeSelect(discord.ui.Select):
    def __init__(self, current_type: str, has_channel_or_category: bool = False):
        options = [
            discord.SelectOption(label="Messages", value="top_roles_messages",
                                 description="Roles with most messages", emoji="💬"),
            discord.SelectOption(label="Voice Activity", value="top_roles_voice",
                                 description="Roles with most voice time", emoji="🎤"),
        ]

        if not has_channel_or_category:
            options.append(
                discord.SelectOption(label="Invites", value="top_roles_invites",
                                     description="Roles with most invites", emoji="📨")
            )

        for option in options:
            option.default = (option.value == current_type)

        super().__init__(placeholder="Select leaderboard type...",
                         options=options, custom_id="role_leaderboard_type")

    async def callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False, thinking=False)

        view = self.view
        view.leaderboard_type = self.values[0]
        view.page = 0
        await view.update_message(interaction)


class ChannelLeaderboardView(discord.ui.View):
    def __init__(self, cog_instance, guild: discord.Guild, channel: Union[discord.TextChannel, discord.VoiceChannel],
                 start_time: datetime = None, end_time: datetime = None, days_back_equiv: int = Config.DEFAULT_DAYS_BACK,
                 display_text: str = f"{Config.DEFAULT_DAYS_BACK} days", leaderboard_type: str = "top_text_users", page: int = 0,
                 selected_role_id: str = None, pool=None, using_server_default: bool = True):
        super().__init__(timeout=600)
        self.cog = cog_instance
        self.guild = guild
        self.channel = channel
        self.pool = pool
        self.current_start_time = start_time
        self.current_end_time = end_time
        self.current_days_back_equiv = days_back_equiv
        self.current_display_text = display_text
        self.leaderboard_type = leaderboard_type
        self.page = page
        self.selected_role_id = selected_role_id
        self.using_server_default = using_server_default
        self.show_time_buttons = False

        if isinstance(channel, discord.TextChannel):
            self.channel_type = "text"
            if leaderboard_type not in ["top_text_users"]:
                leaderboard_type = "top_text_users"
        elif isinstance(channel, discord.VoiceChannel):
            self.channel_type = "voice"
            if leaderboard_type not in ["top_voice_users", "top_text_users"]:
                leaderboard_type = "top_voice_users"
        else:
            self.channel_type = "unknown"
            leaderboard_type = "top_text_users"

        self._update_buttons()

    def _update_buttons(self):
        self.clear_items()

        if self.channel_type in ["text", "voice"]:
            self.add_item(ChannelLeaderboardTypeSelect(
                self.leaderboard_type, self.channel_type))

        self.add_item(PrevButton())
        self.add_item(PageIndicator())
        self.add_item(NextButton())

        self.add_item(RoleIdButton())

        refresh_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=discord.PartialEmoji(name="refresh", id=1518249841505861743),
            custom_id="channel_refresh",
            row=4
        )
        refresh_button.callback = self.refresh_callback

        time_settings_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=discord.PartialEmoji(name="clockk", id=1518249803069259867),
            custom_id="channel_time_settings",
            row=4
        )
        time_settings_button.callback = self.time_settings_callback

        self.add_item(refresh_button)
        self.add_item(time_settings_button)

        if self.show_time_buttons:
            row = 5
            all_time_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 999999 else discord.ButtonStyle.secondary,
                label="All Time",
                custom_id="channel_all_time",
                row=row
            )
            all_time_button.callback = self.all_time_callback
            self.add_item(all_time_button)

            for days in Config.TIME_PERIODS:
                days_button = discord.ui.Button(
                    style=discord.ButtonStyle.primary if self.current_days_back_equiv == days else discord.ButtonStyle.secondary,
                    label=f"{days} Days",
                    custom_id=f"channel_days_{days}",
                    row=row
                )
                days_button.callback = self.create_days_callback(days)
                self.add_item(days_button)

            custom_button = discord.ui.Button(
                style=discord.ButtonStyle.success if self.current_days_back_equiv not in Config.TIME_PERIODS and self.current_days_back_equiv != 999999 else discord.ButtonStyle.secondary,
                label=f"Custom ({self.current_days_back_equiv}d)" if self.current_days_back_equiv not in Config.TIME_PERIODS and self.current_days_back_equiv != 999999 else "Custom",
                custom_id="channel_custom_days",
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
        modal = ChannelLeaderboardTimeModal(
            self.cog, interaction.message.id, self.guild, self.channel, self.leaderboard_type)
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
        pool = self.pool

        if isinstance(self.channel, discord.TextChannel):
            if self.leaderboard_type == "top_text_users":
                leaderboard_data = await self.cog.get_channel_text_leaderboard(
                    self.guild, self.channel, self.current_start_time, self.current_end_time, self.selected_role_id
                )
                total_value = sum(
                    count for _, count in leaderboard_data) if leaderboard_data else 0

                return await generate_message_leaderboard_image(
                    guild=self.guild,
                    leaderboard_data=leaderboard_data,
                    target_name=f"#{UnicodeNormalizer.normalize_text(self.channel.name)}",
                    display_text=self.current_display_text,
                    role_id=self.selected_role_id,
                    total_value=total_value,
                    page=self.page,
                    pool=pool,
                    data_type="users",
                    cog=self.cog
                )
            else:
                leaderboard_data = []
                return await generate_message_leaderboard_image(
                    guild=self.guild,
                    leaderboard_data=leaderboard_data,
                    target_name=f"#{UnicodeNormalizer.normalize_text(self.channel.name)}",
                    display_text=self.current_display_text,
                    role_id=self.selected_role_id,
                    total_value=0,
                    page=self.page,
                    pool=pool,
                    data_type="users",
                    cog=self.cog
                )

        elif isinstance(self.channel, discord.VoiceChannel):
            if self.leaderboard_type == "top_voice_users":
                leaderboard_data = await self.cog.get_channel_voice_leaderboard(
                    self.guild, self.channel, self.current_start_time, self.current_end_time, self.selected_role_id
                )
                total_value = sum(
                    seconds for _, seconds in leaderboard_data) if leaderboard_data else 0

                return await generate_voice_leaderboard_image(
                    guild=self.guild,
                    leaderboard_data=leaderboard_data,
                    target_name=f"🔊{UnicodeNormalizer.normalize_text(self.channel.name)}",
                    display_text=self.current_display_text,
                    role_id=self.selected_role_id,
                    total_value=total_value,
                    page=self.page,
                    pool=pool,
                    data_type="users",
                    cog=self.cog
                )
            elif self.leaderboard_type == "top_text_users":
                leaderboard_data = await self.cog.get_channel_text_leaderboard(
                    self.guild, self.channel, self.current_start_time, self.current_end_time, self.selected_role_id
                )
                total_value = sum(
                    count for _, count in leaderboard_data) if leaderboard_data else 0

                return await generate_message_leaderboard_image(
                    guild=self.guild,
                    leaderboard_data=leaderboard_data,
                    target_name=f"🔊{UnicodeNormalizer.normalize_text(self.channel.name)}",
                    display_text=self.current_display_text,
                    role_id=self.selected_role_id,
                    total_value=total_value,
                    page=self.page,
                    pool=pool,
                    data_type="users",
                    cog=self.cog
                )
            else:
                leaderboard_data = []
                return await generate_voice_leaderboard_image(
                    guild=self.guild,
                    leaderboard_data=leaderboard_data,
                    target_name=f"🔊{UnicodeNormalizer.normalize_text(self.channel.name)}",
                    display_text=self.current_display_text,
                    role_id=self.selected_role_id,
                    total_value=0,
                    page=self.page,
                    pool=pool,
                    data_type="users",
                    cog=self.cog
                )

        return await generate_message_leaderboard_image(
            guild=self.guild,
            leaderboard_data=[],
            target_name="Unknown",
            display_text=self.current_display_text,
            role_id=self.selected_role_id,
            page=self.page,
            pool=pool,
            data_type="users",
            cog=self.cog
        )

    async def update_message(self, interaction: discord.Interaction):
        try:
            if isinstance(self.channel, discord.TextChannel):
                leaderboard_data = await self.cog.get_channel_text_leaderboard(
                    self.guild, self.channel, self.current_start_time, self.current_end_time, self.selected_role_id
                )
            elif isinstance(self.channel, discord.VoiceChannel):
                if self.leaderboard_type == "top_voice_users":
                    leaderboard_data = await self.cog.get_channel_voice_leaderboard(
                        self.guild, self.channel, self.current_start_time, self.current_end_time, self.selected_role_id
                    )
                else:
                    leaderboard_data = await self.cog.get_channel_text_leaderboard(
                        self.guild, self.channel, self.current_start_time, self.current_end_time, self.selected_role_id
                    )
            else:
                leaderboard_data = []

            total_items = len(leaderboard_data)
            total_pages = max(
                1, (total_items + Config.USERS_PER_PAGE - 1) // Config.USERS_PER_PAGE)

            if self.page >= total_pages:
                self.page = max(0, total_pages - 1)

            img_bytes = await self.generate_image()

            for child in self.children:
                if isinstance(child, PageIndicator):
                    child.label = f"Page {self.page + 1}/{total_pages}"
                elif isinstance(child, PrevButton):
                    child.disabled = (self.page == 0 or total_pages <= 1)
                elif isinstance(child, NextButton):
                    child.disabled = (
                        self.page >= total_pages - 1 or total_pages <= 1)

            self._update_buttons()

            file = discord.File(img_bytes, filename="channel_leaderboard.png")

            if interaction.response.is_done():
                await interaction.edit_original_response(attachments=[file], view=self)
            else:
                await interaction.response.edit_message(attachments=[file], view=self)

        except Exception as e:
            logger.error(f"Error updating channel leaderboard message: {e}")
            traceback.print_exc()
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ An error occurred while updating the leaderboard.", ephemeral=True)
                else:
                    await interaction.followup.send("❌ An error occurred while updating the leaderboard.", ephemeral=True)
            except:
                pass


class ServerLeaderboardView(discord.ui.View):
    def __init__(self, cog_instance, guild: discord.Guild, start_time: datetime = None, end_time: datetime = None,
                 days_back_equiv: int = Config.DEFAULT_DAYS_BACK, display_text: str = f"{Config.DEFAULT_DAYS_BACK} days",
                 leaderboard_type: str = "top_users_messages", page: int = 0,
                 selected_role_id: str = None, pool=None, using_server_default: bool = True):
        super().__init__(timeout=600)
        self.cog = cog_instance
        self.guild = guild
        self.current_start_time = start_time
        self.current_end_time = end_time
        self.current_days_back_equiv = days_back_equiv
        self.current_display_text = display_text
        self.leaderboard_type = leaderboard_type
        self.page = page
        self.selected_role_id = selected_role_id
        self.pool = pool
        self.using_server_default = using_server_default
        self.show_time_buttons = False
        self._update_buttons()

    def _update_buttons(self):
        self.clear_items()

        self.add_item(ServerLeaderboardTypeSelect(self.leaderboard_type))

        self.add_item(PrevButton())
        self.add_item(PageIndicator())
        self.add_item(NextButton())

        self.add_item(RoleIdButton())

        refresh_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=discord.PartialEmoji(name="refresh", id=1518249841505861743),
            custom_id="server_refresh",
            row=4
        )
        refresh_button.callback = self.refresh_callback

        time_settings_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=discord.PartialEmoji(name="clockk", id=1518249803069259867),
            custom_id="server_time_settings",
            row=4
        )
        time_settings_button.callback = self.time_settings_callback

        self.add_item(refresh_button)
        self.add_item(time_settings_button)

        if self.show_time_buttons:
            row = 5
            all_time_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 999999 else discord.ButtonStyle.secondary,
                label="All Time",
                custom_id="server_all_time",
                row=row
            )
            all_time_button.callback = self.all_time_callback
            self.add_item(all_time_button)

            for days in Config.TIME_PERIODS:
                days_button = discord.ui.Button(
                    style=discord.ButtonStyle.primary if self.current_days_back_equiv == days else discord.ButtonStyle.secondary,
                    label=f"{days} Days",
                    custom_id=f"server_days_{days}",
                    row=row
                )
                days_button.callback = self.create_days_callback(days)
                self.add_item(days_button)

            custom_button = discord.ui.Button(
                style=discord.ButtonStyle.success if self.current_days_back_equiv not in Config.TIME_PERIODS and self.current_days_back_equiv != 999999 else discord.ButtonStyle.secondary,
                label=f"Custom ({self.current_days_back_equiv}d)" if self.current_days_back_equiv not in Config.TIME_PERIODS and self.current_days_back_equiv != 999999 else "Custom",
                custom_id="server_custom_days",
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
        modal = ServerLeaderboardTimeModal(
            self.cog, interaction.message.id, self.guild)
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
        pool = self.pool

        if self.leaderboard_type in ["top_users_voice", "top_voice_channels", "top_voice_categories"]:
            data = await self.cog.get_server_voice_data(self.guild, self.current_start_time, self.current_end_time, self.selected_role_id)

            if self.leaderboard_type == "top_users_voice":
                leaderboard_data = data.get("users", [])
                total_value = sum(
                    seconds for _, seconds in leaderboard_data) if leaderboard_data else 0
                return await generate_voice_leaderboard_image(
                    guild=self.guild,
                    leaderboard_data=leaderboard_data,
                    target_name=UnicodeNormalizer.normalize_text(
                        self.guild.name),
                    display_text=self.current_display_text,
                    role_id=self.selected_role_id,
                    total_value=total_value,
                    page=self.page,
                    pool=pool,
                    data_type="users",
                    cog=self.cog
                )
            elif self.leaderboard_type == "top_voice_channels":
                leaderboard_data = data.get("channels", [])
                total_value = sum(
                    seconds for _, seconds in leaderboard_data) if leaderboard_data else 0
                return await generate_voice_leaderboard_image(
                    guild=self.guild,
                    leaderboard_data=leaderboard_data,
                    target_name=UnicodeNormalizer.normalize_text(
                        self.guild.name),
                    display_text=self.current_display_text,
                    role_id=self.selected_role_id,
                    total_value=total_value,
                    page=self.page,
                    pool=pool,
                    data_type="channels",
                    cog=self.cog
                )
            else:
                leaderboard_data = data.get("voice_categories", [])
                total_value = sum(
                    seconds for _, seconds in leaderboard_data) if leaderboard_data else 0
                return await generate_voice_leaderboard_image(
                    guild=self.guild,
                    leaderboard_data=leaderboard_data,
                    target_name=UnicodeNormalizer.normalize_text(
                        self.guild.name),
                    display_text=self.current_display_text,
                    role_id=self.selected_role_id,
                    total_value=total_value,
                    page=self.page,
                    pool=pool,
                    data_type="categories",
                    cog=self.cog
                )
        else:
            data = await self.cog.get_server_message_data(self.guild, self.current_start_time, self.current_end_time, self.selected_role_id)

            if self.leaderboard_type == "top_users_messages":
                leaderboard_data = data.get("users", [])
                total_value = sum(
                    count for _, count in leaderboard_data) if leaderboard_data else 0
                return await generate_message_leaderboard_image(
                    guild=self.guild,
                    leaderboard_data=leaderboard_data,
                    target_name=UnicodeNormalizer.normalize_text(
                        self.guild.name),
                    display_text=self.current_display_text,
                    role_id=self.selected_role_id,
                    total_value=total_value,
                    page=self.page,
                    pool=pool,
                    data_type="users",
                    cog=self.cog
                )
            elif self.leaderboard_type == "top_text_channels":
                leaderboard_data = data.get("channels", [])
                total_value = sum(
                    count for _, count in leaderboard_data) if leaderboard_data else 0
                return await generate_message_leaderboard_image(
                    guild=self.guild,
                    leaderboard_data=leaderboard_data,
                    target_name=UnicodeNormalizer.normalize_text(
                        self.guild.name),
                    display_text=self.current_display_text,
                    role_id=self.selected_role_id,
                    total_value=total_value,
                    page=self.page,
                    pool=pool,
                    data_type="channels",
                    cog=self.cog
                )
            else:
                leaderboard_data = data.get("message_categories", [])
                total_value = sum(
                    count for _, count in leaderboard_data) if leaderboard_data else 0
                return await generate_message_leaderboard_image(
                    guild=self.guild,
                    leaderboard_data=leaderboard_data,
                    target_name=UnicodeNormalizer.normalize_text(
                        self.guild.name),
                    display_text=self.current_display_text,
                    role_id=self.selected_role_id,
                    total_value=total_value,
                    page=self.page,
                    pool=pool,
                    data_type="categories",
                    cog=self.cog
                )

    async def update_message(self, interaction: discord.Interaction):
        try:
            img_bytes = await self.generate_image()

            if self.leaderboard_type in ["top_users_voice", "top_voice_channels", "top_voice_categories"]:
                data = await self.cog.get_server_voice_data(self.guild, self.current_start_time, self.current_end_time, self.selected_role_id)
                leaderboard_data = data.get("users", []) if self.leaderboard_type == "top_users_voice" else \
                    data.get("channels", []) if self.leaderboard_type in ["top_voice_channels"] else \
                    data.get("voice_categories", [])
            else:
                data = await self.cog.get_server_message_data(self.guild, self.current_start_time, self.current_end_time, self.selected_role_id)
                leaderboard_data = data.get("users", []) if self.leaderboard_type == "top_users_messages" else \
                    data.get("channels", []) if self.leaderboard_type == "top_text_channels" else \
                    data.get("message_categories", [])

            total_items = len(leaderboard_data)
            total_pages = max(
                1, (total_items + Config.USERS_PER_PAGE - 1) // Config.USERS_PER_PAGE)

            if self.page >= total_pages:
                self.page = max(0, total_pages - 1)

            for child in self.children:
                if isinstance(child, PageIndicator):
                    child.label = f"Page {self.page + 1}/{total_pages}"
                elif isinstance(child, PrevButton):
                    child.disabled = (self.page == 0 or total_pages <= 1)
                elif isinstance(child, NextButton):
                    child.disabled = (
                        self.page >= total_pages - 1 or total_pages <= 1)

            file = discord.File(img_bytes, filename="server_leaderboard.png")

            if interaction.response.is_done():
                await interaction.edit_original_response(attachments=[file], view=self)
            else:
                await interaction.response.edit_message(attachments=[file], view=self)

        except Exception as e:
            logger.error(f"Error updating server leaderboard message: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ An error occurred while updating the leaderboard.", ephemeral=True)
                else:
                    await interaction.followup.send("❌ An error occurred while updating the leaderboard.", ephemeral=True)
            except:
                pass


class CategoryLeaderboardView(discord.ui.View):
    def __init__(self, cog_instance, guild: discord.Guild, category: discord.CategoryChannel,
                 start_time: datetime = None, end_time: datetime = None, days_back_equiv: int = Config.DEFAULT_DAYS_BACK,
                 display_text: str = f"{Config.DEFAULT_DAYS_BACK} days", leaderboard_type: str = "top_text_channels", page: int = 0,
                 selected_role_id: str = None, pool=None, using_server_default: bool = True):
        super().__init__(timeout=600)
        self.cog = cog_instance
        self.guild = guild
        self.category = category
        self.current_start_time = start_time
        self.current_end_time = end_time
        self.current_days_back_equiv = days_back_equiv
        self.current_display_text = display_text
        self.leaderboard_type = leaderboard_type
        self.page = page
        self.selected_role_id = selected_role_id
        self.pool = pool
        self.using_server_default = using_server_default
        self.show_time_buttons = False
        self._update_buttons()

    def _update_buttons(self):
        self.clear_items()

        self.add_item(CategoryLeaderboardTypeSelect(self.leaderboard_type))

        self.add_item(PrevButton())
        self.add_item(PageIndicator())
        self.add_item(NextButton())

        self.add_item(RoleIdButton())

        refresh_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=discord.PartialEmoji(name="refresh", id=1518249841505861743),
            custom_id="category_refresh",
            row=4
        )
        refresh_button.callback = self.refresh_callback

        time_settings_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=discord.PartialEmoji(name="clockk", id=1518249803069259867),
            custom_id="category_time_settings",
            row=4
        )
        time_settings_button.callback = self.time_settings_callback

        self.add_item(refresh_button)
        self.add_item(time_settings_button)

        if self.show_time_buttons:
            row = 5
            all_time_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 999999 else discord.ButtonStyle.secondary,
                label="All Time",
                custom_id="category_all_time",
                row=row
            )
            all_time_button.callback = self.all_time_callback
            self.add_item(all_time_button)

            for days in Config.TIME_PERIODS:
                days_button = discord.ui.Button(
                    style=discord.ButtonStyle.primary if self.current_days_back_equiv == days else discord.ButtonStyle.secondary,
                    label=f"{days} Days",
                    custom_id=f"category_days_{days}",
                    row=row
                )
                days_button.callback = self.create_days_callback(days)
                self.add_item(days_button)

            custom_button = discord.ui.Button(
                style=discord.ButtonStyle.success if self.current_days_back_equiv not in Config.TIME_PERIODS and self.current_days_back_equiv != 999999 else discord.ButtonStyle.secondary,
                label=f"Custom ({self.current_days_back_equiv}d)" if self.current_days_back_equiv not in Config.TIME_PERIODS and self.current_days_back_equiv != 999999 else "Custom",
                custom_id="category_custom_days",
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
        modal = CategoryLeaderboardTimeModal(
            self.cog, interaction.message.id, self.guild, self.category)
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
        pool = self.pool

        data = await self.cog.get_category_data(self.guild, self.category, self.current_start_time, self.current_end_time,
                                                self.leaderboard_type, self.selected_role_id)

        target_name = UnicodeNormalizer.normalize_text(self.category.name)

        if self.leaderboard_type == "top_users_messages":
            leaderboard_data = data.get("users", [])
            total_value = sum(
                value for _, value in leaderboard_data) if leaderboard_data else 0
            return await generate_message_leaderboard_image(
                guild=self.guild,
                leaderboard_data=leaderboard_data,
                target_name=target_name,
                display_text=self.current_display_text,
                role_id=self.selected_role_id,
                total_value=total_value,
                page=self.page,
                pool=pool,
                data_type="users",
                cog=self.cog
            )
        elif self.leaderboard_type == "top_users_voice":
            leaderboard_data = data.get("users", [])
            total_value = sum(
                value for _, value in leaderboard_data) if leaderboard_data else 0
            return await generate_voice_leaderboard_image(
                guild=self.guild,
                leaderboard_data=leaderboard_data,
                target_name=target_name,
                display_text=self.current_display_text,
                role_id=self.selected_role_id,
                total_value=total_value,
                page=self.page,
                pool=pool,
                data_type="users",
                cog=self.cog
            )
        elif self.leaderboard_type == "top_text_channels":
            leaderboard_data = data.get("channels", [])
            total_value = sum(
                value for _, value in leaderboard_data) if leaderboard_data else 0
            return await generate_message_leaderboard_image(
                guild=self.guild,
                leaderboard_data=leaderboard_data,
                target_name=target_name,
                display_text=self.current_display_text,
                role_id=self.selected_role_id,
                total_value=total_value,
                page=self.page,
                pool=pool,
                data_type="channels",
                cog=self.cog
            )
        elif self.leaderboard_type == "top_voice_channels":
            leaderboard_data = data.get("channels", [])
            total_value = sum(
                value for _, value in leaderboard_data) if leaderboard_data else 0
            return await generate_voice_leaderboard_image(
                guild=self.guild,
                leaderboard_data=leaderboard_data,
                target_name=target_name,
                display_text=self.current_display_text,
                role_id=self.selected_role_id,
                total_value=total_value,
                page=self.page,
                pool=pool,
                data_type="channels",
                cog=self.cog
            )
        else:
            leaderboard_data = data.get("channels", [])
            total_value = sum(
                value for _, value in leaderboard_data) if leaderboard_data else 0
            return await generate_message_leaderboard_image(
                guild=self.guild,
                leaderboard_data=leaderboard_data,
                target_name=target_name,
                display_text=self.current_display_text,
                role_id=self.selected_role_id,
                total_value=total_value,
                page=self.page,
                pool=pool,
                data_type="channels",
                cog=self.cog
            )

    async def update_message(self, interaction: discord.Interaction):
        try:
            data = await self.cog.get_category_data(self.guild, self.category, self.current_start_time, self.current_end_time,
                                                    self.leaderboard_type, self.selected_role_id)

            if self.leaderboard_type in ["top_users_messages", "top_users_voice"]:
                leaderboard_data = data.get("users", [])
            else:
                leaderboard_data = data.get("channels", [])

            total_items = len(leaderboard_data)
            total_pages = max(
                1, (total_items + Config.USERS_PER_PAGE - 1) // Config.USERS_PER_PAGE)

            if self.page >= total_pages:
                self.page = max(0, total_pages - 1)

            img_bytes = await self.generate_image()

            for child in self.children:
                if isinstance(child, PageIndicator):
                    child.label = f"Page {self.page + 1}/{total_pages}"
                elif isinstance(child, PrevButton):
                    child.disabled = (self.page == 0 or total_pages <= 1)
                elif isinstance(child, NextButton):
                    child.disabled = (
                        self.page >= total_pages - 1 or total_pages <= 1)

            self._update_buttons()

            file = discord.File(img_bytes, filename="category_leaderboard.png")

            if interaction.response.is_done():
                await interaction.edit_original_response(attachments=[file], view=self)
            else:
                await interaction.response.edit_message(attachments=[file], view=self)

        except Exception as e:
            logger.error(f"Error updating category leaderboard message: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ An error occurred while updating the leaderboard.", ephemeral=True)
                else:
                    await interaction.followup.send("❌ An error occurred while updating the leaderboard.", ephemeral=True)
            except:
                pass


class RoleLeaderboardView(discord.ui.View):
    def __init__(self, cog_instance, guild: discord.Guild, start_time: datetime = None, end_time: datetime = None,
                 days_back_equiv: int = Config.DEFAULT_DAYS_BACK, display_text: str = f"{Config.DEFAULT_DAYS_BACK} days",
                 leaderboard_type: str = "top_roles_messages", page: int = 0,
                 selected_role_id: str = None, target: Optional[Union[discord.abc.GuildChannel, discord.CategoryChannel]] = None,
                 pool=None, using_server_default: bool = True):
        super().__init__(timeout=600)
        self.cog = cog_instance
        self.guild = guild
        self.current_start_time = start_time
        self.current_end_time = end_time
        self.current_days_back_equiv = days_back_equiv
        self.current_display_text = display_text
        self.leaderboard_type = leaderboard_type
        self.page = page
        self.selected_role_id = selected_role_id
        self.target = target
        self.pool = pool
        self.using_server_default = using_server_default

        self.channel = target if isinstance(
            target, (discord.TextChannel, discord.VoiceChannel)) else None
        self.category = target if isinstance(
            target, discord.CategoryChannel) else None

        self.show_time_buttons = False
        self._update_buttons()

    def _update_buttons(self):
        self.clear_items()

        has_channel_or_category = (self.channel is not None) or (
            self.category is not None)
        self.add_item(RoleLeaderboardTypeSelect(
            self.leaderboard_type, has_channel_or_category))

        self.add_item(PrevButton())
        self.add_item(PageIndicator())
        self.add_item(NextButton())

        self.add_item(RoleIdButton())

        refresh_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=discord.PartialEmoji(name="refresh", id=1518249841505861743),
            custom_id="role_refresh",
            row=4
        )
        refresh_button.callback = self.refresh_callback

        time_settings_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=discord.PartialEmoji(name="clockk", id=1518249803069259867),
            custom_id="role_time_settings",
            row=4
        )
        time_settings_button.callback = self.time_settings_callback

        self.add_item(refresh_button)
        self.add_item(time_settings_button)

        if self.show_time_buttons:
            row = 5
            all_time_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 999999 else discord.ButtonStyle.secondary,
                label="All Time",
                custom_id="role_all_time",
                row=row
            )
            all_time_button.callback = self.all_time_callback
            self.add_item(all_time_button)

            for days in Config.TIME_PERIODS:
                days_button = discord.ui.Button(
                    style=discord.ButtonStyle.primary if self.current_days_back_equiv == days else discord.ButtonStyle.secondary,
                    label=f"{days} Days",
                    custom_id=f"role_days_{days}",
                    row=row
                )
                days_button.callback = self.create_days_callback(days)
                self.add_item(days_button)

            custom_button = discord.ui.Button(
                style=discord.ButtonStyle.success if self.current_days_back_equiv not in Config.TIME_PERIODS and self.current_days_back_equiv != 999999 else discord.ButtonStyle.secondary,
                label=f"Custom ({self.current_days_back_equiv}d)" if self.current_days_back_equiv not in Config.TIME_PERIODS and self.current_days_back_equiv != 999999 else "Custom",
                custom_id="role_custom_days",
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
        modal = RoleLeaderboardTimeModal(
            self.cog, interaction.message.id, self.guild, self.target)
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
        pool = self.pool

        leaderboard_data = await self.cog.get_role_leaderboard_data(
            self.guild, self.current_start_time, self.current_end_time, self.leaderboard_type,
            self.channel, self.category, self.selected_role_id
        )

        total_value = sum(
            value for _, value in leaderboard_data) if leaderboard_data else 0

        target_name = UnicodeNormalizer.normalize_text(self.guild.name)
        if self.channel:
            if isinstance(self.channel, discord.TextChannel):
                target_name = f"#{UnicodeNormalizer.normalize_text(self.channel.name)}"
            elif isinstance(self.channel, discord.VoiceChannel):
                target_name = f"🔊{UnicodeNormalizer.normalize_text(self.channel.name)}"
        elif self.category:
            target_name = UnicodeNormalizer.normalize_text(self.category.name)

        if 'voice' in self.leaderboard_type:
            return await generate_voice_leaderboard_image(
                guild=self.guild,
                leaderboard_data=leaderboard_data,
                target_name=target_name,
                display_text=self.current_display_text,
                role_id=self.selected_role_id,
                total_value=total_value,
                page=self.page,
                pool=pool,
                data_type="roles",
                cog=self.cog
            )
        elif 'invites' in self.leaderboard_type:
            return await generate_invite_leaderboard_image(
                guild=self.guild,
                leaderboard_data=leaderboard_data,
                target_name=target_name,
                display_text=self.current_display_text,
                role_id=self.selected_role_id,
                total_value=total_value,
                page=self.page,
                pool=pool,
                data_type="roles",
                cog=self.cog
            )
        else:
            return await generate_message_leaderboard_image(
                guild=self.guild,
                leaderboard_data=leaderboard_data,
                target_name=target_name,
                display_text=self.current_display_text,
                role_id=self.selected_role_id,
                total_value=total_value,
                page=self.page,
                pool=pool,
                data_type="roles",
                cog=self.cog
            )

    async def update_message(self, interaction: discord.Interaction):
        try:
            leaderboard_data = await self.cog.get_role_leaderboard_data(
                self.guild, self.current_start_time, self.current_end_time, self.leaderboard_type,
                self.channel, self.category, self.selected_role_id
            )

            total_items = len(leaderboard_data)
            total_pages = max(
                1, (total_items + Config.USERS_PER_PAGE - 1) // Config.USERS_PER_PAGE)

            if self.page >= total_pages:
                self.page = max(0, total_pages - 1)

            img_bytes = await self.generate_image()

            for child in self.children:
                if isinstance(child, PageIndicator):
                    child.label = f"Page {self.page + 1}/{total_pages}"
                elif isinstance(child, PrevButton):
                    child.disabled = (self.page == 0 or total_pages <= 1)
                elif isinstance(child, NextButton):
                    child.disabled = (
                        self.page >= total_pages - 1 or total_pages <= 1)

            self._update_buttons()

            file = discord.File(img_bytes, filename="role_leaderboard.png")

            if interaction.response.is_done():
                await interaction.edit_original_response(attachments=[file], view=self)
            else:
                await interaction.response.edit_message(attachments=[file], view=self)

        except Exception as e:
            logger.error(f"Error updating role leaderboard message: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ An error occurred while updating the leaderboard.", ephemeral=True)
                else:
                    await interaction.followup.send("❌ An error occurred while updating the leaderboard.", ephemeral=True)
            except:
                pass


# PERMISSION CHECK FUNCTION
async def check_permission(interaction: discord.Interaction) -> bool:
    if interaction.user.guild_permissions.administrator:
        return True

    settings_cog = interaction.client.get_cog('Settings')
    if not settings_cog:
        return True

    try:
        settings = await settings_cog.get_guild_settings(interaction.guild.id)
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
            return interaction.user.guild_permissions.manage_guild

        return True
    except Exception as e:
        logger.error(f"Error checking permissions: {e}")
        return True


# INITIALIZATION
class Leaderboards(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_cog = None
        self.active_views = {}
        self.users_per_page = Config.USERS_PER_PAGE
        self.rate_limiter = get_rate_limiter()
        self.user_cache = {}
        self.clean_cache_task.start()

    def cog_unload(self):
        self.clean_cache_task.cancel()

    @tasks.loop(hours=1)
    async def clean_cache_task(self):
        self.user_cache.clear()
        gc.collect()

    @rate_limited(RateLimitType.API, timeout=1.0)
    async def _fetch_user_with_rate_limit(self, user_id: int):
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
        await self._wait_for_db_cog()

    async def _wait_for_db_cog(self):
        for _ in range(30):
            self.db_cog = self.bot.get_cog('DatabaseStats')
            if self.db_cog:
                break
            await asyncio.sleep(1)

        if not self.db_cog:
            logger.warning(
                "⚠️ Leaderboards: DatabaseStats cog not found after waiting!")

    # NEW METHOD: GET SERVER DEFAULT TIME RANGE
    # NEW METHOD: GET SERVER DEFAULT TIME RANGE
    async def get_server_default_time_range(self, guild: discord.Guild) -> tuple:
        """Get the default time range from server settings. Returns (start_time, end_time, display_text, days_back_equiv)"""
        try:
            settings_cog = self.bot.get_cog('Settings')
            if not settings_cog:
                end = datetime.now(timezone.utc)
                start = end - timedelta(days=Config.DEFAULT_DAYS_BACK)
                return (start, end, f"{Config.DEFAULT_DAYS_BACK} days", Config.DEFAULT_DAYS_BACK)

            settings = await settings_cog.get_guild_settings(guild.id)
            mode = settings.get('default_time_mode', 'days_back')
            now = datetime.now(timezone.utc)

            if mode == 'all_time':
                return (None, now, "All Time", 999999)

            elif mode == 'days_back':
                days = settings.get(
                    'default_days_back') or Config.DEFAULT_DAYS_BACK
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
            start = now - timedelta(days=Config.DEFAULT_DAYS_BACK)
            return (start, end, f"{Config.DEFAULT_DAYS_BACK} days", Config.DEFAULT_DAYS_BACK)

        except Exception as e:
            import traceback
            traceback.print_exc()
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=Config.DEFAULT_DAYS_BACK)
            return (start, end, f"{Config.DEFAULT_DAYS_BACK} days", Config.DEFAULT_DAYS_BACK)

    async def _filter_members_by_role(self, guild: discord.Guild, role_id: str) -> List[int]:
        if not guild or not role_id or role_id == "none":
            return []

        try:
            role_id_int = int(role_id)
            role = guild.get_role(role_id_int)
            if not role:
                return []

            member_ids = []
            for member in guild.members:
                if role in member.roles:
                    member_ids.append(member.id)

            return member_ids
        except Exception as e:
            logger.error(f"Error filtering members by role: {e}")
            return []

    async def get_channel_voice_leaderboard(self, guild: discord.Guild, channel: discord.VoiceChannel,
                                            start_time: datetime = None, end_time: datetime = None, role_id: str = None):
        if not self.db_cog:
            logger.warning("DatabaseStats cog not available")
            return []

        try:
            guild_id_int = int(guild.id)

            role_filter_ids = None
            if role_id and role_id != "none":
                role_id_int = int(role_id)
                role_filter_ids = [role_id_int]

            top_users = await self.db_cog.q_leaderboard_voice_users_in_channel(
                guild_id=guild_id_int,
                channel_id=channel.id,
                limit=100,
                role_filter_ids=role_filter_ids,
                start_time=start_time,
                end_time=end_time
            )

            user_stats = []
            for user_data in top_users:
                user_id = user_data.get('user_id')
                total_seconds = user_data.get('total_seconds', 0)

                if user_id and total_seconds > 0:
                    user_stats.append((str(user_id), total_seconds))

            return user_stats

        except Exception as e:
            logger.error(f"Error getting voice leaderboard: {e}")
            traceback.print_exc()
            return []

    async def get_channel_text_leaderboard(self, guild: discord.Guild, channel: discord.TextChannel,
                                           start_time: datetime = None, end_time: datetime = None, role_id: str = None):
        if not self.db_cog:
            logger.warning("DatabaseStats cog not available")
            return []

        try:
            guild_id_int = int(guild.id)

            role_filter_ids = None
            if role_id and role_id != "none":
                role_id_int = int(role_id)
                role_filter_ids = [role_id_int]

            top_users = await self.db_cog.q_leaderboard_text_users_in_channel(
                guild_id=guild_id_int,
                channel_id=channel.id,
                limit=100,
                role_filter_ids=role_filter_ids,
                start_time=start_time,
                end_time=end_time
            )

            user_stats = []
            for user_data in top_users:
                user_id = user_data.get('user_id')
                message_count = user_data.get('message_count', 0)

                if user_id and message_count > 0:
                    user_stats.append((str(user_id), message_count))

            return user_stats

        except Exception as e:
            logger.error(f"Error getting text leaderboard: {e}")
            traceback.print_exc()
            return []

    async def get_server_message_data(self, guild: discord.Guild, start_time: datetime = None, end_time: datetime = None,
                                      role_id: str = None):
        if not self.db_cog:
            logger.warning("DatabaseStats cog not available")
            return {"users": [], "channels": [], "message_categories": [], "voice_categories": []}

        result = {
            "users": [],
            "channels": [],
            "message_categories": [],
            "voice_categories": []
        }

        try:
            guild_id_int = int(guild.id)

            role_filter_ids = None
            if role_id and role_id != "none":
                role_id_int = int(role_id)
                role_filter_ids = [role_id_int]

            top_users = await self.db_cog.q_server_top3_users_messages(
                guild_id=guild_id_int,
                role_filter_ids=role_filter_ids,
                start_time=start_time,
                end_time=end_time
            )

            for user_data in top_users:
                user_id = user_data.get('user_id')
                message_count = user_data.get('message_count', 0)

                if user_id and message_count > 0:
                    result["users"].append((str(user_id), message_count))

            top_channels = await self.db_cog.q_leaderboard_server_top_text_channels(
                guild_id=guild_id_int,
                limit=100,
                role_filter_ids=role_filter_ids,
                start_time=start_time,
                end_time=end_time
            )

            for channel_data in top_channels:
                channel_id = channel_data.get('channel_id')
                message_count = channel_data.get('message_count', 0)

                if channel_id and message_count > 0:
                    result["channels"].append((str(channel_id), message_count))

            top_categories = await self.db_cog.q_leaderboard_server_top_categories_messages(
                guild_id=guild_id_int,
                limit=100,
                role_filter_ids=role_filter_ids,
                start_time=start_time,
                end_time=end_time
            )

            for category_data in top_categories:
                category_id = category_data.get('category_id')
                message_count = category_data.get('message_count', 0)

                if category_id and message_count > 0:
                    result["message_categories"].append(
                        (str(category_id), message_count))

        except Exception as e:
            logger.error(f"Error getting server message data: {e}")
            traceback.print_exc()

        return result

    async def get_server_voice_data(self, guild: discord.Guild, start_time: datetime = None, end_time: datetime = None,
                                    role_id: str = None):
        if not self.db_cog:
            logger.warning("DatabaseStats cog not available")
            return {"users": [], "channels": [], "voice_categories": []}

        result = {
            "users": [],
            "channels": [],
            "voice_categories": []
        }

        try:
            guild_id_int = int(guild.id)

            role_filter_ids = None
            if role_id and role_id != "none":
                role_id_int = int(role_id)
                role_filter_ids = [role_id_int]

            top_users = await self.db_cog.q_server_top3_users_voice(
                guild_id=guild_id_int,
                role_filter_ids=role_filter_ids,
                start_time=start_time,
                end_time=end_time
            )

            for user_data in top_users:
                user_id = user_data.get('user_id')
                total_seconds = user_data.get('total_seconds', 0)

                if user_id and total_seconds > 0:
                    result["users"].append((str(user_id), total_seconds))

            top_channels = await self.db_cog.q_leaderboard_server_top_voice_channels(
                guild_id=guild_id_int,
                limit=100,
                role_filter_ids=role_filter_ids,
                start_time=start_time,
                end_time=end_time
            )

            for channel_data in top_channels:
                channel_id = channel_data.get('channel_id')
                total_seconds = channel_data.get('total_seconds', 0)

                if channel_id and total_seconds > 0:
                    result["channels"].append((str(channel_id), total_seconds))

            top_categories = await self.db_cog.q_leaderboard_server_top_categories_voice(
                guild_id=guild_id_int,
                limit=100,
                role_filter_ids=role_filter_ids,
                start_time=start_time,
                end_time=end_time
            )

            for category_data in top_categories:
                category_id = category_data.get('category_id')
                total_seconds = category_data.get('total_seconds', 0)

                if category_id and total_seconds > 0:
                    result["voice_categories"].append(
                        (str(category_id), total_seconds))

        except Exception as e:
            logger.error(f"Error getting server voice data: {e}")
            traceback.print_exc()

        return result

    async def get_category_data(self, guild: discord.Guild, category: discord.CategoryChannel,
                                start_time: datetime = None, end_time: datetime = None, leaderboard_type: str = None, role_id: str = None):
        if not self.db_cog:
            logger.warning("DatabaseStats cog not available")
            return {"users": [], "channels": []}

        result = {
            "users": [],
            "channels": []
        }

        try:
            guild_id_int = int(guild.id)

            role_filter_ids = None
            if role_id and role_id != "none":
                role_id_int = int(role_id)
                role_filter_ids = [role_id_int]

            if leaderboard_type == "top_users_messages":
                top_users = await self.db_cog.q_leaderboard_category_users_messages(
                    guild_id=guild_id_int,
                    category_id=category.id,
                    limit=100,
                    role_filter_ids=role_filter_ids,
                    start_time=start_time,
                    end_time=end_time
                )

                for user_data in top_users:
                    user_id = user_data.get('user_id')
                    message_count = user_data.get('message_count', 0)

                    if user_id and message_count > 0:
                        result["users"].append((str(user_id), message_count))

            elif leaderboard_type == "top_users_voice":
                top_users = await self.db_cog.q_leaderboard_category_users_voice(
                    guild_id=guild_id_int,
                    category_id=category.id,
                    limit=100,
                    role_filter_ids=role_filter_ids,
                    start_time=start_time,
                    end_time=end_time
                )

                for user_data in top_users:
                    user_id = user_data.get('user_id')
                    total_seconds = user_data.get('total_seconds', 0)

                    if user_id and total_seconds > 0:
                        result["users"].append((str(user_id), total_seconds))

            elif leaderboard_type == "top_text_channels":
                top_channels = await self.db_cog.q_category_top5_text_channels(
                    guild_id=guild_id_int,
                    category_id=category.id,
                    role_filter_ids=role_filter_ids,
                    start_time=start_time,
                    end_time=end_time
                )

                for channel_data in top_channels:
                    channel_id = channel_data.get('channel_id')
                    message_count = channel_data.get('message_count', 0)

                    if channel_id and message_count > 0:
                        result["channels"].append(
                            (str(channel_id), message_count))

            elif leaderboard_type == "top_voice_channels":
                top_channels = await self.db_cog.q_category_top5_voice_channels(
                    guild_id=guild_id_int,
                    category_id=category.id,
                    role_filter_ids=role_filter_ids,
                    start_time=start_time,
                    end_time=end_time
                )

                for channel_data in top_channels:
                    channel_id = channel_data.get('channel_id')
                    total_seconds = channel_data.get('total_seconds', 0)

                    if channel_id and total_seconds > 0:
                        result["channels"].append(
                            (str(channel_id), total_seconds))

        except Exception as e:
            logger.error(f"Error getting category data: {e}")
            traceback.print_exc()

        return result

    async def get_role_leaderboard_data(self, guild: discord.Guild, start_time: datetime = None, end_time: datetime = None,
                                        leaderboard_type: str = None, channel: discord.abc.GuildChannel = None,
                                        category: discord.CategoryChannel = None, role_id: str = None):
        if not self.db_cog:
            logger.warning("DatabaseStats cog not available")
            return []

        try:
            guild_id_int = int(guild.id)

            role_filter_ids = None
            if role_id and role_id != "none":
                role_id_int = int(role_id)
                role_filter_ids = [role_id_int]

            if leaderboard_type == "top_roles_messages":
                if channel:
                    data = await self.db_cog.q_leaderboard_roles_messages_channel(
                        guild_id=guild_id_int,
                        channel_id=channel.id,
                        limit=100,
                        role_filter_ids=role_filter_ids,
                        start_time=start_time,
                        end_time=end_time
                    )
                elif category:
                    data = await self.db_cog.q_leaderboard_roles_messages_category(
                        guild_id=guild_id_int,
                        category_id=category.id,
                        limit=100,
                        role_filter_ids=role_filter_ids,
                        start_time=start_time,
                        end_time=end_time
                    )
                else:
                    data = await self.db_cog.q_leaderboard_roles_messages_server(
                        guild_id=guild_id_int,
                        limit=100,
                        role_filter_ids=role_filter_ids,
                        start_time=start_time,
                        end_time=end_time
                    )

                role_stats = []
                for role_data in data:
                    role_id_val = role_data.get('role_id')
                    message_count = role_data.get('message_count', 0)

                    if role_id_val and message_count > 0:
                        role_stats.append((str(role_id_val), message_count))

                return role_stats

            elif leaderboard_type == "top_roles_voice":
                if channel:
                    data = await self.db_cog.q_leaderboard_roles_voice_channel(
                        guild_id=guild_id_int,
                        channel_id=channel.id,
                        limit=100,
                        role_filter_ids=role_filter_ids,
                        start_time=start_time,
                        end_time=end_time
                    )
                elif category:
                    data = await self.db_cog.q_leaderboard_roles_voice_category(
                        guild_id=guild_id_int,
                        category_id=category.id,
                        limit=100,
                        role_filter_ids=role_filter_ids,
                        start_time=start_time,
                        end_time=end_time
                    )
                else:
                    data = await self.db_cog.q_leaderboard_roles_voice_server(
                        guild_id=guild_id_int,
                        limit=100,
                        role_filter_ids=role_filter_ids,
                        start_time=start_time,
                        end_time=end_time
                    )

                role_stats = []
                for role_data in data:
                    role_id_val = role_data.get('role_id')
                    total_seconds = role_data.get('total_seconds', 0)

                    if role_id_val and total_seconds > 0:
                        role_stats.append((str(role_id_val), total_seconds))

                return role_stats

            elif leaderboard_type == "top_roles_invites":
                if channel:
                    data = await self.db_cog.q_leaderboard_roles_invites_channel(
                        guild_id=guild_id_int,
                        channel_id=channel.id,
                        limit=100,
                        role_filter_ids=role_filter_ids,
                        start_time=start_time,
                        end_time=end_time
                    )
                elif category:
                    data = await self.db_cog.q_leaderboard_roles_invites_category(
                        guild_id=guild_id_int,
                        category_id=category.id,
                        limit=100,
                        role_filter_ids=role_filter_ids,
                        start_time=start_time,
                        end_time=end_time
                    )
                else:
                    data = await self.db_cog.q_leaderboard_roles_invites_server(
                        guild_id=guild_id_int,
                        limit=100,
                        role_filter_ids=role_filter_ids,
                        start_time=start_time,
                        end_time=end_time
                    )

                role_stats = []
                for role_data in data:
                    role_id_val = role_data.get('role_id')
                    valid_invites = role_data.get('valid_invites', 0)

                    if role_id_val and valid_invites > 0:
                        role_stats.append((str(role_id_val), valid_invites))

                return role_stats

            return []

        except Exception as e:
            logger.error(f"Error getting role leaderboard data: {e}")
            traceback.print_exc()
            return []

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def _handle_leaderboard_command(self, ctx_or_interaction, command_type, target=None, target_user=None, is_interaction=False):
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

            has_permission = await check_permission(ctx_or_interaction if is_interaction else type('obj', (object,), {'user': user, 'guild': guild, 'response': type('obj', (object,), {'is_done': lambda: False})()})())
            if not has_permission:
                if is_interaction:
                    await ctx_or_interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
                else:
                    await ctx_or_interaction.send("❌ You don't have permission to use this command.", delete_after=10)
                return

            if not self.db_cog:
                await self._wait_for_db_cog()

            if not self.db_cog:
                if is_interaction:
                    await ctx_or_interaction.followup.send("❌ Database connection not available. Please make sure the DatabaseStats cog is loaded.", ephemeral=True)
                else:
                    await ctx_or_interaction.send("❌ Database connection not available. Please make sure the DatabaseStats cog is loaded.", delete_after=10)
                return

            if is_interaction:
                await ctx_or_interaction.response.defer()

            pool = self.db_cog.pool if hasattr(self.db_cog, 'pool') else None

            start_time, end_time, display_text, days_back_equiv = await self.get_server_default_time_range(guild)

            if command_type == "server":
                data = await self.get_server_message_data(guild, start_time, end_time)
                leaderboard_data = data["users"]
                total_messages = sum(
                    count for _, count in leaderboard_data) if leaderboard_data else 0

                img_bytes = await generate_message_leaderboard_image(
                    guild=guild,
                    leaderboard_data=leaderboard_data,
                    target_name=UnicodeNormalizer.normalize_text(guild.name),
                    display_text=display_text,
                    total_value=total_messages,
                    page=0,
                    pool=pool,
                    cog=self
                )
                file = discord.File(
                    img_bytes, filename="server_leaderboard.png")
                view = ServerLeaderboardView(
                    self, guild, start_time=start_time, end_time=end_time, days_back_equiv=days_back_equiv, display_text=display_text, pool=pool, using_server_default=True)

            elif command_type == "channel":
                if target is None:
                    if is_interaction:
                        channel = ctx_or_interaction.channel
                    else:
                        channel = ctx_or_interaction.channel
                else:
                    channel = target

                if not isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
                    if is_interaction:
                        await ctx_or_interaction.followup.send("❌ Please select a text or voice channel.", ephemeral=True)
                    else:
                        await ctx_or_interaction.send("❌ Please select a text or voice channel.", delete_after=10)
                    return

                if isinstance(channel, discord.TextChannel):
                    leaderboard_type = "top_text_users"
                    leaderboard_data = await self.get_channel_text_leaderboard(guild, channel, start_time, end_time)
                    total_value = sum(
                        count for _, count in leaderboard_data) if leaderboard_data else 0

                    img_bytes = await generate_message_leaderboard_image(
                        guild=guild,
                        leaderboard_data=leaderboard_data,
                        target_name=f"#{UnicodeNormalizer.normalize_text(channel.name)}",
                        display_text=display_text,
                        total_value=total_value,
                        page=0,
                        pool=pool,
                        cog=self
                    )
                else:
                    leaderboard_type = "top_voice_users"
                    leaderboard_data = await self.get_channel_voice_leaderboard(guild, channel, start_time, end_time)
                    total_value = sum(
                        seconds for _, seconds in leaderboard_data) if leaderboard_data else 0

                    img_bytes = await generate_voice_leaderboard_image(
                        guild=guild,
                        leaderboard_data=leaderboard_data,
                        target_name=f"🔊{UnicodeNormalizer.normalize_text(channel.name)}",
                        display_text=display_text,
                        total_value=total_value,
                        page=0,
                        pool=pool,
                        cog=self
                    )

                file = discord.File(
                    img_bytes, filename="channel_leaderboard.png")
                view = ChannelLeaderboardView(
                    self, guild, channel, start_time=start_time, end_time=end_time, days_back_equiv=days_back_equiv, display_text=display_text, leaderboard_type=leaderboard_type, pool=pool, using_server_default=True)

            elif command_type == "category":
                if target is None:
                    if is_interaction:
                        channel = ctx_or_interaction.channel
                    else:
                        channel = ctx_or_interaction.channel

                    if hasattr(channel, 'category') and channel.category:
                        category = channel.category
                    else:
                        if is_interaction:
                            await ctx_or_interaction.followup.send("❌ This channel doesn't belong to a category. Please specify a category.", ephemeral=True)
                        else:
                            await ctx_or_interaction.send("❌ This channel doesn't belong to a category. Please specify a category.", delete_after=10)
                        return
                else:
                    category = target

                data = await self.get_category_data(guild, category, start_time, end_time, "top_text_channels")
                leaderboard_data = data["channels"]
                total_value = sum(
                    count for _, count in leaderboard_data) if leaderboard_data else 0

                img_bytes = await generate_message_leaderboard_image(
                    guild=guild,
                    leaderboard_data=leaderboard_data,
                    target_name=UnicodeNormalizer.normalize_text(
                        category.name),
                    display_text=display_text,
                    total_value=total_value,
                    page=0,
                    pool=pool,
                    data_type="channels",
                    cog=self
                )
                file = discord.File(
                    img_bytes, filename="category_leaderboard.png")
                view = CategoryLeaderboardView(
                    self, guild, category, start_time=start_time, end_time=end_time, days_back_equiv=days_back_equiv, display_text=display_text, pool=pool, using_server_default=True)

            elif command_type == "role":
                leaderboard_data = await self.get_role_leaderboard_data(
                    guild,
                    start_time,
                    end_time,
                    "top_roles_messages",
                    channel=target if isinstance(
                        target, (discord.TextChannel, discord.VoiceChannel)) else None,
                    category=target if isinstance(
                        target, discord.CategoryChannel) else None
                )

                total_value = sum(
                    value for _, value in leaderboard_data) if leaderboard_data else 0

                target_name = UnicodeNormalizer.normalize_text(guild.name)
                if target:
                    if isinstance(target, discord.TextChannel):
                        target_name = f"#{UnicodeNormalizer.normalize_text(target.name)}"
                    elif isinstance(target, discord.VoiceChannel):
                        target_name = f"🔊{UnicodeNormalizer.normalize_text(target.name)}"
                    elif isinstance(target, discord.CategoryChannel):
                        target_name = UnicodeNormalizer.normalize_text(
                            target.name)

                img_bytes = await generate_message_leaderboard_image(
                    guild=guild,
                    leaderboard_data=leaderboard_data,
                    target_name=target_name,
                    display_text=display_text,
                    total_value=total_value,
                    page=0,
                    pool=pool,
                    data_type="roles",
                    cog=self
                )
                file = discord.File(img_bytes, filename="role_leaderboard.png")
                view = RoleLeaderboardView(
                    self, guild, start_time=start_time, end_time=end_time, days_back_equiv=days_back_equiv, display_text=display_text, target=target, pool=pool, using_server_default=True)

            else:
                if is_interaction:
                    await ctx_or_interaction.followup.send("❌ Invalid command type.", ephemeral=True)
                else:
                    await ctx_or_interaction.send("❌ Invalid command type.", delete_after=10)
                return

            retention_alert_text = await self.db_cog.maybe_get_retention_alert(guild.id) if self.db_cog else None

            if is_interaction:
                msg = await send_method(content=retention_alert_text, file=file, view=view)
            else:
                msg = await send_method(content=retention_alert_text, file=file, view=view, delete_after=300)

            self.active_views[msg.id] = view

        except Exception as e:
            logger.error(f"Error in _handle_leaderboard_command: {e}")
            traceback.print_exc()
            if is_interaction:
                try:
                    await ctx_or_interaction.followup.send("❌ An error occurred while generating the leaderboard.", ephemeral=True)
                except:
                    pass
            else:
                try:
                    await ctx_or_interaction.send("❌ An error occurred while generating the leaderboard.", delete_after=10)
                except:
                    pass

    @commands.group(name="leaderboard", invoke_without_command=True)
    async def leaderboard_group_prefix(self, ctx: commands.Context):
        await ctx.send("Available leaderboard commands:\n"
                       "- `leaderboard server` or `ls` - Server-wide leaderboards\n"
                       "- `leaderboard channel [channel]` or `lch [channel]` - Channel leaderboards\n"
                       "- `leaderboard category [category]` or `lca [category]` - Category leaderboards\n"
                       "- `leaderboard role [channel/category]` or `lr [channel/category]` - Role leaderboards")

    @leaderboard_group_prefix.command(name="server")
    async def leaderboard_server_prefix(self, ctx: commands.Context):
        await self._handle_leaderboard_command(ctx, "server", is_interaction=False)

    @leaderboard_group_prefix.command(name="channel")
    async def leaderboard_channel_prefix(self, ctx: commands.Context, channel: Optional[Union[discord.TextChannel, discord.VoiceChannel]] = None):
        await self._handle_leaderboard_command(ctx, "channel", target=channel, is_interaction=False)

    @leaderboard_group_prefix.command(name="category")
    async def leaderboard_category_prefix(self, ctx: commands.Context, category: Optional[discord.CategoryChannel] = None):
        await self._handle_leaderboard_command(ctx, "category", target=category, is_interaction=False)

    @leaderboard_group_prefix.command(name="role")
    async def leaderboard_role_prefix(self, ctx: commands.Context, target: Optional[Union[discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel]] = None):
        await self._handle_leaderboard_command(ctx, "role", target=target, is_interaction=False)

    @commands.command(name="ls")
    async def leaderboard_server_shortcut(self, ctx: commands.Context):
        await self._handle_leaderboard_command(ctx, "server", is_interaction=False)

    @commands.command(name="lch")
    async def leaderboard_channel_shortcut(self, ctx: commands.Context, channel: Optional[Union[discord.TextChannel, discord.VoiceChannel]] = None):
        await self._handle_leaderboard_command(ctx, "channel", target=channel, is_interaction=False)

    @commands.command(name="lca")
    async def leaderboard_category_shortcut(self, ctx: commands.Context, category: Optional[discord.CategoryChannel] = None):
        await self._handle_leaderboard_command(ctx, "category", target=category, is_interaction=False)

    @commands.command(name="lr")
    async def leaderboard_role_shortcut(self, ctx: commands.Context, target: Optional[Union[discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel]] = None):
        await self._handle_leaderboard_command(ctx, "role", target=target, is_interaction=False)

    leaderboard_group = app_commands.Group(
        name="leaderboard", description="Various leaderboards")

    @leaderboard_group.command(name="channel", description="Show leaderboard for a specific channel")
    @app_commands.describe(channel="Select a text or voice channel to show leaderboard for (optional - defaults to current channel)")
    async def channel_leaderboard(self, interaction: discord.Interaction, channel: Optional[Union[discord.TextChannel, discord.VoiceChannel]] = None):
        await self._handle_leaderboard_command(interaction, "channel", target=channel, is_interaction=True)

    @leaderboard_group.command(name="server", description="Show server-wide leaderboards")
    async def server_leaderboard(self, interaction: discord.Interaction):
        await self._handle_leaderboard_command(interaction, "server", is_interaction=True)

    @leaderboard_group.command(name="category", description="Show category-specific leaderboards")
    @app_commands.describe(category="Select a category to show leaderboard for (optional - defaults to current channel's category)")
    async def category_leaderboard(self, interaction: discord.Interaction, category: Optional[discord.CategoryChannel] = None):
        await self._handle_leaderboard_command(interaction, "category", target=category, is_interaction=True)

    @leaderboard_group.command(name="role", description="Show top roles by messages, voice activity, or invites")
    @app_commands.describe(target="Optional: Show roles in a specific channel or category")
    async def role_leaderboard(self, interaction: discord.Interaction,
                               target: Optional[Union[discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel]] = None):
        await self._handle_leaderboard_command(interaction, "role", target=target, is_interaction=True)

    @channel_leaderboard.error
    @server_leaderboard.error
    @category_leaderboard.error
    @role_leaderboard.error
    async def leaderboard_error_handler(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        try:
            if isinstance(error, app_commands.CommandInvokeError):
                original = error.original
                if isinstance(original, discord.Forbidden):
                    if not interaction.response.is_done():
                        await interaction.response.send_message("❌ I don't have permission to send messages in this channel.", ephemeral=True)
                    else:
                        await interaction.followup.send("❌ I don't have permission to send messages in this channel.", ephemeral=True)
                elif isinstance(original, discord.HTTPException):
                    if not interaction.response.is_done():
                        await interaction.response.send_message(f"❌ Discord API error: {str(original)}", ephemeral=True)
                    else:
                        await interaction.followup.send(f"❌ Discord API error: {str(original)}", ephemeral=True)
                else:
                    logger.error(f"Leaderboard error: {original}")
                    traceback.print_exc()
                    if not interaction.response.is_done():
                        await interaction.response.send_message("❌ An unexpected error occurred. Please try again.", ephemeral=True)
                    else:
                        await interaction.followup.send("❌ An unexpected error occurred. Please try again.", ephemeral=True)
            else:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ Error: {str(error)}", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ Error: {str(error)}", ephemeral=True)
        except discord.errors.InteractionResponded:
            pass
        except Exception as e:
            logger.error(f"Error in error handler: {e}")
            traceback.print_exc()


async def setup(bot):
    await bot.add_cog(Leaderboards(bot))
