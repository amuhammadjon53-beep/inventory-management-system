import discord
from discord.ext import commands
from discord.ext import tasks
from discord import app_commands
from datetime import timedelta, datetime, timezone
import asyncio
import io
import logging
import traceback
from typing import Optional, Union, List, Dict, Any
from PIL import Image, ImageDraw, ImageFont
import aiohttp
import os
from pathlib import Path
import unicodedata
import gc

from .ratelimiter import RateLimiter, RateLimitType, rate_limited, get_rate_limiter

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent


class MentionsConfig:
    USERS_PER_PAGE = 10
    MAX_CUSTOM_DAYS = 2000
    TIME_PERIODS = [7, 14, 30]

    TEMPLATE_PATH = BASE_DIR / "assets" / "images" / "leaderboards final png.png"
    FONT_PATH = BASE_DIR / "assets" / "fonts" / "HorndonD.ttf"

    IMAGE_WIDTH = 800
    IMAGE_HEIGHT = 600

    COLORS = {
        'gold': (255, 215, 0, 220),
        'silver': (192, 192, 192, 220),
        'bronze': (205, 127, 50, 220),
        'default': (93, 0, 136, 255),
        'background': (0, 0, 0, 220),
    }


class UnicodeNormalizer:
    @staticmethod
    def normalize_text(text: str) -> str:
        if not text:
            return ""
        normalized = unicodedata.normalize('NFKD', text)
        ascii_safe = normalized.encode('ascii', 'ignore').decode('ascii')
        return ascii_safe if ascii_safe else text[:10]


