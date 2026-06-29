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


# ======================================================================
# CONSTANTS
# ======================================================================

# Types shown in server / channel / category dropdowns
# "Mentions Received" is removed; "Mentions Sent" is renamed to "Mentions"
ACTIVITY_TYPES_SERVER = [
    ("Messages",       "Message activity distribution"),
    ("Voice Activity", "Voice time distribution"),
    ("Activities",     "General activity / game presence"),
    ("Emoji Usage",    "Emoji usage distribution"),
    ("Mentions",       "Mentions sent distribution"),
    ("Invites",        "Invite usage distribution"),
    ("Joins",          "Member join distribution"),
    ("Leaves",         "Member leave distribution"),
]

ACTIVITY_TYPES_CHANNEL = [
    ("Messages",       "Message activity distribution"),
    ("Voice Activity", "Voice time distribution"),
    ("Emoji Usage",    "Emoji usage distribution"),
    ("Mentions",       "Mentions sent distribution"),
]

ACTIVITY_TYPES_CATEGORY = [
    ("Messages",       "Message activity distribution"),
    ("Voice Activity", "Voice time distribution"),
    ("Emoji Usage",    "Emoji usage distribution"),
    ("Mentions",       "Mentions sent distribution"),
]

# User scope keeps full Mentions Sent / Received separation and adds Invites
ACTIVITY_TYPES_USER = [
    ("Messages",          "Message activity distribution"),
    ("Voice Activity",    "Voice time distribution"),
    ("Activities",        "General activity / game presence"),
    ("Emoji Usage",       "Emoji usage distribution"),
    ("Mentions Sent",     "Mentions sent distribution"),
    ("Mentions Received", "Mentions received distribution"),
    ("Invites",           "Invites sent by this user"),
]

SCOPE_TYPE_LIST = {
    "server":   ACTIVITY_TYPES_SERVER,
    "channel":  ACTIVITY_TYPES_CHANNEL,
    "category": ACTIVITY_TYPES_CATEGORY,
    "user":     ACTIVITY_TYPES_USER,
}

# Stat types where role_filter_ids must NOT be forwarded to the DB
ROLE_FILTER_UNSUPPORTED = {"Joins", "Leaves", "Invites"}


# ======================================================================
# INITIALIZATION
# ======================================================================

