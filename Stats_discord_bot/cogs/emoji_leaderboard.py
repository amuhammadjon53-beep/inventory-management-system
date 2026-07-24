import discord
from discord.ext import commands
from discord import app_commands
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import re
import asyncio
import os
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
import io
import aiohttp
from pilmoji import Pilmoji
import traceback
import json
from pathlib import Path
import unicodedata
from .ratelimiter import RateLimiter, RateLimitType, rate_limited, get_rate_limiter
import gc
from discord.ext import tasks

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


# HELPER FUNCTIONS
def get_ordinal(n: int) -> str:
    """Get ordinal suffix for a number (e.g., 1st, 2nd, 3rd)"""
    if 10 <= n % 100 <= 20:
        return 'th'
    return {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')


def format_count_with_k(value):
    """Format a count, abbreviating thousands as e.g. 31.5k (one decimal max)."""
    try:
        if value >= 1000:
            return f"{value / 1000:.1f}k"
        return f"{value:,}"
    except Exception:
        return str(value)

# CONFIGURATION


class EmojiConfig:

    EMOJIS_PER_PAGE = 10
    USERS_PER_PAGE = 10
    MAX_ROLES_IN_SELECT = 25
    DEFAULT_DAYS_BACK = 14
    TIME_PERIODS = [7, 14, 30]
    MAX_CUSTOM_DAYS = 2000

    # Paths
    TEMPLATE_PATH = BASE_DIR / "assets" / "images" / "leaderboards final png.png"
    FONT_PATH = BASE_DIR / "assets" / "fonts" / "HorndonD.ttf"

    # Colors
    COLORS = {
        'gold': (255, 215, 0, 220),
        'silver': (192, 192, 192, 220),
        'bronze': (205, 127, 50, 220),
        'default': (93, 0, 136, 255),
        'background': (0, 0, 0, 220)
    }


# PAGE JUMP MODAL
class PageJumpModal(discord.ui.Modal, title='Jump to Page'):
    def __init__(self, view, total_pages):
        super().__init__(timeout=60)
        self.view = view
        self.total_pages = total_pages
        self.rate_limiter = get_rate_limiter()

        self.page_number = discord.ui.TextInput(
            label=f'Enter page number (1-{total_pages})',
            placeholder=f'1 to {total_pages}',
            min_length=1,
            max_length=4,
            required=True
        )
        self.add_item(self.page_number)

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
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


# FONTS

def get_fonts():

    try:
        custom_font_path = EmojiConfig.FONT_PATH
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


# TEXT NORMALIZATION

def normalize_text_for_display(text):
    normalized = unicodedata.normalize('NFKD', text)
    ascii_only = normalized.encode('ASCII', 'ignore').decode('ASCII')
    return ascii_only if ascii_only else text


# DRAWING FUNCTIONS

def draw_text_with_stroke_and_emoji(pilmoji, position, text, font, fill, stroke_fill="black", stroke_width=1):

    x, y = position

    for dx in [-stroke_width, 0, stroke_width]:
        for dy in [-stroke_width, 0, stroke_width]:
            if dx != 0 or dy != 0:
                pilmoji.text((x + dx, y + dy), text,
                             font=font, fill=stroke_fill)

    pilmoji.text((x, y), text, font=font, fill=fill)


def draw_text_centered_with_stroke_and_emoji(pilmoji, text, center_position, font, fill="white", stroke_fill="black", stroke_width=2, max_width=None):

    center_x, center_y = center_position

    temp_draw = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    bbox = temp_draw.textbbox((0, 0), text, font=font)
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
                bbox = temp_draw.textbbox((0, 0), text, font=smaller_font)
                text_width = bbox[2] - bbox[0]

                if text_width <= max_width:
                    text_height = bbox[3] - bbox[1]
                    x = center_x - (text_width // 2)
                    y = center_y - (text_height // 2)
                    draw_text_with_stroke_and_emoji(
                        pilmoji, (x, y), text, smaller_font, fill, stroke_fill, stroke_width)
                    return
            except:
                continue
    draw_text_with_stroke_and_emoji(pilmoji, (x, y), text, font, fill,
                                    stroke_fill, stroke_width)


# RECTANGLE FUNCTIONS

def draw_rounded_rectangle(draw, xy, radius, fill=None, outline=None):

    x1, y1, x2, y2 = xy
    draw.rectangle([x1 + radius, y1, x2 - radius, y2],
                   fill=fill, outline=outline)
    draw.rectangle([x1, y1 + radius, x2, y2 - radius],
                   fill=fill, outline=outline)
    draw.pieslice([x1, y1, x1 + radius * 2, y1 + radius * 2],
                  180, 270, fill=fill, outline=outline)
    draw.pieslice([x2 - radius * 2, y1, x2, y2 - radius * 2],
                  270, 360, fill=fill, outline=outline)
    draw.pieslice([x1, y2 - radius * 2, x1 + radius * 2, y2],
                  90, 180, fill=fill, outline=outline)
    draw.pieslice([x2 - radius * 2, y2 - radius * 2, x2, y2],
                  0, 90, fill=fill, outline=outline)


def fit_text_to_rectangle(draw, text, text_start_x, text_start_y, rect_center_x, rect_center_y, rect_width, rect_height, is_username=False):

    font_paths = [BASE_DIR / "assets" / "fonts" / "HorndonD.ttf"]

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


async def add_server_profile_pic_and_name(image, guild, font_huge, channel=None, category=None, target_member=None, target_location=None):

    temp_draw = ImageDraw.Draw(image)

    avatar_x, avatar_y = 7, 10
    avatar_size = (60, 60)

    text_start_x = 85
    text_start_y = 30

    rect_center_x = 150
    rect_center_y = 30
    rect_width = 183
    rect_height = 35

    try:
        if target_member:
            avatar_url = target_member.avatar.url if target_member.avatar else target_member.default_avatar.url
        elif guild.icon:
            avatar_url = guild.icon.url
        else:
            avatar_url = None

        if avatar_url:
            async with aiohttp.ClientSession() as session:
                async with session.get(avatar_url) as response:
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
        print(f"❌ Could not add avatar: {e}")

    with Pilmoji(image) as pilmoji:
        display_text = ""
        if target_member:
            display_text = target_member.name  # Use username instead of display name
        elif channel:
            display_text = f"#{normalize_text_for_display(channel.name)}"
        elif category:
            display_text = normalize_text_for_display(category.name)
        else:
            display_text = normalize_text_for_display(guild.name)

        fitted_text, text_font, text_pos = fit_text_to_rectangle(
            temp_draw,
            display_text,
            text_start_x,
            text_start_y,
            rect_center_x,
            rect_center_y,
            rect_width,
            rect_height,
            is_username=True
        )

        if fitted_text and text_font:
            draw_text_with_stroke_and_emoji(pilmoji, text_pos, fitted_text,
                                            font=text_font, fill="white", stroke_fill="black", stroke_width=1)
        else:
            draw_text_with_stroke_and_emoji(pilmoji, (text_start_x, text_start_y), display_text,
                                            font=font_huge, fill="white", stroke_fill="black", stroke_width=1)

        # Add location text at (360, 80) if target_location is provided
        if target_location:
            if isinstance(target_location, discord.TextChannel):
                location_text = f"in #{normalize_text_for_display(target_location.name)}"
            else:
                location_text = f"in {normalize_text_for_display(target_location.name)}"

            # Get font_small for 16px font size
            font_small, font_medium, font_large, font_larger, font_huge, font_giant = get_fonts()
            location_font = font_small  # 16px font size

            location_bbox = temp_draw.textbbox(
                (0, 0), location_text, font=location_font)
            location_width = location_bbox[2] - location_bbox[0]
            location_x = 370 - (location_width // 2)
            location_y = 70

            draw_text_with_stroke_and_emoji(pilmoji, (location_x, location_y), location_text,
                                            font=location_font, fill="white", stroke_fill="black", stroke_width=1)
            gc.collect()


async def generate_emoji_leaderboard_image(
    guild: discord.Guild,
    leaderboard_data: list,
    leaderboard_type: str,
    display_text: str,
    role_id: str = None,
    role_name: str = None,
    target_member: discord.Member = None,
    usage_type: str = 'all',
    page: int = 0,
    total_pages: int = 1,
    channel: discord.TextChannel = None,
    category: discord.CategoryChannel = None,
    target_location=None
):

    template_path = EmojiConfig.TEMPLATE_PATH
    try:
        image = Image.open(template_path)
    except FileNotFoundError:
        image = Image.new('RGB', (800, 600), color='#2F3136')
        print(f"❌ Template not found at: {template_path}")

    if image.mode != "RGB":
        image = image.convert("RGB")

    draw = ImageDraw.Draw(image)
    font_small, font_medium, font_large, font_larger, font_huge, font_giant = get_fonts()

    if target_member and (channel or category or target_location):
        await add_server_profile_pic_and_name(image, guild, font_huge, target_member=target_member, target_location=target_location)
    elif target_member:
        await add_server_profile_pic_and_name(image, guild, font_huge, target_member=target_member)
    elif leaderboard_type == 'channel' and channel:
        await add_server_profile_pic_and_name(image, guild, font_huge, channel=channel)
    elif leaderboard_type == 'category' and category:
        await add_server_profile_pic_and_name(image, guild, font_huge, category=category)
    else:
        await add_server_profile_pic_and_name(image, guild, font_huge)

    # USE DATABASE ROLE NAME INSTEAD OF DISCORD API
    role_text = role_name if role_name else "No Filter"

    with Pilmoji(image) as pilmoji:
        draw_text_with_stroke_and_emoji(pilmoji, (70, 424), role_text,
                                        font=font_small, fill="white", stroke_fill="black", stroke_width=1)
        draw_text_with_stroke_and_emoji(pilmoji, (630, 422), display_text,
                                        font=font_small, fill="white", stroke_fill="black", stroke_width=1)
        draw_text_with_stroke_and_emoji(pilmoji, (550, 38), datetime.now(timezone.utc).strftime(
            "%B %d, %Y"), font=font_small, fill="white", stroke_fill="black", stroke_width=1)

        draw_text_with_stroke_and_emoji(
            pilmoji, (400, 450), f"Page {page + 1}/{total_pages}", font=font_medium, fill="white", stroke_fill="black", stroke_width=1)

        if leaderboard_data:
            start_idx = page * EmojiConfig.EMOJIS_PER_PAGE
            end_idx = min(start_idx + EmojiConfig.EMOJIS_PER_PAGE,
                          len(leaderboard_data))
            page_data = leaderboard_data[start_idx:end_idx]

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

            for i, ((emoji_str, total_count, message_count, reaction_count), (box_x, box_y)) in enumerate(zip(page_data, positions)):
                global_rank = start_idx + i + 1

                draw_rounded_rectangle(draw, [box_x, box_y, box_x + box_width, box_y + box_height],
                                       radius=8, fill=EmojiConfig.COLORS['background'], outline=None)

                placement_width = 35
                if global_rank == 1:
                    placement_color = EmojiConfig.COLORS['gold']
                elif global_rank == 2:
                    placement_color = EmojiConfig.COLORS['silver']
                elif global_rank == 3:
                    placement_color = EmojiConfig.COLORS['bronze']
                else:
                    placement_color = EmojiConfig.COLORS['default']

                draw_rounded_rectangle(draw, [box_x, box_y, box_x + placement_width, box_y + box_height],
                                       radius=8, fill=placement_color, outline=None)

                total_uses = sum(count for _, count, _, _ in leaderboard_data)
                percentage = (total_count / total_uses) * \
                    100 if total_uses > 0 else 0
                value_text = f"{format_count_with_k(total_count)} uses ({percentage:.1f}%)"

                rank_text = f"#{global_rank}"
                rank_bbox = draw.textbbox((0, 0), rank_text, font=font_medium)
                rank_width = rank_bbox[2] - rank_bbox[0]

                value_bbox = draw.textbbox(
                    (0, 0), value_text, font=font_medium)
                value_width = value_bbox[2] - value_bbox[0]

                emoji_name = ""
                display_emoji = emoji_str

                if emoji_str.startswith('<') and emoji_str.endswith('>'):

                    emoji_parts = emoji_str.split(':')
                    if len(emoji_parts) >= 3:
                        emoji_name = emoji_parts[1]

                        emoji_id = emoji_parts[2][:-1]
                        guild_emoji = guild.get_emoji(int(emoji_id))
                        if guild_emoji:
                            display_emoji = str(guild_emoji)
                    else:
                        emoji_name = "custom"
                else:
                    emoji_name = ""

                emoji_space = 40
                if emoji_name:
                    name_bbox = draw.textbbox(
                        (0, 0), emoji_name, font=font_medium)
                    name_width = name_bbox[2] - name_bbox[0]
                    total_content_width = emoji_space + name_width + 10
                else:
                    total_content_width = emoji_space

                available_width = box_width - placement_width - value_width - 30

                name_font = font_medium
                if emoji_name and total_content_width > available_width:
                    try:
                        smaller_font = ImageFont.truetype(font_medium.path, 16) if hasattr(
                            font_medium, 'path') else font_small
                        smaller_bbox = draw.textbbox(
                            (0, 0), emoji_name, font=smaller_font)
                        smaller_width = smaller_bbox[2] - smaller_bbox[0]

                        if (emoji_space + smaller_width + 10) <= available_width:
                            name_font = smaller_font
                        else:

                            while len(emoji_name) > 3:
                                emoji_name = emoji_name[:-4] + "..."
                                truncated_bbox = draw.textbbox(
                                    (0, 0), emoji_name, font=name_font)
                                truncated_width = truncated_bbox[2] - \
                                    truncated_bbox[0]
                                if (emoji_space + truncated_width + 10) <= available_width:
                                    break
                    except:

                        while len(emoji_name) > 3 and (emoji_space + name_width + 10) > available_width:
                            emoji_name = emoji_name[:-4] + "..."
                            name_bbox = draw.textbbox(
                                (0, 0), emoji_name, font=name_font)
                            name_width = name_bbox[2] - name_bbox[0]

                rank_height = rank_bbox[3] - rank_bbox[1]
                value_height = value_bbox[3] - value_bbox[1]

                rank_y = box_y + (box_height - rank_height) // 2
                value_y = box_y + (box_height - value_height) // 2

                rank_x = box_x + (placement_width - rank_width) // 2
                draw_text_with_stroke_and_emoji(pilmoji, (rank_x, rank_y), rank_text,
                                                font=font_medium, fill="white", stroke_fill="black", stroke_width=1)

                emoji_x = box_x + placement_width + 5
                emoji_y = box_y + (box_height - 30) // 2 - 13

                try:
                    pilmoji.text((emoji_x, emoji_y), display_emoji,
                                 font=font_large, fill=(255, 255, 255))
                except Exception as e:
                    print(f"❌ Error drawing emoji {display_emoji}: {e}")
                    pilmoji.text((emoji_x, emoji_y), display_emoji,
                                 font=font_large, fill=(255, 255, 255))

                if emoji_name:
                    name_height = name_bbox[3] - name_bbox[1] if name_font == font_medium else draw.textbbox(
                        (0, 0), emoji_name, font=name_font)[3] - draw.textbbox((0, 0), emoji_name, font=name_font)[1]
                    name_y = box_y + (box_height - name_height) // 2
                    name_x = emoji_x + 35
                    draw_text_with_stroke_and_emoji(pilmoji, (name_x, name_y), emoji_name,
                                                    font=name_font, fill="white", stroke_fill="black", stroke_width=1)

                value_x = box_x + box_width - value_width - 8
                draw_text_with_stroke_and_emoji(pilmoji, (value_x, value_y), value_text,
                                                font=font_medium, fill="white", stroke_fill="black", stroke_width=1)
        else:
            cx, cy = image.size[0] // 2, image.size[1] // 2
            draw_text_centered_with_stroke_and_emoji(
                pilmoji, "NO DATA AVAILABLE", (cx, cy), font=font_giant, fill="white", stroke_fill="black", stroke_width=3)

    img_bytes = io.BytesIO()
    image.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    gc.collect()
    return img_bytes


async def generate_user_emoji_leaderboard_image(
    guild: discord.Guild,
    user_data: list,
    display_text: str,
    role_id: str = None,
    role_name: str = None,
    usage_type: str = "all",
    page: int = 0,
    total_pages: int = 1,
    target_channel: discord.TextChannel = None,
    target_category: discord.CategoryChannel = None,
    target_location=None,
    cog=None
):

    template_path = EmojiConfig.TEMPLATE_PATH
    try:
        image = Image.open(template_path)
    except FileNotFoundError:
        image = Image.new('RGB', (800, 600), color='#2F3136')
        print(f"❌ Template not found at: {template_path}")

    if image.mode != "RGB":
        image = image.convert("RGB")

    draw = ImageDraw.Draw(image)
    font_small, font_medium, font_large, font_larger, font_huge, font_giant = get_fonts()

    if target_location:
        await add_server_profile_pic_and_name(image, guild, font_huge, target_location=target_location)
    elif target_channel:
        await add_server_profile_pic_and_name(image, guild, font_huge, channel=target_channel)
    elif target_category:
        await add_server_profile_pic_and_name(image, guild, font_huge, category=target_category)
    else:
        await add_server_profile_pic_and_name(image, guild, font_huge)

    # USE DATABASE ROLE NAME INSTEAD OF DISCORD API
    role_text = role_name if role_name else "No Filter"

    with Pilmoji(image) as pilmoji:
        draw_text_with_stroke_and_emoji(pilmoji, (70, 424), role_text,
                                        font=font_small, fill="white", stroke_fill="black", stroke_width=1)
        draw_text_with_stroke_and_emoji(pilmoji, (630, 422), display_text,
                                        font=font_small, fill="white", stroke_fill="black", stroke_width=1)
        draw_text_with_stroke_and_emoji(pilmoji, (550, 38), datetime.now(timezone.utc).strftime(
            "%B %d, %Y"), font=font_small, fill="white", stroke_fill="black", stroke_width=1)

        draw_text_with_stroke_and_emoji(
            pilmoji, (400, 450), f"Page {page + 1}/{total_pages}", font=font_medium, fill="white", stroke_fill="black", stroke_width=1)

        if user_data:
            start_idx = page * EmojiConfig.USERS_PER_PAGE
            end_idx = min(start_idx + EmojiConfig.USERS_PER_PAGE,
                          len(user_data))
            page_data = user_data[start_idx:end_idx]

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

            for i, ((user_id, total_count, message_count, reaction_count), (box_x, box_y)) in enumerate(zip(page_data, positions)):
                global_rank = start_idx + i + 1

                draw_rounded_rectangle(draw, [box_x, box_y, box_x + box_width, box_y + box_height],
                                       radius=8, fill=EmojiConfig.COLORS['background'], outline=None)

                placement_width = 35
                if global_rank == 1:
                    placement_color = EmojiConfig.COLORS['gold']
                elif global_rank == 2:
                    placement_color = EmojiConfig.COLORS['silver']
                elif global_rank == 3:
                    placement_color = EmojiConfig.COLORS['bronze']
                else:
                    placement_color = EmojiConfig.COLORS['default']

                draw_rounded_rectangle(draw, [box_x, box_y, box_x + placement_width, box_y + box_height],
                                       radius=8, fill=placement_color, outline=None)

                total_uses = sum(count for _, count, _, _ in user_data)
                percentage = (total_count / total_uses) * \
                    100 if total_uses > 0 else 0
                value_text = f"{format_count_with_k(total_count)} uses ({percentage:.1f}%)"

                rank_text = f"#{global_rank}"
                rank_bbox = draw.textbbox((0, 0), rank_text, font=font_medium)
                rank_width = rank_bbox[2] - rank_bbox[0]

                value_bbox = draw.textbbox(
                    (0, 0), value_text, font=font_medium)
                value_width = value_bbox[2] - value_bbox[0]

                # Get username - ONLY rate limit the fallback when user left
                member = guild.get_member(user_id)
                if member:
                    # User is still in server - NO rate limiting
                    username = member.name
                else:
                    # User left the server - ONLY rate limit this fallback
                    @rate_limited(RateLimitType.API, timeout=1.0)
                    async def fetch_user_limited(uid):
                        if cog and cog.bot:
                            return await cog.bot.fetch_user(uid)
                        return None

                    try:
                        # Need to run the async function
                        loop = asyncio.get_event_loop()
                        user = await fetch_user_limited(user_id)
                        if user:
                            username = user.name
                        else:
                            username = f"Unknown User ({user_id})"
                    except discord.NotFound:
                        username = "[Deleted User]"
                    except Exception:
                        username = f"Unknown User ({user_id})"

                available_width = box_width - placement_width - value_width - 30

                name_bbox = draw.textbbox((0, 0), username, font=font_medium)
                name_width = name_bbox[2] - name_bbox[0]

                name_font = font_medium
                if name_width > available_width:
                    try:
                        smaller_font = ImageFont.truetype(font_medium.path, 16) if hasattr(
                            font_medium, 'path') else font_small
                        smaller_bbox = draw.textbbox(
                            (0, 0), username, font=smaller_font)
                        smaller_width = smaller_bbox[2] - smaller_bbox[0]

                        if smaller_width <= available_width:
                            name_font = smaller_font
                        else:
                            display_name = username
                            while len(display_name) > 3:
                                display_name = display_name[:-4] + "..."
                                truncated_bbox = draw.textbbox(
                                    (0, 0), display_name, font=name_font)
                                truncated_width = truncated_bbox[2] - \
                                    truncated_bbox[0]
                                if truncated_width <= available_width:
                                    username = display_name
                                    break
                    except:
                        display_name = username
                        while len(display_name) > 3 and name_width > available_width:
                            display_name = display_name[:-4] + "..."
                            name_bbox = draw.textbbox(
                                (0, 0), display_name, font=name_font)
                            name_width = name_bbox[2] - name_bbox[0]
                        username = display_name

                rank_height = rank_bbox[3] - rank_bbox[1]
                name_height = name_bbox[3] - name_bbox[1] if name_font == font_medium else draw.textbbox(
                    (0, 0), username, font=name_font)[3] - draw.textbbox((0, 0), username, font=name_font)[1]
                value_height = value_bbox[3] - value_bbox[1]

                rank_y = box_y + (box_height - rank_height) // 2
                name_y = box_y + (box_height - name_height) // 2
                value_y = box_y + (box_height - value_height) // 2

                rank_x = box_x + (placement_width - rank_width) // 2
                draw_text_with_stroke_and_emoji(pilmoji, (rank_x, rank_y), rank_text,
                                                font=font_medium, fill="white", stroke_fill="black", stroke_width=1)

                name_x = box_x + placement_width + 8
                draw_text_with_stroke_and_emoji(pilmoji, (name_x, name_y), username,
                                                font=name_font, fill="white", stroke_fill="black", stroke_width=1)

                value_x = box_x + box_width - value_width - 8
                draw_text_with_stroke_and_emoji(pilmoji, (value_x, value_y), value_text,
                                                font=font_medium, fill="white", stroke_fill="black", stroke_width=1)
        else:
            cx, cy = image.size[0] // 2, image.size[1] // 2
            draw_text_centered_with_stroke_and_emoji(
                pilmoji, "NO DATA AVAILABLE", (cx, cy), font=font_giant, fill="white", stroke_fill="black", stroke_width=3)

    img_bytes = io.BytesIO()
    image.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    gc.collect()
    return img_bytes


# PERMISSION CHECK FUNCTIONS

async def check_emoji_permission(interaction: discord.Interaction, target_user: discord.Member = None) -> bool:
    """Check if user has permission to use emoji commands"""
    # Get Settings cog
    settings_cog = interaction.client.get_cog('Settings')
    if not settings_cog or not settings_cog.initialized:
        # If Settings cog not available, allow command
        return True

    # Get guild settings
    settings = await settings_cog.get_guild_settings(interaction.guild_id)
    permission_level = settings.get('permission_level', 'Default')

    # Users with Administrator permission bypass all restrictions
    if interaction.user.guild_permissions.administrator:
        return True

    # Check permission levels
    if permission_level == 'All':
        return True

    elif permission_level == 'Default':
        # Default allows anyone to use commands
        return True

    elif permission_level == 'User Restriction':
        # User can only use commands on themselves
        if target_user and target_user.id != interaction.user.id:
            embed = discord.Embed(
                title="❌ Permission Denied",
                description="Sorry! You can only use this command on yourself.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        return True

    elif permission_level == 'Admin':
        # Only users with Administrator permission
        if not interaction.user.guild_permissions.administrator:
            embed = discord.Embed(
                title="❌ Permission Denied",
                description="Sorry! You need the `Administrator` permission to access this command.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        return True

    elif permission_level == 'Moderator':
        # Only users with Manage Server permission
        if not interaction.user.guild_permissions.manage_guild:
            embed = discord.Embed(
                title="❌ Permission Denied",
                description="Sorry! You need the `Manage Server` permission to access this command.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return False
        return True

    # Default fallback - allow command
    return True


async def check_prefix_emoji_permission(ctx, target_user: discord.Member = None) -> bool:
    """Check if user has permission to use emoji commands for prefix"""
    # Get Settings cog
    settings_cog = ctx.bot.get_cog('Settings')
    if not settings_cog or not settings_cog.initialized:
        return True

    # Get guild settings - use await directly
    settings = await settings_cog.get_guild_settings(ctx.guild.id)

    permission_level = settings.get('permission_level', 'Default')

    # Users with Administrator permission bypass all restrictions
    if ctx.author.guild_permissions.administrator:
        return True

    # Check permission levels
    if permission_level == 'All':
        return True
    elif permission_level == 'Default':
        return True
    elif permission_level == 'User Restriction':
        # User can only use commands on themselves
        if target_user and target_user.id != ctx.author.id:
            return False
        return True
    elif permission_level == 'Admin':
        # Only users with Administrator permission
        if not ctx.author.guild_permissions.administrator:
            return False
        return True
    elif permission_level == 'Moderator':
        # Only users with Manage Server permission
        if not ctx.author.guild_permissions.manage_guild:
            return False
        return True

    return True


# USAGE TYPE SELECT MENU

class UsageTypeSelectMenu(discord.ui.Select):
    def __init__(self, current_usage_type: str = 'all'):
        options = [
            discord.SelectOption(
                label="All Usage",
                value="all",
                description="Show all emoji usage",
                emoji="📊",
                default=(current_usage_type == 'all')
            ),
            discord.SelectOption(
                label="Messages Only",
                value="message",
                description="Show emojis used in messages",
                emoji="💬",
                default=(current_usage_type == 'message')
            ),
            discord.SelectOption(
                label="Reactions Only",
                value="reaction",
                description="Show emojis used as reactions",
                emoji="❤️",
                default=(current_usage_type == 'reaction')
            )
        ]

        super().__init__(
            placeholder="Filter by usage type...",
            options=options,
            custom_id="usage_type_select",
            min_values=1,
            max_values=1
        )
        self.rate_limiter = get_rate_limiter()

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False, thinking=False)
        view = self.view
        if hasattr(view, 'usage_type'):
            view.usage_type = self.values[0]
            view.page = 0
            await view.update_message(interaction)


# ROLE INPUT BUTTON AND MODAL

class RoleInputButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label="Filter By Role",
            custom_id="role_input_button"
        )
        self.rate_limiter = get_rate_limiter()

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def callback(self, interaction: discord.Interaction):
        modal = RoleInputModal(self.view)
        await interaction.response.send_modal(modal)


class RoleInputModal(discord.ui.Modal, title="Enter Role ID"):
    def __init__(self, view):
        super().__init__(timeout=300)
        self.view = view
        self.rate_limiter = get_rate_limiter()

        self.role_id_input = discord.ui.TextInput(
            label="Role ID",
            placeholder="Enter the role ID to filter by...",
            default=self.view.selected_role_id if self.view.selected_role_id != "none" else "",
            min_length=1,
            max_length=20,
            required=True
        )
        self.add_item(self.role_id_input)

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            role_id = self.role_id_input.value.strip()

            if role_id.lower() == "none" or role_id == "":
                self.view.selected_role_id = "none"
                self.view.using_server_default = False
                self.view.page = 0
                await interaction.response.defer(ephemeral=False, thinking=False)
                await self.view.update_message(interaction)
                return

            role = self.view.guild.get_role(int(role_id))
            if role:
                self.view.selected_role_id = role_id
                self.view.using_server_default = False
                self.view.page = 0
                await interaction.response.defer(ephemeral=False, thinking=False)
                await self.view.update_message(interaction)
            else:
                embed = discord.Embed(
                    title="Invalid Role ID",
                    description="Sorry! The role id you inputted is not valid, please try again.",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)

        except ValueError:
            embed = discord.Embed(
                title="Invalid Input",
                description="Please enter a valid numeric role ID.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            embed = discord.Embed(
                title="Error",
                description="An error occurred while processing your request.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


# BUTTONS

class EmojiPrevButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary,
                         emoji=discord.PartialEmoji(name="arrowleft", id=1521149181207777331), custom_id="emoji_leaderboard_prev")
        self.rate_limiter = get_rate_limiter()

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
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


class EmojiNextButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary,
                         emoji=discord.PartialEmoji(name="arrowright", id=1521149211373076501), custom_id="emoji_leaderboard_next")
        self.rate_limiter = get_rate_limiter()

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def callback(self, interaction: discord.Interaction):
        if self.disabled:
            await interaction.response.defer(ephemeral=True, thinking=False)
            return

        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False, thinking=False)

        view = self.view
        view.page += 1
        await view.update_message(interaction)


class EmojiPageIndicator(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary,
                         label="Page 1/1", custom_id="emoji_leaderboard_page", disabled=False)
        self.rate_limiter = get_rate_limiter()

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def callback(self, interaction: discord.Interaction):
        view = self.view

        # Get total pages based on current data
        if isinstance(view, EmojiLeaderboardView):
            total_items = len(view.last_emoji_data) if hasattr(
                view, 'last_emoji_data') else 0
            items_per_page = EmojiConfig.EMOJIS_PER_PAGE
        elif isinstance(view, UserEmojiLeaderboardView):
            total_items = len(view.last_user_data) if hasattr(
                view, 'last_user_data') else 0
            items_per_page = EmojiConfig.USERS_PER_PAGE
        elif isinstance(view, ChannelEmojiLeaderboardView):
            total_items = len(view.last_emoji_data) if hasattr(
                view, 'last_emoji_data') else 0
            items_per_page = EmojiConfig.EMOJIS_PER_PAGE
        elif isinstance(view, CategoryEmojiLeaderboardView):
            total_items = len(view.last_emoji_data) if hasattr(
                view, 'last_emoji_data') else 0
            items_per_page = EmojiConfig.EMOJIS_PER_PAGE
        elif isinstance(view, UserSpecificEmojiLeaderboardView):
            total_items = len(view.last_emoji_data) if hasattr(
                view, 'last_emoji_data') else 0
            items_per_page = EmojiConfig.EMOJIS_PER_PAGE
        else:
            total_items = 0
            items_per_page = 10

        total_pages = max(
            1, (total_items + items_per_page - 1) // items_per_page)

        modal = PageJumpModal(view, total_pages)
        await interaction.response.send_modal(modal)


class RefreshButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary,
                         emoji=discord.PartialEmoji(name="refresh", id=1518249841505861743), custom_id="emoji_stats_refresh")
        self.rate_limiter = get_rate_limiter()

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.view.update_message(interaction)


class TimeSettingsButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary,
                         emoji=discord.PartialEmoji(name="clockk", id=1518249803069259867), custom_id="emoji_stats_time_settings")
        self.rate_limiter = get_rate_limiter()

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.view.show_time_buttons = not self.view.show_time_buttons
        await self.view.update_message(interaction)


class AllTimeButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="All Time", custom_id="emoji_stats_all_time"
        )
        self.rate_limiter = get_rate_limiter()

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        now = datetime.now(timezone.utc)
        self.view.start_time = None
        self.view.end_time = now
        self.view.days_back_equiv = 999999
        self.view.display_text = "All Time"
        self.view.using_server_default = False
        self.view.page = 0
        self.view.show_time_buttons = False
        await self.view.update_message(interaction)


class Days7Button(discord.ui.Button):
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="7 Days", custom_id="emoji_stats_days_7"
        )
        self.rate_limiter = get_rate_limiter()

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        now = datetime.now(timezone.utc)
        self.view.start_time = now - timedelta(days=7)
        self.view.end_time = now
        self.view.days_back_equiv = 7
        self.view.display_text = "7 days"
        self.view.using_server_default = False
        self.view.page = 0
        self.view.show_time_buttons = False
        await self.view.update_message(interaction)


