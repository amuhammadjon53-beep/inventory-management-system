import discord
from discord.ext import commands
from discord import Embed
from datetime import datetime, timedelta, timezone
import asyncio
import math


class SlashCommandStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.allowed_users = {591655972414685229, 1428927519515611141}
        self.db_cog = None
        self.active_views = {}

    # =========================================================
    # Load Database cog safely
    # =========================================================
    async def cog_load(self):
        for _ in range(30):
            self.db_cog = self.bot.get_cog("DatabaseStats")
            if self.db_cog:
                break
            await asyncio.sleep(1)

    # =========================================================
    # Permission check for ALL commands in this cog
    # =========================================================
    async def cog_check(self, ctx: commands.Context):
        return ctx.author.id in self.allowed_users

    # =========================================================
    # s!sc  (stats) - With button-based UI
    # =========================================================
    @commands.command(name="sc")
    async def slash_command_stats(self, ctx: commands.Context, days: int = 30):
        """Show global slash command usage stats"""
        try:
            await ctx.message.delete()
        except:
            pass

        if not self.db_cog or not self.db_cog.pool:
            return await ctx.send("❌ Database not available.", delete_after=5)

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)

        embed = await self.create_slash_command_embed(days, page=0)
        if not embed:
            return await ctx.send("❌ No data found.", delete_after=5)

        view = SlashCommandView(
            cog=self,
            current_days=days,
            current_start_time=start,
            current_end_time=end,
            page=0,
            display_text=f"{days} days"
        )

        msg = await ctx.send(embed=embed, view=view)
        view.message = msg
        self.active_views[msg.id] = view

    # =========================================================
    # s!scd  (delete from daily aggregated table)
    # =========================================================
    @commands.command(name="scd")
    async def slash_command_delete_daily(self, ctx: commands.Context, days: int = None):
        """Delete slash command data from daily aggregated table"""
        try:
            await ctx.message.delete()
        except:
            pass

        if not self.db_cog or not self.db_cog.pool:
            return await ctx.send("❌ Database not available.", delete_after=5)

        # Confirmation message
        confirm_msg = await ctx.send(
            f"⚠️ Are you sure you want to delete daily aggregated data "
            + (f"older than **{days} days**?" if days else "**all daily aggregated data**?") +
            "\nType `confirm` within 30 seconds to proceed.",
            delete_after=30
        )

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() == "confirm"

        try:
            await self.bot.wait_for("message", timeout=30, check=check)
        except asyncio.TimeoutError:
            return await ctx.send("❌ Deletion cancelled.", delete_after=5)

        async with self.db_cog.pool.acquire() as conn:
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name='slash_commands_daily'
                )
            """)

            if not table_exists:
                return await ctx.send("⚠️ No `slash_commands_daily` table found.", delete_after=5)

            if days:
                cutoff = datetime.utcnow() - timedelta(days=days)
                deleted_count = await conn.fetchval("""
                    SELECT COUNT(*) FROM slash_commands_daily WHERE day < $1
                """, cutoff)
                await conn.execute("""
                    DELETE FROM slash_commands_daily WHERE day < $1
                """, cutoff)
            else:
                deleted_count = await conn.fetchval("""
                    SELECT COUNT(*) FROM slash_commands_daily
                """)
                await conn.execute("DELETE FROM slash_commands_daily")

        embed = Embed(
            title="✅ Daily Data Deletion Complete",
            description=f"Deleted **{deleted_count:,}** daily records" +
            (f" older than {days} days." if days else "."),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed, delete_after=10)

    # =========================================================
    # s!scs  (summary of both tables)
    # =========================================================
    @commands.command(name="scs")
    async def slash_command_summary(self, ctx: commands.Context):
        """Show summary of slash commands tables"""
        try:
            await ctx.message.delete()
        except:
            pass

        if not self.db_cog or not self.db_cog.pool:
            return await ctx.send("❌ Database not available.", delete_after=5)

        async with self.db_cog.pool.acquire() as conn:

            daily_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name='slash_commands_daily'
                )
            """)

            embed = Embed(
                title="📊 Slash Commands Tables Summary",
                color=discord.Color.blue()
            )

            if daily_exists:
                daily_count = await conn.fetchval("SELECT COUNT(*) FROM slash_commands_daily")
                daily_earliest = await conn.fetchval("SELECT MIN(day) FROM slash_commands_daily")
                daily_latest = await conn.fetchval("SELECT MAX(day) FROM slash_commands_daily")

                total_commands = await conn.fetchval("SELECT SUM(command_count) FROM slash_commands_daily") or 0

                embed.add_field(
                    name="📅 Daily Aggregated (slash_commands_daily)",
                    value=f"**Records:** {daily_count:,}\n"
                    f"**Total Commands:** {total_commands:,}\n"
                    f"**Earliest:** {daily_earliest.strftime('%Y-%m-%d') if daily_earliest else 'N/A'}\n"
                    f"**Latest:** {daily_latest.strftime('%Y-%m-%d') if daily_latest else 'N/A'}",
                    inline=False
                )
            else:
                embed.add_field(name="📅 Daily Aggregated",
                                value="❌ Not found", inline=False)

        await ctx.send(embed=embed, delete_after=30)

    # =========================================================
    # EMBED CREATION - USING DAILY AGGREGATED TABLE
    # =========================================================
    async def create_slash_command_embed(self, days: int, page: int = 0, items_per_page: int = 15,
                                         start_time: datetime = None, end_time: datetime = None) -> Embed:
        if not self.db_cog or not self.db_cog.pool:
            return None

        if start_time is None or end_time is None:
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=days)
        else:
            end = end_time
            start = start_time

        # Calculate effective days for display
        if start and end:
            effective_days = max(1, (end - start).days)
        else:
            effective_days = days

        async with self.db_cog.pool.acquire() as conn:
            # Check if daily table exists
            daily_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name='slash_commands_daily'
                )
            """)

            if daily_exists:
                rows = await conn.fetch("""
                    SELECT command_name, SUM(command_count) AS usage_count
                    FROM slash_commands_daily
                    WHERE day BETWEEN $1 AND $2
                    GROUP BY command_name
                    ORDER BY usage_count DESC
                """, start, end)
            else:
                return None

        if not rows:
            return None

        total_pages = max(1, math.ceil(len(rows) / items_per_page))
        start_idx = page * items_per_page
        page_rows = rows[start_idx:start_idx + items_per_page]

        display_text = f"{effective_days} days"
        if effective_days >= 999999:
            display_text = "All Time"

        embed = Embed(
            title="📊 Global Slash Command Usage",
            description=f"Top commands across all servers ({display_text})",
            color=discord.Color.purple()
        )
        embed.set_footer(text=f"Page {page+1}/{total_pages}")

        for i, row in enumerate(page_rows, start=1):
            embed.add_field(
                name=f"#{start_idx+i} `{row['command_name']}`",
                value=f"**{row['usage_count']:,}** uses",
                inline=False
            )

        total_uses = sum(r["usage_count"] for r in rows)
        embed.add_field(
            name="📈 Total Statistics",
            value=f"**Total Uses:** {total_uses:,}\n**Unique Commands:** {len(rows):,}",
            inline=False
        )

        return embed

    # =========================================================
    # Helper to get total pages
    # =========================================================
    async def get_total_pages(self, days: int = 30, items_per_page: int = 15,
                              start_time: datetime = None, end_time: datetime = None) -> int:
        if not self.db_cog or not self.db_cog.pool:
            return 1

        if start_time is None or end_time is None:
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=days)
        else:
            end = end_time
            start = start_time

        async with self.db_cog.pool.acquire() as conn:
            daily_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name='slash_commands_daily'
                )
            """)

            if daily_exists:
                count = await conn.fetchval("""
                    SELECT COUNT(DISTINCT command_name)
                    FROM slash_commands_daily
                    WHERE day BETWEEN $1 AND $2
                """, start, end)
                return max(1, math.ceil(count / items_per_page))
            return 1