def format_mention_count(count: int) -> str:
    if count < 1000:
        return str(count)
    elif count < 10000:
        return f"{count / 1000:.1f}k".rstrip('0').rstrip('.')
    else:
        return f"{count // 1000}k"


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

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            page = int(self.page_number.value) - 1

            if page < 0 or page >= self.total_pages:
                embed = discord.Embed(
                    title="Invalid Page",
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
                title="Invalid Input",
                description="Please enter a valid page number.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


class MentionsImageGenerator:
    @staticmethod
    def get_fonts():
        try:
            custom_font_path = MentionsConfig.FONT_PATH
            if os.path.exists(custom_font_path):
                font_small = ImageFont.truetype(custom_font_path, 16)
                font_medium = ImageFont.truetype(custom_font_path, 20)
                font_large = ImageFont.truetype(custom_font_path, 24)
                font_larger = ImageFont.truetype(custom_font_path, 30)
                font_huge = ImageFont.truetype(custom_font_path, 40)
                font_giant = ImageFont.truetype(custom_font_path, 60)
                return font_small, font_medium, font_large, font_larger, font_huge, font_giant
        except Exception:
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
                        MentionsImageGenerator.draw_text_with_stroke(
                            draw, (x, y), text, smaller_font, fill, stroke_fill, stroke_width)
                        return
                except:
                    continue
        MentionsImageGenerator.draw_text_with_stroke(
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
    def fit_text_to_rectangle(draw, text, text_start_x, text_start_y, rect_center_x, rect_center_y, rect_width, rect_height, is_username=False):
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

    @staticmethod
    async def add_server_profile_pic_and_name(image, guild, target_name, font_huge):
        draw = ImageDraw.Draw(image)

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
        except Exception:
            pass

        normalized_name = UnicodeNormalizer.normalize_text(target_name)

        fitted_text, text_font, text_pos = MentionsImageGenerator.fit_text_to_rectangle(
            draw, normalized_name, text_start_x, text_start_y,
            username_rectangle["center"][0], username_rectangle["center"][1],
            username_rectangle["width"], username_rectangle["height"],
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
                      normalized_name, font=font_huge, fill="white")

    @staticmethod
    async def add_user_profile_pic_and_name(image, guild, user, font_huge):
        draw = ImageDraw.Draw(image)

        avatar_x, avatar_y = 7, 10
        avatar_size = (60, 60)
        text_start_x = 85
        text_start_y = 30
        username_rectangle = {"center": (150, 30), "width": 183, "height": 35}

        try:
            avatar_url = user.avatar.url if user.avatar else (
                user.display_avatar.url if user.display_avatar else None)
            if avatar_url:
                async with aiohttp.ClientSession() as session:
                    async with session.get(avatar_url) as response:
                        avatar_data = await response.read()

                avatar_image = Image.open(io.BytesIO(avatar_data))
                avatar_image = avatar_image.resize(
                    avatar_size, Image.Resampling.LANCZOS).convert('RGBA')

                mask = Image.new('L', avatar_size, 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.ellipse(
                    (0, 0, avatar_size[0], avatar_size[1]), fill=255)
                avatar_image.putalpha(mask)

                avatar_area = image.crop(
                    (avatar_x, avatar_y, avatar_x + avatar_size[0], avatar_y + avatar_size[1])).convert('RGBA')
                avatar_with_bg = Image.new('RGBA', avatar_size, (0, 0, 0, 0))
                avatar_with_bg.paste(avatar_image, (0, 0), avatar_image)
                avatar_area.paste(avatar_with_bg, (0, 0), avatar_with_bg)
                image.paste(avatar_area.convert('RGB'), (avatar_x, avatar_y))
                avatar_image.close()
        except Exception:
            pass

        normalized_name = UnicodeNormalizer.normalize_text(
            user.display_name if user.display_name else user.name)

        fitted_text, text_font, text_pos = MentionsImageGenerator.fit_text_to_rectangle(
            draw, normalized_name, text_start_x, text_start_y,
            username_rectangle["center"][0], username_rectangle["center"][1],
            username_rectangle["width"], username_rectangle["height"],
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
                      normalized_name, font=font_huge, fill="white")

    @staticmethod
    async def generate_leaderboard_image(
        guild: discord.Guild,
        leaderboard_data: list,
        title: str,
        display_text: str,
        role_id: str = None,
        page: int = 0,
        pool=None,
        target_user: discord.Member = None,
        metric_type: str = "sent"
    ) -> io.BytesIO:
        template_path = MentionsConfig.TEMPLATE_PATH
        try:
            image = Image.open(template_path)
        except FileNotFoundError:
            image = Image.new('RGB', (MentionsConfig.IMAGE_WIDTH,
                                      MentionsConfig.IMAGE_HEIGHT), color='#2F3136')

        if image.mode != "RGB":
            image = image.convert("RGB")

        draw = ImageDraw.Draw(image)
        font_small, font_medium, font_large, font_larger, font_huge, font_giant = MentionsImageGenerator.get_fonts()

        if target_user:
            await MentionsImageGenerator.add_user_profile_pic_and_name(image, guild, target_user, font_huge)
        else:
            await MentionsImageGenerator.add_server_profile_pic_and_name(image, guild, title, font_huge)

        role_text = role_id if role_id else "No Filter"
        MentionsImageGenerator.draw_text_with_stroke(
            draw, (70, 424), role_text, font_small, "white", "black", 1)

        MentionsImageGenerator.draw_text_with_stroke(
            draw, (630, 422), display_text, font_small, "white", "black", 1)

        MentionsImageGenerator.draw_text_with_stroke(draw, (550, 38), datetime.now(
        ).strftime("%B %d, %Y"), font_small, "white", "black", 1)

        if leaderboard_data:
            total_items = len(leaderboard_data)
            users_per_page = MentionsConfig.USERS_PER_PAGE
            total_pages = (total_items + users_per_page - 1) // users_per_page
            MentionsImageGenerator.draw_text_with_stroke(
                draw, (400, 450), f"Page {page + 1}/{total_pages}", font_medium, "white", "black", 1)

            start_idx = page * MentionsConfig.USERS_PER_PAGE
            end_idx = min(start_idx + MentionsConfig.USERS_PER_PAGE,
                          len(leaderboard_data))
            page_data = leaderboard_data[start_idx:end_idx]

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

            for i, item in enumerate(page_data):
                box_x, box_y = positions[i]
                global_rank = start_idx + i + 1

                MentionsImageGenerator.draw_rounded_rectangle(
                    draw, [box_x, box_y, box_x +
                           box_width, box_y + box_height],
                    radius=8, fill=MentionsConfig.COLORS['background'], outline=None
                )

                placement_width = 35
                if global_rank == 1:
                    placement_color = MentionsConfig.COLORS['gold']
                elif global_rank == 2:
                    placement_color = MentionsConfig.COLORS['silver']
                elif global_rank == 3:
                    placement_color = MentionsConfig.COLORS['bronze']
                else:
                    placement_color = MentionsConfig.COLORS['default']

                MentionsImageGenerator.draw_rounded_rectangle(
                    draw, [box_x, box_y, box_x +
                           placement_width, box_y + box_height],
                    radius=8, fill=placement_color, outline=None
                )

                if metric_type == "ratio":
                    ratio_display = item.get('ratio_display', '0.0')
                    value_text = ratio_display
                else:
                    mention_count = item.get('mention_count', 0)
                    value_text = format_mention_count(mention_count)

                rank_text = f"#{global_rank}"
                rank_bbox = draw.textbbox((0, 0), rank_text, font=font_medium)
                rank_width = rank_bbox[2] - rank_bbox[0]

                value_bbox = draw.textbbox(
                    (0, 0), value_text, font=font_medium)
                value_width = value_bbox[2] - value_bbox[0]

                available_name_width = box_width - placement_width - value_width - 20

                display_name = item.get('name', 'Unknown')
                name_font = font_medium
                display_name, name_font = MentionsImageGenerator.truncate_text_for_width(
                    draw, display_name, name_font, available_name_width
                )

                rank_height = rank_bbox[3] - rank_bbox[1]
                name_bbox = draw.textbbox((0, 0), display_name, font=name_font)
                name_height = name_bbox[3] - name_bbox[1]
                value_height = value_bbox[3] - value_bbox[0]

                rank_y = box_y + (box_height - rank_height) // 2
                name_y = box_y + (box_height - name_height) // 2
                value_y = box_y + (box_height - value_height) // 2

                rank_x = box_x + (placement_width - rank_width) // 2
                MentionsImageGenerator.draw_text_with_stroke(
                    draw, (rank_x, rank_y), rank_text, font_medium, "white", "black", 1)

                name_x = box_x + placement_width + 8
                MentionsImageGenerator.draw_text_with_stroke(
                    draw, (name_x, name_y), display_name, name_font, "white", "black", 1)

                value_x = box_x + box_width - value_width - 8
                MentionsImageGenerator.draw_text_with_stroke(
                    draw, (value_x, value_y), value_text, font_medium, "white", "black", 1)
        else:
            cx, cy = image.size[0] // 2, image.size[1] // 2
            MentionsImageGenerator.draw_text_centered_with_stroke(
                draw, "NO DATA AVAILABLE", (cx, cy), font_giant, "white", "black", 3)

        img_bytes = io.BytesIO()
        image.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        gc.collect()
        return img_bytes


class MentionsTimeModal(discord.ui.Modal, title='Custom Time Period'):
    def __init__(self, cog_instance, original_message_id, guild, target_channel=None, target_category=None, target_user=None):
        super().__init__(timeout=300)
        self.cog = cog_instance
        self.original_message_id = original_message_id
        self.guild = guild
        self.target_channel = target_channel
        self.target_category = target_category
        self.target_user = target_user

    days = discord.ui.TextInput(
        label='Enter number of days',
        placeholder='e.g., 7, 14, 30, 90...',
        min_length=1,
        max_length=4,
        required=True
    )

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            days = int(self.days.value)
            if days <= 0 or days > MentionsConfig.MAX_CUSTOM_DAYS:
                await interaction.response.send_message(f"❌ Please enter a number between 1 and {MentionsConfig.MAX_CUSTOM_DAYS} days.", ephemeral=True)
                return

            await interaction.response.defer()

            view = self.cog.active_views.get(self.original_message_id)
            if not view:
                await interaction.followup.send("❌ Could not find the leaderboard view. Please try the command again.", ephemeral=True)
                return

            now = datetime.now(timezone.utc)
            view.current_start_time = now - timedelta(days=days)
            view.current_end_time = now
            view.current_days_back_equiv = days
            view.current_display_text = f"{days} days"
            view.using_server_default = False
            view.show_time_buttons = False
            view.page = 0

            await view.update_message(interaction)

        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in time modal submit: {e}")
            await interaction.followup.send("❌ An error occurred while updating the leaderboard.", ephemeral=True)


class MentionsPrevButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary,
                         emoji=discord.PartialEmoji(name="arrowleft", id=1521149181207777331), custom_id="mentions_prev")

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def callback(self, interaction: discord.Interaction):
        if self.disabled:
            await interaction.response.defer(ephemeral=True)
            return
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False)
        view = self.view
        if view.page > 0:
            view.page -= 1
            await view.update_message(interaction)


class MentionsNextButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary,
                         emoji=discord.PartialEmoji(name="arrowright", id=1521149211373076501), custom_id="mentions_next")

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def callback(self, interaction: discord.Interaction):
        if self.disabled:
            await interaction.response.defer(ephemeral=True)
            return
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False)
        view = self.view
        view.page += 1
        await view.update_message(interaction)


class MentionsPageIndicator(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary,
                         label="Page 1/1", custom_id="mentions_page", disabled=False)

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def callback(self, interaction: discord.Interaction):
        view = self.view

        if hasattr(view, 'leaderboard_data') and view.leaderboard_data:
            total_pages = (len(view.leaderboard_data) +
                           MentionsConfig.USERS_PER_PAGE - 1) // MentionsConfig.USERS_PER_PAGE
        else:
            total_pages = 1

        modal = PageJumpModal(view, total_pages)
        await interaction.response.send_modal(modal)