class Days14Button(discord.ui.Button):
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="14 Days", custom_id="emoji_stats_days_14"
        )
        self.rate_limiter = get_rate_limiter()

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        now = datetime.now(timezone.utc)
        self.view.start_time = now - timedelta(days=14)
        self.view.end_time = now
        self.view.days_back_equiv = 14
        self.view.display_text = "14 days"
        self.view.using_server_default = False
        self.view.page = 0
        self.view.show_time_buttons = False
        await self.view.update_message(interaction)


class Days30Button(discord.ui.Button):
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="30 Days", custom_id="emoji_stats_days_30"
        )
        self.rate_limiter = get_rate_limiter()

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        now = datetime.now(timezone.utc)
        self.view.start_time = now - timedelta(days=30)
        self.view.end_time = now
        self.view.days_back_equiv = 30
        self.view.display_text = "30 days"
        self.view.using_server_default = False
        self.view.page = 0
        self.view.show_time_buttons = False
        await self.view.update_message(interaction)


class DaysCustomButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.success,
            label="Custom", custom_id="emoji_stats_days_custom"
        )
        self.rate_limiter = get_rate_limiter()

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def callback(self, interaction: discord.Interaction):
        modal = CustomDaysModal(self.view)
        await interaction.response.send_modal(modal)