# =========================================================
# TIME MODAL
# =========================================================
class SlashCommandTimeModal(discord.ui.Modal, title='Custom Time Period'):
    def __init__(self, cog_instance, original_message_id):
        super().__init__(timeout=300)
        self.cog = cog_instance
        self.original_message_id = original_message_id

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

            view = self.cog.active_views.get(self.original_message_id)
            if not view:
                await interaction.followup.send("❌ Could not find the stats view. Please try the command again.", ephemeral=True)
                return

            now = datetime.now(timezone.utc)
            view.current_start_time = now - timedelta(days=days)
            view.current_end_time = now
            view.current_days = days
            view.display_text = f"{days} days"
            view.show_time_buttons = False
            view.page = 0

            await view.update_message(interaction)

        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number.", ephemeral=True)


# =========================================================
# PAGE JUMP MODAL
# =========================================================
class SlashPageJumpModal(discord.ui.Modal, title='Jump to Page'):
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


# =========================================================
# BUTTON CLASSES
# =========================================================
class PrevButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            emoji=discord.PartialEmoji(
                name="arrowleft", id=1521149181207777331),
            custom_id="sc_prev"
        )

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
        super().__init__(
            style=discord.ButtonStyle.secondary,
            emoji=discord.PartialEmoji(
                name="arrowright", id=1521149211373076501),
            custom_id="sc_next"
        )

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
    def __init__(self, label="Page 1/1"):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label=label,
            custom_id="sc_page",
            disabled=False
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        total_pages = await view.cog.get_total_pages(
            days=view.current_days,
            start_time=view.current_start_time,
            end_time=view.current_end_time
        )
        modal = SlashPageJumpModal(view, total_pages)
        await interaction.response.send_modal(modal)