class MentionsMetricSelect(discord.ui.Select):
    def __init__(self, current_metric: str):
        options = [
            discord.SelectOption(label="Mentions Sent", value="sent",
                                 description="Users who sent the most mentions"),
            discord.SelectOption(label="Mentions Received", value="received",
                                 description="Users who received the most mentions"),
        ]

        for option in options:
            option.default = (option.value == current_metric)

        super().__init__(placeholder="Select metric type...",
                         options=options, custom_id="mentions_metric")

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False)

        view = self.view
        view.metric_type = self.values[0]
        view.page = 0
        await view.update_message(interaction)


class MentionsRatioOrderSelect(discord.ui.Select):
    def __init__(self, current_order: str):
        options = [
            discord.SelectOption(label="High Ratio (Most Popular)", value="high",
                                 description="Users who receive more mentions than they send"),
            discord.SelectOption(label="Low Ratio (Most Ignored)", value="low",
                                 description="Users who send more mentions than they receive"),
        ]

        for option in options:
            option.default = (option.value == current_order)

        super().__init__(placeholder="Select ratio order...",
                         options=options, custom_id="mentions_ratio_order")

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False)

        view = self.view
        view.ratio_order = self.values[0]
        view.page = 0
        await view.update_message(interaction)


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

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            role_id_value = self.role_id.value.strip()

            try:
                role_id_int = int(role_id_value)
            except ValueError:
                embed = discord.Embed(
                    title="Invalid Role ID", description="Please enter a valid numeric Role ID.", color=discord.Color.red())
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            db_cog = self.cog.db_cog
            role_name = None
            if db_cog and hasattr(db_cog, 'get_role_name_from_db'):
                role_name = await db_cog.get_role_name_from_db(self.guild.id, role_id_int)

            if not role_name:
                embed = discord.Embed(
                    title="Invalid Role ID", description="The role ID you inputted is not valid in this server.", color=discord.Color.red())
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            await interaction.response.defer(ephemeral=False)

            view = self.cog.active_views.get(self.original_message_id)
            if view:
                view.selected_role_id = role_id_value
                view.role_filter_name = role_name
                view.page = 0
                await view.update_message(interaction)
            else:
                await interaction.followup.send("❌ Could not find the leaderboard view.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in role modal: {e}")
            embed = discord.Embed(
                title="Error", description="An error occurred while processing the role ID.", color=discord.Color.red())
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)


class RoleIdButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary,
                         label="Filter By Role", custom_id="mentions_role_filter")

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if hasattr(view, 'guild'):
            modal = RoleIdModal(view.cog, interaction.message.id, view.guild)
            await interaction.response.send_modal(modal)


