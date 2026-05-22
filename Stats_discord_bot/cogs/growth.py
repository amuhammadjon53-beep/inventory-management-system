import numpy as np
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncpg
import asyncio
from datetime import datetime, timedelta, date, timezone
import io
import os
from typing import Optional, Dict, List, Tuple, Any
from dotenv import load_dotenv
import aiohttp
import traceback
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from pilmoji import Pilmoji
import matplotlib
import unicodedata
import pytz
from statistics import mean, stdev
import math
import aiocron
import scipy
import time
import gc
from .ratelimiter import RateLimiter, RateLimitType, rate_limited, get_rate_limiter

# Import custom exceptions
from exceptions import (
    DatabaseConnectionError, DatabaseQueryError, DatabaseTimeoutError,
    CacheConnectionError, CacheWriteFailed, CacheReadFailed,
    CacheBatchFailed, CacheKeyNotFound
)

matplotlib.use('Agg')

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# =========================================================
# FORECASTING SYSTEM
# =========================================================


class GrowthForecaster:
    """
    Advanced growth forecasting system using:
    - 7-day moving average smoothing
    - Linear regression on smoothed data
    - Spike/anomaly detection
    """

    def __init__(self, days_data: List[Dict]):
        self.raw_data = self._extract_counts(days_data)
        self.dates = [d['date'] for d in days_data]
        self.n = len(self.raw_data)

    def _extract_counts(self, days_data: List[Dict]) -> List[float]:
        return [float(d.get('count', 0)) for d in days_data]

    def calculate_moving_average(self, window: int = 7) -> List[float]:
        if self.n < 2:
            return self.raw_data.copy()
        window = min(window, self.n)
        moving_avg = []
        for i in range(self.n):
            if i < window - 1:
                avg = sum(self.raw_data[:i+1]) / (i + 1)
            else:
                start_idx = i - window + 1
                avg = sum(self.raw_data[start_idx:i+1]) / window
            moving_avg.append(avg)
        return moving_avg

    def linear_regression(self, y_values: List[float]) -> Dict[str, float]:
        n = len(y_values)
        if n == 0:
            return {'slope': 0, 'intercept': 0, 'r2': 0, 'prediction': 0}
        if n == 1:
            return {'slope': 0, 'intercept': y_values[0], 'r2': 1.0, 'prediction': y_values[0]}

        x_values = list(range(n))
        x_mean = sum(x_values) / n
        y_mean = sum(y_values) / n

        numerator = sum((x - x_mean) * (y - y_mean)
                        for x, y in zip(x_values, y_values))
        denominator = sum((x - x_mean) ** 2 for x in x_values)
        slope = numerator / denominator if denominator != 0 else 0
        intercept = y_mean - slope * x_mean

        y_pred = [slope * x + intercept for x in x_values]
        ss_res = sum((y - yp) ** 2 for y, yp in zip(y_values, y_pred))
        ss_tot = sum((y - y_mean) ** 2 for y in y_values)
        r2 = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

        next_prediction = slope * n + intercept

        return {
            'slope': slope,
            'intercept': intercept,
            'r2': max(0, min(1, r2)),
            'prediction': max(0, next_prediction)
        }

    def detect_spikes(self, lookback_days: int = 14, threshold: float = 2.0) -> Dict[str, Any]:
        if self.n < 3:
            return {'status': 'normal', 'deviation_percent': 0, 'is_spike': False,
                    'direction': 'none', 'z_score': 0, 'expected': 0, 'actual': 0}

        lookback = min(lookback_days, self.n - 1)
        recent_data = self.raw_data[-lookback-1:-
                                    1] if lookback > 0 else self.raw_data[:-1]

        if len(recent_data) < 2:
            return {'status': 'normal', 'deviation_percent': 0, 'is_spike': False,
                    'direction': 'none', 'z_score': 0, 'expected': 0, 'actual': 0}

        baseline_mean = sum(recent_data) / len(recent_data)
        if len(recent_data) > 1:
            variance = sum((x - baseline_mean) **
                           2 for x in recent_data) / (len(recent_data) - 1)
            baseline_std = math.sqrt(variance) if variance > 0 else 0
        else:
            baseline_std = 0

        latest_value = self.raw_data[-1]

        if baseline_std == 0:
            if latest_value > baseline_mean * 1.5:
                status = 'positive_spike'
                direction = 'up'
                is_spike = True
            elif latest_value < baseline_mean * 0.5:
                status = 'negative_spike'
                direction = 'down'
                is_spike = True
            else:
                status = 'normal'
                direction = 'none'
                is_spike = False
            z_score = (latest_value - baseline_mean) / (baseline_mean + 1)
        else:
            z_score = (latest_value - baseline_mean) / baseline_std
            if z_score > threshold:
                status = 'positive_spike'
                is_spike = True
                direction = 'up'
            elif z_score < -threshold:
                status = 'negative_spike'
                is_spike = True
                direction = 'down'
            else:
                status = 'normal'
                is_spike = False
                direction = 'none'

        percent_deviation = (
            (latest_value - baseline_mean) / (baseline_mean + 1)) * 100

        return {
            'status': status,
            'deviation_percent': round(percent_deviation, 2),
            'is_spike': is_spike,
            'direction': direction,
            'z_score': round(z_score, 2),
            'expected': round(baseline_mean, 2),
            'actual': latest_value
        }

    def calculate_volatility(self, window: int = 14) -> float:
        if self.n < 3:
            return 0.0
        window = min(window, self.n)
        recent_data = self.raw_data[-window:]
        data_mean = sum(recent_data) / len(recent_data)
        if data_mean == 0:
            return 0.0
        if len(recent_data) > 1:
            variance = sum((x - data_mean) **
                           2 for x in recent_data) / (len(recent_data) - 1)
            data_std = math.sqrt(variance) if variance > 0 else 0
        else:
            data_std = 0
        return round(data_std / data_mean, 3)

    def forecast(self, days_ahead: int = 30) -> Dict[str, Any]:
        if self.n == 0:
            return {
                'baseline_prediction': 0,
                'trend_slope': 0,
                'daily_growth_rate': 0,
                'growth_rate_percent': 0,
                'r2_confidence': 0,
                'volatility': 0,
                'spike_status': 'normal',
                'spike_details': {'status': 'normal', 'deviation_percent': 0, 'is_spike': False},
                'percent_deviation_from_expected': 0,
                'future_predictions': [0] * min(days_ahead, 30),
                'trend_direction': 'stable',
                'data_points_analyzed': 0,
                'smoothed_data': []
            }

        smoothed_data = self.calculate_moving_average(7)
        regression = self.linear_regression(smoothed_data)
        spike_info = self.detect_spikes()
        volatility = self.calculate_volatility()

        # Generate predictions for ALL requested days (up to 1825 for 5 years)
        future_predictions = []
        n = len(smoothed_data)

        # Cap at 1825 days (5 years) maximum to prevent excessive calculations
        max_days = min(days_ahead, 1825)

        for i in range(1, max_days + 1):
            pred = regression['slope'] * (n + i - 1) + regression['intercept']
            future_predictions.append(max(0, round(pred, 2)))

        daily_growth_rate = regression['slope']
        growth_rate_percent = (
            daily_growth_rate / regression['intercept']) * 100 if regression['intercept'] > 0 else 0

        slope_threshold = 0.01 * \
            (sum(smoothed_data) / len(smoothed_data)) if smoothed_data else 0.01
        if regression['slope'] > slope_threshold:
            trend_direction = 'up'
        elif regression['slope'] < -slope_threshold:
            trend_direction = 'down'
        else:
            trend_direction = 'stable'

        return {
            'baseline_prediction': round(regression['prediction'], 2),
            'trend_slope': round(regression['slope'], 4),
            'daily_growth_rate': round(daily_growth_rate, 4),
            'growth_rate_percent': round(growth_rate_percent, 2),
            'r2_confidence': round(regression['r2'], 3),
            'volatility': volatility,
            'spike_status': spike_info['status'],
            'spike_details': spike_info,
            'percent_deviation_from_expected': spike_info['deviation_percent'],
            'future_predictions': future_predictions[:days_ahead],
            'trend_direction': trend_direction,
            'data_points_analyzed': self.n,
            'smoothed_data': [round(x, 2) for x in smoothed_data]
        }

# =========================================================
# DRAWING FUNCTIONS
# =========================================================


def draw_text_with_stroke(draw, position, text, font, text_color, stroke_color, stroke_width):
    x, y = position
    for dx in range(-stroke_width, stroke_width + 1):
        for dy in range(-stroke_width, stroke_width + 1):
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, font=font, fill=stroke_color)
    draw.text((x, y), text, font=font, fill=text_color)