# =========================================================
# MAIN VIEW
# =========================================================
class SlashCommandView(discord.ui.View):
    def __init__(self, cog, current_days: int = 30, current_start_time: datetime = None,
                 current_end_time: datetime = None, page: int = 0, display_text: str = "30 days"):
        super().__init__(timeout=600)
        self.cog = cog
        self.message = None
        self.current_days = current_days
        self.current_start_time = current_start_time
        self.current_end_time = current_end_time
        self.page = page
        self.display_text = display_text
        self.show_time_buttons = False
        self._update_buttons()

    def _update_buttons(self):
        self.clear_items()

        # Add prev, page indicator, next buttons
        self.add_item(PrevButton())
        self.add_item(PageIndicator())
        self.add_item(NextButton())

        # Add refresh and time settings buttons (row 4 like reference cog)
        refresh_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=discord.PartialEmoji(name="refresh", id=1518249841505861743),
            custom_id="sc_refresh",
            row=4
        )
        refresh_button.callback = self.refresh_callback

        time_settings_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji=discord.PartialEmoji(name="clockk", id=1518249803069259867),
            custom_id="sc_time_settings",
            row=4
        )
        time_settings_button.callback = self.time_settings_callback

        self.add_item(refresh_button)
        self.add_item(time_settings_button)

        # Time period buttons (shown when toggled)
        if self.show_time_buttons:
            row = 5
            # All Time button
            all_time_button = discord.ui.Button(
                style=discord.ButtonStyle.primary if self.current_days >= 999999 else discord.ButtonStyle.secondary,
                label="All Time",
                custom_id="sc_all_time",
                row=row
            )
            all_time_button.callback = self.all_time_callback
            self.add_item(all_time_button)

            # 7, 14, 30 days buttons
            for days in [7, 14, 30]:
                days_button = discord.ui.Button(
                    style=discord.ButtonStyle.primary if self.current_days == days else discord.ButtonStyle.secondary,
                    label=f"{days} Days",
                    custom_id=f"sc_days_{days}",
                    row=row
                )
                days_button.callback = self.create_days_callback(days)
                self.add_item(days_button)

            # Custom button
            is_custom = self.current_days not in [7, 14, 30, 999999]
            custom_button = discord.ui.Button(
                style=discord.ButtonStyle.success if is_custom else discord.ButtonStyle.secondary,
                label=f"Custom ({self.current_days}d)" if is_custom else "Custom",
                custom_id="sc_custom_days",
                row=row
            )
            custom_button.callback = self.custom_days_callback
            self.add_item(custom_button)

    def create_days_callback(self, days: int):
        async def callback(interaction: discord.Interaction):
            now = datetime.now(timezone.utc)
            await self.handle_time_period_change(
                interaction, days, now -
                timedelta(days=days), now, f"{days} days"
            )
        return callback

    async def all_time_callback(self, interaction: discord.Interaction):
        now = datetime.now(timezone.utc)
        await self.handle_time_period_change(
            interaction, 999999, None, now, "All Time"
        )

    async def refresh_callback(self, interaction: discord.Interaction):
        if interaction.response.is_done():
            return
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False, thinking=False)
        await self.update_message(interaction)

    async def time_settings_callback(self, interaction: discord.Interaction):
        if interaction.response.is_done():
            return
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False, thinking=False)
        self.show_time_buttons = not self.show_time_buttons
        self._update_buttons()
        await interaction.edit_original_response(view=self)

    async def custom_days_callback(self, interaction: discord.Interaction):
        modal = SlashCommandTimeModal(self.cog, interaction.message.id)
        await interaction.response.send_modal(modal)

    async def handle_time_period_change(self, interaction: discord.Interaction, days: int,
                                        start_time: datetime, end_time: datetime, display_text: str):
        if interaction.response.is_done():
            return
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=False, thinking=False)
        self.current_days = days
        self.current_start_time = start_time
        self.current_end_time = end_time
        self.display_text = display_text
        self.show_time_buttons = False
        self.page = 0
        await self.update_message(interaction)

    async def update_message(self, interaction: discord.Interaction):
        try:
            embed = await self.cog.create_slash_command_embed(
                days=self.current_days,
                page=self.page,
                start_time=self.current_start_time,
                end_time=self.current_end_time
            )

            if not embed:
                embed = discord.Embed(
                    title="📊 Global Slash Command Usage",
                    description="No data available for this time period.",
                    color=discord.Color.purple()
                )

            total_pages = await self.cog.get_total_pages(
                days=self.current_days,
                start_time=self.current_start_time,
                end_time=self.current_end_time
            )

            # Update page indicator and disable/enable prev/next
            for child in self.children:
                if isinstance(child, PageIndicator):
                    child.label = f"Page {self.page + 1}/{total_pages}"
                elif isinstance(child, PrevButton):
                    child.disabled = (self.page == 0 or total_pages <= 1)
                elif isinstance(child, NextButton):
                    child.disabled = (
                        self.page >= total_pages - 1 or total_pages <= 1)

            self._update_buttons()

            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed, view=self)
            else:
                await interaction.response.edit_message(embed=embed, view=self)

        except Exception as e:
            import traceback
            traceback.print_exc()
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ An error occurred while updating.", ephemeral=True)
                else:
                    await interaction.followup.send("❌ An error occurred while updating.", ephemeral=True)
            except:
                pass


async def setup(bot):
    await bot.add_cog(SlashCommandStats(bot))