class MentionsLeaderboardView(discord.ui.View):
    def __init__(self, cog_instance, guild: discord.Guild, start_time: datetime = None, end_time: datetime = None,
                 days_back_equiv: int = 30, display_text: str = "30 days", metric_type: str = "sent",
                 page: int = 0, selected_role_id: str = None, pool=None, using_server_default: bool = True,
                 target_channel: Union[discord.TextChannel,
                                       discord.VoiceChannel] = None,
                 target_category: discord.CategoryChannel = None,
                 target_user: discord.Member = None,
                 selected_role_name: str = None):
        super().__init__(timeout=600)
        self.cog = cog_instance
        self.guild = guild
        self.current_start_time = start_time
        self.current_end_time = end_time
        self.current_days_back_equiv = days_back_equiv
        self.current_display_text = display_text
        self.metric_type = metric_type
        self.page = page
        self.selected_role_id = selected_role_id
        self.role_filter_name = selected_role_name
        self.pool = pool
        self.using_server_default = using_server_default
        self.show_time_buttons = False
        self.leaderboard_data = []
        self.target_channel = target_channel
        self.target_category = target_category
        self.target_user = target_user
        self._update_buttons()

    def _update_buttons(self):
        self.clear_items()

        self.add_item(MentionsMetricSelect(self.metric_type))

        self.add_item(MentionsPrevButton())
        self.add_item(MentionsPageIndicator())
        self.add_item(MentionsNextButton())

        self.add_item(RoleIdButton())

        refresh_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=discord.PartialEmoji(name="refresh", id=1518249841505861743),
            custom_id="mentions_refresh", row=3)
        refresh_button.callback = self.refresh_callback
        time_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=discord.PartialEmoji(name="clockk", id=1518249803069259867),
            custom_id="mentions_time", row=3)
        time_button.callback = self.time_settings_callback
        self.add_item(refresh_button)
        self.add_item(time_button)

        if self.show_time_buttons:
            row = 4
            all_time = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 999999 else discord.ButtonStyle.secondary,
                label="All Time", custom_id="mentions_all_time", row=row
            )
            all_time.callback = self.all_time_callback
            self.add_item(all_time)

            for days in MentionsConfig.TIME_PERIODS:
                days_button = discord.ui.Button(
                    style=discord.ButtonStyle.primary if self.current_days_back_equiv == days else discord.ButtonStyle.secondary,
                    label=f"{days} Days", custom_id=f"mentions_days_{days}", row=row
                )
                days_button.callback = self.create_days_callback(days)
                self.add_item(days_button)

            custom_button = discord.ui.Button(
                style=discord.ButtonStyle.success if self.current_days_back_equiv not in MentionsConfig.TIME_PERIODS and self.current_days_back_equiv != 999999 else discord.ButtonStyle.secondary,
                label=f"Custom ({self.current_days_back_equiv}d)" if self.current_days_back_equiv not in MentionsConfig.TIME_PERIODS and self.current_days_back_equiv != 999999 else "Custom",
                custom_id="mentions_custom", row=row
            )
            custom_button.callback = self.custom_days_callback
            self.add_item(custom_button)

    def create_days_callback(self, days: int):
        @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
        async def callback(interaction: discord.Interaction):
            now = datetime.now(timezone.utc)
            await self.handle_time_period_change(interaction, days, now - timedelta(days=days), now, f"{days} days")
        return callback

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def all_time_callback(self, interaction: discord.Interaction):
        now = datetime.now(timezone.utc)
        await self.handle_time_period_change(interaction, 999999, None, now, "All Time")

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def refresh_callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False)
        await self.update_message(interaction)

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def time_settings_callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False)
        self.show_time_buttons = not self.show_time_buttons
        self._update_buttons()
        await interaction.edit_original_response(view=self)

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def custom_days_callback(self, interaction: discord.Interaction):
        modal = MentionsTimeModal(self.cog, interaction.message.id, self.guild,
                                  self.target_channel, self.target_category, self.target_user)
        await interaction.response.send_modal(modal)

    async def handle_time_period_change(self, interaction: discord.Interaction, days_back_equiv: int, start_time: datetime, end_time: datetime, display_text: str):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False)
        self.current_start_time = start_time
        self.current_end_time = end_time
        self.current_days_back_equiv = days_back_equiv
        self.current_display_text = display_text
        self.using_server_default = False
        self.show_time_buttons = False
        self.page = 0
        await self.update_message(interaction)

    async def _get_decrypted_username(self, user_id: int) -> Optional[str]:
        if not self.cog.db_cog:
            return None
        return await self.cog.db_cog.get_decrypted_username_any_table(self.guild.id, user_id)

    async def fetch_data(self):
        if not self.cog.db_cog:
            return []

        role_filter_ids = None
        if self.selected_role_id and self.selected_role_id != "none":
            role_filter_ids = [int(self.selected_role_id)]

        if self.target_user:
            if self.metric_type == "sent":
                data = await self.cog.db_cog.q_leaderboard_mentions_to_user_server(
                    guild_id=self.guild.id,
                    source_user_id=self.target_user.id,
                    limit=100,
                    role_filter_ids=role_filter_ids,
                    start_time=self.current_start_time,
                    end_time=self.current_end_time
                )
            else:
                data = await self.cog.db_cog.q_leaderboard_mentions_target_user_server(
                    guild_id=self.guild.id,
                    target_user_id=self.target_user.id,
                    limit=100,
                    role_filter_ids=role_filter_ids,
                    start_time=self.current_start_time,
                    end_time=self.current_end_time
                )
        elif self.target_channel:
            if isinstance(self.target_channel, discord.TextChannel):
                if self.metric_type == "sent":
                    data = await self.cog.db_cog.q_leaderboard_mentions_sent_channel(
                        guild_id=self.guild.id,
                        channel_id=self.target_channel.id,
                        limit=100,
                        role_filter_ids=role_filter_ids,
                        start_time=self.current_start_time,
                        end_time=self.current_end_time
                    )
                else:
                    data = await self.cog.db_cog.q_leaderboard_mentions_received_channel(
                        guild_id=self.guild.id,
                        channel_id=self.target_channel.id,
                        limit=100,
                        role_filter_ids=role_filter_ids,
                        start_time=self.current_start_time,
                        end_time=self.current_end_time
                    )
            else:
                return []
        elif self.target_category:
            if self.metric_type == "sent":
                data = await self.cog.db_cog.q_leaderboard_mentions_sent_category(
                    guild_id=self.guild.id,
                    category_id=self.target_category.id,
                    limit=100,
                    role_filter_ids=role_filter_ids,
                    start_time=self.current_start_time,
                    end_time=self.current_end_time
                )
            else:
                data = await self.cog.db_cog.q_leaderboard_mentions_received_category(
                    guild_id=self.guild.id,
                    category_id=self.target_category.id,
                    limit=100,
                    role_filter_ids=role_filter_ids,
                    start_time=self.current_start_time,
                    end_time=self.current_end_time
                )
        else:
            if self.metric_type == "sent":
                data = await self.cog.db_cog.q_leaderboard_mentions_sent_server(
                    guild_id=self.guild.id,
                    limit=100,
                    role_filter_ids=role_filter_ids,
                    start_time=self.current_start_time,
                    end_time=self.current_end_time
                )
            else:
                data = await self.cog.db_cog.q_leaderboard_mentions_received_server(
                    guild_id=self.guild.id,
                    limit=100,
                    role_filter_ids=role_filter_ids,
                    start_time=self.current_start_time,
                    end_time=self.current_end_time
                )

        formatted_data = []
        for item in data:
            user_id = item.get('user_id')
            mention_count = item.get('mention_count', 0)

            name = await self._get_decrypted_username(user_id)
            if not name:
                name = f"User {user_id}"

            formatted_data.append({
                'user_id': user_id,
                'name': name,
                'mention_count': mention_count
            })

        return formatted_data

    async def generate_image(self):
        self.leaderboard_data = await self.fetch_data()

        return await MentionsImageGenerator.generate_leaderboard_image(
            guild=self.guild,
            leaderboard_data=self.leaderboard_data,
            title=self.guild.name,
            display_text=self.current_display_text,
            role_id=self.role_filter_name,
            page=self.page,
            pool=self.pool,
            target_user=self.target_user,
            metric_type=self.metric_type
        )

    async def update_message(self, interaction: discord.Interaction):
        try:
            img_bytes = await self.generate_image()

            total_items = len(self.leaderboard_data)
            total_pages = max(
                1, (total_items + MentionsConfig.USERS_PER_PAGE - 1) // MentionsConfig.USERS_PER_PAGE)

            if self.page >= total_pages:
                self.page = max(0, total_pages - 1)

            for child in self.children:
                if isinstance(child, MentionsPageIndicator):
                    child.label = f"Page {self.page + 1}/{total_pages}"
                elif isinstance(child, MentionsPrevButton):
                    child.disabled = (self.page == 0 or total_pages <= 1)
                elif isinstance(child, MentionsNextButton):
                    child.disabled = (
                        self.page >= total_pages - 1 or total_pages <= 1)

            self._update_buttons()

            file = discord.File(img_bytes, filename="mentions_leaderboard.png")

            if interaction.response.is_done():
                await interaction.edit_original_response(attachments=[file], view=self)
            else:
                await interaction.response.edit_message(attachments=[file], view=self)

        except Exception as e:
            logger.error(f"Error updating mentions leaderboard: {e}")
            traceback.print_exc()
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ An error occurred while updating the leaderboard.", ephemeral=True)
                else:
                    await interaction.followup.send("❌ An error occurred while updating the leaderboard.", ephemeral=True)
            except:
                pass


class MentionsRatioLeaderboardView(discord.ui.View):
    def __init__(self, cog_instance, guild: discord.Guild, start_time: datetime = None, end_time: datetime = None,
                 days_back_equiv: int = 30, display_text: str = "30 days", ratio_order: str = "high",
                 page: int = 0, selected_role_id: str = None, pool=None, using_server_default: bool = True,
                 target_channel: Union[discord.TextChannel,
                                       discord.VoiceChannel] = None,
                 target_category: discord.CategoryChannel = None,
                 selected_role_name: str = None):
        super().__init__(timeout=600)
        self.cog = cog_instance
        self.guild = guild
        self.current_start_time = start_time
        self.current_end_time = end_time
        self.current_days_back_equiv = days_back_equiv
        self.current_display_text = display_text
        self.ratio_order = ratio_order
        self.page = page
        self.selected_role_id = selected_role_id
        self.role_filter_name = selected_role_name
        self.pool = pool
        self.using_server_default = using_server_default
        self.show_time_buttons = False
        self.leaderboard_data = []
        self.target_channel = target_channel
        self.target_category = target_category
        self._update_buttons()

    def _update_buttons(self):
        self.clear_items()

        self.add_item(MentionsRatioOrderSelect(self.ratio_order))

        self.add_item(MentionsPrevButton())
        self.add_item(MentionsPageIndicator())
        self.add_item(MentionsNextButton())

        self.add_item(RoleIdButton())

        refresh = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=discord.PartialEmoji(name="refresh", id=1518249841505861743),
            custom_id="ratio_refresh", row=3)
        refresh.callback = self.refresh_callback
        time_btn = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=discord.PartialEmoji(name="clockk", id=1518249803069259867),
            custom_id="ratio_time", row=3)
        time_btn.callback = self.time_settings_callback
        self.add_item(refresh)
        self.add_item(time_btn)

        if self.show_time_buttons:
            row = 4
            all_time = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 999999 else discord.ButtonStyle.secondary,
                label="All Time", custom_id="ratio_all_time", row=row
            )
            all_time.callback = self.all_time_callback
            self.add_item(all_time)

            for days in MentionsConfig.TIME_PERIODS:
                days_btn = discord.ui.Button(
                    style=discord.ButtonStyle.primary if self.current_days_back_equiv == days else discord.ButtonStyle.secondary,
                    label=f"{days} Days", custom_id=f"ratio_days_{days}", row=row
                )
                days_btn.callback = self.create_days_callback(days)
                self.add_item(days_btn)

            custom = discord.ui.Button(
                style=discord.ButtonStyle.success if self.current_days_back_equiv not in MentionsConfig.TIME_PERIODS and self.current_days_back_equiv != 999999 else discord.ButtonStyle.secondary,
                label=f"Custom ({self.current_days_back_equiv}d)" if self.current_days_back_equiv not in MentionsConfig.TIME_PERIODS and self.current_days_back_equiv != 999999 else "Custom",
                custom_id="ratio_custom", row=row
            )
            custom.callback = self.custom_days_callback
            self.add_item(custom)

    def create_days_callback(self, days: int):
        @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
        async def callback(interaction: discord.Interaction):
            now = datetime.now(timezone.utc)
            await self.handle_time_period_change(interaction, days, now - timedelta(days=days), now, f"{days} days")
        return callback

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def all_time_callback(self, interaction: discord.Interaction):
        now = datetime.now(timezone.utc)
        await self.handle_time_period_change(interaction, 999999, None, now, "All Time")

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def refresh_callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False)
        await self.update_message(interaction)

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def time_settings_callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False)
        self.show_time_buttons = not self.show_time_buttons
        self._update_buttons()
        await interaction.edit_original_response(view=self)

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def custom_days_callback(self, interaction: discord.Interaction):
        modal = MentionsTimeModal(self.cog, interaction.message.id,
                                  self.guild, self.target_channel, self.target_category)
        await interaction.response.send_modal(modal)

    async def handle_time_period_change(self, interaction: discord.Interaction, days_back_equiv: int, start_time: datetime, end_time: datetime, display_text: str):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False)
        self.current_start_time = start_time
        self.current_end_time = end_time
        self.current_days_back_equiv = days_back_equiv
        self.current_display_text = display_text
        self.using_server_default = False
        self.show_time_buttons = False
        self.page = 0
        await self.update_message(interaction)

    async def _get_decrypted_username(self, user_id: int) -> Optional[str]:
        if not self.cog.db_cog:
            return None
        return await self.cog.db_cog.get_decrypted_username_any_table(self.guild.id, user_id)

    async def fetch_data(self):
        if not self.cog.db_cog:
            return []

        role_filter_ids = None
        if self.selected_role_id and self.selected_role_id != "none":
            role_filter_ids = [int(self.selected_role_id)]

        if self.target_channel:
            if isinstance(self.target_channel, discord.TextChannel):
                data = await self.cog.db_cog.q_leaderboard_mentions_ratio_channel(
                    guild_id=self.guild.id,
                    channel_id=self.target_channel.id,
                    limit=100,
                    min_mentions_sent=1,
                    role_filter_ids=role_filter_ids,
                    start_time=self.current_start_time,
                    end_time=self.current_end_time
                )
                if self.ratio_order == "low" and data:
                    data = list(reversed(data))
            else:
                return []
        elif self.target_category:
            data = await self.cog.db_cog.q_leaderboard_mentions_ratio_category(
                guild_id=self.guild.id,
                category_id=self.target_category.id,
                limit=100,
                min_mentions_sent=1,
                role_filter_ids=role_filter_ids,
                start_time=self.current_start_time,
                end_time=self.current_end_time
            )
            if self.ratio_order == "low" and data:
                data = list(reversed(data))
        else:
            data = await self.cog.db_cog.q_leaderboard_mentions_ratio_server(
                guild_id=self.guild.id,
                limit=100,
                min_mentions_sent=1,
                role_filter_ids=role_filter_ids,
                start_time=self.current_start_time,
                end_time=self.current_end_time
            )
            if self.ratio_order == "low" and data:
                data = list(reversed(data))

        formatted_data = []
        for item in data:
            user_id = item.get('user_id')
            mentions_received = item.get('mentions_received', 0)
            mentions_sent = item.get('mentions_sent', 0)
            ratio = item.get('ratio', 0.0)

            name = await self._get_decrypted_username(user_id)
            if not name:
                name = f"User {user_id}"

            if mentions_sent == 0:
                safe_ratio = float(mentions_received) / 1.0
            else:
                safe_ratio = ratio

            ratio_display = f"{safe_ratio:.1f}"

            formatted_data.append({
                'user_id': user_id,
                'name': name,
                'mention_count': mentions_received,
                'ratio_display': ratio_display,
            })

        return formatted_data

    async def generate_image(self):
        self.leaderboard_data = await self.fetch_data()

        return await MentionsImageGenerator.generate_leaderboard_image(
            guild=self.guild,
            leaderboard_data=self.leaderboard_data,
            title=self.guild.name,
            display_text=self.current_display_text,
            role_id=self.role_filter_name,
            page=self.page,
            pool=self.pool,
            target_user=None,
            metric_type="ratio"
        )

    async def update_message(self, interaction: discord.Interaction):
        try:
            img_bytes = await self.generate_image()

            total_items = len(self.leaderboard_data)
            total_pages = max(
                1, (total_items + MentionsConfig.USERS_PER_PAGE - 1) // MentionsConfig.USERS_PER_PAGE)

            if self.page >= total_pages:
                self.page = max(0, total_pages - 1)

            for child in self.children:
                if isinstance(child, MentionsPageIndicator):
                    child.label = f"Page {self.page + 1}/{total_pages}"
                elif isinstance(child, MentionsPrevButton):
                    child.disabled = (self.page == 0 or total_pages <= 1)
                elif isinstance(child, MentionsNextButton):
                    child.disabled = (
                        self.page >= total_pages - 1 or total_pages <= 1)

            self._update_buttons()

            file = discord.File(
                img_bytes, filename="mentions_ratio_leaderboard.png")

            if interaction.response.is_done():
                await interaction.edit_original_response(attachments=[file], view=self)
            else:
                await interaction.response.edit_message(attachments=[file], view=self)

        except Exception as e:
            logger.error(f"Error updating ratio leaderboard: {e}")
            traceback.print_exc()
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ An error occurred while updating the leaderboard.", ephemeral=True)
                else:
                    await interaction.followup.send("❌ An error occurred while updating the leaderboard.", ephemeral=True)
            except:
                pass


class MentionsRatioEmbedView(discord.ui.View):
    def __init__(self, cog_instance, guild: discord.Guild, start_time: datetime = None, end_time: datetime = None,
                 days_back_equiv: int = 30, display_text: str = "30 days", target_user: discord.Member = None):
        super().__init__(timeout=600)
        self.cog = cog_instance
        self.guild = guild
        self.current_start_time = start_time
        self.current_end_time = end_time
        self.current_days_back_equiv = days_back_equiv
        self.current_display_text = display_text
        self.target_user = target_user
        self.show_time_buttons = False
        self._update_buttons()

    def _update_buttons(self):
        self.clear_items()

        refresh_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=discord.PartialEmoji(name="refresh", id=1518249841505861743),
            custom_id="ratio_embed_refresh")
        refresh_button.callback = self.refresh_callback
        time_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=discord.PartialEmoji(name="clockk", id=1518249803069259867),
            custom_id="ratio_embed_time")
        time_button.callback = self.time_settings_callback
        self.add_item(refresh_button)
        self.add_item(time_button)

        if self.show_time_buttons:
            row = 2
            all_time = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days_back_equiv == 999999 else discord.ButtonStyle.secondary,
                label="All Time", custom_id="ratio_embed_all_time", row=row
            )
            all_time.callback = self.all_time_callback
            self.add_item(all_time)

            for days in MentionsConfig.TIME_PERIODS:
                days_button = discord.ui.Button(
                    style=discord.ButtonStyle.primary if self.current_days_back_equiv == days else discord.ButtonStyle.secondary,
                    label=f"{days} Days", custom_id=f"ratio_embed_days_{days}", row=row
                )
                days_button.callback = self.create_days_callback(days)
                self.add_item(days_button)

            custom_button = discord.ui.Button(
                style=discord.ButtonStyle.success if self.current_days_back_equiv not in MentionsConfig.TIME_PERIODS and self.current_days_back_equiv != 999999 else discord.ButtonStyle.secondary,
                label=f"Custom ({self.current_days_back_equiv}d)" if self.current_days_back_equiv not in MentionsConfig.TIME_PERIODS and self.current_days_back_equiv != 999999 else "Custom",
                custom_id="ratio_embed_custom", row=row
            )
            custom_button.callback = self.custom_days_callback
            self.add_item(custom_button)

    def create_days_callback(self, days: int):
        @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
        async def callback(interaction: discord.Interaction):
            now = datetime.now(timezone.utc)
            await self.handle_time_period_change(interaction, days, now - timedelta(days=days), now, f"{days} days")
        return callback

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def all_time_callback(self, interaction: discord.Interaction):
        now = datetime.now(timezone.utc)
        await self.handle_time_period_change(interaction, 999999, None, now, "All Time")

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def refresh_callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False)
        await self.update_embed(interaction)

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def time_settings_callback(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False)
        self.show_time_buttons = not self.show_time_buttons
        self._update_buttons()
        await interaction.edit_original_response(view=self)

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def custom_days_callback(self, interaction: discord.Interaction):
        modal = MentionsTimeModal(self.cog, interaction.message.id, self.guild)
        await interaction.response.send_modal(modal)

    async def handle_time_period_change(self, interaction: discord.Interaction, days_back_equiv: int, start_time: datetime, end_time: datetime, display_text: str):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False)
        self.current_start_time = start_time
        self.current_end_time = end_time
        self.current_days_back_equiv = days_back_equiv
        self.current_display_text = display_text
        self.show_time_buttons = False
        await self.update_embed(interaction)

    async def update_embed(self, interaction: discord.Interaction):
        try:
            ratio_data = await self.cog.db_cog.q_user_mentions_ratio_server(
                guild_id=self.guild.id,
                user_id=self.target_user.id,
                start_time=self.current_start_time,
                end_time=self.current_end_time
            )

            mentions_sent = ratio_data.get('mentions_sent', 0)
            mentions_received = ratio_data.get('mentions_received', 0)
            ratio = ratio_data.get('ratio', 0.0)

            if mentions_sent == 0:
                safe_ratio = float(mentions_received) / 1.0
            else:
                safe_ratio = ratio

            ratio_display = f"{safe_ratio:.1f}"

            embed = discord.Embed(
                title=f"Mentions Ratio for {self.target_user.display_name}",
                description=f"**Ratio:** {ratio_display}\n\n"
                f"**Mentions Received/Mentions Sent = **{format_mention_count(mentions_received)} / {format_mention_count(mentions_sent)}\n",
                color=discord.Color.from_rgb(170, 0, 255)
            )

            if self.target_user.avatar:
                embed.set_thumbnail(url=self.target_user.avatar.url)

            embed.set_footer(text=f"Time Period: {self.current_display_text}")

            self._update_buttons()

            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed, view=self)
            else:
                await interaction.response.edit_message(embed=embed, view=self)

        except Exception as e:
            logger.error(f"Error updating ratio embed: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ An error occurred while updating the ratio.", ephemeral=True)
                else:
                    await interaction.followup.send("❌ An error occurred while updating the ratio.", ephemeral=True)
            except:
                pass