def draw_text_with_stroke_and_emoji(pilmoji_draw, position, text, font, text_color, stroke_color, stroke_width):
    x, y = position
    for dx in range(-stroke_width, stroke_width + 1):
        for dy in range(-stroke_width, stroke_width + 1):
            if dx != 0 or dy != 0:
                pilmoji_draw.text((x + dx, y + dy), text, font=font,
                                  fill=stroke_color, emoji_position_offset=(0, 0))
    pilmoji_draw.text((x, y), text, font=font, fill=text_color,
                      emoji_position_offset=(0, 0))

# =========================================================
# TIME SETTINGS MODAL
# =========================================================


class GrowthTimeModal(discord.ui.Modal, title='Custom Time Period'):
    def __init__(self, view):
        super().__init__(timeout=300)
        self.view = view

    days = discord.ui.TextInput(
        label='Enter number of days',
        placeholder='e.g., 7, 14, 30, 90, 365, 2000...',
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
            self.view.current_days = days
            self.view.show_time_buttons = False
            await self.view.update_chart(interaction)

        except ValueError:
            traceback.print_exc()
            await interaction.response.send_message("❌ Please enter a valid number.", ephemeral=True)
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send("❌ An error occurred while generating chart preview.", ephemeral=True)

# =========================================================
# GROWTH DROPDOWN MENU
# =========================================================


class GrowthSelectMenu(discord.ui.Select):
    def __init__(self, current_selection: str, growth_type: str = "member"):
        if growth_type == "member":
            options = [
                discord.SelectOption(
                    label="Member Count",
                    value="member_count",
                    description="Track server member count over time",
                    emoji="👥",
                    default=(current_selection == "member_count")
                ),
                discord.SelectOption(
                    label="Joins and Leaves",
                    value="joins_leaves",
                    description="Track server joins and leaves",
                    emoji="📈",
                    default=(current_selection == "joins_leaves")
                ),
                discord.SelectOption(
                    label="Forecast & Analytics",
                    value="forecast",
                    description="Advanced forecasting with trend analysis",
                    emoji="🔮",
                    default=(current_selection == "forecast")
                )
            ]
            placeholder = "Select view type..."
        else:
            options = []
            placeholder = None

        super().__init__(
            placeholder=placeholder,
            options=options,
            custom_id="growth_type_select",
            min_values=1,
            max_values=1,
            row=0,
            disabled=(growth_type != "member")
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            view = self.view
            view.growth_type = self.values[0]
            view.current_selection = self.values[0]
            await interaction.response.defer()
            await view.update_chart(interaction)
        except Exception as e:
            traceback.print_exc()
            await interaction.response.send_message("❌ An error occurred while updating view type.", ephemeral=True)

# =========================================================
# GROWTH VIEW
# =========================================================


class GrowthView(discord.ui.View):
    def __init__(self, cog, guild_id: int, days: int = 14, growth_type: str = "member_count",
                 chart_type: str = "member", role_id: Optional[int] = None):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild_id = guild_id
        self.guild = cog.bot.get_guild(guild_id)
        self.current_days = days
        self.growth_type = growth_type
        self.current_selection = growth_type
        self.chart_type = chart_type
        self.role_id = role_id
        self.show_time_buttons = False
        self.message_id = None
        self.forecast_data = None

        self._update_buttons()

    def get_time_label(self, days: int = None) -> str:
        if days is None:
            days = self.current_days
        if self.chart_type == "member":
            if self.growth_type == "member_count":
                return f"Last {days} Days"
            elif self.growth_type == "joins_leaves":
                return f"Last {days} Days"
            else:
                return f"Next {days} Days"
        else:
            return f"Last {days} Days"

    def _update_buttons(self):
        self.clear_items()

        if self.chart_type == "member":
            growth_select = GrowthSelectMenu(self.current_selection, "member")
            growth_select.row = 0
            self.add_item(growth_select)

        refresh_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="🔄 Refresh",
            custom_id="growth_refresh",
            row=1
        )
        refresh_button.callback = self.refresh_callback
        self.add_item(refresh_button)

        time_settings_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="⏰ Time Settings",
            custom_id="growth_time_settings",
            row=1
        )
        time_settings_button.callback = self.time_settings_callback
        self.add_item(time_settings_button)

        if self.show_time_buttons:
            days_7_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days == 7 else discord.ButtonStyle.secondary,
                label="7 Days",
                custom_id="growth_days_7",
                row=2
            )
            days_7_button.callback = self.days_7_callback
            self.add_item(days_7_button)

            days_14_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days == 14 else discord.ButtonStyle.secondary,
                label="14 Days",
                custom_id="growth_days_14",
                row=2
            )
            days_14_button.callback = self.days_14_callback
            self.add_item(days_14_button)

            days_30_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days == 30 else discord.ButtonStyle.secondary,
                label="30 Days",
                custom_id="growth_days_30",
                row=2
            )
            days_30_button.callback = self.days_30_callback
            self.add_item(days_30_button)

            custom_button = discord.ui.Button(
                style=discord.ButtonStyle.success,
                label="Custom",
                custom_id="growth_custom_days",
                row=2
            )
            custom_button.callback = self.custom_days_callback
            self.add_item(custom_button)

    async def refresh_callback(self, interaction: discord.Interaction):
        await self.handle_button_click(interaction, refresh=True)

    async def time_settings_callback(self, interaction: discord.Interaction):
        await self.handle_time_settings(interaction)

    async def days_7_callback(self, interaction: discord.Interaction):
        await self.handle_button_click(interaction, days=7)

    async def days_14_callback(self, interaction: discord.Interaction):
        await self.handle_button_click(interaction, days=14)

    async def days_30_callback(self, interaction: discord.Interaction):
        await self.handle_button_click(interaction, days=30)

    async def custom_days_callback(self, interaction: discord.Interaction):
        if not self.guild:
            await interaction.response.send_message("❌ Could not find guild information.", ephemeral=True)
            return

        modal = GrowthTimeModal(self)
        await interaction.response.send_modal(modal)

    async def handle_button_click(self, interaction: discord.Interaction, refresh: bool = False, days: int = None):
        try:
            await interaction.response.defer()

            if days:
                self.current_days = days
                self.show_time_buttons = False

            await self.update_chart(interaction)

        except Exception as e:
            traceback.print_exc()
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
            traceback.print_exc()
            try:
                await interaction.response.send_message("❌ An error occurred while updating time settings.", ephemeral=True)
            except:
                pass

    async def update_chart(self, interaction: discord.Interaction):
        try:
            if self.chart_type == "member":
                if self.growth_type == "member_count":
                    data = await self.cog.fetch_member_count_history(self.guild_id, self.current_days)
                else:
                    data = await self.cog.fetch_historical_growth(self.guild_id, self.current_days)

                if not data or (self.growth_type == "member_count" and not data.get('counts')):
                    await self._safe_edit_response(interaction, content="❌ No member count data available", view=self)
                    return
                if self.growth_type in ("joins_leaves", "forecast") and (not data.get('joins') or not data.get('leaves')):
                    await self._safe_edit_response(interaction, content="❌ No growth data available", view=self)
                    return
            else:
                data = await self.cog.fetch_role_historical_growth(self.guild_id, self.role_id, self.current_days)
                if not data or (not data.get('joins') and not data.get('leaves')):
                    await self._safe_edit_response(interaction, content="❌ No growth data available for this role", view=self)
                    return

            if self.growth_type == "forecast" and self.chart_type == "member":
                forecast = await self.generate_forecast(data)
                self.forecast_data = forecast
                chart_img, timestamps, y_labels = self.cog.generate_forecast_chart(
                    forecast, self.current_days
                )
                total_joins_pred = sum(forecast.get('joins_forecast', []))
                total_leaves_pred = sum(forecast.get('leaves_forecast', []))
                label = f"Predicted Joins: {int(total_joins_pred)} | Predicted Leaves: {int(total_leaves_pred)}"
            elif self.growth_type == "member_count" and self.chart_type == "member":
                chart_img, timestamps, y_labels = self.cog.generate_member_count_chart(
                    data, self.current_days
                )
                counts = data.get('counts', [])
                current_count = str(counts[-1]['count']) if counts else "0"
                label = current_count
            else:
                chart_img, timestamps, y_labels = self.cog.generate_growth_chart(
                    data, self.current_days, self.growth_type, self.chart_type
                )
                if self.chart_type == "member":
                    label = self.create_member_label(data, self.current_days)
                else:
                    label = self.create_role_label(data, self.current_days)

            final_image_bytes = await self.cog.draw_growth_on_template(
                chart_img, label, self.current_days,
                timestamps, y_labels, self.current_selection,
                self.growth_type, self.guild_id, self.chart_type,
                self.role_id, self.forecast_data if self.growth_type == "forecast" else None
            )

            file = discord.File(final_image_bytes, filename='growth_chart.png')
            self._update_buttons()
            await self._safe_edit_response(interaction, content=None, attachments=[file], view=self)

        except Exception as e:
            traceback.print_exc()
            try:
                await self._safe_edit_response(interaction, content="❌ Error generating growth chart", view=self)
            except:
                pass

    async def _safe_edit_response(self, interaction: discord.Interaction, **kwargs):
        try:
            await interaction.edit_original_response(**kwargs)
        except discord.NotFound:
            try:
                await interaction.followup.send(**kwargs, ephemeral=True)
            except:
                pass
        except:
            pass

    def create_member_label(self, data: Dict, days: int) -> str:
        total_joins = data.get('total_joins', 0)
        total_leaves = data.get('total_leaves', 0)
        return f"Joins: {total_joins} | Leaves: {total_leaves}"

    def create_role_label(self, data: Dict, days: int) -> str:
        total_added = data.get('total_joins', 0)
        total_removed = data.get('total_leaves', 0)
        return f"Added: {total_added} | Removed: {total_removed}"

    async def fetch_member_growth_data(self) -> Dict:
        if self.growth_type in ("joins_leaves", "forecast"):
            return await self.cog.fetch_historical_growth(self.guild_id, self.current_days)
        return self.cog._get_empty_growth_data()

    async def generate_forecast(self, historical_data: Dict) -> Dict:
        joins_data = historical_data.get('joins', [])
        leaves_data = historical_data.get('leaves', [])

        if not joins_data and not leaves_data:
            return {
                'joins_forecast': [],
                'leaves_forecast': [],
                'joins_smoothed': [],
                'leaves_smoothed': [],
                'volatility': 0,
                'trend_direction': 'stable'
            }

        forecaster_joins = GrowthForecaster(joins_data) if joins_data else None
        forecaster_leaves = GrowthForecaster(
            leaves_data) if leaves_data else None

        joins_forecast = forecaster_joins.forecast(
            days_ahead=self.current_days) if forecaster_joins else {'future_predictions': []}
        leaves_forecast = forecaster_leaves.forecast(
            days_ahead=self.current_days) if forecaster_leaves else {'future_predictions': []}

        return {
            'joins_forecast': joins_forecast.get('future_predictions', []),
            'leaves_forecast': leaves_forecast.get('future_predictions', []),
            'joins_smoothed': joins_forecast.get('smoothed_data', []),
            'leaves_smoothed': leaves_forecast.get('smoothed_data', []),
            'volatility': max(joins_forecast.get('volatility', 0), leaves_forecast.get('volatility', 0)),
            'trend_direction': joins_forecast.get('trend_direction', 'stable')
        }

    async def fetch_role_growth_data(self) -> Dict:
        if not self.role_id:
            return self.cog._get_empty_growth_data()
        return await self.cog.fetch_role_historical_growth(self.guild_id, self.role_id, self.current_days)

