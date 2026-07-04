import discord
import time
from discord.ext import commands
from .ratelimiter import RateLimiter, RateLimitType, rate_limited, get_rate_limiter

ALLOWED_DIAG_USERS = {591655972414685229, 1428927519515611141}


class Diagnostics(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_stats = None

    async def cog_load(self):
        self.db_stats = self.bot.get_cog("DatabaseStats")

    # =========================================================
    # Permission check for ALL commands in this cog
    # =========================================================
    async def cog_check(self, ctx: commands.Context):
        return ctx.author.id in ALLOWED_DIAG_USERS

    async def cog_command_error(self, ctx, error):
        # Swallow CheckFailure (unauthorized users) silently — no response, no traceback noise.
        if isinstance(error, commands.CheckFailure):
            return
        raise error

    @commands.command(name="diag")
    async def diag(self, ctx):
        try:
            await ctx.message.delete()
        except:
            pass

        latency_ms = round(self.bot.latency * 1000, 2)
        guild_count = len(self.bot.guilds)
        total_users = sum(g.member_count for g in self.bot.guilds)

        top_guilds = sorted(
            self.bot.guilds, key=lambda g: g.member_count, reverse=True)[:100]
        top_guilds_str = "\n".join(
            f"{i+1}. {g.name} — {g.member_count:,}" for i, g in enumerate(top_guilds[:20])
        ) or "None"
        # only first 20 shown inline (embed field limit); full 100 sent as a file if needed

        pool_size = pool_idle = pool_active = "N/A"
        if self.db_stats and self.db_stats.pool:
            pool_size = self.db_stats.pool.get_size()
            pool_idle = self.db_stats.pool.get_idle_size()
            pool_active = pool_size - pool_idle

        rl_stats = get_rate_limiter().get_stats()
        rl_summary = "\n".join(
            f"{k}: {v['total']} total, {v['limited']} limited, {v['timeout']} timeout"
            for k, v in rl_stats.items()
        ) or "No data yet"

        embed = discord.Embed(title="StatsHQ Bot Diagnostics",
                              color=discord.Color.blurple())
        embed.add_field(name="Latency", value=f"{latency_ms} ms", inline=True)
        embed.add_field(name="Guilds", value=f"{guild_count:,}", inline=True)
        embed.add_field(name="Total Users",
                        value=f"{total_users:,}", inline=True)
        embed.add_field(
            name="DB Pool", value=f"{pool_active}/{pool_size} active, {pool_idle} idle", inline=True)
        embed.add_field(name="Top 20 Guilds (of 100)",
                        value=top_guilds_str[:1024], inline=False)
        embed.add_field(name="Rate Limiter (bot process)",
                        value=rl_summary[:1024], inline=False)

        await ctx.send(embed=embed)

        # Full top 100 as a text file since embeds can't hold that much
        if len(top_guilds) > 20:
            lines = "\n".join(
                f"{i+1}. {g.name} ({g.id}) — {g.member_count:,}" for i, g in enumerate(top_guilds))
            import io
            file = discord.File(io.StringIO(
                lines), filename="top_100_guilds.txt")
            await ctx.send(file=file)


async def setup(bot):
    await bot.add_cog(Diagnostics(bot))
