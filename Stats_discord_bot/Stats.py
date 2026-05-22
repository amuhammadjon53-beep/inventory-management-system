import asyncio
import asyncpg
import os
from dotenv import load_dotenv
import logging
import discord
from discord.ext import commands
import sys
import traceback
from datetime import datetime, timezone

# =========================================================
# ENV
# =========================================================
load_dotenv()
token = os.getenv("DISCORD_TOKEN")
api_host = os.getenv("API_HOST", "0.0.0.0")
api_port = int(os.getenv("API_PORT", 8000))

logging.basicConfig(level=logging.INFO)

# =========================================================
# INTENTS
# =========================================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.messages = True
intents.guilds = True
intents.voice_states = True
intents.presences = True
intents.invites = True

# =========================================================
# PREFIX SYSTEM
# =========================================================


async def get_prefix(bot, message):
    default = "s!"
    db = bot.get_cog("DatabaseStats")

    if not message.guild or not db or not db.pool:
        return default

    try:
        async with db.pool.acquire() as conn:
            prefix = await conn.fetchval(
                "SELECT prefix FROM settings WHERE guild_id = $1",
                message.guild.id
            )
            return prefix or default
    except Exception:
        return default

# =========================================================
# BOT
# =========================================================
bot = commands.Bot(
    command_prefix=get_prefix,
    case_insensitive=True,
    strip_after_prefix=True,
    intents=intents,
    help_command=None
)

guild_id = 1424021358680998022
pool = None
api_thread = None

# =========================================================
# READY
# =========================================================


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

    global pool, api_thread

    # Set bot activity
    activity = discord.Activity(
        type=discord.ActivityType.watching,
        name="/help | statshq.xyz"
    )
    await bot.change_presence(activity=activity)
    print(f"🎮 Set bot activity to: Watching /help | statshq.xyz")

    # Database connection
    try:
        pool = await asyncpg.create_pool(
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT"),
            min_size=1,
            max_size=10
        )

        bot.pool = pool
        print("✅ PostgreSQL connection pool created")
        # ========================================

    except Exception as e:
        print(f"❌ Failed to connect to PostgreSQL: {e}")
        bot.pool = None

    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f"🔄 Synced {len(synced)} commands globally")

        guild = discord.Object(id=guild_id)
        await bot.tree.sync(guild=guild)
        print(f"🔄 Synced commands to guild ID: {guild_id}")

    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")
        # ==========================================


# =========================================================
# LOAD COGS
# =========================================================


async def load_cogs():
    """Load all cogs from the cogs directory"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    cogs_path = os.path.join(current_dir, "cogs")

    # Check if cogs directory exists
    if not os.path.exists(cogs_path):
        print(f"⚠️ Cogs directory not found: {cogs_path}")
        return

    # Load all .py files in cogs directory
    for filename in os.listdir(cogs_path):
        if filename.endswith(".py") and filename != "__init__.py":
            try:
                await bot.load_extension(f"cogs.{filename[:-3]}")
                print(f"✅ Loaded cog: {filename}")
            except Exception as e:
                print(f"❌ Failed to load cog {filename}: {e}")

# =========================================================
# SHUTDOWN HANDLER
# =========================================================


@bot.event
async def on_disconnect():
    print("⚠️ Bot disconnected from Discord")

# =========================================================
# MAIN ENTRY POINT
# =========================================================


async def main():
    """Main entry point"""
    print(f"Python: {sys.version.split()[0]}")
    print(f"Discord.py: {discord.__version__}")
    print("=" * 60)

    # Load cogs
    await load_cogs()

    # Start the bot
    try:
        await bot.start(token)
    except KeyboardInterrupt:
        print("\n🛑 Received keyboard interrupt, shutting down...")
    except Exception as e:
        print(f"❌ Bot crashed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n👋 Bot shutting down...")
        # Close database connection
        if bot.pool:
            await bot.pool.close()
            print("✅ Database connection closed")
        print("✅ Shutdown complete")

if __name__ == "__main__":
    # Run the bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