class CustomDaysModal(discord.ui.Modal, title="Custom Time Range"):
    def __init__(self, view):
        super().__init__(timeout=300)
        self.view = view
        self.rate_limiter = get_rate_limiter()

        self.days_input = discord.ui.TextInput(
            label="Number of Days",
            placeholder="Enter number of days (max 2000)",
            default=str(
                self.view.days_back_equiv) if self.view.days_back_equiv != 999999 else "",
            min_length=1,
            max_length=4,
            required=True
        )
        self.add_item(self.days_input)

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            days = int(self.days_input.value)
            if days <= 0:
                await interaction.response.send_message("Please enter a positive number.", ephemeral=True)
                return
            if days > EmojiConfig.MAX_CUSTOM_DAYS:
                await interaction.response.send_message(f"Maximum is {EmojiConfig.MAX_CUSTOM_DAYS} days.", ephemeral=True)
                return

            await interaction.response.defer(ephemeral=False, thinking=False)
            now = datetime.now(timezone.utc)
            self.view.start_time = now - timedelta(days=days)
            self.view.end_time = now
            self.view.days_back_equiv = days
            self.view.display_text = f"{days} days"
            self.view.using_server_default = False
            self.view.page = 0
            self.view.show_time_buttons = False
            await self.view.update_message(interaction)

        except ValueError:
            await interaction.response.send_message("Please enter a valid number.", ephemeral=True)