# =========================================================
# MAIN COG
# =========================================================


class GrowthSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.pool = None
        self.tables_created = False
        self.snapshot_cron = None
        self.db_initialized = False
        self.rate_limiter = get_rate_limiter()

    def _get_fernet(self):
        """Get fernet instance from DatabaseStats cog."""
        db_stats = self.bot.get_cog('DatabaseStats')
        if db_stats and hasattr(db_stats, 'fernet'):
            return db_stats.fernet
        return None

    async def cog_load(self):
        """Called when cog is loaded - initialize and start cron."""

        # Start DB initialization in background (don't await it)
        asyncio.create_task(self.initialize_db_connection())

        # Start cron job immediately (it will check if DB is ready)
        self.snapshot_cron = aiocron.crontab(
            '0 * * * *', func=self.snapshot_member_counts)
        print("✅ Cron job created")

    async def cog_unload(self):
        """Clean up on unload."""
        print("🛑 GrowthSystem.cog_unload - stopping cron")
        if self.snapshot_cron:
            self.snapshot_cron.stop()

    async def initialize_db_connection(self):
        """Wait for DatabaseStats cog to be ready and get the pool."""

        # Wait a bit for the bot to start
        await asyncio.sleep(5)

        db_cog = self.bot.get_cog("DatabaseStats")
        if not db_cog:
            print("❌ DatabaseStats cog not found!")
            return

        attempts = 0
        max_attempts = 30
        while not db_cog.db_connected or not db_cog.pool:
            if attempts >= max_attempts:
                print("❌ Timed out waiting for database connection")
                return
            await asyncio.sleep(1)
            attempts += 1
            if attempts % 5 == 0:
                print(f"⏳ Waiting for database connection... ({attempts}s)")

        self.pool = db_cog.pool
        self.db_initialized = True

        await self.ensure_tables_exist()
        print("✅ Growth Tables verified/created")

    async def ensure_tables_exist(self):
        """Ensure all required tables exist with encrypted_username columns."""

        if not self.pool:
            print("❌ No database pool")
            return

        try:
            async with self.pool.acquire() as conn:
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS server_member_counts (
                        guild_id BIGINT NOT NULL,
                        recorded_at TIMESTAMPTZ NOT NULL,
                        member_count INT NOT NULL,
                        encrypted_username TEXT,
                        PRIMARY KEY (guild_id, recorded_at)
                    )
                ''')
                print("✅ server_member_counts table ready")

                # Add encrypted_username column if missing
                await conn.execute('''
                    ALTER TABLE server_member_counts 
                    ADD COLUMN IF NOT EXISTS encrypted_username TEXT
                ''')

                self.tables_created = True
        except Exception as e:
            print(f"❌ Error creating table: {e}")

    async def snapshot_member_counts(self):
        """Take snapshot every hour with bot filtering from settings cog."""
        print(
            f"🔍 SNAPSHOT TRIGGERED at {datetime.now(timezone.utc).strftime('%H:%M:%S')}")

        if not self.db_initialized or not self.pool or not self.tables_created:
            print(
                f"   SKIPPED - db_initialized: {self.db_initialized}, pool: {self.pool is not None}, tables: {self.tables_created}")
            return

        now = datetime.now(timezone.utc)
        records = []
        settings_cog = self.bot.get_cog("Settings")
        fernet = self._get_fernet()

        for guild in self.bot.guilds:
            # Rate limit BEFORE each guild (to prevent Discord API spam)
            if not await self.rate_limiter.acquire(RateLimitType.API, timeout=30.0):
                print(f"  ⚠️ Rate limited for guild {guild.name}, waiting...")
                await asyncio.sleep(5)
                continue

            # Get bot filter setting from settings cog
            bot_filter = False
            if settings_cog:
                try:
                    settings = await settings_cog.get_guild_settings(guild.id)
                    bot_filter = settings.get('bot_filter', False)
                except Exception as e:
                    print(
                        f"⚠️ Could not get settings for guild {guild.id}: {e}")

            if bot_filter:
                # Count only non-bot members (this iterates through guild.members which is cached, no API call)
                count = sum(1 for member in guild.members if not member.bot)
            else:
                # Count all members (using cached guild.member_count)
                count = guild.member_count or len(guild.members)

            # Get encrypted username for the guild owner (or first member for privacy)
            encrypted_username = None
            if fernet and guild.owner:
                encrypted_username = self._encrypt_username(
                    fernet, str(guild.owner))
            elif fernet and guild.members:
                for member in guild.members:
                    if not member.bot:
                        encrypted_username = self._encrypt_username(
                            fernet, str(member))
                        break

            records.append((guild.id, now, count, encrypted_username))

            # Small delay between guilds to be gentle
            await asyncio.sleep(0.1)

        if not records:
            return

        try:
            async with self.pool.acquire() as conn:
                await conn.executemany("""
                    INSERT INTO server_member_counts (guild_id, recorded_at, member_count, encrypted_username)
                    VALUES ($1, $2, $3, $4)
                """, records)
            print(
                f"   ✅ SNAPSHOT COMPLETE at {datetime.now(timezone.utc).strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"   ❌ Error recording snapshot: {e}")

    def _encrypt_username(self, fernet, username: str) -> Optional[str]:
        """Encrypt username for privacy."""
        if not username or not fernet:
            return None
        try:
            return fernet.encrypt(username.encode()).decode()
        except Exception:
            return None

    def _decrypt_username(self, fernet, encrypted: Optional[str]) -> Optional[str]:
        """Decrypt username if possible."""
        if not encrypted or not fernet:
            return encrypted
        try:
            return fernet.decrypt(encrypted.encode()).decode()
        except Exception:
            return None

    # =========================================================
    # PERMISSION CHECK METHODS
    # =========================================================

    async def get_settings_cog(self):
        try:
            return self.bot.get_cog("Settings")
        except Exception as e:
            traceback.print_exc()
            print(f"❌ Error in get_settings_cog: {e}")
            return None

    async def check_growth_permission(self, interaction: discord.Interaction) -> Tuple[bool, Optional[str]]:
        try:
            settings_cog = await self.get_settings_cog()
            if not settings_cog:
                return True, None

            settings = await settings_cog.get_guild_settings(interaction.guild_id)
            permission_level = settings.get('permission_level', 'Default')

            if permission_level in ['All', 'User Restriction', 'Default']:
                return True, None
            elif permission_level == 'Moderator':
                if interaction.user.guild_permissions.manage_guild or interaction.user.guild_permissions.administrator:
                    return True, None
                return False, "Manage Server or Administrator"
            elif permission_level == 'Admin':
                if interaction.user.guild_permissions.administrator:
                    return True, None
                return False, "Administrator"

            return True, None

        except Exception as e:
            traceback.print_exc()
            print(f"❌ Error in check_growth_permission: {e}")
            return True, None

    async def check_growth_permission_ctx(self, ctx: commands.Context) -> Tuple[bool, Optional[str]]:
        try:
            settings_cog = await self.get_settings_cog()
            if not settings_cog:
                return True, None

            settings = await settings_cog.get_guild_settings(ctx.guild.id)
            permission_level = settings.get('permission_level', 'Default')

            if permission_level in ['All', 'User Restriction', 'Default']:
                return True, None
            elif permission_level == 'Moderator':
                if ctx.author.guild_permissions.manage_guild or ctx.author.guild_permissions.administrator:
                    return True, None
                return False, "Manage Server or Administrator"
            elif permission_level == 'Admin':
                if ctx.author.guild_permissions.administrator:
                    return True, None
                return False, "Administrator"

            return True, None

        except Exception as e:
            traceback.print_exc()
            print(f"❌ Error in check_growth_permission_ctx: {e}")
            return True, None

    # =========================================================
    # BOT FILTER HELPER METHOD
    # =========================================================

    async def _apply_bot_filter(self, query: str, params: List, guild_id: int, table_name: str = None) -> Tuple[str, List]:
        try:
            if not table_name or not self.bot:
                return query, params

            settings_cog = self.bot.get_cog("Settings")
            if not settings_cog:
                return query, params

            try:
                settings = await settings_cog.get_guild_settings(guild_id)
                bot_filter = settings.get('bot_filter', False)

                if not bot_filter:
                    return query, params

                tables_with_bot_column = [
                    'member_joins_hourly', 'member_leaves_hourly', 'member_growth_stats', 'role_growth_hourly']

                if table_name in tables_with_bot_column:
                    condition = "is_bot = FALSE"
                    query_upper = query.upper()

                    where_pos = query_upper.find("WHERE")
                    if where_pos != -1:
                        insert_position = where_pos + 5
                        query = query[:insert_position] + " " + \
                            condition + " AND" + query[insert_position:]
                    else:
                        group_by_pos = query_upper.find("GROUP BY")
                        if group_by_pos != -1:
                            insert_position = group_by_pos
                        else:
                            order_by_pos = query_upper.find("ORDER BY")
                            if order_by_pos != -1:
                                insert_position = order_by_pos
                            else:
                                insert_position = len(query)

                        query = query[:insert_position].rstrip(
                        ) + " WHERE " + condition + " " + query[insert_position:].lstrip()

            except Exception as e:
                traceback.print_exc()
                print(
                    f"⚠️ Error applying bot filter for guild {guild_id}: {e}")

        except Exception as e:
            traceback.print_exc()
            print(f"❌ Error in _apply_bot_filter: {e}")

        return query, params

    # =========================================================
    # ROLE MEMBERSHIP HELPER METHODS
    # =========================================================

    async def _get_users_with_roles(self, guild_id: int, role_ids: Optional[List[int]] = None) -> Optional[List[int]]:
        """Get all user IDs that have at least one of the specified roles."""
        if not role_ids:
            return None

        try:
            async with self.pool.acquire() as conn:
                placeholders = [f"${i+2}" for i in range(len(role_ids))]
                query = f"""
                    SELECT DISTINCT user_id
                    FROM current_role_members
                    WHERE guild_id = $1
                    AND role_id IN ({', '.join(placeholders)})
                """
                params = [guild_id] + role_ids
                rows = await conn.fetch(query, *params)
                return [row['user_id'] for row in rows]
        except Exception as e:
            print(f"Error getting users with roles for guild {guild_id}: {e}")
            return []

    async def _get_all_role_members(self, guild_id: int) -> Dict[int, List[int]]:
        """Get all role memberships for a guild at once."""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch('''
                    SELECT role_id, user_id
                    FROM current_role_members
                    WHERE guild_id = $1
                ''', guild_id)
                role_members = {}
                for row in rows:
                    role_id = row['role_id']
                    user_id = row['user_id']
                    if role_id not in role_members:
                        role_members[role_id] = []
                    role_members[role_id].append(user_id)
                return role_members
        except Exception as e:
            print(f"Error fetching all role members for guild {guild_id}: {e}")
            return {}

    # =========================================================
    # DATA FETCHING METHODS
    # =========================================================

    async def fetch_member_count_history(self, guild_id: int, days: int) -> Dict:
        if not self.pool:
            return {'counts': []}

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT recorded_at, member_count
                    FROM server_member_counts
                    WHERE guild_id = $1 AND recorded_at >= $2
                    ORDER BY recorded_at
                """, guild_id, start)

                # If no historical data exists, take a current snapshot with bot filtering
                if not rows:
                    guild = self.bot.get_guild(guild_id)
                    if guild and guild.member_count:
                        # Apply bot filter for current snapshot
                        settings_cog = self.bot.get_cog("Settings")
                        bot_filter = False
                        if settings_cog:
                            try:
                                settings = await settings_cog.get_guild_settings(guild_id)
                                bot_filter = settings.get('bot_filter', False)
                            except:
                                pass

                        if bot_filter:
                            current_count = sum(
                                1 for member in guild.members if not member.bot)
                        else:
                            current_count = guild.member_count or len(
                                guild.members)

                        rows = [{'recorded_at': datetime.now(
                            timezone.utc), 'member_count': current_count}]

                counts = [{'date': r['recorded_at'],
                           'count': r['member_count']} for r in rows]
                max_count = max([r['member_count'] for r in rows], default=0)

                return {
                    'counts': counts,
                    'max_count': max_count
                }
        except asyncpg.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch member count history",
                context={'guild_id': guild_id, 'days': days},
                original=e
            )
        except Exception as e:
            raise DatabaseConnectionError(
                "Database error while fetching member counts",
                context={'guild_id': guild_id},
                original=e
            )

    async def fetch_historical_growth(self, guild_id: int, days: int = 14) -> Dict:
        """Fetch historical member growth data using hourly aggregated tables."""
        current_utc = datetime.now(timezone.utc)

        try:
            if not self.pool:
                return self._get_empty_growth_data()

            async with self.pool.acquire() as conn:
                start_date = current_utc.date() - timedelta(days=days - 1)

                joins_points = []
                leaves_points = []

                for day_offset in range(days):
                    current_date = start_date + timedelta(days=day_offset)
                    day_start = datetime.combine(
                        current_date, datetime.min.time()).replace(tzinfo=timezone.utc)
                    day_end = datetime.combine(
                        current_date, datetime.max.time()).replace(tzinfo=timezone.utc)

                    joins_query = """
                        SELECT COALESCE(SUM(join_count), 0) 
                        FROM member_joins_hourly 
                        WHERE guild_id = $1 
                        AND hour >= $2
                        AND hour <= $3
                    """
                    joins_params = [guild_id, day_start, day_end]
                    joins_query, joins_params = await self._apply_bot_filter(
                        joins_query, joins_params, guild_id, 'member_joins_hourly'
                    )
                    daily_joins = await conn.fetchval(joins_query, *joins_params) or 0

                    leaves_query = """
                        SELECT COALESCE(SUM(leave_count), 0) 
                        FROM member_leaves_hourly 
                        WHERE guild_id = $1 
                        AND hour >= $2
                        AND hour <= $3
                    """
                    leaves_params = [guild_id, day_start, day_end]
                    leaves_query, leaves_params = await self._apply_bot_filter(
                        leaves_query, leaves_params, guild_id, 'member_leaves_hourly'
                    )
                    daily_leaves = await conn.fetchval(leaves_query, *leaves_params) or 0

                    joins_points.append(
                        {'date': current_date, 'count': daily_joins})
                    leaves_points.append(
                        {'date': current_date, 'count': daily_leaves})

                total_joins = sum(p['count'] for p in joins_points)
                total_leaves = sum(p['count'] for p in leaves_points)

                max_daily_joins = max([p['count']
                                      for p in joins_points], default=0)
                max_daily_leaves = max([p['count']
                                       for p in leaves_points], default=0)
                max_daily_value = max(max_daily_joins, max_daily_leaves, 1)

                return {
                    'joins': joins_points,
                    'leaves': leaves_points,
                    'total_joins': total_joins,
                    'total_leaves': total_leaves,
                    'max_daily_value': max_daily_value,
                    'max_total_value': max(total_joins, total_leaves, 1)
                }

        except asyncpg.PostgresError as e:
            raise DatabaseQueryError(
                "Database error in fetch_historical_growth",
                context={'guild_id': guild_id, 'days': days},
                original=e
            )
        except Exception as e:
            raise DatabaseConnectionError(
                "Unexpected error in fetch_historical_growth",
                context={'guild_id': guild_id},
                original=e
            )

    async def fetch_role_historical_growth(self, guild_id: int, role_id: int, days: int = 14) -> Dict:
        """Fetch historical role growth data using role_growth_hourly table."""
        current_utc = datetime.now(timezone.utc)

        try:
            if not self.pool:
                return self._get_empty_growth_data()

            async with self.pool.acquire() as conn:
                start_date = current_utc.date() - timedelta(days=days - 1)

                added_points = []
                removed_points = []

                for day_offset in range(days):
                    current_date = start_date + timedelta(days=day_offset)
                    day_start = datetime.combine(
                        current_date, datetime.min.time()).replace(tzinfo=timezone.utc)
                    day_end = datetime.combine(
                        current_date, datetime.max.time()).replace(tzinfo=timezone.utc)

                    added_query = """
                        SELECT COALESCE(SUM(added_count), 0) 
                        FROM role_growth_hourly 
                        WHERE guild_id = $1 
                        AND role_id = $2
                        AND hour >= $3
                        AND hour <= $4
                    """
                    added_params = [guild_id, role_id, day_start, day_end]
                    added_query, added_params = await self._apply_bot_filter(
                        added_query, added_params, guild_id, 'role_growth_hourly'
                    )
                    daily_added = await conn.fetchval(added_query, *added_params) or 0

                    removed_query = """
                        SELECT COALESCE(SUM(removed_count), 0) 
                        FROM role_growth_hourly 
                        WHERE guild_id = $1 
                        AND role_id = $2
                        AND hour >= $3
                        AND hour <= $4
                    """
                    removed_params = [guild_id, role_id, day_start, day_end]
                    removed_query, removed_params = await self._apply_bot_filter(
                        removed_query, removed_params, guild_id, 'role_growth_hourly'
                    )
                    daily_removed = await conn.fetchval(removed_query, *removed_params) or 0

                    added_points.append(
                        {'date': current_date, 'count': daily_added})
                    removed_points.append(
                        {'date': current_date, 'count': daily_removed})

                total_added = sum(p['count'] for p in added_points)
                total_removed = sum(p['count'] for p in removed_points)

                max_daily_added = max([p['count']
                                      for p in added_points], default=0)
                max_daily_removed = max([p['count']
                                        for p in removed_points], default=0)
                max_daily_value = max(max_daily_added, max_daily_removed, 1)

                return {
                    'joins': added_points,
                    'leaves': removed_points,
                    'total_joins': total_added,
                    'total_leaves': total_removed,
                    'max_daily_value': max_daily_value,
                    'max_total_value': max(total_added, total_removed, 1),
                    'role_growth': True
                }

        except asyncpg.PostgresError as e:
            raise DatabaseQueryError(
                "Database error in fetch_role_historical_growth",
                context={'guild_id': guild_id,
                         'role_id': role_id, 'days': days},
                original=e
            )
        except Exception as e:
            raise DatabaseConnectionError(
                "Unexpected error in fetch_role_historical_growth",
                context={'guild_id': guild_id, 'role_id': role_id},
                original=e
            )

    def _get_empty_growth_data(self):
        return {
            'joins': [],
            'leaves': [],
            'total_joins': 0,
            'total_leaves': 0,
            'max_daily_value': 1,
            'max_total_value': 1
        }

    # =========================================================
    # CHART GENERATION METHODS
    # =========================================================

    def generate_member_count_chart(self, data: Dict, days: int) -> Tuple[Image.Image, List[str], List[Tuple[float, str]]]:
        """Generate chart for member count over time with actual data points."""
        try:
            plt.style.use('dark_background')
            fig, ax = plt.subplots(
                figsize=(6, 2.5), dpi=300, facecolor=(0, 0, 0, 0))
            ax.set_axis_off()

            counts = data.get('counts', [])
            if not counts:
                timestamps = [f"Day {i+1}" for i in range(8)]
                img = Image.new('RGBA', (644, 250), (0, 0, 0, 0))
                y_labels = [(0, "0")]
                return img, timestamps, y_labels

            counts.sort(key=lambda x: x['date'])
            dates = [row['date'] for row in counts]
            values = [float(row['count']) for row in counts]
            dates_numeric = mdates.date2num(dates)

            max_val = max(values)
            if max_val <= 10:
                if max_val <= 5:
                    y_max = max(5, max_val * 1.2)
                else:
                    y_max = max_val * 1.5
            else:
                y_max = max_val * 1.1
            y_max = max(y_max, 5)

            ax.set_ylim(0, y_max)

            if len(dates_numeric) > 1:
                x_smooth = np.linspace(
                    min(dates_numeric), max(dates_numeric), 500)
                y_smooth = np.interp(x_smooth, dates_numeric, values)
                from scipy.ndimage import gaussian_filter1d
                y_smooth = gaussian_filter1d(y_smooth, sigma=2)
                ax.plot(x_smooth, y_smooth, linewidth=4, color='#00aaff',
                        solid_capstyle='round', antialiased=True)
            else:
                ax.plot(dates_numeric, values, 'o',
                        markersize=4, color='#00aaff')

            timestamps = self.generate_growth_timestamps(counts, False)

            y_labels = [
                (y_max, self.format_number(y_max)),
                (y_max * 0.75, self.format_number(y_max * 0.75)),
                (y_max * 0.5, self.format_number(y_max * 0.5)),
                (y_max * 0.25, self.format_number(y_max * 0.25)),
                (0, "0")
            ]

            buf = io.BytesIO()
            plt.savefig(buf, format='png', transparent=True,
                        bbox_inches='tight', pad_inches=0, dpi=300)
            buf.seek(0)
            chart_img = Image.open(buf)
            plt.close(fig)

            return chart_img, timestamps, y_labels

        except Exception as e:
            traceback.print_exc()
            print(f"❌ Error in generate_member_count_chart: {e}")
            img = Image.new('RGBA', (644, 250), (0, 0, 0, 0))
            return img, [f"Day {i+1}" for i in range(8)], [(0, "0")]

    def generate_growth_chart(self, data: Dict, days: int, growth_type: str, chart_type: str = "member") -> Tuple[Image.Image, List[str], List[Tuple[float, str]]]:
        """Generate chart for joins/leaves (historical only)."""
        try:
            plt.style.use('dark_background')
            fig, ax = plt.subplots(
                figsize=(6, 2.5), dpi=300, facecolor=(0, 0, 0, 0))
            ax.set_axis_off()

            joins_data = data.get('joins', [])
            leaves_data = data.get('leaves', [])
            max_daily_value = data.get('max_daily_value', 1)

            if max_daily_value <= 10:
                if max_daily_value <= 5:
                    y_max = max(5, max_daily_value * 1.2)
                else:
                    y_max = max_daily_value * 1.5
            else:
                y_max = max_daily_value * 1.1
            y_max = max(y_max, 5)

            ax.set_ylim(0, y_max)

            all_points = joins_data + leaves_data
            if all_points:
                timestamps = self.generate_growth_timestamps(all_points, False)

                if joins_data:
                    joins_data.sort(key=lambda x: x['date'])
                    join_dates = [row['date'] for row in joins_data]
                    join_values = [float(row['count']) for row in joins_data]
                    join_dates_numeric = mdates.date2num(join_dates)

                    if len(join_dates_numeric) > 1:
                        x_smooth = np.linspace(
                            min(join_dates_numeric), max(join_dates_numeric), 500)
                        y_smooth = np.interp(
                            x_smooth, join_dates_numeric, join_values)
                        from scipy.ndimage import gaussian_filter1d
                        y_smooth = gaussian_filter1d(y_smooth, sigma=2)
                        ax.plot(x_smooth, y_smooth, linewidth=4, color='#21ef00',
                                solid_capstyle='round', antialiased=True)
                    else:
                        ax.plot(join_dates_numeric, join_values,
                                'o', markersize=4, color='#21ef00')

                if leaves_data:
                    leaves_data.sort(key=lambda x: x['date'])
                    leave_dates = [row['date'] for row in leaves_data]
                    leave_values = [float(row['count']) for row in leaves_data]
                    leave_dates_numeric = mdates.date2num(leave_dates)

                    if len(leave_dates_numeric) > 1:
                        x_smooth = np.linspace(
                            min(leave_dates_numeric), max(leave_dates_numeric), 500)
                        y_smooth = np.interp(
                            x_smooth, leave_dates_numeric, leave_values)
                        from scipy.ndimage import gaussian_filter1d
                        y_smooth = gaussian_filter1d(y_smooth, sigma=2)
                        ax.plot(x_smooth, y_smooth, linewidth=4, color='#ef0000',
                                solid_capstyle='round', antialiased=True)
                    else:
                        ax.plot(leave_dates_numeric, leave_values,
                                'o', markersize=4, color='#ef0000')
            else:
                timestamps = [f"Day {i+1}" for i in range(8)]
                x_smooth = np.linspace(1, 8, 100)
                y_joins = np.ones_like(x_smooth) * (y_max * 0.5)
                y_leaves = np.ones_like(x_smooth) * (y_max * 0.25)
                ax.plot(x_smooth, y_joins, linewidth=4,
                        color='#21ef00', alpha=0.5)
                ax.plot(x_smooth, y_leaves, linewidth=4,
                        color='#ef0000', alpha=0.5)

            y_labels = [
                (y_max, self.format_number(y_max)),
                (y_max * 0.75, self.format_number(y_max * 0.75)),
                (y_max * 0.5, self.format_number(y_max * 0.5)),
                (y_max * 0.25, self.format_number(y_max * 0.25)),
                (0, "0")
            ]

            buf = io.BytesIO()
            plt.savefig(buf, format='png', transparent=True,
                        bbox_inches='tight', pad_inches=0, dpi=300)
            buf.seek(0)
            chart_img = Image.open(buf)
            plt.close(fig)

            return chart_img, timestamps, y_labels

        except Exception as e:
            traceback.print_exc()
            print(f"❌ Error in generate_growth_chart: {e}")
            img = Image.new('RGBA', (644, 250), (0, 0, 0, 0))
            return img, [f"Day {i+1}" for i in range(8)], [(0, "0")]

    def generate_forecast_chart(self, forecast: Dict, days: int) -> Tuple[Image.Image, List[str], List[Tuple[float, str]]]:
        """Generate chart with only forecasted joins and leaves."""
        try:
            plt.style.use('dark_background')
            fig, ax = plt.subplots(
                figsize=(6, 2.5), dpi=300, facecolor=(0, 0, 0, 0))
            ax.set_axis_off()

            joins_forecast = forecast.get('joins_forecast', [])
            leaves_forecast = forecast.get('leaves_forecast', [])

            if not joins_forecast and not leaves_forecast:
                timestamps = [f"Day {i+1}" for i in range(min(days, 8))]
                img = Image.new('RGBA', (644, 250), (0, 0, 0, 0))
                y_labels = [(0, "0")]
                return img, timestamps, y_labels

            forecast_max = max(
                max(joins_forecast) if joins_forecast else 0,
                max(leaves_forecast) if leaves_forecast else 0,
                1
            )
            if forecast_max <= 10:
                if forecast_max <= 5:
                    y_max = max(5, forecast_max * 1.2)
                else:
                    y_max = forecast_max * 1.5
            else:
                y_max = forecast_max * 1.1
            y_max = max(y_max, 5)

            ax.set_ylim(0, y_max)

            x = list(range(1, days + 1))

            if joins_forecast:
                jf = joins_forecast[:days]
                if len(jf) < days:
                    jf += [0] * (days - len(jf))
                ax.plot(x, jf, linewidth=4, color='#21ef00',
                        solid_capstyle='round', antialiased=True)

            if leaves_forecast:
                lf = leaves_forecast[:days]
                if len(lf) < days:
                    lf += [0] * (days - len(lf))
                ax.plot(x, lf, linewidth=4, color='#ef0000',
                        solid_capstyle='round', antialiased=True)

            if days <= 8:
                label_indices = list(range(1, days + 1))
            else:
                step = (days - 1) / 7
                label_indices = [int(1 + i * step) for i in range(8)]
            timestamps = [f"Day {i}" for i in label_indices]

            y_labels = [
                (y_max, self.format_number(y_max)),
                (y_max * 0.75, self.format_number(y_max * 0.75)),
                (y_max * 0.5, self.format_number(y_max * 0.5)),
                (y_max * 0.25, self.format_number(y_max * 0.25)),
                (0, "0")
            ]

            buf = io.BytesIO()
            plt.savefig(buf, format='png', transparent=True,
                        bbox_inches='tight', pad_inches=0, dpi=300)
            buf.seek(0)
            chart_img = Image.open(buf)
            plt.close(fig)

            return chart_img, timestamps, y_labels

        except Exception as e:
            traceback.print_exc()
            print(f"❌ Error in generate_forecast_chart: {e}")
            img = Image.new('RGBA', (644, 250), (0, 0, 0, 0))
            return img, [f"Day {i+1}" for i in range(8)], [(0, "0")]

    def format_number(self, num: float) -> str:
        if num >= 1000:
            return f"{num/1000:.1f}k"
        return str(int(num))

    def generate_growth_timestamps(self, data_points: List[Dict], is_projection: bool = False) -> List[str]:
        try:
            if not data_points or len(data_points) < 2:
                return [f"Day {i+1}" for i in range(8)]

            dates = [row['date'] for row in data_points if 'date' in row]
            if not dates:
                return [f"Day {i+1}" for i in range(8)]

            start_time = min(dates)
            end_time = max(dates)
            delta = end_time - start_time
            total_days = delta.days + (delta.seconds / 86400)

            if total_days <= 2:
                if isinstance(start_time, date) and not isinstance(start_time, datetime):
                    start_time = datetime.combine(
                        start_time, datetime.min.time())
                    end_time = datetime.combine(end_time, datetime.min.time())

                timestamps = []
                if total_days <= 1:
                    hours = [0, 3, 6, 9, 12, 15, 18, 21]
                    for hour in hours:
                        timestamps.append(f"{hour:02d}:00")
                else:
                    hours = [0, 6, 12, 18, 24, 30, 36, 42]
                    for hour in hours:
                        if hour < 24:
                            timestamps.append(f"{hour:02d}:00")
                        else:
                            display_hour = hour - 24
                            timestamps.append(f"{display_hour:02d}:00")
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

        except Exception as e:
            traceback.print_exc()
            print(f"❌ Error in generate_growth_timestamps: {e}")
            return [f"Day {i+1}" for i in range(8)]

    def get_timestamp_x_positions(self) -> List[int]:
        x_start = 65
        x_end = 650
        interval = (x_end - x_start) / 7
        return [int(x_start + interval * i) for i in range(8)]

    async def draw_growth_header(self, template: Image.Image, growth_type: str, guild_id: int, chart_type: str = "member", role_id: Optional[int] = None) -> Image.Image:
        try:
            draw = ImageDraw.Draw(template)

            avatar_x, avatar_y = 10, 10
            avatar_size = (52, 52)
            text_start_x = 70
            text_start_y = 28
            username_rectangle = {"center": (
                133, 35), "width": 183, "height": 35}

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

            draw_text_with_stroke(
                draw, (570, 38), current_date, horndon_font, "white", "black", 2)

            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                return template

            def fit_text_to_rectangle(text, text_start_x, text_start_y, rect_center_x, rect_center_y, rect_width, rect_height):
                font_paths = [BASE_DIR / "assets" / "fonts" / "HorndonD.ttf"]
                font_sizes = [32, 30, 28, 26, 24, 22, 20, 18, 16]

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

            if chart_type == "member":
                target_name = guild.name
                use_server_icon = True
            else:
                role = guild.get_role(role_id) if role_id else None
                if role:
                    target_name = role.name
                    use_server_icon = False
                    role_color = role.color
                    if role_color == discord.Color.default():
                        role_color = discord.Color(0x2b2d31)
                else:
                    target_name = "Unknown Role"
                    use_server_icon = True

            normalized_name = unicodedata.normalize('NFKD', target_name)
            ascii_name = normalized_name.encode(
                'ascii', 'ignore').decode('ascii')
            if not ascii_name:
                ascii_name = target_name

            try:
                if chart_type == "member" or use_server_icon:
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
                else:
                    role_color_tuple = (
                        role_color.r, role_color.g, role_color.b)
                    role_image = Image.new(
                        'RGB', avatar_size, role_color_tuple)

                    mask = Image.new('L', avatar_size, 0)
                    mask_draw = ImageDraw.Draw(mask)
                    mask_draw.ellipse(
                        (0, 0, avatar_size[0], avatar_size[1]), fill=255)

                    role_image.putalpha(mask)

                    draw_role = ImageDraw.Draw(role_image)
                    try:
                        role_font = ImageFont.truetype(
                            BASE_DIR / "assets" / "fonts" / "HorndonD.ttf", 35)
                    except:
                        role_font = ImageFont.load_default()

                    initial = target_name[0].upper() if target_name else "R"
                    bbox = draw_role.textbbox((0, 0), initial, font=role_font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    text_x = (avatar_size[0] - text_width) // 2
                    text_y = (avatar_size[1] - text_height) // 2 - 10

                    stroke_width = 1
                    for dx in [-stroke_width, 0, stroke_width]:
                        for dy in [-stroke_width, 0, stroke_width]:
                            if dx != 0 or dy != 0:
                                draw_role.text(
                                    (text_x + dx, text_y + dy), initial, font=role_font, fill="black")

                    draw_role.text((text_x, text_y), initial,
                                   font=role_font, fill="white")

                    avatar_area = template.crop(
                        (avatar_x, avatar_y, avatar_x +
                         avatar_size[0], avatar_y + avatar_size[1])
                    ).convert('RGBA')

                    avatar_area.paste(role_image, (0, 0), role_image)
                    template.paste(avatar_area.convert(
                        'RGB'), (avatar_x, avatar_y))

            except Exception as e:
                traceback.print_exc()
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

            gc.collect()

            return template

        except Exception as e:
            traceback.print_exc()
            print(f"❌ Error in draw_growth_header: {e}")
            return template

    async def draw_growth_on_template(self, chart_img: Image.Image, label_text: str, days: int,
                                      timestamps: List[str], y_labels: List[Tuple[float, str]],
                                      growth_type: str, chart_type: str, guild_id: int,
                                      template_type: str = "member", role_id: Optional[int] = None,
                                      forecast_data: Optional[Dict] = None) -> io.BytesIO:
        try:
            # Choose the appropriate template based on view type
            if template_type == "member" and growth_type == "member_count":
                template_path = BASE_DIR / "assets" / "images" / "server count png.png"
            elif template_type == "member":
                template_path = BASE_DIR / "assets" / "images" / "growth final png.png"
            else:
                template_path = BASE_DIR / "assets" / "images" / "chart role.png"

            try:
                template = Image.open(template_path).convert("RGBA")
            except FileNotFoundError:
                traceback.print_exc()
                print(f"❌ Template file not found: {template_path}")
                template = Image.new('RGBA', (1200, 700), (47, 49, 54, 255))

            chart_width = 644
            chart_height = 250
            chart_img = chart_img.resize(
                (chart_width, chart_height), Image.Resampling.LANCZOS)
            template.paste(chart_img, (38, 170), chart_img)

            template = await self.draw_growth_header(template, growth_type, guild_id, template_type, role_id)

            draw = ImageDraw.Draw(template)
            try:
                horndon_font = ImageFont.truetype(
                    BASE_DIR / "assets" / "fonts" / "HorndonD.ttf", 16)
                horndon_small_font = ImageFont.truetype(
                    BASE_DIR / "assets" / "fonts" / "HorndonD.ttf", 12)
            except:
                horndon_font = ImageFont.load_default()
                horndon_small_font = ImageFont.load_default()

            # Use larger fonts for member count view
            if template_type == "member" and growth_type == "member_count":
                try:
                    member_count_font = ImageFont.truetype(
                        BASE_DIR / "assets" / "fonts" / "HorndonD.ttf", 20)  # +4 from 16
                    time_font = ImageFont.truetype(
                        BASE_DIR / "assets" / "fonts" / "HorndonD.ttf", 21)          # +5 from 16
                except:
                    member_count_font = horndon_font
                    time_font = horndon_font
            else:
                member_count_font = horndon_font
                time_font = horndon_font

            text_color = "white"
            shadow_color = "black"

            # Time period text (moved left 3 units for member count)
            if template_type == "member":
                if growth_type == "member_count":
                    time_text = f"Last {days} Days"
                    time_x = 95  # moved left from 108
                    current_font = time_font
                elif growth_type == "joins_leaves":
                    time_text = f"Last {days} Days"
                    time_x = 108
                    current_font = horndon_font
                else:
                    time_text = f"Next {days} Days"
                    time_x = 108
                    current_font = horndon_font
            else:
                time_text = f"Last {days} Days"
                time_x = 108
                current_font = horndon_font

            draw_text_with_stroke(
                draw, (time_x, 88), time_text, current_font, text_color, shadow_color, 1)

            # Draw the stats numbers at different positions based on template
            if template_type == "member":
                if growth_type == "member_count":
                    # Member count number at (362, 91) in white, using larger font
                    try:
                        draw_text_with_stroke(
                            draw, (362, 91), label_text, member_count_font, "white", shadow_color, 1)
                    except:
                        draw_text_with_stroke(
                            draw, (362, 91), "0", member_count_font, "white", shadow_color, 1)
                elif growth_type == "joins_leaves":
                    if "Joins:" in label_text:
                        try:
                            joins_text = label_text.split(
                                "Joins: ")[1].split(" |")[0]
                            draw_text_with_stroke(
                                draw, (358, 95), joins_text, horndon_font, "#21ef00", shadow_color, 1)
                        except:
                            draw_text_with_stroke(
                                draw, (358, 95), "0", horndon_font, "#21ef00", shadow_color, 1)

                    if "Leaves:" in label_text:
                        try:
                            leaves_text = label_text.split(
                                "Leaves: ")[1].split(" |")[0]
                            draw_text_with_stroke(
                                draw, (578, 95), leaves_text, horndon_font, "#ef0000", shadow_color, 1)
                        except:
                            draw_text_with_stroke(
                                draw, (578, 95), "0", horndon_font, "#ef0000", shadow_color, 1)
                elif growth_type == "forecast":
                    try:
                        joins_pred = label_text.split("Predicted Joins: ")[
                            1].split(" |")[0]
                        leaves_pred = label_text.split("Predicted Leaves: ")[1]
                        draw_text_with_stroke(
                            draw, (358, 95), joins_pred, horndon_font, "#21ef00", shadow_color, 1)
                        draw_text_with_stroke(
                            draw, (578, 95), leaves_pred, horndon_font, "#ef0000", shadow_color, 1)
                    except:
                        draw_text_with_stroke(
                            draw, (358, 95), "0", horndon_font, "#21ef00", shadow_color, 1)
                        draw_text_with_stroke(
                            draw, (578, 95), "0", horndon_font, "#ef0000", shadow_color, 1)
            else:
                # Role growth template
                if "Added:" in label_text:
                    try:
                        added_text = label_text.split(
                            "Added: ")[1].split(" |")[0]
                        draw_text_with_stroke(
                            draw, (365, 95), added_text, horndon_font, "#21ef00", shadow_color, 1)
                    except:
                        draw_text_with_stroke(
                            draw, (365, 95), "0", horndon_font, "#21ef00", shadow_color, 1)

                if "Removed:" in label_text:
                    try:
                        removed_text = label_text.split(
                            "Removed: ")[1].split(" |")[0]
                        draw_text_with_stroke(
                            draw, (595, 95), removed_text, horndon_font, "#ef0000", shadow_color, 1)
                    except:
                        draw_text_with_stroke(
                            draw, (595, 95), "0", horndon_font, "#ef0000", shadow_color, 1)

            # Timestamps (same for all templates)
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

            # Y-axis labels (same for all templates)
            y_label_positions = [(27, 148), (27, 215),
                                 (27, 280), (27, 345), (27, 400)]

            for (x, y), (value, label) in zip(y_label_positions, y_labels):
                draw_text_with_stroke(
                    draw, (x, y), label, horndon_small_font, text_color, shadow_color, 1)

            output = io.BytesIO()
            template.save(output, format='PNG')
            output.seek(0)
            gc.collect()
            return output

        except Exception as e:
            traceback.print_exc()
            print(f"❌ Error in draw_growth_on_template: {e}")
            blank = Image.new('RGBA', (1200, 700), (47, 49, 54, 255))
            output = io.BytesIO()
            blank.save(output, format='PNG')
            output.seek(0)
            return output

    # =========================================================
    # INTERNAL HANDLER FOR BOTH COMMANDS
    # =========================================================
    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def _handle_growth_member_command(self, ctx_or_interaction, is_interaction=False):
        try:
            if is_interaction:
                user = ctx_or_interaction.user
                guild = ctx_or_interaction.guild
                send_method = ctx_or_interaction.followup.send
                original_message = None
            else:
                user = ctx_or_interaction.author
                guild = ctx_or_interaction.guild
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

            if is_interaction:
                has_permission, required_permission = await self.check_growth_permission(ctx_or_interaction)
            else:
                has_permission, required_permission = await self.check_growth_permission_ctx(ctx_or_interaction)

            if not has_permission:
                embed = discord.Embed(
                    title="❌ Permission Denied",
                    description=f"Sorry! You need the `{required_permission}` permission to access this command.",
                    color=discord.Color.red()
                )
                if is_interaction:
                    await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    await ctx_or_interaction.send(embed=embed, delete_after=10)
                return

            if is_interaction:
                await ctx_or_interaction.response.defer()

            view = GrowthView(self, guild.id, days=14,
                              growth_type="member_count", chart_type="member")

            if view.growth_type == "member_count":
                data = await view.cog.fetch_member_count_history(guild.id, view.current_days)
                if not data or not data.get('counts'):
                    await view._safe_edit_response(ctx_or_interaction, content="❌ No member count data available", view=view)
                    return
                chart_img, timestamps, y_labels = self.generate_member_count_chart(
                    data, view.current_days)
                counts = data.get('counts', [])
                current_count = str(counts[-1]['count']) if counts else "0"
                label = current_count
            else:
                data = await view.fetch_member_growth_data()
                if not data or (not data.get('joins') and not data.get('leaves')):
                    await view._safe_edit_response(ctx_or_interaction, content="❌ No growth data available", view=view)
                    return
                chart_img, timestamps, y_labels = self.generate_growth_chart(
                    data, view.current_days, view.growth_type, "member")
                label = view.create_member_label(data, view.current_days)

            final_image_bytes = await self.draw_growth_on_template(
                chart_img, label, view.current_days,
                timestamps, y_labels, view.current_selection, view.growth_type, guild.id, "member"
            )

            file = discord.File(final_image_bytes, filename='growth_chart.png')

            if is_interaction:
                msg = await send_method(file=file, view=view)
            else:
                msg = await send_method(file=file, view=view, delete_after=300)

        except Exception as e:
            traceback.print_exc()
            if is_interaction:
                try:
                    await ctx_or_interaction.followup.send("❌ An error occurred while generating growth chart.", ephemeral=True)
                except:
                    pass
            else:
                try:
                    await ctx_or_interaction.send("❌ An error occurred while generating growth chart.", delete_after=10)
                except:
                    pass

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def _handle_growth_role_command(self, ctx_or_interaction, role, is_interaction=False):
        try:
            if is_interaction:
                user = ctx_or_interaction.user
                guild = ctx_or_interaction.guild
                send_method = ctx_or_interaction.followup.send
                original_message = None
            else:
                user = ctx_or_interaction.author
                guild = ctx_or_interaction.guild
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

            if is_interaction:
                has_permission, required_permission = await self.check_growth_permission(ctx_or_interaction)
            else:
                has_permission, required_permission = await self.check_growth_permission_ctx(ctx_or_interaction)

            if not has_permission:
                embed = discord.Embed(
                    title="❌ Permission Denied",
                    description=f"Sorry! You need the `{required_permission}` permission to access this command.",
                    color=discord.Color.red()
                )
                if is_interaction:
                    await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    await ctx_or_interaction.send(embed=embed, delete_after=10)
                return

            if role.id == guild.id or role.name == "@here":
                if is_interaction:
                    await ctx_or_interaction.response.send_message("❌ Cannot track growth for this role.", ephemeral=True)
                else:
                    await ctx_or_interaction.send("❌ Cannot track growth for this role.", delete_after=5)
                return

            if is_interaction:
                await ctx_or_interaction.response.defer()

            view = GrowthView(self, guild.id, days=14, chart_type="role",
                              growth_type="role_additions_removals", role_id=role.id)

            data = await view.fetch_role_growth_data()

            if not data or (not data.get('joins') and not data.get('leaves')):
                if is_interaction:
                    await ctx_or_interaction.followup.send("❌ No growth data available for this role", view=view)
                else:
                    await ctx_or_interaction.send("❌ No growth data available for this role", view=view, delete_after=300)
                return

            chart_img, timestamps, y_labels = self.generate_growth_chart(
                data, view.current_days, view.growth_type, "role"
            )

            label = view.create_role_label(data, view.current_days)
            final_image_bytes = await self.draw_growth_on_template(
                chart_img, label, view.current_days,
                timestamps, y_labels, view.current_selection, view.growth_type, guild.id, "role", role.id
            )

            file = discord.File(final_image_bytes, filename='growth_chart.png')

            if is_interaction:
                msg = await send_method(file=file, view=view)
            else:
                msg = await send_method(file=file, view=view, delete_after=300)

        except Exception as e:
            traceback.print_exc()
            if is_interaction:
                try:
                    await ctx_or_interaction.followup.send("❌ An error occurred while generating growth chart.", ephemeral=True)
                except:
                    pass
            else:
                try:
                    await ctx_or_interaction.send("❌ An error occurred while generating growth chart.", delete_after=10)
                except:
                    pass

    # =========================================================
    # SHORTCUT COMMANDS
    # =========================================================

    @commands.command(name="gm")
    async def growth_member_shortcut(self, ctx: commands.Context):
        await self._handle_growth_member_command(ctx, is_interaction=False)

    @commands.command(name="gr")
    async def growth_role_shortcut(self, ctx: commands.Context, role: discord.Role):
        await self._handle_growth_role_command(ctx, role, is_interaction=False)

    # =========================================================
    # PREFIX COMMAND GROUP
    # =========================================================

    @commands.group(name="growth", invoke_without_command=True)
    async def growth_group_prefix(self, ctx: commands.Context):
        try:
            await ctx.send("Available commands:\n- `growth member` - Track server member growth\n- `growth role <role>` - Track role growth\n- `gm` - Shortcut for growth member\n- `gr <role>` - Shortcut for growth role")
        except Exception as e:
            traceback.print_exc()
            await ctx.send("❌ An error occurred while displaying help.")

    @growth_group_prefix.command(name="member")
    async def growth_member_prefix(self, ctx: commands.Context):
        await self._handle_growth_member_command(ctx, is_interaction=False)

    @growth_group_prefix.command(name="role")
    async def growth_role_prefix(self, ctx: commands.Context, role: discord.Role):
        await self._handle_growth_role_command(ctx, role, is_interaction=False)

    # =========================================================
    # SLASH COMMAND GROUP
    # =========================================================

    growth_group = app_commands.Group(
        name="growth",
        description="Track server growth and role growth"
    )

    @growth_group.command(name="member", description="Track server member growth and projections")
    async def growth_member(self, interaction: discord.Interaction):
        await self._handle_growth_member_command(interaction, is_interaction=True)

    @growth_group.command(name="role", description="Track role growth over time")
    @app_commands.describe(role="The role to track growth for")
    async def growth_role(self, interaction: discord.Interaction, role: discord.Role):
        await self._handle_growth_role_command(interaction, role, is_interaction=True)

# =========================================================
# SETUP
# =========================================================


async def setup(bot):
    try:
        cog = GrowthSystem(bot)
        await bot.add_cog(cog)
    except Exception as e:
        traceback.print_exc()
        print(f"❌ Error loading GrowthSystem cog: {e}")