class Mentions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_cog = None
        self.active_views = {}
        self.rate_limiter = get_rate_limiter()
        self.clean_cache_task.start()

    def cog_unload(self):
        self.clean_cache_task.cancel()

    @tasks.loop(hours=1)
    async def clean_cache_task(self):
        gc.collect()

    async def cog_load(self):
        for _ in range(30):
            self.db_cog = self.bot.get_cog('DatabaseStats')
            if self.db_cog:
                break
            await asyncio.sleep(1)

    async def get_server_default_time_range(self, guild: discord.Guild) -> tuple:
        """Get the default time range from server settings. Returns (start_time, end_time, display_text, days_back_equiv)"""
        try:
            settings_cog = self.bot.get_cog('Settings')
            if not settings_cog:
                end = datetime.now(timezone.utc)
                start = end - timedelta(days=14)
                return (start, end, "14 days", 14)

            settings = await settings_cog.get_guild_settings(guild.id)
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

    async def _check_permission(self, ctx_or_interaction) -> bool:
        user = ctx_or_interaction.user if hasattr(
            ctx_or_interaction, 'user') else ctx_or_interaction.author
        guild = ctx_or_interaction.guild

        if user.guild_permissions.administrator:
            return True

        settings_cog = self.bot.get_cog('Settings')
        if not settings_cog:
            return True

        try:
            settings = await settings_cog.get_guild_settings(guild.id)
            permission_level = settings.get('permission_level', 'Default')
            if permission_level in ['All', 'Default', 'User Restriction']:
                return True
            elif permission_level == 'Admin':
                return False
            elif permission_level == 'Moderator':
                return user.guild_permissions.manage_guild
            return True
        except Exception:
            return True

    # ============================================================================
    # SLASH COMMANDS
    # ============================================================================

    mentions_group = app_commands.Group(
        name="mentions", description="Mentions statistics and leaderboard commands")
    ratios_group = app_commands.Group(
        name="ratios", description="Mentions ratio commands", parent=mentions_group)

    @mentions_group.command(name="leaderboard", description="Show mentions leaderboard for the server, channel, category, or user")
    @app_commands.describe(
        target="Optional: Channel or category to filter by",
        target_user="Optional: User to analyze (shows who mentioned them or who they mentioned)"
    )
    @app_commands.rename(target_user="user")
    async def slash_mentions_leaderboard(
        self,
        interaction: discord.Interaction,
        target: Optional[Union[discord.TextChannel,
                               discord.VoiceChannel, discord.CategoryChannel]] = None,
        target_user: Optional[discord.Member] = None
    ):
        await self._handle_slash_leaderboard(interaction, target, target_user)

    @ratios_group.command(name="leaderboard", description="Show mentions ratios leaderboard")
    @app_commands.describe(target="Optional: Channel or category to filter by")
    async def slash_mentions_ratios_leaderboard(
        self,
        interaction: discord.Interaction,
        target: Optional[Union[discord.TextChannel,
                               discord.VoiceChannel, discord.CategoryChannel]] = None
    ):
        await self._handle_slash_ratios_leaderboard(interaction, target)

    @mentions_group.command(name="ratio", description="Show your mentions ratio (received/sent)")
    @app_commands.describe(target_user="The user to check (optional - defaults to you)")
    @app_commands.rename(target_user="user")
    async def slash_mentions_ratio(self, interaction: discord.Interaction, target_user: Optional[discord.Member] = None):
        await self._handle_slash_ratio(interaction, target_user or interaction.user)

    # ============================================================================
    # PREFIX COMMANDS
    # ============================================================================

    @commands.group(name="mentions", invoke_without_command=True)
    async def prefix_mentions(self, ctx: commands.Context):
        """Mentions commands."""
        await ctx.send("Available mentions commands:\n"
                       "- `mentions leaderboard [channel/category] [user]` - Mentions leaderboard\n"
                       "- `mentions ratios leaderboard [channel/category]` - Mentions ratios leaderboard\n"
                       "- `mentions ratio [user]` - Mentions ratio for a user\n\n"
                       "Shortcuts:\n"
                       "- `ml [channel/category] [user]` - Mentions leaderboard\n"
                       "- `mrl [channel/category]` - Mentions ratios leaderboard\n"
                       "- `mr [user]` - Mentions ratio")

    @prefix_mentions.command(name="leaderboard")
    async def prefix_mentions_leaderboard(
        self,
        ctx: commands.Context,
        target: Optional[Union[discord.TextChannel,
                               discord.VoiceChannel, discord.CategoryChannel]] = None,
        target_user: Optional[discord.Member] = None
    ):
        await self._handle_prefix_leaderboard(ctx, target, target_user)

    @prefix_mentions.command(name="ratios")
    async def prefix_mentions_ratios_leaderboard(
        self,
        ctx: commands.Context,
        target: Optional[Union[discord.TextChannel,
                               discord.VoiceChannel, discord.CategoryChannel]] = None
    ):
        await self._handle_prefix_ratios_leaderboard(ctx, target)

    @prefix_mentions.command(name="ratio")
    async def prefix_mentions_ratio(self, ctx: commands.Context, target_user: Optional[discord.Member] = None):
        await self._handle_prefix_ratio(ctx, target_user or ctx.author)

    # ============================================================================
    # SHORTCUTS
    # ============================================================================

    @commands.command(name="ml")
    async def shortcut_ml(
        self,
        ctx: commands.Context,
        target: Optional[Union[discord.TextChannel,
                               discord.VoiceChannel, discord.CategoryChannel]] = None,
        target_user: Optional[discord.Member] = None
    ):
        """Shortcut for mentions leaderboard."""
        await self._handle_prefix_leaderboard(ctx, target, target_user)

    @commands.command(name="mrl")
    async def shortcut_mrl(
        self,
        ctx: commands.Context,
        target: Optional[Union[discord.TextChannel,
                               discord.VoiceChannel, discord.CategoryChannel]] = None
    ):
        """Shortcut for mentions ratio leaderboard."""
        await self._handle_prefix_ratios_leaderboard(ctx, target)

    @commands.command(name="mr")
    async def shortcut_mr(self, ctx: commands.Context, target_user: Optional[discord.Member] = None):
        """Shortcut for mentions ratio."""
        await self._handle_prefix_ratio(ctx, target_user or ctx.author)

    # ============================================================================
    # HANDLERS
    # ============================================================================

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def _handle_slash_leaderboard(
        self,
        interaction: discord.Interaction,
        target: Optional[Union[discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel]],
        target_user: Optional[discord.Member]
    ):
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        if not await self._check_permission(interaction):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return

        if not self.db_cog:
            await interaction.response.send_message("❌ Database connection not available.", ephemeral=True)
            return

        await interaction.response.defer()

        start_time, end_time, display_text, days_back_equiv = await self.get_server_default_time_range(interaction.guild)

        pool = self.db_cog.pool if hasattr(self.db_cog, 'pool') else None

        target_channel = None
        target_category = None
        target_user_param = None

        if target_user:
            target_user_param = target_user
        elif target:
            if isinstance(target, (discord.TextChannel, discord.VoiceChannel)):
                target_channel = target
            elif isinstance(target, discord.CategoryChannel):
                target_category = target

        view = MentionsLeaderboardView(
            self, interaction.guild, start_time, end_time, days_back_equiv, display_text, "sent",
            selected_role_id=None, pool=pool, using_server_default=True,
            target_channel=target_channel,
            target_category=target_category,
            target_user=target_user_param
        )

        img_bytes = await view.generate_image()
        file = discord.File(img_bytes, filename="mentions_leaderboard.png")

        retention_alert_text = await self.db_cog.maybe_get_retention_alert(interaction.guild.id) if self.db_cog else None

        msg = await interaction.followup.send(content=retention_alert_text, file=file, view=view)
        self.active_views[msg.id] = view

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def _handle_slash_ratio(self, interaction: discord.Interaction, target_user: discord.Member):
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        if not await self._check_permission(interaction):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return

        if not self.db_cog:
            await interaction.response.send_message("❌ Database connection not available.", ephemeral=True)
            return

        await interaction.response.defer()

        start_time, end_time, display_text, days_back_equiv = await self.get_server_default_time_range(interaction.guild)

        ratio_data = await self.db_cog.q_user_mentions_ratio_server(
            guild_id=interaction.guild.id,
            user_id=target_user.id,
            start_time=start_time,
            end_time=end_time
        )

        mentions_sent = ratio_data.get('mentions_sent', 0)
        mentions_received = ratio_data.get('mentions_received', 0)
        ratio = ratio_data.get('ratio', 0.0)

        if mentions_sent == 0:
            safe_ratio = float(mentions_received) / 1.0
        else:
            safe_ratio = ratio

        ratio_display = f"{safe_ratio:.1f}"

        embed = discord.Embed(
            title=f"Mentions Ratio for {target_user.display_name}",
            description=f"**Ratio:** {ratio_display}\n\n"
            f"**Mentions Received/Mentions Sent = **{format_mention_count(mentions_received)} / {format_mention_count(mentions_sent)}\n",
            color=discord.Color.from_rgb(170, 0, 255)
        )

        if target_user.avatar:
            embed.set_thumbnail(url=target_user.avatar.url)

        embed.set_footer(text=f"Time Period: {display_text}")

        view = MentionsRatioEmbedView(
            self, interaction.guild, start_time, end_time, days_back_equiv, display_text, target_user)

        retention_alert_text = await self.db_cog.maybe_get_retention_alert(interaction.guild.id) if self.db_cog else None

        await interaction.followup.send(content=retention_alert_text, embed=embed, view=view)

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def _handle_slash_ratios_leaderboard(
        self,
        interaction: discord.Interaction,
        target: Optional[Union[discord.TextChannel,
                               discord.VoiceChannel, discord.CategoryChannel]]
    ):
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        if not await self._check_permission(interaction):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
            return

        if not self.db_cog:
            await interaction.response.send_message("❌ Database connection not available.", ephemeral=True)
            return

        await interaction.response.defer()

        start_time, end_time, display_text, days_back_equiv = await self.get_server_default_time_range(interaction.guild)

        pool = self.db_cog.pool if hasattr(self.db_cog, 'pool') else None

        target_channel = None
        target_category = None

        if target:
            if isinstance(target, (discord.TextChannel, discord.VoiceChannel)):
                target_channel = target
            elif isinstance(target, discord.CategoryChannel):
                target_category = target

        view = MentionsRatioLeaderboardView(
            self, interaction.guild, start_time, end_time, days_back_equiv, display_text, "high",
            selected_role_id=None, pool=pool, using_server_default=True,
            target_channel=target_channel,
            target_category=target_category
        )

        img_bytes = await view.generate_image()
        file = discord.File(
            img_bytes, filename="mentions_ratios_leaderboard.png")

        retention_alert_text = await self.db_cog.maybe_get_retention_alert(interaction.guild.id) if self.db_cog else None

        msg = await interaction.followup.send(content=retention_alert_text, file=file, view=view)
        self.active_views[msg.id] = view

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def _handle_prefix_leaderboard(
        self,
        ctx: commands.Context,
        target: Optional[Union[discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel]],
        target_user: Optional[discord.Member]
    ):
        if not ctx.guild:
            await ctx.send("❌ This command can only be used in a server.", delete_after=5)
            return

        if not await self._check_permission(ctx):
            await ctx.send("❌ You don't have permission to use this command.", delete_after=10)
            return

        if not self.db_cog:
            await ctx.send("❌ Database connection not available.", delete_after=10)
            return

        try:
            await ctx.message.delete()
        except:
            pass

        await ctx.defer()

        start_time, end_time, display_text, days_back_equiv = await self.get_server_default_time_range(ctx.guild)

        pool = self.db_cog.pool if hasattr(self.db_cog, 'pool') else None

        target_channel = None
        target_category = None
        target_user_param = None

        if target_user:
            target_user_param = target_user
        elif target:
            if isinstance(target, (discord.TextChannel, discord.VoiceChannel)):
                target_channel = target
            elif isinstance(target, discord.CategoryChannel):
                target_category = target

        view = MentionsLeaderboardView(
            self, ctx.guild, start_time, end_time, days_back_equiv, display_text, "sent",
            selected_role_id=None, pool=pool, using_server_default=True,
            target_channel=target_channel,
            target_category=target_category,
            target_user=target_user_param
        )

        img_bytes = await view.generate_image()
        file = discord.File(img_bytes, filename="mentions_leaderboard.png")

        retention_alert_text = await self.db_cog.maybe_get_retention_alert(ctx.guild.id) if self.db_cog else None

        msg = await ctx.send(content=retention_alert_text, file=file, view=view)
        self.active_views[msg.id] = view

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def _handle_prefix_ratio(self, ctx: commands.Context, target_user: discord.Member):
        if not ctx.guild:
            await ctx.send("❌ This command can only be used in a server.", delete_after=5)
            return

        if not await self._check_permission(ctx):
            await ctx.send("❌ You don't have permission to use this command.", delete_after=10)
            return

        if not self.db_cog:
            await ctx.send("❌ Database connection not available.", delete_after=10)
            return

        try:
            await ctx.message.delete()
        except:
            pass

        await ctx.defer()

        start_time, end_time, display_text, days_back_equiv = await self.get_server_default_time_range(ctx.guild)

        ratio_data = await self.db_cog.q_user_mentions_ratio_server(
            guild_id=ctx.guild.id,
            user_id=target_user.id,
            start_time=start_time,
            end_time=end_time
        )

        mentions_sent = ratio_data.get('mentions_sent', 0)
        mentions_received = ratio_data.get('mentions_received', 0)
        ratio = ratio_data.get('ratio', 0.0)

        if mentions_sent == 0:
            safe_ratio = float(mentions_received) / 1.0
        else:
            safe_ratio = ratio

        ratio_display = f"{safe_ratio:.1f}"

        embed = discord.Embed(
            title=f"Mentions Ratio for {target_user.display_name}",
            description=f"**Ratio:** {ratio_display}\n\n"
            f"**Mentions Received/Mentions Sent = **{format_mention_count(mentions_received)} / {format_mention_count(mentions_sent)}\n",
            color=discord.Color.from_rgb(170, 0, 255)
        )

        if target_user.avatar:
            embed.set_thumbnail(url=target_user.avatar.url)

        embed.set_footer(text=f"Time Period: {display_text}")

        view = MentionsRatioEmbedView(
            self, ctx.guild, start_time, end_time, days_back_equiv, display_text, target_user)

        retention_alert_text = await self.db_cog.maybe_get_retention_alert(ctx.guild.id) if self.db_cog else None

        await ctx.send(content=retention_alert_text, embed=embed, view=view)

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def _handle_prefix_ratios_leaderboard(
        self,
        ctx: commands.Context,
        target: Optional[Union[discord.TextChannel,
                               discord.VoiceChannel, discord.CategoryChannel]]
    ):
        if not ctx.guild:
            await ctx.send("❌ This command can only be used in a server.", delete_after=5)
            return

        if not await self._check_permission(ctx):
            await ctx.send("❌ You don't have permission to use this command.", delete_after=10)
            return

        if not self.db_cog:
            await ctx.send("❌ Database connection not available.", delete_after=10)
            return

        try:
            await ctx.message.delete()
        except:
            pass

        await ctx.defer()

        start_time, end_time, display_text, days_back_equiv = await self.get_server_default_time_range(ctx.guild)

        pool = self.db_cog.pool if hasattr(self.db_cog, 'pool') else None

        target_channel = None
        target_category = None

        if target:
            if isinstance(target, (discord.TextChannel, discord.VoiceChannel)):
                target_channel = target
            elif isinstance(target, discord.CategoryChannel):
                target_category = target

        view = MentionsRatioLeaderboardView(
            self, ctx.guild, start_time, end_time, days_back_equiv, display_text, "high",
            selected_role_id=None, pool=pool, using_server_default=True,
            target_channel=target_channel,
            target_category=target_category
        )

        img_bytes = await view.generate_image()
        file = discord.File(
            img_bytes, filename="mentions_ratios_leaderboard.png")

        retention_alert_text = await self.db_cog.maybe_get_retention_alert(ctx.guild.id) if self.db_cog else None

        msg = await ctx.send(content=retention_alert_text, file=file, view=view)
        self.active_views[msg.id] = view


async def setup(bot):
    await bot.add_cog(Mentions(bot))