# EMOJI LEADERBOARD VIEW

class EmojiLeaderboardView(discord.ui.View):
    def __init__(self, cog_instance, guild: discord.Guild, start_time: datetime = None, end_time: datetime = None,
                 days_back_equiv: int = 14, display_text: str = "14 days", page: int = 0, selected_role_id: str = None,
                 usage_type: str = 'all', using_server_default: bool = True):
        super().__init__(timeout=600)
        self.cog = cog_instance
        self.guild = guild
        self.start_time = start_time
        self.end_time = end_time if end_time else datetime.now(timezone.utc)
        self.days_back_equiv = days_back_equiv
        self.display_text = display_text
        self.page = page
        self.selected_role_id = selected_role_id
        self.usage_type = usage_type
        self.show_time_buttons = False
        self.using_server_default = using_server_default
        self.last_emoji_data = []
        self.message = None

    async def _update_buttons(self, total_pages: int = 1):
        self.clear_items()

        self.add_item(UsageTypeSelectMenu(self.usage_type))

        prev_button = EmojiPrevButton()
        next_button = EmojiNextButton()
        page_indicator = EmojiPageIndicator()

        prev_button.disabled = (self.page == 0 or total_pages <= 1)
        next_button.disabled = (
            self.page >= total_pages - 1 or total_pages <= 1)
        page_indicator.label = f"Page {self.page + 1}/{total_pages}"

        self.add_item(prev_button)
        self.add_item(page_indicator)
        self.add_item(next_button)

        self.add_item(RoleInputButton())

        self.add_item(RefreshButton())

        self.add_item(TimeSettingsButton())

        if self.show_time_buttons:
            self.add_item(AllTimeButton())
            self.add_item(Days7Button())
            self.add_item(Days14Button())
            self.add_item(Days30Button())
            self.add_item(DaysCustomButton())

    async def generate_image(self):
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

        self.last_emoji_data = await self.cog.get_emoji_stats(
            self.guild, self.start_time, self.end_time, self.usage_type, self.selected_role_id)

        total_emojis = len(self.last_emoji_data)
        total_pages = max(
            1, (total_emojis + EmojiConfig.EMOJIS_PER_PAGE - 1) // EmojiConfig.EMOJIS_PER_PAGE)

        if self.page >= total_pages:
            self.page = max(0, total_pages - 1)

        return await generate_emoji_leaderboard_image(
            guild=self.guild,
            leaderboard_data=self.last_emoji_data,
            leaderboard_type='server',
            display_text=self.display_text,
            role_id=self.selected_role_id,
            role_name=role_name,
            usage_type=self.usage_type,
            page=self.page,
            total_pages=total_pages
        ), total_pages

    async def update_message(self, interaction: discord.Interaction = None):
        try:
            img_bytes, total_pages = await self.generate_image()
            await self._update_buttons(total_pages)

            file = discord.File(img_bytes, filename="emoji_leaderboard.png")

            if interaction:
                await interaction.edit_original_response(attachments=[file], view=self)
            elif self.message:
                await self.message.edit(attachments=[file], view=self)

        except Exception as e:
            print(f"Error updating emoji leaderboard message: {e}")
            try:
                if interaction:
                    await interaction.followup.send("❌ An error occurred while updating the leaderboard.", ephemeral=True)
            except:
                pass


# EMOJI USER LEADERBOARD VIEW

class UserEmojiLeaderboardView(discord.ui.View):
    def __init__(self, cog_instance, guild: discord.Guild, start_time: datetime = None, end_time: datetime = None,
                 days_back_equiv: int = 14, display_text: str = "14 days", page: int = 0, selected_role_id: str = None,
                 usage_type: str = 'all', target_location=None, using_server_default: bool = True):
        super().__init__(timeout=600)
        self.cog = cog_instance
        self.guild = guild
        self.start_time = start_time
        self.end_time = end_time if end_time else datetime.now(timezone.utc)
        self.days_back_equiv = days_back_equiv
        self.display_text = display_text
        self.page = page
        self.selected_role_id = selected_role_id
        self.usage_type = usage_type
        self.target_location = target_location
        self.using_server_default = using_server_default
        self.last_user_data = []
        self.show_time_buttons = False
        self.message = None

    async def _update_buttons(self, total_pages: int = 1):
        self.clear_items()

        self.add_item(UsageTypeSelectMenu(self.usage_type))

        prev_button = EmojiPrevButton()
        next_button = EmojiNextButton()
        page_indicator = EmojiPageIndicator()

        prev_button.disabled = (self.page == 0 or total_pages <= 1)
        next_button.disabled = (
            self.page >= total_pages - 1 or total_pages <= 1)
        page_indicator.label = f"Page {self.page + 1}/{total_pages}"

        self.add_item(prev_button)
        self.add_item(page_indicator)
        self.add_item(next_button)

        self.add_item(RoleInputButton())

        self.add_item(RefreshButton())

        self.add_item(TimeSettingsButton())

        if self.show_time_buttons:
            self.add_item(AllTimeButton())
            self.add_item(Days7Button())
            self.add_item(Days14Button())
            self.add_item(Days30Button())
            self.add_item(DaysCustomButton())

    async def generate_image(self):
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

        if self.target_location:
            if isinstance(self.target_location, discord.TextChannel):
                self.last_user_data = await self.cog.get_user_emoji_stats(
                    self.guild, self.start_time, self.end_time, self.usage_type, self.selected_role_id,
                    channel_id=self.target_location.id)
            elif isinstance(self.target_location, discord.CategoryChannel):
                self.last_user_data = await self.cog.get_user_emoji_stats(
                    self.guild, self.start_time, self.end_time, self.usage_type, self.selected_role_id,
                    category_id=self.target_location.id)
            else:
                self.last_user_data = await self.cog.get_user_emoji_stats(
                    self.guild, self.start_time, self.end_time, self.usage_type, self.selected_role_id)
        else:
            self.last_user_data = await self.cog.get_user_emoji_stats(
                self.guild, self.start_time, self.end_time, self.usage_type, self.selected_role_id)

        total_users = len(self.last_user_data)
        total_pages = max(
            1, (total_users + EmojiConfig.USERS_PER_PAGE - 1) // EmojiConfig.USERS_PER_PAGE)

        if self.page >= total_pages:
            self.page = max(0, total_pages - 1)

        return await generate_user_emoji_leaderboard_image(
            guild=self.guild,
            user_data=self.last_user_data,
            display_text=self.display_text,
            role_id=self.selected_role_id,
            role_name=role_name,
            usage_type=self.usage_type,
            page=self.page,
            total_pages=total_pages,
            target_location=self.target_location,
            cog=self.cog
        ), total_pages

    async def update_message(self, interaction: discord.Interaction = None):
        try:
            img_bytes, total_pages = await self.generate_image()
            await self._update_buttons(total_pages)

            file = discord.File(
                img_bytes, filename="user_emoji_leaderboard.png")

            if interaction:
                await interaction.edit_original_response(attachments=[file], view=self)
            elif self.message:
                await self.message.edit(attachments=[file], view=self)

        except Exception as e:
            print(f"Error updating user emoji leaderboard message: {e}")
            try:
                if interaction:
                    await interaction.followup.send("❌ An error occurred while updating the leaderboard.", ephemeral=True)
            except:
                pass


# EMOJI CHANNEL LEADERBOARD VIEW
class ChannelEmojiLeaderboardView(discord.ui.View):
    def __init__(self, cog_instance, guild: discord.Guild, channel: discord.TextChannel,
                 start_time: datetime = None, end_time: datetime = None, days_back_equiv: int = 14,
                 display_text: str = "14 days", page: int = 0, selected_role_id: str = None,
                 usage_type: str = 'all', using_server_default: bool = True):
        super().__init__(timeout=600)
        self.cog = cog_instance
        self.guild = guild
        self.channel = channel
        self.start_time = start_time
        self.end_time = end_time if end_time else datetime.now(timezone.utc)
        self.days_back_equiv = days_back_equiv
        self.display_text = display_text
        self.page = page
        self.selected_role_id = selected_role_id
        self.usage_type = usage_type
        self.using_server_default = using_server_default
        self.last_emoji_data = []
        self.show_time_buttons = False
        self.message = None

    async def _update_buttons(self, total_pages: int = 1):
        self.clear_items()

        self.add_item(UsageTypeSelectMenu(self.usage_type))

        prev_button = EmojiPrevButton()
        next_button = EmojiNextButton()
        page_indicator = EmojiPageIndicator()

        prev_button.disabled = (self.page == 0 or total_pages <= 1)
        next_button.disabled = (
            self.page >= total_pages - 1 or total_pages <= 1)
        page_indicator.label = f"Page {self.page + 1}/{total_pages}"

        self.add_item(prev_button)
        self.add_item(page_indicator)
        self.add_item(next_button)

        self.add_item(RoleInputButton())

        self.add_item(RefreshButton())

        self.add_item(TimeSettingsButton())

        if self.show_time_buttons:
            self.add_item(AllTimeButton())
            self.add_item(Days7Button())
            self.add_item(Days14Button())
            self.add_item(Days30Button())
            self.add_item(DaysCustomButton())

    async def generate_image(self):
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

        self.last_emoji_data = await self.cog.get_channel_emoji_stats(
            self.guild, self.channel.id, self.start_time, self.end_time, self.usage_type, self.selected_role_id)

        total_emojis = len(self.last_emoji_data)
        total_pages = max(
            1, (total_emojis + EmojiConfig.EMOJIS_PER_PAGE - 1) // EmojiConfig.EMOJIS_PER_PAGE)

        if self.page >= total_pages:
            self.page = max(0, total_pages - 1)

        return await generate_emoji_leaderboard_image(
            guild=self.guild,
            leaderboard_data=self.last_emoji_data,
            leaderboard_type='channel',
            display_text=self.display_text,
            role_id=self.selected_role_id,
            role_name=role_name,
            usage_type=self.usage_type,
            page=self.page,
            total_pages=total_pages,
            channel=self.channel
        ), total_pages

    async def update_message(self, interaction: discord.Interaction = None):
        try:
            img_bytes, total_pages = await self.generate_image()
            await self._update_buttons(total_pages)

            file = discord.File(
                img_bytes, filename="channel_emoji_leaderboard.png")

            if interaction:
                await interaction.edit_original_response(attachments=[file], view=self)
            elif self.message:
                await self.message.edit(attachments=[file], view=self)

        except Exception as e:
            print(f"Error updating channel emoji leaderboard message: {e}")
            try:
                if interaction:
                    await interaction.followup.send("❌ An error occurred while updating the leaderboard.", ephemeral=True)
            except:
                pass


# EMOJI CATEGORY LEADERBOARD VIEW
class CategoryEmojiLeaderboardView(discord.ui.View):
    def __init__(self, cog_instance, guild: discord.Guild, category: discord.CategoryChannel,
                 start_time: datetime = None, end_time: datetime = None, days_back_equiv: int = 14,
                 display_text: str = "14 days", page: int = 0, selected_role_id: str = None,
                 usage_type: str = 'all', using_server_default: bool = True):
        super().__init__(timeout=600)
        self.cog = cog_instance
        self.guild = guild
        self.category = category
        self.start_time = start_time
        self.end_time = end_time if end_time else datetime.now(timezone.utc)
        self.days_back_equiv = days_back_equiv
        self.display_text = display_text
        self.page = page
        self.selected_role_id = selected_role_id
        self.usage_type = usage_type
        self.using_server_default = using_server_default
        self.last_emoji_data = []
        self.show_time_buttons = False
        self.message = None

    async def _update_buttons(self, total_pages: int = 1):
        self.clear_items()

        self.add_item(UsageTypeSelectMenu(self.usage_type))

        prev_button = EmojiPrevButton()
        next_button = EmojiNextButton()
        page_indicator = EmojiPageIndicator()

        prev_button.disabled = (self.page == 0 or total_pages <= 1)
        next_button.disabled = (
            self.page >= total_pages - 1 or total_pages <= 1)
        page_indicator.label = f"Page {self.page + 1}/{total_pages}"

        self.add_item(prev_button)
        self.add_item(page_indicator)
        self.add_item(next_button)

        self.add_item(RoleInputButton())

        self.add_item(RefreshButton())

        self.add_item(TimeSettingsButton())

        if self.show_time_buttons:
            self.add_item(AllTimeButton())
            self.add_item(Days7Button())
            self.add_item(Days14Button())
            self.add_item(Days30Button())
            self.add_item(DaysCustomButton())

    async def generate_image(self):
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

        self.last_emoji_data = await self.cog.get_category_emoji_stats(
            self.guild, self.category.id, self.start_time, self.end_time, self.usage_type, self.selected_role_id)

        total_emojis = len(self.last_emoji_data)
        total_pages = max(
            1, (total_emojis + EmojiConfig.EMOJIS_PER_PAGE - 1) // EmojiConfig.EMOJIS_PER_PAGE)

        if self.page >= total_pages:
            self.page = max(0, total_pages - 1)

        return await generate_emoji_leaderboard_image(
            guild=self.guild,
            leaderboard_data=self.last_emoji_data,
            leaderboard_type='category',
            display_text=self.display_text,
            role_id=self.selected_role_id,
            role_name=role_name,
            usage_type=self.usage_type,
            page=self.page,
            total_pages=total_pages,
            category=self.category
        ), total_pages

    async def update_message(self, interaction: discord.Interaction = None):
        try:
            img_bytes, total_pages = await self.generate_image()
            await self._update_buttons(total_pages)

            file = discord.File(
                img_bytes, filename="category_emoji_leaderboard.png")

            if interaction:
                await interaction.edit_original_response(attachments=[file], view=self)
            elif self.message:
                await self.message.edit(attachments=[file], view=self)

        except Exception as e:
            print(f"Error updating category emoji leaderboard message: {e}")
            try:
                if interaction:
                    await interaction.followup.send("❌ An error occurred while updating the leaderboard.", ephemeral=True)
            except:
                pass


# USER SPECIFIC EMOJI LEADERBOARD VIEW
class UserSpecificEmojiLeaderboardView(discord.ui.View):
    def __init__(self, cog_instance, guild: discord.Guild, target_user: discord.Member,
                 start_time: datetime = None, end_time: datetime = None, days_back_equiv: int = 14,
                 display_text: str = "14 days", page: int = 0, selected_role_id: str = None,
                 usage_type: str = 'all', target_location=None, using_server_default: bool = True):
        super().__init__(timeout=600)
        self.cog = cog_instance
        self.guild = guild
        self.target_user = target_user
        self.start_time = start_time
        self.end_time = end_time if end_time else datetime.now(timezone.utc)
        self.days_back_equiv = days_back_equiv
        self.display_text = display_text
        self.page = page
        self.selected_role_id = selected_role_id
        self.usage_type = usage_type
        self.target_location = target_location
        self.using_server_default = using_server_default
        self.last_emoji_data = []
        self.show_time_buttons = False
        self.message = None

    async def _update_buttons(self, total_pages: int = 1):
        self.clear_items()

        self.add_item(UsageTypeSelectMenu(self.usage_type))

        prev_button = EmojiPrevButton()
        next_button = EmojiNextButton()
        page_indicator = EmojiPageIndicator()

        prev_button.disabled = (self.page == 0 or total_pages <= 1)
        next_button.disabled = (
            self.page >= total_pages - 1 or total_pages <= 1)
        page_indicator.label = f"Page {self.page + 1}/{total_pages}"

        self.add_item(prev_button)
        self.add_item(page_indicator)
        self.add_item(next_button)

        self.add_item(RoleInputButton())

        self.add_item(RefreshButton())

        self.add_item(TimeSettingsButton())

        if self.show_time_buttons:
            self.add_item(AllTimeButton())
            self.add_item(Days7Button())
            self.add_item(Days14Button())
            self.add_item(Days30Button())
            self.add_item(DaysCustomButton())

    async def generate_image(self):
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

        if self.target_location:
            if isinstance(self.target_location, discord.TextChannel):
                self.last_emoji_data = await self.cog.get_user_top_emojis(
                    self.guild, self.target_user.id,
                    self.start_time, self.end_time, self.usage_type, self.selected_role_id,
                    channel_id=self.target_location.id
                )
            elif isinstance(self.target_location, discord.CategoryChannel):
                self.last_emoji_data = await self.cog.get_user_top_emojis(
                    self.guild, self.target_user.id,
                    self.start_time, self.end_time, self.usage_type, self.selected_role_id,
                    category_id=self.target_location.id
                )
            else:
                self.last_emoji_data = await self.cog.get_user_top_emojis(
                    self.guild, self.target_user.id,
                    self.start_time, self.end_time, self.usage_type, self.selected_role_id
                )
        else:
            self.last_emoji_data = await self.cog.get_user_top_emojis(
                self.guild, self.target_user.id,
                self.start_time, self.end_time, self.usage_type, self.selected_role_id
            )

        total_emojis = len(self.last_emoji_data)
        total_pages = max(
            1, (total_emojis + EmojiConfig.EMOJIS_PER_PAGE -
                1) // EmojiConfig.EMOJIS_PER_PAGE
        )

        if self.page >= total_pages:
            self.page = max(0, total_pages - 1)

        img_bytes = await generate_emoji_leaderboard_image(
            guild=self.guild,
            leaderboard_data=self.last_emoji_data,
            leaderboard_type='server',
            display_text=self.display_text,
            role_id=self.selected_role_id,
            role_name=role_name,
            target_member=self.target_user,
            usage_type=self.usage_type,
            page=self.page,
            total_pages=total_pages,
            target_location=self.target_location
        )

        return img_bytes, total_pages

    async def update_message(self, interaction: discord.Interaction = None):
        try:
            img_bytes, total_pages = await self.generate_image()
            await self._update_buttons(total_pages)

            filename = "user_specific_emoji_leaderboard.png"
            file = discord.File(img_bytes, filename=filename)

            if interaction:
                await interaction.edit_original_response(attachments=[file], view=self)
            elif self.message:
                await self.message.edit(attachments=[file], view=self)

        except Exception as e:
            print(
                f"Error updating user-specific emoji leaderboard message: {e}")
            try:
                if interaction:
                    await interaction.followup.send("❌ An error occurred while updating the leaderboard.", ephemeral=True)
            except:
                pass


# QUERY FUNCTIONS - UPDATED TO USE HOURLY AGGREGATED TABLES

class EmojiLeaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.initialized = False
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
        """Fetch user globally with rate limiting. Only used as fallback."""
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
        self.initialized = True

    # NEW METHOD: GET SERVER DEFAULT TIME RANGE
    # NEW METHOD: GET SERVER DEFAULT TIME RANGE
    async def get_server_default_time_range(self, guild_id: int) -> tuple:
        """Get the default time range from server settings. Returns (start_time, end_time, display_text, days_back_equiv)"""
        try:
            settings_cog = self.bot.get_cog('Settings')
            if not settings_cog:
                end = datetime.now(timezone.utc)
                start = end - timedelta(days=EmojiConfig.DEFAULT_DAYS_BACK)
                return (start, end, f"{EmojiConfig.DEFAULT_DAYS_BACK} days", EmojiConfig.DEFAULT_DAYS_BACK)

            settings = await settings_cog.get_guild_settings(guild_id)
            mode = settings.get('default_time_mode', 'days_back')
            now = datetime.now(timezone.utc)

            if mode == 'all_time':
                return (None, now, "All Time", 999999)

            elif mode == 'days_back':
                days = settings.get(
                    'default_days_back') or EmojiConfig.DEFAULT_DAYS_BACK
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
            start = now - timedelta(days=EmojiConfig.DEFAULT_DAYS_BACK)
            return (start, end, f"{EmojiConfig.DEFAULT_DAYS_BACK} days", EmojiConfig.DEFAULT_DAYS_BACK)

        except Exception as e:
            import traceback
            traceback.print_exc()
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=EmojiConfig.DEFAULT_DAYS_BACK)
            return (start, end, f"{EmojiConfig.DEFAULT_DAYS_BACK} days", EmojiConfig.DEFAULT_DAYS_BACK)

    async def get_database_cog(self):
        return self.bot.get_cog('DatabaseStats')

    async def get_emoji_stats(self, guild: discord.Guild, start_time: datetime = None, end_time: datetime = None,
                              usage_type: str = 'all', role_id: str = None):
        """Server-wide emoji stats using emoji_usage_hourly table"""
        db_cog = await self.get_database_cog()
        if not db_cog:
            return []

        role_filter_ids = None
        if role_id and role_id != "none":
            role = guild.get_role(int(role_id))
            if role:
                role_filter_ids = [role.id]

        emoji_data = await db_cog.q_emoji_server_leaderboard(
            guild_id=guild.id,
            limit=100,
            role_filter_ids=role_filter_ids,
            start_time=start_time,
            end_time=end_time,
            usage_type=usage_type if usage_type != 'all' else None
        )

        formatted_data = []
        for emoji in emoji_data:
            total_count = emoji['usage_count']

            if usage_type == 'all':
                message_count = total_count // 2
                reaction_count = total_count - message_count
            elif usage_type == 'message':
                message_count = total_count
                reaction_count = 0
            elif usage_type == 'reaction':
                message_count = 0
                reaction_count = total_count
            else:
                message_count = 0
                reaction_count = 0

            formatted_data.append((
                emoji['emoji_str'],
                total_count,
                message_count,
                reaction_count
            ))

        return formatted_data

    async def get_user_emoji_stats(self, guild: discord.Guild, start_time: datetime = None, end_time: datetime = None,
                                   usage_type: str = 'all', role_id: str = None, channel_id: int = None, category_id: int = None):
        """User emoji leaderboard using emoji_usage_hourly table"""
        db_cog = await self.get_database_cog()
        if not db_cog:
            return []

        role_filter_ids = None
        if role_id and role_id != "none":
            role = guild.get_role(int(role_id))
            if role:
                role_filter_ids = [role.id]

        user_data = await db_cog.q_emoji_user_leaderboard(
            guild_id=guild.id,
            limit=100,
            role_filter_ids=role_filter_ids,
            start_time=start_time,
            end_time=end_time,
            usage_type=usage_type if usage_type != 'all' else None,
            channel_id=channel_id,
            category_id=category_id
        )

        formatted_data = []
        for user in user_data:
            total_count = user['usage_count']

            if usage_type == 'all':
                message_count = total_count // 2
                reaction_count = total_count - message_count
            elif usage_type == 'message':
                message_count = total_count
                reaction_count = 0
            elif usage_type == 'reaction':
                message_count = 0
                reaction_count = total_count
            else:
                message_count = 0
                reaction_count = 0

            formatted_data.append((
                user['user_id'],
                total_count,
                message_count,
                reaction_count
            ))

        return formatted_data

    async def get_channel_emoji_stats(self, guild: discord.Guild, channel_id: int, start_time: datetime = None,
                                      end_time: datetime = None, usage_type: str = 'all', role_id: str = None):
        """Channel emoji stats using emoji_usage_hourly table"""
        db_cog = await self.get_database_cog()
        if not db_cog:
            return []

        role_filter_ids = None
        if role_id and role_id != "none":
            role = guild.get_role(int(role_id))
            if role:
                role_filter_ids = [role.id]

        emoji_data = await db_cog.q_emoji_channel_leaderboard(
            guild_id=guild.id,
            channel_id=channel_id,
            limit=100,
            role_filter_ids=role_filter_ids,
            start_time=start_time,
            end_time=end_time,
            usage_type=usage_type if usage_type != 'all' else None
        )

        formatted_data = []
        for emoji in emoji_data:
            total_count = emoji['usage_count']

            if usage_type == 'all':
                message_count = total_count // 2
                reaction_count = total_count - message_count
            elif usage_type == 'message':
                message_count = total_count
                reaction_count = 0
            elif usage_type == 'reaction':
                message_count = 0
                reaction_count = total_count
            else:
                message_count = 0
                reaction_count = 0

            formatted_data.append((
                emoji['emoji_str'],
                total_count,
                message_count,
                reaction_count
            ))

        return formatted_data

    async def get_category_emoji_stats(self, guild: discord.Guild, category_id: int, start_time: datetime = None,
                                       end_time: datetime = None, usage_type: str = 'all', role_id: str = None):
        """Category emoji stats using emoji_usage_hourly table"""
        db_cog = await self.get_database_cog()
        if not db_cog:
            return []

        role_filter_ids = None
        if role_id and role_id != "none":
            role = guild.get_role(int(role_id))
            if role:
                role_filter_ids = [role.id]

        emoji_data = await db_cog.q_emoji_category_leaderboard(
            guild_id=guild.id,
            category_id=category_id,
            limit=100,
            role_filter_ids=role_filter_ids,
            start_time=start_time,
            end_time=end_time,
            usage_type=usage_type if usage_type != 'all' else None
        )

        formatted_data = []
        for emoji in emoji_data:
            total_count = emoji['usage_count']

            if usage_type == 'all':
                message_count = total_count // 2
                reaction_count = total_count - message_count
            elif usage_type == 'message':
                message_count = total_count
                reaction_count = 0
            elif usage_type == 'reaction':
                message_count = 0
                reaction_count = total_count
            else:
                message_count = 0
                reaction_count = 0

            formatted_data.append((
                emoji['emoji_str'],
                total_count,
                message_count,
                reaction_count
            ))

        return formatted_data

    async def get_user_top_emojis(self, guild: discord.Guild, user_id: int, start_time: datetime = None,
                                  end_time: datetime = None, usage_type: str = 'all', role_id: str = None,
                                  channel_id: int = None, category_id: int = None):
        """User's top emojis using emoji_usage_hourly table"""
        db_cog = await self.get_database_cog()
        if not db_cog:
            return []

        role_filter_ids = None
        if role_id and role_id != "none":
            role = guild.get_role(int(role_id))
            if role:
                role_filter_ids = [role.id]

        emoji_data = await db_cog.q_user_top_emojis(
            guild_id=guild.id,
            user_id=user_id,
            limit=100,
            role_filter_ids=role_filter_ids,
            start_time=start_time,
            end_time=end_time,
            usage_type=usage_type if usage_type != 'all' else None,
            channel_id=channel_id,
            category_id=category_id
        )

        formatted_data = []
        for emoji in emoji_data:
            total_count = emoji['usage_count']

            if usage_type == 'all':
                message_count = total_count // 2
                reaction_count = total_count - message_count
            elif usage_type == 'message':
                message_count = total_count
                reaction_count = 0
            elif usage_type == 'reaction':
                message_count = 0
                reaction_count = total_count
            else:
                message_count = 0
                reaction_count = 0

            formatted_data.append((
                emoji['emoji_str'],
                total_count,
                message_count,
                reaction_count
            ))

        return formatted_data

    # =========================================================
    # INTERNAL FUNCTION FOR PREFIX COMMANDS
    # =========================================================
    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def _handle_prefix_command(self, ctx, command_type, target_id=None, target_type=None, user_target=None):
        """Internal function to handle all prefix commands"""
        try:
            guild = ctx.guild
            if guild is None:
                await ctx.send("❌ This command can only be used in a server.", delete_after=5)
                return

            # Check permission - use await here
            if not await check_prefix_emoji_permission(ctx, user_target):
                embed = discord.Embed(
                    title="❌ Permission Denied",
                    description="Sorry! You don't have permission to use this command.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed, delete_after=10)
                return

            # Try to delete the command message
            try:
                await ctx.message.delete()
            except:
                pass

            # Get server default time range
            start_time, end_time, display_text, days_back_equiv = await self.get_server_default_time_range(guild.id)

            # Default parameters
            selected_role_id = "none"
            usage_type = "all"

            # Handle different command types
            if command_type == "server":
                # Server-wide emoji leaderboard
                view = EmojiLeaderboardView(
                    self, guild, start_time=start_time, end_time=end_time,
                    days_back_equiv=days_back_equiv, display_text=display_text,
                    selected_role_id=selected_role_id, usage_type=usage_type,
                    using_server_default=True
                )

            elif command_type == "channel":
                # Channel-specific emoji leaderboard
                if target_id:
                    channel = guild.get_channel(int(target_id))
                else:
                    channel = ctx.channel

                if not isinstance(channel, discord.TextChannel):
                    await ctx.send("❌ Please specify a valid text channel or use this command in a text channel.", delete_after=5)
                    return

                view = ChannelEmojiLeaderboardView(
                    self, guild, channel, start_time=start_time, end_time=end_time,
                    days_back_equiv=days_back_equiv, display_text=display_text,
                    selected_role_id=selected_role_id, usage_type=usage_type,
                    using_server_default=True
                )

            elif command_type == "category":
                # Category-specific emoji leaderboard
                if target_id:
                    category = guild.get_channel(int(target_id))
                else:
                    # Try to get category from current channel
                    if hasattr(ctx.channel, 'category') and ctx.channel.category:
                        category = ctx.channel.category
                    else:
                        await ctx.send("❌ Please specify a category ID or use this command in a channel with a category.", delete_after=5)
                        return

                if not isinstance(category, discord.CategoryChannel):
                    await ctx.send("❌ Please specify a valid category.", delete_after=5)
                    return

                view = CategoryEmojiLeaderboardView(
                    self, guild, category, start_time=start_time, end_time=end_time,
                    days_back_equiv=days_back_equiv, display_text=display_text,
                    selected_role_id=selected_role_id, usage_type=usage_type,
                    using_server_default=True
                )

            elif command_type == "user_stats":
                # User-specific emoji stats
                if user_target:
                    target_user = user_target
                else:
                    target_user = ctx.author

                if target_type == "channel" and target_id:
                    target_location = guild.get_channel(int(target_id))
                elif target_type == "category" and target_id:
                    target_location = guild.get_channel(int(target_id))
                else:
                    target_location = None

                view = UserSpecificEmojiLeaderboardView(
                    self, guild, target_user, start_time=start_time, end_time=end_time,
                    days_back_equiv=days_back_equiv, display_text=display_text,
                    selected_role_id=selected_role_id, usage_type=usage_type,
                    target_location=target_location, using_server_default=True
                )

            elif command_type == "user_leaderboard":
                # User emoji leaderboard
                if target_type == "channel" and target_id:
                    target_location = guild.get_channel(int(target_id))
                elif target_type == "category" and target_id:
                    target_location = guild.get_channel(int(target_id))
                else:
                    target_location = None

                view = UserEmojiLeaderboardView(
                    self, guild, start_time=start_time, end_time=end_time,
                    days_back_equiv=days_back_equiv, display_text=display_text,
                    selected_role_id=selected_role_id, usage_type=usage_type,
                    target_location=target_location, using_server_default=True
                )
            else:
                await ctx.send("❌ Invalid command type.", delete_after=5)
                return

            # Generate and send the image
            # Generate and send the image
            img_bytes, total_pages = await view.generate_image()
            file = discord.File(img_bytes, filename="emoji_leaderboard.png")

            db_cog = await self.get_database_cog()
            retention_alert_text = await db_cog.maybe_get_retention_alert(guild.id) if db_cog else None
            stat_type_warning = await db_cog.check_stat_types_enabled(guild.id, ['track_emojis']) if db_cog else None
            content_parts = [p for p in (
                retention_alert_text, stat_type_warning) if p]
            content = "\n".join(content_parts) if content_parts else None

            msg = await ctx.send(content=content, file=file, view=view)
            view.message = msg

            # Update buttons
            await view._update_buttons(total_pages)
            await msg.edit(view=view)

        except Exception as e:
            print(f"Error in _handle_prefix_command: {e}")
            await ctx.send("❌ An error occurred while processing the command.", delete_after=10)

    # =========================================================
    # SHORTCUT COMMANDS
    # =========================================================

    @commands.command(name="els")
    async def emoji_leaderboard_server_shortcut(self, ctx):
        """Shortcut for emoji leaderboard server"""
        await self._handle_prefix_command(ctx, "server")

    @commands.command(name="elch")
    async def emoji_leaderboard_channel_shortcut(self, ctx, channel_id: str = None):
        """Shortcut for emoji leaderboard channel"""
        await self._handle_prefix_command(ctx, "channel", target_id=channel_id)

    @commands.command(name="elca")
    async def emoji_leaderboard_category_shortcut(self, ctx, category_id: str = None):
        """Shortcut for emoji leaderboard category"""
        await self._handle_prefix_command(ctx, "category", target_id=category_id)

    @commands.command(name="eu")
    async def emoji_user_stats_shortcut(self, ctx, user: discord.Member = None, target_id: str = None):
        """Shortcut for emoji user stats"""
        target_type = None
        if target_id:
            # Try to determine if it's a channel or category
            guild = ctx.guild
            target_channel = guild.get_channel(
                int(target_id)) if target_id.isdigit() else None
            if target_channel:
                if isinstance(target_channel, discord.TextChannel):
                    target_type = "channel"
                elif isinstance(target_channel, discord.CategoryChannel):
                    target_type = "category"

        await self._handle_prefix_command(ctx, "user_stats", target_id=target_id, target_type=target_type, user_target=user)

    @commands.command(name="eul")
    async def emoji_user_leaderboard_shortcut(self, ctx, target_id: str = None):
        """Shortcut for emoji user leaderboard"""
        target_type = None
        if target_id:
            # Try to determine if it's a channel or category
            guild = ctx.guild
            target_channel = guild.get_channel(
                int(target_id)) if target_id.isdigit() else None
            if target_channel:
                if isinstance(target_channel, discord.TextChannel):
                    target_type = "channel"
                elif isinstance(target_channel, discord.CategoryChannel):
                    target_type = "category"

        await self._handle_prefix_command(ctx, "user_leaderboard", target_id=target_id, target_type=target_type)

    # =========================================================
    # PREFIX COMMAND GROUPS
    # =========================================================

    @commands.group(name="emoji", invoke_without_command=True)
    async def emoji_group_prefix(self, ctx):
        """Emoji statistics and leaderboard commands"""
        await ctx.send("Available commands:\n"
                       "- `emoji leaderboard server` - Show most used emojis in the server\n"
                       "- `emoji leaderboard channel [channel_id]` - Show most used emojis in a channel\n"
                       "- `emoji leaderboard category [category_id]` - Show most used emojis in a category\n"
                       "- `emoji user stats [user] [target_id]` - Show top emojis used by a user\n"
                       "- `emoji user leaderboard [target_id]` - Show top emoji users\n\n"
                       "Shortcuts:\n"
                       "- `els` - Emoji leaderboard server\n"
                       "- `elch [channel_id]` - Emoji leaderboard channel\n"
                       "- `elca [category_id]` - Emoji leaderboard category\n"
                       "- `eu [user] [target_id]` - Emoji user stats\n"
                       "- `eul [target_id]` - Emoji user leaderboard")

    @emoji_group_prefix.group(name="leaderboard", invoke_without_command=True)
    async def emoji_leaderboard_group_prefix(self, ctx):
        """Emoji leaderboard commands"""
        await ctx.send("Available leaderboard commands:\n"
                       "- `emoji leaderboard server` - Server-wide emoji leaderboard\n"
                       "- `emoji leaderboard channel [channel_id]` - Channel-specific emoji leaderboard\n"
                       "- `emoji leaderboard category [category_id]` - Category-specific emoji leaderboard")

    @emoji_leaderboard_group_prefix.command(name="server")
    async def emoji_leaderboard_server_prefix(self, ctx):
        """Server-wide emoji leaderboard via prefix command"""
        await self._handle_prefix_command(ctx, "server")

    @emoji_leaderboard_group_prefix.command(name="channel")
    async def emoji_leaderboard_channel_prefix(self, ctx, channel_id: str = None):
        """Channel-specific emoji leaderboard via prefix command"""
        await self._handle_prefix_command(ctx, "channel", target_id=channel_id)

    @emoji_leaderboard_group_prefix.command(name="category")
    async def emoji_leaderboard_category_prefix(self, ctx, category_id: str = None):
        """Category-specific emoji leaderboard via prefix command"""
        await self._handle_prefix_command(ctx, "category", target_id=category_id)

    @emoji_group_prefix.group(name="user", invoke_without_command=True)
    async def emoji_user_group_prefix(self, ctx):
        """Emoji user statistics commands"""
        await ctx.send("Available user commands:\n"
                       "- `emoji user stats [user] [target_id]` - Show top emojis used by a user\n"
                       "- `emoji user leaderboard [target_id]` - Show top emoji users")

    @emoji_user_group_prefix.command(name="stats")
    async def emoji_user_stats_prefix(self, ctx, user: discord.Member = None, target_id: str = None):
        """User-specific emoji stats via prefix command"""
        target_type = None
        if target_id:
            # Try to determine if it's a channel or category
            guild = ctx.guild
            target_channel = guild.get_channel(
                int(target_id)) if target_id.isdigit() else None
            if target_channel:
                if isinstance(target_channel, discord.TextChannel):
                    target_type = "channel"
                elif isinstance(target_channel, discord.CategoryChannel):
                    target_type = "category"

        await self._handle_prefix_command(ctx, "user_stats", target_id=target_id, target_type=target_type, user_target=user)

    @emoji_user_group_prefix.command(name="leaderboard")
    async def emoji_user_leaderboard_prefix(self, ctx, target_id: str = None):
        """User emoji leaderboard via prefix command"""
        target_type = None
        if target_id:
            # Try to determine if it's a channel or category
            guild = ctx.guild
            target_channel = guild.get_channel(
                int(target_id)) if target_id.isdigit() else None
            if target_channel:
                if isinstance(target_channel, discord.TextChannel):
                    target_type = "channel"
                elif isinstance(target_channel, discord.CategoryChannel):
                    target_type = "category"

        await self._handle_prefix_command(ctx, "user_leaderboard", target_id=target_id, target_type=target_type)

    # =========================================================
    # SLASH COMMANDS
    # =========================================================

    emoji_group = app_commands.Group(
        name="emoji", description="Emoji statistics and leaderboard commands")
    emoji_user_group = app_commands.Group(
        name="user", description="Emoji user statistics commands", parent=emoji_group)
    emoji_channel_group = app_commands.Group(
        name="channel", description="Channel-specific emoji statistics commands", parent=emoji_group)
    emoji_category_group = app_commands.Group(
        name="category", description="Category-specific emoji statistics commands", parent=emoji_group)

    @emoji_group.command(name="leaderboard", description="Show most used emojis in the server")
    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def emoji_leaderboard(self, interaction: discord.Interaction):
        """Server-wide emoji leaderboard - NO TARGET PARAMETER HERE"""
        try:
            guild = interaction.guild
            if guild is None:
                await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
                return

            # Check permission
            if not await check_emoji_permission(interaction):
                return

            await interaction.response.defer()

            # Get server default time range
            start_time, end_time, display_text, days_back_equiv = await self.get_server_default_time_range(guild.id)

            view = EmojiLeaderboardView(
                self, guild, start_time=start_time, end_time=end_time,
                days_back_equiv=days_back_equiv, display_text=display_text,
                using_server_default=True)

            img_bytes, total_pages = await view.generate_image()
            file = discord.File(img_bytes, filename="emoji_leaderboard.png")

            db_cog = await self.get_database_cog()
            retention_alert_text = await db_cog.maybe_get_retention_alert(guild.id) if db_cog else None
            stat_type_warning = await db_cog.check_stat_types_enabled(guild.id, ['track_emojis']) if db_cog else None
            content_parts = [p for p in (
                retention_alert_text, stat_type_warning) if p]
            content = "\n".join(content_parts) if content_parts else None

            await interaction.followup.send(content=content, file=file, view=view)

            message = await interaction.original_response()
            view.message = message

            await view._update_buttons(total_pages)
            await message.edit(view=view)

        except Exception as e:
            print(f"Error in emoji_leaderboard: {e}")
            await interaction.followup.send("❌ An error occurred while retrieving emoji stats.")

    @emoji_user_group.command(name="leaderboard", description="Show top emoji users in the server")
    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    @app_commands.describe(
        target="Filter by specific channel or category (optional)"
    )
    async def emoji_user_leaderboard(self, interaction: discord.Interaction,
                                     target: discord.abc.GuildChannel = None):
        try:
            guild = interaction.guild
            if guild is None:
                await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
                return

            # Check permission
            if not await check_emoji_permission(interaction):
                return

            # Validate target type
            target_location = None
            if target:
                if isinstance(target, (discord.TextChannel, discord.CategoryChannel)):
                    target_location = target
                else:
                    await interaction.response.send_message("Please select either a text channel or a category.", ephemeral=True)
                    return

            await interaction.response.defer()

            # Get server default time range
            start_time, end_time, display_text, days_back_equiv = await self.get_server_default_time_range(guild.id)

            view = UserEmojiLeaderboardView(
                self, guild, start_time=start_time, end_time=end_time,
                days_back_equiv=days_back_equiv, display_text=display_text,
                target_location=target_location, using_server_default=True)

            img_bytes, total_pages = await view.generate_image()
            file = discord.File(
                img_bytes, filename="user_emoji_leaderboard.png")

            db_cog = await self.get_database_cog()
            retention_alert_text = await db_cog.maybe_get_retention_alert(guild.id) if db_cog else None
            stat_type_warning = await db_cog.check_stat_types_enabled(guild.id, ['track_emojis']) if db_cog else None
            content_parts = [p for p in (
                retention_alert_text, stat_type_warning) if p]
            content = "\n".join(content_parts) if content_parts else None

            await interaction.followup.send(content=content, file=file, view=view)

            message = await interaction.original_response()
            view.message = message

            await view._update_buttons(total_pages)
            await message.edit(view=view)

        except Exception as e:
            print(f"Error in emoji_user_leaderboard: {e}")
            await interaction.followup.send("❌ An error occurred while retrieving user emoji stats.")

    @emoji_channel_group.command(name="leaderboard", description="Show most used emojis in a specific channel")
    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    @app_commands.describe(channel="Select a text channel")
    async def emoji_channel_leaderboard(self, interaction: discord.Interaction, channel: discord.TextChannel):
        try:
            guild = interaction.guild
            if guild is None:
                await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
                return

            # Check permission
            if not await check_emoji_permission(interaction):
                return

            await interaction.response.defer()

            # Get server default time range
            start_time, end_time, display_text, days_back_equiv = await self.get_server_default_time_range(guild.id)

            view = ChannelEmojiLeaderboardView(
                self, guild, channel, start_time=start_time, end_time=end_time,
                days_back_equiv=days_back_equiv, display_text=display_text,
                using_server_default=True)

            img_bytes, total_pages = await view.generate_image()
            file = discord.File(
                img_bytes, filename="channel_emoji_leaderboard.png")

            db_cog = await self.get_database_cog()
            retention_alert_text = await db_cog.maybe_get_retention_alert(guild.id) if db_cog else None
            stat_type_warning = await db_cog.check_stat_types_enabled(guild.id, ['track_emojis']) if db_cog else None
            content_parts = [p for p in (
                retention_alert_text, stat_type_warning) if p]
            content = "\n".join(content_parts) if content_parts else None

            await interaction.followup.send(content=content, file=file, view=view)

            message = await interaction.original_response()
            view.message = message

            await view._update_buttons(total_pages)
            await message.edit(view=view)

        except Exception as e:
            print(f"Error in emoji_channel_leaderboard: {e}")
            await interaction.followup.send("❌ An error occurred while retrieving channel emoji stats.")

    @emoji_category_group.command(name="leaderboard", description="Show most used emojis in a specific category")
    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    @app_commands.describe(category="Select a category")
    async def emoji_category_leaderboard(self, interaction: discord.Interaction, category: discord.CategoryChannel):
        try:
            guild = interaction.guild
            if guild is None:
                await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
                return

            # Check permission
            if not await check_emoji_permission(interaction):
                return

            await interaction.response.defer()

            # Get server default time range
            start_time, end_time, display_text, days_back_equiv = await self.get_server_default_time_range(guild.id)

            view = CategoryEmojiLeaderboardView(
                self, guild, category, start_time=start_time, end_time=end_time,
                days_back_equiv=days_back_equiv, display_text=display_text,
                using_server_default=True)

            img_bytes, total_pages = await view.generate_image()
            file = discord.File(
                img_bytes, filename="category_emoji_leaderboard.png")

            db_cog = await self.get_database_cog()
            retention_alert_text = await db_cog.maybe_get_retention_alert(guild.id) if db_cog else None
            stat_type_warning = await db_cog.check_stat_types_enabled(guild.id, ['track_emojis']) if db_cog else None
            content_parts = [p for p in (
                retention_alert_text, stat_type_warning) if p]
            content = "\n".join(content_parts) if content_parts else None

            await interaction.followup.send(content=content, file=file, view=view)

            message = await interaction.original_response()
            view.message = message

            await view._update_buttons(total_pages)
            await message.edit(view=view)

        except Exception as e:
            print(f"Error in emoji_category_leaderboard: {e}")
            await interaction.followup.send("❌ An error occurred while retrieving category emoji stats.")

    @emoji_user_group.command(name="stats", description="Show top emojis used by a specific user")
    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    @app_commands.describe(
        user="The user to show emoji stats for",
        target="Filter by specific channel or category (optional)"
    )
    async def emoji_user_stats(self, interaction: discord.Interaction,
                               user: discord.Member,
                               target: discord.abc.GuildChannel = None):
        try:
            guild = interaction.guild
            if guild is None:
                await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
                return

            # Check permission with target user
            if not await check_emoji_permission(interaction, target_user=user):
                return

            # Validate target type
            target_location = None
            if target:
                if isinstance(target, (discord.TextChannel, discord.CategoryChannel)):
                    target_location = target
                else:
                    await interaction.response.send_message("Please select either a text channel or a category.", ephemeral=True)
                    return

            await interaction.response.defer()

            # Get server default time range
            start_time, end_time, display_text, days_back_equiv = await self.get_server_default_time_range(guild.id)

            view = UserSpecificEmojiLeaderboardView(
                self, guild, user, start_time=start_time, end_time=end_time,
                days_back_equiv=days_back_equiv, display_text=display_text,
                target_location=target_location, using_server_default=True)

            img_bytes, total_pages = await view.generate_image()
            file = discord.File(img_bytes, filename="user_emoji_stats.png")

            db_cog = await self.get_database_cog()
            retention_alert_text = await db_cog.maybe_get_retention_alert(guild.id) if db_cog else None
            stat_type_warning = await db_cog.check_stat_types_enabled(guild.id, ['track_emojis']) if db_cog else None
            content_parts = [p for p in (
                retention_alert_text, stat_type_warning) if p]
            content = "\n".join(content_parts) if content_parts else None

            await interaction.followup.send(content=content, file=file, view=view)

            message = await interaction.original_response()
            view.message = message

            await view._update_buttons(total_pages)
            await message.edit(view=view)

        except Exception as e:
            print(f"Error in emoji_user_stats: {e}")
            await interaction.followup.send("❌ An error occurred while retrieving user's emoji stats.")


# SETUP

async def setup(bot):
    await bot.add_cog(EmojiLeaderboard(bot))
