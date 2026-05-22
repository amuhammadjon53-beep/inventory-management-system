import discord
from discord.ext import commands
from discord import Embed
from datetime import datetime, timedelta
import asyncio
import math


class SlashCommandStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.allowed_users = {591655972414685229, 1428927519515611141}
        self.db_cog = None

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
    # s!sc  (stats) - NOW USING DAILY AGGREGATED TABLE
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

        embed = await self.create_slash_command_embed(days)
        if not embed:
            return await ctx.send("❌ No data found.", delete_after=5)

        msg = await ctx.send(embed=embed, delete_after=300)
        await self.add_pagination(msg, days)

    # =========================================================
    # s!scdd  (delete from daily aggregated table)
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
    async def create_slash_command_embed(self, days: int, page: int = 0, items_per_page: int = 15) -> Embed:
        if not self.db_cog or not self.db_cog.pool:
            return None

        end = datetime.utcnow()
        start = end - timedelta(days=days)

        async with self.db_cog.pool.acquire() as conn:
            # Check if daily table exists, fallback to raw if not
            daily_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name='slash_commands_daily'
                )
            """)

            if daily_exists:
                # Use daily aggregated table
                rows = await conn.fetch("""
                    SELECT command_name, SUM(command_count) AS usage_count
                    FROM slash_commands_daily
                    WHERE day BETWEEN $1 AND $2
                    GROUP BY command_name
                    ORDER BY usage_count DESC
                """, start, end)

        if not rows:
            return None

        total_pages = max(1, math.ceil(len(rows) / items_per_page))
        start_idx = page * items_per_page
        page_rows = rows[start_idx:start_idx + items_per_page]

        embed = Embed(
            title="📊 Global Slash Command Usage",
            description=f"Top commands across all servers ({days} days)",
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
    # PAGINATION
    # =========================================================
    async def add_pagination(self, message: discord.Message, days: int, current_page: int = 0):
        await message.add_reaction("⬅️")
        await message.add_reaction("➡️")
        await message.add_reaction("❌")

        def check(r, u):
            return u.id in self.allowed_users and r.message.id == message.id and str(r.emoji) in ["⬅️", "➡️", "❌"]

        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=300, check=check)
                emoji = str(reaction.emoji)

                if emoji == "❌":
                    return await message.delete()

                new_page = current_page + (1 if emoji == "➡️" else -1)
                embed = await self.create_slash_command_embed(days, new_page)
                if embed:
                    await message.edit(embed=embed)
                    current_page = new_page

                await reaction.remove(user)
            except asyncio.TimeoutError:
                await message.clear_reactions()
                break


async def setup(bot):
    await bot.add_cog(SlashCommandStats(bot))