class TimezoneDistribution(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_sessions = {}
        self.background_image_path = BASE_DIR / "assets" / \
            "images" / "timezone chart final png.png"
        self.font_path = BASE_DIR / "assets" / "fonts" / "HorndonD.ttf"
        self.rate_limiter = get_rate_limiter()

    # ------------------------------------------------------------------
    # Helper cog accessors
    # ------------------------------------------------------------------
    def get_db_cog(self):
        return self.bot.get_cog('DatabaseStats')

    def get_settings_cog(self):
        return self.bot.get_cog('Settings')

    # ------------------------------------------------------------------
    # PERMISSION CHECKING
    # ------------------------------------------------------------------
    async def check_permission(self, interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        settings_cog = self.get_settings_cog()
        if not settings_cog:
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
            elif permission_level in ('Default', 'User Restriction'):
                return True
            return True
        except Exception as e:
            print(f"⚠️ Error checking permission: {e}")
            return interaction.user.guild_permissions.administrator

    async def send_permission_error(self, interaction: discord.Interaction):
        settings_cog = self.get_settings_cog()
        required_permission = "Administrator"
        if settings_cog:
            try:
                settings = await settings_cog.get_guild_settings(interaction.guild_id)
                permission_level = settings.get('permission_level', 'Default')
                if permission_level == 'Moderator':
                    required_permission = "Manage Server"
            except:
                pass
        embed = discord.Embed(
            title="❌ Permission Denied",
            description=f"Sorry! You need the `{required_permission}` permission to access this command.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # SERVER DEFAULT TIME RANGE
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # SERVER DEFAULT TIME RANGE
    # ------------------------------------------------------------------
    async def get_server_default_time_range(self, guild_id: int) -> tuple:
        """Get the default time range from server settings. Returns (start_time, end_time, display_text, days_back_equiv)"""
        try:
            settings_cog = self.get_settings_cog()
            if not settings_cog:
                end = datetime.now(timezone.utc)
                start = end - timedelta(days=30)
                return (start, end, "30 days", 30)

            settings = await settings_cog.get_guild_settings(guild_id)
            mode = settings.get('default_time_mode', 'days_back')
            now = datetime.now(timezone.utc)

            if mode == 'all_time':
                return (None, now, "All Time", 999999)

            elif mode == 'days_back':
                days = settings.get('default_days_back') or 30
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
            start = now - timedelta(days=30)
            return (start, end, "30 days", 30)

        except Exception as e:
            import traceback
            traceback.print_exc()
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=30)
            return (start, end, "30 days", 30)

    # ------------------------------------------------------------------
    # TIMEZONE HELPER
    # ------------------------------------------------------------------
    async def get_guild_timezone(self, guild_id: int) -> str:
        settings_cog = self.get_settings_cog()
        if not settings_cog:
            return "UTC"
        try:
            settings = await settings_cog.get_guild_settings(guild_id)
            return settings.get('timezone', 'UTC')
        except:
            return "UTC"

    # ------------------------------------------------------------------
    # PREFIX PERMISSION CHECK
    # ------------------------------------------------------------------
    async def _check_prefix_permission(self, ctx: commands.Context) -> bool:
        user = ctx.author
        settings_cog = self.get_settings_cog()
        if not settings_cog:
            if not user.guild_permissions.administrator:
                embed = discord.Embed(
                    title="❌ Permission Denied",
                    description="Sorry! You need the `Administrator` permission to access this command.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed, delete_after=10)
                return False
            return True
        try:
            settings = await settings_cog.get_guild_settings(ctx.guild.id)
            level = settings.get('permission_level', 'Default')
            if level in ('All', 'Default', 'User Restriction'):
                return True
            elif level == 'Admin':
                if not user.guild_permissions.administrator:
                    embed = discord.Embed(
                        title="❌ Permission Denied",
                        description="Sorry! You need the `Administrator` permission.",
                        color=discord.Color.red()
                    )
                    await ctx.send(embed=embed, delete_after=10)
                    return False
            elif level == 'Moderator':
                if not user.guild_permissions.manage_guild:
                    embed = discord.Embed(
                        title="❌ Permission Denied",
                        description="Sorry! You need the `Manage Server` permission.",
                        color=discord.Color.red()
                    )
                    await ctx.send(embed=embed, delete_after=10)
                    return False
            return True
        except Exception as e:
            print(f"⚠️ Prefix permission error: {e}")
            if not user.guild_permissions.administrator:
                embed = discord.Embed(
                    title="❌ Permission Denied",
                    description="Sorry! You need the `Administrator` permission.",
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed, delete_after=10)
                return False
            return True

    # ======================================================================
    # DATA FETCHING
    # ======================================================================

    async def get_hourly_activity_data(
        self,
        guild_id: int,
        activity_type: str,
        start_time: datetime = None,
        end_time: datetime = None,
        days_back_equiv: int = 30,
        scope: str = "server",
        scope_id: int = None,
        role_filter_ids=None,
        timezone_str: str = 'UTC',
    ):
        """Dispatch to the correct DB query based on scope + activity_type."""
        try:
            db_cog = self.get_db_cog()
            if not db_cog:
                print("⚠️ DatabaseStats cog not initialised")
                return [0] * 24

            # Normalise role_filter_ids
            if isinstance(role_filter_ids, list):
                role_filter_ids = [
                    r for r in role_filter_ids if r is not None] or None
            elif isinstance(role_filter_ids, int):
                role_filter_ids = [role_filter_ids]
            elif not role_filter_ids:
                role_filter_ids = None

            # Silently suppress role filter for stat types that don't support it
            if activity_type in ROLE_FILTER_UNSUPPORTED:
                role_filter_ids = None

            # If end_time not provided, use current time
            if end_time is None:
                end_time = datetime.now(timezone.utc)

            result = await self._dispatch_query(
                db_cog, guild_id, activity_type, scope, scope_id,
                role_filter_ids, start_time, end_time, timezone_str
            )

            if result is None:
                return [0] * 24

            return [result.get(f'hour_{i}', 0) for i in range(24)]

        except Exception as e:
            print(f"❌ Error in get_hourly_activity_data: {e}")
            import traceback
            traceback.print_exc()
            return [0] * 24

    async def _dispatch_query(
        self, db_cog, guild_id, activity_type, scope, scope_id,
        role_filter_ids, start_time, end_time, timezone_str
    ):
        """Route to the matching q_* method on db_cog."""
        kw = dict(
            guild_id=guild_id,
            role_filter_ids=role_filter_ids,
            start_time=start_time,
            end_time=end_time,
            timezone_str=timezone_str,
        )

        # Inject scope-specific id
        if scope == "channel" and scope_id:
            kw["channel_id"] = scope_id
        elif scope == "category" and scope_id:
            kw["category_id"] = scope_id
        elif scope == "user" and scope_id:
            kw["user_id"] = scope_id

        prefix_map = {
            "server":   "q_server_distribution_",
            "channel":  "q_channel_distribution_",
            "category": "q_category_distribution_",
            "user":     "q_user_distribution_",
        }
        prefix = prefix_map.get(scope, "q_server_distribution_")

        # Map display label → DB method suffix
        # "Mentions" (server/channel/category) maps to mentions_sent
        # User scope keeps "Mentions Sent" and "Mentions Received" separate
        # User "Invites" maps to invites_sent
        type_map = {
            "Messages":           "messages",
            "Voice Activity":     "voice",
            "Activities":         "activity",
            "Emoji Usage":        "emoji_usage",
            "Mentions":           "mentions_sent",   # server/channel/category label
            "Mentions Sent":      "mentions_sent",   # user label
            "Mentions Received":  "mentions_received",
            "Invites":            "invites" if scope != "user" else "invites_sent",
            "Joins":              "joins",
            "Leaves":             "leaves",
        }
        suffix = type_map.get(activity_type)
        if not suffix:
            return None

        method_name = prefix + suffix
        method = getattr(db_cog, method_name, None)
        if method is None:
            print(
                f"⚠️ Method {method_name} not found on db_cog – returning zeros")
            return None

        if suffix == "emoji_usage":
            kw["usage_type"] = None

        # Strip kwargs the method doesn't accept
        import inspect
        sig_params = inspect.signature(method).parameters
        kw = {k: v for k, v in kw.items() if k in sig_params}

        return await method(**kw)

    # ======================================================================
    # TIMEZONE / ACTIVITY HELPERS
    # ======================================================================

    def apply_timezone_offset(self, hourly_data: list, timezone: str):
        offsets = {
            "UTC": 0, "GMT": 0,
            "EST": -5, "PST": -8, "CST": -6, "MST": -7,
            "CET": 1, "EET": 2, "IST": 5.5, "JST": 9,
            "AEST": 10, "NZST": 12,
        }
        offset_hours = int(offsets.get(timezone, 0))
        shifted = [0] * 24
        for i in range(24):
            shifted[(i - offset_hours) % 24] = hourly_data[i]
        return shifted

    def categorize_activity_levels(self, hourly_data: list):
        total = sum(hourly_data)
        if total == 0:
            return [("Low Activity", 0)] * 24
        avg = total / 24
        peak_thr = avg * 2.0
        high_thr = avg * 1.5
        medium_thr = avg * 0.8
        result = []
        for v in hourly_data:
            if v >= peak_thr:
                result.append(("Peak Activity",   v))
            elif v >= high_thr:
                result.append(("High Activity",   v))
            elif v >= medium_thr:
                result.append(("Medium Activity", v))
            else:
                result.append(("Low Activity",    v))
        return result

    # ======================================================================
    # CHART DRAWING
    # ======================================================================

    def draw_text_with_stroke(self, draw, position, text, font,
                              fill_color, stroke_color, stroke_width):
        x, y = position
        for dx in range(-stroke_width, stroke_width + 1):
            for dy in range(-stroke_width, stroke_width + 1):
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), text,
                              font=font, fill=stroke_color)
        draw.text((x, y), text, font=font, fill=fill_color)

    async def create_clock_pie_chart(
        self, activity_levels, timezone, activity_type,
        guild, display_text, role_filter_name=None,
        scope="server", scope_member: discord.Member = None
    ):
        try:
            background = Image.open(self.background_image_path).convert('RGBA')
            image = background.copy()
            draw = ImageDraw.Draw(image)

            def load_font(size):
                try:
                    return ImageFont.truetype(str(self.font_path), size)
                except:
                    return ImageFont.load_default()

            font_huge = load_font(40)
            font_large = load_font(24)
            font_medium = load_font(20)
            font_small = load_font(16)
            font_clock = load_font(16)

            def stroke_text(drw, pos, txt, fnt, fill, stroke, sw):
                x, y = pos
                for dx in [-sw, 0, sw]:
                    for dy in [-sw, 0, sw]:
                        if dx != 0 or dy != 0:
                            drw.text((x + dx, y + dy), txt,
                                     font=fnt, fill=stroke)
                drw.text((x, y), txt, font=fnt, fill=fill)

            def fit_text(text, sx, sy, cx, cy, rw, rh):
                rl, rr = cx - rw//2, cx + rw//2
                rt, rb = cy - rh//2, cy + rh//2
                for size in [40, 38, 36, 34, 32, 30, 28, 26, 24, 22, 20, 18, 16]:
                    fnt = load_font(size)
                    bb = draw.textbbox((0, 0), text, font=fnt)
                    tw, th = bb[2]-bb[0], bb[3]-bb[1]
                    tx, ty = sx, sy - th//2
                    vo = sum([1 for s in [40, 30, 20, 16] if size <= s])
                    ty += vo
                    if tx >= rl-1 and tx+tw <= rr+1 and ty >= rt-1 and ty+th <= rb+1:
                        return text, fnt, (tx, ty)
                # fallback: truncate
                fnt = load_font(16)
                cur = text
                while len(cur) > 3:
                    cur = cur[:-4] + "..."
                    bb = draw.textbbox((0, 0), cur, font=fnt)
                    tw = bb[2]-bb[0]
                    if sx+tw <= rr+1:
                        return cur, fnt, (sx, sy)
                return text[:3]+"...", fnt, (sx, sy)

            # ------------------------------------------------------------------
            # TOP-LEFT: user avatar+name for user scope, server icon+name otherwise
            # ------------------------------------------------------------------
            if scope == "user" and scope_member is not None:
                # User avatar
                try:
                    async with aiohttp.ClientSession() as sess:
                        async with sess.get(scope_member.display_avatar.url) as resp:
                            avatar_data = await resp.read()
                    ava = Image.open(io.BytesIO(avatar_data)).resize(
                        (60, 60), Image.Resampling.LANCZOS).convert('RGBA')
                    mask = Image.new('L', (60, 60), 0)
                    ImageDraw.Draw(mask).ellipse((0, 0, 60, 60), fill=255)
                    ava.putalpha(mask)
                    area = image.crop((7, 10, 67, 70)).convert('RGBA')
                    area.paste(ava, (0, 0), ava)
                    image.paste(area.convert('RGB'), (7, 10))
                    ava.close()
                    del ava, avatar_data
                except Exception as e:
                    print(f"❌ Could not load user avatar: {e}")

                # User display name
                display_name = scope_member.display_name
                txt, fnt, pos = fit_text(
                    display_name, 85, 30, 150, 30, 183, 35)
                stroke_text(draw, pos, txt, fnt, "white", "black", 1)

            else:
                # Server icon
                try:
                    if guild.icon:
                        async with aiohttp.ClientSession() as sess:
                            async with sess.get(guild.icon.url) as resp:
                                icon_data = await resp.read()
                        ico = Image.open(io.BytesIO(icon_data)).resize(
                            (60, 60), Image.Resampling.LANCZOS).convert('RGBA')
                        mask = Image.new('L', (60, 60), 0)
                        ImageDraw.Draw(mask).ellipse((0, 0, 60, 60), fill=255)
                        ico.putalpha(mask)
                        area = image.crop((7, 10, 67, 70)).convert('RGBA')
                        area.paste(ico, (0, 0), ico)
                        image.paste(area.convert('RGB'), (7, 10))
                        ico.close()
                        del ico, icon_data
                except Exception as e:
                    print(f"❌ Could not load server icon: {e}")

                # Server name
                txt, fnt, pos = fit_text(guild.name, 85, 30, 150, 30, 183, 35)
                stroke_text(draw, pos, txt, fnt, "white", "black", 1)

            # --- Date ---
            stroke_text(draw, (560, 38), datetime.now().strftime("%B %d, %Y"),
                        font_small, "white", "black", 1)

            # --- Time period (use display_text) ---
            stroke_text(draw, (105, 423), display_text,
                        font_medium, "white", "black", 1)

            # --- Role filter (only show if a filter is active and supported) ---
            if role_filter_name and role_filter_name != "No Filter":
                stroke_text(draw, (105, 450), f"Filter: {role_filter_name}",
                            font_medium, "white", "black", 1)

            # --- Clock pie ---
            colors = {
                "Peak Activity":   (255, 215,   0, 255),
                "High Activity":   (255, 107, 107, 255),
                "Medium Activity": (81, 207, 102, 255),
                "Low Activity":    (134, 142, 150, 255),
            }
            cx, cy, radius = 380, 240, 180
            clock_layer = Image.new('RGBA', image.size, (0, 0, 0, 0))
            cd = ImageDraw.Draw(clock_layer)

            for i, (cat, _) in enumerate(activity_levels):
                sa = i * 15 - 90
                ea = (i+1) * 15 - 90
                cd.pieslice([cx-radius, cy-radius, cx+radius, cy+radius],
                            sa, ea, fill=colors[cat], outline="white", width=1)

            cd.ellipse([cx-10, cy-10, cx+10, cy+10], fill=(0, 0, 0, 255))

            tz_offsets = {"UTC": 0, "GMT": 0, "EST": -5, "PST": -8, "CST": -6, "MST": -7,
                          "CET": 1, "EET": 2, "IST": 5.5, "JST": 9, "AEST": 10, "NZST": 12}
            off = int(tz_offsets.get(timezone, 0))
            nr = radius + 15
            for i in range(24):
                angle = np.radians(i * 15 - 90)
                x = cx + nr * np.cos(angle)
                y = cy + nr * np.sin(angle)
                hour_num = ((i + off) % 24) + 1
                try:
                    bb = cd.textbbox((0, 0), str(hour_num), font=font_clock)
                    tw, th = bb[2]-bb[0], bb[3]-bb[1]
                    tx, ty = x - tw/2, y - th/2
                except:
                    tx, ty = x-8, y-8
                stroke_text(cd, (tx, ty), str(hour_num),
                            font_clock, "white", "black", 2)

            image = Image.alpha_composite(image, clock_layer)
            buf = BytesIO()
            image.save(buf, format='PNG')
            buf.seek(0)
            gc.collect()
            return buf

        except Exception as e:
            print(f"Error creating Pillow chart: {e}")
            import traceback
            traceback.print_exc()
            return self._fallback_chart(activity_levels, timezone, activity_type, display_text)

    def _fallback_chart(self, activity_levels, timezone, activity_type, display_text):
        plt.style.use('default')
        fig, ax = plt.subplots(
            figsize=(10, 10), subplot_kw=dict(projection='polar'))
        colors = {
            "Peak Activity": "#FFD700", "High Activity": "#FF6B6B",
            "Medium Activity": "#51CF66", "Low Activity": "#868E96",
        }
        theta = np.linspace(0, 2*np.pi, 24, endpoint=False)
        width = 2*np.pi / 24
        for i, (cat, _) in enumerate(activity_levels):
            ax.bar(theta[i], 1, width=width, bottom=0,
                   color=colors[cat], alpha=1.0, edgecolor='white', linewidth=1)
        ax.set_title(f"{activity_type} – {display_text}", pad=20, fontsize=12)
        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)
        ax.set_ylim(0, 1)
        ax.set_yticklabels([])
        ax.grid(False)
        ax.spines['polar'].set_visible(False)
        buf = BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight',
                    dpi=100, facecolor='white')
        buf.seek(0)
        plt.close()
        gc.collect()
        return buf

    # ======================================================================
    # MODALS
    # ======================================================================

    class TimezoneTimeModal(discord.ui.Modal, title='Custom Time Period'):
        def __init__(self, cog_instance, guild, view):
            super().__init__(timeout=300)
            self.cog = cog_instance
            self.guild = guild
            self.view = view

        days = discord.ui.TextInput(
            label='Enter number of days',
            placeholder='e.g., 7, 14, 30, 90, 2000…',
            min_length=1, max_length=4, required=True,
        )

        async def on_submit(self, interaction: discord.Interaction):
            try:
                days = int(self.days.value)
                if days <= 0 or days > 2000:
                    await interaction.response.send_message(
                        "❌ Please enter a number between 1 and 2000 days.", ephemeral=True)
                    return
                await interaction.response.defer(ephemeral=False)
                if self.view:
                    now = datetime.now(timezone.utc)
                    self.view.current_start_time = now - timedelta(days=days)
                    self.view.current_end_time = now
                    self.view.current_days_back_equiv = days
                    self.view.current_display_text = f"{days} days"
                    self.view.using_server_default = False
                    await self.view.update_message(interaction)
                else:
                    await interaction.followup.send("❌ Could not update chart.", ephemeral=True)
            except ValueError:
                await interaction.response.send_message("❌ Please enter a valid number.", ephemeral=True)
            except Exception as e:
                print(f"Error in timezone modal: {e}")
                await interaction.followup.send("❌ An error occurred.", ephemeral=True)

    class RoleFilterModal(discord.ui.Modal, title='Filter By Role'):
        def __init__(self, cog_instance, guild, view):
            super().__init__(timeout=300)
            self.cog = cog_instance
            self.guild = guild
            self.view = view

        role_id = discord.ui.TextInput(
            label='Enter Role ID or "none"',
            placeholder='e.g., 123456789012345678 or "none"',
            min_length=1, max_length=20, required=True,
        )

        async def on_submit(self, interaction: discord.Interaction):
            try:
                raw = self.role_id.value.strip().lower()
                if raw == "none":
                    role_name, role_filter_ids = "No Filter", None
                else:
                    try:
                        rid = int(raw)
                        role = self.guild.get_role(rid)
                        if role is None:
                            await interaction.response.send_message(embed=discord.Embed(
                                title="❌ Invalid Role ID",
                                description="The role ID you entered is not valid.",
                                color=discord.Color.red()), ephemeral=True)
                            return
                        role_name, role_filter_ids = role.name, [rid]
                    except ValueError:
                        await interaction.response.send_message(embed=discord.Embed(
                            title="❌ Invalid Input",
                            description="Please enter a valid role ID number or 'none'.",
                            color=discord.Color.red()), ephemeral=True)
                        return
                await interaction.response.defer(ephemeral=False)
                if self.view:
                    self.view.role_filter_ids = role_filter_ids
                    self.view.role_filter_name = role_name
                    await self.view.update_message(interaction)
                else:
                    await interaction.followup.send("❌ Could not update chart.", ephemeral=True)
            except Exception as e:
                print(f"Error in role filter modal: {e}")
                await interaction.response.send_message(embed=discord.Embed(
                    title="❌ Error", description="An error occurred.",
                    color=discord.Color.red()), ephemeral=True)

    # ======================================================================
    # ACTIVITY TYPE DROPDOWN
    # ======================================================================

    class ActivityTypeSelect(discord.ui.Select):
        def __init__(self, current_type: str, scope: str):
            type_list = SCOPE_TYPE_LIST.get(scope, ACTIVITY_TYPES_SERVER)
            # If current_type not in this scope's list, default to first option
            valid_labels = {t[0] for t in type_list}
            effective_current = current_type if current_type in valid_labels else type_list[
                0][0]
            options = [
                discord.SelectOption(
                    label=label,
                    description=desc,
                    value=label,
                    default=(label == effective_current),
                )
                for label, desc in type_list
            ]
            super().__init__(
                placeholder="Select stat type…",
                options=options,
                custom_id="activity_type_select",
            )

        async def callback(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=False, thinking=False)
            self.view.activity_type = self.values[0]
            await self.view.update_message(interaction)

    # ======================================================================
    # MAIN VIEW
    # ======================================================================

    class DistributionView(discord.ui.View):
        def __init__(
            self, cog, guild: discord.Guild,
            scope: str = "server",
            scope_id: int = None,
            scope_member: discord.Member = None,
            timezone: str = "UTC",
            activity_type: str = "Messages",
            start_time: datetime = None,
            end_time: datetime = None,
            days_back_equiv: int = 30,
            display_text: str = "30 days",
            using_server_default: bool = True,
        ):
            super().__init__(timeout=600)
            self.cog = cog
            self.guild = guild
            self.scope = scope
            self.scope_id = scope_id
            self.scope_member = scope_member   # discord.Member for user scope
            self.timezone = timezone
            self.activity_type = activity_type
            self.current_start_time = start_time
            self.current_end_time = end_time if end_time else datetime.now(
                timezone.utc)
            self.current_days_back_equiv = days_back_equiv
            self.current_display_text = display_text
            self.show_time_buttons = False
            self.role_filter_ids = None
            self.role_filter_name = None
            self.using_server_default = using_server_default
            self._update_buttons()

        def _update_buttons(self):
            self.clear_items()

            # Row 0: dropdown
            self.add_item(TimezoneDistribution.ActivityTypeSelect(
                self.activity_type, self.scope))

            # Row 1: Input Role Id (only non-user scopes), Refresh, Time Settings
            # Button order: Input Role Id → Refresh → Time Settings
            if self.scope != "user":
                btn_role = discord.ui.Button(
                    style=discord.ButtonStyle.primary, label="Filter By Role",
                    custom_id="dist_role_filter")
                btn_role.callback = self._role_filter_cb
                self.add_item(btn_role)

            btn_refresh = discord.ui.Button(
                style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji(
                    name="refresh", id=1518249841505861743),
                custom_id="dist_refresh")
            btn_refresh.callback = self._refresh_cb
            self.add_item(btn_refresh)

            btn_time = discord.ui.Button(
                style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji(
                    name="clockk", id=1518249803069259867),
                custom_id="dist_time_settings")
            btn_time.callback = self._time_settings_cb
            self.add_item(btn_time)

            if self.show_time_buttons:
                presets = [(999999, "All Time"), (7, "7 Days"),
                           (14, "14 Days"), (30, "30 Days"), (90, "90 Days")]
                for days_val, lbl in presets:
                    b = discord.ui.Button(
                        style=(discord.ButtonStyle.primary
                               if self.current_days_back_equiv == days_val
                               else discord.ButtonStyle.secondary),
                        label=lbl,
                        custom_id=f"dist_preset_{days_val}",
                    )
                    b.callback = self._make_preset_cb(days_val, lbl.lower())
                    self.add_item(b)

                custom_label = (self.current_display_text
                                if self.current_days_back_equiv not in (7, 14, 30, 90, 999999)
                                else "Custom")
                if len(custom_label) > 20:
                    custom_label = custom_label[:17] + "..."
                b_custom = discord.ui.Button(
                    style=discord.ButtonStyle.success,
                    label=custom_label, custom_id="dist_custom_days")
                b_custom.callback = self._custom_days_cb
                self.add_item(b_custom)

        def _make_preset_cb(self, days_val, display):
            async def cb(interaction: discord.Interaction):
                await interaction.response.defer(ephemeral=False, thinking=False)
                now = datetime.now(timezone.utc)
                if days_val == 999999:
                    start_time = None
                else:
                    start_time = now - timedelta(days=days_val)
                self.current_start_time = start_time
                self.current_end_time = now
                self.current_days_back_equiv = days_val
                self.current_display_text = display
                self.using_server_default = False
                self.show_time_buttons = False
                await self.update_message(interaction)
            return cb

        async def _refresh_cb(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=False, thinking=False)
            await self.update_message(interaction)

        async def _time_settings_cb(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=False, thinking=False)
            self.show_time_buttons = not self.show_time_buttons
            self._update_buttons()
            await interaction.edit_original_response(view=self)

        async def _role_filter_cb(self, interaction: discord.Interaction):
            modal = TimezoneDistribution.RoleFilterModal(
                self.cog, self.guild, self)
            await interaction.response.send_modal(modal)

        async def _custom_days_cb(self, interaction: discord.Interaction):
            modal = TimezoneDistribution.TimezoneTimeModal(
                self.cog, self.guild, self)
            await interaction.response.send_modal(modal)

        async def generate_chart(self):
            hourly = await self.cog.get_hourly_activity_data(
                guild_id=self.guild.id,
                activity_type=self.activity_type,
                start_time=self.current_start_time,
                end_time=self.current_end_time,
                days_back_equiv=self.current_days_back_equiv,
                scope=self.scope,
                scope_id=self.scope_id,
                role_filter_ids=self.role_filter_ids,
                timezone_str=self.timezone,
            )
            shifted = self.cog.apply_timezone_offset(hourly, self.timezone)
            levels = self.cog.categorize_activity_levels(shifted)
            return await self.cog.create_clock_pie_chart(
                levels, self.timezone, self.activity_type,
                self.guild, self.current_display_text,
                self.role_filter_name,
                scope=self.scope,
                scope_member=self.scope_member,
            )

        async def update_message(self, interaction: discord.Interaction):
            try:
                buf = await self.generate_chart()
                self._update_buttons()
                f = discord.File(buf, filename="distribution.png")
                if interaction.response.is_done():
                    await interaction.edit_original_response(attachments=[f], view=self)
                else:
                    await interaction.response.edit_message(attachments=[f], view=self)
            except Exception as e:
                print(f"❌ Error updating distribution message: {e}")
                msg = "❌ An error occurred while updating the chart."
                try:
                    if not interaction.response.is_done():
                        await interaction.response.send_message(msg, ephemeral=True)
                    else:
                        await interaction.followup.send(msg, ephemeral=True)
                except:
                    pass

    # ======================================================================
    # SHARED SEND HELPER
    # ======================================================================

    async def _send_distribution(
        self,
        ctx_or_interaction,
        is_interaction: bool,
        scope: str,
        scope_id: int = None,
        scope_member: discord.Member = None,
    ):
        """Build and send a DistributionView for any scope."""
        try:
            if is_interaction:
                guild = ctx_or_interaction.guild
                send = ctx_or_interaction.followup.send
            else:
                guild = ctx_or_interaction.guild
                try:
                    await ctx_or_interaction.message.delete()
                except:
                    pass
                send = ctx_or_interaction.send

            if guild is None:
                msg = "❌ This command can only be used in a server."
                if is_interaction:
                    await ctx_or_interaction.response.send_message(msg, ephemeral=True)
                else:
                    await ctx_or_interaction.send(msg, delete_after=5)
                return

            if is_interaction:
                if not await self.check_permission(ctx_or_interaction):
                    await self.send_permission_error(ctx_or_interaction)
                    return
                await ctx_or_interaction.response.defer()
            else:
                if not await self._check_prefix_permission(ctx_or_interaction):
                    return

            db_cog = self.get_db_cog()
            if not db_cog:
                msg = "❌ Database connection not available."
                if is_interaction:
                    await ctx_or_interaction.followup.send(msg, ephemeral=True)
                else:
                    await ctx_or_interaction.send(msg, delete_after=10)
                return

            tz = await self.get_guild_timezone(guild.id)
            start_time, end_time, display_text, days_back_equiv = await self.get_server_default_time_range(guild.id)

            view = self.DistributionView(
                cog=self,
                guild=guild,
                scope=scope,
                scope_id=scope_id,
                scope_member=scope_member,
                timezone=tz,
                activity_type="Messages",
                start_time=start_time,
                end_time=end_time,
                days_back_equiv=days_back_equiv,
                display_text=display_text,
                using_server_default=True,
            )

            buf = await view.generate_chart()
            file = discord.File(buf, filename="distribution.png")

            db_cog = self.get_db_cog()
            retention_alert_text = await db_cog.maybe_get_retention_alert(guild.id) if db_cog else None

            await send(content=retention_alert_text, file=file, view=view)

        except Exception as e:
            print(f"❌ Error in _send_distribution ({scope}): {e}")
            import traceback
            traceback.print_exc()
            err = "❌ An error occurred while generating the chart. Please try again later."
            if is_interaction:
                try:
                    await ctx_or_interaction.followup.send(err, ephemeral=True)
                except:
                    pass
            else:
                try:
                    await ctx_or_interaction.send(err, delete_after=10)
                except:
                    pass

    # ======================================================================
    # PREFIX COMMAND GROUP
    # ======================================================================

    @commands.group(name="distribution", invoke_without_command=True)
    async def distribution_group(self, ctx: commands.Context):
        """Distribution commands. Use a subcommand: server, channel, user, category."""
        await ctx.send_help(ctx.command)

    @distribution_group.command(name="server")
    async def dist_server_prefix(self, ctx: commands.Context):
        """Server-wide hourly activity distribution."""
        await self._send_distribution(ctx, is_interaction=False, scope="server")

    @distribution_group.command(name="channel")
    async def dist_channel_prefix(self, ctx: commands.Context,
                                  channel: discord.TextChannel = None):
        """Channel hourly activity distribution. Defaults to current channel."""
        ch = channel or ctx.channel
        await self._send_distribution(
            ctx, is_interaction=False,
            scope="channel", scope_id=ch.id,
        )

    @distribution_group.command(name="user")
    async def dist_user_prefix(self, ctx: commands.Context,
                               member: discord.Member = None):
        """User hourly activity distribution. Defaults to command author."""
        m = member or ctx.author
        await self._send_distribution(
            ctx, is_interaction=False,
            scope="user", scope_id=m.id,
            scope_member=m,
        )

    @distribution_group.command(name="category")
    async def dist_category_prefix(self, ctx: commands.Context,
                                   category: discord.CategoryChannel = None):
        """Category hourly activity distribution."""
        cat = category or (
            ctx.channel.category if ctx.channel.category else None)
        if cat is None:
            await ctx.send("❌ Please specify a category or use this command inside a categorised channel.",
                           delete_after=10)
            return
        await self._send_distribution(
            ctx, is_interaction=False,
            scope="category", scope_id=cat.id,
        )

    # ======================================================================
    # SHORTCUT PREFIX COMMANDS
    # ======================================================================

    @commands.command(name="ds")
    async def shortcut_server(self, ctx: commands.Context):
        """Shortcut for `distribution server`."""
        await self._send_distribution(ctx, is_interaction=False, scope="server")

    @commands.command(name="dc")
    async def shortcut_channel(self, ctx: commands.Context,
                               channel: discord.TextChannel = None):
        """Shortcut for `distribution channel`."""
        ch = channel or ctx.channel
        await self._send_distribution(
            ctx, is_interaction=False,
            scope="channel", scope_id=ch.id,
        )

    @commands.command(name="du")
    async def shortcut_user(self, ctx: commands.Context,
                            member: discord.Member = None):
        """Shortcut for `distribution user`."""
        m = member or ctx.author
        await self._send_distribution(
            ctx, is_interaction=False,
            scope="user", scope_id=m.id,
            scope_member=m,
        )

    @commands.command(name="dca")
    async def shortcut_category(self, ctx: commands.Context,
                                category: discord.CategoryChannel = None):
        """Shortcut for `distribution category`."""
        cat = category or (
            ctx.channel.category if ctx.channel.category else None)
        if cat is None:
            await ctx.send("❌ Please specify a category or use this command inside a categorised channel.",
                           delete_after=10)
            return
        await self._send_distribution(
            ctx, is_interaction=False,
            scope="category", scope_id=cat.id,
        )

    # ======================================================================
    # SLASH COMMAND GROUP
    # ======================================================================

    distribution_slash = app_commands.Group(
        name="distribution",
        description="Hourly activity distribution charts.",
    )

    @distribution_slash.command(name="server",
                                description="Server-wide hourly activity distribution.")
    async def slash_dist_server(self, interaction: discord.Interaction):
        await self._send_distribution(interaction, is_interaction=True, scope="server")

    @distribution_slash.command(name="channel",
                                description="Channel hourly activity distribution.")
    @app_commands.describe(channel="The channel to view (defaults to current channel).")
    async def slash_dist_channel(
        self, interaction: discord.Interaction,
        channel: discord.TextChannel = None,
    ):
        ch = channel or interaction.channel
        await self._send_distribution(
            interaction, is_interaction=True,
            scope="channel", scope_id=ch.id,
        )

    @distribution_slash.command(name="user",
                                description="User hourly activity distribution.")
    @app_commands.describe(member="The member to view (defaults to yourself).")
    async def slash_dist_user(
        self, interaction: discord.Interaction,
        member: discord.Member = None,
    ):
        m = member or interaction.user
        # interaction.user is a User not Member when fetched directly; get Member
        if not isinstance(m, discord.Member):
            m = interaction.guild.get_member(m.id) or m
        await self._send_distribution(
            interaction, is_interaction=True,
            scope="user", scope_id=m.id,
            scope_member=m,
        )

    @distribution_slash.command(name="category",
                                description="Category hourly activity distribution.")
    @app_commands.describe(category="The category to view (defaults to current channel's category).")
    async def slash_dist_category(
        self, interaction: discord.Interaction,
        category: discord.CategoryChannel = None,
    ):
        cat = category or (
            interaction.channel.category
            if hasattr(interaction.channel, 'category') else None
        )
        if cat is None:
            await interaction.response.send_message(
                "❌ Please specify a category or run this inside a categorised channel.",
                ephemeral=True)
            return
        await self._send_distribution(
            interaction, is_interaction=True,
            scope="category", scope_id=cat.id,
        )

    # ======================================================================
    # COG UNLOAD
    # ======================================================================

    async def cog_unload(self):
        self.active_sessions.clear()
        print("TimezoneDistribution cog: Cleaned up active sessions")


# ======================================================================
# SETUP
# ======================================================================

async def setup(bot):
    await bot.add_cog(TimezoneDistribution(bot))
