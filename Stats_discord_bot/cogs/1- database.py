from exceptions import (
    DatabaseConnectionError, DatabaseQueryError, DatabaseTransactionError,
    DatabaseIntegrityError, DatabaseTimeoutError,
    CacheConnectionError, CacheReadFailed, CacheWriteFailed,
    CacheDeleteFailed, CacheBatchFailed, CacheKeyNotFound,
    CacheTimeoutError, CacheSerializationError
)
import asyncio
import aiohttp
import json
import os
import copy
import time
import uuid
from zoneinfo import ZoneInfo
import datetime as dt
from datetime import datetime, timedelta, date, timezone  # ← REMOVED ", time"
from typing import Dict, List, Optional, Tuple, Any, Set, Union
from collections import defaultdict
import discord
from discord.ext import commands, tasks
import asyncpg
import redis
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError, RedisError
from cryptography.fernet import Fernet
import pytz
from dotenv import load_dotenv
import matplotlib.pyplot as plt
import io
import numpy as np
import hashlib
import re
from asyncio import Semaphore
import emoji
import unicodedata
from emoji import is_emoji
import base64
import sys
import os
from pathlib import Path
import aiocron
from .ratelimiter import RateLimiter, RateLimitType, rate_limited, get_rate_limiter


root_dir = Path(__file__).parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))


load_dotenv()


# Constants

class Constants:
    # Redis batching settings
    REDIS_BATCH_FLUSH_INTERVAL = 30
    REDIS_BATCH_MAX_SIZE = 1000

    # Voice tracking
    VOICE_TRACKER_INTERVAL = 60

    # INFINITE RECONNECTION
    RECONNECT_BASE_DELAY = 1.0
    RECONNECT_MAX_DELAY = 300.0
    RECONNECT_MAX_ATTEMPTS = 0

    # HIGH OPERATION RETRIES
    DB_RETRY_ATTEMPTS = 10
    DB_RETRY_BASE_DELAY = 0.5
    DB_RETRY_MAX_DELAY = 30.0
    REDIS_RETRY_ATTEMPTS = 5
    REDIS_RETRY_DELAY = 0.1

    # Health check
    CONNECTION_POOL_HEALTH_CHECK_INTERVAL = 300
    SHUTDOWN_TIMEOUT = 30

    # TimescaleDB settings
    HYPERTABLE_CHUNK_TIME_INTERVAL = '7 days'
    COMPRESSION_SEGMENT_BY = 'guild_id'
    COMPRESSION_ORDER_BY = 'created_at DESC, id'
    COMPRESSION_AFTER_DAYS = {
        'message_tracking_hourly': 30,
        'voice_session_history_hourly': 60,
        'emoji_usage_hourly': 90,
        'invite_tracking': 90,
        'user_mentions_hourly': 60,
        'activity_sessions_hourly': 30,
        'activities': 30,
        'role_growth_hourly': 30,
        'member_joins_hourly': 30,
        'member_leaves_hourly': 30,
        'slash_commands_daily': 90
    }
    RETENTION_DAYS = {
        'message_tracking_hourly': 365,
        'voice_session_history_hourly': 365,
        'emoji_usage_hourly': 365,
        'invite_tracking': 365,
        'user_mentions_hourly': 365,
        'activity_sessions_hourly': 365,
        'activities': 365,
        'role_growth_hourly': 365,
        'member_joins_hourly': 365,
        'member_leaves_hourly': 365,
        'slash_commands_daily': 365
    }

    EMPTY_VOICE_RESULT = {
        'total_seconds': 0, 'total_hours': 0.0, 'session_count': 0,
        'avg_session': 0.0, 'first_session': None, 'last_session': None
    }

    EMPTY_SERVER_VOICE_RESULT = {
        'total_seconds': 0, 'total_hours': 0.0, 'session_count': 0,
        'unique_users': 0, 'avg_session': 0.0, 'seconds_per_user': 0.0
    }


def ensure_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Convert naive datetime to aware UTC datetime."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class DatabaseStats(commands.Cog):

    def __init__(self, bot: commands.Bot):
        print("=" * 50)
        print("DATABASE STATS COG LOADED - VERSION WITH ENCRYPTED_USERNAME FIX")
        print("=" * 50)
        self.bot = bot
        self.pool: Optional[asyncpg.Pool] = None
        self.redis: Optional[Redis] = None
        self.fernet: Optional[Fernet] = None
        print(
            f"✅ Fernet initialized successfully, self.fernet = {self.fernet is not None}")

        self.EMPTY_VOICE_RESULT = Constants.EMPTY_VOICE_RESULT
        self.EMPTY_SERVER_VOICE_RESULT = Constants.EMPTY_SERVER_VOICE_RESULT

        # Async locks for thread safety
        self.voice_lock = asyncio.Lock()
        self.reconnect_lock = asyncio.Lock()
        self.shutdown_lock = asyncio.Lock()
        self.metrics_lock = asyncio.Lock()

        self.timescale_lock = asyncio.Lock()
        self.redis_batch_lock = asyncio.Lock()

        self.invite_snapshot_locks: Dict[int, asyncio.Lock] = {}
        self.invite_snapshots: Dict[int, dict] = {}

        # State tracking
        self.shutting_down = False
        self.reconnect_attempts = 0
        self.db_connected = False
        self.redis_connected = False

        self.is_timescale_initialized = False
        self.processed_messages: Dict[str, datetime] = {}
        self.invite_locks: Dict[int, asyncio.Lock] = {}
        self.rate_limits: Dict[str, list] = {}
        self.rate_limiter = get_rate_limiter()

        # Role members cache
        self.role_members_cache: Dict[str, Tuple[datetime, List[int]]] = {}

        # Start cleanup tasks
        self.cleanup_task = None

        # (timestamp, success)
        self.recent_operations: List[Tuple[float, bool]] = []
        self.total_operations_last_minute = 0
        self.failed_operations_last_minute = 0

        # Voice session tracking
        self.active_voice_sessions: Dict[int, Dict[str, Any]] = {}
        self.connection_semaphore = Semaphore(20)

        # Voice state flags mapping
        self.voice_state_bits = {
            'afk_channel': 1 << 0,
            'server_mute': 1 << 1,
            'server_deaf': 1 << 2,
            'self_mute': 1 << 3,
            'self_deaf': 1 << 4,
            'streaming': 1 << 5,
            'video': 1 << 6,
            'suppressed': 1 << 7,
        }

        # Redis write batching system - unchanged structure, only SQL changes
        self.redis_batches: Dict[str, List[Dict[str, Any]]] = {
            'messages': [],
            'voice_sessions': [],
            'mentions': [],
            'emojis': [],
            'invites': [],
            'activities': [],
            'activity_active': [],
            'slash_commands': [],
            'role_growth': [],
            'member_joins': [],
            'member_leaves': [],
            'role_members': []
        }
        self.batch_sizes = {key: 0 for key in self.redis_batches.keys()}
        self.last_flush_time = time.time()

        # Metrics
        self.metrics = {
            'redis_writes': 0,
            'redis_batch_flushes': 0,
            'voice_updates': 0,
            'message_inserts': 0,
            'emoji_inserts': 0,
            'invite_inserts': 0,
            'mention_inserts': 0,
            'slash_command_inserts': 0,
            'role_growth_inserts': 0,
            'member_join_inserts': 0,
            'member_leave_inserts': 0,
            'errors': 0,

            'db_queries': 0,
            'active_voice_sessions': 0,
            'connection_retries': 0,
            'failed_operations': 0,
            'timescale_compression_ratio': 0.0,
            'hypertable_sizes': {},
            'chunk_count': 0,
            'redis_batch_sizes': self.batch_sizes.copy()
        }

        # Start tasks
        self.init_pools.start()
        self.voice_activity_tracker.start()
        self.connection_pool_health_check.start()

        self.metrics_reset_task.start()

        self.redis_batch_flusher.start()
        self.cleanup_task = asyncio.create_task(self._periodic_cleanup())
        self.is_running = True
        self.channel_sync_cron = aiocron.crontab(
            '0 9 * * *', func=self.daily_channel_sync_task, tz=ZoneInfo('UTC'))
        self.guild_check_cron = aiocron.crontab(
            '0 3 * * *', func=self.sync_user_servers_on_ready, tz=ZoneInfo('UTC'))
        self.permission_sync_cron = aiocron.crontab(
            '0 6,14,22 * * *', func=self.sync_user_permissions, tz=ZoneInfo('UTC'))
        self.role_filter_sync_cron = aiocron.crontab(
            # 18:00 UTC daily
            '0 18 * * *', func=self.sync_role_memberships_for_filtering, tz=ZoneInfo('UTC'))
        self.streak_update_cron = aiocron.crontab(
            # 00:00 UTC daily
            '0 0 * * *', func=self.update_activity_streaks, tz=ZoneInfo('UTC'))
        self.server_count_cron = aiocron.crontab(
            '0 */3 * * *', func=self.send_server_count_message, tz=ZoneInfo('UTC'))
        self.reset_schedule_cron = aiocron.crontab(
            '0 */12 * * *', func=self.check_and_execute_scheduled_resets, tz=ZoneInfo('UTC'))

        print("✅ Scheduled tasks: Channel sync at 09:00, Guild scan at 03:00, Permission scan at 06:00/14:00/22:00 UTC, Role filter sync at 18:00 UTC, Activity streak update at 00:00 UTC, Server count message every 3 hours, Reset schedule checker every 12 hours")

    async def check_and_execute_scheduled_resets(self):
        """Check for due reset schedules and execute them - runs every 12 hours."""
        try:
            # Get the ResetStats cog
            reset_cog = self.bot.get_cog('ResetStats')
            if not reset_cog:
                print("⚠️ ResetStats cog not found - cannot check scheduled resets")
                return

            # Check if the cog has the required method
            if hasattr(reset_cog, 'check_and_execute_scheduled_resets'):
                await reset_cog.check_and_execute_scheduled_resets()
                print(
                    f"✅ Scheduled reset check completed at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
            else:
                print(
                    "⚠️ ResetStats cog does not have check_and_execute_scheduled_resets method")

        except Exception as e:
            print(f"❌ Error in scheduled reset check: {e}")
            import traceback
            traceback.print_exc()

    async def send_server_count_message(self):
        """Send a message with the total server count and total users every 3 hours, and update bot lists."""
        try:
            # Wait for bot to be ready
            if not self.bot.is_ready():
                print("⏳ Bot not ready yet, waiting before sending server count...")
                await self.bot.wait_until_ready()

            target_guild_id = 1456950849094811726
            target_channel_id = 1500165234583933151

            # Get total server count from bot's cache
            total_servers = len(self.bot.guilds)

            # Get total users from database (sum latest member_count from all guilds)
            total_users = 0

            if self.pool and self.db_connected:
                try:
                    async with self.pool.acquire() as conn:
                        total_users_result = await conn.fetchval("""
                            SELECT COALESCE(SUM(member_count), 0)
                            FROM (
                                SELECT DISTINCT ON (guild_id) guild_id, member_count
                                FROM server_member_counts
                                ORDER BY guild_id, recorded_at DESC
                            ) AS latest_counts
                        """)
                        total_users = total_users_result or 0
                        print(
                            f"📊 Database user total: {total_users:,} users across {total_servers} servers")
                except Exception as e:
                    print(f"⚠️ Could not get total users from database: {e}")
                    total_users = sum(guild.member_count or len(
                        guild.members) for guild in self.bot.guilds)
                    print(f"📊 Fallback user total: {total_users:,} users")
            else:
                total_users = sum(guild.member_count or len(
                    guild.members) for guild in self.bot.guilds)
                print(
                    f"📊 Using cache - Users: {total_users:,}, Servers: {total_servers}")

            # Get the target guild and channel for the embed message
            guild = self.bot.get_guild(target_guild_id)
            if not guild:
                print(f"❌ Could not find guild with ID {target_guild_id}")
                return

            channel = guild.get_channel(target_channel_id)
            if not channel:
                print(
                    f"❌ Could not find channel with ID {target_channel_id} in guild {guild.name}")
                return

            if not isinstance(channel, discord.TextChannel):
                print(f"❌ Channel {target_channel_id} is not a text channel")
                return

            # Acquire rate limit for message sending
            if not await self.rate_limiter.acquire(RateLimitType.MESSAGE, timeout=30.0):
                print(
                    "⚠️ Rate limit timeout for server count message, will retry next cycle")
                return

            # Get current timestamp in UTC
            current_time = datetime.now(
                timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')

            # Create the embed
            embed = discord.Embed(
                title="📊 Bot Statistics",
                description=f"**Total Servers:** {total_servers:,}\n**Total Users:** {total_users:,}",
                color=discord.Color.from_rgb(170, 0, 255),
                timestamp=datetime.now(timezone.utc)
            )

            embed.add_field(name="🕐 Reported At",
                            value=current_time, inline=True)
            embed.add_field(name="🤖 Bot Status", value="Online" if self.bot.is_ready(
            ) else "Offline", inline=True)

            if total_servers > 0:
                avg_users = total_users / total_servers
                embed.add_field(name="📈 Avg Users/Server",
                                value=f"{avg_users:.1f}", inline=True)

            embed.set_footer(text="StatsHQ • Server Count Update")

            await channel.send(embed=embed)
            print(
                f"📊 Sent server count message: {total_servers:,} servers, {total_users:,} users reported at {current_time}")

            # =========================================================
            # UPDATE TOP.GG
            # =========================================================
            topgg_token = os.getenv('TOPGG_TOKEN')
            if topgg_token and total_servers > 0:
                try:
                    async with aiohttp.ClientSession() as session:
                        bot_id = self.bot.user.id
                        url = f"https://top.gg/api/bots/{bot_id}/stats"
                        payload = {"server_count": total_servers}
                        if self.bot.shard_count:
                            payload["shard_count"] = self.bot.shard_count
                        headers = {"Authorization": topgg_token,
                                   "Content-Type": "application/json"}
                        async with session.post(url, json=payload, headers=headers) as response:
                            if response.status == 200:
                                print(
                                    f"✅ Successfully updated Top.gg with {total_servers} servers")
                            else:
                                response_text = await response.text()
                                print(
                                    f"⚠️ Top.gg update failed with status {response.status}: {response_text}")
                except aiohttp.ClientError as e:
                    print(f"❌ Network error updating Top.gg: {e}")
                except Exception as e:
                    print(f"❌ Error updating Top.gg: {e}")
            elif not topgg_token:
                print("⚠️ TOPGG_TOKEN not found - skipping Top.gg update")

            # =========================================================
            # UPDATE DISCORD BOT LIST (discordbotlist.com)
            # =========================================================
            discord_bot_list_token = os.getenv('DISCORD_BOT_LIST_TOKEN')
            if discord_bot_list_token and total_servers > 0:
                try:
                    async with aiohttp.ClientSession() as session:
                        bot_id = self.bot.user.id
                        url = f"https://discordbotlist.com/api/v1/bots/{bot_id}/stats"
                        payload = {"guilds": total_servers}
                        if self.bot.shard_count:
                            payload["shards"] = self.bot.shard_count
                        headers = {"Authorization": discord_bot_list_token,
                                   "Content-Type": "application/json"}
                        async with session.post(url, json=payload, headers=headers) as response:
                            if response.status == 200:
                                print(
                                    f"✅ Successfully updated Discord Bot List with {total_servers} servers")
                            else:
                                response_text = await response.text()
                                print(
                                    f"⚠️ Discord Bot List update failed with status {response.status}: {response_text}")
                except aiohttp.ClientError as e:
                    print(f"❌ Network error updating Discord Bot List: {e}")
                except Exception as e:
                    print(f"❌ Error updating Discord Bot List: {e}")
            elif not discord_bot_list_token:
                print(
                    "⚠️ DISCORD_BOT_LIST_TOKEN not found - skipping Discord Bot List update")

            # =========================================================
            # UPDATE DISCORDS.COM
            # =========================================================
            discords_token = os.getenv('DISCORDS_TOKEN')
            if discords_token and total_servers > 0:
                print("🔄 Attempting to update Discords.com...")
                await self._update_discords_com(bot_id, total_servers, discords_token)

        except discord.Forbidden:
            print(
                f"❌ Missing permissions to send message to channel {target_channel_id}")
        except discord.HTTPException as e:
            print(
                f"❌ Discord HTTP error sending server count message: {e.status}")
        except Exception as e:
            print(f"❌ Error sending server count message: {e}")
            import traceback
            traceback.print_exc()

    async def _update_discords_com(self, bot_id: int, total_servers: int, token: str):
        """
        Attempts to update server count on discords.com by trying both
        common authentication methods for bot list APIs.
        """
        # The correct endpoint as per our last discussion
        url = f"https://discords.com/api/bot/{bot_id}/stats"
        payload = {"server_count": total_servers}
        if self.bot.shard_count:
            payload["shard_count"] = self.bot.shard_count

        # Define the two auth methods to try
        auth_methods = {
            "Bot Token": {"Authorization": f"Bot {token}"},
            "Bearer Token": {"Authorization": f"Bearer {token}"}
        }

        for method_name, headers in auth_methods.items():
            headers["Content-Type"] = "application/json"
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload, headers=headers) as response:
                        if response.status == 200:
                            print(
                                f"✅ Discords.com update successful using '{method_name}'!")
                            print(f"   Server count: {total_servers}")
                            return  # Success, we can exit the function
                        else:
                            # Log the failure for this specific method
                            print(
                                f"⚠️ Discords.com attempt with '{method_name}' failed (HTTP {response.status}).")
                            # Optionally read response text for debugging, but limit length
                            # response_text = await response.text()
                            # print(f"   Response: {response_text[:200]}")
            except aiohttp.ClientError as e:
                print(
                    f"❌ Network error during Discords.com update ({method_name}): {e}")
            except Exception as e:
                print(
                    f"❌ Unexpected error during Discords.com update ({method_name}): {e}")

        # If we've tried all methods and none worked:
        print("❌ All Discords.com authentication methods failed.")
        print("   Please verify your DISCORDS_TOKEN in the .env file.")

    async def sync_all_guilds_channels_sharded(self):
        """Sync channels for all guilds with sharded approach and rate limiting."""
        if not self.pool or not self.db_connected:
            print("❌ Cannot sync channels - database not connected")
            return 0

        guilds = self.bot.guilds
        total_guilds = len(guilds)

        if total_guilds == 0:
            print("⚠️ No guilds found to sync")
            return 0

        print(f"\n📡 SYNCING CHANNELS FOR {total_guilds} GUILDS")
        print("-" * 50)

        success_count = 0
        failed_count = 0
        total_channels_synced = 0

        for idx, guild in enumerate(guilds, 1):
            try:
                # ✅ Rate limit BEFORE each guild's API calls
                if not await self.rate_limiter.acquire(RateLimitType.API, timeout=30.0):
                    print(f"  ⚠️ Rate limited for {guild.name}, waiting...")
                    await asyncio.sleep(5)
                    continue

                print(
                    f"  [{idx}/{total_guilds}] Syncing channels for: {guild.name}")

                # Rate limit: 0.5 seconds between guilds to be gentle to Discord API
                if idx > 1:
                    await asyncio.sleep(0.5)

                synced = await self.sync_guild_channels(guild)

                if synced > 0:
                    success_count += 1
                    total_channels_synced += synced
                    print(f"    ✅ Synced {synced} channels/categories")
                else:
                    failed_count += 1
                    print(f"    ⚠️ No channels synced (check bot permissions)")

            except discord.Forbidden:
                failed_count += 1
                print(f"    ❌ Permission denied")
            except discord.HTTPException as e:
                failed_count += 1
                print(f"    ❌ Discord API error: {e.status}")
            except Exception as e:
                failed_count += 1
                print(f"    ❌ Unexpected error: {type(e).__name__}: {e}")

        print(
            f"\n✅ Channel sync complete: {success_count} succeeded, {failed_count} failed")
        print(f"📊 Total channels/categories synced: {total_channels_synced}")
        return success_count

    async def _sync_guild_role_memberships(self, guild: discord.Guild):
        """Actually sync role memberships for a single guild with role names and colors."""
        if not self.pool or not self.db_connected:
            print(f"  ❌ Cannot sync roles - database not connected")
            return 0

        try:
            # ✅ Rate limit BEFORE Discord API calls
            if not await self.rate_limiter.acquire(RateLimitType.API, timeout=30.0):
                print(f"  ⚠️ Rate limited for {guild.name}, waiting...")
                await asyncio.sleep(5)
                return 0

            # Rate limit: be gentle to Discord API
            await asyncio.sleep(0.1)

            members = guild.members
            if not members:
                print(f"  ⚠️ No members found in {guild.name}")
                return 0

            current_time = datetime.now(timezone.utc)
            synced_count = 0

            # Step 1: Clear ALL existing role memberships for this guild
            async with self.pool.acquire() as conn:
                result = await conn.execute("""
                    DELETE FROM current_role_members 
                    WHERE guild_id = $1
                """, guild.id)
                print(f"    Cleared existing role memberships")

            # Step 2: Insert current role memberships for all members
            for member in members:
                # Skip bots if you want (optional - set to False if you want to track bots)
                if member.bot:
                    continue

                # Get non-default roles for this member
                non_default_roles = [
                    role for role in member.roles if not role.is_default()]

                if not non_default_roles:
                    continue

                # Batch write each role membership with role name and color
                for role in non_default_roles:
                    await self.redis_batch_write('role_members', {
                        'params': [
                            guild.id,           # guild_id
                            member.id,          # user_id
                            role.id,            # role_id
                            role.name,          # role_name (ADDED)
                            role.color.value,   # role_color (ADDED)
                            current_time,       # updated_at
                            member.bot          # is_bot
                        ]
                    })
                    synced_count += 1

                # Small delay to prevent overwhelming the system
                if synced_count % 100 == 0:
                    await asyncio.sleep(0.01)

            # Step 3: Flush all batched role memberships to database
            if synced_count > 0:
                await self._flush_batch_to_postgresql('role_members')
                print(
                    f"    ✅ Synced {synced_count} role memberships for {guild.name}")
            else:
                print(f"    ⚠️ No role memberships to sync for {guild.name}")

            return synced_count

        except discord.Forbidden:
            print(f"    ❌ Permission denied for {guild.name}")
            return 0
        except discord.HTTPException as e:
            print(f"    ❌ Discord API error for {guild.name}: {e.status}")
            return 0
        except Exception as e:
            print(
                f"    ❌ Error syncing role memberships for {guild.name}: {e}")
            import traceback
            traceback.print_exc()
            return 0
    # FIXED: Use the correct pool reference

    # Remove @rate_limited decorator from this function
    async def sync_guild_channels(self, guild: discord.Guild):
        """Sync all channels and categories for a guild to the discord_channels table"""
        if not self.pool or not guild:
            return 0

        try:
            # Create rate limiter for Discord API calls

            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    # First, mark all existing channels for this guild as potentially deleted
                    await conn.execute("""
                        UPDATE discord_channels 
                        SET is_deleted = TRUE, last_synced = NOW()
                        WHERE guild_id = $1
                    """, guild.id)

                    synced_count = 0

                    # Process each channel in the guild
                    for channel in guild.channels:

                        # Determine channel type
                        if isinstance(channel, discord.CategoryChannel):
                            channel_type = 'category'
                            category_id = None
                        elif isinstance(channel, discord.TextChannel):
                            channel_type = 'text'
                            category_id = channel.category.id if channel.category else None
                        elif isinstance(channel, discord.VoiceChannel):
                            channel_type = 'voice'
                            category_id = channel.category.id if channel.category else None
                        elif isinstance(channel, discord.StageChannel):
                            channel_type = 'stage'
                            category_id = channel.category.id if channel.category else None
                        elif isinstance(channel, discord.ForumChannel):
                            channel_type = 'forum'
                            category_id = channel.category.id if channel.category else None
                        else:
                            continue

                        await conn.execute("""
                            INSERT INTO discord_channels (
                                guild_id, channel_id, channel_name, channel_type, 
                                category_id, is_deleted, last_synced, created_at
                            ) VALUES ($1, $2, $3, $4, $5, FALSE, NOW(), NOW())
                            ON CONFLICT (channel_id) DO UPDATE SET
                                guild_id = EXCLUDED.guild_id,
                                channel_name = EXCLUDED.channel_name,
                                channel_type = EXCLUDED.channel_type,
                                category_id = EXCLUDED.category_id,
                                is_deleted = FALSE,
                                last_synced = NOW()
                            WHERE discord_channels.guild_id = EXCLUDED.guild_id
                        """,
                                           guild.id,
                                           channel.id,
                                           channel.name,
                                           channel_type,
                                           category_id
                                           )
                        synced_count += 1

                    print(
                        f"✅ Synced {synced_count} channels/categories for guild {guild.name}")
                    return synced_count

        except Exception as e:
            print(f"❌ Error syncing channels for guild {guild.name}: {e}")
            import traceback
            traceback.print_exc()
            return 0

    async def sync_role_memberships_for_filtering(self):
        """Sync role memberships for all guilds (for role filtering)."""
        if not self.db_connected or not self.pool:
            print("Role filter sync skipped - database not connected")
            return

        print(f"\n{'='*60}")
        print(
            f"🔄 Starting role membership sync at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"{'='*60}")

        guilds = self.bot.guilds
        total_guilds = len(guilds)

        # Clear role members cache
        self.role_members_cache.clear()

        success_count = 0
        for idx, guild in enumerate(guilds, 1):
            try:
                # ✅ Rate limit BEFORE each guild's API calls
                if not await self.rate_limiter.acquire(RateLimitType.API, timeout=30.0):
                    print(f"  ⚠️ Rate limited for {guild.name}, waiting...")
                    await asyncio.sleep(5)
                    continue

                print(
                    f"  [{idx}/{total_guilds}] Syncing role memberships for: {guild.name}")
                await self._sync_guild_role_memberships(guild)
                success_count += 1
                await asyncio.sleep(0.1)  # Small delay between guilds
            except Exception as e:
                print(
                    f"  ❌ Failed to sync role memberships for {guild.name}: {e}")

        print(
            f"\n✅ Role membership sync completed: {success_count}/{total_guilds} guilds synced")
        print(f"{'='*60}\n")

    async def update_activity_streaks(self):
        """Update activity streaks for all users (uses ActivityTracker cog)."""
        print(f"\n{'='*60}")
        print(
            f"🔄 Updating activity streaks at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"{'='*60}")

        # Get the ActivityTracker cog
        activity_cog = self.bot.get_cog('ActivityTracker')
        if not activity_cog:
            print("❌ ActivityTracker cog not found - cannot update streaks")
            return

        try:
            if hasattr(activity_cog, 'db') and activity_cog.db:
                # Use the ActivityTracker's streak update method
                await activity_cog.db.update_all_streaks()
                print("✅ Activity streaks updated successfully")
            else:
                print("❌ ActivityTracker database not initialized")
        except Exception as e:
            print(f"❌ Error updating activity streaks: {e}")
            import traceback
            traceback.print_exc()

        print(f"{'='*60}\n")

    async def startup_sync_all_guilds(self):
        """Run all sync operations sequentially at startup."""
        if not self.pool or not self.db_connected:
            print("❌ Database not connected - cannot run startup sync")
            return

        # Wait for bot to be ready with proper error handling
        try:
            # Check if bot has the required attributes
            if not hasattr(self.bot, 'wait_until_ready'):
                print("❌ Bot not fully initialized yet - will retry later")
                asyncio.create_task(self._retry_startup_sync())
                return

            await self.bot.wait_until_ready()
        except RuntimeError:
            print("⚠️ Starting startup sync in 60 seconds")
            asyncio.create_task(self._retry_startup_sync())
            return

        # Give it an extra moment for guilds to populate
        await asyncio.sleep(5)

        # Double-check we have guilds
        if len(self.bot.guilds) == 0:
            print("⚠️ No guilds found after waiting - will retry later")
            asyncio.create_task(self._retry_startup_sync())
            return

        guilds = self.bot.guilds
        total_guilds = len(guilds)

        print(f"\n{'='*60}")
        print(f"🚀 STARTING COMPLETE STARTUP SYNC FOR {total_guilds} GUILDS")
        print(f"{'='*60}")
        print(
            f"⏰ Started at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"{'='*60}\n")

        # STEP 1: CHANNEL SYNC
        print("📋 STEP 1/4: SYNCING CHANNELS")
        print("-" * 40)
        # This now has internal rate limiting
        await self.sync_all_guilds_channels_sharded()
        print(f"\n✅ Channel sync complete\n")

        # STEP 2: PERMISSION SYNC
        print("📋 STEP 2/4: SYNCING PERMISSIONS")
        print("-" * 40)
        await self.sync_user_permissions()  # Remove decorator from this too
        print(f"\n✅ Permission sync complete\n")

        # STEP 3: ROLE MEMBERSHIP SYNC
        print("📋 STEP 3/4: SYNCING ROLE MEMBERSHIPS")
        print("-" * 40)

        for idx, guild in enumerate(guilds, 1):
            # ✅ Rate limit before each guild
            if not await self.rate_limiter.acquire(RateLimitType.API, timeout=30.0):
                print(f"  ⚠️ Rate limited for {guild.name}, waiting...")
                await asyncio.sleep(5)
                continue

            print(
                f"  [{idx}/{total_guilds}] Syncing role memberships for: {guild.name}")
            await self._sync_guild_role_memberships(guild)
            await asyncio.sleep(0.1)

        print(f"\n✅ Role membership sync complete\n")

        # STEP 4: VOICE SESSION SCAN
        print("📋 STEP 4/4: SCANNING ACTIVE VOICE SESSIONS")
        print("-" * 40)
        # This doesn't need rate limiting (no API calls)
        await self.scan_active_voice_sessions()
        print(f"\n✅ Voice session scan complete\n")

        print(f"\n{'='*60}")
        print(f"🎉 STARTUP SYNC COMPLETE!")
        print(f"{'='*60}")
        print(
            f"⏰ Finished at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"{'='*60}\n")

    async def _retry_startup_sync(self):
        """Retry startup sync if it failed due to bot not being ready."""
        # ✅ This function just calls startup_sync_all_guilds
        # No direct API calls, so remove the decorator

        # Wait longer for bot to initialize
        await asyncio.sleep(30)

        try:
            if self.bot.is_ready():
                print("🔄 Starting Startup Sync")
                await self.startup_sync_all_guilds()
            else:
                print("⚠️ Startup sync will start in 60 seconds")
                await asyncio.sleep(60)
                if self.bot.is_ready():
                    await self.startup_sync_all_guilds()
                else:
                    print("❌ Bot never became ready - startup sync skipped")
        except Exception as e:
            print(f"❌ Retry failed: {e}")

    async def scan_active_voice_sessions(self):
        """Scan all guilds for currently active voice sessions at startup."""
        # ✅ This function doesn't make Discord API calls
        # It just reads from cached bot.guilds and bot.guilds.members
        # Remove the decorator

        if not self.bot.is_ready():
            print("⏳ Bot not ready yet, waiting before voice scan...")
            await self.bot.wait_until_ready()

        print("\n" + "="*60)
        print("🎙️ SCANNING FOR ACTIVE VOICE SESSIONS")
        print("="*60)

        current_time = datetime.now(timezone.utc)
        sessions_found = 0

        async with self.voice_lock:
            self.active_voice_sessions.clear()

            for guild in self.bot.guilds:
                for member in guild.members:
                    if member.bot:
                        continue

                    if member.voice and member.voice.channel:
                        channel = member.voice.channel
                        category_id = None
                        if hasattr(channel, 'category_id') and channel.category_id:
                            category_id = channel.category_id

                        self.active_voice_sessions[member.id] = {
                            'guild_id': guild.id,
                            'user_id': member.id,
                            'channel_id': channel.id,
                            'category_id': category_id,
                            'server_mute': member.voice.mute,
                            'server_deaf': member.voice.deaf,
                            'self_mute': member.voice.self_mute,
                            'self_deaf': member.voice.self_deaf,
                            'streaming': member.voice.self_stream,
                            'video': member.voice.self_video,
                            'suppressed': member.voice.suppress,
                            'is_afk_channel': getattr(channel, 'afk_channel', False),
                            'join_time': current_time,
                            'last_join_time': current_time,
                            'last_activity': current_time,
                            'last_minute_tracked': current_time,
                            'is_bot': member.bot
                        }
                        sessions_found += 1

            print(
                f"✅ Found {sessions_found} active voice sessions across {len(self.bot.guilds)} guilds")
            print(
                f"   {len(self.active_voice_sessions)} users currently in voice channels")

        return sessions_found

    async def scan_guild_voice_sessions(self, guild: discord.Guild) -> int:
        """Scan a specific guild for currently active voice sessions and start tracking them."""
        # ✅ This function doesn't make Discord API calls
        # It reads from cached guild.members
        # Remove the decorator

        if not self.pool or not self.db_connected:
            print(
                f"⚠️ Cannot scan voice sessions for {guild.name} - database not connected")
            return 0

        print(f"\n🎙️ SCANNING VOICE SESSIONS FOR GUILD: {guild.name}")

        current_time = datetime.now(timezone.utc)
        sessions_found = 0

        async with self.voice_lock:
            for member in guild.members:
                if member.bot:
                    continue

                if member.voice and member.voice.channel:
                    channel = member.voice.channel
                    category_id = None
                    if hasattr(channel, 'category_id') and channel.category_id:
                        category_id = channel.category_id

                    # Check if we're already tracking this user
                    if member.id in self.active_voice_sessions:
                        # Update existing session
                        self.active_voice_sessions[member.id].update({
                            'guild_id': guild.id,
                            'user_id': member.id,
                            'channel_id': channel.id,
                            'category_id': category_id,
                            'server_mute': member.voice.mute,
                            'server_deaf': member.voice.deaf,
                            'self_mute': member.voice.self_mute,
                            'self_deaf': member.voice.self_deaf,
                            'streaming': member.voice.self_stream,
                            'video': member.voice.self_video,
                            'suppressed': member.voice.suppress,
                            'is_afk_channel': getattr(channel, 'afk_channel', False),
                            'last_activity': current_time,
                        })
                    else:
                        # Start new session
                        self.active_voice_sessions[member.id] = {
                            'guild_id': guild.id,
                            'user_id': member.id,
                            'channel_id': channel.id,
                            'category_id': category_id,
                            'server_mute': member.voice.mute,
                            'server_deaf': member.voice.deaf,
                            'self_mute': member.voice.self_mute,
                            'self_deaf': member.voice.self_deaf,
                            'streaming': member.voice.self_stream,
                            'video': member.voice.self_video,
                            'suppressed': member.voice.suppress,
                            'is_afk_channel': getattr(channel, 'afk_channel', False),
                            'join_time': current_time,
                            'last_join_time': current_time,
                            'last_activity': current_time,
                            'last_minute_tracked': current_time,
                            'is_bot': member.bot
                        }

                    sessions_found += 1

        print(
            f"✅ Found {sessions_found} active voice sessions in guild {guild.name}")
        return sessions_found
    # ======================================================================
    # HELPER: Get users with roles from current_role_members table
    # ======================================================================

    async def _get_users_with_roles(self, guild_id: int, role_ids: Optional[List[int]] = None) -> Optional[List[int]]:
        """
        Get all user IDs that have at least one of the specified roles from the current_role_members table.
        Returns None if no role filter is provided (meaning no filtering).
        """
        if not role_ids:
            return None

        # Check cache
        cache_key = f"role_members:{guild_id}:{','.join(sorted(str(rid) for rid in role_ids))}"
        if hasattr(self, 'role_members_cache') and cache_key in self.role_members_cache:
            cache_time, user_ids = self.role_members_cache[cache_key]
            if (datetime.now(timezone.utc) - cache_time).total_seconds() < 300:  # 5 minute cache
                return user_ids

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
                user_ids = [row['user_id'] for row in rows]

                # Cache the result
                if not hasattr(self, 'role_members_cache'):
                    self.role_members_cache = {}
                self.role_members_cache[cache_key] = (
                    datetime.now(timezone.utc), user_ids)

                return user_ids

        except Exception as e:
            # 👇 ADD ERROR LOGGING
            print(f"Error getting users with roles for guild {guild_id}: {e}")
            return []

    async def _get_all_role_members(self, guild_id: int) -> Dict[int, List[int]]:
        """Get all role memberships for a guild at once.
        Returns a dictionary mapping role_id -> list of user_ids."""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch('''
                    SELECT role_id, user_id
                    FROM current_role_members
                    WHERE guild_id = $1
                ''', guild_id)

                role_members = defaultdict(list)
                for row in rows:
                    role_members[row['role_id']].append(row['user_id'])

                return dict(role_members)
        except Exception as e:
            print(f"Error fetching all role members for guild {guild_id}: {e}")
            return {}

    # ======================================================================
    # BUFFERING METHODS - UNCHANGED
    # ======================================================================

    async def buffer_event(self, event_type: str, guild_id: int, data: Dict[str, Any]):
        """Buffer an event for batch processing."""
        if event_type == 'emoji':
            await self._buffer_emoji_event(guild_id, data)
        elif event_type == 'invite':
            await self._buffer_invite_event(
                guild_id=guild_id,
                inviter_id=data.get('inviter_id', 0),
                invitee_id=data.get('invitee_id'),
                invite_code=data.get('invite_code', 'unknown'),
                invite_type=data.get('invite_type', 'valid')
            )
        elif event_type == 'message':
            message = data.get('message')
            if message:
                await self._track_message_content(message)
        else:
            # Don't raise error for unknown event types - just ignore
            pass

    async def decrypt_single_username(self, guild_id: int, user_id: int) -> str:
        """
        Decrypt a single username by trying all tables.
        """
        username = await self.get_decrypted_username_any_table(guild_id, user_id)
        return username or f"User {user_id}"

    async def decrypt_username_batch(self, guild_id: int, user_ids: List[int]) -> Dict[int, str]:
        """
        Decrypt usernames for a list of users by trying all tables.
        Returns a dictionary mapping user_id -> decrypted username.
        """
        if not user_ids:
            return {}

        # Try messages table first (most common)
        result = await self.batch_get_decrypted_usernames_from_messages(guild_id, user_ids)

        # Check which users are still missing
        missing_users = [uid for uid in user_ids if result.get(
            uid, '').startswith('User ')]

        if missing_users:
            # Try voice table
            voice_results = await self.batch_get_decrypted_usernames_any_table(guild_id, missing_users, 'voice')
            for uid, username in voice_results.items():
                if username and not username.startswith('User '):
                    result[uid] = username

            # Check again for remaining missing
            missing_users = [uid for uid in user_ids if result.get(
                uid, '').startswith('User ')]

            if missing_users:
                # Try emojis table
                emoji_results = await self.batch_get_decrypted_usernames_any_table(guild_id, missing_users, 'emojis')
                for uid, username in emoji_results.items():
                    if username and not username.startswith('User '):
                        result[uid] = username

                # Continue with other tables if needed...
                missing_users = [uid for uid in user_ids if result.get(
                    uid, '').startswith('User ')]

                if missing_users:
                    # Try activity table
                    activity_results = await self.batch_get_decrypted_usernames_any_table(guild_id, missing_users, 'activity')
                    for uid, username in activity_results.items():
                        if username and not username.startswith('User '):
                            result[uid] = username

        return result

    # ======================================================================
    # BLACKLIST CHECKING METHODS - FIXED EXCEPTION HANDLING AND NONE RETURN
    # ======================================================================

    async def _get_cached_blacklists(self, guild_id: int) -> Dict[str, Set[int]]:
        """Get blacklists from database - ALWAYS returns a dictionary, never None."""
        # Start with empty box at the VERY beginning (this NEVER changes)
        blacklists = {
            'users': set(),
            'channels': set(),
            'categories': set(),
            'roles': set()
        }

        # If no database connection, return the empty box
        if not self.pool or not self.db_connected:
            return blacklists  # 📦 empty box

        try:
            async with self.connection_semaphore:
                async with self.pool.acquire() as conn:
                    # Try to get users - if it fails, we keep the empty set
                    try:
                        rows = await conn.fetch('''
                            SELECT user_id FROM blacklisted_users 
                            WHERE guild_id = $1
                        ''', guild_id)
                        blacklists['users'] = {row['user_id'] for row in rows}
                    except Exception as e:
                        print(
                            f"Couldn't get blacklisted users for {guild_id}: {e}")
                        # blacklists['users'] is STILL an empty set from above

                    # Try to get channels
                    try:
                        rows = await conn.fetch('''
                            SELECT channel_id FROM blacklisted_channels 
                            WHERE guild_id = $1
                        ''', guild_id)
                        blacklists['channels'] = {
                            row['channel_id'] for row in rows}
                    except Exception as e:
                        print(
                            f"Couldn't get blacklisted channels for {guild_id}: {e}")

                    # Try to get categories
                    try:
                        rows = await conn.fetch('''
                            SELECT category_id FROM blacklisted_categories 
                            WHERE guild_id = $1
                        ''', guild_id)
                        blacklists['categories'] = {
                            row['category_id'] for row in rows}
                    except Exception as e:
                        print(
                            f"Couldn't get blacklisted categories for {guild_id}: {e}")

                    # Try to get roles
                    try:
                        rows = await conn.fetch('''
                            SELECT role_id FROM blacklisted_roles 
                            WHERE guild_id = $1
                        ''', guild_id)
                        blacklists['roles'] = {row['role_id'] for row in rows}
                    except Exception as e:
                        print(
                            f"Couldn't get blacklisted roles for {guild_id}: {e}")

        except Exception as e:
            # BIG error? Server on fire? Internet down?
            # We STILL return our empty box!
            print(f"Major error in _get_cached_blacklists for {guild_id}: {e}")

        # 👇 ADD THIS MISSING RETURN
        return blacklists  # 📦 Could be empty, but it's ALWAYS a box!

    async def is_user_or_roles_blacklisted(self, guild_id: int, user_id: int) -> bool:
        """Check if user or their roles are blacklisted."""
        if not self.pool or not self.db_connected:
            return False

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return False

        try:
            # This ALWAYS gives us a dictionary now!
            blacklists = await self._get_cached_blacklists(guild_id)

            # Safe to check because blacklists is ALWAYS a dict with all keys
            if user_id in blacklists['users']:  # ✅ This will NEVER crash!
                return True

            member = guild.get_member(user_id)
            if member and blacklists['roles']:
                user_role_ids = {role.id for role in member.roles}
                if user_role_ids.intersection(blacklists['roles']):
                    return True

            return False

        except Exception as e:
            # If ANYTHING goes wrong, assume not blacklisted (better safe than sorry)
            print(
                f"Error checking blacklist for user {user_id} in guild {guild_id}: {e}")
            return False

    async def _is_user_blacklisted(self, guild_id: int, user_id: int) -> bool:
        """Check if specific user is blacklisted."""
        try:
            # This ALWAYS gives us a dictionary!
            blacklists = await self._get_cached_blacklists(guild_id)
            # Safe to check because blacklists is ALWAYS a dict
            return user_id in blacklists['users']  # ✅ Safe!
        except Exception as e:
            # If anything breaks, assume not blacklisted
            print(f"Error checking if user {user_id} is blacklisted: {e}")
            return False

    # ======================================================================
    # CLEANUP TASKS
    # ======================================================================

    async def _periodic_cleanup(self):
        """Periodic cleanup task - runs every 30 minutes."""
        while not self.shutting_down:
            try:
                # Run cleanup every 30 minutes (1800 seconds)
                await asyncio.sleep(1800)
                await self._cleanup_old_data()
                # Clean role members cache (separate, also every 30 min)
                await self._cleanup_role_cache()
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Don't raise during cleanup - just log and continue
                print(f"Error in periodic cleanup: {e}")
                continue

    async def _cleanup_old_data(self):
        """Clean up old data from memory caches with size limits and TTL enforcement."""
        try:
            current_time = datetime.now(timezone.utc)

            # ==================================================================
            # 1. CLEANUP PROCESSED MESSAGES (deduplication cache)
            # ==================================================================
            # Remove messages older than 1 hour
            expired_keys = []
            for key, timestamp in self.processed_messages.items():
                if (current_time - timestamp).total_seconds() > 3600:  # 1 hour TTL
                    expired_keys.append(key)

            for key in expired_keys:
                if key in self.processed_messages:  # Safety check
                    del self.processed_messages[key]

            # Enforce maximum size (prevent memory bloat on high-traffic servers)
            MAX_PROCESSED_MESSAGES = 10000
            if len(self.processed_messages) > MAX_PROCESSED_MESSAGES:
                # Remove oldest 20% when too large
                sorted_items = sorted(
                    self.processed_messages.items(), key=lambda x: x[1])
                to_remove = int(len(sorted_items) * 0.2)
                for key, _ in sorted_items[:to_remove]:
                    if key in self.processed_messages:  # Check if still exists
                        del self.processed_messages[key]
                print(
                    f"🧹 Cleaned processed_messages: removed {to_remove} oldest entries, now {len(self.processed_messages)}")

            # ==================================================================
            # 2. CLEANUP RATE LIMITS (most critical - can grow huge)
            # ==================================================================
            MAX_RATE_LIMIT_KEYS = 50000  # Maximum keys to keep
            expired_rate_limits = []

            # First pass: remove expired timestamps and identify empty keys
            for key, timestamps in list(self.rate_limits.items()):
                # Filter timestamps older than 1 hour
                filtered = [ts for ts in timestamps
                            if (current_time - ts).total_seconds() < 3600]

                if filtered:
                    self.rate_limits[key] = filtered
                else:
                    # No valid timestamps left, mark for deletion
                    expired_rate_limits.append(key)

            # Remove empty keys
            for key in expired_rate_limits:
                if key in self.rate_limits:
                    del self.rate_limits[key]

            # Second pass: enforce maximum size using LRU-like strategy
            if len(self.rate_limits) > MAX_RATE_LIMIT_KEYS:
                # Sort keys by their most recent activity (newest first)
                # For each key, get the latest timestamp (or datetime.min if empty)
                sorted_keys = sorted(
                    self.rate_limits.keys(),
                    key=lambda k: max(self.rate_limits[k]) if self.rate_limits[k] else datetime.min.replace(
                        tzinfo=timezone.utc),
                    reverse=True
                )

                # Keep most recent 80%, delete oldest 20%
                keys_to_keep_count = int(MAX_RATE_LIMIT_KEYS * 0.8)
                keys_to_keep = set(sorted_keys[:keys_to_keep_count])

                removed_count = 0
                for key in list(self.rate_limits.keys()):
                    if key not in keys_to_keep:
                        del self.rate_limits[key]
                        removed_count += 1

                print(
                    f"🧹 Cleaned rate_limits: removed {removed_count} least active keys, now {len(self.rate_limits)} keys")

            # ==================================================================
            # 3. CLEANUP STALE INVITE SNAPSHOTS (guilds bot has left)
            # ==================================================================
            try:
                current_guild_ids = {guild.id for guild in self.bot.guilds}
                stale_snapshots = []

                # Find snapshots for guilds the bot is no longer in
                for guild_id in list(self.invite_snapshots.keys()):
                    if guild_id not in current_guild_ids:
                        stale_snapshots.append(guild_id)

                # Also check for snapshots older than 24 hours (safety net)
                current_time = datetime.now(timezone.utc)
                for guild_id, snapshot in list(self.invite_snapshots.items()):
                    snapshot_time = snapshot.get('timestamp')
                    # 24 hours
                    if snapshot_time and (current_time - snapshot_time).total_seconds() > 86400:
                        if guild_id not in stale_snapshots:
                            stale_snapshots.append(guild_id)

                # Remove stale snapshots
                for guild_id in stale_snapshots:
                    if guild_id in self.invite_snapshots:
                        del self.invite_snapshots[guild_id]
                        print(
                            f"🧹 Removed stale invite snapshot for guild {guild_id}")

                # Also clean up locks for guilds no longer in snapshots
                for guild_id in list(self.invite_snapshot_locks.keys()):
                    if guild_id not in self.invite_snapshots:
                        lock = self.invite_snapshot_locks.get(guild_id)
                        if lock and not lock.locked():
                            del self.invite_snapshot_locks[guild_id]

            except Exception as e:
                print(f"Error cleaning up invite snapshots: {e}")

            # ==================================================================
            # 4. CLEANUP ORPHANED VOICE SESSIONS
            # ==================================================================
            async with self.voice_lock:
                expired_sessions = []
                for user_id in list(self.active_voice_sessions.keys()):
                    user_found = False
                    for guild in self.bot.guilds:
                        if guild.get_member(user_id):
                            user_found = True
                            break

                    # Also cleanup sessions older than 24 hours (safety net)
                    session = self.active_voice_sessions.get(user_id)
                    if session and not user_found:
                        expired_sessions.append(user_id)
                    elif session:
                        join_time = session.get('join_time')
                        # 24 hours
                        if join_time and (current_time - join_time).total_seconds() > 86400:
                            expired_sessions.append(user_id)

                for user_id in expired_sessions:
                    if user_id in self.active_voice_sessions:
                        del self.active_voice_sessions[user_id]

                if expired_sessions:
                    print(
                        f"🧹 Cleaned voice sessions: removed {len(expired_sessions)} orphaned/expired sessions")

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist during cleanup",
                context={'operation': '_cleanup_old_data'},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed during cleanup",
                context={'operation': '_cleanup_old_data'},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out during cleanup",
                context={'operation': '_cleanup_old_data'},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error during cleanup",
                context={'operation': '_cleanup_old_data'},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error during cleanup",
                    context={'operation': '_cleanup_old_data'},
                    original=e
                )
            raise

    async def _cleanup_role_cache(self):
        """Clean up old role members cache entries (TTL: 5 minutes)."""
        try:
            current_time = datetime.now(timezone.utc)
            expired_keys = []

            for key, (cache_time, _) in self.role_members_cache.items():
                if (current_time - cache_time).total_seconds() > 300:  # 5 minutes
                    expired_keys.append(key)

            # Also enforce max size on role cache as safety
            MAX_ROLE_CACHE_ENTRIES = 5000
            for key in expired_keys:
                if key in self.role_members_cache:
                    del self.role_members_cache[key]

            # If still too large, remove oldest entries
            if len(self.role_members_cache) > MAX_ROLE_CACHE_ENTRIES:
                sorted_items = sorted(
                    self.role_members_cache.items(),
                    key=lambda x: x[1][0]  # Sort by cache_time
                )
                to_remove = len(sorted_items) - MAX_ROLE_CACHE_ENTRIES
                for key, _ in sorted_items[:to_remove]:
                    if key in self.role_members_cache:
                        del self.role_members_cache[key]
                print(
                    f"🧹 Cleaned role cache: removed {to_remove} oldest entries, now {len(self.role_members_cache)}")
            elif expired_keys:
                print(
                    f"🧹 Cleaned role cache: removed {len(expired_keys)} expired entries")

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist during role cache cleanup",
                context={'operation': '_cleanup_role_cache'},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed during role cache cleanup",
                context={'operation': '_cleanup_role_cache'},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out during role cache cleanup",
                context={'operation': '_cleanup_role_cache'},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error during role cache cleanup",
                context={'operation': '_cleanup_role_cache'},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error during role cache cleanup",
                    context={'operation': '_cleanup_role_cache'},
                    original=e
                )
            raise

    # ======================================================================
    # REDIS WRITE BATCH SYSTEM
    # ======================================================================

    async def redis_batch_write(self, batch_type: str, data: Dict[str, Any]):
        """Write data to Redis batch queue or directly to PostgreSQL if Redis unavailable."""

        if not self.redis or not self.redis_connected:
            await self._write_direct_to_postgresql(batch_type, data)
            return

        try:
            should_flush = False
            async with self.redis_batch_lock:
                if batch_type not in self.redis_batches:
                    return

                self.redis_batches[batch_type].append(data)
                self.batch_sizes[batch_type] = len(
                    self.redis_batches[batch_type])

                async with self.metrics_lock:
                    self.metrics['redis_writes'] += 1
                    self.metrics['redis_batch_sizes'][batch_type] = self.batch_sizes[batch_type]

                if self.batch_sizes[batch_type] >= Constants.REDIS_BATCH_MAX_SIZE:
                    should_flush = True

            if should_flush:
                await self._flush_batch_to_postgresql(batch_type)

        except RedisConnectionError as e:
            raise CacheConnectionError(
                "Redis connection failed during batch write",
                context={
                    'batch_type': batch_type,
                    'batch_size': len(self.redis_batches.get(batch_type, []))
                },
                original=e
            )
        except RedisTimeoutError as e:
            raise CacheTimeoutError(
                "Redis operation timed out during batch write",
                context={
                    'batch_type': batch_type,
                    'batch_size': len(self.redis_batches.get(batch_type, []))
                },
                original=e
            )
        except RedisError as e:
            raise CacheReadFailed(
                "Redis write failed during batching",
                context={
                    'batch_type': batch_type,
                    'batch_size': len(self.redis_batches.get(batch_type, []))
                },
                original=e
            )

    async def _write_direct_to_postgresql(self, batch_type: str, data: Dict[str, Any]) -> bool:
        """Write directly to PostgreSQL when Redis is unavailable.
        Now uses aggregated tables with ON CONFLICT."""
        if not self.pool:
            return False

        try:
            async with self.pool.acquire() as conn:
                if batch_type == 'messages':
                    params = data['params']
                    if len(params) >= 12:
                        guild_id = params[0]
                        user_id = params[1]
                        channel_id = params[2] or 0
                        category_id = params[3]
                        message_id = params[4]
                        encrypted_username = params[5]
                        message_length = params[6] or 0
                        mentions = params[7]
                        has_attachment = bool(params[8])
                        has_embed = bool(params[9])
                        created_at = ensure_aware(params[10])
                        is_bot = bool(params[11])

                        hour = ensure_aware(created_at.replace(
                            minute=0, second=0, microsecond=0))

                        try:
                            await conn.execute('''
                                INSERT INTO message_tracking_hourly 
                                (hour, guild_id, user_id, channel_id, category_id, message_count,
                                total_chars, attachment_count, embed_count, is_bot, encrypted_username)
                                VALUES ($1, $2, $3, $4, $5, 1, $6, $7, $8, $9, $10)
                                ON CONFLICT (guild_id, user_id, channel_id, hour) 
                                DO UPDATE SET 
                                    message_count = message_tracking_hourly.message_count + 1,
                                    total_chars = message_tracking_hourly.total_chars + $6,
                                    attachment_count = message_tracking_hourly.attachment_count + $7,
                                    embed_count = message_tracking_hourly.embed_count + $8,
                                    encrypted_username = COALESCE(
                                        message_tracking_hourly.encrypted_username, EXCLUDED.encrypted_username
                                    )
                            ''', hour, guild_id, user_id, channel_id, category_id,
                                               message_length,
                                               1 if has_attachment else 0,
                                               1 if has_embed else 0,
                                               is_bot,
                                               encrypted_username)
                        except asyncpg.exceptions.PostgresError as e:
                            raise DatabaseQueryError(
                                "Failed to insert into message_tracking_hourly",
                                context={'batch_type': batch_type},
                                original=e
                            )

                elif batch_type == 'voice_sessions':
                    params = data['params']
                    if len(params) >= 16:
                        guild_id = params[0]
                        user_id = params[1]
                        channel_id = params[2] or 0
                        category_id = params[3]
                        encrypted_username = params[4]
                        join_time = ensure_aware(params[5])
                        leave_time = ensure_aware(params[6])
                        duration_seconds = params[7] or 0
                        state_flags = params[8] or 0
                        state_category = params[9]
                        was_muted = 1 if params[10] else 0
                        was_deafened = 1 if params[11] else 0
                        was_streaming = 1 if params[12] else 0
                        was_video = 1 if params[13] else 0
                        is_bot = params[14] if isinstance(params[14], bool) else bool(
                            params[14]) if params[14] else False
                        hour = ensure_aware(params[15]) if len(params) > 15 else ensure_aware(join_time.replace(
                            minute=0, second=0, microsecond=0))

                        try:
                            await conn.execute('''
                                INSERT INTO voice_session_history_hourly 
                                (hour, guild_id, user_id, channel_id, category_id,
                                total_seconds, session_count, state_flags,
                                was_muted_count, was_deafened_count, was_streaming_count, was_video_count,
                                is_bot, encrypted_username)
                                VALUES ($1, $2, $3, $4, $5, $6, 1, $7, $8, $9, $10, $11, $12, $13)
                                ON CONFLICT (guild_id, user_id, channel_id, hour, state_flags) 
                                DO UPDATE SET 
                                    total_seconds = voice_session_history_hourly.total_seconds + $6,
                                    session_count = voice_session_history_hourly.session_count + 1,
                                    was_muted_count = voice_session_history_hourly.was_muted_count + $8,
                                    was_deafened_count = voice_session_history_hourly.was_deafened_count + $9,
                                    was_streaming_count = voice_session_history_hourly.was_streaming_count + $10,
                                    was_video_count = voice_session_history_hourly.was_video_count + $11,
                                    encrypted_username = COALESCE(
                                        voice_session_history_hourly.encrypted_username, EXCLUDED.encrypted_username
                                    )
                            ''', hour, guild_id, user_id, channel_id, category_id,
                                               duration_seconds, state_flags,
                                               was_muted, was_deafened, was_streaming, was_video,
                                               is_bot, encrypted_username)
                        except asyncpg.exceptions.PostgresError as e:
                            raise DatabaseQueryError(
                                "Failed to insert into voice_session_history_hourly",
                                context={'batch_type': batch_type},
                                original=e
                            )

                elif batch_type == 'mentions':
                    params = data['params']
                    if len(params) >= 10:
                        guild_id = params[0]
                        mentioned_user_id = params[1]
                        mentioner_user_id = params[2]
                        channel_id = params[3] or 0
                        category_id = params[4]
                        message_id = params[5]
                        created_at = ensure_aware(params[6])
                        encrypted_username = params[7]
                        is_bot = bool(params[8])
                        encrypted_mentioned_username = params[9]

                        hour = ensure_aware(created_at.replace(
                            minute=0, second=0, microsecond=0))

                        try:
                            await conn.execute('''
                                INSERT INTO user_mentions_hourly 
                                (hour, guild_id, mentioned_user_id, mentioner_user_id,
                                channel_id, category_id, mention_count, is_bot,
                                encrypted_username, encrypted_mentioned_username)
                                VALUES ($1, $2, $3, $4, $5, $6, 1, $7, $8, $9)
                                ON CONFLICT (guild_id, mentioned_user_id, mentioner_user_id, channel_id, hour) 
                                DO UPDATE SET 
                                    mention_count = user_mentions_hourly.mention_count + 1,
                                    encrypted_username = COALESCE(
                                        user_mentions_hourly.encrypted_username, EXCLUDED.encrypted_username
                                    ),
                                    encrypted_mentioned_username = COALESCE(
                                        user_mentions_hourly.encrypted_mentioned_username, EXCLUDED.encrypted_mentioned_username
                                    )
                            ''', hour, guild_id, mentioned_user_id, mentioner_user_id,
                                               channel_id, category_id, is_bot, encrypted_username, encrypted_mentioned_username)
                        except asyncpg.exceptions.PostgresError as e:
                            raise DatabaseQueryError(
                                "Failed to insert into user_mentions_hourly",
                                context={'batch_type': batch_type},
                                original=e
                            )

                elif batch_type == 'emojis':
                    params = data['params']
                    if len(params) >= 11:
                        guild_id = params[0]
                        user_id = params[1]
                        channel_id = params[2] or 0
                        category_id = params[3]
                        encrypted_username = params[4]
                        emoji_str = params[5]
                        is_custom = bool(params[6])
                        usage_count = params[7] or 1
                        last_used = ensure_aware(params[8])
                        usage_type = params[9]
                        is_bot = bool(params[10])

                        hour = ensure_aware(last_used.replace(
                            minute=0, second=0, microsecond=0))

                        try:
                            await conn.execute('''
                                INSERT INTO emoji_usage_hourly 
                                (hour, guild_id, user_id, channel_id, category_id,
                                emoji_str, is_custom, usage_count, usage_type, is_bot, encrypted_username)
                                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                                ON CONFLICT (guild_id, user_id, channel_id, emoji_str, usage_type, hour) 
                                DO UPDATE SET 
                                    usage_count = emoji_usage_hourly.usage_count + $8,
                                    encrypted_username = COALESCE(
                                        emoji_usage_hourly.encrypted_username, EXCLUDED.encrypted_username
                                    )
                            ''', hour, guild_id, user_id, channel_id, category_id,
                                               emoji_str, is_custom, usage_count, usage_type, is_bot, encrypted_username)
                        except asyncpg.exceptions.PostgresError as e:
                            raise DatabaseQueryError(
                                "Failed to insert into emoji_usage_hourly",
                                context={'batch_type': batch_type},
                                original=e
                            )

                elif batch_type == 'slash_commands':
                    params = data['params']
                    if len(params) >= 8:
                        guild_id = params[0]
                        command_name = params[2]
                        channel_id = params[3] or 0
                        category_id = params[4]
                        created_at = ensure_aware(params[5])
                        encrypted_username = params[6]
                        is_bot = bool(params[7])

                        day = ensure_aware(created_at.replace(
                            hour=0, minute=0, second=0, microsecond=0))

                        try:
                            existing = await conn.fetchrow('''
                                SELECT command_count FROM slash_commands_daily
                                WHERE guild_id = $1 AND command_name = $2 AND day = $3
                            ''', guild_id, command_name, day)

                            if existing:
                                await conn.execute('''
                                    UPDATE slash_commands_daily 
                                    SET command_count = command_count + 1,
                                        unique_users = unique_users + 1,
                                        encrypted_username = COALESCE(
                                            slash_commands_daily.encrypted_username, $4
                                        )
                                    WHERE guild_id = $1 AND command_name = $2 AND day = $3
                                ''', guild_id, command_name, day, encrypted_username)
                            else:
                                await conn.execute('''
                                    INSERT INTO slash_commands_daily 
                                    (day, guild_id, command_name, command_count, unique_users, is_bot, encrypted_username)
                                    VALUES ($1, $2, $3, 1, 1, $4, $5)
                                ''', day, guild_id, command_name, is_bot, encrypted_username)
                        except asyncpg.exceptions.PostgresError as e:
                            raise DatabaseQueryError(
                                "Failed to insert into slash_commands_daily",
                                context={'batch_type': batch_type},
                                original=e
                            )

                elif batch_type == 'role_growth':
                    params = data['params']
                    if len(params) >= 7:
                        guild_id = params[0]
                        role_id = params[1]
                        user_id = params[2]
                        action = params[3]
                        created_at = ensure_aware(params[4])
                        encrypted_username = params[5]
                        is_bot = params[6]

                        hour = ensure_aware(created_at.replace(
                            minute=0, second=0, microsecond=0))

                        added_count = 1 if action == 'added' else 0
                        removed_count = 1 if action == 'removed' else 0

                        try:
                            await conn.execute('''
                                INSERT INTO role_growth_hourly 
                                (hour, guild_id, role_id, user_id, added_count, removed_count, is_bot, encrypted_username)
                                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                                ON CONFLICT (guild_id, role_id, user_id, hour) 
                                DO UPDATE SET 
                                    added_count = role_growth_hourly.added_count + $5,
                                    removed_count = role_growth_hourly.removed_count + $6,
                                    encrypted_username = COALESCE(
                                        role_growth_hourly.encrypted_username, EXCLUDED.encrypted_username
                                    )
                            ''', hour, guild_id, role_id, user_id, added_count, removed_count, is_bot, encrypted_username)
                        except asyncpg.exceptions.PostgresError as e:
                            raise DatabaseQueryError(
                                "Failed to insert into role_growth_hourly",
                                context={'batch_type': batch_type},
                                original=e
                            )

                elif batch_type == 'member_joins':
                    params = data['params']
                    if len(params) >= 6:
                        guild_id = params[0]
                        user_id = params[1]
                        join_time = ensure_aware(params[2])
                        encrypted_username = params[3]
                        is_bot = bool(params[4])
                        member_count = params[5] if len(params) > 5 else 0

                        hour = ensure_aware(join_time.replace(
                            minute=0, second=0, microsecond=0))

                        try:
                            await conn.execute('''
                                INSERT INTO member_joins_hourly 
                                (hour, guild_id, user_id, join_count, is_bot, encrypted_username)
                                VALUES ($1, $2, $3, 1, $4, $5)
                                ON CONFLICT (guild_id, user_id, hour) 
                                DO UPDATE SET 
                                    join_count = member_joins_hourly.join_count + 1,
                                    encrypted_username = COALESCE(
                                        member_joins_hourly.encrypted_username, EXCLUDED.encrypted_username
                                    )
                            ''', hour, guild_id, user_id, is_bot, encrypted_username)
                        except asyncpg.exceptions.PostgresError as e:
                            raise DatabaseQueryError(
                                "Failed to insert into member_joins_hourly",
                                context={'batch_type': batch_type},
                                original=e
                            )

                elif batch_type == 'member_leaves':
                    params = data['params']
                    if len(params) >= 6:
                        guild_id = params[0]
                        user_id = params[1]
                        leave_time = ensure_aware(params[2])
                        encrypted_username = params[3]
                        is_bot = bool(params[4])
                        member_count = params[5] if len(params) > 5 else 0

                        hour = ensure_aware(leave_time.replace(
                            minute=0, second=0, microsecond=0))

                        try:
                            await conn.execute('''
                                INSERT INTO member_leaves_hourly 
                                (hour, guild_id, user_id, leave_count, is_bot, encrypted_username)
                                VALUES ($1, $2, $3, 1, $4, $5)
                                ON CONFLICT (guild_id, user_id, hour) 
                                DO UPDATE SET 
                                    leave_count = member_leaves_hourly.leave_count + 1,
                                    encrypted_username = COALESCE(
                                        member_leaves_hourly.encrypted_username, EXCLUDED.encrypted_username
                                    )
                            ''', hour, guild_id, user_id, is_bot, encrypted_username)
                        except asyncpg.exceptions.PostgresError as e:
                            raise DatabaseQueryError(
                                "Failed to insert into member_leaves_hourly",
                                context={'batch_type': batch_type},
                                original=e
                            )

                elif batch_type == 'invites':
                    params = data['params']
                    if len(params) >= 9:
                        created_at = ensure_aware(params[5])
                        is_bot = bool(
                            params[6]) if params[6] is not None else False
                        is_vanity = bool(
                            params[7]) if params[7] is not None else False
                        encrypted_username = params[8] if len(
                            params) > 8 else None

                        try:
                            await conn.execute('''
                                INSERT INTO invite_tracking 
                                (guild_id, inviter_id, invitee_id, invite_code, invite_type,
                                created_at, is_bot, is_vanity, encrypted_username)
                                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                            ''', params[0], params[1], params[2], params[3], params[4],
                                created_at, is_bot, is_vanity, encrypted_username)
                        except asyncpg.exceptions.PostgresError as e:
                            raise DatabaseQueryError(
                                "Failed to insert invite tracking record",
                                context={'batch_type': batch_type},
                                original=e
                            )

                elif batch_type == 'role_members':
                    params = data['params']
                    updated_at = ensure_aware(params[5]) if len(
                        params) > 5 else datetime.now(timezone.utc)

                    if len(params) > 7 and params[7] == 'DELETE':
                        try:
                            await conn.execute("""
                                DELETE FROM current_role_members
                                WHERE guild_id = $1 AND user_id = $2 AND role_id = $3
                            """, params[0], params[1], params[2])
                        except asyncpg.exceptions.PostgresError as e:
                            raise DatabaseQueryError(
                                "Failed to delete role member",
                                context={'batch_type': batch_type},
                                original=e
                            )
                    else:
                        try:
                            is_bot = bool(params[6]) if len(
                                params) > 6 else False
                            role_name = params[3] if len(
                                params) > 3 else 'Unknown Role'
                            role_color = params[4] if len(params) > 4 else 0

                            await conn.execute("""
                                INSERT INTO current_role_members (guild_id, user_id, role_id, role_name, role_color, updated_at, is_bot)
                                VALUES ($1, $2, $3, $4, $5, $6, $7)
                                ON CONFLICT (guild_id, user_id, role_id) 
                                DO UPDATE SET 
                                    role_name = EXCLUDED.role_name,
                                    role_color = EXCLUDED.role_color,
                                    updated_at = EXCLUDED.updated_at,
                                    is_bot = EXCLUDED.is_bot
                            """, params[0], params[1], params[2], role_name, role_color, updated_at, is_bot)
                        except asyncpg.exceptions.PostgresError as e:
                            raise DatabaseQueryError(
                                "Failed to insert role member",
                                context={'batch_type': batch_type},
                                original=e
                            )

                else:
                    return False

                return True

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist during direct write",
                context={'batch_type': batch_type},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed during direct write",
                context={'batch_type': batch_type},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out during direct write",
                context={'batch_type': batch_type},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            if not isinstance(e, (DatabaseQueryError, DatabaseConnectionError, DatabaseTimeoutError)):
                raise DatabaseQueryError(
                    "Database error during direct write",
                    context={'batch_type': batch_type},
                    original=e
                )
            raise
        except Exception as e:
            if not isinstance(e, DatabaseQueryError):
                raise DatabaseQueryError(
                    "Unexpected error during direct write",
                    context={'batch_type': batch_type},
                    original=e
                )
            raise

    # ======================================================================
    # BATCH FLUSHING METHODS - FIXED EXCEPTION HANDLING
    # ======================================================================

    async def _flush_batch_to_postgresql(self, batch_type: str):
        """Flush a specific batch to PostgreSQL.
        Each record gets its own transaction to ensure commits happen."""
        if not self.pool or not self.db_connected:
            return

        async with self.redis_batch_lock:
            if batch_type not in self.redis_batches or not self.redis_batches[batch_type]:
                return

            batch_data = self.redis_batches[batch_type].copy()
            self.redis_batches[batch_type].clear()
            self.batch_sizes[batch_type] = 0

        if not batch_data:
            return

        failed_count = 0
        failed_records = []
        successful_count = 0

        # Process each record in its OWN transaction
        for idx, data in enumerate(batch_data):
            try:
                async with self.pool.acquire() as conn:
                    async with conn.transaction():  # Each record gets its own transaction

                        if batch_type == 'voice_sessions':
                            params = data.get('params', [])
                            if len(params) >= 16:
                                guild_id = params[0]
                                user_id = params[1]
                                channel_id = params[2] or 0
                                category_id = params[3]
                                encrypted_username = params[4]
                                join_time = params[5]
                                leave_time = params[6]
                                duration_seconds = params[7] or 0
                                state_flags = params[8] or 0
                                state_category = params[9]

                                was_muted = 1 if params[10] else 0
                                was_deafened = 1 if params[11] else 0
                                was_streaming = 1 if params[12] else 0
                                was_video = 1 if params[13] else 0

                                if params[14] is None:
                                    is_bot = False
                                elif isinstance(params[14], bool):
                                    is_bot = params[14]
                                else:
                                    is_bot = bool(params[14])

                                hour = params[15]

                                if not isinstance(hour, datetime):
                                    hour = join_time.replace(
                                        minute=0, second=0, microsecond=0)
                                hour = ensure_aware(hour)

                                await conn.execute('''
                                    INSERT INTO voice_session_history_hourly 
                                    (hour, guild_id, user_id, channel_id, category_id,
                                    total_seconds, session_count, state_flags,
                                    was_muted_count, was_deafened_count, was_streaming_count, was_video_count,
                                    is_bot, encrypted_username)
                                    VALUES ($1, $2, $3, $4, $5, $6, 1, $7, $8, $9, $10, $11, $12, $13)
                                    ON CONFLICT (guild_id, user_id, channel_id, hour, state_flags) 
                                    DO UPDATE SET 
                                        total_seconds = voice_session_history_hourly.total_seconds + $6,
                                        session_count = voice_session_history_hourly.session_count + 1,
                                        was_muted_count = voice_session_history_hourly.was_muted_count + $8,
                                        was_deafened_count = voice_session_history_hourly.was_deafened_count + $9,
                                        was_streaming_count = voice_session_history_hourly.was_streaming_count + $10,
                                        was_video_count = voice_session_history_hourly.was_video_count + $11,
                                        encrypted_username = COALESCE(
                                            voice_session_history_hourly.encrypted_username, EXCLUDED.encrypted_username
                                        )
                                ''',
                                                   hour, guild_id, user_id, channel_id, category_id,
                                                   duration_seconds, state_flags,
                                                   was_muted, was_deafened, was_streaming, was_video,
                                                   is_bot, encrypted_username)

                        elif batch_type == 'messages':
                            params = data.get('params', [])
                            if len(params) >= 12:
                                guild_id = params[0]
                                user_id = params[1]
                                channel_id = params[2] or 0
                                category_id = params[3]
                                message_id = params[4]
                                encrypted_username = params[5]
                                message_length = params[6] or 0
                                mentions = params[7]
                                has_attachment = bool(params[8])
                                has_embed = bool(params[9])
                                created_at = params[10]
                                created_at = ensure_aware(created_at)
                                is_bot = bool(params[11])

                                hour = created_at.replace(
                                    minute=0, second=0, microsecond=0)
                                hour = ensure_aware(hour)

                                await conn.execute('''
                                    INSERT INTO message_tracking_hourly 
                                    (hour, guild_id, user_id, channel_id, category_id, message_count,
                                    total_chars, attachment_count, embed_count, is_bot, encrypted_username)
                                    VALUES ($1, $2, $3, $4, $5, 1, $6, $7, $8, $9, $10)
                                    ON CONFLICT (guild_id, user_id, channel_id, hour) 
                                    DO UPDATE SET 
                                        message_count = message_tracking_hourly.message_count + 1,
                                        total_chars = message_tracking_hourly.total_chars + $6,
                                        attachment_count = message_tracking_hourly.attachment_count + $7,
                                        embed_count = message_tracking_hourly.embed_count + $8,
                                        encrypted_username = COALESCE(
                                            message_tracking_hourly.encrypted_username, EXCLUDED.encrypted_username
                                        )
                                ''',
                                                   hour, guild_id, user_id, channel_id, category_id,
                                                   message_length,
                                                   1 if has_attachment else 0,
                                                   1 if has_embed else 0,
                                                   is_bot,
                                                   encrypted_username)

                        elif batch_type == 'mentions':
                            params = data.get('params', [])
                            if len(params) >= 10:
                                guild_id = params[0]
                                mentioned_user_id = params[1]
                                mentioner_user_id = params[2]
                                channel_id = params[3] or 0
                                category_id = params[4]
                                message_id = params[5]
                                created_at = params[6]
                                created_at = ensure_aware(created_at)
                                encrypted_username = params[7]
                                is_bot = bool(params[8])
                                encrypted_mentioned_username = params[9]

                                hour = created_at.replace(
                                    minute=0, second=0, microsecond=0)
                                hour = ensure_aware(hour)

                                await conn.execute('''
                                    INSERT INTO user_mentions_hourly 
                                    (hour, guild_id, mentioned_user_id, mentioner_user_id,
                                    channel_id, category_id, mention_count, is_bot,
                                    encrypted_username, encrypted_mentioned_username)
                                    VALUES ($1, $2, $3, $4, $5, $6, 1, $7, $8, $9)
                                    ON CONFLICT (guild_id, mentioned_user_id, mentioner_user_id, channel_id, hour) 
                                    DO UPDATE SET 
                                        mention_count = user_mentions_hourly.mention_count + 1,
                                        encrypted_username = COALESCE(
                                            user_mentions_hourly.encrypted_username, EXCLUDED.encrypted_username
                                        ),
                                        encrypted_mentioned_username = COALESCE(
                                            user_mentions_hourly.encrypted_mentioned_username, EXCLUDED.encrypted_mentioned_username
                                        )
                                ''',
                                                   hour, guild_id, mentioned_user_id, mentioner_user_id,
                                                   channel_id, category_id, is_bot, encrypted_username, encrypted_mentioned_username)

                        elif batch_type == 'emojis':
                            params = data.get('params', [])
                            if len(params) >= 11:
                                guild_id = params[0]
                                user_id = params[1]
                                channel_id = params[2] or 0
                                category_id = params[3]
                                encrypted_username = params[4]
                                emoji_str = params[5]
                                is_custom = bool(params[6])
                                usage_count = params[7] or 1
                                last_used = params[8]
                                last_used = ensure_aware(last_used)
                                usage_type = params[9]
                                is_bot = bool(params[10])

                                hour = last_used.replace(
                                    minute=0, second=0, microsecond=0)
                                hour = ensure_aware(hour)

                                await conn.execute('''
                                    INSERT INTO emoji_usage_hourly 
                                    (hour, guild_id, user_id, channel_id, category_id,
                                    emoji_str, is_custom, usage_count, usage_type, is_bot, encrypted_username)
                                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                                    ON CONFLICT (guild_id, user_id, channel_id, emoji_str, usage_type, hour) 
                                    DO UPDATE SET 
                                        usage_count = emoji_usage_hourly.usage_count + $8,
                                        encrypted_username = COALESCE(
                                            emoji_usage_hourly.encrypted_username, EXCLUDED.encrypted_username
                                        )
                                ''',
                                                   hour, guild_id, user_id, channel_id, category_id,
                                                   emoji_str, is_custom, usage_count, usage_type, is_bot, encrypted_username)

                        elif batch_type == 'slash_commands':
                            params = data.get('params', [])
                            if len(params) >= 8:
                                guild_id = params[0]
                                command_name = params[2]
                                channel_id = params[3] or 0
                                category_id = params[4]
                                created_at = params[5]
                                created_at = ensure_aware(created_at)
                                encrypted_username = params[6]
                                is_bot = bool(params[7])

                                day = created_at.replace(
                                    hour=0, minute=0, second=0, microsecond=0)
                                day = ensure_aware(day)

                                await conn.execute('''
                                    INSERT INTO slash_commands_daily 
                                    (day, guild_id, command_name, command_count, unique_users, is_bot, encrypted_username)
                                    VALUES ($1, $2, $3, 1, 1, $4, $5)
                                    ON CONFLICT (guild_id, command_name, day) 
                                    DO UPDATE SET 
                                        command_count = slash_commands_daily.command_count + 1,
                                        unique_users = slash_commands_daily.unique_users + 1,
                                        encrypted_username = COALESCE(
                                            slash_commands_daily.encrypted_username, EXCLUDED.encrypted_username
                                        )
                                ''', day, guild_id, command_name, is_bot, encrypted_username)

                        elif batch_type == 'role_growth':
                            params = data.get('params', [])
                            if len(params) >= 7:
                                guild_id = params[0]
                                role_id = params[1]
                                user_id = params[2]
                                action = params[3]
                                created_at = params[4]
                                created_at = ensure_aware(created_at)
                                encrypted_username = params[5]
                                is_bot = bool(params[6])

                                hour = created_at.replace(
                                    minute=0, second=0, microsecond=0)
                                hour = ensure_aware(hour)

                                added_count = 1 if action == 'added' else 0
                                removed_count = 1 if action == 'removed' else 0

                                await conn.execute('''
                                    INSERT INTO role_growth_hourly 
                                    (hour, guild_id, role_id, user_id, added_count, removed_count, is_bot, encrypted_username)
                                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                                    ON CONFLICT (guild_id, role_id, user_id, hour) 
                                    DO UPDATE SET 
                                        added_count = role_growth_hourly.added_count + $5,
                                        removed_count = role_growth_hourly.removed_count + $6,
                                        encrypted_username = COALESCE(
                                            role_growth_hourly.encrypted_username, EXCLUDED.encrypted_username
                                        )
                                ''',
                                                   hour, guild_id, role_id, user_id, added_count, removed_count, is_bot, encrypted_username)

                        elif batch_type == 'member_joins':
                            params = data.get('params', [])
                            if len(params) >= 6:
                                guild_id = params[0]
                                user_id = params[1]
                                join_time = params[2]
                                join_time = ensure_aware(join_time)
                                encrypted_username = params[3]
                                is_bot = bool(params[4])
                                member_count = params[5] if len(
                                    params) > 5 else 0

                                hour = join_time.replace(
                                    minute=0, second=0, microsecond=0)
                                hour = ensure_aware(hour)

                                await conn.execute('''
                                    INSERT INTO member_joins_hourly 
                                    (hour, guild_id, user_id, join_count, is_bot, encrypted_username)
                                    VALUES ($1, $2, $3, 1, $4, $5)
                                    ON CONFLICT (guild_id, user_id, hour) 
                                    DO UPDATE SET 
                                        join_count = member_joins_hourly.join_count + 1,
                                        encrypted_username = COALESCE(
                                            member_joins_hourly.encrypted_username, EXCLUDED.encrypted_username
                                        )
                                ''',
                                                   hour, guild_id, user_id, is_bot, encrypted_username)

                        elif batch_type == 'member_leaves':
                            params = data.get('params', [])
                            if len(params) >= 6:
                                guild_id = params[0]
                                user_id = params[1]
                                leave_time = params[2]
                                leave_time = ensure_aware(leave_time)
                                encrypted_username = params[3]
                                is_bot = bool(params[4])
                                member_count = params[5] if len(
                                    params) > 5 else 0

                                hour = leave_time.replace(
                                    minute=0, second=0, microsecond=0)
                                hour = ensure_aware(hour)

                                await conn.execute('''
                                    INSERT INTO member_leaves_hourly 
                                    (hour, guild_id, user_id, leave_count, is_bot, encrypted_username)
                                    VALUES ($1, $2, $3, 1, $4, $5)
                                    ON CONFLICT (guild_id, user_id, hour) 
                                    DO UPDATE SET 
                                        leave_count = member_leaves_hourly.leave_count + 1,
                                        encrypted_username = COALESCE(
                                            member_leaves_hourly.encrypted_username, EXCLUDED.encrypted_username
                                        )
                                ''',
                                                   hour, guild_id, user_id, is_bot, encrypted_username)

                        elif batch_type == 'invites':
                            params = data.get('params', [])
                            if len(params) >= 9:
                                guild_id = params[0]
                                inviter_id = params[1]
                                invitee_id = params[2]
                                invite_code = params[3]
                                invite_type = params[4]
                                created_at = params[5]
                                created_at = ensure_aware(created_at)
                                is_bot = bool(
                                    params[6]) if params[6] is not None else False
                                is_vanity = bool(
                                    params[7]) if params[7] is not None else False
                                encrypted_username = params[8] if len(
                                    params) > 8 else None

                                await conn.execute('''
                                    INSERT INTO invite_tracking 
                                    (guild_id, inviter_id, invitee_id, invite_code, invite_type,
                                    created_at, is_bot, is_vanity, encrypted_username)
                                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                                ''',
                                                   guild_id, inviter_id, invitee_id, invite_code,
                                                   invite_type, created_at, is_bot, is_vanity, encrypted_username)

                        elif batch_type == 'role_members':
                            params = data.get('params', [])
                            if len(params) >= 7:
                                updated_at = params[5]
                                updated_at = ensure_aware(updated_at)
                                if len(params) > 7 and params[7] == 'DELETE':
                                    await conn.execute("""
                                        DELETE FROM current_role_members
                                        WHERE guild_id = $1 AND user_id = $2 AND role_id = $3
                                    """, params[0], params[1], params[2])
                                else:
                                    is_bot = bool(params[6])
                                    role_name = params[3] if len(
                                        params) > 3 else 'Unknown Role'
                                    role_color = params[4] if len(
                                        params) > 4 else 0
                                    await conn.execute("""
                                        INSERT INTO current_role_members (guild_id, user_id, role_id, role_name, role_color, updated_at, is_bot)
                                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                                        ON CONFLICT (guild_id, user_id, role_id) 
                                        DO UPDATE SET 
                                            role_name = EXCLUDED.role_name,
                                            role_color = EXCLUDED.role_color,
                                            updated_at = EXCLUDED.updated_at,
                                            is_bot = EXCLUDED.is_bot
                                    """, params[0], params[1], params[2], role_name, role_color, updated_at, is_bot)

                        successful_count += 1

            except Exception as e:
                failed_count += 1
                failed_records.append({
                    'index': idx,
                    'error': str(e),
                    'data': str(data)[:200]
                })
                continue

        async with self.metrics_lock:
            self.metrics['redis_batch_flushes'] += 1
            if batch_type in self.metrics['redis_batch_sizes']:
                self.metrics['redis_batch_sizes'][batch_type] = 0

        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        if successful_count > 0 or failed_count > 0:
            if failed_count > 0:
                print(
                    f"⚠️ [{timestamp}] {batch_type.upper()}: {successful_count} saved, {failed_count} failed")
                if failed_records:
                    print(
                        f"   First failure: {failed_records[0]['error'][:100]}")
            else:
                print(
                    f"✅ [{timestamp}] {batch_type.upper()}: {successful_count} records saved")

    async def _flush_all_batches_to_postgresql(self):
        """Flush all batches to PostgreSQL."""
        failed_batches = []
        for batch_type in list(self.redis_batches.keys()):
            try:
                await self._flush_batch_to_postgresql(batch_type)
            except Exception as e:
                failed_batches.append(batch_type)
                # Don't raise - collect all failures

        if failed_batches:
            raise CacheBatchFailed(
                "Failed to flush some batches",
                context={
                    'failed_batches': failed_batches,
                    'timestamp': time.time()
                }
            )

    @tasks.loop(seconds=Constants.REDIS_BATCH_FLUSH_INTERVAL)
    async def redis_batch_flusher(self):
        """Periodic task to flush Redis batches with aggregated summary."""
        if not self.pool or not self.db_connected:
            return

        try:
            # Collect batch statistics before flushing
            batch_stats = {}
            for batch_type in self.redis_batches.keys():
                if self.redis_batches[batch_type]:
                    batch_stats[batch_type] = len(
                        self.redis_batches[batch_type])

            # Flush all batches
            await self._flush_all_batches_to_postgresql()
            self.last_flush_time = time.time()

            # Print aggregated summary if any batches had data
            if batch_stats:
                total_records = sum(batch_stats.values())
                batch_list = ', '.join(
                    [f"{k}: {v}" for k, v in batch_stats.items()])
                print(
                    f"📊 BATCH FLUSH SUMMARY [{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}]: {total_records} total records ({batch_list})")

        except Exception as e:
            if not isinstance(e, CacheBatchFailed):
                raise CacheBatchFailed(
                    "Error in redis batch flusher",
                    context={'last_flush_time': self.last_flush_time},
                    original=e
                )
            raise

    # ======================================================================
    # DATABASE INITIALIZATION WITH AGGREGATED TABLES - FIXED EXCEPTION HANDLING
    # ======================================================================

    async def initialize_database(self) -> bool:
        """Initialize database with all required tables and indexes, including aggregated tables."""
        if not self.pool:
            raise DatabaseConnectionError(
                "No database pool available for initialization",
                context={'operation': 'initialize_database'}
            )

        try:
            async with self.pool.acquire() as conn:
                # Enable required extensions
                try:
                    await conn.execute('CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE')
                    print("✅ TimescaleDB extension enabled")
                except asyncpg.exceptions.PostgresError as e:
                    raise DatabaseQueryError(
                        "Failed to create timescaledb extension",
                        context={'operation': 'initialize_database'},
                        original=e
                    )

                print("\n" + "="*60)
                print("📋 CREATING DATABASE TABLES")
                print("="*60)

                # ===== CREATE ALL TABLES FIRST (BEFORE HYPERTABLES) =====

                # Create user_mentions_hourly table
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS user_mentions_hourly (
                        hour TIMESTAMPTZ NOT NULL,
                        guild_id BIGINT NOT NULL,
                        mentioned_user_id BIGINT NOT NULL,
                        mentioner_user_id BIGINT NOT NULL,
                        channel_id BIGINT,
                        category_id BIGINT,
                        mention_count INT DEFAULT 1,
                        is_bot BOOLEAN DEFAULT FALSE,
                        encrypted_username TEXT,
                        encrypted_mentioned_username TEXT
                    )
                ''')
                print("  ✅ Created/verified table: user_mentions_hourly")

                # Create message_tracking_hourly table
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS message_tracking_hourly (
                        hour TIMESTAMPTZ NOT NULL,
                        guild_id BIGINT NOT NULL,
                        user_id BIGINT NOT NULL,
                        channel_id BIGINT,
                        category_id BIGINT,
                        message_count INT DEFAULT 0,
                        total_chars BIGINT DEFAULT 0,
                        attachment_count INT DEFAULT 0,
                        embed_count INT DEFAULT 0,
                        is_bot BOOLEAN DEFAULT FALSE,
                        encrypted_username TEXT
                    )
                ''')
                print("  ✅ Created/verified table: message_tracking_hourly")

                # Create voice_session_history_hourly table
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS voice_session_history_hourly (
                        hour TIMESTAMPTZ NOT NULL,
                        guild_id BIGINT NOT NULL,
                        user_id BIGINT NOT NULL,
                        channel_id BIGINT,
                        category_id BIGINT,
                        total_seconds BIGINT DEFAULT 0,
                        session_count INT DEFAULT 0,
                        state_flags INT DEFAULT 0,
                        was_muted_count INT DEFAULT 0,
                        was_deafened_count INT DEFAULT 0,
                        was_streaming_count INT DEFAULT 0,
                        was_video_count INT DEFAULT 0,
                        is_bot BOOLEAN DEFAULT FALSE,
                        encrypted_username TEXT
                    )
                ''')
                print("  ✅ Created/verified table: voice_session_history_hourly")

                # Create emoji_usage_hourly table
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS emoji_usage_hourly (
                        hour TIMESTAMPTZ NOT NULL,
                        guild_id BIGINT NOT NULL,
                        user_id BIGINT NOT NULL,
                        channel_id BIGINT,
                        category_id BIGINT,
                        emoji_str TEXT NOT NULL,
                        is_custom BOOLEAN DEFAULT FALSE,
                        usage_count INT DEFAULT 1,
                        usage_type TEXT NOT NULL,
                        is_bot BOOLEAN DEFAULT FALSE,
                        encrypted_username TEXT
                    )
                ''')
                print("  ✅ Created/verified table: emoji_usage_hourly")

                # Create activity_sessions_hourly table
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS activity_sessions_hourly (
                        hour TIMESTAMPTZ NOT NULL,
                        guild_id BIGINT NOT NULL,
                        user_id BIGINT NOT NULL,
                        activity_name TEXT NOT NULL,
                        activity_type TEXT NOT NULL,
                        total_seconds BIGINT DEFAULT 0,
                        session_count INT DEFAULT 0,
                        is_bot BOOLEAN DEFAULT FALSE,
                        encrypted_username TEXT
                    )
                ''')
                print("  ✅ Created/verified table: activity_sessions_hourly")

                # Create role_growth_hourly table
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS role_growth_hourly (
                        hour TIMESTAMPTZ NOT NULL,
                        guild_id BIGINT NOT NULL,
                        role_id BIGINT NOT NULL,
                        user_id BIGINT NOT NULL,
                        added_count INT DEFAULT 0,
                        removed_count INT DEFAULT 0,
                        is_bot BOOLEAN DEFAULT FALSE,
                        encrypted_username TEXT
                    )
                ''')
                print("  ✅ Created/verified table: role_growth_hourly")

                # Create member_joins_hourly table
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS member_joins_hourly (
                        hour TIMESTAMPTZ NOT NULL,
                        guild_id BIGINT NOT NULL,
                        user_id BIGINT NOT NULL,
                        join_count INT DEFAULT 0,
                        is_bot BOOLEAN DEFAULT FALSE,
                        encrypted_username TEXT
                    )
                ''')
                print("  ✅ Created/verified table: member_joins_hourly")

                # Create member_leaves_hourly table
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS member_leaves_hourly (
                        hour TIMESTAMPTZ NOT NULL,
                        guild_id BIGINT NOT NULL,
                        user_id BIGINT NOT NULL,
                        leave_count INT DEFAULT 0,
                        is_bot BOOLEAN DEFAULT FALSE,
                        encrypted_username TEXT
                    )
                ''')
                print("  ✅ Created/verified table: member_leaves_hourly")

                # Create slash_commands_daily table
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS slash_commands_daily (
                        day TIMESTAMPTZ NOT NULL,
                        guild_id BIGINT NOT NULL,
                        command_name TEXT NOT NULL,
                        command_count INT DEFAULT 0,
                        unique_users INT DEFAULT 0,
                        is_bot BOOLEAN DEFAULT FALSE,
                        encrypted_username TEXT
                    )
                ''')
                print("  ✅ Created/verified table: slash_commands_daily")

                # Create invite_tracking table (static)
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS invite_tracking (
                        id BIGSERIAL,
                        guild_id BIGINT NOT NULL,
                        inviter_id BIGINT NOT NULL,
                        invitee_id BIGINT,
                        invite_code TEXT NOT NULL,
                        invite_type TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        is_bot BOOLEAN DEFAULT FALSE,
                        is_vanity BOOLEAN DEFAULT FALSE,
                        encrypted_username TEXT,
                        PRIMARY KEY (id, created_at)
                    )
                ''')
                print("  ✅ Created/verified table: invite_tracking")

                # Create invite_uses table (static)
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS invite_uses (
                        id BIGSERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        invite_code TEXT NOT NULL,
                        uses INT DEFAULT 0,
                        leaves INT DEFAULT 0,
                        inviter_id BIGINT,
                        is_vanity BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW(),
                        deleted BOOLEAN DEFAULT FALSE,
                        UNIQUE(guild_id, invite_code)
                    )
                ''')
                print("  ✅ Created/verified table: invite_uses")

                # Create activities table (static)
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS activities (
                        id BIGSERIAL,
                        guild_id BIGINT NOT NULL,
                        user_id BIGINT NOT NULL,
                        encrypted_username TEXT,
                        activity_name TEXT NOT NULL,
                        activity_type TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (id, created_at)
                    )
                ''')
                print("  ✅ Created/verified table: activities")

                # Create blacklist tables
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS blacklisted_users (
                        id BIGSERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        user_id BIGINT NOT NULL,
                        added_by BIGINT NOT NULL DEFAULT 0,
                        added_at TIMESTAMPTZ DEFAULT NOW(),
                        UNIQUE(guild_id, user_id)
                    )
                ''')
                print("  ✅ Created/verified table: blacklisted_users")

                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS blacklisted_channels (
                        id BIGSERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        channel_id BIGINT NOT NULL,
                        added_by BIGINT NOT NULL DEFAULT 0,
                        added_at TIMESTAMPTZ DEFAULT NOW(),
                        UNIQUE(guild_id, channel_id)
                    )
                ''')
                print("  ✅ Created/verified table: blacklisted_channels")

                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS blacklisted_categories (
                        id BIGSERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        category_id BIGINT NOT NULL,
                        added_by BIGINT NOT NULL DEFAULT 0,
                        added_at TIMESTAMPTZ DEFAULT NOW(),
                        UNIQUE(guild_id, category_id)
                    )
                ''')
                print("  ✅ Created/verified table: blacklisted_categories")

                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS blacklisted_roles (
                        id BIGSERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        role_id BIGINT NOT NULL,
                        added_by BIGINT NOT NULL DEFAULT 0,
                        added_at TIMESTAMPTZ DEFAULT NOW(),
                        UNIQUE(guild_id, role_id)
                    )
                ''')
                print("  ✅ Created/verified table: blacklisted_roles")

                # Create settings table
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS settings (
                        guild_id BIGINT PRIMARY KEY,
                        prefix TEXT DEFAULT 's!',
                        timezone TEXT DEFAULT 'UTC',
                        voice_states TEXT[] DEFAULT '{"self_mute", "self_deafen", "streaming", "video"}',
                        permission_level TEXT DEFAULT 'Default',
                        bot_filter BOOLEAN DEFAULT TRUE,
                        dashboard_access_level TEXT DEFAULT 'Member',
                        min_account_age_days INT DEFAULT 3,
                        default_time_mode TEXT DEFAULT 'days_back' CHECK (default_time_mode IN ('all_time', 'days_back', 'date_range', 'rolling_window')),
                        default_days_back INT DEFAULT 14,
                        default_from_date TIMESTAMPTZ DEFAULT NULL,
                        default_to_date TIMESTAMPTZ DEFAULT NULL,
                        default_rolling_type TEXT DEFAULT NULL,
                        default_rolling_value INT DEFAULT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                print("  ✅ Created/verified table: settings")

                # Create current_role_members table
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS current_role_members (
                        id BIGSERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        user_id BIGINT NOT NULL,
                        role_id BIGINT NOT NULL,
                        role_name TEXT NOT NULL DEFAULT 'Unknown Role',
                        role_color INT DEFAULT 0,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        is_bot BOOLEAN DEFAULT FALSE,
                        UNIQUE(guild_id, user_id, role_id)
                    )
                ''')
                print("  ✅ Created/verified table: current_role_members")

                # Create cart_items table
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS cart_items (
                        id BIGSERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        item_type TEXT NOT NULL CHECK (item_type IN ('module', 'tier')),
                        item_id TEXT NOT NULL,
                        billing_cycle TEXT NOT NULL CHECK (billing_cycle IN ('monthly', 'yearly')),
                        price_usd NUMERIC(10,2) NOT NULL,
                        added_at TIMESTAMPTZ DEFAULT NOW(),
                        UNIQUE(user_id, item_id)
                    )
                ''')
                print("  ✅ Created/verified table: cart_items")

                # Create cart_item_servers table
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS cart_item_servers (
                        id BIGSERIAL PRIMARY KEY,
                        cart_item_id BIGINT NOT NULL REFERENCES cart_items(id) ON DELETE CASCADE,
                        user_id BIGINT NOT NULL,
                        guild_id BIGINT NOT NULL,
                        assigned_at TIMESTAMPTZ DEFAULT NOW(),
                        UNIQUE(cart_item_id, guild_id)
                    )
                ''')
                print("  ✅ Created/verified table: cart_item_servers")

                # Create member_growth_stats table
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS member_growth_stats (
                        id BIGSERIAL,
                        guild_id BIGINT NOT NULL,
                        date DATE NOT NULL,
                        joins_count INT DEFAULT 0,
                        leaves_count INT DEFAULT 0,
                        net_growth INT DEFAULT 0,
                        PRIMARY KEY (id, date),
                        UNIQUE(guild_id, date)
                    )
                ''')
                print("  ✅ Created/verified table: member_growth_stats")

                # Create discord_channels table
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS discord_channels (
                        id BIGSERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        channel_id BIGINT NOT NULL UNIQUE,
                        channel_name TEXT NOT NULL,
                        channel_type VARCHAR(20) NOT NULL,
                        category_id BIGINT,
                        is_deleted BOOLEAN DEFAULT FALSE,
                        last_synced TIMESTAMP DEFAULT NOW(),
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                ''')
                print("  ✅ Created/verified table: discord_channels")

                # Create server_member_counts table
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS server_member_counts (
                        id BIGSERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        member_count INT NOT NULL,
                        UNIQUE(guild_id, recorded_at)
                    )
                ''')
                print("  ✅ Created/verified table: server_member_counts")

                # Create reset_schedules table
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS reset_schedules (
                        id SERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        requested_by_id BIGINT NOT NULL,
                        reset_types TEXT[] NOT NULL,
                        schedule_type TEXT NOT NULL DEFAULT 'immediate',
                        target_time TIMESTAMPTZ,
                        recurring_pattern TEXT,
                        recurring_weekday INTEGER,
                        recurring_day_of_month INTEGER,
                        recurring_time TIME,
                        recurring_interval_days INTEGER,
                        recurring_weekdays INTEGER[],
                        recurring_days_of_month INTEGER[],
                        recurring_times TIME[],
                        delete_from_date TIMESTAMPTZ,
                        delete_to_date TIMESTAMPTZ,
                        time_period_days INTEGER,
                        completed BOOLEAN DEFAULT FALSE NOT NULL,
                        last_executed_at TIMESTAMPTZ,
                        next_execution_at TIMESTAMPTZ,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
                        executed_at TIMESTAMPTZ,
                        failure_count INTEGER DEFAULT 0,
                        last_error TEXT,
                        scope_type TEXT,
                        scope_details TEXT,
                        channel_id BIGINT,
                        category_id BIGINT,
                        schedule_name VARCHAR(100),
                        enabled BOOLEAN DEFAULT TRUE,
                        reason TEXT,
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                ''')
                print("  ✅ Created/verified table: reset_schedules")

                # ===================================================================
                # ===== PADDLE PAYMENT SYSTEM TABLES =====
                # ===================================================================
                print("\n" + "="*60)
                print("💳 CREATING PADDLE PAYMENT TABLES")
                print("="*60)

                # ----- modules -----
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS modules (
                        id                  SERIAL PRIMARY KEY,
                        module_key          TEXT UNIQUE NOT NULL,
                        display_name        TEXT NOT NULL,
                        description         TEXT,
                        module_number       TEXT NOT NULL,
                        monthly_price_usd   NUMERIC(10,2) NOT NULL,
                        yearly_price_usd    NUMERIC(10,2) NOT NULL,
                        paddle_product_id   TEXT UNIQUE NOT NULL,
                        paddle_monthly_price_id TEXT UNIQUE NOT NULL,
                        paddle_yearly_price_id  TEXT UNIQUE NOT NULL,
                        is_active           BOOLEAN DEFAULT TRUE,
                        created_at          TIMESTAMPTZ DEFAULT NOW()
                    )
                ''')
                print("  ✅ Created/verified table: modules")

                # ----- tiers -----
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS tiers (
                        id                  SERIAL PRIMARY KEY,
                        tier_key            TEXT UNIQUE NOT NULL,
                        display_name        TEXT NOT NULL,
                        monthly_price_usd   NUMERIC(10,2) NOT NULL,
                        yearly_price_usd    NUMERIC(10,2) NOT NULL,
                        paddle_product_id   TEXT UNIQUE,
                        paddle_monthly_price_id TEXT UNIQUE,
                        paddle_yearly_price_id  TEXT UNIQUE,
                        discount_pct        NUMERIC(5,2) DEFAULT 0,
                        is_active           BOOLEAN DEFAULT FALSE,
                        created_at          TIMESTAMPTZ DEFAULT NOW()
                    )
                ''')
                print("  ✅ Created/verified table: tiers")

                # ----- tier_modules -----
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS tier_modules (
                        tier_id     INTEGER NOT NULL REFERENCES tiers(id) ON DELETE CASCADE,
                        module_id   INTEGER NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
                        PRIMARY KEY (tier_id, module_id)
                    )
                ''')
                print("  ✅ Created/verified table: tier_modules")

                # ----- server_count_discounts -----
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS server_count_discounts (
                        id                      SERIAL PRIMARY KEY,
                        server_count            INTEGER UNIQUE NOT NULL,
                        discount_pct            NUMERIC(5,2) NOT NULL,
                        paddle_discount_id      TEXT UNIQUE NOT NULL,
                        created_at              TIMESTAMPTZ DEFAULT NOW()
                    )
                ''')
                print("  ✅ Created/verified table: server_count_discounts")

                # ----- paddle_customers -----
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS paddle_customers (
                        id                  SERIAL PRIMARY KEY,
                        discord_id          TEXT UNIQUE NOT NULL,
                        paddle_customer_id  TEXT UNIQUE,
                        email               TEXT,
                        created_at          TIMESTAMPTZ DEFAULT NOW(),
                        updated_at          TIMESTAMPTZ DEFAULT NOW()
                    )
                ''')
                print("  ✅ Created/verified table: paddle_customers")

                # ----- subscriptions -----
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS subscriptions (
                        id                      SERIAL PRIMARY KEY,
                        discord_id              TEXT NOT NULL,
                        guild_id                BIGINT NOT NULL,
                        paddle_subscription_id  TEXT UNIQUE NOT NULL,
                        paddle_transaction_id   TEXT,
                        paddle_customer_id      TEXT NOT NULL,

                        module_id               INTEGER REFERENCES modules(id),
                        tier_id                 INTEGER REFERENCES tiers(id),
                        billing_cycle           TEXT NOT NULL CHECK (billing_cycle IN ('monthly', 'yearly')),

                        base_price_usd          NUMERIC(10,2) NOT NULL,
                        discount_pct            NUMERIC(5,2)  DEFAULT 0,
                        final_price_usd         NUMERIC(10,2) NOT NULL,
                        server_count_at_purchase INTEGER DEFAULT 1,

                        status                  TEXT NOT NULL DEFAULT 'active'
                                                    CHECK (status IN ('active','past_due','canceled','paused','trialing')),
                        current_period_start    TIMESTAMPTZ,
                        current_period_end      TIMESTAMPTZ,
                        canceled_at             TIMESTAMPTZ,
                        cancel_at_period_end    BOOLEAN DEFAULT FALSE,

                        created_at              TIMESTAMPTZ DEFAULT NOW(),
                        updated_at              TIMESTAMPTZ DEFAULT NOW(),

                        CONSTRAINT sub_must_have_module_or_tier
                            CHECK (module_id IS NOT NULL OR tier_id IS NOT NULL)
                    )
                ''')
                print("  ✅ Created/verified table: subscriptions")

                # ----- guild_module_access -----
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS guild_module_access (
                        id              SERIAL PRIMARY KEY,
                        guild_id        BIGINT  NOT NULL,
                        module_id       INTEGER NOT NULL REFERENCES modules(id),
                        subscription_id INTEGER NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
                        discord_id      TEXT    NOT NULL,
                        is_active       BOOLEAN DEFAULT TRUE,
                        granted_at      TIMESTAMPTZ DEFAULT NOW(),
                        revoked_at      TIMESTAMPTZ,

                        UNIQUE(guild_id, module_id, subscription_id)
                    )
                ''')
                print("  ✅ Created/verified table: guild_module_access")

                # ----- payment_transactions -----
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS payment_transactions (
                        id                      SERIAL PRIMARY KEY,
                        paddle_transaction_id   TEXT UNIQUE NOT NULL,
                        paddle_subscription_id  TEXT,
                        paddle_customer_id      TEXT,
                        discord_id              TEXT,
                        guild_id                BIGINT,
                        amount_usd              NUMERIC(10,2),
                        currency                TEXT DEFAULT 'USD',
                        status                  TEXT,
                        transaction_type        TEXT,
                        raw_payload             JSONB,
                        created_at              TIMESTAMPTZ DEFAULT NOW()
                    )
                ''')
                print("  ✅ Created/verified table: payment_transactions")

                # ----- paddle_webhook_events -----
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS paddle_webhook_events (
                        id              SERIAL PRIMARY KEY,
                        event_id        TEXT UNIQUE NOT NULL,
                        event_type      TEXT NOT NULL,
                        payload         JSONB NOT NULL,
                        processed       BOOLEAN DEFAULT FALSE,
                        processing_error TEXT,
                        received_at     TIMESTAMPTZ DEFAULT NOW(),
                        processed_at    TIMESTAMPTZ
                    )
                ''')
                print("  ✅ Created/verified table: paddle_webhook_events")

                # ----- refunds -----
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS refunds (
                        id                      SERIAL PRIMARY KEY,
                        paddle_transaction_id   TEXT NOT NULL,
                        paddle_subscription_id  TEXT,
                        discord_id              TEXT,
                        guild_id                BIGINT,
                        amount_usd              NUMERIC(10,2),
                        reason                  TEXT,
                        refunded_at             TIMESTAMPTZ DEFAULT NOW()
                    )
                ''')
                print("  ✅ Created/verified table: refunds")

                # ----- indexes for paddle tables -----
                paddle_index_queries = [
                    'CREATE INDEX IF NOT EXISTS idx_subscriptions_discord ON subscriptions(discord_id)',
                    'CREATE INDEX IF NOT EXISTS idx_subscriptions_guild ON subscriptions(guild_id)',
                    'CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status)',
                    'CREATE INDEX IF NOT EXISTS idx_subscriptions_module ON subscriptions(module_id)',
                    'CREATE INDEX IF NOT EXISTS idx_guild_module_access_guild ON guild_module_access(guild_id)',
                    'CREATE INDEX IF NOT EXISTS idx_guild_module_access_active ON guild_module_access(guild_id, module_id, is_active)',
                ]
                for query in paddle_index_queries:
                    try:
                        await conn.execute(query)
                    except asyncpg.exceptions.PostgresError as e:
                        print(f"  ⚠️ Could not create index: {e}")
                print("  ✅ Paddle indexes checked/created")

                # ----- seed: modules -----
                # Pricing rule: yearly = monthly x 10 (2 months free, ~16.7% off)
                optimization_monthly = 2.49
                optimization_yearly = round(optimization_monthly * 10, 2)  # 24.90

                await conn.execute('''
                    INSERT INTO modules (
                        module_key, display_name, description, module_number,
                        monthly_price_usd, yearly_price_usd,
                        paddle_product_id, paddle_monthly_price_id, paddle_yearly_price_id
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9
                    ) ON CONFLICT (module_key) DO NOTHING
                ''',
                    'optimization',
                    'Optimization+',
                    'Unlock scheduled resets, custom time periods, unlimited history syncs and indefinite data storage.',
                    '1.1',
                    optimization_monthly,
                    optimization_yearly,
                    'pro_01kv2cxndcxkfgrzzd8ay3tb11',
                    'pri_01kv2czhp9jn6kd489rmtqgqg9',
                    'pri_01kv2cyny93van4n4gjz58gayv'
                )
                print(f"  ✅ Seeded module: optimization (monthly=${optimization_monthly}, yearly=${optimization_yearly})")

                # ----- seed: multi-server discounts -----
                discount_rows = [
                    (2,  5, 'dsc_01kv2d0jq5sw5m51gsk80sggzw'),
                    (3, 10, 'dsc_01kv2d149rm948wrmnh4w3ted3'),
                    (4, 15, 'dsc_01kv2d1kqteswvfbe5j3yqjh19'),
                    (5, 20, 'dsc_01kv2d20r8rrnr9ghsd1jza5p9'),
                    (6, 25, 'dsc_01kv2d2d559d0c4sn3zs41y38k'),
                    (7, 30, 'dsc_01kv2d2s0q9z5gyvpk2zcyqcbd'),
                    (8, 35, 'dsc_01kv2d3ab0a1wfam7zyjaz2brb'),
                    (9, 40, 'dsc_01kv2d3mz7tjn3pdmv967tyqnf'),
                    (10, 45, 'dsc_01kv2d3y5eq5qeaq9tvjeq4h09'),
                    (11, 50, 'dsc_01kv2d47wvdzc65cy8ay731z9s'),
                ]
                for server_count, discount_pct, paddle_discount_id in discount_rows:
                    await conn.execute('''
                        INSERT INTO server_count_discounts (server_count, discount_pct, paddle_discount_id)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (server_count) DO NOTHING
                    ''', server_count, discount_pct, paddle_discount_id)
                print("  ✅ Seeded multi-server discounts")

                # ===== ADD PRIMARY KEYS AND CONSTRAINTS =====
                print("\n" + "="*60)
                print("🔑 ADDING PRIMARY KEYS AND CONSTRAINTS")
                print("="*60)

                constraints = [
                    ('message_tracking_hourly_pkey', 'message_tracking_hourly',
                     '(guild_id, user_id, channel_id, hour)'),
                    ('voice_session_history_hourly_pkey', 'voice_session_history_hourly',
                     '(guild_id, user_id, channel_id, hour, state_flags)'),
                    ('emoji_usage_hourly_pkey', 'emoji_usage_hourly',
                     '(guild_id, user_id, channel_id, emoji_str, usage_type, hour)'),
                    ('user_mentions_hourly_pkey', 'user_mentions_hourly',
                     '(guild_id, mentioned_user_id, mentioner_user_id, channel_id, hour)'),
                    ('activity_sessions_hourly_pkey', 'activity_sessions_hourly',
                     '(guild_id, user_id, activity_name, activity_type, hour)'),
                    ('role_growth_hourly_pkey', 'role_growth_hourly',
                     '(guild_id, role_id, user_id, hour)'),
                    ('member_joins_hourly_pkey', 'member_joins_hourly',
                     '(guild_id, user_id, hour)'),
                    ('member_leaves_hourly_pkey', 'member_leaves_hourly',
                     '(guild_id, user_id, hour)'),
                    ('slash_commands_daily_pkey', 'slash_commands_daily',
                     '(guild_id, command_name, day)')
                ]

                for constraint_name, table, columns in constraints:
                    await conn.execute(f'''
                        DO $$
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1 FROM information_schema.table_constraints 
                                WHERE constraint_name = '{constraint_name}' AND table_name = '{table}'
                            ) THEN
                                ALTER TABLE {table} ADD PRIMARY KEY {columns};
                            END IF;
                        END $$;
                    ''')
                    print(f"  ✅ Added/verified primary key to {table}")

                # ===== ALTER EXISTING TABLES TO ADD MISSING COLUMNS =====
                print("\n" + "="*60)
                print("🔄 ALTERING TABLES TO ADD MISSING COLUMNS")
                print("="*60)

                alter_queries = [
                    "ALTER TABLE user_mentions_hourly ADD COLUMN IF NOT EXISTS encrypted_mentioned_username TEXT",
                    "ALTER TABLE message_tracking_hourly ADD COLUMN IF NOT EXISTS encrypted_username TEXT",
                    "ALTER TABLE voice_session_history_hourly ADD COLUMN IF NOT EXISTS encrypted_username TEXT",
                    "ALTER TABLE emoji_usage_hourly ADD COLUMN IF NOT EXISTS encrypted_username TEXT",
                    "ALTER TABLE activity_sessions_hourly ADD COLUMN IF NOT EXISTS encrypted_username TEXT",
                    "ALTER TABLE role_growth_hourly ADD COLUMN IF NOT EXISTS encrypted_username TEXT",
                    "ALTER TABLE member_joins_hourly ADD COLUMN IF NOT EXISTS encrypted_username TEXT",
                    "ALTER TABLE member_leaves_hourly ADD COLUMN IF NOT EXISTS encrypted_username TEXT",
                    "ALTER TABLE slash_commands_daily ADD COLUMN IF NOT EXISTS encrypted_username TEXT",
                    "ALTER TABLE invite_tracking ADD COLUMN IF NOT EXISTS encrypted_username TEXT",
                ]

                for query in alter_queries:
                    try:
                        await conn.execute(query)
                    except Exception as e:
                        print(f"  ⚠️ Warning setting column: {e}")
                print("  ✅ All column extensions checked")

                try:
                    await conn.execute("""
                        DO $$
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1 FROM information_schema.check_constraints WHERE constraint_name = 'valid_time_mode'
                            ) THEN
                                ALTER TABLE settings ADD CONSTRAINT valid_time_mode CHECK (default_time_mode IN ('all_time', 'days_back', 'date_range', 'rolling_window'));
                            END IF;
                        END $$;
                    """)
                    print("  ✅ Added/verified CHECK constraint: valid_time_mode")
                except Exception as e:
                    print(
                        f"  ⚠️ Warning: Could not add valid_time_mode constraint: {e}")

                # ===== CREATE INDEXES =====
                print("\n" + "="*60)
                print("📊 CREATING INDEXES")
                print("="*60)

                hourly_index_queries = [
                    'CREATE INDEX IF NOT EXISTS idx_message_hourly_guild_hour ON message_tracking_hourly(guild_id, hour)',
                    'CREATE INDEX IF NOT EXISTS idx_message_hourly_guild_user_hour ON message_tracking_hourly(guild_id, user_id, hour)',
                    'CREATE INDEX IF NOT EXISTS idx_message_hourly_guild_channel_hour ON message_tracking_hourly(guild_id, channel_id, hour)',
                    'CREATE INDEX IF NOT EXISTS idx_message_hourly_guild_category_hour ON message_tracking_hourly(guild_id, category_id, hour)',
                    'CREATE INDEX IF NOT EXISTS idx_voice_hourly_guild_hour ON voice_session_history_hourly(guild_id, hour)',
                    'CREATE INDEX IF NOT EXISTS idx_voice_hourly_guild_user_hour ON voice_session_history_hourly(guild_id, user_id, hour)',
                    'CREATE INDEX IF NOT EXISTS idx_voice_hourly_guild_channel_hour ON voice_session_history_hourly(guild_id, channel_id, hour)',
                    'CREATE INDEX IF NOT EXISTS idx_voice_hourly_guild_category_hour ON voice_session_history_hourly(guild_id, category_id, hour)',
                    'CREATE INDEX IF NOT EXISTS idx_voice_hourly_state_flags ON voice_session_history_hourly(state_flags, hour)',
                    'CREATE INDEX IF NOT EXISTS idx_emoji_hourly_guild_hour ON emoji_usage_hourly(guild_id, hour)',
                    'CREATE INDEX IF NOT EXISTS idx_emoji_hourly_guild_user_hour ON emoji_usage_hourly(guild_id, user_id, hour)',
                    'CREATE INDEX IF NOT EXISTS idx_mentions_hourly_guild_hour ON user_mentions_hourly(guild_id, hour)',
                    'CREATE INDEX IF NOT EXISTS idx_mentions_hourly_guild_mentioned_hour ON user_mentions_hourly(guild_id, mentioned_user_id, hour)',
                    'CREATE INDEX IF NOT EXISTS idx_mentions_hourly_guild_mentioner_hour ON user_mentions_hourly(guild_id, mentioner_user_id, hour)',
                    'CREATE INDEX IF NOT EXISTS idx_slash_daily_guild_day ON slash_commands_daily(guild_id, day)',
                    'CREATE INDEX IF NOT EXISTS idx_role_growth_hourly_guild_hour ON role_growth_hourly(guild_id, hour)',
                    'CREATE INDEX IF NOT EXISTS idx_role_growth_role_hour ON role_growth_hourly(role_id, hour)',
                    'CREATE INDEX IF NOT EXISTS idx_role_growth_composite ON role_growth_hourly(guild_id, role_id, hour)',
                    'CREATE INDEX IF NOT EXISTS idx_joins_hourly_guild_hour ON member_joins_hourly(guild_id, hour)',
                    'CREATE INDEX IF NOT EXISTS idx_leaves_hourly_guild_hour ON member_leaves_hourly(guild_id, hour)',
                ]

                for query in hourly_index_queries:
                    try:
                        await conn.execute(query)
                    except asyncpg.exceptions.PostgresError as e:
                        print(f"  ⚠️ Could not create index: {e}")
                print("  ✅ All indexes checked/created")

                # ===== CREATE HYPERTABLES =====
                print("\n" + "="*60)
                print("📈 CREATING HYPERTABLES")
                print("="*60)

                hypertable_configs = [
                    ('message_tracking_hourly', 'hour'),
                    ('voice_session_history_hourly', 'hour'),
                    ('emoji_usage_hourly', 'hour'),
                    ('user_mentions_hourly', 'hour'),
                    ('activity_sessions_hourly', 'hour'),
                    ('role_growth_hourly', 'hour'),
                    ('member_joins_hourly', 'hour'),
                    ('member_leaves_hourly', 'hour'),
                    ('slash_commands_daily', 'day')
                ]

                for table_name, time_col in hypertable_configs:
                    try:
                        await conn.execute(f"SELECT create_hypertable('{table_name}', '{time_col}', if_not_exists => TRUE)")
                        print(
                            f"  ✅ Hypertable ready: {table_name} (on column: {time_col})")
                    except Exception as e:
                        print(
                            f"  ⚠️ Error registering hypertable {table_name}: {e}")

                # ===== PURGE RETENTION POLICIES =====
                print("\n" + "="*60)
                print("🗑️ PURGING ALL RETENTION POLICIES")
                print("="*60)

                for table_name, _ in hypertable_configs:
                    try:
                        await conn.execute(f"SELECT remove_retention_policy('{table_name}', if_exists => true)")
                        print(
                            f"  🗑️ Safely dropped retention policy for: {table_name}")
                    except Exception as e:
                        print(
                            f"  ⚠️ Could not drop retention policy on {table_name}: {e}")

                # ===== CONFIGURE COMPRESSION POLICIES =====
                print("\n" + "="*60)
                print("🤐 CONFIGURING COMPRESSION POLICIES")
                print("="*60)

                compression_configs = [
                    ('message_tracking_hourly', 'hour'),
                    ('voice_session_history_hourly', 'hour'),
                    ('emoji_usage_hourly', 'hour'),
                    ('user_mentions_hourly', 'hour'),
                    ('activity_sessions_hourly', 'hour'),
                    ('role_growth_hourly', 'hour'),
                    ('member_joins_hourly', 'hour'),
                    ('member_leaves_hourly', 'hour'),
                    ('slash_commands_daily', 'day')
                ]

                for table_name, time_col in compression_configs:
                    try:
                        await conn.execute(f"""
                            ALTER TABLE {table_name} SET (
                                timescaledb.compress,
                                timescaledb.compress_segmentby = 'guild_id',
                                timescaledb.compress_orderby = '{time_col} DESC'
                            )
                        """)

                        await conn.execute(f"""
                            SELECT add_compression_policy('{table_name}', INTERVAL '14 days', if_not_exists => true)
                        """)
                        print(
                            f"  ✅ Compression policy configured for: {table_name}")
                    except Exception as e:
                        print(f"  ⚠️ Compression error on {table_name}: {e}")

            return True

        except Exception as e:
            print(f"❌ Critical database initialization failure: {e}")
            return False

    # ======================================================================
    # SHUTDOWN - FIXED EXCEPTION HANDLING
    # ======================================================================

    async def cog_unload(self):
        async with self.shutdown_lock:
            self.shutting_down = True

        # Cancel loop tasks
        loop_tasks = [
            self.voice_activity_tracker,
            self.connection_pool_health_check,
            self.init_pools,
            self.metrics_reset_task,
            self.redis_batch_flusher,
        ]
        if hasattr(self, 'channel_sync_cron'):
            self.channel_sync_cron.stop()
        if hasattr(self, 'guild_check_cron'):
            self.guild_check_cron.stop()
        if hasattr(self, 'permission_sync_cron'):
            self.permission_sync_cron.stop()
        if hasattr(self, 'role_filter_sync_cron'):
            self.role_filter_sync_cron.stop()
        if hasattr(self, 'streak_update_cron'):
            self.streak_update_cron.stop()
        if hasattr(self, 'server_count_cron'):
            self.server_count_cron.stop()

        for task in loop_tasks:
            if task and task.is_running():
                task.cancel()

        # Cancel asyncio task separately
        if self.cleanup_task and not self.cleanup_task.done():
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass

        try:
            await asyncio.wait_for(
                asyncio.gather(
                    *[task for task in loop_tasks if task and task.is_running()],
                    return_exceptions=True
                ),
                timeout=Constants.SHUTDOWN_TIMEOUT
            )
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass
        except Exception:
            pass

        try:
            await self._flush_all_batches_to_postgresql()
        except Exception:
            pass

        try:
            await self._cleanup_all_voice_sessions()
        except Exception:
            pass

        close_tasks = []
        if self.pool:
            close_tasks.append(self.pool.close())
        if self.redis:
            close_tasks.append(self.redis.close())

        if close_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*close_tasks, return_exceptions=True),
                    timeout=10
                )
            except (asyncio.TimeoutError, Exception):
                pass

        try:
            await self._cleanup_all_memory()
        except Exception:
            pass

        # Clean up invite tracking state
        # Check each lock before deleting in case a join event is mid-flight
        for guild_id in list(self.invite_snapshot_locks.keys()):
            lock = self.invite_snapshot_locks.get(guild_id)
            if lock is not None and lock.locked():
                # A join is still in progress - wait briefly for it to finish
                try:
                    await asyncio.wait_for(lock.acquire(), timeout=5.0)
                    lock.release()
                except asyncio.TimeoutError:
                    pass

        self.invite_snapshot_locks.clear()
        self.invite_snapshots.clear()

    async def _cleanup_all_memory(self):
        """Clean up all memory caches."""
        try:
            self.processed_messages.clear()
            self.rate_limits.clear()
            self.invite_locks.clear()

            async with self.voice_lock:
                self.active_voice_sessions.clear()
        except Exception as e:
            raise DatabaseQueryError(
                "Failed to clean up memory caches",
                context={'operation': '_cleanup_all_memory'},
                original=e
            )

    async def _cleanup_all_voice_sessions(self):
        """Clean up all active voice sessions."""
        async with self.voice_lock:
            sessions_copy = copy.deepcopy(self.active_voice_sessions)
            self.active_voice_sessions.clear()

        current_time = datetime.now(timezone.utc)
        for user_id, session_data in sessions_copy.items():
            try:
                duration = int(
                    (current_time - session_data['join_time']).total_seconds())
                if duration > 0:
                    await self._record_voice_session_history_direct(
                        guild_id=session_data['guild_id'],
                        user_id=user_id,
                        channel_id=session_data['channel_id'],
                        join_time=session_data['join_time'],
                        leave_time=current_time,
                        duration=duration,
                        state_flags=self._calculate_state_flags(session_data)
                    )
            except Exception as e:
                # Don't raise during cleanup - just continue
                continue

    # ======================================================================
    # DATABASE CONNECTION RETRY - FIXED EXCEPTION HANDLING
    # ======================================================================

    @tasks.loop(minutes=5, count=None)
    async def init_pools(self):
        """Initialize database and Redis connection pools with production-safe retry logic."""
        if self.shutting_down:
            return

        if self.db_connected and self.pool and self.redis_connected and self.redis:
            return

        # PostgreSQL connection with retry logic
        MAX_ATTEMPTS = 10
        BASE_DELAY = 1.0
        MAX_DELAY = 10.0

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                # Attempt to create the pool
                self.pool = await asyncpg.create_pool(
                    host=os.getenv('DB_HOST'),
                    database=os.getenv('DB_NAME'),
                    user=os.getenv('DB_USER'),
                    password=os.getenv('DB_PASSWORD'),
                    port=int(os.getenv('DB_PORT')),
                    min_size=5,
                    max_size=20,
                    command_timeout=30
                )

                # Immediately verify connection with SELECT 1
                async with self.pool.acquire() as conn:
                    await conn.fetchval('SELECT 1')

                # Success - log and break retry loop
                self.db_connected = True
                print(
                    f"✅ PostgreSQL connection established on attempt {attempt}")
                break

            except asyncpg.exceptions.PostgresError as e:
                self.db_connected = False
                if attempt == MAX_ATTEMPTS:
                    raise DatabaseConnectionError(
                        f"Failed to connect to PostgreSQL after {MAX_ATTEMPTS} attempts",
                        context={'operation': 'init_pools',
                                 'attempt': attempt},
                        original=e
                    )

                # Exponential backoff with cap
                delay = min(BASE_DELAY * (2 ** (attempt - 1)), MAX_DELAY)
                print(f"⚠️ PostgreSQL attempt {attempt} failed: {e}")
                print(f"   Retrying in {delay:.2f}s...")
                await asyncio.sleep(delay)

        # Continue with Redis connection (unchanged from your original)
        try:
            redis_host = os.getenv('REDIS_HOST', 'redis')
            redis_port = int(os.getenv('REDIS_PORT', '6379'))
            redis_password = os.getenv('REDIS_PASSWORD')
            redis_db = int(os.getenv('REDIS_DB', '0'))

            if redis_password:
                redis_url = f"redis://:{redis_password}@{redis_host}:{redis_port}/{redis_db}"
            else:
                redis_url = f"redis://{redis_host}:{redis_port}/{redis_db}"

            self.redis = Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
                retry_on_timeout=True,
                encoding='utf-8'
            )

            await self.redis.ping()
            self.redis_connected = True

        except RedisConnectionError as e:
            raise CacheConnectionError(
                "Failed to connect to Redis",
                context={'host': redis_host, 'port': redis_port},
                original=e
            )
        except RedisTimeoutError as e:
            raise CacheTimeoutError(
                "Redis connection timed out",
                context={'host': redis_host, 'port': redis_port},
                original=e
            )
        except RedisError as e:
            raise CacheConnectionError(
                "Redis error during connection",
                context={'host': redis_host, 'port': redis_port},
                original=e
            )

        # Encryption initialization (unchanged)
        fernet_key = os.getenv('FERNET_KEY')
        if fernet_key:
            try:
                fernet_key = fernet_key.strip()
                try:
                    self.fernet = Fernet(fernet_key.encode())
                    print(
                        f"✅ Fernet initialized successfully, self.fernet = {self.fernet is not None}")
                except (ValueError, TypeError):
                    key_hash = hashlib.sha256(fernet_key.encode()).digest()
                    valid_key = base64.urlsafe_b64encode(key_hash)
                    self.fernet = Fernet(valid_key)
            except Exception as e:
                raise CacheSerializationError(
                    "Failed to initialize Fernet encryption",
                    context={'operation': 'init_pools'},
                    original=e
                )

        # Initialize database schema if this is a fresh connection
        if not self.is_timescale_initialized:
            success = await self.initialize_database()
            if success:
                self.is_timescale_initialized = True
                asyncio.create_task(self.startup_sync_all_guilds())

    # ======================================================================
    # HELPER METHODS - FIXED EXCEPTION HANDLING
    # ======================================================================

    def _calculate_state_flags(self, session_data: Dict[str, Any]) -> int:
        """Calculate state flags from session data."""
        state_flags = 0

        if session_data.get('is_afk_channel'):
            state_flags |= self.voice_state_bits['afk_channel']
        if session_data.get('server_mute'):
            state_flags |= self.voice_state_bits['server_mute']
        if session_data.get('server_deaf'):
            state_flags |= self.voice_state_bits['server_deaf']
        if session_data.get('self_mute'):
            state_flags |= self.voice_state_bits['self_mute']
        if session_data.get('self_deaf'):
            state_flags |= self.voice_state_bits['self_deaf']
        if session_data.get('streaming'):
            state_flags |= self.voice_state_bits['streaming']
        if session_data.get('video'):
            state_flags |= self.voice_state_bits['video']
        if session_data.get('suppressed'):
            state_flags |= self.voice_state_bits['suppressed']

        return state_flags

    async def _save_voice_session(self, guild_id: int, user_id: int, member: Optional[discord.Member],
                                  session_data: Dict[str, Any], leave_time: datetime, duration: int):
        """Save discrete voice session chunk to aggregated table."""
        channel_id = session_data.get('channel_id', 0)
        category_id = session_data.get('category_id')

        if member:
            encrypted_username = self.encrypt_username(str(member))
            is_bot = member.bot
        else:
            encrypted_username = self.encrypt_username(
                f"Unknown User {user_id}")
            is_bot = False

        state_flags = self._calculate_state_flags(session_data)

        was_muted = bool(session_data.get('server_mute', False)
                         or session_data.get('self_mute', False))
        was_deafened = bool(session_data.get(
            'server_deaf', False) or session_data.get('self_deaf', False))
        was_streaming = bool(session_data.get('streaming', False))
        was_video = bool(session_data.get('video', False))

        # Use the last join time or the original join time
        join_time = session_data.get(
            'last_join_time', session_data['join_time'])
        join_time = ensure_aware(join_time)
        leave_time = ensure_aware(leave_time)
        hour = join_time.replace(minute=0, second=0, microsecond=0)
        hour = ensure_aware(hour)

        # 👇 FIXED: Include state_category at index 9
        params = [
            guild_id,                    # 0
            user_id,                     # 1
            channel_id,                  # 2
            category_id,                 # 3
            encrypted_username,          # 4
            join_time,                   # 5
            leave_time,                  # 6
            duration,                    # 7
            state_flags,                 # 8
            session_data.get('state_category', 'normal'),  # 9 👈 ADD THIS!
            was_muted,                   # 10
            was_deafened,                # 11
            was_streaming,               # 12
            was_video,                   # 13
            is_bot,                      # 14
            hour                         # 15
        ]

        # Ensure correct parameter count
        while len(params) < 16:  # 👈 Changed from 15 to 16
            params.append(None)
        params = params[:16]  # 👈 Changed from 15 to 16

        await self.redis_batch_write('voice_sessions', {'params': params})

    async def _record_voice_session_history_direct(self, guild_id: int, user_id: int, channel_id: int,
                                                   join_time: datetime, leave_time: datetime,
                                                   duration: int, state_flags: int) -> bool:
        """Record voice session directly to database (aggregated table)."""
        try:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return False

            member = guild.get_member(user_id)
            if not member:
                return False

            encrypted_username = self.encrypt_username(str(member))
            category_id = None

            channel = guild.get_channel(channel_id)
            if channel and hasattr(channel, 'category_id') and channel.category_id:
                category_id = channel.category_id

            join_time = ensure_aware(join_time)
            leave_time = ensure_aware(leave_time)
            hour = join_time.replace(minute=0, second=0, microsecond=0)
            hour = ensure_aware(hour)
            is_bot = member.bot

            was_muted = bool(state_flags & self.voice_state_bits['self_mute'] or
                             state_flags & self.voice_state_bits['server_mute'])
            was_deafened = bool(state_flags & self.voice_state_bits['self_deaf'] or
                                state_flags & self.voice_state_bits['server_deaf'])
            was_streaming = bool(
                state_flags & self.voice_state_bits['streaming'])
            was_video = bool(state_flags & self.voice_state_bits['video'])

            async with self.pool.acquire() as conn:
                try:
                    await conn.execute('''
                        INSERT INTO voice_session_history_hourly 
                        (hour, guild_id, user_id, channel_id, category_id,
                         total_seconds, session_count, state_flags,
                         was_muted_count, was_deafened_count, was_streaming_count, was_video_count,
                         is_bot)
                        VALUES ($1, $2, $3, $4, $5, $6, 1, $7, $8, $9, $10, $11, $12)
                        ON CONFLICT (guild_id, user_id, channel_id, hour, state_flags) 
                        DO UPDATE SET 
                            total_seconds = voice_session_history_hourly.total_seconds + $6,
                            session_count = voice_session_history_hourly.session_count + 1,
                            was_muted_count = voice_session_history_hourly.was_muted_count + $8,
                            was_deafened_count = voice_session_history_hourly.was_deafened_count + $9,
                            was_streaming_count = voice_session_history_hourly.was_streaming_count + $10,
                            was_video_count = voice_session_history_hourly.was_video_count + $11
                    ''', hour, guild_id, user_id, channel_id, category_id,
                                       duration, state_flags,
                                       1 if was_muted else 0,
                                       1 if was_deafened else 0,
                                       1 if was_streaming else 0,
                                       1 if was_video else 0,
                                       is_bot)
                except asyncpg.exceptions.PostgresError as e:
                    raise DatabaseQueryError(
                        "Failed to record voice session directly",
                        context={
                            'guild_id': guild_id,
                            'user_id': user_id,
                            'channel_id': channel_id
                        },
                        original=e
                    )

            return True

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while recording voice session",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while recording voice session",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while recording voice session",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Database error recording voice session",
                    context={'guild_id': guild_id, 'user_id': user_id},
                    original=e
                )
            raise
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error recording voice session",
                    context={'guild_id': guild_id, 'user_id': user_id},
                    original=e
                )
            raise

    def encrypt_username(self, username: str) -> Optional[str]:
        """Encrypt username for privacy."""
        if not username:
            return None

        if not self.fernet:
            return hashlib.sha256(username.encode()).hexdigest()[:32]

        try:
            return self.fernet.encrypt(username.encode()).decode()
        except Exception as e:
            # Fallback to hash on encryption error
            return hashlib.sha256(username.encode()).hexdigest()[:32]

    def decrypt_username(self, encrypted: Optional[str]) -> Optional[str]:
        """Decrypt username if possible."""
        if not encrypted or not self.fernet:
            return encrypted if encrypted else None

        try:
            # Strip whitespace and newlines
            encrypted = encrypted.strip()

            # Try to decode
            decrypted = self.fernet.decrypt(encrypted.encode())
            return decrypted.decode()
        except Exception as e:
            print(f"Decrypt failed for {encrypted[:50]}...: {e}")
            return None

    async def get_decrypted_mentioned_username(self, guild_id: int, user_id: int) -> Optional[str]:
        """Get decrypted username for a mentioned user."""
        if not self.pool:
            return None

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow('''
                    SELECT encrypted_mentioned_username
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 AND mentioned_user_id = $2
                    AND encrypted_mentioned_username IS NOT NULL
                    LIMIT 1
                ''', guild_id, user_id)

                if row and row['encrypted_mentioned_username']:
                    return self.decrypt_username(row['encrypted_mentioned_username'])
        except Exception as e:
            print(f"Error getting mentioned username for {user_id}: {e}")

        return None

    async def get_decrypted_username_any_table(self, guild_id: int, user_id: int) -> Optional[str]:
        """Get decrypted username by trying all relevant tables."""
        # Try messages table first
        username = await self.get_decrypted_username_from_messages(guild_id, user_id)
        if username and not username.startswith('User '):
            return username

        # Try voice table
        username = await self.get_decrypted_username_from_voice(guild_id, user_id)
        if username and not username.startswith('User '):
            return username

        # Try emojis table
        username = await self.get_decrypted_username_from_emojis(guild_id, user_id)
        if username and not username.startswith('User '):
            return username

        # Try activity table
        username = await self.get_decrypted_username_from_activity(guild_id, user_id)
        if username and not username.startswith('User '):
            return username

        return None

    async def get_decrypted_username_from_messages(self, guild_id: int, user_id: int) -> Optional[str]:
        """Get decrypted username from messages table."""
        if not self.pool:
            return None

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow('''
                    SELECT encrypted_username
                    FROM message_tracking_hourly
                    WHERE guild_id = $1 AND user_id = $2
                    AND encrypted_username IS NOT NULL
                    LIMIT 1
                ''', guild_id, user_id)

                if row and row['encrypted_username']:
                    return self.decrypt_username(row['encrypted_username'])
        except Exception as e:
            print(f"Error getting username from messages for {user_id}: {e}")

        return None

    async def get_decrypted_username_from_voice(self, guild_id: int, user_id: int) -> Optional[str]:
        """Get decrypted username from voice table."""
        if not self.pool:
            return None

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow('''
                    SELECT encrypted_username
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1 AND user_id = $2
                    AND encrypted_username IS NOT NULL
                    LIMIT 1
                ''', guild_id, user_id)

                if row and row['encrypted_username']:
                    return self.decrypt_username(row['encrypted_username'])
        except Exception as e:
            print(f"Error getting username from voice for {user_id}: {e}")

        return None

    async def get_decrypted_username_from_emojis(self, guild_id: int, user_id: int) -> Optional[str]:
        """Get decrypted username from emojis table."""
        if not self.pool:
            return None

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow('''
                    SELECT encrypted_username
                    FROM emoji_usage_hourly
                    WHERE guild_id = $1 AND user_id = $2
                    AND encrypted_username IS NOT NULL
                    LIMIT 1
                ''', guild_id, user_id)

                if row and row['encrypted_username']:
                    return self.decrypt_username(row['encrypted_username'])
        except Exception as e:
            print(f"Error getting username from emojis for {user_id}: {e}")

        return None

    async def get_decrypted_username_from_activity(self, guild_id: int, user_id: int) -> Optional[str]:
        """Get decrypted username from activity table."""
        if not self.pool:
            return None

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow('''
                    SELECT encrypted_username
                    FROM activity_sessions_hourly
                    WHERE guild_id = $1 AND user_id = $2
                    AND encrypted_username IS NOT NULL
                    LIMIT 1
                ''', guild_id, user_id)

                if row and row['encrypted_username']:
                    return self.decrypt_username(row['encrypted_username'])
        except Exception as e:
            print(f"Error getting username from activity for {user_id}: {e}")

        return None

    async def batch_get_decrypted_usernames_from_messages(self, guild_id: int, user_ids: List[int]) -> Dict[int, str]:
        """Batch get decrypted usernames from messages table."""
        if not self.pool or not user_ids:
            return {user_id: f"User {user_id}" for user_id in user_ids}

        result = {user_id: f"User {user_id}" for user_id in user_ids}

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch('''
                    SELECT DISTINCT ON (user_id) user_id, encrypted_username
                    FROM message_tracking_hourly
                    WHERE guild_id = $1 AND user_id = ANY($2::bigint[])
                    AND encrypted_username IS NOT NULL
                    ORDER BY user_id, hour DESC
                ''', guild_id, user_ids)

                for row in rows:
                    user_id = row['user_id']
                    encrypted = row['encrypted_username']
                    if encrypted:
                        decrypted = self.decrypt_username(encrypted)
                        if decrypted:
                            result[user_id] = decrypted
        except Exception as e:
            print(f"Error batch getting usernames from messages: {e}")

        return result

    async def batch_get_decrypted_usernames_any_table(self, guild_id: int, user_ids: List[int], table: str = 'voice') -> Dict[int, str]:
        """Batch get decrypted usernames from a specific table."""
        if not self.pool or not user_ids:
            return {}

        table_map = {
            'voice': 'voice_session_history_hourly',
            'emojis': 'emoji_usage_hourly',
            'activity': 'activity_sessions_hourly'
        }

        table_name = table_map.get(table, 'voice_session_history_hourly')
        result = {}

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(f'''
                    SELECT DISTINCT ON (user_id) user_id, encrypted_username
                    FROM {table_name}
                    WHERE guild_id = $1 AND user_id = ANY($2::bigint[])
                    AND encrypted_username IS NOT NULL
                    ORDER BY user_id, hour DESC
                ''', guild_id, user_ids)

                for row in rows:
                    user_id = row['user_id']
                    encrypted = row['encrypted_username']
                    if encrypted:
                        decrypted = self.decrypt_username(encrypted)
                        if decrypted:
                            result[user_id] = decrypted
        except Exception as e:
            print(f"Error batch getting usernames from {table}: {e}")

        return result

    def _get_channel_display_name(self, guild_id: int, channel_id: int,
                                  channel_type: str = 'channel') -> str:
        """Get display name for channel/category."""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return f'[Deleted {channel_type.capitalize()}]'

        if channel_type == 'category':
            category = discord.utils.get(guild.categories, id=channel_id)
            if category:
                return f'#{category.name}'
            return '[Deleted Category]'
        else:
            channel = guild.get_channel(channel_id)
            if channel:
                if isinstance(channel, discord.TextChannel):
                    return f'#{channel.name}'
                elif isinstance(channel, discord.VoiceChannel):
                    return f'🔊{channel.name}'
                elif isinstance(channel, discord.StageChannel):
                    return f'🎤{channel.name}'
                return channel.name
            return '[Deleted Channel]'

    def _get_user_display_name(self, guild_id: int, user_id: int) -> str:
        """Get display name for user."""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return '[Unknown User]'

        member = guild.get_member(user_id)
        if member:
            return str(member)
        try:
            user = self.bot.get_user(user_id)
            if user:
                return str(user)
        except:
            pass
        return '[Unknown User]'

    def _serialize_datetime(self, obj: Any) -> Any:
        """Serialize datetime objects for JSON."""
        if isinstance(obj, datetime):
            if obj.tzinfo is None:
                obj = obj.replace(tzinfo=timezone.utc)
            return obj.isoformat()
        elif isinstance(obj, (list, tuple)):
            return [self._serialize_datetime(item) for item in obj]
        elif isinstance(obj, dict):
            return {key: self._serialize_datetime(value) for key, value in obj.items()}
        elif isinstance(obj, date):
            return obj.isoformat()
        return obj

    def _ensure_int(self, value: Any) -> Optional[int]:
        """Ensure value is an integer."""
        if value is None:
            return None
        if isinstance(value, int):
            return value
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    # ======================================================================
    # FILTERS
    # ======================================================================

    async def _apply_bot_filter(self, query: str, params: List, guild_id: int, table_name: str = None) -> Tuple[str, List]:
        """Apply bot filter to query based on guild settings."""
        if not table_name:
            return query, params

        try:
            settings_cog = self.bot.get_cog("Settings")
            if not settings_cog:
                return query, params

            settings = await settings_cog.get_guild_settings(guild_id)
            bot_filter = settings.get('bot_filter', False)

            if not bot_filter:
                return query, params

            tables_with_bot_column = [
                'message_tracking_hourly', 'voice_session_history_hourly', 'emoji_usage_hourly',
                'user_mentions_hourly', 'slash_commands_daily', 'invite_tracking',
                'role_growth_hourly', 'member_joins_hourly', 'member_leaves_hourly',
                'activity_sessions_hourly'
            ]

            if table_name in tables_with_bot_column:
                condition = "is_bot = FALSE"

                # Check if there's already a WHERE clause
                if 'WHERE' in query.upper():
                    # Insert before any ORDER BY, GROUP BY, or LIMIT
                    insert_position = len(query)

                    # Find where to insert (before ORDER BY, GROUP BY, or LIMIT)
                    order_by_pos = query.upper().find('ORDER BY')
                    if order_by_pos != -1 and order_by_pos < insert_position:
                        insert_position = order_by_pos

                    group_by_pos = query.upper().find('GROUP BY')
                    if group_by_pos != -1 and group_by_pos < insert_position:
                        insert_position = group_by_pos

                    limit_pos = query.upper().find('LIMIT')
                    if limit_pos != -1 and limit_pos < insert_position:
                        insert_position = limit_pos

                    # Insert AND condition
                    query = query[:insert_position] + \
                        f" AND {condition} " + query[insert_position:]
                else:
                    # No WHERE clause, add one before ORDER BY/GROUP BY/LIMIT
                    insert_position = len(query)

                    order_by_pos = query.upper().find('ORDER BY')
                    if order_by_pos != -1 and order_by_pos < insert_position:
                        insert_position = order_by_pos

                    group_by_pos = query.upper().find('GROUP BY')
                    if group_by_pos != -1 and group_by_pos < insert_position:
                        insert_position = group_by_pos

                    limit_pos = query.upper().find('LIMIT')
                    if limit_pos != -1 and limit_pos < insert_position:
                        insert_position = limit_pos

                    query = query[:insert_position] + \
                        f" WHERE {condition} " + query[insert_position:]

            return query, params

        except Exception as e:
            raise DatabaseQueryError(
                "Failed to apply bot filter",
                context={
                    'guild_id': guild_id,
                    'table_name': table_name,
                    'operation': '_apply_bot_filter'
                },
                original=e
            )

    async def _apply_voice_state_filter(self, query: str, params: List, guild_id: int, state_flags_column: str = 'state_flags') -> Tuple[str, List]:
        """Apply voice state filter based on guild settings."""
        try:
            settings_cog = self.bot.get_cog("Settings")
            if not settings_cog:
                return query, params

            settings = await settings_cog.get_guild_settings(guild_id)
            voice_states = settings.get('voice_states', [])

            if not voice_states:
                return query, params

            state_bits = {
                'afk': self.voice_state_bits['afk_channel'],
                'self_mute': self.voice_state_bits['self_mute'],
                'self_deafen': self.voice_state_bits['self_deaf'],
                'server_mute': self.voice_state_bits['server_mute'],
                'server_deafen': self.voice_state_bits['server_deaf'],
                'streaming': self.voice_state_bits['streaming'],
                'video': self.voice_state_bits['video'],
                'suppressed': self.voice_state_bits['suppressed']
            }

            allowed_mask = 0
            for state in voice_states:
                if state in state_bits:
                    allowed_mask |= state_bits[state]

            # 👇 FIX: If no states selected, return without filter
            if allowed_mask == 0:
                return query, params

            # 👇 FIX: This condition includes normal sessions (state_flags = 0)
            # AND sessions that have ANY of the selected flags
            condition = f"({state_flags_column} = 0 OR ({state_flags_column} & ${len(params) + 1}) != 0)"

            query_upper = query.upper()
            insert_position = len(query)

            group_by_pos = query_upper.find("GROUP BY")
            if group_by_pos != -1 and group_by_pos < insert_position:
                insert_position = group_by_pos

            order_by_pos = query_upper.find("ORDER BY")
            if order_by_pos != -1 and order_by_pos < insert_position:
                insert_position = order_by_pos

            if 'WHERE' in query_upper[:insert_position]:
                insert_string = f" AND {condition}"
            else:
                insert_string = f" WHERE {condition}"

            query = query[:insert_position].rstrip(
            ) + insert_string + " " + query[insert_position:].lstrip()
            params.append(allowed_mask)

            return query, params

        except Exception as e:
            raise DatabaseQueryError(
                "Failed to apply voice state filter",
                context={
                    'guild_id': guild_id,
                    'operation': '_apply_voice_state_filter'
                },
                original=e
            )

    async def _apply_comprehensive_blacklist_filters(self, guild_id: int, guild: discord.Guild,
                                                     query: str, params: List,
                                                     table_name: str,
                                                     include_users: bool = True,
                                                     include_channels: bool = True,
                                                     specific_channel_id: Optional[int] = None,
                                                     specific_category_id: Optional[int] = None) -> Tuple[Optional[str], List]:
        """Apply comprehensive blacklist filters to a query."""
        try:
            blacklists = await self._get_cached_blacklists(guild_id)

            conditions = []
            param_index = len(params) + 1

            # SPECIAL CASES: Different tables have different user ID column names
            if table_name == 'user_mentions_hourly':
                user_column = 'mentioner_user_id'
            elif table_name == 'invite_tracking':
                # Special handling for invites (need both inviter_id AND invitee_id)
                user_column = None
            else:
                user_column = 'user_id'

            # Handle user blacklisting
            if include_users and blacklists['users']:
                if table_name == 'invite_tracking':
                    # For invite_tracking, filter out records where inviter_id OR invitee_id is blacklisted.
                    # The same $N placeholders are reused for both conditions, so params
                    # must only be extended ONCE (not twice).
                    placeholders = ', '.join([f'${i}' for i in range(
                        param_index, param_index + len(blacklists['users']))])
                    conditions.append(
                        f"(inviter_id NOT IN ({placeholders}) AND invitee_id NOT IN ({placeholders}))")
                    params.extend(blacklists['users'])
                    param_index += len(blacklists['users'])
                elif user_column:
                    # Standard handling for other tables
                    placeholders = ', '.join([f'${i}' for i in range(
                        param_index, param_index + len(blacklists['users']))])
                    conditions.append(f"{user_column} NOT IN ({placeholders})")
                    params.extend(blacklists['users'])
                    param_index += len(blacklists['users'])

            # Handle channel blacklisting (skip for invite_tracking - no channel column)
            if include_channels and not specific_channel_id and blacklists['channels'] and table_name != 'invite_tracking':
                placeholders = ', '.join([f'${i}' for i in range(
                    param_index, param_index + len(blacklists['channels']))])
                conditions.append(f"channel_id NOT IN ({placeholders})")
                params.extend(blacklists['channels'])
                param_index += len(blacklists['channels'])

            # Handle category blacklisting (skip for invite_tracking - no category column)
            if include_channels and not specific_category_id and blacklists['categories'] and table_name != 'invite_tracking':
                placeholders = ', '.join([f'${i}' for i in range(
                    param_index, param_index + len(blacklists['categories']))])
                conditions.append(f"category_id NOT IN ({placeholders})")
                params.extend(blacklists['categories'])
                param_index += len(blacklists['categories'])

            # Add conditions to query if we have any
            if conditions:
                where_clause = " AND ".join(conditions)
                query_upper = query.upper()
                insert_position = len(query)

                where_pos = query_upper.find("WHERE")
                if where_pos != -1:
                    insert_position = where_pos + 5
                    query = query[:insert_position] + " " + \
                        where_clause + " AND" + query[insert_position:]
                else:
                    group_by_pos = query_upper.find("GROUP BY")
                    if group_by_pos != -1:
                        insert_position = group_by_pos
                    else:
                        order_by_pos = query_upper.find("ORDER BY")
                        if order_by_pos != -1:
                            insert_position = order_by_pos

                    query = query[:insert_position].rstrip(
                    ) + " WHERE " + where_clause + " " + query[insert_position:].lstrip()

            return query, params

        except Exception as e:
            raise DatabaseQueryError(
                f"Failed to apply comprehensive blacklist filters",
                context={
                    'guild_id': guild_id,
                    'table_name': table_name,
                    'operation': '_apply_comprehensive_blacklist_filters'
                },
                original=e
            )

    async def get_role_name_from_db(self, guild_id: int, role_id: int) -> Optional[str]:
        if not self.pool:
            return None
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT role_name FROM current_role_members 
                    WHERE role_id = $1 AND guild_id = $2 
                    LIMIT 1
                """, role_id, guild_id)
                return row['role_name'] if row else None
        except:
            return None

    # ======================================================================
    # VOICE SESSION HELPER FUNCTIONS
    # ======================================================================

    async def _get_voice_session_cte(self, base_where: str = "1=1", params: List = None) -> tuple:
        """Return CTE SQL for identifying continuous voice sessions (using aggregated table)."""
        cte = f'''
        WITH hourly_sessions AS (
            SELECT 
                guild_id,
                user_id,
                channel_id,
                category_id,
                hour,
                total_seconds,
                session_count,
                state_flags,
                is_bot
            FROM voice_session_history_hourly vshh
            WHERE {base_where}
        ),
        session_chunks AS (
            SELECT 
                hs.*,
                LAG(hs.hour) OVER (
                    PARTITION BY hs.guild_id, hs.user_id 
                    ORDER BY hs.hour
                ) as prev_hour
            FROM hourly_sessions hs
        ),
        session_groups AS (
            SELECT 
                *,
                CASE 
                    WHEN prev_hour IS NULL 
                        OR EXTRACT(EPOCH FROM (hour - prev_hour)) > 7200  -- 2 hour gap threshold
                    THEN 1
                    ELSE 0
                END as is_new_session
            FROM session_chunks
        ),
        session_ids AS (
            SELECT 
                *,
                SUM(is_new_session) OVER (
                    PARTITION BY guild_id, user_id 
                    ORDER BY hour
                ) as session_number
            FROM session_groups
        ),
        continuous_sessions AS (
            SELECT 
                guild_id,
                user_id,
                channel_id,
                category_id,
                session_number,
                MIN(hour) as session_start,
                MAX(hour) + interval '1 hour' as session_end,  -- Approximate end
                SUM(total_seconds) as session_duration,
                SUM(session_count) as chunk_count
            FROM session_ids
            GROUP BY guild_id, user_id, channel_id, category_id, session_number
        )
        '''
        return cte, params

    async def _build_voice_session_query(self, guild_id: int, filters: Dict = None,
                                         group_by_user: bool = False,
                                         group_by_channel: bool = False,
                                         group_by_category: bool = False,
                                         limit: Optional[int] = None,
                                         include_min_max: bool = False) -> tuple:
        """Build a complete query for voice sessions using hourly aggregated table."""
        filters = filters or {}

        where_clauses = ["guild_id = $1"]
        params = [guild_id]
        param_index = 2

        filter_mapping = [
            ('user_id', 'user_id'),
            ('channel_id', 'channel_id'),
            ('category_id', 'category_id'),
            ('state_flags', 'state_flags'),
            ('start_time', 'hour >=', True),
            ('end_time', 'hour <=', True)
        ]

        for filter_key, sql_key, *extra in filter_mapping:
            if filter_key in filters and filters[filter_key] is not None:
                value = filters[filter_key]
                if isinstance(value, datetime):
                    value = ensure_aware(value)
                if extra and extra[0]:
                    where_clauses.append(f"{sql_key} ${param_index}")
                else:
                    where_clauses.append(f"{sql_key} = ${param_index}")
                params.append(value)
                param_index += 1

        base_where = " AND ".join(where_clauses)
        cte, _ = await self._get_voice_session_cte(base_where, params)

        select_clauses = [
            "SUM(session_duration) as total_seconds",
            "SUM(chunk_count) as session_count",
            "AVG(session_duration) as avg_session_duration"
        ]

        if include_min_max:
            select_clauses.append("MIN(session_start) as first_session")
            select_clauses.append("MAX(session_end) as last_session")

        group_by_clauses = []
        if group_by_user:
            select_clauses.insert(0, "user_id")
            group_by_clauses.append("user_id")

        if group_by_channel:
            select_clauses.insert(0, "channel_id")
            group_by_clauses.append("channel_id")

        if group_by_category:
            select_clauses.insert(0, "category_id")
            group_by_clauses.append("category_id")

        query = cte + '''
        SELECT 
            ''' + ', '.join(select_clauses) + '''
        FROM continuous_sessions
        WHERE 1=1
        '''

        if group_by_clauses:
            query += " GROUP BY " + ", ".join(group_by_clauses)

        query += " HAVING SUM(session_duration) > 0"

        if group_by_user or group_by_channel or group_by_category:
            query += " ORDER BY total_seconds DESC"

        if limit:
            query += f" LIMIT {limit}"

        return query, params

    async def _get_voice_stats_simple(self, guild_id: int, filters: Dict = None) -> Dict[str, Any]:
        """Get basic voice stats for given filters using hourly aggregated table."""
        if not self.pool:
            return {'total_seconds': 0, 'session_count': 0, 'avg_session': 0.0}

        try:
            async with self.pool.acquire() as conn:
                # Simplified query using hourly aggregated table
                base_query = '''
                    SELECT 
                        COALESCE(SUM(total_seconds), 0) as total_seconds,
                        COALESCE(SUM(session_count), 0) as session_count
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1
                '''
                params = [guild_id]

                if filters:
                    if 'user_id' in filters and filters['user_id']:
                        base_query += f" AND user_id = ${len(params) + 1}"
                        params.append(filters['user_id'])

                    if 'channel_id' in filters and filters['channel_id']:
                        base_query += f" AND channel_id = ${len(params) + 1}"
                        params.append(filters['channel_id'])

                    if 'category_id' in filters and filters['category_id']:
                        base_query += f" AND category_id = ${len(params) + 1}"
                        params.append(filters['category_id'])

                    # 👇 ADD VOICE STATE FILTER SUPPORT
                    if 'state_flags' in filters and filters['state_flags'] is not None:
                        base_query += f" AND state_flags = ${len(params) + 1}"
                        params.append(filters['state_flags'])

                    if 'start_time' in filters and filters['start_time']:
                        start_time = ensure_aware(filters['start_time'])
                        base_query += f" AND hour >= ${len(params) + 1}"
                        params.append(start_time)

                    if 'end_time' in filters and filters['end_time']:
                        end_time = ensure_aware(filters['end_time'])
                        base_query += f" AND hour <= ${len(params) + 1}"
                        params.append(end_time)

                try:
                    row = await conn.fetchrow(base_query, *params)
                except asyncpg.exceptions.PostgresError as e:
                    raise DatabaseQueryError(
                        "Failed to fetch voice stats",
                        context={'guild_id': guild_id,
                                 'filters': str(filters)},
                        original=e
                    )

                total_seconds = row['total_seconds'] if row and row['total_seconds'] else 0
                session_count = row['session_count'] if row and row['session_count'] else 0
                avg_session = total_seconds / max(session_count, 1)

                return {
                    'total_seconds': total_seconds,
                    'session_count': session_count,
                    'avg_session': round(avg_session, 2) if avg_session else 0.0
                }

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching voice stats",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching voice stats",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching voice stats",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching voice stats",
                context={'guild_id': guild_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching voice stats",
                    context={'guild_id': guild_id},
                    original=e
                )
            raise

    async def _apply_filters_to_cte(self, guild_id: int, filters: Dict = None,
                                    role_filter_ids: Optional[List[int]] = None,
                                    guild=None) -> Dict:
        """Apply role filters and blacklist filters to create filtered CTE parameters."""
        filters = filters or {}

        if role_filter_ids and guild:
            try:
                user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                if user_ids:
                    if 'user_id' in filters:
                        if filters['user_id'] in user_ids:
                            pass
                        else:
                            return {'user_id': -1}
                    else:
                        filters['_multi_user_ids'] = user_ids
            except Exception as e:
                raise DatabaseQueryError(
                    "Failed to apply role filters",
                    context={'guild_id': guild_id,
                             'role_filter_ids': str(role_filter_ids)},
                    original=e
                )

        return filters

    async def _build_query_with_filters(self, guild_id: int, guild, base_filters: Dict = None,
                                        role_filter_ids: Optional[List[int]] = None,
                                        include_blacklists: bool = True) -> tuple:
        """Build a complete query with all filters applied."""
        filters = base_filters.copy() if base_filters else {}

        try:
            filters = await self._apply_filters_to_cte(guild_id, filters, role_filter_ids, guild)

            if '_multi_user_ids' in filters and not filters['_multi_user_ids']:
                return "SELECT 0 as total_seconds, 0 as session_count, 0 as avg_session_duration", []

            query, params = await self._build_voice_session_query(
                guild_id, filters,
                group_by_user=False,
                group_by_channel=False,
                group_by_category=False,
                include_min_max='start_time' in filters or 'end_time' in filters
            )

            if '_multi_user_ids' in filters:
                user_ids = filters.pop('_multi_user_ids')
                query = query.replace(
                    "WHERE guild_id = $1",
                    f"WHERE guild_id = $1 AND user_id = ANY(${len(params) + 1}::bigint[])"
                )
                params.append(user_ids)

            return query, params

        except Exception as e:
            if not isinstance(e, DatabaseQueryError):
                raise DatabaseQueryError(
                    "Failed to build query with filters",
                    context={'guild_id': guild_id},
                    original=e
                )
            raise

    async def _get_voice_state_filter_value(self, guild_id: int) -> Optional[int]:
        """Get voice state filter value from settings."""
        try:
            settings_cog = self.bot.get_cog("Settings")
            if settings_cog:
                settings = await settings_cog.get_guild_settings(guild_id)
                voice_filter_enabled = settings.get(
                    'voice_state_filter_enabled', False)
                if voice_filter_enabled:
                    voice_filter_value = settings.get(
                        'voice_state_filter_value', 0)
                    return int(voice_filter_value)
        except Exception as e:
            raise DatabaseQueryError(
                "Failed to get voice state filter value",
                context={'guild_id': guild_id},
                original=e
            )

        return None

    # ======================================================================
    # USER STATS - FIXED EXCEPTION HANDLING
    # ======================================================================

    async def q_user_rank_messages(self, guild_id: int, user_id: int,
                                   role_filter_ids: Optional[List[int]] = None,
                                   start_time: Optional[datetime] = None,
                                   end_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Get user's message rank using hourly aggregated table."""
        if not self.pool:
            return {'rank': 0, 'total_users': 0, 'message_count': 0}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {'rank': 0, 'total_users': 0, 'message_count': 0}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = '''
                    SELECT 
                        user_id,
                        SUM(message_count) as message_count,
                        RANK() OVER (ORDER BY SUM(message_count) DESC) as rank
                    FROM message_tracking_hourly
                    WHERE guild_id = $1
                '''
                params = [guild_id]

                query, params = await self._apply_bot_filter(query, params, guild_id, 'message_tracking_hourly')

                if start_time:
                    query += " AND hour >= $2"
                    params.append(start_time)
                    if end_time:
                        query += " AND hour <= $3"
                        params.append(end_time)
                elif end_time:
                    query += " AND hour <= $2"
                    params.append(end_time)

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        placeholders = [
                            f"${len(params) + i + 1}" for i in range(len(user_ids))]
                        query += f" AND user_id IN ({', '.join(placeholders)})"
                        params.extend(user_ids)
                    else:
                        # No users have these roles, return empty result
                        return {'rank': 0, 'total_users': 0, 'message_count': 0}

                query += " GROUP BY user_id HAVING SUM(message_count) > 0 ORDER BY message_count DESC"

                try:
                    rows = await conn.fetch(query, *params)
                except asyncpg.exceptions.PostgresError as e:
                    raise DatabaseQueryError(
                        "Failed to fetch user message rank",
                        context={'guild_id': guild_id, 'user_id': user_id},
                        original=e
                    )

                user_rank = 0
                user_count = 0
                total_users = len(rows)

                for idx, row in enumerate(rows, 1):
                    if row['user_id'] == user_id:
                        user_rank = idx
                        user_count = row['message_count'] or 0
                        break

                return {
                    'rank': user_rank,
                    'total_users': total_users,
                    'message_count': user_count
                }

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching user message rank",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching user message rank",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching user message rank",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching user message rank",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching user message rank",
                    context={'guild_id': guild_id, 'user_id': user_id},
                    original=e
                )
            raise

    async def q_user_rank_voice(self, guild_id: int, user_id: int,
                                role_filter_ids: Optional[List[int]] = None,
                                start_time: Optional[datetime] = None,
                                end_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Get user's voice rank using hourly aggregated table."""
        if not self.pool:
            return {'rank': 0, 'total_users': 0, 'voice_seconds': 0, 'voice_hours': 0.0}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {'rank': 0, 'total_users': 0, 'voice_seconds': 0, 'voice_hours': 0.0}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)
            state_flags_filter = await self._get_voice_state_filter_value(guild_id)

            async with self.pool.acquire() as conn:
                base_where = ["guild_id = $1"]
                params = [guild_id]

                # 👇 ADD VOICE STATE FILTER
                if state_flags_filter is not None:
                    base_where.append(f"state_flags = ${len(params) + 1}")
                    params.append(state_flags_filter)

                if start_time:
                    base_where.append(f"hour >= ${len(params) + 1}")
                    params.append(start_time)
                if end_time:
                    base_where.append(f"hour <= ${len(params) + 1}")
                    params.append(end_time)

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        placeholders = [
                            f"${len(params) + i + 1}" for i in range(len(user_ids))]
                        base_where.append(
                            f"user_id IN ({', '.join(placeholders)})")
                        params.extend(user_ids)
                    else:
                        # No users have these roles, return empty result
                        return {'rank': 0, 'total_users': 0, 'voice_seconds': 0, 'voice_hours': 0.0}

                query = '''
                    SELECT 
                        user_id,
                        SUM(total_seconds) as total_seconds,
                        RANK() OVER (ORDER BY SUM(total_seconds) DESC) as rank
                    FROM voice_session_history_hourly
                    WHERE ''' + " AND ".join(base_where) + '''
                    GROUP BY user_id
                    HAVING SUM(total_seconds) > 0
                    ORDER BY total_seconds DESC
                '''

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'voice_session_history_hourly',
                    include_users=True, include_channels=True
                )

                query, params = await self._apply_bot_filter(query, params, guild_id, 'voice_session_history_hourly')

                try:
                    rows = await conn.fetch(query, *params)
                except asyncpg.exceptions.PostgresError as e:
                    raise DatabaseQueryError(
                        "Failed to fetch user voice rank",
                        context={'guild_id': guild_id, 'user_id': user_id},
                        original=e
                    )

                user_rank = 0
                user_seconds = 0
                total_users = len(rows)

                for idx, row in enumerate(rows, 1):
                    if row['user_id'] == user_id:
                        user_rank = idx
                        user_seconds = row['total_seconds'] or 0
                        break

                return {
                    'rank': user_rank,
                    'total_users': total_users,
                    'voice_seconds': user_seconds,
                    'voice_hours': round(user_seconds / 3600, 2) if user_seconds > 0 else 0.0
                }

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching user voice rank",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching user voice rank",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching user voice rank",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching user voice rank",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching user voice rank",
                    context={'guild_id': guild_id, 'user_id': user_id},
                    original=e
                )
            raise

    async def q_user_timeseries_messages_1d_5d_10d_20d_30d(self, guild_id: int, user_id: int,
                                                           role_filter_ids: Optional[List[int]] = None,
                                                           start_time: Optional[datetime] = None,
                                                           end_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Get user message counts for different time periods using hourly aggregated table."""
        if not self.pool:
            return {'1d': 0, '5d': 0, '10d': 0, '20d': 0, '30d': 0}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {'1d': 0, '5d': 0, '10d': 0, '20d': 0, '30d': 0}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                periods = [1, 5, 10, 20, 30]
                result = {}

                # Get the absolute time bounds if provided
                absolute_end = end_time if end_time else datetime.now(
                    timezone.utc)
                absolute_start = start_time if start_time else (
                    absolute_end - timedelta(days=30))

                for days in periods:
                    # Calculate window relative to the absolute end time
                    window_end = absolute_end
                    window_start = absolute_end - timedelta(days=days)

                    # Ensure we don't go before the absolute start
                    if window_start < absolute_start:
                        window_start = absolute_start

                    # Skip if window is invalid (start after end)
                    if window_start >= window_end:
                        result[f'{days}d'] = 0
                        continue

                    query = '''
                        SELECT COALESCE(SUM(message_count), 0) as message_count
                        FROM message_tracking_hourly
                        WHERE guild_id = $1 
                        AND user_id = $2
                        AND hour >= $3
                        AND hour <= $4
                    '''
                    params = [guild_id, user_id, window_start, window_end]

                    # Apply filters
                    query, params = await self._apply_bot_filter(query, params, guild_id, 'message_tracking_hourly')

                    # Apply role filtering using current_role_members table
                    if role_filter_ids:
                        user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                        if user_ids and user_id not in user_ids:
                            result[f'{days}d'] = 0
                            continue

                    query, params = await self._apply_comprehensive_blacklist_filters(
                        guild_id, guild, query, params, 'message_tracking_hourly',
                        include_users=True, include_channels=True
                    )

                    try:
                        row = await conn.fetchrow(query, *params)
                    except asyncpg.exceptions.PostgresError as e:
                        raise DatabaseQueryError(
                            "Failed to fetch user message timeseries",
                            context={'guild_id': guild_id,
                                     'user_id': user_id, 'days': days},
                            original=e
                        )

                    result[f'{days}d'] = row['message_count'] or 0

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching user message timeseries",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching user message timeseries",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching user message timeseries",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching user message timeseries",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching user message timeseries",
                    context={'guild_id': guild_id, 'user_id': user_id},
                    original=e
                )
            raise

    async def q_user_timeseries_voice_1d_5d_10d_20d_30d(self, guild_id: int, user_id: int,
                                                        role_filter_ids: Optional[List[int]] = None,
                                                        start_time: Optional[datetime] = None,
                                                        end_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Get user voice seconds for different time periods using hourly aggregated table."""
        if not self.pool:
            return {'1d': 0, '5d': 0, '10d': 0, '20d': 0, '30d': 0}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {'1d': 0, '5d': 0, '10d': 0, '20d': 0, '30d': 0}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                periods = [1, 5, 10, 20, 30]
                result = {}

                # Get the absolute time bounds if provided
                absolute_end = end_time if end_time else datetime.now(
                    timezone.utc)
                absolute_start = start_time if start_time else (
                    absolute_end - timedelta(days=30))

                for days in periods:
                    # Calculate window relative to the absolute end time
                    window_end = absolute_end
                    window_start = absolute_end - timedelta(days=days)

                    # Ensure we don't go before the absolute start
                    if window_start < absolute_start:
                        window_start = absolute_start

                    # Skip if window is invalid (start after end)
                    if window_start >= window_end:
                        result[f'{days}d'] = 0
                        continue

                    query = '''
                        SELECT COALESCE(SUM(total_seconds), 0) as voice_seconds
                        FROM voice_session_history_hourly
                        WHERE guild_id = $1 
                        AND user_id = $2
                        AND hour >= $3
                        AND hour <= $4
                    '''
                    params = [guild_id, user_id, window_start, window_end]

                    # Apply filters
                    query, params = await self._apply_voice_state_filter(query, params, guild_id, 'state_flags')
                    query, params = await self._apply_bot_filter(query, params, guild_id, 'voice_session_history_hourly')

                    # Apply role filtering using current_role_members table
                    if role_filter_ids:
                        user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                        if user_ids and user_id not in user_ids:
                            result[f'{days}d'] = 0
                            continue

                    query, params = await self._apply_comprehensive_blacklist_filters(
                        guild_id, guild, query, params, 'voice_session_history_hourly',
                        include_users=True, include_channels=True
                    )

                    try:
                        row = await conn.fetchrow(query, *params)
                    except asyncpg.exceptions.PostgresError as e:
                        raise DatabaseQueryError(
                            "Failed to fetch user voice timeseries",
                            context={'guild_id': guild_id,
                                     'user_id': user_id, 'days': days},
                            original=e
                        )

                    result[f'{days}d'] = row['voice_seconds'] or 0

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching user voice timeseries",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching user voice timeseries",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching user voice timeseries",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching user voice timeseries",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching user voice timeseries",
                    context={'guild_id': guild_id, 'user_id': user_id},
                    original=e
                )
            raise

    async def q_user_total_messages(self, guild_id: int, user_id: int,
                                    role_filter_ids: Optional[List[int]] = None,
                                    start_time: Optional[datetime] = None,
                                    end_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Get total message stats for a user using hourly aggregated table."""
        if not self.pool or not self.db_connected:
            return {'total_messages': 0, 'total_chars': 0, 'avg_chars': 0.0,
                    'has_attachments': 0, 'has_embeds': 0,
                    'first_message': None, 'last_message': None}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {
                'total_messages': 0, 'total_chars': 0, 'avg_chars': 0.0,
                'has_attachments': 0, 'has_embeds': 0,
                'first_message': None, 'last_message': None
            }

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = '''
                    SELECT 
                        COALESCE(SUM(message_count), 0) as total_messages,
                        COALESCE(SUM(total_chars), 0) as total_chars,
                        COALESCE(SUM(total_chars) / NULLIF(SUM(message_count), 0), 0) as avg_chars,
                        COALESCE(SUM(attachment_count), 0) as has_attachments,
                        COALESCE(SUM(embed_count), 0) as has_embeds,
                        MIN(hour) as first_message,
                        MAX(hour) as last_message
                    FROM message_tracking_hourly
                    WHERE guild_id = $1 AND user_id = $2
                '''
                params = [guild_id, user_id]

                query, params = await self._apply_bot_filter(query, params, guild_id, 'message_tracking_hourly')

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids and user_id not in user_ids:
                        return {
                            'total_messages': 0, 'total_chars': 0, 'avg_chars': 0.0,
                            'has_attachments': 0, 'has_embeds': 0,
                            'first_message': None, 'last_message': None
                        }

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'message_tracking_hourly',
                    include_users=True, include_channels=True
                )

                try:
                    row = await conn.fetchrow(query, *params)
                except asyncpg.exceptions.PostgresError as e:
                    raise DatabaseQueryError(
                        "Failed to fetch user total messages",
                        context={'guild_id': guild_id, 'user_id': user_id},
                        original=e
                    )

                total_messages = row['total_messages'] or 0

                return {
                    'total_messages': total_messages,
                    'total_chars': row['total_chars'] or 0,
                    'avg_chars': round(row['avg_chars'] or 0, 2),
                    'has_attachments': row['has_attachments'] or 0,
                    'has_embeds': row['has_embeds'] or 0,
                    'first_message': row['first_message'].isoformat() if row['first_message'] else None,
                    'last_message': row['last_message'].isoformat() if row['last_message'] else None
                }

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching user total messages",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching user total messages",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching user total messages",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching user total messages",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching user total messages",
                    context={'guild_id': guild_id, 'user_id': user_id},
                    original=e
                )
            raise

    async def q_user_total_voice(self, guild_id: int, user_id: int,
                                 role_filter_ids: Optional[List[int]] = None,
                                 start_time: Optional[datetime] = None,
                                 end_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Get total voice stats for a user using hourly aggregated table."""
        if not self.pool or not self.db_connected:
            return Constants.EMPTY_VOICE_RESULT

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return Constants.EMPTY_VOICE_RESULT

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)
            state_flags_filter = await self._get_voice_state_filter_value(guild_id)

            filters = {
                'user_id': user_id,
                'start_time': start_time,
                'end_time': end_time
            }
            if state_flags_filter is not None:
                filters['state_flags'] = state_flags_filter

            # Apply role filtering using current_role_members table
            if role_filter_ids:
                user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                if user_ids and user_id not in user_ids:
                    return Constants.EMPTY_VOICE_RESULT

            async with self.pool.acquire() as conn:
                # Simplified query using hourly aggregated table
                query = '''
                    SELECT 
                        COALESCE(SUM(total_seconds), 0) as total_seconds,
                        COALESCE(SUM(session_count), 0) as session_count,
                        COALESCE(SUM(total_seconds) / NULLIF(SUM(session_count), 0), 0) as avg_session,
                        MIN(hour) as first_session,
                        MAX(hour) + interval '1 hour' as last_session
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1 AND user_id = $2
                '''
                params = [guild_id, user_id]

                if state_flags_filter is not None:
                    query += f" AND state_flags = ${len(params) + 1}"
                    params.append(state_flags_filter)

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'voice_session_history_hourly')

                try:
                    row = await conn.fetchrow(query, *params)
                except asyncpg.exceptions.PostgresError as e:
                    raise DatabaseQueryError(
                        "Failed to fetch user total voice",
                        context={'guild_id': guild_id, 'user_id': user_id},
                        original=e
                    )

                if not row:
                    return Constants.EMPTY_VOICE_RESULT

                total_seconds = row['total_seconds'] or 0

                return {
                    'total_seconds': total_seconds,
                    'total_hours': round(total_seconds / 3600, 2),
                    'session_count': row['session_count'] or 0,
                    'avg_session': round(row['avg_session'] or 0, 2),
                    'first_session': row['first_session'].isoformat() if row['first_session'] else None,
                    'last_session': row['last_session'].isoformat() if row['last_session'] else None
                }

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching user total voice",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching user total voice",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching user total voice",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching user total voice",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching user total voice",
                    context={'guild_id': guild_id, 'user_id': user_id},
                    original=e
                )
            raise

    async def q_user_messages_per_hour_distribution(self, guild_id: int, user_id: int,
                                                    role_filter_ids: Optional[List[int]] = None,
                                                    start_time: Optional[datetime] = None,
                                                    end_time: Optional[datetime] = None,
                                                    timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get message distribution by hour for a user using hourly aggregated table."""
        if not self.pool:
            result = {f'hour_{i}': 0 for i in range(24)}
            result.update({'total': 0, 'peak_hour': -1})
            return result

        guild = self.bot.get_guild(guild_id)
        if not guild:
            result = {f'hour_{i}': 0 for i in range(24)}
            result.update({'total': 0, 'peak_hour': -1})
            return result

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                # Extract hour from the hour timestamp
                query = f'''
                    SELECT 
                        EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        SUM(message_count) as message_count
                    FROM message_tracking_hourly
                    WHERE guild_id = $1 AND user_id = $2
                '''
                params = [guild_id, user_id]

                query, params = await self._apply_bot_filter(query, params, guild_id, 'message_tracking_hourly')

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids and user_id not in user_ids:
                        result = {f'hour_{i}': 0 for i in range(24)}
                        result.update({'total': 0, 'peak_hour': -1})
                        return result

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'message_tracking_hourly',
                    include_users=True, include_channels=True
                )

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                try:
                    rows = await conn.fetch(query, *params)
                except asyncpg.exceptions.PostgresError as e:
                    raise DatabaseQueryError(
                        "Failed to fetch user message hour distribution",
                        context={'guild_id': guild_id, 'user_id': user_id},
                        original=e
                    )

                result = {f'hour_{i}': 0 for i in range(24)}
                total = 0
                peak_hour = -1
                peak_count = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    count = row['message_count'] or 0
                    result[f'hour_{hour}'] = count
                    total += count

                    if count > peak_count:
                        peak_count = count
                        peak_hour = hour

                result['total'] = total
                result['peak_hour'] = peak_hour

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching user message hour distribution",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching user message hour distribution",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching user message hour distribution",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching user message hour distribution",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching user message hour distribution",
                    context={'guild_id': guild_id, 'user_id': user_id},
                    original=e
                )
            raise

    async def q_user_voice_per_hour_distribution(self, guild_id: int, user_id: int,
                                                 role_filter_ids: Optional[List[int]] = None,
                                                 start_time: Optional[datetime] = None,
                                                 end_time: Optional[datetime] = None,
                                                 timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get voice distribution by hour for a user using hourly aggregated table."""
        if not self.pool or not self.db_connected:
            return {'total_messages': 0}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'hour_{i}': 0 for i in range(24)} | {'total_seconds': 0, 'peak_hour': -1}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = f'''
                    SELECT 
                        EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COALESCE(SUM(total_seconds), 0) as total_seconds
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1 AND user_id = $2
                '''
                params = [guild_id, user_id]

                query, params = await self._apply_voice_state_filter(query, params, guild_id, 'state_flags')

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids and user_id not in user_ids:
                        return {f'hour_{i}': 0 for i in range(24)} | {'total_seconds': 0, 'peak_hour': -1}

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'voice_session_history_hourly',
                    include_users=True, include_channels=True
                )

                query, params = await self._apply_bot_filter(query, params, guild_id, 'voice_session_history_hourly')

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                try:
                    rows = await conn.fetch(query, *params)
                except asyncpg.exceptions.PostgresError as e:
                    raise DatabaseQueryError(
                        "Failed to fetch user voice hour distribution",
                        context={'guild_id': guild_id, 'user_id': user_id},
                        original=e
                    )

                result = {f'hour_{i}': 0 for i in range(24)}
                total_seconds = 0
                peak_hour = -1
                peak_seconds = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    seconds = row['total_seconds'] or 0
                    result[f'hour_{hour}'] = seconds
                    total_seconds += seconds

                    if seconds > peak_seconds:
                        peak_seconds = seconds
                        peak_hour = hour

                result['total_seconds'] = total_seconds
                result['peak_hour'] = peak_hour

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching user voice hour distribution",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching user voice hour distribution",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching user voice hour distribution",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching user voice hour distribution",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching user voice hour distribution",
                    context={'guild_id': guild_id, 'user_id': user_id},
                    original=e
                )
            raise

    async def q_user_top3_voice_channels(self, guild_id: int, user_id: int,
                                         role_filter_ids: Optional[List[int]] = None,
                                         start_time: Optional[datetime] = None,
                                         end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get user's top 3 voice channels using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)
            state_flags_filter = await self._get_voice_state_filter_value(guild_id)

            # Apply role filtering using current_role_members table
            if role_filter_ids:
                user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                if user_ids and user_id not in user_ids:
                    return []

            async with self.pool.acquire() as conn:
                # Simplified query using hourly aggregated table
                query = '''
                    SELECT 
                        channel_id,
                        COALESCE(SUM(total_seconds), 0) as total_seconds,
                        COALESCE(SUM(session_count), 0) as session_count
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1 AND user_id = $2
                '''
                params = [guild_id, user_id]

                if state_flags_filter is not None:
                    query += f" AND state_flags = ${len(params) + 1}"
                    params.append(state_flags_filter)

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'voice_session_history_hourly')

                query += '''
                    GROUP BY channel_id
                    HAVING SUM(total_seconds) > 0
                    ORDER BY total_seconds DESC
                    LIMIT 3
                '''

                try:
                    rows = await conn.fetch(query, *params)
                except asyncpg.exceptions.PostgresError as e:
                    raise DatabaseQueryError(
                        "Failed to fetch user top voice channels",
                        context={'guild_id': guild_id, 'user_id': user_id},
                        original=e
                    )

                # Get total for percentage calculation
                total_query = '''
                    SELECT COALESCE(SUM(total_seconds), 0) as total_seconds
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1 AND user_id = $2
                '''
                total_params = [guild_id, user_id]

                if state_flags_filter is not None:
                    total_query += f" AND state_flags = ${len(total_params) + 1}"
                    total_params.append(state_flags_filter)

                if start_time:
                    total_query += f" AND hour >= ${len(total_params) + 1}"
                    total_params.append(start_time)
                if end_time:
                    total_query += f" AND hour <= ${len(total_params) + 1}"
                    total_params.append(end_time)

                total_row = await conn.fetchrow(total_query, *total_params)
                total_seconds = total_row['total_seconds'] or 0

                result = []
                for row in rows:
                    channel_seconds = row['total_seconds'] or 0
                    percentage = (channel_seconds / total_seconds *
                                  100) if total_seconds > 0 else 0

                    result.append({
                        'channel_id': row['channel_id'],
                        'total_seconds': channel_seconds,
                        'total_hours': round(channel_seconds / 3600, 2),
                        'session_count': row['session_count'] or 0,
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching user top voice channels",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching user top voice channels",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching user top voice channels",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching user top voice channels",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching user top voice channels",
                    context={'guild_id': guild_id, 'user_id': user_id},
                    original=e
                )
            raise

    async def q_user_top3_text_channels(self, guild_id: int, user_id: int,
                                        role_filter_ids: Optional[List[int]] = None,
                                        start_time: Optional[datetime] = None,
                                        end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get user's top 3 text channels using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            # Apply role filtering using current_role_members table
            if role_filter_ids:
                user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                if user_ids and user_id not in user_ids:
                    return []

            async with self.pool.acquire() as conn:
                # Get total messages for percentage calculation
                total_query = '''
                    SELECT COALESCE(SUM(message_count), 0) as total_messages
                    FROM message_tracking_hourly
                    WHERE guild_id = $1 AND user_id = $2
                '''
                total_params = [guild_id, user_id]

                if start_time:
                    total_query += f" AND hour >= ${len(total_params) + 1}"
                    total_params.append(start_time)
                if end_time:
                    total_query += f" AND hour <= ${len(total_params) + 1}"
                    total_params.append(end_time)

                total_query, total_params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, total_query, total_params, 'message_tracking_hourly',
                    include_users=True, include_channels=True
                )

                total_row = await conn.fetchrow(total_query, *total_params)
                total_messages = total_row['total_messages'] or 0

                if total_messages == 0:
                    return []

                # Get per-channel stats
                query = '''
                    SELECT 
                        channel_id,
                        COALESCE(SUM(message_count), 0) as message_count,
                        COALESCE(SUM(total_chars), 0) as total_chars,
                        COALESCE(SUM(total_chars) / NULLIF(SUM(message_count), 0), 0) as avg_chars
                    FROM message_tracking_hourly
                    WHERE guild_id = $1 AND user_id = $2
                '''
                params = [guild_id, user_id]

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'message_tracking_hourly')

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'message_tracking_hourly',
                    include_users=True, include_channels=True
                )

                query += '''
                    GROUP BY channel_id
                    HAVING SUM(message_count) > 0
                    ORDER BY message_count DESC
                    LIMIT 3
                '''

                rows = await conn.fetch(query, *params)

                result = []
                for row in rows:
                    channel_messages = row['message_count'] or 0
                    percentage = (channel_messages / total_messages *
                                  100) if total_messages > 0 else 0

                    result.append({
                        'channel_id': row['channel_id'],
                        'message_count': channel_messages,
                        'total_chars': row['total_chars'] or 0,
                        'avg_chars': round(row['avg_chars'] or 0, 2),
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching user top text channels",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching user top text channels",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching user top text channels",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching user top text channels",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching user top text channels",
                    context={'guild_id': guild_id, 'user_id': user_id},
                    original=e
                )
            raise

    # ======================================================================
    # SERVER STATS - FIXED EXCEPTION HANDLING
    # ======================================================================

    async def q_server_top3_emojis(self, guild_id: int,
                                   role_filter_ids: Optional[List[int]] = None,
                                   start_time: Optional[datetime] = None,
                                   end_time: Optional[datetime] = None,
                                   usage_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get server's top 3 emojis using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = '''
                    SELECT 
                        emoji_str,
                        is_custom,
                        SUM(usage_count) as total_usage,
                        COUNT(DISTINCT user_id) as unique_users
                    FROM emoji_usage_hourly
                    WHERE guild_id = $1
                '''
                params = [guild_id]

                query, params = await self._apply_bot_filter(query, params, guild_id, 'emoji_usage_hourly')

                if usage_type:
                    query += f" AND usage_type = ${len(params) + 1}"
                    params.append(usage_type)

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        placeholders = [
                            f"${len(params) + i + 1}" for i in range(len(user_ids))]
                        query += f" AND user_id IN ({', '.join(placeholders)})"
                        params.extend(user_ids)
                    else:
                        # No users have these roles, return empty result
                        return []

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'emoji_usage_hourly',
                    include_users=True, include_channels=True
                )

                query += '''
                    GROUP BY emoji_str, is_custom
                    HAVING SUM(usage_count) > 0
                    ORDER BY total_usage DESC
                    LIMIT 3
                '''

                try:
                    rows = await conn.fetch(query, *params)
                except asyncpg.exceptions.PostgresError as e:
                    raise DatabaseQueryError(
                        "Failed to fetch server top emojis",
                        context={'guild_id': guild_id},
                        original=e
                    )

                result = []
                for row in rows:
                    total_usage = row['total_usage'] or 0
                    unique_users = row['unique_users'] or 0
                    avg_usage = total_usage / max(unique_users, 1)

                    result.append({
                        'emoji_str': row['emoji_str'],
                        'is_custom': row['is_custom'],
                        'usage_count': total_usage,
                        'unique_users': unique_users,
                        'avg_usage_per_user': round(avg_usage, 2)
                    })

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching server top emojis",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching server top emojis",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching server top emojis",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching server top emojis",
                context={'guild_id': guild_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching server top emojis",
                    context={'guild_id': guild_id},
                    original=e
                )
            raise

    async def q_server_total_messages(self, guild_id: int,
                                      role_filter_ids: Optional[List[int]] = None,
                                      start_time: Optional[datetime] = None,
                                      end_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Get total message stats for a server using hourly aggregated table."""
        if not self.pool:
            return {
                'total_messages': 0, 'total_chars': 0, 'avg_chars': 0.0,
                'unique_users': 0, 'messages_per_user': 0.0,
                'has_attachments': 0, 'has_embeds': 0
            }

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {
                'total_messages': 0, 'total_chars': 0, 'avg_chars': 0.0,
                'unique_users': 0, 'messages_per_user': 0.0,
                'has_attachments': 0, 'has_embeds': 0
            }

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = '''
                    SELECT 
                        COALESCE(SUM(message_count), 0) as total_messages,
                        COALESCE(SUM(total_chars), 0) as total_chars,
                        COALESCE(SUM(total_chars) / NULLIF(SUM(message_count), 0), 0) as avg_chars,
                        COUNT(DISTINCT user_id) as unique_users,
                        COALESCE(SUM(attachment_count), 0) as has_attachments,
                        COALESCE(SUM(embed_count), 0) as has_embeds
                    FROM message_tracking_hourly
                    WHERE guild_id = $1
                '''
                params = [guild_id]

                query, params = await self._apply_bot_filter(query, params, guild_id, 'message_tracking_hourly')

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        placeholders = [
                            f"${len(params) + i + 1}" for i in range(len(user_ids))]
                        query += f" AND user_id IN ({', '.join(placeholders)})"
                        params.extend(user_ids)
                    else:
                        # No users have these roles, return empty result
                        return {
                            'total_messages': 0, 'total_chars': 0, 'avg_chars': 0.0,
                            'unique_users': 0, 'messages_per_user': 0.0,
                            'has_attachments': 0, 'has_embeds': 0
                        }

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'message_tracking_hourly',
                    include_users=True, include_channels=True
                )

                try:
                    row = await conn.fetchrow(query, *params)
                except asyncpg.exceptions.PostgresError as e:
                    raise DatabaseQueryError(
                        "Failed to fetch server total messages",
                        context={'guild_id': guild_id},
                        original=e
                    )

                total_messages = row['total_messages'] or 0
                unique_users = row['unique_users'] or 0
                messages_per_user = total_messages / max(unique_users, 1)

                return {
                    'total_messages': total_messages,
                    'total_chars': row['total_chars'] or 0,
                    'avg_chars': round(row['avg_chars'] or 0, 2),
                    'unique_users': unique_users,
                    'messages_per_user': round(messages_per_user, 2),
                    'has_attachments': row['has_attachments'] or 0,
                    'has_embeds': row['has_embeds'] or 0
                }

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching server total messages",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching server total messages",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching server total messages",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching server total messages",
                context={'guild_id': guild_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching server total messages",
                    context={'guild_id': guild_id},
                    original=e
                )
            raise

    async def q_server_total_voice(self, guild_id: int,
                                   role_filter_ids: Optional[List[int]] = None,
                                   start_time: Optional[datetime] = None,
                                   end_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Get total voice stats for a server using hourly aggregated table."""

        if not self.pool:
            print("  ❌ No database pool")
            return Constants.EMPTY_SERVER_VOICE_RESULT

        guild = self.bot.get_guild(guild_id)
        if not guild:
            print(f"  ❌ Guild {guild_id} not found")
            return Constants.EMPTY_SERVER_VOICE_RESULT

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)
            state_flags_filter = await self._get_voice_state_filter_value(guild_id)

            async with self.pool.acquire() as conn:
                # Stats query
                stats_query = '''
                    SELECT 
                        COALESCE(SUM(total_seconds), 0) as total_seconds,
                        COALESCE(SUM(session_count), 0) as session_count,
                        COALESCE(SUM(total_seconds) / NULLIF(SUM(session_count), 0), 0) as avg_session
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1
                '''
                stats_params = [guild_id]

                if state_flags_filter is not None:
                    stats_query += f" AND state_flags = ${len(stats_params) + 1}"
                    stats_params.append(state_flags_filter)

                if start_time:
                    stats_query += f" AND hour >= ${len(stats_params) + 1}"
                    stats_params.append(start_time)

                if end_time:
                    stats_query += f" AND hour <= ${len(stats_params) + 1}"
                    stats_params.append(end_time)

                stats_query, stats_params = await self._apply_bot_filter(stats_query, stats_params, guild_id, 'voice_session_history_hourly')

                # Unique users query
                users_query = '''
                    SELECT COUNT(DISTINCT user_id) as unique_users
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1
                '''
                users_params = [guild_id]

                if state_flags_filter is not None:
                    users_query += f" AND state_flags = ${len(users_params) + 1}"
                    users_params.append(state_flags_filter)

                if start_time:
                    users_query += f" AND hour >= ${len(users_params) + 1}"
                    users_params.append(start_time)
                if end_time:
                    users_query += f" AND hour <= ${len(users_params) + 1}"
                    users_params.append(end_time)

                users_query, users_params = await self._apply_bot_filter(users_query, users_params, guild_id, 'voice_session_history_hourly')

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        stats_query = stats_query.replace(
                            "WHERE guild_id = $1",
                            f"WHERE guild_id = $1 AND user_id = ANY(${len(stats_params) + 1}::bigint[])"
                        )
                        stats_params.append(user_ids)

                        users_query = users_query.replace(
                            "WHERE guild_id = $1",
                            f"WHERE guild_id = $1 AND user_id = ANY(${len(users_params) + 1}::bigint[])"
                        )
                        users_params.append(user_ids)

                    else:
                        # No users have these roles, return empty result
                        print("  ❌ No users found with these roles")
                        return Constants.EMPTY_SERVER_VOICE_RESULT

                try:

                    stats_row = await conn.fetchrow(stats_query, *stats_params)

                    users_row = await conn.fetchrow(users_query, *users_params)

                    total_seconds = stats_row['total_seconds'] if stats_row else 0
                    unique_users = users_row['unique_users'] if users_row else 0
                    seconds_per_user = total_seconds / max(unique_users, 1)

                    result = {
                        'total_seconds': total_seconds,
                        'total_hours': round(total_seconds / 3600, 2),
                        'session_count': stats_row['session_count'] if stats_row else 0,
                        'unique_users': unique_users,
                        'avg_session': round(stats_row['avg_session'] or 0, 2),
                        'seconds_per_user': round(seconds_per_user, 2)
                    }

                    return result

                except Exception as e:
                    print(f"  ❌ Error executing queries: {e}")
                    import traceback
                    traceback.print_exc()
                    raise

        except Exception as e:
            print(f"  ❌ Error in q_server_total_voice: {e}")
            import traceback
            traceback.print_exc()
            raise

    async def q_server_timeseries_messages_1d_5d_10d_20d_30d(self, guild_id: int,
                                                             role_filter_ids: Optional[List[int]] = None,
                                                             start_time: Optional[datetime] = None,
                                                             end_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Get server message counts for different time periods using hourly aggregated table."""
        if not self.pool:
            return {'1d': 0, '5d': 0, '10d': 0, '20d': 0, '30d': 0}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {'1d': 0, '5d': 0, '10d': 0, '20d': 0, '30d': 0}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                periods = [1, 5, 10, 20, 30]
                result = {}

                # Get the absolute time bounds if provided
                absolute_end = end_time if end_time else datetime.now(
                    timezone.utc)
                absolute_start = start_time if start_time else (
                    absolute_end - timedelta(days=30))

                for days in periods:
                    # Calculate window relative to the absolute end time
                    window_end = absolute_end
                    window_start = absolute_end - timedelta(days=days)

                    # Ensure we don't go before the absolute start
                    if window_start < absolute_start:
                        window_start = absolute_start

                    # Skip if window is invalid (start after end)
                    if window_start >= window_end:
                        result[f'{days}d'] = 0
                        continue

                    query = '''
                        SELECT COALESCE(SUM(message_count), 0) as message_count
                        FROM message_tracking_hourly
                        WHERE guild_id = $1
                        AND hour >= $2
                        AND hour <= $3
                    '''
                    params = [guild_id, window_start, window_end]

                    # Apply filters
                    query, params = await self._apply_bot_filter(query, params, guild_id, 'message_tracking_hourly')

                    # Apply role filtering using current_role_members table
                    if role_filter_ids:
                        user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                        if user_ids:
                            placeholders = [
                                f"${len(params) + i + 1}" for i in range(len(user_ids))]
                            query += f" AND user_id IN ({', '.join(placeholders)})"
                            params.extend(user_ids)
                        else:
                            result[f'{days}d'] = 0
                            continue

                    query, params = await self._apply_comprehensive_blacklist_filters(
                        guild_id, guild, query, params, 'message_tracking_hourly',
                        include_users=True, include_channels=True
                    )

                    try:
                        row = await conn.fetchrow(query, *params)
                    except asyncpg.exceptions.PostgresError as e:
                        raise DatabaseQueryError(
                            "Failed to fetch server message timeseries",
                            context={'guild_id': guild_id, 'days': days},
                            original=e
                        )

                    result[f'{days}d'] = row['message_count'] or 0

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching server message timeseries",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching server message timeseries",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching server message timeseries",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching server message timeseries",
                context={'guild_id': guild_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching server message timeseries",
                    context={'guild_id': guild_id},
                    original=e
                )
            raise

    async def q_server_timeseries_voice_1d_5d_10d_20d_30d(self, guild_id: int,
                                                          role_filter_ids: Optional[List[int]] = None,
                                                          start_time: Optional[datetime] = None,
                                                          end_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Get server voice seconds for different time periods using hourly aggregated table."""

        if not self.pool:
            print("  ❌ No database pool")
            return {'1d': 0, '5d': 0, '10d': 0, '20d': 0, '30d': 0}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            print(f"  ❌ Guild {guild_id} not found")
            return {'1d': 0, '5d': 0, '10d': 0, '20d': 0, '30d': 0}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                periods = [1, 5, 10, 20, 30]
                result = {}

                # Get the absolute time bounds if provided
                absolute_end = end_time if end_time else datetime.now(
                    timezone.utc)
                absolute_start = start_time if start_time else (
                    absolute_end - timedelta(days=30))

                # First, let's see what data exists in the table for this guild
                try:
                    sample_data = await conn.fetch('''
                        SELECT 
                            hour,
                            total_seconds,
                            user_id
                        FROM voice_session_history_hourly
                        WHERE guild_id = $1
                        ORDER BY hour DESC
                        LIMIT 5
                    ''', guild_id)

                except asyncpg.exceptions.PostgresError as e:
                    print(f"    ⚠️ Could not fetch sample data: {e}")
                    # Non-critical, continue

                for days in periods:

                    # Calculate window relative to the absolute end time
                    window_end = absolute_end
                    window_start = absolute_end - timedelta(days=days)

                    # Ensure we don't go before the absolute start
                    if window_start < absolute_start:
                        window_start = absolute_start

                    # Skip if window is invalid (start after end)
                    if window_start >= window_end:
                        result[f'{days}d'] = 0
                        continue

                    query = '''
                        SELECT COALESCE(SUM(total_seconds), 0) as voice_seconds
                        FROM voice_session_history_hourly
                        WHERE guild_id = $1 
                        AND hour >= $2
                        AND hour <= $3
                    '''
                    params = [guild_id, window_start, window_end]

                    # Apply voice state filter
                    try:
                        query, params = await self._apply_voice_state_filter(query, params, guild_id, 'state_flags')

                    except Exception as e:
                        raise DatabaseQueryError(
                            "Failed to apply voice state filter",
                            context={'guild_id': guild_id, 'days': days},
                            original=e
                        )

                    # Apply bot filter
                    try:
                        query, params = await self._apply_bot_filter(query, params, guild_id, 'voice_session_history_hourly')

                    except Exception as e:
                        raise DatabaseQueryError(
                            "Failed to apply bot filter",
                            context={'guild_id': guild_id, 'days': days},
                            original=e
                        )

                    # Apply role filtering using current_role_members table
                    if role_filter_ids:

                        try:
                            user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                            if user_ids:

                                placeholders = [
                                    f"${len(params) + i + 1}" for i in range(len(user_ids))]
                                query += f" AND user_id IN ({', '.join(placeholders)})"
                                params.extend(user_ids)

                            else:
                                result[f'{days}d'] = 0
                                continue
                        except Exception as e:
                            raise DatabaseQueryError(
                                "Failed to apply role filter",
                                context={
                                    'guild_id': guild_id, 'role_filter_ids': role_filter_ids, 'days': days},
                                original=e
                            )

                    # Apply blacklist filters
                    try:
                        query, params = await self._apply_comprehensive_blacklist_filters(
                            guild_id, guild, query, params, 'voice_session_history_hourly',
                            include_users=True, include_channels=True
                        )

                    except Exception as e:
                        raise DatabaseQueryError(
                            "Failed to apply blacklist filters",
                            context={'guild_id': guild_id, 'days': days},
                            original=e
                        )

                    try:

                        row = await conn.fetchrow(query, *params)
                        seconds = row['voice_seconds'] if row else 0
                        result[f'{days}d'] = seconds

                        # If result is 0, let's check why
                        if seconds == 0:
                            try:
                                # Check if there's any data in this time range at all
                                check_query = '''
                                    SELECT COUNT(*) as count, COALESCE(SUM(total_seconds), 0) as total
                                    FROM voice_session_history_hourly
                                    WHERE guild_id = $1 AND hour >= $2 AND hour <= $3
                                '''
                                check_params = [
                                    guild_id, window_start, window_end]
                                check_row = await conn.fetchrow(check_query, *check_params)

                            except asyncpg.exceptions.PostgresError as e:
                                print(f"    ⚠️ Range check failed: {e}")

                    except asyncpg.exceptions.PostgresError as e:
                        if "timeout" in str(e).lower():
                            raise DatabaseTimeoutError(
                                "Database operation timed out while fetching server voice timeseries",
                                context={'guild_id': guild_id, 'days': days},
                                original=e
                            ) from e
                        else:
                            raise DatabaseQueryError(
                                "Failed to execute query for server voice timeseries",
                                context={'guild_id': guild_id, 'days': days},
                                original=e
                            ) from e

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching server voice timeseries",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching server voice timeseries",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching server voice timeseries",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error while fetching server voice timeseries",
                context={'guild_id': guild_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching server voice timeseries",
                    context={'guild_id': guild_id},
                    original=e
                )
            raise

    async def q_server_top3_voice_channels(self, guild_id: int,
                                           role_filter_ids: Optional[List[int]] = None,
                                           start_time: Optional[datetime] = None,
                                           end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get server's top 3 voice channels using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)
            state_flags_filter = await self._get_voice_state_filter_value(guild_id)

            async with self.pool.acquire() as conn:
                query = '''
                    SELECT 
                        channel_id,
                        COALESCE(SUM(total_seconds), 0) as total_seconds,
                        COALESCE(SUM(session_count), 0) as session_count
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1
                '''
                params = [guild_id]

                if state_flags_filter is not None:
                    query += f" AND state_flags = ${len(params) + 1}"
                    params.append(state_flags_filter)

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'voice_session_history_hourly')

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        query = query.replace(
                            "WHERE guild_id = $1",
                            f"WHERE guild_id = $1 AND user_id = ANY(${len(params) + 1}::bigint[])"
                        )
                        params.append(user_ids)
                    else:
                        return []

                query += '''
                    GROUP BY channel_id
                    HAVING SUM(total_seconds) > 0
                    ORDER BY total_seconds DESC
                    LIMIT 3
                '''

                try:
                    rows = await conn.fetch(query, *params)
                except asyncpg.exceptions.PostgresError as e:
                    raise DatabaseQueryError(
                        "Failed to fetch server top voice channels",
                        context={'guild_id': guild_id},
                        original=e
                    )

                total_query = '''
                    SELECT COALESCE(SUM(total_seconds), 0) as total_seconds
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1
                '''
                total_params = [guild_id]

                if state_flags_filter is not None:
                    total_query += f" AND state_flags = ${len(total_params) + 1}"
                    total_params.append(state_flags_filter)

                if start_time:
                    total_query += f" AND hour >= ${len(total_params) + 1}"
                    total_params.append(start_time)
                if end_time:
                    total_query += f" AND hour <= ${len(total_params) + 1}"
                    total_params.append(end_time)

                total_query, total_params = await self._apply_bot_filter(total_query, total_params, guild_id, 'voice_session_history_hourly')

                if role_filter_ids and 'user_ids' in locals() and user_ids:
                    total_query = total_query.replace(
                        "WHERE guild_id = $1",
                        f"WHERE guild_id = $1 AND user_id = ANY(${len(total_params) + 1}::bigint[])"
                    )
                    total_params.append(user_ids)

                total_row = await conn.fetchrow(total_query, *total_params)
                total_seconds = total_row['total_seconds'] if total_row else 0

                result = []
                for row in rows:
                    channel_seconds = row['total_seconds'] or 0
                    percentage = (channel_seconds / total_seconds *
                                  100) if total_seconds > 0 else 0

                    result.append({
                        'channel_id': row['channel_id'],
                        'total_seconds': channel_seconds,
                        'total_hours': round(channel_seconds / 3600, 2),
                        'session_count': row['session_count'] or 0,
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching server top voice channels",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching server top voice channels",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching server top voice channels",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching server top voice channels",
                context={'guild_id': guild_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching server top voice channels",
                    context={'guild_id': guild_id},
                    original=e
                )
            raise

    async def q_server_top3_text_channels(self, guild_id: int,
                                          role_filter_ids: Optional[List[int]] = None,
                                          start_time: Optional[datetime] = None,
                                          end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get server's top 3 text channels using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                total_query = '''
                    SELECT COALESCE(SUM(message_count), 0) as total_messages
                    FROM message_tracking_hourly
                    WHERE guild_id = $1
                '''
                total_params = [guild_id]

                if start_time:
                    total_query += f" AND hour >= ${len(total_params) + 1}"
                    total_params.append(start_time)
                if end_time:
                    total_query += f" AND hour <= ${len(total_params) + 1}"
                    total_params.append(end_time)

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        placeholders = [
                            f"${len(total_params) + i + 1}" for i in range(len(user_ids))]
                        total_query += f" AND user_id IN ({', '.join(placeholders)})"
                        total_params.extend(user_ids)
                    else:
                        return []

                total_query, total_params = await self._apply_bot_filter(total_query, total_params, guild_id, 'message_tracking_hourly')

                total_query, total_params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, total_query, total_params, 'message_tracking_hourly',
                    include_users=True, include_channels=True
                )

                total_row = await conn.fetchrow(total_query, *total_params)
                total_messages = total_row['total_messages'] or 0

                if total_messages == 0:
                    return []

                query = '''
                    SELECT 
                        channel_id,
                        COALESCE(SUM(message_count), 0) as message_count,
                        COALESCE(SUM(total_chars), 0) as total_chars,
                        COUNT(DISTINCT user_id) as unique_users,
                        COALESCE(SUM(total_chars) / NULLIF(SUM(message_count), 0), 0) as avg_chars
                    FROM message_tracking_hourly
                    WHERE guild_id = $1
                '''
                params = [guild_id]

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        placeholders = [
                            f"${len(params) + i + 1}" for i in range(len(user_ids))]
                        query += f" AND user_id IN ({', '.join(placeholders)})"
                        params.extend(user_ids)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'message_tracking_hourly')

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'message_tracking_hourly',
                    include_users=True, include_channels=True
                )

                query += '''
                    GROUP BY channel_id
                    HAVING SUM(message_count) > 0
                    ORDER BY message_count DESC
                    LIMIT 3
                '''

                rows = await conn.fetch(query, *params)

                result = []
                for row in rows:
                    channel_messages = row['message_count'] or 0
                    percentage = (channel_messages / total_messages *
                                  100) if total_messages > 0 else 0

                    result.append({
                        'channel_id': row['channel_id'],
                        'message_count': channel_messages,
                        'total_chars': row['total_chars'] or 0,
                        'unique_users': row['unique_users'] or 0,
                        'avg_chars': round(row['avg_chars'] or 0, 2),
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching server top text channels",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching server top text channels",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching server top text channels",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching server top text channels",
                context={'guild_id': guild_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching server top text channels",
                    context={'guild_id': guild_id},
                    original=e
                )
            raise

    async def q_server_top3_users_messages(self, guild_id: int,
                                           role_filter_ids: Optional[List[int]] = None,
                                           start_time: Optional[datetime] = None,
                                           end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get server's top 3 users by messages using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                # Build base query
                query = '''
                    SELECT 
                        user_id,
                        COALESCE(SUM(message_count), 0) as message_count,
                        COALESCE(SUM(total_chars), 0) as total_chars,
                        COALESCE(SUM(total_chars) / NULLIF(SUM(message_count), 0), 0) as avg_chars
                    FROM message_tracking_hourly
                    WHERE guild_id = $1
                '''
                params = [guild_id]
                param_index = 2

                if start_time:
                    query += f" AND hour >= ${param_index}"
                    params.append(start_time)
                    param_index += 1
                if end_time:
                    query += f" AND hour <= ${param_index}"
                    params.append(end_time)
                    param_index += 1

                # Apply bot filter
                query, params = await self._apply_bot_filter(query, params, guild_id, 'message_tracking_hourly')
                param_index = len(params) + 1

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        # FIXED: Added ::bigint[] cast
                        query += f" AND user_id = ANY(${param_index}::bigint[])"
                        params.append(user_ids)
                        param_index += 1
                    else:
                        return []

                # Get total for percentage calculation
                total_query = '''
                    SELECT COALESCE(SUM(message_count), 0) as total_messages
                    FROM message_tracking_hourly
                    WHERE guild_id = $1
                '''
                total_params = [guild_id]
                total_param_index = 2

                if start_time:
                    total_query += f" AND hour >= ${total_param_index}"
                    total_params.append(start_time)
                    total_param_index += 1
                if end_time:
                    total_query += f" AND hour <= ${total_param_index}"
                    total_params.append(end_time)
                    total_param_index += 1

                total_query, total_params = await self._apply_bot_filter(total_query, total_params, guild_id, 'message_tracking_hourly')

                if role_filter_ids and 'user_ids' in locals() and user_ids:
                    total_query += f" AND user_id = ANY(${total_param_index}::bigint[])"
                    total_params.append(user_ids)

                total_row = await conn.fetchrow(total_query, *total_params)
                total_messages = total_row['total_messages'] if total_row else 0

                if total_messages == 0:
                    return []

                # Complete the main query
                query += '''
                    GROUP BY user_id
                    HAVING SUM(message_count) > 0
                    ORDER BY message_count DESC
                    LIMIT 3
                '''

                rows = await conn.fetch(query, *params)

                result = []
                for row in rows:
                    user_messages = row['message_count'] or 0
                    percentage = (user_messages / total_messages *
                                  100) if total_messages > 0 else 0

                    result.append({
                        'user_id': row['user_id'],
                        'message_count': user_messages,
                        'total_chars': row['total_chars'] or 0,
                        'avg_chars': round(row['avg_chars'] or 0, 2),
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching server top users by messages",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching server top users by messages",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching server top users by messages",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching server top users by messages",
                context={'guild_id': guild_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching server top users by messages",
                    context={'guild_id': guild_id},
                    original=e
                )
            raise

    async def q_server_top3_users_voice(self, guild_id: int,
                                        role_filter_ids: Optional[List[int]] = None,
                                        start_time: Optional[datetime] = None,
                                        end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get server's top 3 users by voice time using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)
            state_flags_filter = await self._get_voice_state_filter_value(guild_id)

            async with self.pool.acquire() as conn:
                # Build base query
                query = '''
                    SELECT 
                        user_id,
                        COALESCE(SUM(total_seconds), 0) as total_seconds,
                        COALESCE(SUM(session_count), 0) as session_count,
                        COALESCE(SUM(total_seconds) / NULLIF(SUM(session_count), 0), 0) as avg_session
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1
                '''
                params = [guild_id]
                param_index = 2

                # Apply voice state filter
                if state_flags_filter is not None:
                    query += f" AND state_flags = ${param_index}"
                    params.append(state_flags_filter)
                    param_index += 1

                if start_time:
                    query += f" AND hour >= ${param_index}"
                    params.append(start_time)
                    param_index += 1
                if end_time:
                    query += f" AND hour <= ${param_index}"
                    params.append(end_time)
                    param_index += 1

                # Apply bot filter
                query, params = await self._apply_bot_filter(query, params, guild_id, 'voice_session_history_hourly')
                param_index = len(params) + 1

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        # FIXED: Added ::bigint[] cast
                        query += f" AND user_id = ANY(${param_index}::bigint[])"
                        params.append(user_ids)
                        param_index += 1
                    else:
                        return []

                query += '''
                    GROUP BY user_id
                    HAVING SUM(total_seconds) > 0
                    ORDER BY total_seconds DESC
                    LIMIT 3
                '''

                rows = await conn.fetch(query, *params)

                # Get total for percentage calculation
                total_query = '''
                    SELECT COALESCE(SUM(total_seconds), 0) as total_seconds
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1
                '''
                total_params = [guild_id]
                total_param_index = 2

                if state_flags_filter is not None:
                    total_query += f" AND state_flags = ${total_param_index}"
                    total_params.append(state_flags_filter)
                    total_param_index += 1

                if start_time:
                    total_query += f" AND hour >= ${total_param_index}"
                    total_params.append(start_time)
                    total_param_index += 1
                if end_time:
                    total_query += f" AND hour <= ${total_param_index}"
                    total_params.append(end_time)
                    total_param_index += 1

                total_query, total_params = await self._apply_bot_filter(total_query, total_params, guild_id, 'voice_session_history_hourly')

                if role_filter_ids and 'user_ids' in locals() and user_ids:
                    total_query += f" AND user_id = ANY(${total_param_index}::bigint[])"
                    total_params.append(user_ids)

                total_row = await conn.fetchrow(total_query, *total_params)
                total_seconds = total_row['total_seconds'] if total_row else 0

                result = []
                for row in rows:
                    user_seconds = row['total_seconds'] or 0
                    percentage = (user_seconds / total_seconds *
                                  100) if total_seconds > 0 else 0

                    result.append({
                        'user_id': row['user_id'],
                        'total_seconds': user_seconds,
                        'total_hours': round(user_seconds / 3600, 2),
                        'session_count': row['session_count'] or 0,
                        'avg_session': round(row['avg_session'] or 0, 2),
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching server top users by voice",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching server top users by voice",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching server top users by voice",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching server top users by voice",
                context={'guild_id': guild_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching server top users by voice",
                    context={'guild_id': guild_id},
                    original=e
                )
            raise

    # ======================================================================
    # CATEGORY STATS - FIXED EXCEPTION HANDLING
    # ======================================================================

    async def q_category_channel_count(self, guild_id: int, category_id: int) -> Dict[str, Any]:
        """Get channel counts for a category."""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {'text_channels': 0, 'voice_channels': 0, 'total_channels': 0}

        try:
            text_channels = 0
            voice_channels = 0

            for channel in guild.channels:
                if hasattr(channel, 'category_id') and channel.category_id == category_id:
                    if isinstance(channel, discord.TextChannel):
                        text_channels += 1
                    elif isinstance(channel, discord.VoiceChannel):
                        voice_channels += 1

            return {
                'text_channels': text_channels,
                'voice_channels': voice_channels,
                'total_channels': text_channels + voice_channels
            }

        except Exception as e:
            raise DatabaseQueryError(
                "Failed to get category channel count",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )

    async def q_category_total_messages(self, guild_id: int, category_id: int,
                                        role_filter_ids: Optional[List[int]] = None,
                                        start_time: Optional[datetime] = None,
                                        end_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Get total message stats for a category using hourly aggregated table."""
        if not self.pool:
            return {
                'total_messages': 0, 'total_chars': 0, 'avg_chars': 0.0,
                'unique_users': 0, 'messages_per_user': 0.0
            }

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {
                'total_messages': 0, 'total_chars': 0, 'avg_chars': 0.0,
                'unique_users': 0, 'messages_per_user': 0.0
            }

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = '''
                    SELECT 
                        COALESCE(SUM(message_count), 0) as total_messages,
                        COALESCE(SUM(total_chars), 0) as total_chars,
                        COALESCE(SUM(total_chars) / NULLIF(SUM(message_count), 0), 0) as avg_chars,
                        COUNT(DISTINCT user_id) as unique_users
                    FROM message_tracking_hourly
                    WHERE guild_id = $1 
                    AND category_id = $2
                '''
                params = [guild_id, category_id]

                query, params = await self._apply_bot_filter(query, params, guild_id, 'message_tracking_hourly')

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        placeholders = [
                            f"${len(params) + i + 1}" for i in range(len(user_ids))]
                        query += f" AND user_id IN ({', '.join(placeholders)})"
                        params.extend(user_ids)
                    else:
                        return {
                            'total_messages': 0, 'total_chars': 0, 'avg_chars': 0.0,
                            'unique_users': 0, 'messages_per_user': 0.0
                        }

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'message_tracking_hourly',
                    include_users=True, include_channels=False,
                    specific_category_id=category_id
                )

                try:
                    row = await conn.fetchrow(query, *params)
                except asyncpg.exceptions.PostgresError as e:
                    raise DatabaseQueryError(
                        "Failed to fetch category total messages",
                        context={'guild_id': guild_id,
                                 'category_id': category_id},
                        original=e
                    )

                total_messages = row['total_messages'] or 0
                unique_users = row['unique_users'] or 0
                messages_per_user = total_messages / max(unique_users, 1)

                return {
                    'total_messages': total_messages,
                    'total_chars': row['total_chars'] or 0,
                    'avg_chars': round(row['avg_chars'] or 0, 2),
                    'unique_users': unique_users,
                    'messages_per_user': round(messages_per_user, 2)
                }

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching category total messages",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching category total messages",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching category total messages",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching category total messages",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching category total messages",
                    context={'guild_id': guild_id, 'category_id': category_id},
                    original=e
                )
            raise

    async def q_category_total_voice(self, guild_id: int, category_id: int,
                                     role_filter_ids: Optional[List[int]] = None,
                                     start_time: Optional[datetime] = None,
                                     end_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Get total voice stats for a category using hourly aggregated table."""
        if not self.pool:
            return {
                'total_seconds': 0, 'total_hours': 0.0, 'session_count': 0,
                'unique_users': 0, 'avg_session': 0.0
            }

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {
                'total_seconds': 0, 'total_hours': 0.0, 'session_count': 0,
                'unique_users': 0, 'avg_session': 0.0
            }

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)
            state_flags_filter = await self._get_voice_state_filter_value(guild_id)

            async with self.pool.acquire() as conn:
                stats_query = '''
                    SELECT 
                        COALESCE(SUM(total_seconds), 0) as total_seconds,
                        COALESCE(SUM(session_count), 0) as session_count,
                        COALESCE(SUM(total_seconds) / NULLIF(SUM(session_count), 0), 0) as avg_session
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1 
                    AND category_id = $2
                '''
                stats_params = [guild_id, category_id]

                if state_flags_filter is not None:
                    stats_query += f" AND state_flags = ${len(stats_params) + 1}"
                    stats_params.append(state_flags_filter)

                if start_time:
                    stats_query += f" AND hour >= ${len(stats_params) + 1}"
                    stats_params.append(start_time)
                if end_time:
                    stats_query += f" AND hour <= ${len(stats_params) + 1}"
                    stats_params.append(end_time)

                stats_query, stats_params = await self._apply_bot_filter(stats_query, stats_params, guild_id, 'voice_session_history_hourly')

                users_query = '''
                    SELECT COUNT(DISTINCT user_id) as unique_users
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1 
                    AND category_id = $2
                '''
                users_params = [guild_id, category_id]

                if state_flags_filter is not None:
                    users_query += f" AND state_flags = ${len(users_params) + 1}"
                    users_params.append(state_flags_filter)

                if start_time:
                    users_query += f" AND hour >= ${len(users_params) + 1}"
                    users_params.append(start_time)
                if end_time:
                    users_query += f" AND hour <= ${len(users_params) + 1}"
                    users_params.append(end_time)

                users_query, users_params = await self._apply_bot_filter(users_query, users_params, guild_id, 'voice_session_history_hourly')

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        stats_query = stats_query.replace(
                            "WHERE guild_id = $1 AND category_id = $2",
                            f"WHERE guild_id = $1 AND category_id = $2 AND user_id = ANY(${len(stats_params) + 1}::bigint[])"
                        )
                        stats_params.append(user_ids)

                        users_query = users_query.replace(
                            "WHERE guild_id = $1 AND category_id = $2",
                            f"WHERE guild_id = $1 AND category_id = $2 AND user_id = ANY(${len(users_params) + 1}::bigint[])"
                        )
                        users_params.append(user_ids)
                    else:
                        return {
                            'total_seconds': 0, 'total_hours': 0.0, 'session_count': 0,
                            'unique_users': 0, 'avg_session': 0.0
                        }

                try:
                    stats_row = await conn.fetchrow(stats_query, *stats_params)
                    users_row = await conn.fetchrow(users_query, *users_params)
                except asyncpg.exceptions.PostgresError as e:
                    raise DatabaseQueryError(
                        "Failed to fetch category total voice stats",
                        context={'guild_id': guild_id,
                                 'category_id': category_id},
                        original=e
                    )

                total_seconds = stats_row['total_seconds'] if stats_row else 0
                unique_users = users_row['unique_users'] if users_row else 0

                return {
                    'total_seconds': total_seconds,
                    'total_hours': round(total_seconds / 3600, 2),
                    'session_count': stats_row['session_count'] if stats_row else 0,
                    'unique_users': unique_users,
                    'avg_session': round(stats_row['avg_session'] or 0, 2)
                }

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching category total voice",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching category total voice",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching category total voice",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching category total voice",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching category total voice",
                    context={'guild_id': guild_id, 'category_id': category_id},
                    original=e
                )
            raise

    async def q_category_timeseries_messages(self, guild_id: int, category_id: int,
                                             days: List[int] = [
                                                 1, 5, 10, 20, 30],
                                             role_filter_ids: Optional[List[int]] = None,
                                             start_time: Optional[datetime] = None,
                                             end_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Get category message counts for different time periods using hourly aggregated table."""
        if not self.pool:
            return {f'{d}d': 0 for d in days}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'{d}d': 0 for d in days}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                result = {}

                for d in days:
                    window_end = end_time if end_time else datetime.now(
                        timezone.utc)
                    window_start = window_end - timedelta(days=d)

                    query = '''
                        SELECT COALESCE(SUM(message_count), 0) as message_count
                        FROM message_tracking_hourly
                        WHERE guild_id = $1 
                        AND category_id = $2
                        AND hour >= $3
                        AND hour <= $4
                    '''
                    params = [guild_id, category_id, window_start, window_end]

                    query, params = await self._apply_bot_filter(query, params, guild_id, 'message_tracking_hourly')

                    # Apply role filtering using current_role_members table
                    if role_filter_ids:
                        user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                        if user_ids:
                            placeholders = [
                                f"${len(params) + i + 1}" for i in range(len(user_ids))]
                            query += f" AND user_id IN ({', '.join(placeholders)})"
                            params.extend(user_ids)
                        else:
                            result[f'{d}d'] = 0
                            continue

                    query, params = await self._apply_comprehensive_blacklist_filters(
                        guild_id, guild, query, params, 'message_tracking_hourly',
                        include_users=True, include_channels=False,
                        specific_category_id=category_id
                    )

                    try:
                        row = await conn.fetchrow(query, *params)
                    except asyncpg.exceptions.PostgresError as e:
                        raise DatabaseQueryError(
                            "Failed to fetch category message timeseries",
                            context={'guild_id': guild_id,
                                     'category_id': category_id, 'days': d},
                            original=e
                        )

                    result[f'{d}d'] = row['message_count'] or 0

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching category message timeseries",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching category message timeseries",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching category message timeseries",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching category message timeseries",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching category message timeseries",
                    context={'guild_id': guild_id, 'category_id': category_id},
                    original=e
                )
            raise

    async def q_category_timeseries_voice(self, guild_id: int, category_id: int,
                                          days: List[int] = [1, 5, 10, 20, 30],
                                          role_filter_ids: Optional[List[int]] = None,
                                          start_time: Optional[datetime] = None,
                                          end_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Get category voice seconds for different time periods using hourly aggregated table."""
        if not self.pool:
            return {f'{d}d': 0 for d in days}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'{d}d': 0 for d in days}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                result = {}

                for d in days:
                    window_end = end_time if end_time else datetime.now(
                        timezone.utc)
                    window_start = window_end - timedelta(days=d)

                    query = '''
                        SELECT COALESCE(SUM(total_seconds), 0) as voice_seconds
                        FROM voice_session_history_hourly
                        WHERE guild_id = $1 
                        AND category_id = $2 
                        AND hour >= $3
                        AND hour <= $4
                    '''
                    params = [guild_id, category_id, window_start, window_end]

                    query, params = await self._apply_voice_state_filter(query, params, guild_id, 'state_flags')

                    query, params = await self._apply_bot_filter(query, params, guild_id, 'voice_session_history_hourly')

                    # Apply role filtering using current_role_members table
                    if role_filter_ids:
                        user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                        if user_ids:
                            placeholders = [
                                f"${len(params) + i + 1}" for i in range(len(user_ids))]
                            query += f" AND user_id IN ({', '.join(placeholders)})"
                            params.extend(user_ids)
                        else:
                            result[f'{d}d'] = 0
                            continue

                    query, params = await self._apply_comprehensive_blacklist_filters(
                        guild_id, guild, query, params, 'voice_session_history_hourly',
                        include_users=True, include_channels=False,
                        specific_category_id=category_id
                    )

                    try:
                        row = await conn.fetchrow(query, *params)
                    except asyncpg.exceptions.PostgresError as e:
                        raise DatabaseQueryError(
                            "Failed to fetch category voice timeseries",
                            context={'guild_id': guild_id,
                                     'category_id': category_id, 'days': d},
                            original=e
                        )

                    result[f'{d}d'] = row['voice_seconds'] or 0

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching category voice timeseries",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching category voice timeseries",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching category voice timeseries",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching category voice timeseries",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching category voice timeseries",
                    context={'guild_id': guild_id, 'category_id': category_id},
                    original=e
                )
            raise

    async def q_category_top5_voice_channels(self, guild_id: int, category_id: int,
                                             role_filter_ids: Optional[List[int]] = None,
                                             start_time: Optional[datetime] = None,
                                             end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get category's top 5 voice channels using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)
            state_flags_filter = await self._get_voice_state_filter_value(guild_id)

            async with self.pool.acquire() as conn:
                query = '''
                    SELECT 
                        channel_id,
                        COALESCE(SUM(total_seconds), 0) as total_seconds,
                        COALESCE(SUM(session_count), 0) as session_count
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1 
                    AND category_id = $2
                '''
                params = [guild_id, category_id]

                if state_flags_filter is not None:
                    query += f" AND state_flags = ${len(params) + 1}"
                    params.append(state_flags_filter)

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'voice_session_history_hourly')

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        query = query.replace(
                            "WHERE guild_id = $1 AND category_id = $2",
                            f"WHERE guild_id = $1 AND category_id = $2 AND user_id = ANY(${len(params) + 1}::bigint[])"
                        )
                        params.append(user_ids)
                    else:
                        return []

                query += '''
                    GROUP BY channel_id
                    HAVING SUM(total_seconds) > 0
                    ORDER BY total_seconds DESC
                    LIMIT 5
                '''

                rows = await conn.fetch(query, *params)

                total_query = '''
                    SELECT COALESCE(SUM(total_seconds), 0) as total_seconds
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1 
                    AND category_id = $2
                '''
                total_params = [guild_id, category_id]

                if state_flags_filter is not None:
                    total_query += f" AND state_flags = ${len(total_params) + 1}"
                    total_params.append(state_flags_filter)

                if start_time:
                    total_query += f" AND hour >= ${len(total_params) + 1}"
                    total_params.append(start_time)
                if end_time:
                    total_query += f" AND hour <= ${len(total_params) + 1}"
                    total_params.append(end_time)

                total_query, total_params = await self._apply_bot_filter(total_query, total_params, guild_id, 'voice_session_history_hourly')

                if role_filter_ids and 'user_ids' in locals() and user_ids:
                    total_query = total_query.replace(
                        "WHERE guild_id = $1 AND category_id = $2",
                        f"WHERE guild_id = $1 AND category_id = $2 AND user_id = ANY(${len(total_params) + 1}::bigint[])"
                    )
                    total_params.append(user_ids)

                total_row = await conn.fetchrow(total_query, *total_params)
                total_seconds = total_row['total_seconds'] if total_row else 0

                result = []
                for row in rows:
                    channel_seconds = row['total_seconds'] or 0
                    percentage = (channel_seconds / total_seconds *
                                  100) if total_seconds > 0 else 0

                    result.append({
                        'channel_id': row['channel_id'],
                        'total_seconds': channel_seconds,
                        'total_hours': round(channel_seconds / 3600, 2),
                        'session_count': row['session_count'] or 0,
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching category top voice channels",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching category top voice channels",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching category top voice channels",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching category top voice channels",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching category top voice channels",
                    context={'guild_id': guild_id, 'category_id': category_id},
                    original=e
                )
            raise

    async def q_category_top5_text_channels(self, guild_id: int, category_id: int,
                                            role_filter_ids: Optional[List[int]] = None,
                                            start_time: Optional[datetime] = None,
                                            end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get category's top 5 text channels using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                total_query = '''
                    SELECT COALESCE(SUM(message_count), 0) as total_messages
                    FROM message_tracking_hourly
                    WHERE guild_id = $1 AND category_id = $2
                '''
                total_params = [guild_id, category_id]

                if start_time:
                    total_query += f" AND hour >= ${len(total_params) + 1}"
                    total_params.append(start_time)
                if end_time:
                    total_query += f" AND hour <= ${len(total_params) + 1}"
                    total_params.append(end_time)

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        placeholders = [
                            f"${len(total_params) + i + 1}" for i in range(len(user_ids))]
                        total_query += f" AND user_id IN ({', '.join(placeholders)})"
                        total_params.extend(user_ids)
                    else:
                        return []

                total_query, total_params = await self._apply_bot_filter(total_query, total_params, guild_id, 'message_tracking_hourly')

                total_query, total_params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, total_query, total_params, 'message_tracking_hourly',
                    include_users=True, include_channels=False,
                    specific_category_id=category_id
                )

                total_row = await conn.fetchrow(total_query, *total_params)
                total_messages = total_row['total_messages'] or 0

                if total_messages == 0:
                    return []

                query = '''
                    SELECT 
                        channel_id,
                        COALESCE(SUM(message_count), 0) as message_count,
                        COALESCE(SUM(total_chars), 0) as total_chars,
                        COUNT(DISTINCT user_id) as unique_users,
                        COALESCE(SUM(total_chars) / NULLIF(SUM(message_count), 0), 0) as avg_chars
                    FROM message_tracking_hourly
                    WHERE guild_id = $1 AND category_id = $2
                '''
                params = [guild_id, category_id]

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        placeholders = [
                            f"${len(params) + i + 1}" for i in range(len(user_ids))]
                        query += f" AND user_id IN ({', '.join(placeholders)})"
                        params.extend(user_ids)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'message_tracking_hourly')

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'message_tracking_hourly',
                    include_users=True, include_channels=False,
                    specific_category_id=category_id
                )

                query += '''
                    GROUP BY channel_id
                    HAVING SUM(message_count) > 0
                    ORDER BY message_count DESC
                    LIMIT 5
                '''

                rows = await conn.fetch(query, *params)

                result = []
                for row in rows:
                    channel_messages = row['message_count'] or 0
                    percentage = (channel_messages / total_messages *
                                  100) if total_messages > 0 else 0

                    result.append({
                        'channel_id': row['channel_id'],
                        'message_count': channel_messages,
                        'total_chars': row['total_chars'] or 0,
                        'unique_users': row['unique_users'] or 0,
                        'avg_chars': round(row['avg_chars'] or 0, 2),
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching category top text channels",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching category top text channels",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching category top text channels",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching category top text channels",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching category top text channels",
                    context={'guild_id': guild_id, 'category_id': category_id},
                    original=e
                )
            raise

    async def q_category_top5_users_messages(self, guild_id: int, category_id: int,
                                             role_filter_ids: Optional[List[int]] = None,
                                             start_time: Optional[datetime] = None,
                                             end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get category's top 5 users by messages using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                total_query = '''
                    SELECT COALESCE(SUM(message_count), 0) as total_messages
                    FROM message_tracking_hourly
                    WHERE guild_id = $1 AND category_id = $2
                '''
                total_params = [guild_id, category_id]

                if start_time:
                    total_query += f" AND hour >= ${len(total_params) + 1}"
                    total_params.append(start_time)
                if end_time:
                    total_query += f" AND hour <= ${len(total_params) + 1}"
                    total_params.append(end_time)

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        placeholders = [
                            f"${len(total_params) + i + 1}" for i in range(len(user_ids))]
                        total_query += f" AND user_id IN ({', '.join(placeholders)})"
                        total_params.extend(user_ids)
                    else:
                        return []

                total_query, total_params = await self._apply_bot_filter(total_query, total_params, guild_id, 'message_tracking_hourly')

                total_query, total_params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, total_query, total_params, 'message_tracking_hourly',
                    include_users=True, include_channels=False,
                    specific_category_id=category_id
                )

                total_row = await conn.fetchrow(total_query, *total_params)
                total_messages = total_row['total_messages'] or 0

                if total_messages == 0:
                    return []

                query = '''
                    SELECT 
                        user_id,
                        COALESCE(SUM(message_count), 0) as message_count,
                        COALESCE(SUM(total_chars), 0) as total_chars,
                        COALESCE(SUM(total_chars) / NULLIF(SUM(message_count), 0), 0) as avg_chars
                    FROM message_tracking_hourly
                    WHERE guild_id = $1 AND category_id = $2
                '''
                params = [guild_id, category_id]

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        placeholders = [
                            f"${len(params) + i + 1}" for i in range(len(user_ids))]
                        query += f" AND user_id IN ({', '.join(placeholders)})"
                        params.extend(user_ids)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'message_tracking_hourly')

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'message_tracking_hourly',
                    include_users=True, include_channels=False,
                    specific_category_id=category_id
                )

                query += '''
                    GROUP BY user_id
                    HAVING SUM(message_count) > 0
                    ORDER BY message_count DESC
                    LIMIT 5
                '''

                rows = await conn.fetch(query, *params)

                result = []
                for row in rows:
                    user_messages = row['message_count'] or 0
                    percentage = (user_messages / total_messages *
                                  100) if total_messages > 0 else 0

                    result.append({
                        'user_id': row['user_id'],
                        'message_count': user_messages,
                        'total_chars': row['total_chars'] or 0,
                        'avg_chars': round(row['avg_chars'] or 0, 2),
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching category top users by messages",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching category top users by messages",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching category top users by messages",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching category top users by messages",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching category top users by messages",
                    context={'guild_id': guild_id, 'category_id': category_id},
                    original=e
                )
            raise

    async def q_category_top5_users_voice(self, guild_id: int, category_id: int,
                                          role_filter_ids: Optional[List[int]] = None,
                                          start_time: Optional[datetime] = None,
                                          end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get category's top 5 users by voice time using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)
            state_flags_filter = await self._get_voice_state_filter_value(guild_id)

            async with self.pool.acquire() as conn:
                total_query = '''
                    SELECT COALESCE(SUM(total_seconds), 0) as total_seconds
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1 AND category_id = $2
                '''
                total_params = [guild_id, category_id]

                if state_flags_filter is not None:
                    total_query += f" AND state_flags = ${len(total_params) + 1}"
                    total_params.append(state_flags_filter)

                if start_time:
                    total_query += f" AND hour >= ${len(total_params) + 1}"
                    total_params.append(start_time)
                if end_time:
                    total_query += f" AND hour <= ${len(total_params) + 1}"
                    total_params.append(end_time)

                total_query, total_params = await self._apply_voice_state_filter(total_query, total_params, guild_id, 'state_flags')

                total_query, total_params = await self._apply_bot_filter(total_query, total_params, guild_id, 'voice_session_history_hourly')

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        placeholders = [
                            f"${len(total_params) + i + 1}" for i in range(len(user_ids))]
                        total_query += f" AND user_id IN ({', '.join(placeholders)})"
                        total_params.extend(user_ids)
                    else:
                        return []

                total_query, total_params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, total_query, total_params, 'voice_session_history_hourly',
                    include_users=True, include_channels=False,
                    specific_category_id=category_id
                )

                total_row = await conn.fetchrow(total_query, *total_params)
                total_seconds = total_row['total_seconds'] or 0

                if total_seconds == 0:
                    return []

                query = '''
                    SELECT 
                        user_id,
                        COALESCE(SUM(total_seconds), 0) as total_seconds,
                        COALESCE(SUM(session_count), 0) as session_count,
                        COALESCE(SUM(total_seconds) / NULLIF(SUM(session_count), 0), 0) as avg_session
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1 AND category_id = $2
                '''
                params = [guild_id, category_id]

                if state_flags_filter is not None:
                    query += f" AND state_flags = ${len(params) + 1}"
                    params.append(state_flags_filter)

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_voice_state_filter(query, params, guild_id, 'state_flags')

                query, params = await self._apply_bot_filter(query, params, guild_id, 'voice_session_history_hourly')

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        placeholders = [
                            f"${len(params) + i + 1}" for i in range(len(user_ids))]
                        query += f" AND user_id IN ({', '.join(placeholders)})"
                        params.extend(user_ids)

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'voice_session_history_hourly',
                    include_users=True, include_channels=False,
                    specific_category_id=category_id
                )

                query += '''
                    GROUP BY user_id
                    HAVING SUM(total_seconds) > 0
                    ORDER BY total_seconds DESC
                    LIMIT 5
                '''

                rows = await conn.fetch(query, *params)

                result = []
                for row in rows:
                    user_seconds = row['total_seconds'] or 0
                    percentage = (user_seconds / total_seconds *
                                  100) if total_seconds > 0 else 0

                    result.append({
                        'user_id': row['user_id'],
                        'total_seconds': user_seconds,
                        'total_hours': round(user_seconds / 3600, 2),
                        'session_count': row['session_count'] or 0,
                        'avg_session': round(row['avg_session'] or 0, 2),
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching category top users by voice",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching category top users by voice",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching category top users by voice",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching category top users by voice",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching category top users by voice",
                    context={'guild_id': guild_id, 'category_id': category_id},
                    original=e
                )
            raise

    # ======================================================================
    # CHANNEL STATS - FIXED EXCEPTION HANDLING
    # ======================================================================

    async def q_channel_messages_per_hour(self, guild_id: int, channel_id: int,
                                          role_filter_ids: Optional[List[int]] = None,
                                          start_time: Optional[datetime] = None,
                                          end_time: Optional[datetime] = None,
                                          timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get message distribution by hour for a channel using hourly aggregated table."""
        if not self.pool:
            result = {f'hour_{i}': 0 for i in range(24)}
            result.update({'total': 0, 'peak_hour': -1})
            return result

        guild = self.bot.get_guild(guild_id)
        if not guild:
            result = {f'hour_{i}': 0 for i in range(24)}
            result.update({'total': 0, 'peak_hour': -1})
            return result

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = f'''
                    SELECT 
                        EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COALESCE(SUM(message_count), 0) as message_count
                    FROM message_tracking_hourly
                    WHERE guild_id = $1 
                    AND channel_id = $2
                '''
                params = [guild_id, channel_id]

                query, params = await self._apply_bot_filter(query, params, guild_id, 'message_tracking_hourly')

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        placeholders = [
                            f"${len(params) + i + 1}" for i in range(len(user_ids))]
                        query += f" AND user_id IN ({', '.join(placeholders)})"
                        params.extend(user_ids)
                    else:
                        result = {f'hour_{i}': 0 for i in range(24)}
                        result.update({'total': 0, 'peak_hour': -1})
                        return result

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'message_tracking_hourly',
                    include_users=True, include_channels=False,
                    specific_channel_id=channel_id
                )

                if query is None:
                    result = {f'hour_{i}': 0 for i in range(24)}
                    result.update({'total': 0, 'peak_hour': -1})
                    return result

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                try:
                    rows = await conn.fetch(query, *params)
                except asyncpg.exceptions.PostgresError as e:
                    raise DatabaseQueryError(
                        "Failed to fetch channel message hour distribution",
                        context={'guild_id': guild_id,
                                 'channel_id': channel_id},
                        original=e
                    )

                result = {f'hour_{i}': 0 for i in range(24)}
                total = 0
                peak_hour = -1
                peak_count = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    count = row['message_count'] or 0
                    result[f'hour_{hour}'] = count
                    total += count

                    if count > peak_count:
                        peak_count = count
                        peak_hour = hour

                result['total'] = total
                result['peak_hour'] = peak_hour

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching channel message hour distribution",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching channel message hour distribution",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching channel message hour distribution",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching channel message hour distribution",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching channel message hour distribution",
                    context={'guild_id': guild_id, 'channel_id': channel_id},
                    original=e
                )
            raise

    async def q_channel_voice_per_hour(self, guild_id: int, channel_id: int,
                                       role_filter_ids: Optional[List[int]] = None,
                                       start_time: Optional[datetime] = None,
                                       end_time: Optional[datetime] = None,
                                       timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get voice distribution by hour for a channel using hourly aggregated table."""
        if not self.pool:
            return {f'hour_{i}': 0 for i in range(24)} | {'total_seconds': 0, 'peak_hour': -1}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'hour_{i}': 0 for i in range(24)} | {'total_seconds': 0, 'peak_hour': -1}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = f'''
                    SELECT 
                        EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COALESCE(SUM(total_seconds), 0) as total_seconds
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1 
                    AND channel_id = $2
                '''
                params = [guild_id, channel_id]

                query, params = await self._apply_voice_state_filter(query, params, guild_id, 'state_flags')

                query, params = await self._apply_bot_filter(query, params, guild_id, 'voice_session_history_hourly')

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        placeholders = [
                            f"${len(params) + i + 1}" for i in range(len(user_ids))]
                        query += f" AND user_id IN ({', '.join(placeholders)})"
                        params.extend(user_ids)
                    else:
                        return {f'hour_{i}': 0 for i in range(24)} | {'total_seconds': 0, 'peak_hour': -1}

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'voice_session_history_hourly',
                    include_users=True, include_channels=False,
                    specific_channel_id=channel_id
                )

                if query is None:
                    return {f'hour_{i}': 0 for i in range(24)} | {'total_seconds': 0, 'peak_hour': -1}

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                try:
                    rows = await conn.fetch(query, *params)
                except asyncpg.exceptions.PostgresError as e:
                    raise DatabaseQueryError(
                        "Failed to fetch channel voice hour distribution",
                        context={'guild_id': guild_id,
                                 'channel_id': channel_id},
                        original=e
                    )

                result = {f'hour_{i}': 0 for i in range(24)}
                total_seconds = 0
                peak_hour = -1
                peak_seconds = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    seconds = row['total_seconds'] or 0
                    result[f'hour_{hour}'] = seconds
                    total_seconds += seconds

                    if seconds > peak_seconds:
                        peak_seconds = seconds
                        peak_hour = hour

                result['total_seconds'] = total_seconds
                result['peak_hour'] = peak_hour

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching channel voice hour distribution",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching channel voice hour distribution",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching channel voice hour distribution",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching channel voice hour distribution",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching channel voice hour distribution",
                    context={'guild_id': guild_id, 'channel_id': channel_id},
                    original=e
                )
            raise

    async def q_channel_top5_users_messages(self, guild_id: int, channel_id: int,
                                            role_filter_ids: Optional[List[int]] = None,
                                            start_time: Optional[datetime] = None,
                                            end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get channel's top 5 users by messages using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                total_query = '''
                    SELECT COALESCE(SUM(message_count), 0) as total_messages
                    FROM message_tracking_hourly
                    WHERE guild_id = $1 
                    AND channel_id = $2
                '''
                total_params = [guild_id, channel_id]

                if start_time:
                    total_query += f" AND hour >= ${len(total_params) + 1}"
                    total_params.append(start_time)
                if end_time:
                    total_query += f" AND hour <= ${len(total_params) + 1}"
                    total_params.append(end_time)

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        placeholders = [
                            f"${len(total_params) + i + 1}" for i in range(len(user_ids))]
                        total_query += f" AND user_id IN ({', '.join(placeholders)})"
                        total_params.extend(user_ids)
                    else:
                        return []

                total_query, total_params = await self._apply_bot_filter(total_query, total_params, guild_id, 'message_tracking_hourly')

                total_query, total_params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, total_query, total_params, 'message_tracking_hourly',
                    include_users=True, include_channels=False
                )

                if total_query is None:
                    return []

                total_row = await conn.fetchrow(total_query, *total_params)
                total_messages = total_row['total_messages'] or 0

                if total_messages == 0:
                    return []

                query = '''
                    SELECT 
                        user_id,
                        COALESCE(SUM(message_count), 0) as message_count,
                        COALESCE(SUM(total_chars), 0) as total_chars,
                        COALESCE(SUM(total_chars) / NULLIF(SUM(message_count), 0), 0) as avg_chars
                    FROM message_tracking_hourly
                    WHERE guild_id = $1 
                    AND channel_id = $2
                '''
                params = [guild_id, channel_id]

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        placeholders = [
                            f"${len(params) + i + 1}" for i in range(len(user_ids))]
                        query += f" AND user_id IN ({', '.join(placeholders)})"
                        params.extend(user_ids)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'message_tracking_hourly')

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'message_tracking_hourly',
                    include_users=True, include_channels=False
                )

                if query is None:
                    return []

                query += '''
                    GROUP BY user_id
                    HAVING SUM(message_count) > 0
                    ORDER BY message_count DESC
                    LIMIT 5
                '''

                rows = await conn.fetch(query, *params)

                result = []
                for row in rows:
                    user_messages = row['message_count'] or 0
                    percentage = (user_messages / total_messages *
                                  100) if total_messages > 0 else 0

                    result.append({
                        'user_id': row['user_id'],
                        'message_count': user_messages,
                        'total_chars': row['total_chars'] or 0,
                        'avg_chars': round(row['avg_chars'] or 0, 2),
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching channel top users by messages",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching channel top users by messages",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching channel top users by messages",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching channel top users by messages",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching channel top users by messages",
                    context={'guild_id': guild_id, 'channel_id': channel_id},
                    original=e
                )
            raise

    async def q_channel_top5_users_voice(self, guild_id: int, channel_id: int,
                                         role_filter_ids: Optional[List[int]] = None,
                                         start_time: Optional[datetime] = None,
                                         end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get channel's top 5 users by voice time using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)
            state_flags_filter = await self._get_voice_state_filter_value(guild_id)

            async with self.pool.acquire() as conn:
                query = '''
                    SELECT 
                        user_id,
                        COALESCE(SUM(total_seconds), 0) as total_seconds,
                        COALESCE(SUM(session_count), 0) as session_count,
                        COALESCE(SUM(total_seconds) / NULLIF(SUM(session_count), 0), 0) as avg_session
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1 
                    AND channel_id = $2
                '''
                params = [guild_id, channel_id]

                if state_flags_filter is not None:
                    query += f" AND state_flags = ${len(params) + 1}"
                    params.append(state_flags_filter)

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'voice_session_history_hourly')

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        query = query.replace(
                            "WHERE guild_id = $1 AND channel_id = $2",
                            f"WHERE guild_id = $1 AND channel_id = $2 AND user_id = ANY(${len(params) + 1}::bigint[])"
                        )
                        params.append(user_ids)
                    else:
                        return []

                query += '''
                    GROUP BY user_id
                    HAVING SUM(total_seconds) > 0
                    ORDER BY total_seconds DESC
                    LIMIT 5
                '''

                rows = await conn.fetch(query, *params)

                total_query = '''
                    SELECT COALESCE(SUM(total_seconds), 0) as total_seconds
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1 AND channel_id = $2
                '''
                total_params = [guild_id, channel_id]

                if state_flags_filter is not None:
                    total_query += f" AND state_flags = ${len(total_params) + 1}"
                    total_params.append(state_flags_filter)

                if start_time:
                    total_query += f" AND hour >= ${len(total_params) + 1}"
                    total_params.append(start_time)
                if end_time:
                    total_query += f" AND hour <= ${len(total_params) + 1}"
                    total_params.append(end_time)

                total_query, total_params = await self._apply_bot_filter(total_query, total_params, guild_id, 'voice_session_history_hourly')

                if role_filter_ids and 'user_ids' in locals() and user_ids:
                    total_query = total_query.replace(
                        "WHERE guild_id = $1 AND channel_id = $2",
                        f"WHERE guild_id = $1 AND channel_id = $2 AND user_id = ANY(${len(total_params) + 1}::bigint[])"
                    )
                    total_params.append(user_ids)

                total_row = await conn.fetchrow(total_query, *total_params)
                total_seconds = total_row['total_seconds'] if total_row else 0

                result = []
                for row in rows:
                    user_seconds = row['total_seconds'] or 0
                    percentage = (user_seconds / total_seconds *
                                  100) if total_seconds > 0 else 0

                    result.append({
                        'user_id': row['user_id'],
                        'total_seconds': user_seconds,
                        'total_hours': round(user_seconds / 3600, 2),
                        'session_count': row['session_count'] or 0,
                        'avg_session': round(row['avg_session'] or 0, 2),
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching channel top users by voice",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching channel top users by voice",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching channel top users by voice",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching channel top users by voice",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching channel top users by voice",
                    context={'guild_id': guild_id, 'channel_id': channel_id},
                    original=e
                )
            raise

    async def q_channel_timeseries_messages_1d_5d_10d_20d_30d(self, guild_id: int, channel_id: int,
                                                              role_filter_ids: Optional[List[int]] = None,
                                                              start_time: Optional[datetime] = None,
                                                              end_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Get channel message counts for different time periods using hourly aggregated table."""
        if not self.pool:
            return {'1d': 0, '5d': 0, '10d': 0, '20d': 0, '30d': 0}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {'1d': 0, '5d': 0, '10d': 0, '20d': 0, '30d': 0}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                periods = [1, 5, 10, 20, 30]
                result = {}
                end_time_actual = end_time if end_time else datetime.now(
                    timezone.utc)

                for days in periods:
                    window_start = end_time_actual - timedelta(days=days)
                    window_end = end_time_actual

                    if start_time and window_start < start_time:
                        window_start = start_time

                    query = '''
                        SELECT COALESCE(SUM(message_count), 0) as message_count
                        FROM message_tracking_hourly
                        WHERE guild_id = $1 
                        AND channel_id = $2
                        AND hour >= $3
                        AND hour <= $4
                    '''
                    params = [guild_id, channel_id, window_start, window_end]

                    query, params = await self._apply_bot_filter(query, params, guild_id, 'message_tracking_hourly')

                    # Apply role filtering using current_role_members table
                    if role_filter_ids:
                        user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                        if user_ids:
                            placeholders = [
                                f"${len(params) + i + 1}" for i in range(len(user_ids))]
                            query += f" AND user_id IN ({', '.join(placeholders)})"
                            params.extend(user_ids)
                        else:
                            result[f'{days}d'] = 0
                            continue

                    query, params = await self._apply_comprehensive_blacklist_filters(
                        guild_id, guild, query, params, 'message_tracking_hourly',
                        include_users=True, include_channels=False,
                        specific_channel_id=channel_id
                    )

                    if query is None:
                        result[f'{days}d'] = 0
                        continue

                    try:
                        row = await conn.fetchrow(query, *params)
                    except asyncpg.exceptions.PostgresError as e:
                        raise DatabaseQueryError(
                            "Failed to fetch channel message timeseries",
                            context={'guild_id': guild_id,
                                     'channel_id': channel_id, 'days': days},
                            original=e
                        )

                    result[f'{days}d'] = row['message_count'] or 0

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching channel message timeseries",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching channel message timeseries",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching channel message timeseries",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching channel message timeseries",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching channel message timeseries",
                    context={'guild_id': guild_id, 'channel_id': channel_id},
                    original=e
                )
            raise

    async def q_channel_timeseries_voice_1d_5d_10d_20d_30d(self, guild_id: int, channel_id: int,
                                                           role_filter_ids: Optional[List[int]] = None,
                                                           start_time: Optional[datetime] = None,
                                                           end_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Get channel voice seconds for different time periods using hourly aggregated table."""
        if not self.pool:
            return {'1d': 0, '5d': 0, '10d': 0, '20d': 0, '30d': 0}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {'1d': 0, '5d': 0, '10d': 0, '20d': 0, '30d': 0}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                periods = [1, 5, 10, 20, 30]
                result = {}
                end_time_actual = end_time if end_time else datetime.now(
                    timezone.utc)

                for days in periods:
                    window_start = end_time_actual - timedelta(days=days)
                    window_end = end_time_actual

                    if start_time and window_start < start_time:
                        window_start = start_time

                    query = '''
                        SELECT COALESCE(SUM(total_seconds), 0) as voice_seconds
                        FROM voice_session_history_hourly
                        WHERE guild_id = $1 
                        AND channel_id = $2 
                        AND hour >= $3
                        AND hour <= $4
                    '''
                    params = [guild_id, channel_id, window_start, window_end]

                    query, params = await self._apply_voice_state_filter(query, params, guild_id, 'state_flags')

                    query, params = await self._apply_bot_filter(query, params, guild_id, 'voice_session_history_hourly')

                    # Apply role filtering using current_role_members table
                    if role_filter_ids:
                        user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                        if user_ids:
                            placeholders = [
                                f"${len(params) + i + 1}" for i in range(len(user_ids))]
                            query += f" AND user_id IN ({', '.join(placeholders)})"
                            params.extend(user_ids)
                        else:
                            result[f'{days}d'] = 0
                            continue

                    query, params = await self._apply_comprehensive_blacklist_filters(
                        guild_id, guild, query, params, 'voice_session_history_hourly',
                        include_users=True, include_channels=False,
                        specific_channel_id=channel_id
                    )

                    if query is None:
                        result[f'{days}d'] = 0
                        continue

                    try:
                        row = await conn.fetchrow(query, *params)
                    except asyncpg.exceptions.PostgresError as e:
                        raise DatabaseQueryError(
                            "Failed to fetch channel voice timeseries",
                            context={'guild_id': guild_id,
                                     'channel_id': channel_id, 'days': days},
                            original=e
                        )

                    result[f'{days}d'] = row['voice_seconds'] or 0

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching channel voice timeseries",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching channel voice timeseries",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching channel voice timeseries",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching channel voice timeseries",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching channel voice timeseries",
                    context={'guild_id': guild_id, 'channel_id': channel_id},
                    original=e
                )
            raise

    async def q_channel_total_messages(self, guild_id: int, channel_id: int,
                                       role_filter_ids: Optional[List[int]] = None,
                                       start_time: Optional[datetime] = None,
                                       end_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Get total message stats for a channel using hourly aggregated table."""
        if not self.pool:
            return {
                'total_messages': 0, 'total_chars': 0, 'avg_chars': 0.0,
                'unique_users': 0, 'messages_per_user': 0.0,
                'has_attachments': 0, 'has_embeds': 0
            }

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {
                'total_messages': 0, 'total_chars': 0, 'avg_chars': 0.0,
                'unique_users': 0, 'messages_per_user': 0.0,
                'has_attachments': 0, 'has_embeds': 0
            }

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = '''
                    SELECT 
                        COALESCE(SUM(message_count), 0) as total_messages,
                        COALESCE(SUM(total_chars), 0) as total_chars,
                        COALESCE(SUM(total_chars) / NULLIF(SUM(message_count), 0), 0) as avg_chars,
                        COUNT(DISTINCT user_id) as unique_users,
                        COALESCE(SUM(attachment_count), 0) as has_attachments,
                        COALESCE(SUM(embed_count), 0) as has_embeds
                    FROM message_tracking_hourly
                    WHERE guild_id = $1 
                    AND channel_id = $2
                '''
                params = [guild_id, channel_id]

                query, params = await self._apply_bot_filter(query, params, guild_id, 'message_tracking_hourly')

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        placeholders = [
                            f"${len(params) + i + 1}" for i in range(len(user_ids))]
                        query += f" AND user_id IN ({', '.join(placeholders)})"
                        params.extend(user_ids)
                    else:
                        return {
                            'total_messages': 0, 'total_chars': 0, 'avg_chars': 0.0,
                            'unique_users': 0, 'messages_per_user': 0.0,
                            'has_attachments': 0, 'has_embeds': 0
                        }

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'message_tracking_hourly',
                    include_users=True, include_channels=False,
                    specific_channel_id=channel_id
                )

                if query is None:
                    return {
                        'total_messages': 0, 'total_chars': 0, 'avg_chars': 0.0,
                        'unique_users': 0, 'messages_per_user': 0.0,
                        'has_attachments': 0, 'has_embeds': 0
                    }

                try:
                    row = await conn.fetchrow(query, *params)
                except asyncpg.exceptions.PostgresError as e:
                    raise DatabaseQueryError(
                        "Failed to fetch channel total messages",
                        context={'guild_id': guild_id,
                                 'channel_id': channel_id},
                        original=e
                    )

                total_messages = row['total_messages'] or 0
                unique_users = row['unique_users'] or 0
                messages_per_user = total_messages / max(unique_users, 1)

                return {
                    'total_messages': total_messages,
                    'total_chars': row['total_chars'] or 0,
                    'avg_chars': round(row['avg_chars'] or 0, 2),
                    'unique_users': unique_users,
                    'messages_per_user': round(messages_per_user, 2),
                    'has_attachments': row['has_attachments'] or 0,
                    'has_embeds': row['has_embeds'] or 0
                }

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching channel total messages",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching channel total messages",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching channel total messages",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching channel total messages",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching channel total messages",
                    context={'guild_id': guild_id, 'channel_id': channel_id},
                    original=e
                )
            raise

    async def q_channel_total_voice(self, guild_id: int, channel_id: int,
                                    role_filter_ids: Optional[List[int]] = None,
                                    start_time: Optional[datetime] = None,
                                    end_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Get total voice stats for a channel using hourly aggregated table."""
        if not self.pool:
            return {
                'total_seconds': 0, 'total_hours': 0.0, 'session_count': 0,
                'unique_users': 0, 'avg_session': 0.0, 'seconds_per_user': 0.0
            }

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {
                'total_seconds': 0, 'total_hours': 0.0, 'session_count': 0,
                'unique_users': 0, 'avg_session': 0.0, 'seconds_per_user': 0.0
            }

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)
            state_flags_filter = await self._get_voice_state_filter_value(guild_id)

            async with self.pool.acquire() as conn:
                stats_query = '''
                    SELECT 
                        COALESCE(SUM(total_seconds), 0) as total_seconds,
                        COALESCE(SUM(session_count), 0) as session_count,
                        COALESCE(SUM(total_seconds) / NULLIF(SUM(session_count), 0), 0) as avg_session
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1 
                    AND channel_id = $2
                '''
                stats_params = [guild_id, channel_id]

                if state_flags_filter is not None:
                    stats_query += f" AND state_flags = ${len(stats_params) + 1}"
                    stats_params.append(state_flags_filter)

                if start_time:
                    stats_query += f" AND hour >= ${len(stats_params) + 1}"
                    stats_params.append(start_time)
                if end_time:
                    stats_query += f" AND hour <= ${len(stats_params) + 1}"
                    stats_params.append(end_time)

                stats_query, stats_params = await self._apply_bot_filter(stats_query, stats_params, guild_id, 'voice_session_history_hourly')

                users_query = '''
                    SELECT COUNT(DISTINCT user_id) as unique_users
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1 
                    AND channel_id = $2
                '''
                users_params = [guild_id, channel_id]

                if state_flags_filter is not None:
                    users_query += f" AND state_flags = ${len(users_params) + 1}"
                    users_params.append(state_flags_filter)

                if start_time:
                    users_query += f" AND hour >= ${len(users_params) + 1}"
                    users_params.append(start_time)
                if end_time:
                    users_query += f" AND hour <= ${len(users_params) + 1}"
                    users_params.append(end_time)

                users_query, users_params = await self._apply_bot_filter(users_query, users_params, guild_id, 'voice_session_history_hourly')

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        stats_query = stats_query.replace(
                            "WHERE guild_id = $1 AND channel_id = $2",
                            f"WHERE guild_id = $1 AND channel_id = $2 AND user_id = ANY(${len(stats_params) + 1}::bigint[])"
                        )
                        stats_params.append(user_ids)

                        users_query = users_query.replace(
                            "WHERE guild_id = $1 AND channel_id = $2",
                            f"WHERE guild_id = $1 AND channel_id = $2 AND user_id = ANY(${len(users_params) + 1}::bigint[])"
                        )
                        users_params.append(user_ids)
                    else:
                        return {
                            'total_seconds': 0, 'total_hours': 0.0, 'session_count': 0,
                            'unique_users': 0, 'avg_session': 0.0, 'seconds_per_user': 0.0
                        }

                try:
                    stats_row = await conn.fetchrow(stats_query, *stats_params)
                    users_row = await conn.fetchrow(users_query, *users_params)
                except asyncpg.exceptions.PostgresError as e:
                    raise DatabaseQueryError(
                        "Failed to fetch channel total voice stats",
                        context={'guild_id': guild_id,
                                 'channel_id': channel_id},
                        original=e
                    )

                total_seconds = stats_row['total_seconds'] if stats_row else 0
                unique_users = users_row['unique_users'] if users_row else 0
                seconds_per_user = total_seconds / max(unique_users, 1)

                return {
                    'total_seconds': total_seconds,
                    'total_hours': round(total_seconds / 3600, 2),
                    'session_count': stats_row['session_count'] if stats_row else 0,
                    'unique_users': unique_users,
                    'avg_session': round(stats_row['avg_session'] or 0, 2),
                    'seconds_per_user': round(seconds_per_user, 2)
                }

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching channel total voice",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching channel total voice",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching channel total voice",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching channel total voice",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching channel total voice",
                    context={'guild_id': guild_id, 'channel_id': channel_id},
                    original=e
                )
            raise

    # ======================================================================
    # LEADERBOARD SERVER - FIXED EXCEPTION HANDLING
    # ======================================================================

    async def q_leaderboard_server_top_text_channels(self, guild_id: int,
                                                     limit: int = 100000000000,
                                                     role_filter_ids: Optional[List[int]] = None,
                                                     start_time: Optional[datetime] = None,
                                                     end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get server leaderboard of top text channels using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                total_query = '''
                    SELECT COALESCE(SUM(message_count), 0) as total_messages
                    FROM message_tracking_hourly
                    WHERE guild_id = $1
                '''
                total_params = [guild_id]

                if start_time:
                    total_query += f" AND hour >= ${len(total_params) + 1}"
                    total_params.append(start_time)
                if end_time:
                    total_query += f" AND hour <= ${len(total_params) + 1}"
                    total_params.append(end_time)

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        placeholders = [
                            f"${len(total_params) + i + 1}" for i in range(len(user_ids))]
                        total_query += f" AND user_id IN ({', '.join(placeholders)})"
                        total_params.extend(user_ids)
                    else:
                        return []

                total_query, total_params = await self._apply_bot_filter(total_query, total_params, guild_id, 'message_tracking_hourly')

                total_query, total_params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, total_query, total_params, 'message_tracking_hourly',
                    include_users=True, include_channels=True
                )

                total_row = await conn.fetchrow(total_query, *total_params)
                total_messages = total_row['total_messages'] or 0

                if total_messages == 0:
                    return []

                query = '''
                    SELECT 
                        channel_id,
                        COALESCE(SUM(message_count), 0) as message_count,
                        COALESCE(SUM(total_chars), 0) as total_chars,
                        COUNT(DISTINCT user_id) as unique_users,
                        COALESCE(SUM(total_chars) / NULLIF(SUM(message_count), 0), 0) as avg_chars
                    FROM message_tracking_hourly
                    WHERE guild_id = $1
                '''
                params = [guild_id]

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        placeholders = [
                            f"${len(params) + i + 1}" for i in range(len(user_ids))]
                        query += f" AND user_id IN ({', '.join(placeholders)})"
                        params.extend(user_ids)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'message_tracking_hourly')

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'message_tracking_hourly',
                    include_users=True, include_channels=True
                )

                query += f'''
                    GROUP BY channel_id
                    HAVING SUM(message_count) > 0
                    ORDER BY message_count DESC
                    LIMIT {limit}
                '''

                rows = await conn.fetch(query, *params)

                result = []
                for row in rows:
                    channel_messages = row['message_count'] or 0
                    percentage = (channel_messages / total_messages *
                                  100) if total_messages > 0 else 0

                    result.append({
                        'channel_id': row['channel_id'],
                        'message_count': channel_messages,
                        'total_chars': row['total_chars'] or 0,
                        'unique_users': row['unique_users'] or 0,
                        'avg_chars': round(row['avg_chars'] or 0, 2),
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching server top text channels leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching server top text channels leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching server top text channels leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching server top text channels leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching server top text channels leaderboard",
                    context={'guild_id': guild_id},
                    original=e
                )
            raise

    async def q_leaderboard_server_top_voice_channels(self, guild_id: int,
                                                      limit: int = 100000000000,
                                                      role_filter_ids: Optional[List[int]] = None,
                                                      start_time: Optional[datetime] = None,
                                                      end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get server leaderboard of top voice channels using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)
            state_flags_filter = await self._get_voice_state_filter_value(guild_id)

            async with self.pool.acquire() as conn:
                query = '''
                    SELECT 
                        channel_id,
                        COALESCE(SUM(total_seconds), 0) as total_seconds,
                        COALESCE(SUM(session_count), 0) as session_count
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1
                '''
                params = [guild_id]

                if state_flags_filter is not None:
                    query += f" AND state_flags = ${len(params) + 1}"
                    params.append(state_flags_filter)

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'voice_session_history_hourly')

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        query = query.replace(
                            "WHERE guild_id = $1",
                            f"WHERE guild_id = $1 AND user_id = ANY(${len(params) + 1}::bigint[])"
                        )
                        params.append(user_ids)
                    else:
                        return []

                query += '''
                    GROUP BY channel_id
                    HAVING SUM(total_seconds) > 0
                    ORDER BY total_seconds DESC
                '''

                if limit:
                    query += f" LIMIT {limit}"

                rows = await conn.fetch(query, *params)

                total_query = '''
                    SELECT COALESCE(SUM(total_seconds), 0) as total_seconds
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1
                '''
                total_params = [guild_id]

                if state_flags_filter is not None:
                    total_query += f" AND state_flags = ${len(total_params) + 1}"
                    total_params.append(state_flags_filter)

                if start_time:
                    total_query += f" AND hour >= ${len(total_params) + 1}"
                    total_params.append(start_time)
                if end_time:
                    total_query += f" AND hour <= ${len(total_params) + 1}"
                    total_params.append(end_time)

                total_query, total_params = await self._apply_bot_filter(total_query, total_params, guild_id, 'voice_session_history_hourly')

                if role_filter_ids and 'user_ids' in locals() and user_ids:
                    total_query = total_query.replace(
                        "WHERE guild_id = $1",
                        f"WHERE guild_id = $1 AND user_id = ANY(${len(total_params) + 1}::bigint[])"
                    )
                    total_params.append(user_ids)

                total_row = await conn.fetchrow(total_query, *total_params)
                total_seconds = total_row['total_seconds'] if total_row else 0

                result = []
                for row in rows:
                    channel_seconds = row['total_seconds'] or 0
                    percentage = (channel_seconds / total_seconds *
                                  100) if total_seconds > 0 else 0

                    result.append({
                        'channel_id': row['channel_id'],
                        'total_seconds': channel_seconds,
                        'total_hours': round(channel_seconds / 3600, 2),
                        'session_count': row['session_count'] or 0,
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching server top voice channels leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching server top voice channels leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching server top voice channels leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching server top voice channels leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching server top voice channels leaderboard",
                    context={'guild_id': guild_id},
                    original=e
                )
            raise

    async def q_leaderboard_server_top_categories_messages(self, guild_id: int,
                                                           limit: int = 100000000000,
                                                           role_filter_ids: Optional[List[int]] = None,
                                                           start_time: Optional[datetime] = None,
                                                           end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get server leaderboard of top categories by messages using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                total_query = '''
                    SELECT COALESCE(SUM(message_count), 0) as total_messages
                    FROM message_tracking_hourly
                    WHERE guild_id = $1
                '''
                total_params = [guild_id]

                if start_time:
                    total_query += f" AND hour >= ${len(total_params) + 1}"
                    total_params.append(start_time)
                if end_time:
                    total_query += f" AND hour <= ${len(total_params) + 1}"
                    total_params.append(end_time)

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        placeholders = [
                            f"${len(total_params) + i + 1}" for i in range(len(user_ids))]
                        total_query += f" AND user_id IN ({', '.join(placeholders)})"
                        total_params.extend(user_ids)
                    else:
                        return []

                total_query, total_params = await self._apply_bot_filter(total_query, total_params, guild_id, 'message_tracking_hourly')

                total_query, total_params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, total_query, total_params, 'message_tracking_hourly',
                    include_users=True, include_channels=True
                )

                total_row = await conn.fetchrow(total_query, *total_params)
                total_messages = total_row['total_messages'] or 0

                if total_messages == 0:
                    return []

                query = '''
                    SELECT 
                        category_id,
                        COALESCE(SUM(message_count), 0) as message_count,
                        COALESCE(SUM(total_chars), 0) as total_chars,
                        COUNT(DISTINCT user_id) as unique_users,
                        COALESCE(SUM(total_chars) / NULLIF(SUM(message_count), 0), 0) as avg_chars
                    FROM message_tracking_hourly
                    WHERE guild_id = $1 
                    AND category_id IS NOT NULL
                '''
                params = [guild_id]

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        placeholders = [
                            f"${len(params) + i + 1}" for i in range(len(user_ids))]
                        query += f" AND user_id IN ({', '.join(placeholders)})"
                        params.extend(user_ids)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'message_tracking_hourly')

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'message_tracking_hourly',
                    include_users=True, include_channels=True
                )

                query += f'''
                    GROUP BY category_id
                    HAVING SUM(message_count) > 0
                    ORDER BY message_count DESC
                    LIMIT {limit}
                '''

                rows = await conn.fetch(query, *params)

                result = []
                for row in rows:
                    category_messages = row['message_count'] or 0
                    percentage = (category_messages / total_messages *
                                  100) if total_messages > 0 else 0

                    result.append({
                        'category_id': row['category_id'],
                        'message_count': category_messages,
                        'total_chars': row['total_chars'] or 0,
                        'unique_users': row['unique_users'] or 0,
                        'avg_chars': round(row['avg_chars'] or 0, 2),
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching server top categories by messages leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching server top categories by messages leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching server top categories by messages leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching server top categories by messages leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching server top categories by messages leaderboard",
                    context={'guild_id': guild_id},
                    original=e
                )
            raise

    async def q_leaderboard_server_top_categories_voice(self, guild_id: int,
                                                        limit: int = 100000000000,
                                                        role_filter_ids: Optional[List[int]] = None,
                                                        start_time: Optional[datetime] = None,
                                                        end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get server leaderboard of top categories by voice time using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)
            state_flags_filter = await self._get_voice_state_filter_value(guild_id)

            async with self.pool.acquire() as conn:
                # Build base query
                query = '''
                    SELECT 
                        category_id,
                        COALESCE(SUM(total_seconds), 0) as total_seconds,
                        COALESCE(SUM(session_count), 0) as session_count
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1
                '''
                params = [guild_id]
                param_index = 2

                if state_flags_filter is not None:
                    query += f" AND state_flags = ${param_index}"
                    params.append(state_flags_filter)
                    param_index += 1

                if start_time:
                    query += f" AND hour >= ${param_index}"
                    params.append(start_time)
                    param_index += 1
                if end_time:
                    query += f" AND hour <= ${param_index}"
                    params.append(end_time)
                    param_index += 1

                query, params = await self._apply_bot_filter(query, params, guild_id, 'voice_session_history_hourly')

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    # Get user IDs with the specified roles
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        # IMPORTANT: Convert the list to PostgreSQL array format correctly
                        # Use $param_index with ::bigint[] cast
                        query += f" AND user_id = ANY(${param_index}::bigint[])"
                        params.append(user_ids)
                        param_index += 1
                    else:
                        return []

                query += '''
                    GROUP BY category_id
                    HAVING SUM(total_seconds) > 0
                    ORDER BY total_seconds DESC
                '''

                if limit:
                    query += f" LIMIT ${param_index}"
                    params.append(limit)

                # Execute the query
                try:
                    rows = await conn.fetch(query, *params)
                except asyncpg.exceptions.PostgresError as e:
                    # Log the actual query for debugging

                    raise DatabaseQueryError(
                        "Failed to fetch server top categories by voice leaderboard",
                        context={'guild_id': guild_id},
                        original=e
                    )

                # Get total for percentage calculation
                total_query = '''
                    SELECT COALESCE(SUM(total_seconds), 0) as total_seconds
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1
                '''
                total_params = [guild_id]
                total_param_index = 2

                if state_flags_filter is not None:
                    total_query += f" AND state_flags = ${total_param_index}"
                    total_params.append(state_flags_filter)
                    total_param_index += 1

                if start_time:
                    total_query += f" AND hour >= ${total_param_index}"
                    total_params.append(start_time)
                    total_param_index += 1
                if end_time:
                    total_query += f" AND hour <= ${total_param_index}"
                    total_params.append(end_time)
                    total_param_index += 1

                total_query, total_params = await self._apply_bot_filter(total_query, total_params, guild_id, 'voice_session_history_hourly')

                if role_filter_ids and 'user_ids' in locals() and user_ids:
                    total_query += f" AND user_id = ANY(${total_param_index}::bigint[])"
                    total_params.append(user_ids)

                total_row = await conn.fetchrow(total_query, *total_params)
                total_seconds = total_row['total_seconds'] if total_row else 0

                result = []
                for row in rows:
                    category_seconds = row['total_seconds'] or 0
                    percentage = (category_seconds / total_seconds *
                                  100) if total_seconds > 0 else 0

                    result.append({
                        'category_id': row['category_id'],
                        'total_seconds': category_seconds,
                        'total_hours': round(category_seconds / 3600, 2),
                        'session_count': row['session_count'] or 0,
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching server top categories by voice leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching server top categories by voice leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching server top categories by voice leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching server top categories by voice leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching server top categories by voice leaderboard",
                    context={'guild_id': guild_id},
                    original=e
                )
            raise

    # ======================================================================
    # LEADERBOARD CHANNEL - FIXED EXCEPTION HANDLING
    # ======================================================================

    async def q_leaderboard_text_users_in_channel(self, guild_id: int, channel_id: int,
                                                  limit: int = 100000000000,
                                                  role_filter_ids: Optional[List[int]] = None,
                                                  start_time: Optional[datetime] = None,
                                                  end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get leaderboard of users in a text channel using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                # Build base query
                query = '''
                    SELECT 
                        user_id,
                        COALESCE(SUM(message_count), 0) as message_count,
                        COALESCE(SUM(total_chars), 0) as total_chars,
                        COALESCE(SUM(total_chars) / NULLIF(SUM(message_count), 0), 0) as avg_chars
                    FROM message_tracking_hourly
                    WHERE guild_id = $1 
                    AND channel_id = $2
                '''
                params = [guild_id, channel_id]
                param_index = 3

                if start_time:
                    query += f" AND hour >= ${param_index}"
                    params.append(start_time)
                    param_index += 1
                if end_time:
                    query += f" AND hour <= ${param_index}"
                    params.append(end_time)
                    param_index += 1

                # Apply bot filter
                query, params = await self._apply_bot_filter(query, params, guild_id, 'message_tracking_hourly')
                param_index = len(params) + 1

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        # FIXED: Added ::bigint[] cast
                        query += f" AND user_id = ANY(${param_index}::bigint[])"
                        params.append(user_ids)
                        param_index += 1
                    else:
                        return []

                # Get total for percentage calculation
                total_query = '''
                    SELECT COALESCE(SUM(message_count), 0) as total_messages
                    FROM message_tracking_hourly
                    WHERE guild_id = $1 AND channel_id = $2
                '''
                total_params = [guild_id, channel_id]
                total_param_index = 3

                if start_time:
                    total_query += f" AND hour >= ${total_param_index}"
                    total_params.append(start_time)
                    total_param_index += 1
                if end_time:
                    total_query += f" AND hour <= ${total_param_index}"
                    total_params.append(end_time)
                    total_param_index += 1

                total_query, total_params = await self._apply_bot_filter(total_query, total_params, guild_id, 'message_tracking_hourly')

                if role_filter_ids and 'user_ids' in locals() and user_ids:
                    total_query += f" AND user_id = ANY(${total_param_index}::bigint[])"
                    total_params.append(user_ids)

                total_row = await conn.fetchrow(total_query, *total_params)
                total_messages = total_row['total_messages'] if total_row else 0

                if total_messages == 0:
                    return []

                # Complete the main query
                query += '''
                    GROUP BY user_id
                    HAVING SUM(message_count) > 0
                    ORDER BY message_count DESC
                '''

                if limit:
                    query += f" LIMIT ${param_index}"
                    params.append(limit)

                rows = await conn.fetch(query, *params)

                result = []
                for row in rows:
                    user_messages = row['message_count'] or 0
                    percentage = (user_messages / total_messages *
                                  100) if total_messages > 0 else 0

                    result.append({
                        'user_id': row['user_id'],
                        'message_count': user_messages,
                        'total_chars': row['total_chars'] or 0,
                        'avg_chars': round(row['avg_chars'] or 0, 2),
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching channel text user leaderboard",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching channel text user leaderboard",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching channel text user leaderboard",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching channel text user leaderboard",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching channel text user leaderboard",
                    context={'guild_id': guild_id, 'channel_id': channel_id},
                    original=e
                )
            raise

    async def q_leaderboard_voice_users_in_channel(self, guild_id: int, channel_id: int,
                                                   limit: int = 100000000000,
                                                   role_filter_ids: Optional[List[int]] = None,
                                                   start_time: Optional[datetime] = None,
                                                   end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get leaderboard of users in a voice channel using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)
            state_flags_filter = await self._get_voice_state_filter_value(guild_id)

            async with self.pool.acquire() as conn:
                # Build base query
                query = '''
                    SELECT 
                        user_id,
                        COALESCE(SUM(total_seconds), 0) as total_seconds,
                        COALESCE(SUM(session_count), 0) as session_count,
                        COALESCE(SUM(total_seconds) / NULLIF(SUM(session_count), 0), 0) as avg_session
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1 
                    AND channel_id = $2
                '''
                params = [guild_id, channel_id]
                param_index = 3

                # Apply voice state filter
                if state_flags_filter is not None:
                    query += f" AND state_flags = ${param_index}"
                    params.append(state_flags_filter)
                    param_index += 1

                if start_time:
                    query += f" AND hour >= ${param_index}"
                    params.append(start_time)
                    param_index += 1
                if end_time:
                    query += f" AND hour <= ${param_index}"
                    params.append(end_time)
                    param_index += 1

                # Apply bot filter
                query, params = await self._apply_bot_filter(query, params, guild_id, 'voice_session_history_hourly')
                param_index = len(params) + 1

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        # FIXED: Use ::bigint[] cast
                        query += f" AND user_id = ANY(${param_index}::bigint[])"
                        params.append(user_ids)
                        param_index += 1
                    else:
                        return []

                query += '''
                    GROUP BY user_id
                    HAVING SUM(total_seconds) > 0
                    ORDER BY total_seconds DESC
                '''

                if limit:
                    query += f" LIMIT ${param_index}"
                    params.append(limit)

                rows = await conn.fetch(query, *params)

                # Get total for percentage calculation
                total_query = '''
                    SELECT COALESCE(SUM(total_seconds), 0) as total_seconds
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1 AND channel_id = $2
                '''
                total_params = [guild_id, channel_id]
                total_param_index = 3

                if state_flags_filter is not None:
                    total_query += f" AND state_flags = ${total_param_index}"
                    total_params.append(state_flags_filter)
                    total_param_index += 1

                if start_time:
                    total_query += f" AND hour >= ${total_param_index}"
                    total_params.append(start_time)
                    total_param_index += 1
                if end_time:
                    total_query += f" AND hour <= ${total_param_index}"
                    total_params.append(end_time)
                    total_param_index += 1

                total_query, total_params = await self._apply_bot_filter(total_query, total_params, guild_id, 'voice_session_history_hourly')

                if role_filter_ids and 'user_ids' in locals() and user_ids:
                    total_query += f" AND user_id = ANY(${total_param_index}::bigint[])"
                    total_params.append(user_ids)

                total_row = await conn.fetchrow(total_query, *total_params)
                total_seconds = total_row['total_seconds'] if total_row else 0

                result = []
                for row in rows:
                    user_seconds = row['total_seconds'] or 0
                    percentage = (user_seconds / total_seconds *
                                  100) if total_seconds > 0 else 0

                    result.append({
                        'user_id': row['user_id'],
                        'total_seconds': user_seconds,
                        'total_hours': round(user_seconds / 3600, 2),
                        'session_count': row['session_count'] or 0,
                        'avg_session': round(row['avg_session'] or 0, 2),
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching channel voice user leaderboard",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching channel voice user leaderboard",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching channel voice user leaderboard",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching channel voice user leaderboard",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching channel voice user leaderboard",
                    context={'guild_id': guild_id, 'channel_id': channel_id},
                    original=e
                )
            raise

    # ======================================================================
    # LEADERBOARD MENTIONS - NO AGGREGATION NEEDED (static table)
    # ======================================================================

    async def q_leaderboard_mentions_target_user(self, guild_id: int, mentioned_user_id: int,
                                                 limit: int = 100000000000,
                                                 role_filter_ids: Optional[List[int]] = None,
                                                 start_time: Optional[datetime] = None,
                                                 end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get leaderboard of users who mention a target user using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                # Build base query using hourly aggregated table
                query = '''
                    SELECT 
                        mentioner_user_id,
                        SUM(mention_count) as mention_count,
                        MAX(hour) as last_mention
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 
                    AND mentioned_user_id = $2
                '''
                params = [guild_id, mentioned_user_id]
                param_index = 3

                if start_time:
                    query += f" AND hour >= ${param_index}"
                    params.append(start_time)
                    param_index += 1
                if end_time:
                    query += f" AND hour <= ${param_index}"
                    params.append(end_time)
                    param_index += 1

                # Apply bot filter
                query, params = await self._apply_bot_filter(query, params, guild_id, 'user_mentions_hourly')
                param_index = len(params) + 1

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        query += f" AND mentioner_user_id = ANY(${param_index}::bigint[])"
                        params.append(user_ids)
                        param_index += 1
                    else:
                        return []

                # ✅ Now this will work correctly - it will use mentioner_user_id instead of user_id
                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'user_mentions_hourly',
                    include_users=True, include_channels=True
                )

                # Complete the query
                query += '''
                    GROUP BY mentioner_user_id
                    HAVING SUM(mention_count) > 0
                    ORDER BY mention_count DESC
                '''

                if limit and limit < 100000000000:
                    query += f" LIMIT ${len(params) + 1}"
                    params.append(limit)

                # Total query for percentage calculation
                total_query = '''
                    SELECT COALESCE(SUM(mention_count), 0) as total_mentions
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 AND mentioned_user_id = $2
                '''
                total_params = [guild_id, mentioned_user_id]
                total_param_index = 3

                if start_time:
                    total_query += f" AND hour >= ${total_param_index}"
                    total_params.append(start_time)
                    total_param_index += 1
                if end_time:
                    total_query += f" AND hour <= ${total_param_index}"
                    total_params.append(end_time)
                    total_param_index += 1

                total_query, total_params = await self._apply_bot_filter(total_query, total_params, guild_id, 'user_mentions_hourly')

                if role_filter_ids and 'user_ids' in locals() and user_ids:
                    total_query += f" AND mentioner_user_id = ANY(${total_param_index}::bigint[])"
                    total_params.append(user_ids)

                total_row = await conn.fetchrow(total_query, *total_params)
                total_mentions = total_row['total_mentions'] if total_row else 0

                if total_mentions == 0:
                    return []

                # Execute the main query
                rows = await conn.fetch(query, *params)

                result = []
                for row in rows:
                    user_mentions = row['mention_count'] or 0
                    percentage = (user_mentions / total_mentions *
                                  100) if total_mentions > 0 else 0

                    result.append({
                        'user_id': row['mentioner_user_id'],
                        'mention_count': user_mentions,
                        'last_mention': row['last_mention'].isoformat() if row['last_mention'] else None,
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching mentions leaderboard",
                context={'guild_id': guild_id,
                         'mentioned_user_id': mentioned_user_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching mentions leaderboard",
                context={'guild_id': guild_id,
                         'mentioned_user_id': mentioned_user_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching mentions leaderboard",
                context={'guild_id': guild_id,
                         'mentioned_user_id': mentioned_user_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching mentions leaderboard",
                context={'guild_id': guild_id,
                         'mentioned_user_id': mentioned_user_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching mentions leaderboard",
                    context={'guild_id': guild_id,
                             'mentioned_user_id': mentioned_user_id},
                    original=e
                )
            raise
    # ======================================================================
    # MENTIONS LEADERBOARD QUERIES - ENHANCED WITH SCOPE SUPPORT
    # ======================================================================

    async def q_leaderboard_mentions_target_user_server(
        self, guild_id: int, target_user_id: int,
        limit: int = 100,
        role_filter_ids: Optional[List[int]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get leaderboard of users who mention a target user (SERVER SCOPE).
        Shows top users that mentioned the target user in the server.
        """
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = '''
                    SELECT 
                        mentioner_user_id,
                        SUM(mention_count) as mention_count,
                        MAX(hour) as last_mention
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 
                    AND mentioned_user_id = $2
                '''
                params = [guild_id, target_user_id]
                param_index = 3

                if start_time:
                    query += f" AND hour >= ${param_index}"
                    params.append(start_time)
                    param_index += 1
                if end_time:
                    query += f" AND hour <= ${param_index}"
                    params.append(end_time)
                    param_index += 1

                query, params = await self._apply_bot_filter(query, params, guild_id, 'user_mentions_hourly')
                param_index = len(params) + 1

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        query += f" AND mentioner_user_id = ANY(${param_index}::bigint[])"
                        params.append(user_ids)
                        param_index += 1
                    else:
                        return []

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'user_mentions_hourly',
                    include_users=True, include_channels=True
                )

                total_query = '''
                    SELECT COALESCE(SUM(mention_count), 0) as total_mentions
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 AND mentioned_user_id = $2
                '''
                total_params = [guild_id, target_user_id]
                total_param_index = 3

                if start_time:
                    total_query += f" AND hour >= ${total_param_index}"
                    total_params.append(start_time)
                    total_param_index += 1
                if end_time:
                    total_query += f" AND hour <= ${total_param_index}"
                    total_params.append(end_time)
                    total_param_index += 1

                total_query, total_params = await self._apply_bot_filter(total_query, total_params, guild_id, 'user_mentions_hourly')

                if role_filter_ids and 'user_ids' in locals() and user_ids:
                    total_query += f" AND mentioner_user_id = ANY(${total_param_index}::bigint[])"
                    total_params.append(user_ids)

                total_row = await conn.fetchrow(total_query, *total_params)
                total_mentions = total_row['total_mentions'] if total_row else 0

                if total_mentions == 0:
                    return []

                query += '''
                    GROUP BY mentioner_user_id
                    HAVING SUM(mention_count) > 0
                    ORDER BY mention_count DESC
                '''

                if limit:
                    query += f" LIMIT ${param_index}"
                    params.append(limit)

                rows = await conn.fetch(query, *params)

                result = []
                for row in rows:
                    user_mentions = row['mention_count'] or 0
                    percentage = (user_mentions / total_mentions *
                                  100) if total_mentions > 0 else 0

                    result.append({
                        'user_id': row['mentioner_user_id'],
                        'mention_count': user_mentions,
                        'last_mention': row['last_mention'].isoformat() if row['last_mention'] else None,
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch server mentions leaderboard for target user",
                context={'guild_id': guild_id,
                         'target_user_id': target_user_id},
                original=e
            )

    async def q_leaderboard_mentions_target_user_channel(
        self, guild_id: int, channel_id: int, target_user_id: int,
        limit: int = 100,
        role_filter_ids: Optional[List[int]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get leaderboard of users who mention a target user (CHANNEL SCOPE).
        Shows top users that mentioned the target user in a specific channel.
        """
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = '''
                    SELECT 
                        mentioner_user_id,
                        SUM(mention_count) as mention_count,
                        MAX(hour) as last_mention
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 
                    AND channel_id = $2
                    AND mentioned_user_id = $3
                '''
                params = [guild_id, channel_id, target_user_id]
                param_index = 4

                if start_time:
                    query += f" AND hour >= ${param_index}"
                    params.append(start_time)
                    param_index += 1
                if end_time:
                    query += f" AND hour <= ${param_index}"
                    params.append(end_time)
                    param_index += 1

                query, params = await self._apply_bot_filter(query, params, guild_id, 'user_mentions_hourly')
                param_index = len(params) + 1

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        query += f" AND mentioner_user_id = ANY(${param_index}::bigint[])"
                        params.append(user_ids)
                        param_index += 1
                    else:
                        return []

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'user_mentions_hourly',
                    include_users=True, include_channels=False,
                    specific_channel_id=channel_id
                )

                total_query = '''
                    SELECT COALESCE(SUM(mention_count), 0) as total_mentions
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 AND channel_id = $2 AND mentioned_user_id = $3
                '''
                total_params = [guild_id, channel_id, target_user_id]
                total_param_index = 4

                if start_time:
                    total_query += f" AND hour >= ${total_param_index}"
                    total_params.append(start_time)
                    total_param_index += 1
                if end_time:
                    total_query += f" AND hour <= ${total_param_index}"
                    total_params.append(end_time)
                    total_param_index += 1

                total_query, total_params = await self._apply_bot_filter(total_query, total_params, guild_id, 'user_mentions_hourly')

                if role_filter_ids and 'user_ids' in locals() and user_ids:
                    total_query += f" AND mentioner_user_id = ANY(${total_param_index}::bigint[])"
                    total_params.append(user_ids)

                total_row = await conn.fetchrow(total_query, *total_params)
                total_mentions = total_row['total_mentions'] if total_row else 0

                if total_mentions == 0:
                    return []

                query += '''
                    GROUP BY mentioner_user_id
                    HAVING SUM(mention_count) > 0
                    ORDER BY mention_count DESC
                '''

                if limit:
                    query += f" LIMIT ${param_index}"
                    params.append(limit)

                rows = await conn.fetch(query, *params)

                result = []
                for row in rows:
                    user_mentions = row['mention_count'] or 0
                    percentage = (user_mentions / total_mentions *
                                  100) if total_mentions > 0 else 0

                    result.append({
                        'user_id': row['mentioner_user_id'],
                        'mention_count': user_mentions,
                        'last_mention': row['last_mention'].isoformat() if row['last_mention'] else None,
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch channel mentions leaderboard for target user",
                context={'guild_id': guild_id, 'channel_id': channel_id,
                         'target_user_id': target_user_id},
                original=e
            )

    async def q_leaderboard_mentions_target_user_category(
        self, guild_id: int, category_id: int, target_user_id: int,
        limit: int = 100,
        role_filter_ids: Optional[List[int]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get leaderboard of users who mention a target user (CATEGORY SCOPE).
        Shows top users that mentioned the target user in a specific category.
        """
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = '''
                    SELECT 
                        mentioner_user_id,
                        SUM(mention_count) as mention_count,
                        MAX(hour) as last_mention
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 
                    AND category_id = $2
                    AND mentioned_user_id = $3
                '''
                params = [guild_id, category_id, target_user_id]
                param_index = 4

                if start_time:
                    query += f" AND hour >= ${param_index}"
                    params.append(start_time)
                    param_index += 1
                if end_time:
                    query += f" AND hour <= ${param_index}"
                    params.append(end_time)
                    param_index += 1

                query, params = await self._apply_bot_filter(query, params, guild_id, 'user_mentions_hourly')
                param_index = len(params) + 1

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        query += f" AND mentioner_user_id = ANY(${param_index}::bigint[])"
                        params.append(user_ids)
                        param_index += 1
                    else:
                        return []

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'user_mentions_hourly',
                    include_users=True, include_channels=False,
                    specific_category_id=category_id
                )

                total_query = '''
                    SELECT COALESCE(SUM(mention_count), 0) as total_mentions
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 AND category_id = $2 AND mentioned_user_id = $3
                '''
                total_params = [guild_id, category_id, target_user_id]
                total_param_index = 4

                if start_time:
                    total_query += f" AND hour >= ${total_param_index}"
                    total_params.append(start_time)
                    total_param_index += 1
                if end_time:
                    total_query += f" AND hour <= ${total_param_index}"
                    total_params.append(end_time)
                    total_param_index += 1

                total_query, total_params = await self._apply_bot_filter(total_query, total_params, guild_id, 'user_mentions_hourly')

                if role_filter_ids and 'user_ids' in locals() and user_ids:
                    total_query += f" AND mentioner_user_id = ANY(${total_param_index}::bigint[])"
                    total_params.append(user_ids)

                total_row = await conn.fetchrow(total_query, *total_params)
                total_mentions = total_row['total_mentions'] if total_row else 0

                if total_mentions == 0:
                    return []

                query += '''
                    GROUP BY mentioner_user_id
                    HAVING SUM(mention_count) > 0
                    ORDER BY mention_count DESC
                '''

                if limit:
                    query += f" LIMIT ${param_index}"
                    params.append(limit)

                rows = await conn.fetch(query, *params)

                result = []
                for row in rows:
                    user_mentions = row['mention_count'] or 0
                    percentage = (user_mentions / total_mentions *
                                  100) if total_mentions > 0 else 0

                    result.append({
                        'user_id': row['mentioner_user_id'],
                        'mention_count': user_mentions,
                        'last_mention': row['last_mention'].isoformat() if row['last_mention'] else None,
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch category mentions leaderboard for target user",
                context={'guild_id': guild_id, 'category_id': category_id,
                         'target_user_id': target_user_id},
                original=e
            )

    # ======================================================================
    # MENTIONS SENT LEADERBOARD (Total mentions sent by users)
    # ======================================================================

    async def q_leaderboard_mentions_sent_server(
        self, guild_id: int,
        limit: int = 100,
        role_filter_ids: Optional[List[int]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get leaderboard of users who sent the most mentions (SERVER SCOPE).
        Shows top users by total mentions sent in the server.
        """
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = '''
                    SELECT 
                        mentioner_user_id,
                        SUM(mention_count) as mention_count,
                        COUNT(DISTINCT mentioned_user_id) as unique_targets,
                        MAX(hour) as last_mention
                    FROM user_mentions_hourly
                    WHERE guild_id = $1
                '''
                params = [guild_id]
                param_index = 2

                if start_time:
                    query += f" AND hour >= ${param_index}"
                    params.append(start_time)
                    param_index += 1
                if end_time:
                    query += f" AND hour <= ${param_index}"
                    params.append(end_time)
                    param_index += 1

                query, params = await self._apply_bot_filter(query, params, guild_id, 'user_mentions_hourly')
                param_index = len(params) + 1

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        query += f" AND mentioner_user_id = ANY(${param_index}::bigint[])"
                        params.append(user_ids)
                        param_index += 1
                    else:
                        return []

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'user_mentions_hourly',
                    include_users=True, include_channels=True
                )

                total_query = '''
                    SELECT COALESCE(SUM(mention_count), 0) as total_mentions
                    FROM user_mentions_hourly
                    WHERE guild_id = $1
                '''
                total_params = [guild_id]
                total_param_index = 2

                if start_time:
                    total_query += f" AND hour >= ${total_param_index}"
                    total_params.append(start_time)
                    total_param_index += 1
                if end_time:
                    total_query += f" AND hour <= ${total_param_index}"
                    total_params.append(end_time)
                    total_param_index += 1

                total_query, total_params = await self._apply_bot_filter(total_query, total_params, guild_id, 'user_mentions_hourly')

                if role_filter_ids and 'user_ids' in locals() and user_ids:
                    total_query += f" AND mentioner_user_id = ANY(${total_param_index}::bigint[])"
                    total_params.append(user_ids)

                total_row = await conn.fetchrow(total_query, *total_params)
                total_mentions = total_row['total_mentions'] if total_row else 0

                query += '''
                    GROUP BY mentioner_user_id
                    HAVING SUM(mention_count) > 0
                    ORDER BY mention_count DESC
                '''

                if limit:
                    query += f" LIMIT ${param_index}"
                    params.append(limit)

                rows = await conn.fetch(query, *params)

                result = []
                for row in rows:
                    user_mentions = row['mention_count'] or 0
                    percentage = (user_mentions / total_mentions *
                                  100) if total_mentions > 0 else 0

                    result.append({
                        'user_id': row['mentioner_user_id'],
                        'mention_count': user_mentions,
                        'unique_targets': row['unique_targets'] or 0,
                        'last_mention': row['last_mention'].isoformat() if row['last_mention'] else None,
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch server mentions sent leaderboard",
                context={'guild_id': guild_id},
                original=e
            )

    async def q_leaderboard_mentions_sent_channel(
        self, guild_id: int, channel_id: int,
        limit: int = 100,
        role_filter_ids: Optional[List[int]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get leaderboard of users who sent the most mentions (CHANNEL SCOPE).
        Shows top users by total mentions sent in a specific channel.
        """
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = '''
                    SELECT 
                        mentioner_user_id,
                        SUM(mention_count) as mention_count,
                        COUNT(DISTINCT mentioned_user_id) as unique_targets,
                        MAX(hour) as last_mention
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 
                    AND channel_id = $2
                '''
                params = [guild_id, channel_id]
                param_index = 3

                if start_time:
                    query += f" AND hour >= ${param_index}"
                    params.append(start_time)
                    param_index += 1
                if end_time:
                    query += f" AND hour <= ${param_index}"
                    params.append(end_time)
                    param_index += 1

                query, params = await self._apply_bot_filter(query, params, guild_id, 'user_mentions_hourly')
                param_index = len(params) + 1

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        query += f" AND mentioner_user_id = ANY(${param_index}::bigint[])"
                        params.append(user_ids)
                        param_index += 1
                    else:
                        return []

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'user_mentions_hourly',
                    include_users=True, include_channels=False,
                    specific_channel_id=channel_id
                )

                total_query = '''
                    SELECT COALESCE(SUM(mention_count), 0) as total_mentions
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 AND channel_id = $2
                '''
                total_params = [guild_id, channel_id]
                total_param_index = 3

                if start_time:
                    total_query += f" AND hour >= ${total_param_index}"
                    total_params.append(start_time)
                    total_param_index += 1
                if end_time:
                    total_query += f" AND hour <= ${total_param_index}"
                    total_params.append(end_time)
                    total_param_index += 1

                total_query, total_params = await self._apply_bot_filter(total_query, total_params, guild_id, 'user_mentions_hourly')

                if role_filter_ids and 'user_ids' in locals() and user_ids:
                    total_query += f" AND mentioner_user_id = ANY(${total_param_index}::bigint[])"
                    total_params.append(user_ids)

                total_row = await conn.fetchrow(total_query, *total_params)
                total_mentions = total_row['total_mentions'] if total_row else 0

                if total_mentions == 0:
                    return []

                query += '''
                    GROUP BY mentioner_user_id
                    HAVING SUM(mention_count) > 0
                    ORDER BY mention_count DESC
                '''

                if limit:
                    query += f" LIMIT ${param_index}"
                    params.append(limit)

                rows = await conn.fetch(query, *params)

                result = []
                for row in rows:
                    user_mentions = row['mention_count'] or 0
                    percentage = (user_mentions / total_mentions *
                                  100) if total_mentions > 0 else 0

                    result.append({
                        'user_id': row['mentioner_user_id'],
                        'mention_count': user_mentions,
                        'unique_targets': row['unique_targets'] or 0,
                        'last_mention': row['last_mention'].isoformat() if row['last_mention'] else None,
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch channel mentions sent leaderboard",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )

    async def q_leaderboard_mentions_sent_category(
        self, guild_id: int, category_id: int,
        limit: int = 100,
        role_filter_ids: Optional[List[int]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get leaderboard of users who sent the most mentions (CATEGORY SCOPE).
        Shows top users by total mentions sent in a specific category.
        """
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = '''
                    SELECT 
                        mentioner_user_id,
                        SUM(mention_count) as mention_count,
                        COUNT(DISTINCT mentioned_user_id) as unique_targets,
                        MAX(hour) as last_mention
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 
                    AND category_id = $2
                '''
                params = [guild_id, category_id]
                param_index = 3

                if start_time:
                    query += f" AND hour >= ${param_index}"
                    params.append(start_time)
                    param_index += 1
                if end_time:
                    query += f" AND hour <= ${param_index}"
                    params.append(end_time)
                    param_index += 1

                query, params = await self._apply_bot_filter(query, params, guild_id, 'user_mentions_hourly')
                param_index = len(params) + 1

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        query += f" AND mentioner_user_id = ANY(${param_index}::bigint[])"
                        params.append(user_ids)
                        param_index += 1
                    else:
                        return []

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'user_mentions_hourly',
                    include_users=True, include_channels=False,
                    specific_category_id=category_id
                )

                total_query = '''
                    SELECT COALESCE(SUM(mention_count), 0) as total_mentions
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 AND category_id = $2
                '''
                total_params = [guild_id, category_id]
                total_param_index = 3

                if start_time:
                    total_query += f" AND hour >= ${total_param_index}"
                    total_params.append(start_time)
                    total_param_index += 1
                if end_time:
                    total_query += f" AND hour <= ${total_param_index}"
                    total_params.append(end_time)
                    total_param_index += 1

                total_query, total_params = await self._apply_bot_filter(total_query, total_params, guild_id, 'user_mentions_hourly')

                if role_filter_ids and 'user_ids' in locals() and user_ids:
                    total_query += f" AND mentioner_user_id = ANY(${total_param_index}::bigint[])"
                    total_params.append(user_ids)

                total_row = await conn.fetchrow(total_query, *total_params)
                total_mentions = total_row['total_mentions'] if total_row else 0

                if total_mentions == 0:
                    return []

                query += '''
                    GROUP BY mentioner_user_id
                    HAVING SUM(mention_count) > 0
                    ORDER BY mention_count DESC
                '''

                if limit:
                    query += f" LIMIT ${param_index}"
                    params.append(limit)

                rows = await conn.fetch(query, *params)

                result = []
                for row in rows:
                    user_mentions = row['mention_count'] or 0
                    percentage = (user_mentions / total_mentions *
                                  100) if total_mentions > 0 else 0

                    result.append({
                        'user_id': row['mentioner_user_id'],
                        'mention_count': user_mentions,
                        'unique_targets': row['unique_targets'] or 0,
                        'last_mention': row['last_mention'].isoformat() if row['last_mention'] else None,
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch category mentions sent leaderboard",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )

    # ======================================================================
    # MENTIONS RECEIVED LEADERBOARD (Total mentions received by users)
    # ======================================================================

    async def q_leaderboard_mentions_received_server(
        self, guild_id: int,
        limit: int = 100,
        role_filter_ids: Optional[List[int]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get leaderboard of users who received the most mentions (SERVER SCOPE).
        Shows top users by total mentions received in the server.
        """
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = '''
                    SELECT 
                        mentioned_user_id,
                        SUM(mention_count) as mention_count,
                        COUNT(DISTINCT mentioner_user_id) as unique_senders,
                        MAX(hour) as last_mention
                    FROM user_mentions_hourly
                    WHERE guild_id = $1
                '''
                params = [guild_id]
                param_index = 2

                if start_time:
                    query += f" AND hour >= ${param_index}"
                    params.append(start_time)
                    param_index += 1
                if end_time:
                    query += f" AND hour <= ${param_index}"
                    params.append(end_time)
                    param_index += 1

                query, params = await self._apply_bot_filter(query, params, guild_id, 'user_mentions_hourly')
                param_index = len(params) + 1

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        query += f" AND mentioned_user_id = ANY(${param_index}::bigint[])"
                        params.append(user_ids)
                        param_index += 1
                    else:
                        return []

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'user_mentions_hourly',
                    include_users=True, include_channels=True
                )

                total_query = '''
                    SELECT COALESCE(SUM(mention_count), 0) as total_mentions
                    FROM user_mentions_hourly
                    WHERE guild_id = $1
                '''
                total_params = [guild_id]
                total_param_index = 2

                if start_time:
                    total_query += f" AND hour >= ${total_param_index}"
                    total_params.append(start_time)
                    total_param_index += 1
                if end_time:
                    total_query += f" AND hour <= ${total_param_index}"
                    total_params.append(end_time)
                    total_param_index += 1

                total_query, total_params = await self._apply_bot_filter(total_query, total_params, guild_id, 'user_mentions_hourly')

                if role_filter_ids and 'user_ids' in locals() and user_ids:
                    total_query += f" AND mentioned_user_id = ANY(${total_param_index}::bigint[])"
                    total_params.append(user_ids)

                total_row = await conn.fetchrow(total_query, *total_params)
                total_mentions = total_row['total_mentions'] if total_row else 0

                if total_mentions == 0:
                    return []

                query += '''
                    GROUP BY mentioned_user_id
                    HAVING SUM(mention_count) > 0
                    ORDER BY mention_count DESC
                '''

                if limit:
                    query += f" LIMIT ${param_index}"
                    params.append(limit)

                rows = await conn.fetch(query, *params)

                result = []
                for row in rows:
                    user_mentions = row['mention_count'] or 0
                    percentage = (user_mentions / total_mentions *
                                  100) if total_mentions > 0 else 0

                    result.append({
                        'user_id': row['mentioned_user_id'],
                        'mention_count': user_mentions,
                        'unique_senders': row['unique_senders'] or 0,
                        'last_mention': row['last_mention'].isoformat() if row['last_mention'] else None,
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch server mentions received leaderboard",
                context={'guild_id': guild_id},
                original=e
            )

    async def q_leaderboard_mentions_received_channel(
        self, guild_id: int, channel_id: int,
        limit: int = 100,
        role_filter_ids: Optional[List[int]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get leaderboard of users who received the most mentions (CHANNEL SCOPE).
        Shows top users by total mentions received in a specific channel.
        """
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = '''
                    SELECT 
                        mentioned_user_id,
                        SUM(mention_count) as mention_count,
                        COUNT(DISTINCT mentioner_user_id) as unique_senders,
                        MAX(hour) as last_mention
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 
                    AND channel_id = $2
                '''
                params = [guild_id, channel_id]
                param_index = 3

                if start_time:
                    query += f" AND hour >= ${param_index}"
                    params.append(start_time)
                    param_index += 1
                if end_time:
                    query += f" AND hour <= ${param_index}"
                    params.append(end_time)
                    param_index += 1

                query, params = await self._apply_bot_filter(query, params, guild_id, 'user_mentions_hourly')
                param_index = len(params) + 1

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        query += f" AND mentioned_user_id = ANY(${param_index}::bigint[])"
                        params.append(user_ids)
                        param_index += 1
                    else:
                        return []

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'user_mentions_hourly',
                    include_users=True, include_channels=False,
                    specific_channel_id=channel_id
                )

                total_query = '''
                    SELECT COALESCE(SUM(mention_count), 0) as total_mentions
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 AND channel_id = $2
                '''
                total_params = [guild_id, channel_id]
                total_param_index = 3

                if start_time:
                    total_query += f" AND hour >= ${total_param_index}"
                    total_params.append(start_time)
                    total_param_index += 1
                if end_time:
                    total_query += f" AND hour <= ${total_param_index}"
                    total_params.append(end_time)
                    total_param_index += 1

                total_query, total_params = await self._apply_bot_filter(total_query, total_params, guild_id, 'user_mentions_hourly')

                if role_filter_ids and 'user_ids' in locals() and user_ids:
                    total_query += f" AND mentioned_user_id = ANY(${total_param_index}::bigint[])"
                    total_params.append(user_ids)

                total_row = await conn.fetchrow(total_query, *total_params)
                total_mentions = total_row['total_mentions'] if total_row else 0

                if total_mentions == 0:
                    return []

                query += '''
                    GROUP BY mentioned_user_id
                    HAVING SUM(mention_count) > 0
                    ORDER BY mention_count DESC
                '''

                if limit:
                    query += f" LIMIT ${param_index}"
                    params.append(limit)

                rows = await conn.fetch(query, *params)

                result = []
                for row in rows:
                    user_mentions = row['mention_count'] or 0
                    percentage = (user_mentions / total_mentions *
                                  100) if total_mentions > 0 else 0

                    result.append({
                        'user_id': row['mentioned_user_id'],
                        'mention_count': user_mentions,
                        'unique_senders': row['unique_senders'] or 0,
                        'last_mention': row['last_mention'].isoformat() if row['last_mention'] else None,
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch channel mentions received leaderboard",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )

    async def q_leaderboard_mentions_received_category(
        self, guild_id: int, category_id: int,
        limit: int = 100,
        role_filter_ids: Optional[List[int]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get leaderboard of users who received the most mentions (CATEGORY SCOPE).
        Shows top users by total mentions received in a specific category.
        """
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = '''
                    SELECT 
                        mentioned_user_id,
                        SUM(mention_count) as mention_count,
                        COUNT(DISTINCT mentioner_user_id) as unique_senders,
                        MAX(hour) as last_mention
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 
                    AND category_id = $2
                '''
                params = [guild_id, category_id]
                param_index = 3

                if start_time:
                    query += f" AND hour >= ${param_index}"
                    params.append(start_time)
                    param_index += 1
                if end_time:
                    query += f" AND hour <= ${param_index}"
                    params.append(end_time)
                    param_index += 1

                query, params = await self._apply_bot_filter(query, params, guild_id, 'user_mentions_hourly')
                param_index = len(params) + 1

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        query += f" AND mentioned_user_id = ANY(${param_index}::bigint[])"
                        params.append(user_ids)
                        param_index += 1
                    else:
                        return []

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'user_mentions_hourly',
                    include_users=True, include_channels=False,
                    specific_category_id=category_id
                )

                total_query = '''
                    SELECT COALESCE(SUM(mention_count), 0) as total_mentions
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 AND category_id = $2
                '''
                total_params = [guild_id, category_id]
                total_param_index = 3

                if start_time:
                    total_query += f" AND hour >= ${total_param_index}"
                    total_params.append(start_time)
                    total_param_index += 1
                if end_time:
                    total_query += f" AND hour <= ${total_param_index}"
                    total_params.append(end_time)
                    total_param_index += 1

                total_query, total_params = await self._apply_bot_filter(total_query, total_params, guild_id, 'user_mentions_hourly')

                if role_filter_ids and 'user_ids' in locals() and user_ids:
                    total_query += f" AND mentioned_user_id = ANY(${total_param_index}::bigint[])"
                    total_params.append(user_ids)

                total_row = await conn.fetchrow(total_query, *total_params)
                total_mentions = total_row['total_mentions'] if total_row else 0

                if total_mentions == 0:
                    return []

                query += '''
                    GROUP BY mentioned_user_id
                    HAVING SUM(mention_count) > 0
                    ORDER BY mention_count DESC
                '''

                if limit:
                    query += f" LIMIT ${param_index}"
                    params.append(limit)

                rows = await conn.fetch(query, *params)

                result = []
                for row in rows:
                    user_mentions = row['mention_count'] or 0
                    percentage = (user_mentions / total_mentions *
                                  100) if total_mentions > 0 else 0

                    result.append({
                        'user_id': row['mentioned_user_id'],
                        'mention_count': user_mentions,
                        'unique_senders': row['unique_senders'] or 0,
                        'last_mention': row['last_mention'].isoformat() if row['last_mention'] else None,
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch category mentions received leaderboard",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )

    # ======================================================================
    # MENTIONS RATIO CALCULATOR (Received / Sent)
    # ======================================================================

    async def q_user_mentions_ratio_server(
        self, guild_id: int, user_id: int,
        role_filter_ids: Optional[List[int]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Calculate mentions ratio for a user (SERVER SCOPE).
        Returns mentions_sent, mentions_received, and ratio (received/sent).
        """
        if not self.pool:
            return {'mentions_sent': 0, 'mentions_received': 0, 'ratio': 0.0}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {'mentions_sent': 0, 'mentions_received': 0, 'ratio': 0.0}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                # Query for mentions sent
                sent_query = '''
                    SELECT COALESCE(SUM(mention_count), 0) as mentions_sent
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 AND mentioner_user_id = $2
                '''
                sent_params = [guild_id, user_id]
                sent_param_index = 3

                if start_time:
                    sent_query += f" AND hour >= ${sent_param_index}"
                    sent_params.append(start_time)
                    sent_param_index += 1
                if end_time:
                    sent_query += f" AND hour <= ${sent_param_index}"
                    sent_params.append(end_time)
                    sent_param_index += 1

                sent_query, sent_params = await self._apply_bot_filter(sent_query, sent_params, guild_id, 'user_mentions_hourly')

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids and user_id not in user_ids:
                        return {'mentions_sent': 0, 'mentions_received': 0, 'ratio': 0.0}

                sent_row = await conn.fetchrow(sent_query, *sent_params)
                mentions_sent = sent_row['mentions_sent'] if sent_row else 0

                # Query for mentions received
                received_query = '''
                    SELECT COALESCE(SUM(mention_count), 0) as mentions_received
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 AND mentioned_user_id = $2
                '''
                received_params = [guild_id, user_id]
                received_param_index = 3

                if start_time:
                    received_query += f" AND hour >= ${received_param_index}"
                    received_params.append(start_time)
                    received_param_index += 1
                if end_time:
                    received_query += f" AND hour <= ${received_param_index}"
                    received_params.append(end_time)
                    received_param_index += 1

                received_query, received_params = await self._apply_bot_filter(received_query, received_params, guild_id, 'user_mentions_hourly')

                received_row = await conn.fetchrow(received_query, *received_params)
                mentions_received = received_row['mentions_received'] if received_row else 0

                # Calculate ratio
                ratio = (mentions_received / mentions_sent) if mentions_sent > 0 else (
                    float('inf') if mentions_received > 0 else 0.0)

                return {
                    'mentions_sent': mentions_sent,
                    'mentions_received': mentions_received,
                    'ratio': ratio
                }

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to calculate user mentions ratio",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )

    async def q_user_mentions_ratio_channel(
        self, guild_id: int, channel_id: int, user_id: int,
        role_filter_ids: Optional[List[int]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Calculate mentions ratio for a user (CHANNEL SCOPE).
        Returns mentions_sent, mentions_received, and ratio (received/sent).
        """
        if not self.pool:
            return {'mentions_sent': 0, 'mentions_received': 0, 'ratio': 0.0}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {'mentions_sent': 0, 'mentions_received': 0, 'ratio': 0.0}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                sent_query = '''
                    SELECT COALESCE(SUM(mention_count), 0) as mentions_sent
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 AND channel_id = $2 AND mentioner_user_id = $3
                '''
                sent_params = [guild_id, channel_id, user_id]
                sent_param_index = 4

                if start_time:
                    sent_query += f" AND hour >= ${sent_param_index}"
                    sent_params.append(start_time)
                    sent_param_index += 1
                if end_time:
                    sent_query += f" AND hour <= ${sent_param_index}"
                    sent_params.append(end_time)
                    sent_param_index += 1

                sent_query, sent_params = await self._apply_bot_filter(sent_query, sent_params, guild_id, 'user_mentions_hourly')

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids and user_id not in user_ids:
                        return {'mentions_sent': 0, 'mentions_received': 0, 'ratio': 0.0}

                sent_row = await conn.fetchrow(sent_query, *sent_params)
                mentions_sent = sent_row['mentions_sent'] if sent_row else 0

                received_query = '''
                    SELECT COALESCE(SUM(mention_count), 0) as mentions_received
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 AND channel_id = $2 AND mentioned_user_id = $3
                '''
                received_params = [guild_id, channel_id, user_id]
                received_param_index = 4

                if start_time:
                    received_query += f" AND hour >= ${received_param_index}"
                    received_params.append(start_time)
                    received_param_index += 1
                if end_time:
                    received_query += f" AND hour <= ${received_param_index}"
                    received_params.append(end_time)
                    received_param_index += 1

                received_query, received_params = await self._apply_bot_filter(received_query, received_params, guild_id, 'user_mentions_hourly')

                received_row = await conn.fetchrow(received_query, *received_params)
                mentions_received = received_row['mentions_received'] if received_row else 0

                ratio = (mentions_received / mentions_sent) if mentions_sent > 0 else (
                    float('inf') if mentions_received > 0 else 0.0)

                return {
                    'mentions_sent': mentions_sent,
                    'mentions_received': mentions_received,
                    'ratio': ratio
                }

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to calculate channel user mentions ratio",
                context={'guild_id': guild_id,
                         'channel_id': channel_id, 'user_id': user_id},
                original=e
            )

    async def q_user_mentions_ratio_category(
        self, guild_id: int, category_id: int, user_id: int,
        role_filter_ids: Optional[List[int]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Calculate mentions ratio for a user (CATEGORY SCOPE).
        Returns mentions_sent, mentions_received, and ratio (received/sent).
        """
        if not self.pool:
            return {'mentions_sent': 0, 'mentions_received': 0, 'ratio': 0.0}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {'mentions_sent': 0, 'mentions_received': 0, 'ratio': 0.0}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                sent_query = '''
                    SELECT COALESCE(SUM(mention_count), 0) as mentions_sent
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 AND category_id = $2 AND mentioner_user_id = $3
                '''
                sent_params = [guild_id, category_id, user_id]
                sent_param_index = 4

                if start_time:
                    sent_query += f" AND hour >= ${sent_param_index}"
                    sent_params.append(start_time)
                    sent_param_index += 1
                if end_time:
                    sent_query += f" AND hour <= ${sent_param_index}"
                    sent_params.append(end_time)
                    sent_param_index += 1

                sent_query, sent_params = await self._apply_bot_filter(sent_query, sent_params, guild_id, 'user_mentions_hourly')

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids and user_id not in user_ids:
                        return {'mentions_sent': 0, 'mentions_received': 0, 'ratio': 0.0}

                sent_row = await conn.fetchrow(sent_query, *sent_params)
                mentions_sent = sent_row['mentions_sent'] if sent_row else 0

                received_query = '''
                    SELECT COALESCE(SUM(mention_count), 0) as mentions_received
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 AND category_id = $2 AND mentioned_user_id = $3
                '''
                received_params = [guild_id, category_id, user_id]
                received_param_index = 4

                if start_time:
                    received_query += f" AND hour >= ${received_param_index}"
                    received_params.append(start_time)
                    received_param_index += 1
                if end_time:
                    received_query += f" AND hour <= ${received_param_index}"
                    received_params.append(end_time)
                    received_param_index += 1

                received_query, received_params = await self._apply_bot_filter(received_query, received_params, guild_id, 'user_mentions_hourly')

                received_row = await conn.fetchrow(received_query, *received_params)
                mentions_received = received_row['mentions_received'] if received_row else 0

                ratio = (mentions_received / mentions_sent) if mentions_sent > 0 else (
                    float('inf') if mentions_received > 0 else 0.0)

                return {
                    'mentions_sent': mentions_sent,
                    'mentions_received': mentions_received,
                    'ratio': ratio
                }

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to calculate category user mentions ratio",
                context={'guild_id': guild_id,
                         'category_id': category_id, 'user_id': user_id},
                original=e
            )

    # ======================================================================
    # MENTIONS RATIO LEADERBOARD
    # ======================================================================

    async def q_leaderboard_mentions_ratio_server(
        self, guild_id: int,
        limit: int = 100,
        min_mentions_sent: int = 1,
        role_filter_ids: Optional[List[int]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get leaderboard of users by mentions ratio (received/sent) - SERVER SCOPE.
        Users with zero mentions sent are included at the end (ratio = infinity).
        """
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                # Get all users with mention activity
                query = '''
                    SELECT 
                        COALESCE(sent.mentioner_user_id, recv.mentioned_user_id) as user_id,
                        COALESCE(sent.mentions_sent, 0) as mentions_sent,
                        COALESCE(recv.mentions_received, 0) as mentions_received
                    FROM (
                        SELECT mentioner_user_id, SUM(mention_count) as mentions_sent
                        FROM user_mentions_hourly
                        WHERE guild_id = $1
                    ''' + (f" AND hour >= ${2}" if start_time else "") + (f" AND hour <= ${3}" if end_time else "") + '''
                        GROUP BY mentioner_user_id
                    ) sent
                    FULL OUTER JOIN (
                        SELECT mentioned_user_id, SUM(mention_count) as mentions_received
                        FROM user_mentions_hourly
                        WHERE guild_id = $1
                    ''' + (f" AND hour >= ${4}" if start_time else "") + (f" AND hour <= ${5}" if end_time else "") + '''
                        GROUP BY mentioned_user_id
                    ) recv ON sent.mentioner_user_id = recv.mentioned_user_id
                    WHERE COALESCE(sent.mentions_sent, 0) >= $6 OR COALESCE(recv.mentions_received, 0) > 0
                '''

                params = [guild_id]
                param_index = 2

                if start_time:
                    params.append(start_time)
                    param_index += 1
                if end_time:
                    params.append(end_time)
                    param_index += 1
                if start_time and end_time:
                    params.append(start_time)
                    params.append(end_time)
                    param_index = 6
                elif start_time:
                    params.append(start_time)
                    param_index = 5
                elif end_time:
                    params.append(end_time)
                    param_index = 5
                else:
                    param_index = 4

                params.append(min_mentions_sent)

                rows = await conn.fetch(query, *params)

                # Calculate ratio for each user
                user_ratios = []
                for row in rows:
                    user_id = row['user_id']
                    mentions_sent = row['mentions_sent'] or 0
                    mentions_received = row['mentions_received'] or 0

                    # Skip users below min_mentions_sent
                    if mentions_sent < min_mentions_sent and mentions_sent > 0:
                        continue

                    if mentions_sent > 0:
                        ratio = mentions_received / mentions_sent
                        ratio_display = ratio
                    elif mentions_received > 0:
                        ratio = float('inf')
                        ratio_display = "∞"
                    else:
                        ratio = 0.0
                        ratio_display = 0.0

                    user_ratios.append({
                        'user_id': user_id,
                        'mentions_sent': mentions_sent,
                        'mentions_received': mentions_received,
                        'ratio': ratio,
                        'ratio_display': ratio_display
                    })

                # Sort by ratio descending (users with infinity go to the top)
                user_ratios.sort(key=lambda x: x['ratio'] if x['ratio'] != float(
                    'inf') else float('inf'), reverse=True)

                return user_ratios[:limit]

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch server mentions ratio leaderboard",
                context={'guild_id': guild_id},
                original=e
            )

    async def q_leaderboard_mentions_ratio_channel(
        self, guild_id: int, channel_id: int,
        limit: int = 100,
        min_mentions_sent: int = 1,
        role_filter_ids: Optional[List[int]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get leaderboard of users by mentions ratio (received/sent) - CHANNEL SCOPE.
        Users with zero mentions sent are included at the end (ratio = infinity).
        """
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = '''
                    SELECT 
                        COALESCE(sent.mentioner_user_id, recv.mentioned_user_id) as user_id,
                        COALESCE(sent.mentions_sent, 0) as mentions_sent,
                        COALESCE(recv.mentions_received, 0) as mentions_received
                    FROM (
                        SELECT mentioner_user_id, SUM(mention_count) as mentions_sent
                        FROM user_mentions_hourly
                        WHERE guild_id = $1 AND channel_id = $2
                    ''' + (f" AND hour >= ${3}" if start_time else "") + (f" AND hour <= ${4}" if end_time else "") + '''
                        GROUP BY mentioner_user_id
                    ) sent
                    FULL OUTER JOIN (
                        SELECT mentioned_user_id, SUM(mention_count) as mentions_received
                        FROM user_mentions_hourly
                        WHERE guild_id = $1 AND channel_id = $2
                    ''' + (f" AND hour >= ${5}" if start_time else "") + (f" AND hour <= ${6}" if end_time else "") + '''
                        GROUP BY mentioned_user_id
                    ) recv ON sent.mentioner_user_id = recv.mentioned_user_id
                    WHERE COALESCE(sent.mentions_sent, 0) >= $7 OR COALESCE(recv.mentions_received, 0) > 0
                '''

                params = [guild_id, channel_id]
                param_index = 3

                if start_time:
                    params.append(start_time)
                    param_index += 1
                if end_time:
                    params.append(end_time)
                    param_index += 1
                if start_time and end_time:
                    params.append(start_time)
                    params.append(end_time)
                    param_index = 7
                elif start_time:
                    params.append(start_time)
                    param_index = 6
                elif end_time:
                    params.append(end_time)
                    param_index = 6
                else:
                    param_index = 5

                params.append(min_mentions_sent)

                rows = await conn.fetch(query, *params)

                user_ratios = []
                for row in rows:
                    user_id = row['user_id']
                    mentions_sent = row['mentions_sent'] or 0
                    mentions_received = row['mentions_received'] or 0

                    if mentions_sent < min_mentions_sent and mentions_sent > 0:
                        continue

                    if mentions_sent > 0:
                        ratio = mentions_received / mentions_sent
                        ratio_display = ratio
                    elif mentions_received > 0:
                        ratio = float('inf')
                        ratio_display = "∞"
                    else:
                        ratio = 0.0
                        ratio_display = 0.0

                    user_ratios.append({
                        'user_id': user_id,
                        'mentions_sent': mentions_sent,
                        'mentions_received': mentions_received,
                        'ratio': ratio,
                        'ratio_display': ratio_display
                    })

                user_ratios.sort(key=lambda x: x['ratio'] if x['ratio'] != float(
                    'inf') else float('inf'), reverse=True)

                return user_ratios[:limit]

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch channel mentions ratio leaderboard",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )

    async def q_leaderboard_mentions_ratio_category(
        self, guild_id: int, category_id: int,
        limit: int = 100,
        min_mentions_sent: int = 1,
        role_filter_ids: Optional[List[int]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get leaderboard of users by mentions ratio (received/sent) - CATEGORY SCOPE.
        Users with zero mentions sent are included at the end (ratio = infinity).
        """
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = '''
                    SELECT 
                        COALESCE(sent.mentioner_user_id, recv.mentioned_user_id) as user_id,
                        COALESCE(sent.mentions_sent, 0) as mentions_sent,
                        COALESCE(recv.mentions_received, 0) as mentions_received
                    FROM (
                        SELECT mentioner_user_id, SUM(mention_count) as mentions_sent
                        FROM user_mentions_hourly
                        WHERE guild_id = $1 AND category_id = $2
                    ''' + (f" AND hour >= ${3}" if start_time else "") + (f" AND hour <= ${4}" if end_time else "") + '''
                        GROUP BY mentioner_user_id
                    ) sent
                    FULL OUTER JOIN (
                        SELECT mentioned_user_id, SUM(mention_count) as mentions_received
                        FROM user_mentions_hourly
                        WHERE guild_id = $1 AND category_id = $2
                    ''' + (f" AND hour >= ${5}" if start_time else "") + (f" AND hour <= ${6}" if end_time else "") + '''
                        GROUP BY mentioned_user_id
                    ) recv ON sent.mentioner_user_id = recv.mentioned_user_id
                    WHERE COALESCE(sent.mentions_sent, 0) >= $7 OR COALESCE(recv.mentions_received, 0) > 0
                '''

                params = [guild_id, category_id]
                param_index = 3

                if start_time:
                    params.append(start_time)
                    param_index += 1
                if end_time:
                    params.append(end_time)
                    param_index += 1
                if start_time and end_time:
                    params.append(start_time)
                    params.append(end_time)
                    param_index = 7
                elif start_time:
                    params.append(start_time)
                    param_index = 6
                elif end_time:
                    params.append(end_time)
                    param_index = 6
                else:
                    param_index = 5

                params.append(min_mentions_sent)

                rows = await conn.fetch(query, *params)

                user_ratios = []
                for row in rows:
                    user_id = row['user_id']
                    mentions_sent = row['mentions_sent'] or 0
                    mentions_received = row['mentions_received'] or 0

                    if mentions_sent < min_mentions_sent and mentions_sent > 0:
                        continue

                    if mentions_sent > 0:
                        ratio = mentions_received / mentions_sent
                        ratio_display = ratio
                    elif mentions_received > 0:
                        ratio = float('inf')
                        ratio_display = "∞"
                    else:
                        ratio = 0.0
                        ratio_display = 0.0

                    user_ratios.append({
                        'user_id': user_id,
                        'mentions_sent': mentions_sent,
                        'mentions_received': mentions_received,
                        'ratio': ratio,
                        'ratio_display': ratio_display
                    })

                user_ratios.sort(key=lambda x: x['ratio'] if x['ratio'] != float(
                    'inf') else float('inf'), reverse=True)

                return user_ratios[:limit]

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch category mentions ratio leaderboard",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )

    # ======================================================================
    # ENHANCED ORIGINAL MENTIONS LEADERBOARD (with user-to-user direction)
    # ======================================================================

    async def q_leaderboard_mentions_to_user_server(
        self, guild_id: int, source_user_id: int,
        limit: int = 100,
        role_filter_ids: Optional[List[int]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get leaderboard of users that the source user mentioned (SERVER SCOPE).
        Shows top targets that the source user mentioned.
        """
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = '''
                    SELECT 
                        mentioned_user_id,
                        SUM(mention_count) as mention_count,
                        MAX(hour) as last_mention
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 
                    AND mentioner_user_id = $2
                '''
                params = [guild_id, source_user_id]
                param_index = 3

                if start_time:
                    query += f" AND hour >= ${param_index}"
                    params.append(start_time)
                    param_index += 1
                if end_time:
                    query += f" AND hour <= ${param_index}"
                    params.append(end_time)
                    param_index += 1

                query, params = await self._apply_bot_filter(query, params, guild_id, 'user_mentions_hourly')
                param_index = len(params) + 1

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids and source_user_id not in user_ids:
                        return []
                    if user_ids:
                        query += f" AND mentioned_user_id = ANY(${param_index}::bigint[])"
                        params.append(user_ids)
                        param_index += 1

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'user_mentions_hourly',
                    include_users=True, include_channels=True
                )

                total_query = '''
                    SELECT COALESCE(SUM(mention_count), 0) as total_mentions
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 AND mentioner_user_id = $2
                '''
                total_params = [guild_id, source_user_id]
                total_param_index = 3

                if start_time:
                    total_query += f" AND hour >= ${total_param_index}"
                    total_params.append(start_time)
                    total_param_index += 1
                if end_time:
                    total_query += f" AND hour <= ${total_param_index}"
                    total_params.append(end_time)
                    total_param_index += 1

                total_row = await conn.fetchrow(total_query, *total_params)
                total_mentions = total_row['total_mentions'] if total_row else 0

                if total_mentions == 0:
                    return []

                query += '''
                    GROUP BY mentioned_user_id
                    HAVING SUM(mention_count) > 0
                    ORDER BY mention_count DESC
                '''

                if limit:
                    query += f" LIMIT ${param_index}"
                    params.append(limit)

                rows = await conn.fetch(query, *params)

                result = []
                for row in rows:
                    user_mentions = row['mention_count'] or 0
                    percentage = (user_mentions / total_mentions *
                                  100) if total_mentions > 0 else 0

                    result.append({
                        'user_id': row['mentioned_user_id'],
                        'mention_count': user_mentions,
                        'last_mention': row['last_mention'].isoformat() if row['last_mention'] else None,
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch server mentions to user leaderboard",
                context={'guild_id': guild_id,
                         'source_user_id': source_user_id},
                original=e
            )

    async def q_leaderboard_mentions_to_user_channel(
        self, guild_id: int, channel_id: int, source_user_id: int,
        limit: int = 100,
        role_filter_ids: Optional[List[int]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get leaderboard of users that the source user mentioned (CHANNEL SCOPE).
        Shows top targets that the source user mentioned in a specific channel.
        """
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = '''
                    SELECT 
                        mentioned_user_id,
                        SUM(mention_count) as mention_count,
                        MAX(hour) as last_mention
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 
                    AND channel_id = $2
                    AND mentioner_user_id = $3
                '''
                params = [guild_id, channel_id, source_user_id]
                param_index = 4

                if start_time:
                    query += f" AND hour >= ${param_index}"
                    params.append(start_time)
                    param_index += 1
                if end_time:
                    query += f" AND hour <= ${param_index}"
                    params.append(end_time)
                    param_index += 1

                query, params = await self._apply_bot_filter(query, params, guild_id, 'user_mentions_hourly')
                param_index = len(params) + 1

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids and source_user_id not in user_ids:
                        return []
                    if user_ids:
                        query += f" AND mentioned_user_id = ANY(${param_index}::bigint[])"
                        params.append(user_ids)
                        param_index += 1

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'user_mentions_hourly',
                    include_users=True, include_channels=False,
                    specific_channel_id=channel_id
                )

                total_query = '''
                    SELECT COALESCE(SUM(mention_count), 0) as total_mentions
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 AND channel_id = $2 AND mentioner_user_id = $3
                '''
                total_params = [guild_id, channel_id, source_user_id]
                total_param_index = 4

                if start_time:
                    total_query += f" AND hour >= ${total_param_index}"
                    total_params.append(start_time)
                    total_param_index += 1
                if end_time:
                    total_query += f" AND hour <= ${total_param_index}"
                    total_params.append(end_time)
                    total_param_index += 1

                total_row = await conn.fetchrow(total_query, *total_params)
                total_mentions = total_row['total_mentions'] if total_row else 0

                if total_mentions == 0:
                    return []

                query += '''
                    GROUP BY mentioned_user_id
                    HAVING SUM(mention_count) > 0
                    ORDER BY mention_count DESC
                '''

                if limit:
                    query += f" LIMIT ${param_index}"
                    params.append(limit)

                rows = await conn.fetch(query, *params)

                result = []
                for row in rows:
                    user_mentions = row['mention_count'] or 0
                    percentage = (user_mentions / total_mentions *
                                  100) if total_mentions > 0 else 0

                    result.append({
                        'user_id': row['mentioned_user_id'],
                        'mention_count': user_mentions,
                        'last_mention': row['last_mention'].isoformat() if row['last_mention'] else None,
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch channel mentions to user leaderboard",
                context={'guild_id': guild_id, 'channel_id': channel_id,
                         'source_user_id': source_user_id},
                original=e
            )

    async def q_leaderboard_mentions_to_user_category(
        self, guild_id: int, category_id: int, source_user_id: int,
        limit: int = 100,
        role_filter_ids: Optional[List[int]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get leaderboard of users that the source user mentioned (CATEGORY SCOPE).
        Shows top targets that the source user mentioned in a specific category.
        """
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = '''
                    SELECT 
                        mentioned_user_id,
                        SUM(mention_count) as mention_count,
                        MAX(hour) as last_mention
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 
                    AND category_id = $2
                    AND mentioner_user_id = $3
                '''
                params = [guild_id, category_id, source_user_id]
                param_index = 4

                if start_time:
                    query += f" AND hour >= ${param_index}"
                    params.append(start_time)
                    param_index += 1
                if end_time:
                    query += f" AND hour <= ${param_index}"
                    params.append(end_time)
                    param_index += 1

                query, params = await self._apply_bot_filter(query, params, guild_id, 'user_mentions_hourly')
                param_index = len(params) + 1

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids and source_user_id not in user_ids:
                        return []
                    if user_ids:
                        query += f" AND mentioned_user_id = ANY(${param_index}::bigint[])"
                        params.append(user_ids)
                        param_index += 1

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'user_mentions_hourly',
                    include_users=True, include_channels=False,
                    specific_category_id=category_id
                )

                total_query = '''
                    SELECT COALESCE(SUM(mention_count), 0) as total_mentions
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 AND category_id = $2 AND mentioner_user_id = $3
                '''
                total_params = [guild_id, category_id, source_user_id]
                total_param_index = 4

                if start_time:
                    total_query += f" AND hour >= ${total_param_index}"
                    total_params.append(start_time)
                    total_param_index += 1
                if end_time:
                    total_query += f" AND hour <= ${total_param_index}"
                    total_params.append(end_time)
                    total_param_index += 1

                total_row = await conn.fetchrow(total_query, *total_params)
                total_mentions = total_row['total_mentions'] if total_row else 0

                if total_mentions == 0:
                    return []

                query += '''
                    GROUP BY mentioned_user_id
                    HAVING SUM(mention_count) > 0
                    ORDER BY mention_count DESC
                '''

                if limit:
                    query += f" LIMIT ${param_index}"
                    params.append(limit)

                rows = await conn.fetch(query, *params)

                result = []
                for row in rows:
                    user_mentions = row['mention_count'] or 0
                    percentage = (user_mentions / total_mentions *
                                  100) if total_mentions > 0 else 0

                    result.append({
                        'user_id': row['mentioned_user_id'],
                        'mention_count': user_mentions,
                        'last_mention': row['last_mention'].isoformat() if row['last_mention'] else None,
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch category mentions to user leaderboard",
                context={'guild_id': guild_id, 'category_id': category_id,
                         'source_user_id': source_user_id},
                original=e
            )
    # ======================================================================
    # LEADERBOARD CATEGORY - FIXED EXCEPTION HANDLING
    # ======================================================================

    async def q_leaderboard_category_users_messages(self, guild_id: int, category_id: int,
                                                    limit: int = 100000000000,
                                                    role_filter_ids: Optional[List[int]] = None,
                                                    start_time: Optional[datetime] = None,
                                                    end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get leaderboard of users in a category by messages using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                # Build base query
                query = '''
                    SELECT 
                        user_id,
                        COALESCE(SUM(message_count), 0) as message_count,
                        COALESCE(SUM(total_chars), 0) as total_chars,
                        COALESCE(SUM(total_chars) / NULLIF(SUM(message_count), 0), 0) as avg_chars
                    FROM message_tracking_hourly
                    WHERE guild_id = $1 
                    AND category_id = $2
                '''
                params = [guild_id, category_id]
                param_index = 3

                if start_time:
                    query += f" AND hour >= ${param_index}"
                    params.append(start_time)
                    param_index += 1
                if end_time:
                    query += f" AND hour <= ${param_index}"
                    params.append(end_time)
                    param_index += 1

                # Apply bot filter
                query, params = await self._apply_bot_filter(query, params, guild_id, 'message_tracking_hourly')
                param_index = len(params) + 1

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        # FIXED: Added ::bigint[] cast
                        query += f" AND user_id = ANY(${param_index}::bigint[])"
                        params.append(user_ids)
                        param_index += 1
                    else:
                        return []

                # Get total for percentage calculation
                total_query = '''
                    SELECT COALESCE(SUM(message_count), 0) as total_messages
                    FROM message_tracking_hourly
                    WHERE guild_id = $1 AND category_id = $2
                '''
                total_params = [guild_id, category_id]
                total_param_index = 3

                if start_time:
                    total_query += f" AND hour >= ${total_param_index}"
                    total_params.append(start_time)
                    total_param_index += 1
                if end_time:
                    total_query += f" AND hour <= ${total_param_index}"
                    total_params.append(end_time)
                    total_param_index += 1

                total_query, total_params = await self._apply_bot_filter(total_query, total_params, guild_id, 'message_tracking_hourly')

                if role_filter_ids and 'user_ids' in locals() and user_ids:
                    total_query += f" AND user_id = ANY(${total_param_index}::bigint[])"
                    total_params.append(user_ids)

                total_row = await conn.fetchrow(total_query, *total_params)
                total_messages = total_row['total_messages'] if total_row else 0

                if total_messages == 0:
                    return []

                # Complete the main query
                query += '''
                    GROUP BY user_id
                    HAVING SUM(message_count) > 0
                    ORDER BY message_count DESC
                '''

                if limit:
                    query += f" LIMIT ${param_index}"
                    params.append(limit)

                rows = await conn.fetch(query, *params)

                result = []
                for row in rows:
                    user_messages = row['message_count'] or 0
                    percentage = (user_messages / total_messages *
                                  100) if total_messages > 0 else 0

                    result.append({
                        'user_id': row['user_id'],
                        'message_count': user_messages,
                        'total_chars': row['total_chars'] or 0,
                        'avg_chars': round(row['avg_chars'] or 0, 2),
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching category user message leaderboard",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching category user message leaderboard",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching category user message leaderboard",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching category user message leaderboard",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching category user message leaderboard",
                    context={'guild_id': guild_id, 'category_id': category_id},
                    original=e
                )
            raise

    async def q_leaderboard_category_users_voice(self, guild_id: int, category_id: int,
                                                 limit: int = 100000000000,
                                                 role_filter_ids: Optional[List[int]] = None,
                                                 start_time: Optional[datetime] = None,
                                                 end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get leaderboard of users in a category by voice time using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)
            state_flags_filter = await self._get_voice_state_filter_value(guild_id)

            async with self.pool.acquire() as conn:
                # Build base query
                query = '''
                    SELECT 
                        user_id,
                        COALESCE(SUM(total_seconds), 0) as total_seconds,
                        COALESCE(SUM(session_count), 0) as session_count,
                        COALESCE(SUM(total_seconds) / NULLIF(SUM(session_count), 0), 0) as avg_session
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1 
                    AND category_id = $2
                '''
                params = [guild_id, category_id]
                param_index = 3

                # Apply voice state filter
                if state_flags_filter is not None:
                    query += f" AND state_flags = ${param_index}"
                    params.append(state_flags_filter)
                    param_index += 1

                if start_time:
                    query += f" AND hour >= ${param_index}"
                    params.append(start_time)
                    param_index += 1
                if end_time:
                    query += f" AND hour <= ${param_index}"
                    params.append(end_time)
                    param_index += 1

                # Apply bot filter
                query, params = await self._apply_bot_filter(query, params, guild_id, 'voice_session_history_hourly')
                param_index = len(params) + 1

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        # FIXED: Use ::bigint[] cast
                        query += f" AND user_id = ANY(${param_index}::bigint[])"
                        params.append(user_ids)
                        param_index += 1
                    else:
                        return []

                query += '''
                    GROUP BY user_id
                    HAVING SUM(total_seconds) > 0
                    ORDER BY total_seconds DESC
                '''

                if limit:
                    query += f" LIMIT ${param_index}"
                    params.append(limit)

                rows = await conn.fetch(query, *params)

                # Get total for percentage calculation
                total_query = '''
                    SELECT COALESCE(SUM(total_seconds), 0) as total_seconds
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1 AND category_id = $2
                '''
                total_params = [guild_id, category_id]
                total_param_index = 3

                if state_flags_filter is not None:
                    total_query += f" AND state_flags = ${total_param_index}"
                    total_params.append(state_flags_filter)
                    total_param_index += 1

                if start_time:
                    total_query += f" AND hour >= ${total_param_index}"
                    total_params.append(start_time)
                    total_param_index += 1
                if end_time:
                    total_query += f" AND hour <= ${total_param_index}"
                    total_params.append(end_time)
                    total_param_index += 1

                total_query, total_params = await self._apply_bot_filter(total_query, total_params, guild_id, 'voice_session_history_hourly')

                if role_filter_ids and 'user_ids' in locals() and user_ids:
                    total_query += f" AND user_id = ANY(${total_param_index}::bigint[])"
                    total_params.append(user_ids)

                total_row = await conn.fetchrow(total_query, *total_params)
                total_seconds = total_row['total_seconds'] if total_row else 0

                result = []
                for row in rows:
                    user_seconds = row['total_seconds'] or 0
                    percentage = (user_seconds / total_seconds *
                                  100) if total_seconds > 0 else 0

                    result.append({
                        'user_id': row['user_id'],
                        'total_seconds': user_seconds,
                        'total_hours': round(user_seconds / 3600, 2),
                        'session_count': row['session_count'] or 0,
                        'avg_session': round(row['avg_session'] or 0, 2),
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching category user voice leaderboard",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching category user voice leaderboard",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching category user voice leaderboard",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching category user voice leaderboard",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching category user voice leaderboard",
                    context={'guild_id': guild_id, 'category_id': category_id},
                    original=e
                )
            raise

    # ======================================================================
    # EMOJI LEADERBOARDS - FIXED EXCEPTION HANDLING
    # ======================================================================

    async def q_emoji_server_leaderboard(self, guild_id: int,
                                         limit: int = 100000000000,
                                         role_filter_ids: Optional[List[int]] = None,
                                         start_time: Optional[datetime] = None,
                                         end_time: Optional[datetime] = None,
                                         usage_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get server-wide emoji leaderboard using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                total_query = '''
                    SELECT COALESCE(SUM(usage_count), 0) as total_usage
                    FROM emoji_usage_hourly
                    WHERE guild_id = $1
                '''
                total_params = [guild_id]

                if usage_type:
                    total_query += f" AND usage_type = ${len(total_params) + 1}"
                    total_params.append(usage_type)

                if start_time:
                    total_query += f" AND hour >= ${len(total_params) + 1}"
                    total_params.append(start_time)
                if end_time:
                    total_query += f" AND hour <= ${len(total_params) + 1}"
                    total_params.append(end_time)

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        placeholders = [
                            f"${len(total_params) + i + 1}" for i in range(len(user_ids))]
                        total_query += f" AND user_id IN ({', '.join(placeholders)})"
                        total_params.extend(user_ids)
                    else:
                        return []

                total_query, total_params = await self._apply_bot_filter(total_query, total_params, guild_id, 'emoji_usage_hourly')

                total_query, total_params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, total_query, total_params, 'emoji_usage_hourly',
                    include_users=True, include_channels=True
                )

                total_row = await conn.fetchrow(total_query, *total_params)
                total_usage = total_row['total_usage'] or 0

                if total_usage == 0:
                    return []

                query = '''
                    SELECT 
                        emoji_str,
                        is_custom,
                        SUM(usage_count) as total_usage,
                        COUNT(DISTINCT user_id) as unique_users
                    FROM emoji_usage_hourly
                    WHERE guild_id = $1
                '''
                params = [guild_id]

                if usage_type:
                    query += f" AND usage_type = ${len(params) + 1}"
                    params.append(usage_type)

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        placeholders = [
                            f"${len(params) + i + 1}" for i in range(len(user_ids))]
                        query += f" AND user_id IN ({', '.join(placeholders)})"
                        params.extend(user_ids)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'emoji_usage_hourly')

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'emoji_usage_hourly',
                    include_users=True, include_channels=True
                )

                query += f'''
                    GROUP BY emoji_str, is_custom
                    HAVING SUM(usage_count) > 0
                    ORDER BY total_usage DESC
                    LIMIT {limit}
                '''

                rows = await conn.fetch(query, *params)

                result = []
                for row in rows:
                    emoji_usage = row['total_usage'] or 0
                    unique_users = row['unique_users'] or 0
                    percentage = (emoji_usage / total_usage *
                                  100) if total_usage > 0 else 0
                    avg_usage = emoji_usage / max(unique_users, 1)

                    result.append({
                        'emoji_str': row['emoji_str'],
                        'is_custom': row['is_custom'],
                        'usage_count': emoji_usage,
                        'unique_users': unique_users,
                        'avg_usage_per_user': round(avg_usage, 2),
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching server emoji leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching server emoji leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching server emoji leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching server emoji leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching server emoji leaderboard",
                    context={'guild_id': guild_id},
                    original=e
                )
            raise

    async def q_emoji_user_leaderboard(self, guild_id: int,
                                       limit: int = 100000000000,
                                       role_filter_ids: Optional[List[int]] = None,
                                       channel_id: Optional[int] = None,
                                       category_id: Optional[int] = None,
                                       start_time: Optional[datetime] = None,
                                       end_time: Optional[datetime] = None,
                                       usage_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get user emoji usage leaderboard using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        if channel_id and category_id:
            category_id = None

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                total_query = '''
                    SELECT COALESCE(SUM(usage_count), 0) as total_usage
                    FROM emoji_usage_hourly
                    WHERE guild_id = $1
                '''
                total_params = [guild_id]

                if channel_id:
                    total_query += f" AND channel_id = ${len(total_params) + 1}"
                    total_params.append(channel_id)
                elif category_id:
                    total_query += f" AND category_id = ${len(total_params) + 1}"
                    total_params.append(category_id)

                if usage_type:
                    total_query += f" AND usage_type = ${len(total_params) + 1}"
                    total_params.append(usage_type)

                if start_time:
                    total_query += f" AND hour >= ${len(total_params) + 1}"
                    total_params.append(start_time)
                if end_time:
                    total_query += f" AND hour <= ${len(total_params) + 1}"
                    total_params.append(end_time)

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        placeholders = [
                            f"${len(total_params) + i + 1}" for i in range(len(user_ids))]
                        total_query += f" AND user_id IN ({', '.join(placeholders)})"
                        total_params.extend(user_ids)
                    else:
                        return []

                include_channels_in_blacklist = not (channel_id or category_id)
                total_query, total_params = await self._apply_bot_filter(total_query, total_params, guild_id, 'emoji_usage_hourly')

                total_query, total_params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, total_query, total_params, 'emoji_usage_hourly',
                    include_users=True,
                    include_channels=include_channels_in_blacklist,
                    specific_channel_id=channel_id if channel_id else None,
                    specific_category_id=category_id if category_id else None
                )

                total_row = await conn.fetchrow(total_query, *total_params)
                total_usage = total_row['total_usage'] or 0

                if total_usage == 0:
                    return []

                query = '''
                    SELECT 
                        user_id,
                        SUM(usage_count) as total_usage,
                        COUNT(DISTINCT emoji_str) as unique_emojis
                    FROM emoji_usage_hourly
                    WHERE guild_id = $1
                '''
                params = [guild_id]

                if channel_id:
                    query += f" AND channel_id = ${len(params) + 1}"
                    params.append(channel_id)
                elif category_id:
                    query += f" AND category_id = ${len(params) + 1}"
                    params.append(category_id)

                if usage_type:
                    query += f" AND usage_type = ${len(params) + 1}"
                    params.append(usage_type)

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        placeholders = [
                            f"${len(params) + i + 1}" for i in range(len(user_ids))]
                        query += f" AND user_id IN ({', '.join(placeholders)})"
                        params.extend(user_ids)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'emoji_usage_hourly')

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'emoji_usage_hourly',
                    include_users=True,
                    include_channels=include_channels_in_blacklist,
                    specific_channel_id=channel_id if channel_id else None,
                    specific_category_id=category_id if category_id else None
                )

                query += f'''
                    GROUP BY user_id
                    HAVING SUM(usage_count) > 0
                    ORDER BY total_usage DESC
                    LIMIT {limit}
                '''

                rows = await conn.fetch(query, *params)

                result = []
                for row in rows:
                    user_usage = row['total_usage'] or 0
                    unique_emojis = row['unique_emojis'] or 0
                    percentage = (user_usage / total_usage *
                                  100) if total_usage > 0 else 0
                    avg_usage = user_usage / max(unique_emojis, 1)

                    result.append({
                        'user_id': row['user_id'],
                        'usage_count': user_usage,
                        'unique_emojis': unique_emojis,
                        'avg_usage_per_emoji': round(avg_usage, 2),
                        'percentage': round(percentage, 1)
                    })

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching user emoji leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching user emoji leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching user emoji leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching user emoji leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching user emoji leaderboard",
                    context={'guild_id': guild_id},
                    original=e
                )
            raise

    async def q_emoji_channel_leaderboard(self, guild_id: int, channel_id: int,
                                          limit: int = 100000000000,
                                          role_filter_ids: Optional[List[int]] = None,
                                          start_time: Optional[datetime] = None,
                                          end_time: Optional[datetime] = None,
                                          usage_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get channel emoji usage leaderboard using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = '''
                    SELECT 
                        emoji_str,
                        is_custom,
                        SUM(usage_count) as total_usage,
                        COUNT(DISTINCT user_id) as unique_users
                    FROM emoji_usage_hourly
                    WHERE guild_id = $1 
                    AND channel_id = $2
                '''
                params = [guild_id, channel_id]

                if usage_type:
                    query += f" AND usage_type = ${len(params) + 1}"
                    params.append(usage_type)

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                # 👇 ADD ROLE FILTERING
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        placeholders = [
                            f"${len(params) + i + 1}" for i in range(len(user_ids))]
                        query += f" AND user_id IN ({', '.join(placeholders)})"
                        params.extend(user_ids)
                    else:
                        return []

                query, params = await self._apply_bot_filter(query, params, guild_id, 'emoji_usage_hourly')

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'emoji_usage_hourly',
                    include_users=True, include_channels=False,
                    specific_channel_id=channel_id
                )

                query += f'''
                    GROUP BY emoji_str, is_custom
                    HAVING SUM(usage_count) > 0
                    ORDER BY total_usage DESC
                    LIMIT {limit}
                '''

                rows = await conn.fetch(query, *params)

                result = []
                for row in rows:
                    emoji_usage = row['total_usage'] or 0
                    unique_users = row['unique_users'] or 0
                    avg_usage = emoji_usage / max(unique_users, 1)

                    result.append({
                        'emoji_str': row['emoji_str'],
                        'is_custom': row['is_custom'],
                        'usage_count': emoji_usage,
                        'unique_users': unique_users,
                        'avg_usage_per_user': round(avg_usage, 2)
                    })

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching channel emoji leaderboard",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching channel emoji leaderboard",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching channel emoji leaderboard",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching channel emoji leaderboard",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching channel emoji leaderboard",
                    context={'guild_id': guild_id, 'channel_id': channel_id},
                    original=e
                )
            raise

    async def q_emoji_category_leaderboard(self, guild_id: int, category_id: int,
                                           limit: int = 100000000000,
                                           role_filter_ids: Optional[List[int]] = None,
                                           start_time: Optional[datetime] = None,
                                           end_time: Optional[datetime] = None,
                                           usage_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get category emoji usage leaderboard using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = '''
                    SELECT 
                        emoji_str,
                        is_custom,
                        SUM(usage_count) as total_usage,
                        COUNT(DISTINCT user_id) as unique_users
                    FROM emoji_usage_hourly
                    WHERE guild_id = $1 
                    AND category_id = $2
                '''
                params = [guild_id, category_id]

                if usage_type:
                    query += f" AND usage_type = ${len(params) + 1}"
                    params.append(usage_type)

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                # 👇 ADD ROLE FILTERING
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        placeholders = [
                            f"${len(params) + i + 1}" for i in range(len(user_ids))]
                        query += f" AND user_id IN ({', '.join(placeholders)})"
                        params.extend(user_ids)
                    else:
                        return []

                query, params = await self._apply_bot_filter(query, params, guild_id, 'emoji_usage_hourly')

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'emoji_usage_hourly',
                    include_users=True, include_channels=False
                )

                query += f'''
                    GROUP BY emoji_str, is_custom
                    HAVING SUM(usage_count) > 0
                    ORDER BY total_usage DESC
                    LIMIT {limit}
                '''

                rows = await conn.fetch(query, *params)

                result = []
                for row in rows:
                    emoji_usage = row['total_usage'] or 0
                    unique_users = row['unique_users'] or 0
                    avg_usage = emoji_usage / max(unique_users, 1)

                    result.append({
                        'emoji_str': row['emoji_str'],
                        'is_custom': row['is_custom'],
                        'usage_count': emoji_usage,
                        'unique_users': unique_users,
                        'avg_usage_per_user': round(avg_usage, 2)
                    })

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching category emoji leaderboard",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching category emoji leaderboard",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching category emoji leaderboard",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching category emoji leaderboard",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching category emoji leaderboard",
                    context={'guild_id': guild_id, 'category_id': category_id},
                    original=e
                )
            raise

    # ======================================================================
    # INVITE TRACKING - NO AGGREGATION (static tables)
    # ======================================================================

    async def q_user_invite_stats(self, guild_id: int, user_id: int,
                                  start_time: Optional[datetime] = None,
                                  end_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Get invite statistics for a user (uses raw table - static)."""
        if not self.pool:
            return {
                'total_invites': 0, 'valid_invites': 0, 'left_invites': 0,
                'suspicious_invites': 0, 'percentage_valid': 0.0
            }

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = '''
                    SELECT 
                        COUNT(*) as total_invites,
                        COUNT(*) FILTER (WHERE invite_type = 'valid') as valid_invites,
                        COUNT(*) FILTER (WHERE invite_type = 'left') as left_invites,
                        COUNT(*) FILTER (WHERE invite_type = 'suspicious') as suspicious_invites
                    FROM invite_tracking
                    WHERE guild_id = $1 
                    AND inviter_id = $2
                '''
                params = [guild_id, user_id]

                if start_time:
                    query += f" AND created_at >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND created_at <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'invite_tracking')

                try:
                    row = await conn.fetchrow(query, *params)
                except asyncpg.exceptions.PostgresError as e:
                    raise DatabaseQueryError(
                        "Failed to fetch user invite stats",
                        context={'guild_id': guild_id, 'user_id': user_id},
                        original=e
                    )

                total_invites = row['total_invites'] or 0
                valid_invites = row['valid_invites'] or 0
                percentage_valid = (
                    valid_invites / total_invites * 100) if total_invites > 0 else 0

                return {
                    'total_invites': total_invites,
                    'valid_invites': valid_invites,
                    'left_invites': row['left_invites'] or 0,
                    'suspicious_invites': row['suspicious_invites'] or 0,
                    'percentage_valid': round(percentage_valid, 1)
                }

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching user invite stats",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching user invite stats",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching user invite stats",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching user invite stats",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching user invite stats",
                    context={'guild_id': guild_id, 'user_id': user_id},
                    original=e
                )
            raise

    async def q_invite_leaderboard(self, guild_id: int,
                                   limit: int = 100000000000,
                                   role_filter_ids: Optional[List[int]] = None,
                                   start_time: Optional[datetime] = None,
                                   end_time: Optional[datetime] = None,
                                   invite_type_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get invite leaderboard for a server with optional invite type filtering.

        invite_type_filter can be: 'valid', 'suspicious', 'left', 'all', or None (defaults to 'all')
        """
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            # Default to 'all' if None or invalid
            if invite_type_filter not in ['valid', 'suspicious', 'left', 'all']:
                invite_type_filter = 'all'

            async with self.pool.acquire() as conn:
                filtered_inviter_ids = None
                if role_filter_ids:
                    filtered_inviter_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if not filtered_inviter_ids:
                        return []

                # Build the query with invite type filtering
                if invite_type_filter == 'all':
                    query = '''
                        SELECT 
                            inviter_id,
                            COUNT(*) as total_invites,
                            COUNT(*) FILTER (WHERE invite_type = 'valid') as valid_invites,
                            COUNT(*) FILTER (WHERE invite_type = 'suspicious') as suspicious_invites,
                            COUNT(*) FILTER (WHERE invite_type = 'left') as left_invites
                        FROM invite_tracking
                        WHERE guild_id = $1
                    '''
                else:
                    # Filter by specific invite type
                    query = f'''
                        SELECT 
                            inviter_id,
                            COUNT(*) as total_invites,
                            COUNT(*) FILTER (WHERE invite_type = 'valid') as valid_invites,
                            COUNT(*) FILTER (WHERE invite_type = 'suspicious') as suspicious_invites,
                            COUNT(*) FILTER (WHERE invite_type = 'left') as left_invites
                        FROM invite_tracking
                        WHERE guild_id = $1
                        AND invite_type = ${2}
                    '''

                params = [guild_id]

                if invite_type_filter != 'all':
                    params.append(invite_type_filter)

                if start_time:
                    query += f" AND created_at >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND created_at <= ${len(params) + 1}"
                    params.append(end_time)

                if filtered_inviter_ids:
                    placeholders = [
                        f"${len(params) + i + 1}" for i in range(len(filtered_inviter_ids))]
                    query += f" AND inviter_id IN ({', '.join(placeholders)})"
                    params.extend(filtered_inviter_ids)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'invite_tracking')

                # Apply blacklist filters - NOW WORKS with the special case for invite_tracking
                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'invite_tracking',
                    include_users=True, include_channels=False
                )

                # Determine which invite type to sort by based on filter
                if invite_type_filter == 'valid':
                    order_by = "valid_invites DESC"
                elif invite_type_filter == 'suspicious':
                    order_by = "suspicious_invites DESC"
                elif invite_type_filter == 'left':
                    order_by = "left_invites DESC"
                else:
                    order_by = "valid_invites DESC, total_invites DESC"

                query += f'''
                    GROUP BY inviter_id
                    HAVING COUNT(*) > 0
                    ORDER BY {order_by}
                    LIMIT {limit}
                '''

                print(f"Query: {query}")
                print(f"Params count: {len(params)}")
                print(f"Params: {params}")

                rows = await conn.fetch(query, *params)

                result = []
                for row in rows:
                    # For specific invite type filters, use that count as the primary display
                    if invite_type_filter == 'valid':
                        display_count = row['valid_invites'] or 0
                    elif invite_type_filter == 'suspicious':
                        display_count = row['suspicious_invites'] or 0
                    elif invite_type_filter == 'left':
                        display_count = row['left_invites'] or 0
                    else:
                        display_count = row['valid_invites'] or 0

                    total_invites = row['total_invites'] or 0
                    valid_invites = row['valid_invites'] or 0
                    percentage_valid = (
                        valid_invites / total_invites * 100) if total_invites > 0 else 0

                    result.append({
                        'user_id': row['inviter_id'],
                        'valid_invites': valid_invites,
                        'total_invites': total_invites,
                        'left_invites': row['left_invites'] or 0,
                        'suspicious_invites': row['suspicious_invites'] or 0,
                        'percentage_valid': round(percentage_valid, 1),
                        'display_invites': display_count,  # For display based on filter
                        'rank': len(result) + 1
                    })

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching invite leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching invite leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching invite leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching invite leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching invite leaderboard",
                    context={'guild_id': guild_id},
                    original=e
                )
            raise

    # ======================================================================
    # TIMEZONE ACTIVITY DISTRIBUTION - FIXED EXCEPTION HANDLING
    # ======================================================================

    async def q_server_activity_distribution(self, guild_id: int,
                                             days_back: int = 30,
                                             role_filter_ids: Optional[List[int]] = None,
                                             timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get server activity distribution by hour using aggregated tables."""
        if not self.pool:
            return {
                'messages': {f'hour_{i}': 0 for i in range(24)},
                'voice': {f'hour_{i}': 0 for i in range(24)},
                'activities': {f'hour_{i}': 0 for i in range(24)},
                'total_messages': 0,
                'total_voice_seconds': 0,
                'total_activities': 0
            }

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {
                'messages': {f'hour_{i}': 0 for i in range(24)},
                'voice': {f'hour_{i}': 0 for i in range(24)},
                'activities': {f'hour_{i}': 0 for i in range(24)},
                'total_messages': 0,
                'total_voice_seconds': 0,
                'total_activities': 0
            }

        try:
            async with self.pool.acquire() as conn:
                messages = {f'hour_{i}': 0 for i in range(24)}
                voice = {f'hour_{i}': 0 for i in range(24)}
                activities = {f'hour_{i}': 0 for i in range(24)}
                total_messages = 0
                total_voice_seconds = 0
                total_activities = 0

                # Messages query (hourly aggregated)
                query_messages = f'''
                    SELECT 
                        EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COALESCE(SUM(message_count), 0) as message_count
                    FROM message_tracking_hourly
                    WHERE guild_id = $1 
                    AND hour >= NOW() - INTERVAL '{days_back} days'
                    GROUP BY 1
                    ORDER BY 1
                '''
                params_messages = [guild_id]

                query_messages, params_messages = await self._apply_bot_filter(
                    query_messages, params_messages, guild_id, 'message_tracking_hourly'
                )

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        placeholders = [
                            f"${len(params_messages) + i + 1}" for i in range(len(user_ids))]
                        query_messages += f" AND user_id IN ({', '.join(placeholders)})"
                        params_messages.extend(user_ids)

                query_messages, params_messages = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query_messages, params_messages, 'message_tracking_hourly',
                    include_users=True, include_channels=True
                )

                if query_messages is not None:
                    try:
                        rows_messages = await conn.fetch(query_messages, *params_messages)

                        for row in rows_messages:
                            hour = int(row['hour_of_day'])
                            count = row['message_count'] or 0
                            messages[f'hour_{hour}'] = count
                            total_messages += count
                    except asyncpg.exceptions.PostgresError as e:
                        raise DatabaseQueryError(
                            "Failed to fetch server message activity distribution",
                            context={'guild_id': guild_id},
                            original=e
                        )

                # Voice query (hourly aggregated)
                query_voice = f'''
                    SELECT 
                        EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COALESCE(SUM(total_seconds), 0) as total_seconds
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1 
                    AND hour >= NOW() - INTERVAL '{days_back} days'
                    GROUP BY 1
                    ORDER BY 1
                '''
                params_voice = [guild_id]

                query_voice, params_voice = await self._apply_voice_state_filter(query_voice, params_voice, guild_id, 'state_flags')

                query_voice, params_voice = await self._apply_bot_filter(query_voice, params_voice, guild_id, 'voice_session_history_hourly')

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        placeholders = [
                            f"${len(params_voice) + i + 1}" for i in range(len(user_ids))]
                        query_voice += f" AND user_id IN ({', '.join(placeholders)})"
                        params_voice.extend(user_ids)

                query_voice, params_voice = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query_voice, params_voice, 'voice_session_history_hourly',
                    include_users=True, include_channels=True
                )

                if query_voice is not None:
                    try:
                        rows_voice = await conn.fetch(query_voice, *params_voice)
                        for row in rows_voice:
                            hour = int(row['hour_of_day'])
                            seconds = row['total_seconds'] or 0
                            voice[f'hour_{hour}'] = seconds
                            total_voice_seconds += seconds
                    except asyncpg.exceptions.PostgresError as e:
                        raise DatabaseQueryError(
                            "Failed to fetch server voice activity distribution",
                            context={'guild_id': guild_id},
                            original=e
                        )

                # Activities query (raw - static table)
                try:
                    query_activities = f'''
                        SELECT 
                            EXTRACT(HOUR FROM start_time AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                            COUNT(*) as activity_count
                        FROM activity_sessions
                        WHERE guild_id = $1 
                        AND start_time >= NOW() - INTERVAL '{days_back} days'
                        GROUP BY 1
                        ORDER BY 1
                    '''
                    params_activities = [guild_id]

                    rows_activities = await conn.fetch(query_activities, *params_activities)
                    for row in rows_activities:
                        hour = int(row['hour_of_day'])
                        count = row['activity_count'] or 0
                        activities[f'hour_{hour}'] = count
                        total_activities += count
                except asyncpg.exceptions.PostgresError:
                    # Activities table might not exist - ignore
                    pass

                return {
                    'messages': messages,
                    'voice': voice,
                    'activities': activities,
                    'total_messages': total_messages,
                    'total_voice_seconds': total_voice_seconds,
                    'total_activities': total_activities
                }

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching server activity distribution",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching server activity distribution",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching server activity distribution",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching server activity distribution",
                context={'guild_id': guild_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching server activity distribution",
                    context={'guild_id': guild_id},
                    original=e
                )
            raise

    async def q_user_activity_distribution(self, guild_id: int, user_id: int,
                                           days_back: int = 30,
                                           role_filter_ids: Optional[List[int]] = None,
                                           timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get user activity distribution by hour using aggregated tables."""
        if not self.pool:
            return {
                'messages': {f'hour_{i}': 0 for i in range(24)},
                'voice': {f'hour_{i}': 0 for i in range(24)},
                'activities': {f'hour_{i}': 0 for i in range(24)},
                'total_messages': 0,
                'total_voice_seconds': 0,
                'total_activities': 0
            }

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {
                'messages': {f'hour_{i}': 0 for i in range(24)},
                'voice': {f'hour_{i}': 0 for i in range(24)},
                'activities': {f'hour_{i}': 0 for i in range(24)},
                'total_messages': 0,
                'total_voice_seconds': 0,
                'total_activities': 0
            }

        try:
            async with self.pool.acquire() as conn:
                messages = {f'hour_{i}': 0 for i in range(24)}
                voice = {f'hour_{i}': 0 for i in range(24)}
                activities = {f'hour_{i}': 0 for i in range(24)}
                total_messages = 0
                total_voice_seconds = 0
                total_activities = 0

                # Messages query (hourly aggregated)
                query_messages = f'''
                    SELECT 
                        EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COALESCE(SUM(message_count), 0) as message_count
                    FROM message_tracking_hourly
                    WHERE guild_id = $1 
                    AND user_id = $2 
                    AND hour >= NOW() - INTERVAL '{days_back} days'
                    GROUP BY 1
                    ORDER BY 1
                '''
                params_messages = [guild_id, user_id]

                query_messages, params_messages = await self._apply_bot_filter(query_messages, params_messages, guild_id, 'message_tracking_hourly')

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids and user_id not in user_ids:
                        return {
                            'messages': {f'hour_{i}': 0 for i in range(24)},
                            'voice': {f'hour_{i}': 0 for i in range(24)},
                            'activities': {f'hour_{i}': 0 for i in range(24)},
                            'total_messages': 0,
                            'total_voice_seconds': 0,
                            'total_activities': 0
                        }

                query_messages, params_messages = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query_messages, params_messages, 'message_tracking_hourly',
                    include_users=True, include_channels=True
                )

                try:
                    rows_messages = await conn.fetch(query_messages, *params_messages)
                    for row in rows_messages:
                        hour = int(row['hour_of_day'])
                        count = row['message_count'] or 0
                        messages[f'hour_{hour}'] = count
                        total_messages += count
                except asyncpg.exceptions.PostgresError as e:
                    raise DatabaseQueryError(
                        "Failed to fetch user message activity distribution",
                        context={'guild_id': guild_id, 'user_id': user_id},
                        original=e
                    )

                # Voice query (hourly aggregated)
                query_voice = f'''
                    SELECT 
                        EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COALESCE(SUM(total_seconds), 0) as total_seconds
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1 
                    AND user_id = $2 
                    AND hour >= NOW() - INTERVAL '{days_back} days'
                    GROUP BY 1
                    ORDER BY 1
                '''
                params_voice = [guild_id, user_id]

                query_voice, params_voice = await self._apply_voice_state_filter(query_voice, params_voice, guild_id, 'state_flags')

                query_voice, params_voice = await self._apply_bot_filter(query_voice, params_voice, guild_id, 'voice_session_history_hourly')

                query_voice, params_voice = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query_voice, params_voice, 'voice_session_history_hourly',
                    include_users=True, include_channels=True
                )

                try:
                    rows_voice = await conn.fetch(query_voice, *params_voice)
                    for row in rows_voice:
                        hour = int(row['hour_of_day'])
                        seconds = row['total_seconds'] or 0
                        voice[f'hour_{hour}'] = seconds
                        total_voice_seconds += seconds
                except asyncpg.exceptions.PostgresError as e:
                    raise DatabaseQueryError(
                        "Failed to fetch user voice activity distribution",
                        context={'guild_id': guild_id, 'user_id': user_id},
                        original=e
                    )

                # Activities query (raw - static table)
                try:
                    query_activities = f'''
                        SELECT 
                            EXTRACT(HOUR FROM start_time AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                            COUNT(*) as activity_count
                        FROM activity_sessions
                        WHERE guild_id = $1 
                        AND user_id = $2 
                        AND start_time >= NOW() - INTERVAL '{days_back} days'
                        GROUP BY 1
                        ORDER BY 1
                    '''
                    params_activities = [guild_id, user_id]

                    rows_activities = await conn.fetch(query_activities, *params_activities)
                    for row in rows_activities:
                        hour = int(row['hour_of_day'])
                        count = row['activity_count'] or 0
                        activities[f'hour_{hour}'] = count
                        total_activities += count
                except asyncpg.exceptions.PostgresError:
                    # Activities table might not exist - ignore
                    pass

                return {
                    'messages': messages,
                    'voice': voice,
                    'activities': activities,
                    'total_messages': total_messages,
                    'total_voice_seconds': total_voice_seconds,
                    'total_activities': total_activities
                }

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching user activity distribution",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching user activity distribution",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching user activity distribution",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching user activity distribution",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching user activity distribution",
                    context={'guild_id': guild_id, 'user_id': user_id},
                    original=e
                )
            raise

    async def q_channel_activity_distribution(self, guild_id: int, channel_id: int,
                                              days_back: int = 30,
                                              role_filter_ids: Optional[List[int]] = None,
                                              timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get channel activity distribution by hour using aggregated tables."""
        if not self.pool:
            return {
                'messages': {f'hour_{i}': 0 for i in range(24)},
                'voice': {f'hour_{i}': 0 for i in range(24)},
                'total_messages': 0,
                'total_voice_seconds': 0
            }

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {
                'messages': {f'hour_{i}': 0 for i in range(24)},
                'voice': {f'hour_{i}': 0 for i in range(24)},
                'total_messages': 0,
                'total_voice_seconds': 0
            }

        try:
            async with self.pool.acquire() as conn:
                messages = {f'hour_{i}': 0 for i in range(24)}
                voice = {f'hour_{i}': 0 for i in range(24)}
                total_messages = 0
                total_voice_seconds = 0

                channel = guild.get_channel(channel_id)
                if not channel:
                    return {
                        'messages': {f'hour_{i}': 0 for i in range(24)},
                        'voice': {f'hour_{i}': 0 for i in range(24)},
                        'total_messages': 0,
                        'total_voice_seconds': 0
                    }

                if isinstance(channel, discord.TextChannel):
                    # Messages query (hourly aggregated)
                    query_messages = f'''
                        SELECT 
                            EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                            COALESCE(SUM(message_count), 0) as message_count
                        FROM message_tracking_hourly
                        WHERE guild_id = $1 
                        AND channel_id = $2 
                        AND hour >= NOW() - INTERVAL '{days_back} days'
                        GROUP BY 1
                        ORDER BY 1
                    '''
                    params_messages = [guild_id, channel_id]

                    query_messages, params_messages = await self._apply_bot_filter(
                        query_messages, params_messages, guild_id, 'message_tracking_hourly'
                    )

                    # Apply role filtering using current_role_members table
                    if role_filter_ids:
                        user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                        if user_ids:
                            placeholders = [
                                f"${len(params_messages) + i + 1}" for i in range(len(user_ids))]
                            query_messages += f" AND user_id IN ({', '.join(placeholders)})"
                            params_messages.extend(user_ids)

                    query_messages, params_messages = await self._apply_comprehensive_blacklist_filters(
                        guild_id, guild, query_messages, params_messages, 'message_tracking_hourly',
                        include_users=True, include_channels=False
                    )

                    try:
                        rows_messages = await conn.fetch(query_messages, *params_messages)
                        for row in rows_messages:
                            hour = int(row['hour_of_day'])
                            count = row['message_count'] or 0
                            messages[f'hour_{hour}'] = count
                            total_messages += count
                    except asyncpg.exceptions.PostgresError as e:
                        raise DatabaseQueryError(
                            "Failed to fetch channel message activity distribution",
                            context={'guild_id': guild_id,
                                     'channel_id': channel_id},
                            original=e
                        )

                elif isinstance(channel, discord.VoiceChannel):
                    # Voice query (hourly aggregated)
                    query_voice = f'''
                        SELECT 
                            EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                            COALESCE(SUM(total_seconds), 0) as total_seconds
                        FROM voice_session_history_hourly
                        WHERE guild_id = $1 
                        AND channel_id = $2 
                        AND hour >= NOW() - INTERVAL '{days_back} days'
                        GROUP BY 1
                        ORDER BY 1
                    '''
                    params_voice = [guild_id, channel_id]

                    query_voice, params_voice = await self._apply_voice_state_filter(
                        query_voice, params_voice, guild_id, 'state_flags'
                    )

                    query_voice, params_voice = await self._apply_bot_filter(
                        query_voice, params_voice, guild_id, 'voice_session_history_hourly'
                    )

                    # Apply role filtering using current_role_members table
                    if role_filter_ids:
                        user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                        if user_ids:
                            placeholders = [
                                f"${len(params_voice) + i + 1}" for i in range(len(user_ids))]
                            query_voice += f" AND user_id IN ({', '.join(placeholders)})"
                            params_voice.extend(user_ids)

                    query_voice, params_voice = await self._apply_comprehensive_blacklist_filters(
                        guild_id, guild, query_voice, params_voice, 'voice_session_history_hourly',
                        include_users=True, include_channels=False
                    )

                    try:
                        rows_voice = await conn.fetch(query_voice, *params_voice)
                        for row in rows_voice:
                            hour = int(row['hour_of_day'])
                            seconds = row['total_seconds'] or 0
                            voice[f'hour_{hour}'] = seconds
                            total_voice_seconds += seconds
                    except asyncpg.exceptions.PostgresError as e:
                        raise DatabaseQueryError(
                            "Failed to fetch channel voice activity distribution",
                            context={'guild_id': guild_id,
                                     'channel_id': channel_id},
                            original=e
                        )

                return {
                    'messages': messages,
                    'voice': voice,
                    'total_messages': total_messages,
                    'total_voice_seconds': total_voice_seconds
                }

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching channel activity distribution",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching channel activity distribution",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching channel activity distribution",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching channel activity distribution",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching channel activity distribution",
                    context={'guild_id': guild_id, 'channel_id': channel_id},
                    original=e
                )
            raise

    # ======================================================================
    # SERVER DISTRIBUTION QUERIES
    # ======================================================================

    async def q_server_distribution_messages(self, guild_id: int,
                                             role_filter_ids: Optional[List[int]] = None,
                                             start_time: Optional[datetime] = None,
                                             end_time: Optional[datetime] = None,
                                             timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get message distribution by hour for a server using hourly aggregated table."""
        if not self.pool:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = f'''
                    SELECT 
                        EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COALESCE(SUM(message_count), 0) as message_count
                    FROM message_tracking_hourly
                    WHERE guild_id = $1
                '''
                params = [guild_id]

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'message_tracking_hourly')

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        query += f" AND user_id = ANY(${len(params) + 1}::bigint[])"
                        params.append(user_ids)
                    else:
                        return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'message_tracking_hourly',
                    include_users=True, include_channels=True
                )

                if query is None:
                    return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                rows = await conn.fetch(query, *params)

                result = {f'hour_{i}': 0 for i in range(24)}
                total = 0
                peak_hour = -1
                peak_count = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    count = row['message_count'] or 0
                    result[f'hour_{hour}'] = count
                    total += count
                    if count > peak_count:
                        peak_count = count
                        peak_hour = hour

                result['total'] = total
                result['peak_hour'] = peak_hour
                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch server message distribution",
                context={'guild_id': guild_id},
                original=e
            )

    async def q_server_distribution_voice(self, guild_id: int,
                                          role_filter_ids: Optional[List[int]] = None,
                                          start_time: Optional[datetime] = None,
                                          end_time: Optional[datetime] = None,
                                          timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get voice distribution by hour for a server using hourly aggregated table."""
        if not self.pool:
            return {f'hour_{i}': 0 for i in range(24)} | {'total_seconds': 0, 'peak_hour': -1}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'hour_{i}': 0 for i in range(24)} | {'total_seconds': 0, 'peak_hour': -1}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)
            state_flags_filter = await self._get_voice_state_filter_value(guild_id)

            async with self.pool.acquire() as conn:
                query = f'''
                    SELECT 
                        EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COALESCE(SUM(total_seconds), 0) as total_seconds
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1
                '''
                params = [guild_id]

                if state_flags_filter is not None:
                    query += f" AND state_flags = ${len(params) + 1}"
                    params.append(state_flags_filter)

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_voice_state_filter(query, params, guild_id, 'state_flags')
                query, params = await self._apply_bot_filter(query, params, guild_id, 'voice_session_history_hourly')

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        query += f" AND user_id = ANY(${len(params) + 1}::bigint[])"
                        params.append(user_ids)
                    else:
                        return {f'hour_{i}': 0 for i in range(24)} | {'total_seconds': 0, 'peak_hour': -1}

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'voice_session_history_hourly',
                    include_users=True, include_channels=True
                )

                if query is None:
                    return {f'hour_{i}': 0 for i in range(24)} | {'total_seconds': 0, 'peak_hour': -1}

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                rows = await conn.fetch(query, *params)

                result = {f'hour_{i}': 0 for i in range(24)}
                total_seconds = 0
                peak_hour = -1
                peak_seconds = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    seconds = row['total_seconds'] or 0
                    result[f'hour_{hour}'] = seconds
                    total_seconds += seconds
                    if seconds > peak_seconds:
                        peak_seconds = seconds
                        peak_hour = hour

                result['total_seconds'] = total_seconds
                result['peak_hour'] = peak_hour
                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch server voice distribution",
                context={'guild_id': guild_id},
                original=e
            )

    async def q_server_distribution_activity(self, guild_id: int,
                                             role_filter_ids: Optional[List[int]] = None,
                                             start_time: Optional[datetime] = None,
                                             end_time: Optional[datetime] = None,
                                             timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get activity distribution by hour for a server using activity_sessions_hourly table."""
        if not self.pool:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = f'''
                    SELECT 
                        EXTRACT(HOUR FROM ash.hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COALESCE(SUM(ash.session_count), 0) as activity_count
                    FROM activity_sessions_hourly ash
                    WHERE ash.guild_id = $1
                '''
                params = [guild_id]

                if start_time:
                    query += f" AND ash.hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND ash.hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'activity_sessions_hourly')

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        query += f" AND ash.user_id = ANY(${len(params) + 1}::bigint[])"
                        params.append(user_ids)
                    else:
                        return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'activity_sessions_hourly',
                    include_users=True, include_channels=True
                )

                if query is None:
                    return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                rows = await conn.fetch(query, *params)

                result = {f'hour_{i}': 0 for i in range(24)}
                total = 0
                peak_hour = -1
                peak_count = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    count = row['activity_count'] or 0
                    result[f'hour_{hour}'] = count
                    total += count
                    if count > peak_count:
                        peak_count = count
                        peak_hour = hour

                result['total'] = total
                result['peak_hour'] = peak_hour
                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch server activity distribution",
                context={'guild_id': guild_id},
                original=e
            )

    async def q_server_distribution_joins(self, guild_id: int,
                                          start_time: Optional[datetime] = None,
                                          end_time: Optional[datetime] = None,
                                          timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get join distribution by hour for a server using hourly aggregated table."""
        if not self.pool:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = f'''
                    SELECT 
                        EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COALESCE(SUM(join_count), 0) as join_count
                    FROM member_joins_hourly
                    WHERE guild_id = $1
                '''
                params = [guild_id]

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'member_joins_hourly')

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'member_joins_hourly',
                    include_users=True, include_channels=True
                )

                if query is None:
                    return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                rows = await conn.fetch(query, *params)

                result = {f'hour_{i}': 0 for i in range(24)}
                total = 0
                peak_hour = -1
                peak_count = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    count = row['join_count'] or 0
                    result[f'hour_{hour}'] = count
                    total += count
                    if count > peak_count:
                        peak_count = count
                        peak_hour = hour

                result['total'] = total
                result['peak_hour'] = peak_hour
                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch server joins distribution",
                context={'guild_id': guild_id},
                original=e
            )

    async def q_server_distribution_leaves(self, guild_id: int,
                                           start_time: Optional[datetime] = None,
                                           end_time: Optional[datetime] = None,
                                           timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get leave distribution by hour for a server using hourly aggregated table."""
        if not self.pool:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = f'''
                    SELECT 
                        EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COALESCE(SUM(leave_count), 0) as leave_count
                    FROM member_leaves_hourly
                    WHERE guild_id = $1
                '''
                params = [guild_id]

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'member_leaves_hourly')

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'member_leaves_hourly',
                    include_users=True, include_channels=True
                )

                if query is None:
                    return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                rows = await conn.fetch(query, *params)

                result = {f'hour_{i}': 0 for i in range(24)}
                total = 0
                peak_hour = -1
                peak_count = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    count = row['leave_count'] or 0
                    result[f'hour_{hour}'] = count
                    total += count
                    if count > peak_count:
                        peak_count = count
                        peak_hour = hour

                result['total'] = total
                result['peak_hour'] = peak_hour
                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch server leaves distribution",
                context={'guild_id': guild_id},
                original=e
            )

    async def q_server_distribution_invites(self, guild_id: int,
                                            role_filter_ids: Optional[List[int]] = None,
                                            start_time: Optional[datetime] = None,
                                            end_time: Optional[datetime] = None,
                                            timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get invite distribution by hour for a server using invite_tracking table."""
        if not self.pool:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = f'''
                    SELECT 
                        EXTRACT(HOUR FROM created_at AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COUNT(*) as invite_count
                    FROM invite_tracking
                    WHERE guild_id = $1
                    AND invite_type IN ('valid', 'suspicious')
                '''
                params = [guild_id]

                if start_time:
                    query += f" AND created_at >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND created_at <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'invite_tracking')

                if role_filter_ids:
                    inviter_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if inviter_ids:
                        query += f" AND inviter_id = ANY(${len(params) + 1}::bigint[])"
                        params.append(inviter_ids)

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'invite_tracking',
                    include_users=True, include_channels=False
                )

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                rows = await conn.fetch(query, *params)

                result = {f'hour_{i}': 0 for i in range(24)}
                total = 0
                peak_hour = -1
                peak_count = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    count = row['invite_count'] or 0
                    result[f'hour_{hour}'] = count
                    total += count
                    if count > peak_count:
                        peak_count = count
                        peak_hour = hour

                result['total'] = total
                result['peak_hour'] = peak_hour
                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch server invites distribution",
                context={'guild_id': guild_id},
                original=e
            )

    async def q_server_distribution_mentions_sent(self, guild_id: int,
                                                  role_filter_ids: Optional[List[int]] = None,
                                                  start_time: Optional[datetime] = None,
                                                  end_time: Optional[datetime] = None,
                                                  timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get mentions sent distribution by hour for a server using hourly aggregated table."""
        if not self.pool:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = f'''
                    SELECT 
                        EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COALESCE(SUM(mention_count), 0) as mention_count
                    FROM user_mentions_hourly
                    WHERE guild_id = $1
                '''
                params = [guild_id]

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'user_mentions_hourly')

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        query += f" AND mentioner_user_id = ANY(${len(params) + 1}::bigint[])"
                        params.append(user_ids)
                    else:
                        return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'user_mentions_hourly',
                    include_users=True, include_channels=True
                )

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                rows = await conn.fetch(query, *params)

                result = {f'hour_{i}': 0 for i in range(24)}
                total = 0
                peak_hour = -1
                peak_count = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    count = row['mention_count'] or 0
                    result[f'hour_{hour}'] = count
                    total += count
                    if count > peak_count:
                        peak_count = count
                        peak_hour = hour

                result['total'] = total
                result['peak_hour'] = peak_hour
                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch server mentions sent distribution",
                context={'guild_id': guild_id},
                original=e
            )

    async def q_server_distribution_mentions_received(self, guild_id: int,
                                                      role_filter_ids: Optional[List[int]] = None,
                                                      start_time: Optional[datetime] = None,
                                                      end_time: Optional[datetime] = None,
                                                      timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get mentions received distribution by hour for a server using hourly aggregated table."""
        if not self.pool:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = f'''
                    SELECT 
                        EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COALESCE(SUM(mention_count), 0) as mention_count
                    FROM user_mentions_hourly
                    WHERE guild_id = $1
                '''
                params = [guild_id]

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'user_mentions_hourly')

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        query += f" AND mentioned_user_id = ANY(${len(params) + 1}::bigint[])"
                        params.append(user_ids)
                    else:
                        return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'user_mentions_hourly',
                    include_users=True, include_channels=True
                )

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                rows = await conn.fetch(query, *params)

                result = {f'hour_{i}': 0 for i in range(24)}
                total = 0
                peak_hour = -1
                peak_count = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    count = row['mention_count'] or 0
                    result[f'hour_{hour}'] = count
                    total += count
                    if count > peak_count:
                        peak_count = count
                        peak_hour = hour

                result['total'] = total
                result['peak_hour'] = peak_hour
                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch server mentions received distribution",
                context={'guild_id': guild_id},
                original=e
            )

    async def q_server_distribution_emoji_usage(self, guild_id: int,
                                                role_filter_ids: Optional[List[int]] = None,
                                                start_time: Optional[datetime] = None,
                                                end_time: Optional[datetime] = None,
                                                usage_type: Optional[str] = None,
                                                timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get emoji usage distribution by hour for a server using hourly aggregated table."""
        if not self.pool:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = f'''
                    SELECT 
                        EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COALESCE(SUM(usage_count), 0) as usage_count
                    FROM emoji_usage_hourly
                    WHERE guild_id = $1
                '''
                params = [guild_id]

                if usage_type:
                    query += f" AND usage_type = ${len(params) + 1}"
                    params.append(usage_type)

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'emoji_usage_hourly')

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        query += f" AND user_id = ANY(${len(params) + 1}::bigint[])"
                        params.append(user_ids)
                    else:
                        return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'emoji_usage_hourly',
                    include_users=True, include_channels=True
                )

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                rows = await conn.fetch(query, *params)

                result = {f'hour_{i}': 0 for i in range(24)}
                total = 0
                peak_hour = -1
                peak_count = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    count = row['usage_count'] or 0
                    result[f'hour_{hour}'] = count
                    total += count
                    if count > peak_count:
                        peak_count = count
                        peak_hour = hour

                result['total'] = total
                result['peak_hour'] = peak_hour
                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch server emoji usage distribution",
                context={'guild_id': guild_id},
                original=e
            )

    # ======================================================================
    # CHANNEL DISTRIBUTION QUERIES
    # ======================================================================

    async def q_channel_distribution_messages(self, guild_id: int, channel_id: int,
                                              role_filter_ids: Optional[List[int]] = None,
                                              start_time: Optional[datetime] = None,
                                              end_time: Optional[datetime] = None,
                                              timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get message distribution by hour for a channel using hourly aggregated table."""
        if not self.pool:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = f'''
                    SELECT 
                        EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COALESCE(SUM(message_count), 0) as message_count
                    FROM message_tracking_hourly
                    WHERE guild_id = $1 AND channel_id = $2
                '''
                params = [guild_id, channel_id]

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'message_tracking_hourly')

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        query += f" AND user_id = ANY(${len(params) + 1}::bigint[])"
                        params.append(user_ids)
                    else:
                        return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'message_tracking_hourly',
                    include_users=True, include_channels=False,
                    specific_channel_id=channel_id
                )

                if query is None:
                    return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                rows = await conn.fetch(query, *params)

                result = {f'hour_{i}': 0 for i in range(24)}
                total = 0
                peak_hour = -1
                peak_count = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    count = row['message_count'] or 0
                    result[f'hour_{hour}'] = count
                    total += count
                    if count > peak_count:
                        peak_count = count
                        peak_hour = hour

                result['total'] = total
                result['peak_hour'] = peak_hour
                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch channel message distribution",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )

    async def q_channel_distribution_voice(self, guild_id: int, channel_id: int,
                                           role_filter_ids: Optional[List[int]] = None,
                                           start_time: Optional[datetime] = None,
                                           end_time: Optional[datetime] = None,
                                           timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get voice distribution by hour for a channel using hourly aggregated table."""
        if not self.pool:
            return {f'hour_{i}': 0 for i in range(24)} | {'total_seconds': 0, 'peak_hour': -1}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'hour_{i}': 0 for i in range(24)} | {'total_seconds': 0, 'peak_hour': -1}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)
            state_flags_filter = await self._get_voice_state_filter_value(guild_id)

            async with self.pool.acquire() as conn:
                query = f'''
                    SELECT 
                        EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COALESCE(SUM(total_seconds), 0) as total_seconds
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1 AND channel_id = $2
                '''
                params = [guild_id, channel_id]

                if state_flags_filter is not None:
                    query += f" AND state_flags = ${len(params) + 1}"
                    params.append(state_flags_filter)

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_voice_state_filter(query, params, guild_id, 'state_flags')
                query, params = await self._apply_bot_filter(query, params, guild_id, 'voice_session_history_hourly')

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        query += f" AND user_id = ANY(${len(params) + 1}::bigint[])"
                        params.append(user_ids)
                    else:
                        return {f'hour_{i}': 0 for i in range(24)} | {'total_seconds': 0, 'peak_hour': -1}

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'voice_session_history_hourly',
                    include_users=True, include_channels=False,
                    specific_channel_id=channel_id
                )

                if query is None:
                    return {f'hour_{i}': 0 for i in range(24)} | {'total_seconds': 0, 'peak_hour': -1}

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                rows = await conn.fetch(query, *params)

                result = {f'hour_{i}': 0 for i in range(24)}
                total_seconds = 0
                peak_hour = -1
                peak_seconds = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    seconds = row['total_seconds'] or 0
                    result[f'hour_{hour}'] = seconds
                    total_seconds += seconds
                    if seconds > peak_seconds:
                        peak_seconds = seconds
                        peak_hour = hour

                result['total_seconds'] = total_seconds
                result['peak_hour'] = peak_hour
                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch channel voice distribution",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )

    async def q_channel_distribution_mentions_sent(self, guild_id: int, channel_id: int,
                                                   role_filter_ids: Optional[List[int]] = None,
                                                   start_time: Optional[datetime] = None,
                                                   end_time: Optional[datetime] = None,
                                                   timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get mentions sent distribution by hour for a channel using hourly aggregated table."""
        if not self.pool:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = f'''
                    SELECT 
                        EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COALESCE(SUM(mention_count), 0) as mention_count
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 AND channel_id = $2
                '''
                params = [guild_id, channel_id]

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'user_mentions_hourly')

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        query += f" AND mentioner_user_id = ANY(${len(params) + 1}::bigint[])"
                        params.append(user_ids)
                    else:
                        return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'user_mentions_hourly',
                    include_users=True, include_channels=False,
                    specific_channel_id=channel_id
                )

                if query is None:
                    return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                rows = await conn.fetch(query, *params)

                result = {f'hour_{i}': 0 for i in range(24)}
                total = 0
                peak_hour = -1
                peak_count = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    count = row['mention_count'] or 0
                    result[f'hour_{hour}'] = count
                    total += count
                    if count > peak_count:
                        peak_count = count
                        peak_hour = hour

                result['total'] = total
                result['peak_hour'] = peak_hour
                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch channel mentions sent distribution",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )

    async def q_channel_distribution_mentions_received(self, guild_id: int, channel_id: int,
                                                       role_filter_ids: Optional[List[int]] = None,
                                                       start_time: Optional[datetime] = None,
                                                       end_time: Optional[datetime] = None,
                                                       timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get mentions received distribution by hour for a channel using hourly aggregated table."""
        if not self.pool:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = f'''
                    SELECT 
                        EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COALESCE(SUM(mention_count), 0) as mention_count
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 AND channel_id = $2
                '''
                params = [guild_id, channel_id]

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'user_mentions_hourly')

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        query += f" AND mentioned_user_id = ANY(${len(params) + 1}::bigint[])"
                        params.append(user_ids)
                    else:
                        return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'user_mentions_hourly',
                    include_users=True, include_channels=False,
                    specific_channel_id=channel_id
                )

                if query is None:
                    return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                rows = await conn.fetch(query, *params)

                result = {f'hour_{i}': 0 for i in range(24)}
                total = 0
                peak_hour = -1
                peak_count = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    count = row['mention_count'] or 0
                    result[f'hour_{hour}'] = count
                    total += count
                    if count > peak_count:
                        peak_count = count
                        peak_hour = hour

                result['total'] = total
                result['peak_hour'] = peak_hour
                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch channel mentions received distribution",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )

    async def q_channel_distribution_emoji_usage(self, guild_id: int, channel_id: int,
                                                 role_filter_ids: Optional[List[int]] = None,
                                                 start_time: Optional[datetime] = None,
                                                 end_time: Optional[datetime] = None,
                                                 usage_type: Optional[str] = None,
                                                 timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get emoji usage distribution by hour for a channel using hourly aggregated table."""
        if not self.pool:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = f'''
                    SELECT 
                        EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COALESCE(SUM(usage_count), 0) as usage_count
                    FROM emoji_usage_hourly
                    WHERE guild_id = $1 AND channel_id = $2
                '''
                params = [guild_id, channel_id]

                if usage_type:
                    query += f" AND usage_type = ${len(params) + 1}"
                    params.append(usage_type)

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'emoji_usage_hourly')

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        query += f" AND user_id = ANY(${len(params) + 1}::bigint[])"
                        params.append(user_ids)
                    else:
                        return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'emoji_usage_hourly',
                    include_users=True, include_channels=False,
                    specific_channel_id=channel_id
                )

                if query is None:
                    return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                rows = await conn.fetch(query, *params)

                result = {f'hour_{i}': 0 for i in range(24)}
                total = 0
                peak_hour = -1
                peak_count = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    count = row['usage_count'] or 0
                    result[f'hour_{hour}'] = count
                    total += count
                    if count > peak_count:
                        peak_count = count
                        peak_hour = hour

                result['total'] = total
                result['peak_hour'] = peak_hour
                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch channel emoji usage distribution",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )

    # ======================================================================
    # CATEGORY DISTRIBUTION QUERIES
    # ======================================================================

    async def q_category_distribution_messages(self, guild_id: int, category_id: int,
                                               role_filter_ids: Optional[List[int]] = None,
                                               start_time: Optional[datetime] = None,
                                               end_time: Optional[datetime] = None,
                                               timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get message distribution by hour for a category using hourly aggregated table."""
        if not self.pool:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = f'''
                    SELECT 
                        EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COALESCE(SUM(message_count), 0) as message_count
                    FROM message_tracking_hourly
                    WHERE guild_id = $1 AND category_id = $2
                '''
                params = [guild_id, category_id]

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'message_tracking_hourly')

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        query += f" AND user_id = ANY(${len(params) + 1}::bigint[])"
                        params.append(user_ids)
                    else:
                        return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'message_tracking_hourly',
                    include_users=True, include_channels=False,
                    specific_category_id=category_id
                )

                if query is None:
                    return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                rows = await conn.fetch(query, *params)

                result = {f'hour_{i}': 0 for i in range(24)}
                total = 0
                peak_hour = -1
                peak_count = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    count = row['message_count'] or 0
                    result[f'hour_{hour}'] = count
                    total += count
                    if count > peak_count:
                        peak_count = count
                        peak_hour = hour

                result['total'] = total
                result['peak_hour'] = peak_hour
                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch category message distribution",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )

    async def q_category_distribution_voice(self, guild_id: int, category_id: int,
                                            role_filter_ids: Optional[List[int]] = None,
                                            start_time: Optional[datetime] = None,
                                            end_time: Optional[datetime] = None,
                                            timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get voice distribution by hour for a category using hourly aggregated table."""
        if not self.pool:
            return {f'hour_{i}': 0 for i in range(24)} | {'total_seconds': 0, 'peak_hour': -1}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'hour_{i}': 0 for i in range(24)} | {'total_seconds': 0, 'peak_hour': -1}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)
            state_flags_filter = await self._get_voice_state_filter_value(guild_id)

            async with self.pool.acquire() as conn:
                query = f'''
                    SELECT 
                        EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COALESCE(SUM(total_seconds), 0) as total_seconds
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1 AND category_id = $2
                '''
                params = [guild_id, category_id]

                if state_flags_filter is not None:
                    query += f" AND state_flags = ${len(params) + 1}"
                    params.append(state_flags_filter)

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_voice_state_filter(query, params, guild_id, 'state_flags')
                query, params = await self._apply_bot_filter(query, params, guild_id, 'voice_session_history_hourly')

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        query += f" AND user_id = ANY(${len(params) + 1}::bigint[])"
                        params.append(user_ids)
                    else:
                        return {f'hour_{i}': 0 for i in range(24)} | {'total_seconds': 0, 'peak_hour': -1}

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'voice_session_history_hourly',
                    include_users=True, include_channels=False,
                    specific_category_id=category_id
                )

                if query is None:
                    return {f'hour_{i}': 0 for i in range(24)} | {'total_seconds': 0, 'peak_hour': -1}

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                rows = await conn.fetch(query, *params)

                result = {f'hour_{i}': 0 for i in range(24)}
                total_seconds = 0
                peak_hour = -1
                peak_seconds = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    seconds = row['total_seconds'] or 0
                    result[f'hour_{hour}'] = seconds
                    total_seconds += seconds
                    if seconds > peak_seconds:
                        peak_seconds = seconds
                        peak_hour = hour

                result['total_seconds'] = total_seconds
                result['peak_hour'] = peak_hour
                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch category voice distribution",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )

    async def q_category_distribution_mentions_sent(self, guild_id: int, category_id: int,
                                                    role_filter_ids: Optional[List[int]] = None,
                                                    start_time: Optional[datetime] = None,
                                                    end_time: Optional[datetime] = None,
                                                    timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get mentions sent distribution by hour for a category using hourly aggregated table."""
        if not self.pool:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = f'''
                    SELECT 
                        EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COALESCE(SUM(mention_count), 0) as mention_count
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 AND category_id = $2
                '''
                params = [guild_id, category_id]

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'user_mentions_hourly')

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        query += f" AND mentioner_user_id = ANY(${len(params) + 1}::bigint[])"
                        params.append(user_ids)
                    else:
                        return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'user_mentions_hourly',
                    include_users=True, include_channels=False,
                    specific_category_id=category_id
                )

                if query is None:
                    return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                rows = await conn.fetch(query, *params)

                result = {f'hour_{i}': 0 for i in range(24)}
                total = 0
                peak_hour = -1
                peak_count = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    count = row['mention_count'] or 0
                    result[f'hour_{hour}'] = count
                    total += count
                    if count > peak_count:
                        peak_count = count
                        peak_hour = hour

                result['total'] = total
                result['peak_hour'] = peak_hour
                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch category mentions sent distribution",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )

    async def q_category_distribution_mentions_received(self, guild_id: int, category_id: int,
                                                        role_filter_ids: Optional[List[int]] = None,
                                                        start_time: Optional[datetime] = None,
                                                        end_time: Optional[datetime] = None,
                                                        timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get mentions received distribution by hour for a category using hourly aggregated table."""
        if not self.pool:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = f'''
                    SELECT 
                        EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COALESCE(SUM(mention_count), 0) as mention_count
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 AND category_id = $2
                '''
                params = [guild_id, category_id]

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'user_mentions_hourly')

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        query += f" AND mentioned_user_id = ANY(${len(params) + 1}::bigint[])"
                        params.append(user_ids)
                    else:
                        return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'user_mentions_hourly',
                    include_users=True, include_channels=False,
                    specific_category_id=category_id
                )

                if query is None:
                    return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                rows = await conn.fetch(query, *params)

                result = {f'hour_{i}': 0 for i in range(24)}
                total = 0
                peak_hour = -1
                peak_count = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    count = row['mention_count'] or 0
                    result[f'hour_{hour}'] = count
                    total += count
                    if count > peak_count:
                        peak_count = count
                        peak_hour = hour

                result['total'] = total
                result['peak_hour'] = peak_hour
                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch category mentions received distribution",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )

    async def q_category_distribution_emoji_usage(self, guild_id: int, category_id: int,
                                                  role_filter_ids: Optional[List[int]] = None,
                                                  start_time: Optional[datetime] = None,
                                                  end_time: Optional[datetime] = None,
                                                  usage_type: Optional[str] = None,
                                                  timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get emoji usage distribution by hour for a category using hourly aggregated table."""
        if not self.pool:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = f'''
                    SELECT 
                        EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COALESCE(SUM(usage_count), 0) as usage_count
                    FROM emoji_usage_hourly
                    WHERE guild_id = $1 AND category_id = $2
                '''
                params = [guild_id, category_id]

                if usage_type:
                    query += f" AND usage_type = ${len(params) + 1}"
                    params.append(usage_type)

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'emoji_usage_hourly')

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids:
                        query += f" AND user_id = ANY(${len(params) + 1}::bigint[])"
                        params.append(user_ids)
                    else:
                        return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'emoji_usage_hourly',
                    include_users=True, include_channels=False,
                    specific_category_id=category_id
                )

                if query is None:
                    return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                rows = await conn.fetch(query, *params)

                result = {f'hour_{i}': 0 for i in range(24)}
                total = 0
                peak_hour = -1
                peak_count = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    count = row['usage_count'] or 0
                    result[f'hour_{hour}'] = count
                    total += count
                    if count > peak_count:
                        peak_count = count
                        peak_hour = hour

                result['total'] = total
                result['peak_hour'] = peak_hour
                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch category emoji usage distribution",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )

    # ======================================================================
    # USER DISTRIBUTION QUERIES
    # ======================================================================

    async def q_user_distribution_messages(self, guild_id: int, user_id: int,
                                           role_filter_ids: Optional[List[int]] = None,
                                           start_time: Optional[datetime] = None,
                                           end_time: Optional[datetime] = None,
                                           timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get message distribution by hour for a user using hourly aggregated table."""
        if not self.pool:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = f'''
                    SELECT 
                        EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COALESCE(SUM(message_count), 0) as message_count
                    FROM message_tracking_hourly
                    WHERE guild_id = $1 AND user_id = $2
                '''
                params = [guild_id, user_id]

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'message_tracking_hourly')

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids and user_id not in user_ids:
                        return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'message_tracking_hourly',
                    include_users=True, include_channels=True
                )

                if query is None:
                    return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                rows = await conn.fetch(query, *params)

                result = {f'hour_{i}': 0 for i in range(24)}
                total = 0
                peak_hour = -1
                peak_count = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    count = row['message_count'] or 0
                    result[f'hour_{hour}'] = count
                    total += count
                    if count > peak_count:
                        peak_count = count
                        peak_hour = hour

                result['total'] = total
                result['peak_hour'] = peak_hour
                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch user message distribution",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )

    async def q_user_distribution_voice(self, guild_id: int, user_id: int,
                                        role_filter_ids: Optional[List[int]] = None,
                                        start_time: Optional[datetime] = None,
                                        end_time: Optional[datetime] = None,
                                        timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get voice distribution by hour for a user using hourly aggregated table."""
        if not self.pool:
            return {f'hour_{i}': 0 for i in range(24)} | {'total_seconds': 0, 'peak_hour': -1}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'hour_{i}': 0 for i in range(24)} | {'total_seconds': 0, 'peak_hour': -1}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)
            state_flags_filter = await self._get_voice_state_filter_value(guild_id)

            async with self.pool.acquire() as conn:
                query = f'''
                    SELECT 
                        EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COALESCE(SUM(total_seconds), 0) as total_seconds
                    FROM voice_session_history_hourly
                    WHERE guild_id = $1 AND user_id = $2
                '''
                params = [guild_id, user_id]

                if state_flags_filter is not None:
                    query += f" AND state_flags = ${len(params) + 1}"
                    params.append(state_flags_filter)

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_voice_state_filter(query, params, guild_id, 'state_flags')
                query, params = await self._apply_bot_filter(query, params, guild_id, 'voice_session_history_hourly')

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids and user_id not in user_ids:
                        return {f'hour_{i}': 0 for i in range(24)} | {'total_seconds': 0, 'peak_hour': -1}

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'voice_session_history_hourly',
                    include_users=True, include_channels=True
                )

                if query is None:
                    return {f'hour_{i}': 0 for i in range(24)} | {'total_seconds': 0, 'peak_hour': -1}

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                rows = await conn.fetch(query, *params)

                result = {f'hour_{i}': 0 for i in range(24)}
                total_seconds = 0
                peak_hour = -1
                peak_seconds = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    seconds = row['total_seconds'] or 0
                    result[f'hour_{hour}'] = seconds
                    total_seconds += seconds
                    if seconds > peak_seconds:
                        peak_seconds = seconds
                        peak_hour = hour

                result['total_seconds'] = total_seconds
                result['peak_hour'] = peak_hour
                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch user voice distribution",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )

    async def q_user_distribution_activity(self, guild_id: int, user_id: int,
                                           role_filter_ids: Optional[List[int]] = None,
                                           start_time: Optional[datetime] = None,
                                           end_time: Optional[datetime] = None,
                                           timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get activity distribution by hour for a user using activity_sessions_hourly table."""
        if not self.pool:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = f'''
                    SELECT 
                        EXTRACT(HOUR FROM ash.hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COALESCE(SUM(ash.session_count), 0) as activity_count
                    FROM activity_sessions_hourly ash
                    WHERE ash.guild_id = $1 AND ash.user_id = $2
                '''
                params = [guild_id, user_id]

                if start_time:
                    query += f" AND ash.hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND ash.hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'activity_sessions_hourly')

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids and user_id not in user_ids:
                        return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'activity_sessions_hourly',
                    include_users=True, include_channels=True
                )

                if query is None:
                    return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                rows = await conn.fetch(query, *params)

                result = {f'hour_{i}': 0 for i in range(24)}
                total = 0
                peak_hour = -1
                peak_count = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    count = row['activity_count'] or 0
                    result[f'hour_{hour}'] = count
                    total += count
                    if count > peak_count:
                        peak_count = count
                        peak_hour = hour

                result['total'] = total
                result['peak_hour'] = peak_hour
                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch user activity distribution",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )

    async def q_user_distribution_mentions_sent(self, guild_id: int, user_id: int,
                                                role_filter_ids: Optional[List[int]] = None,
                                                start_time: Optional[datetime] = None,
                                                end_time: Optional[datetime] = None,
                                                timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get mentions sent distribution by hour for a user using hourly aggregated table."""
        if not self.pool:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = f'''
                    SELECT 
                        EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COALESCE(SUM(mention_count), 0) as mention_count
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 AND mentioner_user_id = $2
                '''
                params = [guild_id, user_id]

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'user_mentions_hourly')

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids and user_id not in user_ids:
                        return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'user_mentions_hourly',
                    include_users=True, include_channels=True
                )

                if query is None:
                    return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                rows = await conn.fetch(query, *params)

                result = {f'hour_{i}': 0 for i in range(24)}
                total = 0
                peak_hour = -1
                peak_count = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    count = row['mention_count'] or 0
                    result[f'hour_{hour}'] = count
                    total += count
                    if count > peak_count:
                        peak_count = count
                        peak_hour = hour

                result['total'] = total
                result['peak_hour'] = peak_hour
                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch user mentions sent distribution",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )

    async def q_user_distribution_mentions_received(self, guild_id: int, user_id: int,
                                                    role_filter_ids: Optional[List[int]] = None,
                                                    start_time: Optional[datetime] = None,
                                                    end_time: Optional[datetime] = None,
                                                    timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get mentions received distribution by hour for a user using hourly aggregated table."""
        if not self.pool:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = f'''
                    SELECT 
                        EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COALESCE(SUM(mention_count), 0) as mention_count
                    FROM user_mentions_hourly
                    WHERE guild_id = $1 AND mentioned_user_id = $2
                '''
                params = [guild_id, user_id]

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'user_mentions_hourly')

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids and user_id not in user_ids:
                        return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'user_mentions_hourly',
                    include_users=True, include_channels=True
                )

                if query is None:
                    return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                rows = await conn.fetch(query, *params)

                result = {f'hour_{i}': 0 for i in range(24)}
                total = 0
                peak_hour = -1
                peak_count = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    count = row['mention_count'] or 0
                    result[f'hour_{hour}'] = count
                    total += count
                    if count > peak_count:
                        peak_count = count
                        peak_hour = hour

                result['total'] = total
                result['peak_hour'] = peak_hour
                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch user mentions received distribution",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )

    async def q_user_distribution_emoji_usage(self, guild_id: int, user_id: int,
                                              role_filter_ids: Optional[List[int]] = None,
                                              start_time: Optional[datetime] = None,
                                              end_time: Optional[datetime] = None,
                                              usage_type: Optional[str] = None,
                                              timezone_str: str = 'UTC') -> Dict[str, Any]:
        """Get emoji usage distribution by hour for a user using hourly aggregated table."""
        if not self.pool:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = f'''
                    SELECT 
                        EXTRACT(HOUR FROM hour AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COALESCE(SUM(usage_count), 0) as usage_count
                    FROM emoji_usage_hourly
                    WHERE guild_id = $1 AND user_id = $2
                '''
                params = [guild_id, user_id]

                if usage_type:
                    query += f" AND usage_type = ${len(params) + 1}"
                    params.append(usage_type)

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'emoji_usage_hourly')

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids and user_id not in user_ids:
                        return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'emoji_usage_hourly',
                    include_users=True, include_channels=True
                )

                if query is None:
                    return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                rows = await conn.fetch(query, *params)

                result = {f'hour_{i}': 0 for i in range(24)}
                total = 0
                peak_hour = -1
                peak_count = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    count = row['usage_count'] or 0
                    result[f'hour_{hour}'] = count
                    total += count
                    if count > peak_count:
                        peak_count = count
                        peak_hour = hour

                result['total'] = total
                result['peak_hour'] = peak_hour
                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch user emoji usage distribution",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )

    # ======================================================================
    # USER INVITE DISTRIBUTION (Invites SENT by the user)
    # ======================================================================

    async def q_user_distribution_invites_sent(self, guild_id: int, user_id: int,
                                               role_filter_ids: Optional[List[int]] = None,
                                               start_time: Optional[datetime] = None,
                                               end_time: Optional[datetime] = None,
                                               timezone_str: str = 'UTC') -> Dict[str, Any]:
        """
        Get invite distribution by hour for a user (invites they SENT).
        Shows when the user's invites were used to bring people into the server.
        """
        if not self.pool:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = f'''
                    SELECT 
                        EXTRACT(HOUR FROM created_at AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COUNT(*) as invite_count
                    FROM invite_tracking
                    WHERE guild_id = $1 
                    AND inviter_id = $2
                    AND invite_type IN ('valid', 'suspicious')
                '''
                params = [guild_id, user_id]

                if start_time:
                    query += f" AND created_at >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND created_at <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'invite_tracking')

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids and user_id not in user_ids:
                        return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                # Invite tracking doesn't have channel/category columns, so skip those filters
                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'invite_tracking',
                    include_users=True, include_channels=False
                )

                if query is None:
                    return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                rows = await conn.fetch(query, *params)

                result = {f'hour_{i}': 0 for i in range(24)}
                total = 0
                peak_hour = -1
                peak_count = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    count = row['invite_count'] or 0
                    result[f'hour_{hour}'] = count
                    total += count
                    if count > peak_count:
                        peak_count = count
                        peak_hour = hour

                result['total'] = total
                result['peak_hour'] = peak_hour
                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch user invites sent distribution",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )

    # ======================================================================
    # USER INVITE RECEIVED DISTRIBUTION (User JOINED via invite)
    # ======================================================================

    async def q_user_distribution_invites_received(self, guild_id: int, user_id: int,
                                                   role_filter_ids: Optional[List[int]] = None,
                                                   start_time: Optional[datetime] = None,
                                                   end_time: Optional[datetime] = None,
                                                   timezone_str: str = 'UTC') -> Dict[str, Any]:
        """
        Get invite distribution by hour for a user (invites they RECEIVED - i.e., when they joined).
        Shows what time of day this user typically joins the server.
        """
        if not self.pool:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = f'''
                    SELECT 
                        EXTRACT(HOUR FROM created_at AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                        COUNT(*) as invite_count
                    FROM invite_tracking
                    WHERE guild_id = $1 
                    AND invitee_id = $2
                    AND invite_type IN ('valid', 'suspicious')
                '''
                params = [guild_id, user_id]

                if start_time:
                    query += f" AND created_at >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND created_at <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'invite_tracking')

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids and user_id not in user_ids:
                        return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'invite_tracking',
                    include_users=True, include_channels=False
                )

                if query is None:
                    return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                rows = await conn.fetch(query, *params)

                result = {f'hour_{i}': 0 for i in range(24)}
                total = 0
                peak_hour = -1
                peak_count = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    count = row['invite_count'] or 0
                    result[f'hour_{hour}'] = count
                    total += count
                    if count > peak_count:
                        peak_count = count
                        peak_hour = hour

                result['total'] = total
                result['peak_hour'] = peak_hour
                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch user invites received distribution",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )

    # ======================================================================
    # USER INVITE VALIDITY DISTRIBUTION (Valid vs Suspicious invites SENT)
    # ======================================================================

    async def q_user_distribution_invites_by_type(self, guild_id: int, user_id: int,
                                                  invite_type_filter: str = 'valid',
                                                  role_filter_ids: Optional[List[int]] = None,
                                                  start_time: Optional[datetime] = None,
                                                  end_time: Optional[datetime] = None,
                                                  timezone_str: str = 'UTC') -> Dict[str, Any]:
        """
        Get invite distribution by hour for a user filtered by invite type.
        invite_type_filter can be: 'valid', 'suspicious', 'left', or 'all'
        """
        if not self.pool:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                if invite_type_filter == 'all':
                    query = f'''
                        SELECT 
                            EXTRACT(HOUR FROM created_at AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                            COUNT(*) as invite_count
                        FROM invite_tracking
                        WHERE guild_id = $1 
                        AND inviter_id = $2
                        AND invite_type IN ('valid', 'suspicious')
                    '''
                    params = [guild_id, user_id]
                else:
                    query = f'''
                        SELECT 
                            EXTRACT(HOUR FROM created_at AT TIME ZONE 'UTC' AT TIME ZONE '{timezone_str}') as hour_of_day,
                            COUNT(*) as invite_count
                        FROM invite_tracking
                        WHERE guild_id = $1 
                        AND inviter_id = $2
                        AND invite_type = ${3}
                    '''
                    params = [guild_id, user_id, invite_type_filter]

                if start_time:
                    query += f" AND created_at >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND created_at <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'invite_tracking')

                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids and user_id not in user_ids:
                        return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'invite_tracking',
                    include_users=True, include_channels=False
                )

                if query is None:
                    return {f'hour_{i}': 0 for i in range(24)} | {'total': 0, 'peak_hour': -1}

                query += '''
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                '''

                rows = await conn.fetch(query, *params)

                result = {f'hour_{i}': 0 for i in range(24)}
                total = 0
                peak_hour = -1
                peak_count = 0

                for row in rows:
                    hour = int(row['hour_of_day'])
                    count = row['invite_count'] or 0
                    result[f'hour_{hour}'] = count
                    total += count
                    if count > peak_count:
                        peak_count = count
                        peak_hour = hour

                result['total'] = total
                result['peak_hour'] = peak_hour
                return result

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to fetch user invites by type distribution",
                context={'guild_id': guild_id, 'user_id': user_id,
                         'invite_type': invite_type_filter},
                original=e
            )
    # ======================================================================
    # SLASH COMMAND QUERIES - FIXED EXCEPTION HANDLING
    # ======================================================================

    async def q_top_slash_commands(self, guild_id: int,
                                   limit: int = 100000000000,
                                   role_filter_ids: Optional[List[int]] = None,
                                   start_time: Optional[datetime] = None,
                                   end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get top slash commands in a server using daily aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = '''
                    SELECT 
                        command_name,
                        SUM(command_count) as usage_count,
                        SUM(unique_users) as unique_users
                    FROM slash_commands_daily
                    WHERE guild_id = $1
                '''
                params = [guild_id]

                if start_time:
                    query += f" AND day >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND day <= ${len(params) + 1}"
                    params.append(end_time)

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    # We can't filter by user_id in daily aggregated table easily
                    # This is a limitation - we'll need to keep raw for user-level filtering
                    pass

                query, params = await self._apply_bot_filter(query, params, guild_id, 'slash_commands_daily')

                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'slash_commands_daily',
                    include_users=True, include_channels=True
                )

                query += f'''
                    GROUP BY command_name
                    HAVING SUM(command_count) > 0
                    ORDER BY usage_count DESC
                    LIMIT {limit}
                '''

                rows = await conn.fetch(query, *params)

                result = []
                for row in rows:
                    result.append({
                        'command_name': row['command_name'],
                        'usage_count': row['usage_count'] or 0,
                        'unique_users': row['unique_users'] or 0
                    })

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching top slash commands",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching top slash commands",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching top slash commands",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching top slash commands",
                context={'guild_id': guild_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching top slash commands",
                    context={'guild_id': guild_id},
                    original=e
                )
            raise

    # ======================================================================
    # CART SYSTEM
    # ======================================================================

    async def add_cart_item(
        self,
        user_id: int,
        item_type: str,
        item_id: str,
        billing_cycle: str,
        price_usd: float
    ) -> bool:
        """Add or update an item in user's cart."""
        if not self.pool:
            return False

        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO cart_items (user_id, item_type, item_id, billing_cycle, price_usd)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (user_id, item_id) DO UPDATE SET
                        billing_cycle = EXCLUDED.billing_cycle,
                        price_usd = EXCLUDED.price_usd,
                        added_at = NOW()
                """, user_id, item_type, item_id, billing_cycle, price_usd)
                return True
        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while adding cart item",
                context={'user_id': user_id, 'item_id': item_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while adding cart item",
                context={'user_id': user_id, 'item_id': item_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while adding cart item",
                context={'user_id': user_id, 'item_id': item_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error adding cart item",
                context={'user_id': user_id, 'item_id': item_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error adding cart item",
                    context={'user_id': user_id, 'item_id': item_id},
                    original=e
                )
            raise

    async def remove_cart_item(
        self,
        user_id: int,
        item_id: str
    ) -> bool:
        """Remove an item from user's cart."""
        if not self.pool:
            return False

        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute("""
                    DELETE FROM cart_items
                    WHERE user_id = $1 AND item_id = $2
                """, user_id, item_id)
                return 'DELETE 1' in result
        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while removing cart item",
                context={'user_id': user_id, 'item_id': item_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while removing cart item",
                context={'user_id': user_id, 'item_id': item_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while removing cart item",
                context={'user_id': user_id, 'item_id': item_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error removing cart item",
                context={'user_id': user_id, 'item_id': item_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error removing cart item",
                    context={'user_id': user_id, 'item_id': item_id},
                    original=e
                )
            raise

    async def assign_server_to_cart_item(
        self,
        user_id: int,
        item_id: str,
        guild_id: int
    ) -> bool:
        """Assign a server to a cart item."""
        if not self.pool:
            return False

        try:
            async with self.pool.acquire() as conn:
                # Look up the cart_item id
                row = await conn.fetchrow("""
                    SELECT id FROM cart_items
                    WHERE user_id = $1 AND item_id = $2
                """, user_id, item_id)

                if not row:
                    return False

                cart_item_id = row['id']

                # Upsert the server assignment
                await conn.execute("""
                    INSERT INTO cart_item_servers (cart_item_id, user_id, guild_id)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (cart_item_id, guild_id) DO NOTHING
                """, cart_item_id, user_id, guild_id)

                return True
        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while assigning server to cart item",
                context={'user_id': user_id,
                         'item_id': item_id, 'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while assigning server to cart item",
                context={'user_id': user_id,
                         'item_id': item_id, 'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while assigning server to cart item",
                context={'user_id': user_id,
                         'item_id': item_id, 'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error assigning server to cart item",
                context={'user_id': user_id,
                         'item_id': item_id, 'guild_id': guild_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error assigning server to cart item",
                    context={'user_id': user_id,
                             'item_id': item_id, 'guild_id': guild_id},
                    original=e
                )
            raise

    async def unassign_server_from_cart_item(
        self,
        user_id: int,
        item_id: str,
        guild_id: int
    ) -> bool:
        """Remove a server assignment from a cart item."""
        if not self.pool:
            return False

        try:
            async with self.pool.acquire() as conn:
                # Look up the cart_item id
                row = await conn.fetchrow("""
                    SELECT id FROM cart_items
                    WHERE user_id = $1 AND item_id = $2
                """, user_id, item_id)

                if not row:
                    return False

                cart_item_id = row['id']

                # Delete the server assignment
                result = await conn.execute("""
                    DELETE FROM cart_item_servers
                    WHERE cart_item_id = $1 AND guild_id = $2
                """, cart_item_id, guild_id)

                return 'DELETE 1' in result
        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while unassigning server from cart item",
                context={'user_id': user_id,
                         'item_id': item_id, 'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while unassigning server from cart item",
                context={'user_id': user_id,
                         'item_id': item_id, 'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while unassigning server from cart item",
                context={'user_id': user_id,
                         'item_id': item_id, 'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error unassigning server from cart item",
                context={'user_id': user_id,
                         'item_id': item_id, 'guild_id': guild_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error unassigning server from cart item",
                    context={'user_id': user_id,
                             'item_id': item_id, 'guild_id': guild_id},
                    original=e
                )
            raise

    async def get_cart(
        self,
        user_id: int
    ) -> List[Dict[str, Any]]:
        """Get full cart for a user with all server assignments."""
        if not self.pool:
            return []

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT 
                        ci.id,
                        ci.user_id,
                        ci.item_type,
                        ci.item_id,
                        ci.billing_cycle,
                        ci.price_usd,
                        ci.added_at,
                        COALESCE(
                            json_agg(
                                json_build_object('guild_id', cis.guild_id, 'assigned_at', cis.assigned_at)
                            ) FILTER (WHERE cis.guild_id IS NOT NULL),
                            '[]'
                        ) AS assigned_servers
                    FROM cart_items ci
                    LEFT JOIN cart_item_servers cis ON cis.cart_item_id = ci.id
                    WHERE ci.user_id = $1
                    GROUP BY ci.id
                    ORDER BY ci.added_at ASC
                """, user_id)

                result = []
                for row in rows:
                    result.append({
                        'id': row['id'],
                        'user_id': row['user_id'],
                        'item_type': row['item_type'],
                        'item_id': row['item_id'],
                        'billing_cycle': row['billing_cycle'],
                        'price_usd': float(row['price_usd']) if row['price_usd'] else 0.0,
                        'added_at': row['added_at'].isoformat() if row['added_at'] else None,
                        'assigned_servers': [
                            {
                                'guild_id': s['guild_id'],
                                'assigned_at': s['assigned_at'].isoformat() if s['assigned_at'] else None
                            }
                            for s in row['assigned_servers']
                        ]
                    })

                return result
        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while getting cart",
                context={'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while getting cart",
                context={'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while getting cart",
                context={'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error getting cart",
                context={'user_id': user_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error getting cart",
                    context={'user_id': user_id},
                    original=e
                )
            raise

    async def clear_cart(
        self,
        user_id: int
    ) -> bool:
        """Clear all items from user's cart."""
        if not self.pool:
            return False

        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    DELETE FROM cart_items
                    WHERE user_id = $1
                """, user_id)
                return True
        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while clearing cart",
                context={'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while clearing cart",
                context={'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while clearing cart",
                context={'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error clearing cart",
                context={'user_id': user_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error clearing cart",
                    context={'user_id': user_id},
                    original=e
                )
            raise
    # ======================================================================
    # ROLE GROWTH QUERY - FIXED EXCEPTION HANDLING
    # ======================================================================

    async def q_role_growth_stats(self, guild_id: int, role_id: int,
                                  start_time: Optional[datetime] = None,
                                  end_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Get growth statistics for a role using hourly aggregated table."""
        if not self.pool:
            return {
                'total_added': 0,
                'total_removed': 0,
                'net_growth': 0,
                'current_members': 0,
                'growth_rate': 0.0
            }

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {
                'total_added': 0,
                'total_removed': 0,
                'net_growth': 0,
                'current_members': 0,
                'growth_rate': 0.0
            }

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                query = '''
                    SELECT 
                        COALESCE(SUM(added_count), 0) as total_added,
                        COALESCE(SUM(removed_count), 0) as total_removed
                    FROM role_growth_hourly
                    WHERE guild_id = $1 
                    AND role_id = $2
                '''
                params = [guild_id, role_id]

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'role_growth_hourly')

                row = await conn.fetchrow(query, *params)

                total_added = row['total_added'] or 0
                total_removed = row['total_removed'] or 0
                net_growth = total_added - total_removed

                role = guild.get_role(role_id)
                current_members = len(role.members) if role else 0

                growth_rate = 0.0
                if total_added > 0 and start_time and end_time:
                    days = (end_time - start_time).days
                    if days > 0:
                        growth_rate = total_added / days

                return {
                    'total_added': total_added,
                    'total_removed': total_removed,
                    'net_growth': net_growth,
                    'current_members': current_members,
                    'growth_rate': round(growth_rate, 2)
                }

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching role growth stats",
                context={'guild_id': guild_id, 'role_id': role_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching role growth stats",
                context={'guild_id': guild_id, 'role_id': role_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching role growth stats",
                context={'guild_id': guild_id, 'role_id': role_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching role growth stats",
                context={'guild_id': guild_id, 'role_id': role_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching role growth stats",
                    context={'guild_id': guild_id, 'role_id': role_id},
                    original=e
                )
            raise

    # ======================================================================
    # ROLE LEADERBOARD QUERIES - FIXED EXCEPTION HANDLING
    # ======================================================================

    async def q_leaderboard_roles_messages_server(self, guild_id: int,
                                                  limit: int = 100000000000,
                                                  role_filter_ids: Optional[List[int]] = None,
                                                  start_time: Optional[datetime] = None,
                                                  end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get role leaderboard by messages in the server using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                blacklists = await self._get_cached_blacklists(guild_id)

                # OPTIMIZATION: Get all role members at once
                all_role_members = await self._get_all_role_members(guild_id)

                role_message_counts = {}

                for role in guild.roles:
                    if role.is_default():
                        continue

                    if role.id in blacklists['roles']:
                        continue

                    # Get users with this role from pre-fetched data
                    user_ids = all_role_members.get(role.id, [])
                    if not user_ids:
                        continue

                    # Filter out blacklisted users
                    filtered_member_ids = [
                        uid for uid in user_ids if uid not in blacklists['users']]
                    if not filtered_member_ids:
                        continue

                    query = '''
                        SELECT COALESCE(SUM(message_count), 0) as message_count
                        FROM message_tracking_hourly
                        WHERE guild_id = $1 
                        AND user_id = ANY($2::bigint[])
                    '''
                    params = [guild_id, filtered_member_ids]

                    if start_time:
                        query += f" AND hour >= ${len(params) + 1}"
                        params.append(start_time)
                    if end_time:
                        query += f" AND hour <= ${len(params) + 1}"
                        params.append(end_time)

                    query, params = await self._apply_bot_filter(query, params, guild_id, 'message_tracking_hourly')

                    query, params = await self._apply_comprehensive_blacklist_filters(
                        guild_id, guild, query, params, 'message_tracking_hourly',
                        include_users=False, include_channels=True
                    )

                    row = await conn.fetchrow(query, *params)

                    message_count = row['message_count'] or 0

                    if message_count > 0:
                        role_message_counts[role.id] = {
                            'role_id': role.id,
                            'message_count': message_count,
                            'member_count': len(filtered_member_ids),
                            'avg_per_member': message_count / len(filtered_member_ids) if len(filtered_member_ids) > 0 else 0
                        }

                sorted_roles = sorted(role_message_counts.values(),
                                      key=lambda x: x['message_count'],
                                      reverse=True)[:limit]

                return sorted_roles

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching role message leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching role message leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching role message leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching role message leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching role message leaderboard",
                    context={'guild_id': guild_id},
                    original=e
                )
            raise

    async def q_leaderboard_roles_messages_category(self, guild_id: int, category_id: int,
                                                    limit: int = 100000000000,
                                                    role_filter_ids: Optional[List[int]] = None,
                                                    start_time: Optional[datetime] = None,
                                                    end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get role leaderboard by messages in a category using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                blacklists = await self._get_cached_blacklists(guild_id)

                # OPTIMIZATION: Get all role members at once
                all_role_members = await self._get_all_role_members(guild_id)

                role_message_counts = {}

                for role in guild.roles:
                    if role.is_default():
                        continue

                    if role.id in blacklists['roles']:
                        continue

                    # Get users with this role from pre-fetched data
                    user_ids = all_role_members.get(role.id, [])
                    if not user_ids:
                        continue

                    # Filter out blacklisted users
                    filtered_member_ids = [
                        uid for uid in user_ids if uid not in blacklists['users']]
                    if not filtered_member_ids:
                        continue

                    query = '''
                        SELECT COALESCE(SUM(message_count), 0) as message_count
                        FROM message_tracking_hourly
                        WHERE guild_id = $1 
                        AND category_id = $2
                        AND user_id = ANY($3::bigint[])
                    '''
                    params = [guild_id, category_id, filtered_member_ids]

                    if start_time:
                        query += f" AND hour >= ${len(params) + 1}"
                        params.append(start_time)
                    if end_time:
                        query += f" AND hour <= ${len(params) + 1}"
                        params.append(end_time)

                    query, params = await self._apply_bot_filter(query, params, guild_id, 'message_tracking_hourly')

                    query, params = await self._apply_comprehensive_blacklist_filters(
                        guild_id, guild, query, params, 'message_tracking_hourly',
                        include_users=False, include_channels=False,
                        specific_category_id=category_id
                    )

                    row = await conn.fetchrow(query, *params)

                    message_count = row['message_count'] or 0

                    if message_count > 0:
                        role_message_counts[role.id] = {
                            'role_id': role.id,
                            'message_count': message_count,
                            'member_count': len(filtered_member_ids),
                            'avg_per_member': message_count / len(filtered_member_ids) if len(filtered_member_ids) > 0 else 0
                        }

                sorted_roles = sorted(role_message_counts.values(),
                                      key=lambda x: x['message_count'],
                                      reverse=True)[:limit]

                return sorted_roles

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching category role message leaderboard",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching category role message leaderboard",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching category role message leaderboard",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching category role message leaderboard",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching category role message leaderboard",
                    context={'guild_id': guild_id, 'category_id': category_id},
                    original=e
                )
            raise

    async def q_leaderboard_roles_messages_channel(self, guild_id: int, channel_id: int,
                                                   limit: int = 100000000000,
                                                   role_filter_ids: Optional[List[int]] = None,
                                                   start_time: Optional[datetime] = None,
                                                   end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get role leaderboard by messages in a channel using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                blacklists = await self._get_cached_blacklists(guild_id)

                # OPTIMIZATION: Get all role members at once
                all_role_members = await self._get_all_role_members(guild_id)

                role_message_counts = {}

                for role in guild.roles:
                    if role.is_default():
                        continue

                    if role.id in blacklists['roles']:
                        continue

                    # Get users with this role from pre-fetched data
                    user_ids = all_role_members.get(role.id, [])
                    if not user_ids:
                        continue

                    # Filter out blacklisted users
                    filtered_member_ids = [
                        uid for uid in user_ids if uid not in blacklists['users']]
                    if not filtered_member_ids:
                        continue

                    query = '''
                        SELECT COALESCE(SUM(message_count), 0) as message_count
                        FROM message_tracking_hourly
                        WHERE guild_id = $1 
                        AND channel_id = $2
                        AND user_id = ANY($3::bigint[])
                    '''
                    params = [guild_id, channel_id, filtered_member_ids]

                    if start_time:
                        query += f" AND hour >= ${len(params) + 1}"
                        params.append(start_time)
                    if end_time:
                        query += f" AND hour <= ${len(params) + 1}"
                        params.append(end_time)

                    query, params = await self._apply_bot_filter(query, params, guild_id, 'message_tracking_hourly')

                    query, params = await self._apply_comprehensive_blacklist_filters(
                        guild_id, guild, query, params, 'message_tracking_hourly',
                        include_users=False, include_channels=False,
                        specific_channel_id=channel_id
                    )

                    row = await conn.fetchrow(query, *params)

                    message_count = row['message_count'] or 0

                    if message_count > 0:
                        role_message_counts[role.id] = {
                            'role_id': role.id,
                            'message_count': message_count,
                            'member_count': len(filtered_member_ids),
                            'avg_per_member': message_count / len(filtered_member_ids) if len(filtered_member_ids) > 0 else 0
                        }

                sorted_roles = sorted(role_message_counts.values(),
                                      key=lambda x: x['message_count'],
                                      reverse=True)[:limit]

                return sorted_roles

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching channel role message leaderboard",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching channel role message leaderboard",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching channel role message leaderboard",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching channel role message leaderboard",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching channel role message leaderboard",
                    context={'guild_id': guild_id, 'channel_id': channel_id},
                    original=e
                )
            raise

    async def q_leaderboard_roles_voice_server(self, guild_id: int,
                                               limit: int = 100000000000,
                                               role_filter_ids: Optional[List[int]] = None,
                                               start_time: Optional[datetime] = None,
                                               end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get role leaderboard by voice time in the server using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)
            state_flags_filter = await self._get_voice_state_filter_value(guild_id)

            async with self.pool.acquire() as conn:
                blacklists = await self._get_cached_blacklists(guild_id)

                # OPTIMIZATION: Get all role members at once
                all_role_members = await self._get_all_role_members(guild_id)

                role_voice_counts = {}

                for role in guild.roles:
                    if role.is_default():
                        continue

                    if role.id in blacklists['roles']:
                        continue

                    # Get users with this role from pre-fetched data
                    user_ids = all_role_members.get(role.id, [])
                    if not user_ids:
                        continue

                    # Filter out blacklisted users
                    filtered_member_ids = [
                        uid for uid in user_ids if uid not in blacklists['users']]
                    if not filtered_member_ids:
                        continue

                    query = '''
                        SELECT COALESCE(SUM(total_seconds), 0) as total_seconds
                        FROM voice_session_history_hourly
                        WHERE guild_id = $1 
                        AND user_id = ANY($2::bigint[])
                    '''
                    params = [guild_id, filtered_member_ids]

                    # 👇 ADD VOICE STATE FILTER
                    query, params = await self._apply_voice_state_filter(query, params, guild_id, 'state_flags')

                    if state_flags_filter is not None:
                        query += f" AND state_flags = ${len(params) + 1}"
                        params.append(state_flags_filter)

                    if start_time:
                        query += f" AND hour >= ${len(params) + 1}"
                        params.append(start_time)
                    if end_time:
                        query += f" AND hour <= ${len(params) + 1}"
                        params.append(end_time)

                    query, params = await self._apply_bot_filter(query, params, guild_id, 'voice_session_history_hourly')

                    query, params = await self._apply_comprehensive_blacklist_filters(
                        guild_id, guild, query, params, 'voice_session_history_hourly',
                        include_users=False, include_channels=True
                    )

                    row = await conn.fetchrow(query, *params)

                    total_seconds = row['total_seconds'] or 0

                    if total_seconds > 0:
                        role_voice_counts[role.id] = {
                            'role_id': role.id,
                            'total_seconds': total_seconds,
                            'total_hours': round(total_seconds / 3600, 2),
                            'member_count': len(filtered_member_ids),
                            'avg_per_member': total_seconds / len(filtered_member_ids) if len(filtered_member_ids) > 0 else 0
                        }

                sorted_roles = sorted(role_voice_counts.values(),
                                      key=lambda x: x['total_seconds'],
                                      reverse=True)[:limit]

                return sorted_roles

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching role voice leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching role voice leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching role voice leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching role voice leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching role voice leaderboard",
                    context={'guild_id': guild_id},
                    original=e
                )
            raise

    async def q_leaderboard_roles_voice_category(self, guild_id: int, category_id: int,
                                                 limit: int = 100000000000,
                                                 role_filter_ids: Optional[List[int]] = None,
                                                 start_time: Optional[datetime] = None,
                                                 end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get role leaderboard by voice time in a category using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)
            state_flags_filter = await self._get_voice_state_filter_value(guild_id)

            async with self.pool.acquire() as conn:
                blacklists = await self._get_cached_blacklists(guild_id)

                # OPTIMIZATION: Get all role members at once
                all_role_members = await self._get_all_role_members(guild_id)

                role_voice_counts = {}

                for role in guild.roles:
                    if role.is_default():
                        continue

                    if role.id in blacklists['roles']:
                        continue

                    # Get users with this role from pre-fetched data
                    user_ids = all_role_members.get(role.id, [])
                    if not user_ids:
                        continue

                    # Filter out blacklisted users
                    filtered_member_ids = [
                        uid for uid in user_ids if uid not in blacklists['users']]
                    if not filtered_member_ids:
                        continue

                    query = '''
                        SELECT COALESCE(SUM(total_seconds), 0) as total_seconds
                        FROM voice_session_history_hourly
                        WHERE guild_id = $1 
                        AND category_id = $2
                        AND user_id = ANY($3::bigint[])
                    '''
                    params = [guild_id, category_id, filtered_member_ids]

                    # 👇 ADD VOICE STATE FILTER
                    query, params = await self._apply_voice_state_filter(query, params, guild_id, 'state_flags')

                    if state_flags_filter is not None:
                        query += f" AND state_flags = ${len(params) + 1}"
                        params.append(state_flags_filter)

                    if start_time:
                        query += f" AND hour >= ${len(params) + 1}"
                        params.append(start_time)
                    if end_time:
                        query += f" AND hour <= ${len(params) + 1}"
                        params.append(end_time)

                    query, params = await self._apply_bot_filter(query, params, guild_id, 'voice_session_history_hourly')

                    query, params = await self._apply_comprehensive_blacklist_filters(
                        guild_id, guild, query, params, 'voice_session_history_hourly',
                        include_users=False, include_channels=False,
                        specific_category_id=category_id
                    )

                    row = await conn.fetchrow(query, *params)

                    total_seconds = row['total_seconds'] or 0

                    if total_seconds > 0:
                        role_voice_counts[role.id] = {
                            'role_id': role.id,
                            'total_seconds': total_seconds,
                            'total_hours': round(total_seconds / 3600, 2),
                            'member_count': len(filtered_member_ids),
                            'avg_per_member': total_seconds / len(filtered_member_ids) if len(filtered_member_ids) > 0 else 0
                        }

                sorted_roles = sorted(role_voice_counts.values(),
                                      key=lambda x: x['total_seconds'],
                                      reverse=True)[:limit]

                return sorted_roles

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching category role voice leaderboard",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching category role voice leaderboard",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching category role voice leaderboard",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching category role voice leaderboard",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching category role voice leaderboard",
                    context={'guild_id': guild_id, 'category_id': category_id},
                    original=e
                )
            raise

    async def q_leaderboard_roles_voice_channel(self, guild_id: int, channel_id: int,
                                                limit: int = 100000000000,
                                                role_filter_ids: Optional[List[int]] = None,
                                                start_time: Optional[datetime] = None,
                                                end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get role leaderboard by voice time in a channel using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)
            state_flags_filter = await self._get_voice_state_filter_value(guild_id)

            async with self.pool.acquire() as conn:
                blacklists = await self._get_cached_blacklists(guild_id)

                # OPTIMIZATION: Get all role members at once
                all_role_members = await self._get_all_role_members(guild_id)

                role_voice_counts = {}

                for role in guild.roles:
                    if role.is_default():
                        continue

                    if role.id in blacklists['roles']:
                        continue

                    # Get users with this role from pre-fetched data
                    user_ids = all_role_members.get(role.id, [])
                    if not user_ids:
                        continue

                    # Filter out blacklisted users
                    filtered_member_ids = [
                        uid for uid in user_ids if uid not in blacklists['users']]
                    if not filtered_member_ids:
                        continue

                    query = '''
                        SELECT COALESCE(SUM(total_seconds), 0) as total_seconds
                        FROM voice_session_history_hourly
                        WHERE guild_id = $1 
                        AND channel_id = $2
                        AND user_id = ANY($3::bigint[])
                    '''
                    params = [guild_id, channel_id, filtered_member_ids]

                    # 👇 ADD VOICE STATE FILTER
                    query, params = await self._apply_voice_state_filter(query, params, guild_id, 'state_flags')

                    if state_flags_filter is not None:
                        query += f" AND state_flags = ${len(params) + 1}"
                        params.append(state_flags_filter)

                    if start_time:
                        query += f" AND hour >= ${len(params) + 1}"
                        params.append(start_time)
                    if end_time:
                        query += f" AND hour <= ${len(params) + 1}"
                        params.append(end_time)

                    query, params = await self._apply_bot_filter(query, params, guild_id, 'voice_session_history_hourly')

                    query, params = await self._apply_comprehensive_blacklist_filters(
                        guild_id, guild, query, params, 'voice_session_history_hourly',
                        include_users=False, include_channels=False,
                        specific_channel_id=channel_id
                    )

                    row = await conn.fetchrow(query, *params)

                    total_seconds = row['total_seconds'] or 0

                    if total_seconds > 0:
                        role_voice_counts[role.id] = {
                            'role_id': role.id,
                            'total_seconds': total_seconds,
                            'total_hours': round(total_seconds / 3600, 2),
                            'member_count': len(filtered_member_ids),
                            'avg_per_member': total_seconds / len(filtered_member_ids) if len(filtered_member_ids) > 0 else 0
                        }

                sorted_roles = sorted(role_voice_counts.values(),
                                      key=lambda x: x['total_seconds'],
                                      reverse=True)[:limit]

                return sorted_roles

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching channel role voice leaderboard",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching channel role voice leaderboard",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching channel role voice leaderboard",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching channel role voice leaderboard",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching channel role voice leaderboard",
                    context={'guild_id': guild_id, 'channel_id': channel_id},
                    original=e
                )
            raise

    async def q_leaderboard_roles_invites_server(self, guild_id: int,
                                                 limit: int = 100000000000,
                                                 role_filter_ids: Optional[List[int]] = None,
                                                 start_time: Optional[datetime] = None,
                                                 end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get role leaderboard by invites in the server (uses raw table - static)."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                blacklists = await self._get_cached_blacklists(guild_id)

                # OPTIMIZATION: Get all role members at once
                all_role_members = await self._get_all_role_members(guild_id)

                role_invite_counts = {}

                for role in guild.roles:
                    if role.is_default():
                        continue

                    if role.id in blacklists['roles']:
                        continue

                    # Get users with this role from pre-fetched data
                    user_ids = all_role_members.get(role.id, [])
                    if not user_ids:
                        continue

                    # Filter out blacklisted users
                    filtered_member_ids = [
                        uid for uid in user_ids if uid not in blacklists['users']]
                    if not filtered_member_ids:
                        continue

                    # FIXED: Removed channel_id reference (doesn't exist in invite_tracking)
                    query = '''
                        SELECT 
                            COUNT(*) FILTER (WHERE invite_type = 'valid') as valid_invites,
                            COUNT(*) as total_invites
                        FROM invite_tracking
                        WHERE guild_id = $1 
                        AND inviter_id = ANY($2::bigint[])
                        AND invite_type IN ('valid', 'suspicious')
                    '''
                    params = [guild_id, filtered_member_ids]

                    if start_time:
                        query += f" AND created_at >= ${len(params) + 1}"
                        params.append(start_time)
                    if end_time:
                        query += f" AND created_at <= ${len(params) + 1}"
                        params.append(end_time)

                    query, params = await self._apply_bot_filter(query, params, guild_id, 'invite_tracking')

                    # FIXED: Removed channel_id from blacklist filters (invite_tracking doesn't have channel_id)
                    query, params = await self._apply_comprehensive_blacklist_filters(
                        guild_id, guild, query, params, 'invite_tracking',
                        include_users=False, include_channels=False  # Changed to False
                    )

                    row = await conn.fetchrow(query, *params)

                    valid_invites = row['valid_invites'] or 0

                    if valid_invites > 0:
                        role_invite_counts[role.id] = {
                            'role_id': role.id,
                            'valid_invites': valid_invites,
                            'total_invites': row['total_invites'] or 0,
                            'member_count': len(filtered_member_ids),
                            'avg_per_member': valid_invites / len(filtered_member_ids) if len(filtered_member_ids) > 0 else 0
                        }

                sorted_roles = sorted(role_invite_counts.values(),
                                      key=lambda x: x['valid_invites'],
                                      reverse=True)[:limit]

                return sorted_roles

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching role invite leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching role invite leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching role invite leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching role invite leaderboard",
                context={'guild_id': guild_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching role invite leaderboard",
                    context={'guild_id': guild_id},
                    original=e
                )
            raise

    async def q_leaderboard_roles_invites_category(self, guild_id: int, category_id: int,
                                                   limit: int = 100000000000,
                                                   role_filter_ids: Optional[List[int]] = None,
                                                   start_time: Optional[datetime] = None,
                                                   end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get role leaderboard by invites in a category (uses raw table - static)."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                blacklists = await self._get_cached_blacklists(guild_id)

                # OPTIMIZATION: Get all role members at once
                all_role_members = await self._get_all_role_members(guild_id)

                role_invite_counts = {}

                for role in guild.roles:
                    if role.is_default():
                        continue

                    if role.id in blacklists['roles']:
                        continue

                    # Get users with this role from pre-fetched data
                    user_ids = all_role_members.get(role.id, [])
                    if not user_ids:
                        continue

                    # Filter out blacklisted users
                    filtered_member_ids = [
                        uid for uid in user_ids if uid not in blacklists['users']]
                    if not filtered_member_ids:
                        continue

                    query = '''
                        SELECT 
                            COUNT(*) FILTER (WHERE invite_type = 'valid') as valid_invites,
                            COUNT(*) as total_invites
                        FROM invite_tracking
                        WHERE guild_id = $1 
                        AND inviter_id = ANY($2::bigint[])
                        AND invite_type IN ('valid', 'suspicious')
                    '''
                    params = [guild_id, filtered_member_ids]

                    if start_time:
                        query += f" AND created_at >= ${len(params) + 1}"
                        params.append(start_time)
                    if end_time:
                        query += f" AND created_at <= ${len(params) + 1}"
                        params.append(end_time)

                    query, params = await self._apply_bot_filter(query, params, guild_id, 'invite_tracking')

                    query, params = await self._apply_comprehensive_blacklist_filters(
                        guild_id, guild, query, params, 'invite_tracking',
                        include_users=False, include_channels=True
                    )

                    row = await conn.fetchrow(query, *params)

                    valid_invites = row['valid_invites'] or 0

                    if valid_invites > 0:
                        role_invite_counts[role.id] = {
                            'role_id': role.id,
                            'valid_invites': valid_invites,
                            'total_invites': row['total_invites'] or 0,
                            'member_count': len(filtered_member_ids),
                            'avg_per_member': valid_invites / len(filtered_member_ids) if len(filtered_member_ids) > 0 else 0
                        }

                sorted_roles = sorted(role_invite_counts.values(),
                                      key=lambda x: x['valid_invites'],
                                      reverse=True)[:limit]

                return sorted_roles

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching category role invite leaderboard",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching category role invite leaderboard",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching category role invite leaderboard",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching category role invite leaderboard",
                context={'guild_id': guild_id, 'category_id': category_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching category role invite leaderboard",
                    context={'guild_id': guild_id, 'category_id': category_id},
                    original=e
                )
            raise

    async def q_leaderboard_roles_invites_channel(self, guild_id: int, channel_id: int,
                                                  limit: int = 100000000000,
                                                  role_filter_ids: Optional[List[int]] = None,
                                                  start_time: Optional[datetime] = None,
                                                  end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get role leaderboard by invites in a channel (uses raw table - static)."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                blacklists = await self._get_cached_blacklists(guild_id)

                # OPTIMIZATION: Get all role members at once
                all_role_members = await self._get_all_role_members(guild_id)

                role_invite_counts = {}

                for role in guild.roles:
                    if role.is_default():
                        continue

                    if role.id in blacklists['roles']:
                        continue

                    # Get users with this role from pre-fetched data
                    user_ids = all_role_members.get(role.id, [])
                    if not user_ids:
                        continue

                    # Filter out blacklisted users
                    filtered_member_ids = [
                        uid for uid in user_ids if uid not in blacklists['users']]
                    if not filtered_member_ids:
                        continue

                    query = '''
                        SELECT 
                            COUNT(*) FILTER (WHERE invite_type = 'valid') as valid_invites,
                            COUNT(*) as total_invites
                        FROM invite_tracking
                        WHERE guild_id = $1 
                        AND inviter_id = ANY($2::bigint[])
                        AND invite_type IN ('valid', 'suspicious')
                    '''
                    params = [guild_id, filtered_member_ids]

                    if start_time:
                        query += f" AND created_at >= ${len(params) + 1}"
                        params.append(start_time)
                    if end_time:
                        query += f" AND created_at <= ${len(params) + 1}"
                        params.append(end_time)

                    query, params = await self._apply_bot_filter(query, params, guild_id, 'invite_tracking')

                    query, params = await self._apply_comprehensive_blacklist_filters(
                        guild_id, guild, query, params, 'invite_tracking',
                        include_users=False, include_channels=True
                    )

                    row = await conn.fetchrow(query, *params)

                    valid_invites = row['valid_invites'] or 0

                    if valid_invites > 0:
                        role_invite_counts[role.id] = {
                            'role_id': role.id,
                            'valid_invites': valid_invites,
                            'total_invites': row['total_invites'] or 0,
                            'member_count': len(filtered_member_ids),
                            'avg_per_member': valid_invites / len(filtered_member_ids) if len(filtered_member_ids) > 0 else 0
                        }

                sorted_roles = sorted(role_invite_counts.values(),
                                      key=lambda x: x['valid_invites'],
                                      reverse=True)[:limit]

                return sorted_roles

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching channel role invite leaderboard",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching channel role invite leaderboard",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching channel role invite leaderboard",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching channel role invite leaderboard",
                context={'guild_id': guild_id, 'channel_id': channel_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching channel role invite leaderboard",
                    context={'guild_id': guild_id, 'channel_id': channel_id},
                    original=e
                )
            raise

    # ======================================================================
    # EMOJI USER QUERY - FIXED EXCEPTION HANDLING
    # ======================================================================

    async def q_user_top_emojis(self, guild_id: int, user_id: int,
                                limit: int = 100000000000,
                                role_filter_ids: Optional[List[int]] = None,
                                channel_id: Optional[int] = None,
                                category_id: Optional[int] = None,
                                start_time: Optional[datetime] = None,
                                end_time: Optional[datetime] = None,
                                usage_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get a user's top emojis using hourly aggregated table."""
        if not self.pool:
            return []

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return []

        if channel_id and category_id:
            category_id = None

        try:
            start_time = ensure_aware(start_time)
            end_time = ensure_aware(end_time)

            async with self.pool.acquire() as conn:
                blacklists = await self._get_cached_blacklists(guild_id)

                if user_id in blacklists['users']:
                    return []

                # Apply role filtering using current_role_members table
                if role_filter_ids:
                    user_ids = await self._get_users_with_roles(guild_id, role_filter_ids)
                    if user_ids and user_id not in user_ids:
                        return []

                member = guild.get_member(user_id)
                if member:
                    user_role_ids = {role.id for role in member.roles}
                    if user_role_ids.intersection(blacklists['roles']):
                        return []

                query = '''
                    SELECT 
                        emoji_str,
                        is_custom,
                        SUM(usage_count) as total_usage,
                        COUNT(DISTINCT channel_id) as unique_channels
                    FROM emoji_usage_hourly
                    WHERE guild_id = $1 
                    AND user_id = $2
                '''
                params = [guild_id, user_id]

                if channel_id:
                    query += f" AND channel_id = ${len(params) + 1}"
                    params.append(channel_id)
                elif category_id:
                    query += f" AND category_id = ${len(params) + 1}"
                    params.append(category_id)

                if usage_type:
                    query += f" AND usage_type = ${len(params) + 1}"
                    params.append(usage_type)

                if start_time:
                    query += f" AND hour >= ${len(params) + 1}"
                    params.append(start_time)
                if end_time:
                    query += f" AND hour <= ${len(params) + 1}"
                    params.append(end_time)

                query, params = await self._apply_bot_filter(query, params, guild_id, 'emoji_usage_hourly')

                include_channels_in_blacklist = not (channel_id or category_id)
                query, params = await self._apply_comprehensive_blacklist_filters(
                    guild_id, guild, query, params, 'emoji_usage_hourly',
                    include_users=False,
                    include_channels=include_channels_in_blacklist,
                    specific_channel_id=channel_id if channel_id else None,
                    specific_category_id=category_id if category_id else None
                )

                query += f'''
                    GROUP BY emoji_str, is_custom
                    HAVING SUM(usage_count) > 0
                    ORDER BY total_usage DESC
                    LIMIT {limit}
                '''

                rows = await conn.fetch(query, *params)

                result = []
                for row in rows:
                    result.append({
                        'emoji_str': row['emoji_str'],
                        'is_custom': row['is_custom'],
                        'usage_count': row['total_usage'] or 0,
                        'unique_channels': row['unique_channels'] or 0
                    })

                return result

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while fetching user top emojis",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while fetching user top emojis",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while fetching user top emojis",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error fetching user top emojis",
                context={'guild_id': guild_id, 'user_id': user_id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error fetching user top emojis",
                    context={'guild_id': guild_id, 'user_id': user_id},
                    original=e
                )
            raise
        
    
    async def get_all_modules(pool: asyncpg.Pool) -> List[Dict]:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM modules WHERE is_active = TRUE ORDER BY module_number")
            return [dict(r) for r in rows]
    
    
    async def get_module_by_key(pool: asyncpg.Pool, module_key: str) -> Optional[Dict]:
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM modules WHERE module_key = $1", module_key)
            return dict(row) if row else None
    
    
    async def get_module_by_paddle_product(pool: asyncpg.Pool, paddle_product_id: str) -> Optional[Dict]:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM modules WHERE paddle_product_id = $1", paddle_product_id
            )
            return dict(row) if row else None
    
    
    async def get_module_by_paddle_price(pool: asyncpg.Pool, paddle_price_id: str) -> Optional[Dict]:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT * FROM modules
                WHERE paddle_monthly_price_id = $1
                    OR paddle_yearly_price_id   = $1""",
                paddle_price_id,
            )
            return dict(row) if row else None
    
    
    # ──────────────────────────────────────────────────────────────────────────────
    # DISCOUNTS
    # ──────────────────────────────────────────────────────────────────────────────
    
    async def get_discount_for_server_count(pool: asyncpg.Pool, server_count: int) -> Optional[Dict]:
        """Return the discount row for *exactly* server_count, or the highest available."""
        async with pool.acquire() as conn:
            capped = min(server_count, 11)
            row = await conn.fetchrow(
                """SELECT * FROM server_count_discounts
                WHERE server_count <= $1
                ORDER BY server_count DESC LIMIT 1""",
                capped,
            )
            return dict(row) if row else None
    
    
    async def get_all_discounts(pool: asyncpg.Pool) -> List[Dict]:
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM server_count_discounts ORDER BY server_count")
            return [dict(r) for r in rows]
    
    
    # ──────────────────────────────────────────────────────────────────────────────
    # CUSTOMERS
    # ──────────────────────────────────────────────────────────────────────────────
    
    async def upsert_paddle_customer(
        pool: asyncpg.Pool,
        discord_id: str,
        paddle_customer_id: Optional[str] = None,
        email: Optional[str] = None,
    ) -> Dict:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO paddle_customers (discord_id, paddle_customer_id, email, updated_at)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (discord_id) DO UPDATE SET
                    paddle_customer_id = COALESCE(EXCLUDED.paddle_customer_id, paddle_customers.paddle_customer_id),
                    email              = COALESCE(EXCLUDED.email,              paddle_customers.email),
                    updated_at         = NOW()
                RETURNING *""",
                discord_id, paddle_customer_id, email,
            )
            return dict(row)
    
    
    async def get_paddle_customer(pool: asyncpg.Pool, discord_id: str) -> Optional[Dict]:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM paddle_customers WHERE discord_id = $1", discord_id
            )
            return dict(row) if row else None
    
    
    async def get_paddle_customer_by_paddle_id(pool: asyncpg.Pool, paddle_customer_id: str) -> Optional[Dict]:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM paddle_customers WHERE paddle_customer_id = $1", paddle_customer_id
            )
            return dict(row) if row else None
    
    
    # ──────────────────────────────────────────────────────────────────────────────
    # SUBSCRIPTIONS
    # ──────────────────────────────────────────────────────────────────────────────
    
    async def create_subscription(pool: asyncpg.Pool, data: Dict) -> Dict:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO subscriptions (
                    discord_id, guild_id, paddle_subscription_id, paddle_transaction_id,
                    paddle_customer_id, module_id, tier_id, billing_cycle,
                    base_price_usd, discount_pct, final_price_usd, server_count_at_purchase,
                    status, current_period_start, current_period_end
                ) VALUES (
                    $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15
                ) RETURNING *""",
                data["discord_id"], data["guild_id"],
                data["paddle_subscription_id"], data.get("paddle_transaction_id"),
                data["paddle_customer_id"], data.get("module_id"), data.get("tier_id"),
                data["billing_cycle"], data["base_price_usd"],
                data.get("discount_pct", 0), data["final_price_usd"],
                data.get("server_count_at_purchase", 1),
                data.get("status", "active"),
                data.get("current_period_start"), data.get("current_period_end"),
            )
            return dict(row)
    
    
    async def get_subscription(pool: asyncpg.Pool, paddle_subscription_id: str) -> Optional[Dict]:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM subscriptions WHERE paddle_subscription_id = $1",
                paddle_subscription_id,
            )
            return dict(row) if row else None
    
    
    async def get_subscriptions_for_user(pool: asyncpg.Pool, discord_id: str) -> List[Dict]:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT s.*, m.display_name AS module_name, m.module_key
                FROM subscriptions s
                LEFT JOIN modules m ON s.module_id = m.id
                WHERE s.discord_id = $1
                ORDER BY s.created_at DESC""",
                discord_id,
            )
            return [dict(r) for r in rows]
    
    
    async def get_subscriptions_for_guild(pool: asyncpg.Pool, guild_id: int) -> List[Dict]:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT s.*, m.display_name AS module_name, m.module_key
                FROM subscriptions s
                LEFT JOIN modules m ON s.module_id = m.id
                WHERE s.guild_id = $1 AND s.status = 'active'
                ORDER BY s.created_at DESC""",
                guild_id,
            )
            return [dict(r) for r in rows]
    
    
    async def update_subscription_status(
        pool: asyncpg.Pool,
        paddle_subscription_id: str,
        status: str,
        current_period_start: Optional[datetime] = None,
        current_period_end: Optional[datetime] = None,
        canceled_at: Optional[datetime] = None,
        cancel_at_period_end: Optional[bool] = None,
        paddle_transaction_id: Optional[str] = None,
    ) -> Optional[Dict]:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """UPDATE subscriptions SET
                    status                = $2,
                    current_period_start  = COALESCE($3, current_period_start),
                    current_period_end    = COALESCE($4, current_period_end),
                    canceled_at           = COALESCE($5, canceled_at),
                    cancel_at_period_end  = COALESCE($6, cancel_at_period_end),
                    paddle_transaction_id = COALESCE($7, paddle_transaction_id),
                    updated_at            = NOW()
                WHERE paddle_subscription_id = $1
                RETURNING *""",
                paddle_subscription_id, status,
                current_period_start, current_period_end,
                canceled_at, cancel_at_period_end, paddle_transaction_id,
            )
            return dict(row) if row else None
    
    
    # ──────────────────────────────────────────────────────────────────────────────
    # GUILD MODULE ACCESS
    # ──────────────────────────────────────────────────────────────────────────────
    
    async def grant_module_access(
        pool: asyncpg.Pool,
        guild_id: int,
        module_id: int,
        subscription_id: int,
        discord_id: str,
    ) -> Dict:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO guild_module_access (guild_id, module_id, subscription_id, discord_id, is_active)
                VALUES ($1, $2, $3, $4, TRUE)
                ON CONFLICT (guild_id, module_id, subscription_id) DO UPDATE SET
                    is_active  = TRUE,
                    revoked_at = NULL
                RETURNING *""",
                guild_id, module_id, subscription_id, discord_id,
            )
            return dict(row)
    
    
    async def revoke_module_access(pool: asyncpg.Pool, subscription_id: int) -> int:
        """Revoke all access rows tied to a subscription. Returns affected count."""
        async with pool.acquire() as conn:
            result = await conn.execute(
                """UPDATE guild_module_access SET
                    is_active  = FALSE,
                    revoked_at = NOW()
                WHERE subscription_id = $1 AND is_active = TRUE""",
                subscription_id,
            )
            return int(result.split()[-1])
    
    
    async def guild_has_module(pool: asyncpg.Pool, guild_id: int, module_key: str) -> bool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT 1 FROM guild_module_access gma
                JOIN modules m ON gma.module_id = m.id
                WHERE gma.guild_id = $1
                    AND m.module_key = $2
                    AND gma.is_active = TRUE
                LIMIT 1""",
                guild_id, module_key,
            )
            return row is not None
    
    
    async def get_guild_active_modules(pool: asyncpg.Pool, guild_id: int) -> List[Dict]:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT m.module_key, m.display_name, m.module_number,
                        gma.granted_at, gma.discord_id AS granted_by,
                        s.billing_cycle, s.current_period_end,
                        s.paddle_subscription_id
                FROM guild_module_access gma
                JOIN modules m ON gma.module_id = m.id
                JOIN subscriptions s ON gma.subscription_id = s.id
                WHERE gma.guild_id = $1 AND gma.is_active = TRUE
                ORDER BY m.module_number""",
                guild_id,
            )
            return [dict(r) for r in rows]
    
    
    # ──────────────────────────────────────────────────────────────────────────────
    # TRANSACTIONS
    # ──────────────────────────────────────────────────────────────────────────────
    
    async def log_transaction(pool: asyncpg.Pool, data: Dict) -> Dict:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO payment_transactions (
                    paddle_transaction_id, paddle_subscription_id, paddle_customer_id,
                    discord_id, guild_id, amount_usd, currency, status,
                    transaction_type, raw_payload
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                ON CONFLICT (paddle_transaction_id) DO UPDATE SET
                    status      = EXCLUDED.status,
                    raw_payload = EXCLUDED.raw_payload
                RETURNING *""",
                data.get("paddle_transaction_id"), data.get("paddle_subscription_id"),
                data.get("paddle_customer_id"), data.get("discord_id"),
                data.get("guild_id"), data.get("amount_usd"), data.get("currency", "USD"),
                data.get("status"), data.get("transaction_type"),
                json.dumps(data.get("raw_payload", {})),
            )
            return dict(row)
    
    
    async def get_transactions_for_user(pool: asyncpg.Pool, discord_id: str) -> List[Dict]:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM payment_transactions WHERE discord_id = $1 ORDER BY created_at DESC",
                discord_id,
            )
            return [dict(r) for r in rows]
    
    
    async def get_transactions_for_guild(pool: asyncpg.Pool, guild_id: int) -> List[Dict]:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM payment_transactions WHERE guild_id = $1 ORDER BY created_at DESC",
                guild_id,
            )
            return [dict(r) for r in rows]
    
    
    # ──────────────────────────────────────────────────────────────────────────────
    # REFUNDS
    # ──────────────────────────────────────────────────────────────────────────────
    
    async def log_refund(pool: asyncpg.Pool, data: Dict) -> Dict:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """INSERT INTO refunds (
                    paddle_transaction_id, paddle_subscription_id,
                    discord_id, guild_id, amount_usd, reason
                ) VALUES ($1,$2,$3,$4,$5,$6)
                RETURNING *""",
                data.get("paddle_transaction_id"), data.get("paddle_subscription_id"),
                data.get("discord_id"), data.get("guild_id"),
                data.get("amount_usd"), data.get("reason"),
            )
            return dict(row)
    
    
    async def get_refunds_for_user(pool: asyncpg.Pool, discord_id: str) -> List[Dict]:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM refunds WHERE discord_id = $1 ORDER BY refunded_at DESC",
                discord_id,
            )
            return [dict(r) for r in rows]
    
    
    # ──────────────────────────────────────────────────────────────────────────────
    # WEBHOOK EVENT LOG
    # ──────────────────────────────────────────────────────────────────────────────
    
    async def is_event_processed(pool: asyncpg.Pool, event_id: str) -> bool:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT processed FROM paddle_webhook_events WHERE event_id = $1", event_id
            )
            if row is None:
                return False
            return row["processed"]
    
    
    async def record_webhook_event(
        pool: asyncpg.Pool,
        event_id: str,
        event_type: str,
        payload: Dict,
    ) -> None:
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO paddle_webhook_events (event_id, event_type, payload)
                VALUES ($1, $2, $3)
                ON CONFLICT (event_id) DO NOTHING""",
                event_id, event_type, json.dumps(payload),
            )
    
    
    async def mark_event_processed(
        pool: asyncpg.Pool, event_id: str, error: Optional[str] = None
    ) -> None:
        async with pool.acquire() as conn:
            await conn.execute(
                """UPDATE paddle_webhook_events SET
                    processed        = $2,
                    processing_error = $3,
                    processed_at     = NOW()
                WHERE event_id = $1""",
                event_id, error is None, error,
            )


    # ======================================================================
    # CLEANUP TASKS - FIXED EXCEPTION HANDLING
    # ======================================================================

    @tasks.loop(minutes=5)
    async def connection_pool_health_check(self):
        """Check database connection health."""
        if not self.pool or not self.db_connected:
            return

        try:
            async with self.pool.acquire() as conn:
                await conn.fetchval('SELECT 1')

            if self.redis and self.redis_connected:
                await self.redis.ping()

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            self.db_connected = False
            raise DatabaseConnectionError(
                "Database connection does not exist during health check",
                context={'operation': 'connection_pool_health_check'},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            self.db_connected = False
            raise DatabaseConnectionError(
                "Database connection failed during health check",
                context={'operation': 'connection_pool_health_check'},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            self.db_connected = False
            raise DatabaseTimeoutError(
                "Database health check timed out",
                context={'operation': 'connection_pool_health_check'},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            self.db_connected = False
            raise DatabaseQueryError(
                "Database health check query failed",
                context={'operation': 'connection_pool_health_check'},
                original=e
            )
        except RedisConnectionError as e:
            self.redis_connected = False
            raise CacheConnectionError(
                "Redis health check failed",
                context={'operation': 'connection_pool_health_check'},
                original=e
            )
        except RedisTimeoutError as e:
            self.redis_connected = False
            raise CacheTimeoutError(
                "Redis health check timed out",
                context={'operation': 'connection_pool_health_check'},
                original=e
            )
        except RedisError as e:
            self.redis_connected = False
            raise CacheReadFailed(
                "Redis health check failed",
                context={'operation': 'connection_pool_health_check'},
                original=e
            )

    @tasks.loop(hours=24)
    async def metrics_reset_task(self):
        """Reset metrics counters daily."""
        async with self.metrics_lock:
            self.metrics.update({
                'redis_writes': 0,
                'redis_batch_flushes': 0,
                'voice_updates': 0,
                'message_inserts': 0,
                'emoji_inserts': 0,
                'invite_inserts': 0,
                'mention_inserts': 0,
                'errors': 0,
                'db_queries': 0,
                'connection_retries': 0,
                'failed_operations': 0
            })

    # ======================================================================
    # HELPER METHODS FOR SERVER TRACKING - FIXED EXCEPTION HANDLING
    # ======================================================================

    async def update_user_servers_in_db(self, user_id: int, guild: discord.Guild, action: str = "add"):
        """Update user_servers table when a user joins/leaves a guild with the bot."""
        if not self.pool:
            return

        try:
            async with self.pool.acquire() as conn:
                try:
                    user_exists = await conn.fetchval("""
                        SELECT EXISTS(SELECT 1 FROM users WHERE discord_id = $1)
                    """, str(user_id))
                except asyncpg.exceptions.PostgresError as e:
                    raise DatabaseQueryError(
                        "Failed to check user existence",
                        context={'user_id': user_id, 'guild_id': guild.id},
                        original=e
                    )

                if not user_exists:
                    return

                if action == "add":
                    try:
                        await conn.execute("""
                            INSERT INTO user_servers (discord_id, guild_id, guild_name, guild_icon, member_count)
                            VALUES ($1, $2, $3, $4, $5)
                            ON CONFLICT (discord_id, guild_id) 
                            DO UPDATE SET 
                                guild_name = EXCLUDED.guild_name,
                                guild_icon = EXCLUDED.guild_icon,
                                member_count = EXCLUDED.member_count,
                                last_updated = CURRENT_TIMESTAMP
                        """,
                                           str(user_id),
                                           str(guild.id),
                                           guild.name,
                                           guild.icon.key if guild.icon else None,
                                           guild.member_count
                                           )
                    except asyncpg.exceptions.PostgresError as e:
                        raise DatabaseQueryError(
                            "Failed to insert user server",
                            context={'user_id': user_id, 'guild_id': guild.id},
                            original=e
                        )

                elif action == "remove":
                    try:
                        await conn.execute("""
                            DELETE FROM user_servers 
                            WHERE discord_id = $1 AND guild_id = $2
                        """,
                                           str(user_id),
                                           str(guild.id)
                                           )
                    except asyncpg.exceptions.PostgresError as e:
                        raise DatabaseQueryError(
                            "Failed to delete user server",
                            context={'user_id': user_id, 'guild_id': guild.id},
                            original=e
                        )

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while updating user servers",
                context={'user_id': user_id, 'guild_id': guild.id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while updating user servers",
                context={'user_id': user_id, 'guild_id': guild.id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while updating user servers",
                context={'user_id': user_id, 'guild_id': guild.id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error updating user servers",
                context={'user_id': user_id, 'guild_id': guild.id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error updating user servers",
                    context={'user_id': user_id, 'guild_id': guild.id},
                    original=e
                )
            raise

    async def daily_channel_sync_task(self):
        """Run daily channel sync at 10:35 UTC every day"""
        # ✅ Remove decorator - the internal function has rate limiting now

        # Add print immediately (like working functions)
        print(f"\n{'='*60}")
        print(
            f"🔄 Daily channel sync triggered at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"{'='*60}")

        if not self.db_connected or not self.pool:
            print("⚠️ Database not ready - waiting 30 seconds...")
            await asyncio.sleep(30)
            if not self.db_connected or not self.pool:
                print("❌ Database still not ready - aborting sync")
                return
            print("✅ Database ready, continuing sync")

        try:
            await self.sync_all_guilds_channels_sharded()
            print(f"✅ Daily channel sync completed")
        except Exception as e:
            print(f"❌ Error in daily channel sync: {e}")
            import traceback
            traceback.print_exc()

    async def sync_user_servers_on_ready(self):
        """When bot starts, sync all servers for all logged-in users."""
        # ✅ Remove decorator - we'll add internal rate limiting

        if not self.pool:
            return

        try:
            async with self.pool.acquire() as conn:
                try:
                    logged_in_users = await conn.fetch("SELECT discord_id FROM users")
                except asyncpg.exceptions.PostgresError as e:
                    raise DatabaseQueryError(
                        "Failed to fetch logged-in users",
                        context={'operation': 'sync_user_servers_on_ready'},
                        original=e
                    )

                if not logged_in_users:
                    return

                for record in logged_in_users:
                    user_id = int(record['discord_id'])
                    user_servers = []

                    for guild in self.bot.guilds:
                        # ✅ Rate limit before checking each guild
                        if not await self.rate_limiter.acquire(RateLimitType.API, timeout=30.0):
                            print(
                                f"  ⚠️ Rate limited for user {user_id}, waiting...")
                            await asyncio.sleep(5)
                            continue

                        member = guild.get_member(user_id)
                        if member:
                            user_servers.append({
                                'guild_id': str(guild.id),
                                'guild_name': guild.name,
                                'guild_icon': guild.icon.key if guild.icon else None,
                                'member_count': guild.member_count
                            })
                        await asyncio.sleep(0.05)  # Small delay between guilds

                    try:
                        await conn.execute("""
                            DELETE FROM user_servers WHERE discord_id = $1
                        """, str(user_id))
                    except asyncpg.exceptions.PostgresError as e:
                        raise DatabaseQueryError(
                            "Failed to clear user servers",
                            context={'user_id': user_id},
                            original=e
                        )

                    for server in user_servers:
                        try:
                            await conn.execute("""
                                INSERT INTO user_servers (discord_id, guild_id, guild_name, guild_icon, member_count)
                                VALUES ($1, $2, $3, $4, $5)
                            """,
                                               str(user_id),
                                               server['guild_id'],
                                               server['guild_name'],
                                               server['guild_icon'],
                                               server['member_count']
                                               )
                        except asyncpg.exceptions.PostgresError as e:
                            raise DatabaseQueryError(
                                "Failed to insert user server during sync",
                                context={'user_id': user_id,
                                         'guild_id': server['guild_id']},
                                original=e
                            )

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist during user server sync",
                context={'operation': 'sync_user_servers_on_ready'},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed during user server sync",
                context={'operation': 'sync_user_servers_on_ready'},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out during user server sync",
                context={'operation': 'sync_user_servers_on_ready'},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error during user server sync",
                context={'operation': 'sync_user_servers_on_ready'},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error during user server sync",
                    context={'operation': 'sync_user_servers_on_ready'},
                    original=e
                )
            raise

    async def sync_user_permissions(self):
        """Sync user roles and permissions for all authenticated users"""
        # ✅ Remove decorator - we'll add internal rate limiting

        if not self.db_connected or not self.pool:
            return

        try:
            print(f"\n{'='*60}")
            print(
                f"🔄 Starting user permission sync at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
            print(f"{'='*60}")

            async with self.pool.acquire() as conn:
                users = await conn.fetch("SELECT discord_id FROM users")

                if not users:
                    print("No users found in database")
                    return

                print(f"📊 Syncing permissions for {len(users)} users")

                for user_record in users:
                    user_id = int(user_record['discord_id'])

                    for guild in self.bot.guilds:
                        # ✅ Rate limit before each guild check
                        if not await self.rate_limiter.acquire(RateLimitType.API, timeout=30.0):
                            print(
                                f"  ⚠️ Rate limited for user {user_id} on guild {guild.name}, waiting...")
                            await asyncio.sleep(5)
                            continue

                        member = guild.get_member(user_id)
                        if not member:
                            continue

                        # Update user_servers with current member info
                        await conn.execute("""
                            UPDATE user_servers 
                            SET member_count = $1, last_updated = NOW()
                            WHERE discord_id = $2 AND guild_id = $3
                        """, guild.member_count, str(user_id), str(guild.id))

                        # Sync current role memberships
                        for role in member.roles:
                            if role.is_default():
                                continue
                            await self.redis_batch_write('role_members', {
                                'params': [guild.id, member.id, role.id, role.name, role.color.value, datetime.now(timezone.utc), member.bot]
                            })

                        await asyncio.sleep(0.05)  # Small delay between guilds

            print(
                f"✅ Permission sync completed at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
            print(f"{'='*60}\n")

        except Exception as e:
            print(f"❌ Error in permission sync: {e}")
            import traceback
            traceback.print_exc()

    async def update_guild_info_in_db(self, guild: discord.Guild):
        """Update guild information for all users in this guild."""
        if not self.pool:
            return

        try:
            async with self.pool.acquire() as conn:
                try:
                    await conn.execute("""
                        UPDATE user_servers 
                        SET guild_name = $2, guild_icon = $3, member_count = $4, last_updated = CURRENT_TIMESTAMP
                        WHERE guild_id = $1
                    """,
                                       str(guild.id),
                                       guild.name,
                                       guild.icon.key if guild.icon else None,
                                       guild.member_count
                                       )
                except asyncpg.exceptions.PostgresError as e:
                    raise DatabaseQueryError(
                        "Failed to update guild info",
                        context={'guild_id': guild.id},
                        original=e
                    )

        except asyncpg.exceptions.ConnectionDoesNotExistError as e:
            raise DatabaseConnectionError(
                "Database connection does not exist while updating guild info",
                context={'guild_id': guild.id},
                original=e
            )
        except asyncpg.exceptions.ConnectionFailureError as e:
            raise DatabaseConnectionError(
                "Database connection failed while updating guild info",
                context={'guild_id': guild.id},
                original=e
            )
        except asyncpg.exceptions.QueryCanceledError as e:
            raise DatabaseTimeoutError(
                "Database operation timed out while updating guild info",
                context={'guild_id': guild.id},
                original=e
            )
        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Database error updating guild info",
                context={'guild_id': guild.id},
                original=e
            )
        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                raise DatabaseQueryError(
                    "Unexpected error updating guild info",
                    context={'guild_id': guild.id},
                    original=e
                )
            raise

    async def _is_privacy_mode_enabled(self, user_id: int, guild_id: int) -> bool:
        """Check if a user has privacy mode enabled for a specific guild."""
        if not self.pool or not self.db_connected:
            return False

        try:
            settings_cog = self.bot.get_cog("Settings")
            if not settings_cog:
                return False

            user_settings = await settings_cog.get_user_settings(user_id, guild_id)
            return user_settings.get('privacy_enabled', False)

        except Exception as e:
            # If we can't check, assume privacy mode is NOT enabled (track normally)
            print(
                f"⚠️ Could not check privacy mode for user {user_id} in guild {guild_id}: {e}")
            return False

    # ======================================================================
    # VOICE ACTIVITY TRACKING - UNCHANGED (still uses raw table for tracking, but writes to aggregated)
    # ======================================================================

    @tasks.loop(seconds=60)
    async def voice_activity_tracker(self):
        """Track voice activity in 60-second intervals without overlapping sessions."""
        if not self.pool or not self.active_voice_sessions:
            return

        try:
            current_time = datetime.now(timezone.utc)

            async with self.voice_lock:
                sessions_copy = copy.deepcopy(self.active_voice_sessions)

            for user_id, session_data in sessions_copy.items():
                try:
                    guild_id = session_data['guild_id']

                    guild = self.bot.get_guild(guild_id)
                    if not guild:
                        async with self.voice_lock:
                            if user_id in self.active_voice_sessions:
                                del self.active_voice_sessions[user_id]
                        continue

                    member = guild.get_member(user_id)
                    if not member or not member.voice or not member.voice.channel:
                        continue

                    last_tracked = session_data.get(
                        'last_minute_tracked', session_data['join_time'])
                    seconds_since_last_track = int(
                        (current_time - last_tracked).total_seconds())

                    if seconds_since_last_track >= 60:
                        updated_session_data = {
                            'server_mute': member.voice.mute,
                            'server_deaf': member.voice.deaf,
                            'self_mute': member.voice.self_mute,
                            'self_deaf': member.voice.self_deaf,
                            'streaming': member.voice.self_stream,
                            'video': member.voice.self_video,
                            'suppressed': member.voice.suppress,
                            'channel_id': member.voice.channel.id,
                            'join_time': session_data.get('last_join_time', session_data['join_time']),
                            'guild_id': guild_id,
                            'user_id': user_id
                        }

                        if hasattr(member.voice.channel, 'category_id') and member.voice.channel.category_id:
                            updated_session_data['category_id'] = member.voice.channel.category_id

                        await self._save_voice_session(
                            guild_id=guild_id,
                            user_id=user_id,
                            member=member,
                            session_data=updated_session_data,
                            leave_time=current_time,
                            duration=60
                        )

                        async with self.voice_lock:
                            if user_id in self.active_voice_sessions:
                                self.active_voice_sessions[user_id]['last_minute_tracked'] = current_time
                                self.active_voice_sessions[user_id]['last_join_time'] = current_time
                                self.active_voice_sessions[user_id].update(
                                    updated_session_data)

                    async with self.metrics_lock:
                        self.metrics['voice_updates'] += 1

                except Exception as e:
                    # Don't raise during tracking - just continue
                    continue

        except Exception as e:
            raise DatabaseQueryError(
                "Error in voice activity tracker",
                context={'operation': 'voice_activity_tracker'},
                original=e
            )

    def _should_create_new_session(self, old_session, current_time):
        """Check if we should create a new session instead of continuing the old one."""
        if not old_session:
            return True

        time_since_last_activity = (
            current_time - old_session.get('last_activity', current_time)).total_seconds()
        return time_since_last_activity > 300

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Track voice state changes."""
        if not member.guild or self.shutting_down:
            return

        # ✅ PRIVACY MODE CHECK - Skip if user has privacy mode enabled
        if await self._is_privacy_mode_enabled(member.id, member.guild.id):
            return

        try:
            guild = member.guild
            guild_id = guild.id
            user_id = member.id

            # 👇 FIXED: Use aware datetime consistently
            current_time = datetime.now(timezone.utc)

            def ensure_channel_id(channel):
                if channel and hasattr(channel, 'id'):
                    return channel.id
                return 0

            async with self.voice_lock:
                old_session = self.active_voice_sessions.get(user_id)

            if before.channel is None and after.channel is not None:
                # User joined a voice channel
                is_afk_channel = getattr(
                    after.channel, 'afk_channel', False) if after.channel else False
                channel_id = ensure_channel_id(after.channel)
                category_id = None

                if after.channel and hasattr(after.channel, 'category_id') and after.channel.category_id:
                    category_id = after.channel.category_id

                should_continue = not self._should_create_new_session(
                    old_session, current_time) and old_session

                if should_continue and old_session:
                    async with self.voice_lock:
                        self.active_voice_sessions[user_id].update({
                            'channel_id': channel_id,
                            'category_id': category_id,
                            'server_mute': after.mute,
                            'server_deaf': after.deaf,
                            'self_mute': after.self_mute,
                            'self_deaf': after.self_deaf,
                            'streaming': after.self_stream,
                            'video': after.self_video,
                            'suppressed': after.suppress,
                            'is_afk_channel': is_afk_channel,
                            'last_activity': current_time,
                            'last_join_time': old_session.get('last_join_time', old_session['join_time'])
                        })
                else:
                    async with self.voice_lock:
                        self.active_voice_sessions[user_id] = {
                            'guild_id': guild_id,
                            'user_id': user_id,
                            'channel_id': channel_id,
                            'category_id': category_id,
                            'server_mute': after.mute,
                            'server_deaf': after.deaf,
                            'self_mute': after.self_mute,
                            'self_deaf': after.self_deaf,
                            'streaming': after.self_stream,
                            'video': after.self_video,
                            'suppressed': after.suppress,
                            'is_afk_channel': is_afk_channel,
                            'join_time': current_time,
                            'last_join_time': current_time,
                            'last_activity': current_time,
                            'last_minute_tracked': current_time,
                            'is_bot': member.bot
                        }

            elif before.channel is not None and after.channel is None:
                # User left voice channel
                async with self.voice_lock:
                    session_data = self.active_voice_sessions.pop(
                        user_id, None)

                if session_data:
                    last_join_time = session_data.get(
                        'last_join_time', session_data['join_time'])
                    duration = int(
                        (current_time - last_join_time).total_seconds())

                    if duration > 0:
                        state_flags = self._calculate_state_flags(session_data)
                        category_id = session_data.get('category_id')

                        if category_id is None and before.channel and hasattr(before.channel, 'category_id') and before.channel.category_id:
                            category_id = before.channel.category_id

                        encrypted_username = self.encrypt_username(
                            str(member)) if member else None
                        channel_id = session_data.get('channel_id')

                        if channel_id is None:
                            channel_id = ensure_channel_id(before.channel)

                        await self._save_voice_session(
                            guild_id=guild_id,
                            user_id=user_id,
                            member=member,
                            session_data=session_data,
                            leave_time=current_time,
                            duration=duration
                        )

            elif before.channel is not None and after.channel is not None and before.channel.id != after.channel.id:
                # User moved between voice channels
                async with self.voice_lock:
                    old_session_data = self.active_voice_sessions.get(user_id)

                if old_session_data:
                    last_join_time = old_session_data.get(
                        'last_join_time', old_session_data['join_time'])
                    duration = int(
                        (current_time - last_join_time).total_seconds())

                    if duration > 0:
                        await self._save_voice_session(
                            guild_id=guild_id,
                            user_id=user_id,
                            member=member,
                            session_data=old_session_data,
                            leave_time=current_time,
                            duration=duration
                        )

                # Start new session in new channel
                is_afk_channel = getattr(
                    after.channel, 'afk_channel', False) if after.channel else False
                channel_id = ensure_channel_id(after.channel)
                category_id = None

                if after.channel and hasattr(after.channel, 'category_id') and after.channel.category_id:
                    category_id = after.channel.category_id

                async with self.voice_lock:
                    self.active_voice_sessions[user_id] = {
                        'guild_id': guild_id,
                        'user_id': user_id,
                        'channel_id': channel_id,
                        'category_id': category_id,
                        'server_mute': after.mute,
                        'server_deaf': after.deaf,
                        'self_mute': after.self_mute,
                        'self_deaf': after.self_deaf,
                        'streaming': after.self_stream,
                        'video': after.self_video,
                        'suppressed': after.suppress,
                        'is_afk_channel': is_afk_channel,
                        'join_time': current_time,
                        'last_join_time': current_time,
                        'last_activity': current_time,
                        'last_minute_tracked': current_time,
                        'is_bot': member.bot
                    }

        except Exception as e:
            raise DatabaseQueryError(
                "Error in voice state update",
                context={'guild_id': member.guild.id, 'user_id': member.id},
                original=e
            )

    # ======================================================================
    # SLASH COMMAND TRACKING - UNCHANGED (still uses raw table for tracking, but writes to daily aggregated)
    # ======================================================================

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Track slash command usage."""
        if not interaction.guild or self.shutting_down:
            return

        if interaction.type != discord.InteractionType.application_command:
            return

        # ✅ PRIVACY MODE CHECK - Skip if user has privacy mode enabled
        if await self._is_privacy_mode_enabled(interaction.user.id, interaction.guild.id):
            return

        if not await self.check_rate_limit(interaction.user.id, 'slash_command', limit=50, window=30):
            return

        try:
            command_name = interaction.data.get('name', 'unknown')

            if interaction.data.get('options'):
                for option in interaction.data['options']:
                    if option.get('type') == 1:
                        command_name += f" {option['name']}"
                        break

            current_time = datetime.now(timezone.utc)

            category_id = None
            if hasattr(interaction.channel, 'category_id') and interaction.channel.category_id:
                category_id = interaction.channel.category_id

            encrypted_username = self.encrypt_username(str(interaction.user))

            params = [
                interaction.guild.id,
                interaction.user.id,
                command_name,
                interaction.channel.id,
                category_id,
                current_time,
                encrypted_username,
                interaction.user.bot
            ]

            await self.redis_batch_write('slash_commands', {
                'params': params,
                'source': 'slash_command_tracking',
                'timestamp': time.time()
            })

            async with self.metrics_lock:
                self.metrics['slash_command_inserts'] += 1

        except Exception as e:
            raise DatabaseQueryError(
                "Error tracking slash command",
                context={'guild_id': interaction.guild.id,
                         'user_id': interaction.user.id},
                original=e
            )

    # ======================================================================
    # ROLE GROWTH TRACKING - UNCHANGED (still uses raw table for tracking, but writes to hourly aggregated)
    # ======================================================================

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Track role changes for both history and current memberships."""
        if not before.guild or self.shutting_down:
            return

        # ✅ PRIVACY MODE CHECK - Skip if user has privacy mode enabled
        if await self._is_privacy_mode_enabled(before.id, before.guild.id):
            return

        try:
            blacklists = await self._get_cached_blacklists(before.guild.id)

            if before.id in blacklists['users']:
                return

            user_role_ids = {role.id for role in before.roles}
            if user_role_ids.intersection(blacklists['roles']):
                return

            # Only process if roles actually changed
            if before.roles != after.roles:
                added_roles = set(after.roles) - set(before.roles)
                removed_roles = set(before.roles) - set(after.roles)

                # 👇 INVALIDATE ROLE CACHE
                cache_key_prefix = f"role_members:{before.guild.id}:"
                keys_to_delete = []
                for key in list(self.role_members_cache.keys()):
                    if key.startswith(cache_key_prefix):
                        keys_to_delete.append(key)
                for key in keys_to_delete:
                    del self.role_members_cache[key]

                current_time = datetime.now(timezone.utc)
                encrypted_username = self.encrypt_username(str(after))
                is_bot = after.bot

                # Track historical role growth (writes to role_growth_hourly via batch)
                for role in added_roles:
                    if role.is_default():
                        continue
                    if role.id in blacklists['roles']:
                        continue

                    await self.redis_batch_write('role_growth', {
                        'params': [
                            before.guild.id,
                            role.id,
                            before.id,
                            'added',
                            current_time,
                            encrypted_username,
                            is_bot
                        ]
                    })

                for role in removed_roles:
                    if role.is_default():
                        continue
                    if role.id in blacklists['roles']:
                        continue

                    await self.redis_batch_write('role_growth', {
                        'params': [
                            before.guild.id,
                            role.id,
                            before.id,
                            'removed',
                            current_time,
                            encrypted_username,
                            is_bot
                        ]
                    })

                # Track current role memberships (current_role_members table - static)
                for role in added_roles:
                    if role.is_default() or role.id in blacklists['roles']:
                        continue

                    await self.redis_batch_write('role_members', {
                        'params': [
                            before.guild.id,
                            before.id,
                            role.id,
                            role.name,              # ADDED: role name
                            role.color.value,       # ADDED: role color
                            current_time,
                            is_bot
                        ]
                    })

                for role in removed_roles:
                    if role.is_default() or role.id in blacklists['roles']:
                        continue

                    await self.redis_batch_write('role_members', {
                        'params': [
                            before.guild.id,
                            before.id,
                            role.id,
                            role.name,              # ADDED: role name
                            role.color.value,       # ADDED: role color
                            current_time,
                            is_bot,
                            'DELETE'
                        ]
                    })

                async with self.metrics_lock:
                    self.metrics['role_growth_inserts'] += len(
                        added_roles) + len(removed_roles)
                    self.metrics['role_members_updates'] = self.metrics.get(
                        'role_members_updates', 0) + len(added_roles) + len(removed_roles)

        except Exception as e:
            raise DatabaseQueryError(
                "Error tracking role changes",
                context={'guild_id': before.guild.id, 'user_id': before.id},
                original=e
            )

    # ======================================================================
    # MESSAGE TRACKING - UNCHANGED (still uses raw table for tracking, but writes to hourly aggregated)
    # ======================================================================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Track message content and emojis."""
        if not message.guild or self.shutting_down:
            return

        # ✅ EXCLUDE WEBHOOKS - Check if message is from a webhook
        if message.webhook_id is not None:
            return

        # ✅ PRIVACY MODE CHECK - Skip if user has privacy mode enabled
        if await self._is_privacy_mode_enabled(message.author.id, message.guild.id):
            return

        if not await self.check_rate_limit(message.author.id, 'message', limit=30, window=10):
            return

        try:
            message_key = f"msg_{message.id}"
            current_time = datetime.now(timezone.utc)

            if message_key in self.processed_messages:
                time_since = (
                    current_time - self.processed_messages[message_key]).total_seconds()
                if time_since < 0.1:
                    return

            self.processed_messages[message_key] = current_time

            cleanup_time = current_time - timedelta(hours=1)
            old_keys = [k for k, v in self.processed_messages.items()
                        if v < cleanup_time]
            for key in old_keys:
                del self.processed_messages[key]

            await self._track_message_emojis(message)
            await self._track_message_content(message)

        except Exception as e:
            raise DatabaseQueryError(
                "Error tracking message",
                context={'guild_id': message.guild.id,
                         'message_id': message.id},
                original=e
            )

    # ======================================================================
    # EMOJI AND MENTION TRACKING - UNCHANGED (still uses raw table for tracking, but writes to hourly aggregated)
    # ======================================================================

    def _extract_all_emojis_from_content(self, content: str) -> List[Dict[str, Any]]:
        """Extract all emojis from message content."""
        if not content:
            return []

        all_emojis = []

        custom_pattern = r'<a?:\w{2,32}:\d{18,22}>'

        for match in re.finditer(custom_pattern, content):
            emoji_str = match.group()
            all_emojis.append({
                'emoji_str': emoji_str,
                'is_custom': True,
                'is_animated': emoji_str.startswith('<a:'),
                'start_pos': match.start(),
                'end_pos': match.end()
            })

        custom_positions = set()
        for emoji in all_emojis:
            for pos in range(emoji['start_pos'], emoji['end_pos']):
                custom_positions.add(pos)

        i = 0
        while i < len(content):
            if i in custom_positions:
                i += 1
                continue

            char = content[i]

            if is_emoji(char):
                emoji_end = i
                sequence = char

                while emoji_end + 1 < len(content):
                    next_char = content[emoji_end + 1]

                    if (is_emoji(sequence + next_char) or
                            unicodedata.category(next_char).startswith('M')):
                        emoji_end += 1
                        sequence += next_char
                    else:
                        break

                all_emojis.append({
                    'emoji_str': sequence,
                    'is_custom': False,
                    'is_animated': False,
                    'start_pos': i,
                    'end_pos': emoji_end + 1
                })

                for pos in range(i, emoji_end + 1):
                    custom_positions.add(pos)

                i = emoji_end + 1
            else:
                i += 1

        all_emojis.sort(key=lambda x: x['start_pos'])

        return all_emojis

    async def track_message_emojis(self, message: discord.Message):
        """Public method to track message emojis."""
        await self._track_message_emojis(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        """Track emojis in edited messages."""
        if not after.guild or self.shutting_down:
            return

        # ✅ EXCLUDE WEBHOOKS - Check if message is from a webhook
        if after.webhook_id is not None:
            return

        # ✅ PRIVACY MODE CHECK - Skip if user has privacy mode enabled
        if await self._is_privacy_mode_enabled(after.author.id, after.guild.id):
            return

        if not await self.check_rate_limit(after.author.id, 'message_edit', limit=20, window=10):
            return

        try:
            if before.content == after.content:
                return

            edit_key = f"edit_{after.id}"
            current_time = datetime.now(timezone.utc)

            if edit_key in self.processed_messages:
                time_since = (
                    current_time - self.processed_messages[edit_key]).total_seconds()
                if time_since < 0.1:
                    return

            self.processed_messages[edit_key] = current_time

            await self._track_message_emojis(after)

        except Exception as e:
            raise DatabaseQueryError(
                "Error tracking message edit",
                context={'guild_id': after.guild.id, 'message_id': after.id},
                original=e
            )

    async def _track_message_content(self, message: discord.Message):
        """Track message content and mentions (writes to aggregated tables via batch)."""
        try:
            # ✅ EXCLUDE WEBHOOKS - Double-check before processing
            if message.webhook_id is not None:
                return

            guild_id = message.guild.id
            user_id = message.author.id
            channel_id = message.channel.id

            category_id = None
            if hasattr(message.channel, 'category_id') and message.channel.category_id:
                category_id = message.channel.category_id

            encrypted_username = self.encrypt_username(str(message.author))
            created_at = message.created_at.astimezone(timezone.utc)

            await self.redis_batch_write('messages', {
                'params': [
                    guild_id, user_id, channel_id, category_id, message.id,
                    encrypted_username, len(message.content),
                    json.dumps([user.id for user in message.mentions]),
                    len(message.attachments) > 0,
                    len(message.embeds) > 0,
                    created_at, message.author.bot
                ]
            })

            for user in message.mentions:
                if user.id == user_id:
                    continue

                if not await self.check_rate_limit(user_id, 'mention', limit=50, window=30):
                    continue

                # Encrypt BOTH usernames
                encrypted_mentioner_username = self.encrypt_username(
                    str(message.author))
                encrypted_mentioned_username = self.encrypt_username(str(user))

                await self.redis_batch_write('mentions', {
                    'params': [
                        guild_id,
                        user.id,                      # mentioned_user_id
                        user_id,                      # mentioner_user_id
                        channel_id,
                        category_id,
                        message.id,
                        created_at,
                        encrypted_mentioner_username,  # mentioner's username
                        message.author.bot,
                        encrypted_mentioned_username  # mentioned user's username
                    ]
                })

            async with self.metrics_lock:
                self.metrics['message_inserts'] += 1
                self.metrics['mention_inserts'] += len(message.mentions)

        except Exception as e:
            raise DatabaseQueryError(
                "Error tracking message content",
                context={'guild_id': message.guild.id,
                         'message_id': message.id},
                original=e
            )

    def _is_single_emoji(self, text: str) -> bool:
        """Check if text is a single emoji."""
        if not text:
            return False

        cleaned = ''.join(
            c for c in text if not unicodedata.category(c).startswith('M'))
        return is_emoji(cleaned) and len(cleaned) == 1

    def _extract_custom_emojis(self, content: str) -> List[str]:
        """Extract custom emojis from content."""
        pattern = r'<a?:\w{2,32}:\d{18,22}>'
        return re.findall(pattern, content)

    def _extract_unicode_emojis(self, content: str) -> List[str]:
        """Extract unicode emojis from content."""
        emojis = []
        i = 0

        while i < len(content):
            char = content[i]

            if is_emoji(char):
                emoji_end = i
                while emoji_end < len(content) and (
                    is_emoji(content[i:emoji_end+1]) or
                    unicodedata.category(content[emoji_end]).startswith('M')
                ):
                    emoji_end += 1

                emoji_text = content[i:emoji_end]
                emojis.append(emoji_text)
                i = emoji_end
            else:
                i += 1

        return emojis

    async def _track_message_emojis(self, message: discord.Message):
        """Track emojis in a message (writes to aggregated tables via batch)."""
        # ✅ EXCLUDE WEBHOOKS
        if not message.guild or message.webhook_id is not None:
            return

        if not await self.check_rate_limit(message.author.id, 'emoji_message', limit=50, window=30):
            return

        content = message.content.strip()
        if not content:
            return

        current_time = datetime.now(timezone.utc)

        category_id = None
        if hasattr(message.channel, 'category_id') and message.channel.category_id:
            category_id = message.channel.category_id

        emojis_found = self._extract_all_emojis_from_content(content)

        for emoji_data in emojis_found:
            data = {
                'guild_id': message.guild.id,
                'user_id': message.author.id,
                'emoji_str': emoji_data['emoji_str'],
                'usage_type': 'message',
                'created_at': current_time,
                'channel_id': message.channel.id,
                'category_id': category_id,
                'username': str(message.author),
                'is_custom': emoji_data['is_custom'],
                'is_animated': emoji_data.get('is_animated', False)
            }

            await self._buffer_emoji_event(message.guild.id, data)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: Union[discord.Member, discord.User]):
        """Track reaction emojis (writes to aggregated tables via batch)."""
        if self.shutting_down:
            return

        if not reaction.message.guild:
            return

        # ✅ EXCLUDE WEBHOOKS - Check if the user is a webhook (webhooks can't react, but just in case)
        if isinstance(user, discord.Webhook) or (hasattr(user, 'webhook_id') and user.webhook_id):
            return

        # ✅ PRIVACY MODE CHECK - Skip if user has privacy mode enabled
        if await self._is_privacy_mode_enabled(user.id, reaction.message.guild.id):
            return

        if not await self.check_rate_limit(user.id, 'reaction', limit=40, window=10):
            return

        try:
            emoji = reaction.emoji
            current_time = datetime.now(timezone.utc)

            if isinstance(emoji, discord.Emoji):
                emoji_str = f"<{'a' if emoji.animated else ''}:{emoji.name}:{emoji.id}>"
                is_custom = True
                is_animated = emoji.animated
            else:
                emoji_str = str(emoji)
                is_custom = False
                is_animated = False

            if not is_custom and not is_emoji(emoji_str):
                return

            category_id = None
            if hasattr(reaction.message.channel, 'category_id') and reaction.message.channel.category_id:
                category_id = reaction.message.channel.category_id

            data = {
                'guild_id': reaction.message.guild.id,
                'user_id': user.id,
                'emoji_str': emoji_str,
                'usage_type': 'reaction',
                'created_at': current_time,
                'channel_id': reaction.message.channel.id,
                'category_id': category_id,
                'username': str(user),
                'is_custom': is_custom,
                'is_animated': is_animated
            }

            await self._buffer_emoji_event(reaction.message.guild.id, data)

        except Exception as e:
            raise DatabaseQueryError(
                "Error tracking reaction add",
                context={'guild_id': reaction.message.guild.id,
                         'user_id': user.id},
                original=e
            )

    async def _buffer_emoji_event(self, guild_id: int, data: Dict[str, Any]):
        """Buffer an emoji event for batch processing (writes to aggregated tables)."""
        try:
            guild = self.bot.get_guild(guild_id)
            member = guild.get_member(data['user_id']) if guild else None
            is_bot = member.bot if member else False

            encrypted_username = self.encrypt_username(data['username'])

            params = [
                data['guild_id'],
                data['user_id'],
                data['channel_id'],
                data.get('category_id'),
                encrypted_username,
                data['emoji_str'],
                data['is_custom'],
                1,
                data['created_at'],
                data['usage_type'],
                is_bot
            ]

            await self.redis_batch_write('emojis', {
                'params': params,
                'source': 'emoji_tracking',
                'timestamp': time.time()
            })

            async with self.metrics_lock:
                self.metrics['emoji_inserts'] += 1

        except Exception as e:
            raise DatabaseQueryError(
                "Error buffering emoji event",
                context={'guild_id': guild_id, 'user_id': data.get('user_id')},
                original=e
            )

    # ======================================================================
    # INVITE & GROWTH LISTENING EVENTS - UNCHANGED (still uses raw tables for tracking, static tables unchanged)
    # ======================================================================

    def _get_member_count(self, guild: discord.Guild) -> int:
        """Get total member count for a guild."""
        if not guild:
            return 0
        return guild.member_count or len(guild.members)

    async def _take_invite_snapshot(self, guild: discord.Guild) -> dict:
        """Take a complete snapshot of all invites."""
        snapshot = {
            'timestamp': datetime.now(timezone.utc),
            'regular_invites': {},
            'vanity_info': None,
            'member_count': guild.member_count
        }

        try:
            # Get all regular invites
            invites = await guild.invites()

            print(
                f"📸 Took snapshot for {guild.name}: Found {len(invites)} invites")

            for invite in invites:

                snapshot['regular_invites'][invite.code] = {
                    'code': invite.code,
                    'uses': invite.uses,
                    'inviter_id': invite.inviter.id if invite.inviter else 0,  # ← Make sure this is set!
                    'max_uses': invite.max_uses,
                    'max_age': invite.max_age,
                    'created_at': invite.created_at,
                    'is_vanity': False
                }

            # Get vanity invite info
            if guild.vanity_url_code:
                vanity_invite = await guild.vanity_invite()
                if vanity_invite:
                    snapshot['vanity_info'] = {
                        'code': vanity_invite.code,
                        'uses': None,
                        'inviter_id': guild.owner.id if guild.owner else 0,
                        'url': guild.vanity_url,
                        'is_vanity': True
                    }

        except discord.Forbidden:
            print(f"⚠️ No permission to fetch invites for {guild.name}")
        except discord.HTTPException as e:
            print(
                f"⚠️ HTTP error fetching invites for {guild.name}: {e.status}")
            raise
        except Exception as e:
            print(f"Error taking snapshot for {guild.id}: {e}")
            raise

        return snapshot

    def _get_invite_lock(self, guild_id: int) -> asyncio.Lock:
        """Get or create a per-guild invite lock."""
        if guild_id not in self.invite_snapshot_locks:
            self.invite_snapshot_locks[guild_id] = asyncio.Lock()
        return self.invite_snapshot_locks[guild_id]

    def _get_invite_snapshot(self, guild_id: int) -> Optional[dict]:
        """Get the cached invite snapshot for a guild."""
        return self.invite_snapshots.get(guild_id)

    def _set_invite_snapshot(self, guild_id: int, snapshot: dict):
        """Store the cached invite snapshot for a guild."""
        self.invite_snapshots[guild_id] = snapshot

    def _clear_invite_snapshot(self, guild_id: int):
        """Remove the cached invite snapshot for a guild."""
        self.invite_snapshots.pop(guild_id, None)

    async def _find_used_invite_by_comparison(self, guild: discord.Guild,
                                              before: dict, after: dict):
        """Find which invite was used by comparing snapshots."""

        # Check regular invites that still exist and have increased usage
        for code, after_invite in after['regular_invites'].items():
            before_invite = before['regular_invites'].get(code)
            if before_invite and after_invite['uses'] is not None:

                if after_invite['uses'] > before_invite['uses']:
                    return {
                        'code': code,
                        'inviter_id': after_invite['inviter_id'],
                        'uses': after_invite['uses'],
                        'is_vanity': False,
                        'uncertain': False
                    }

        # Check invites that existed before but are now gone
        for code, before_invite in before['regular_invites'].items():
            if code not in after['regular_invites']:
                return {
                    'code': code,
                    'inviter_id': before_invite['inviter_id'],
                    'uses': before_invite.get('uses', 0) + 1,
                    'is_vanity': False,
                    'uncertain': False
                }

        print(f"  ❌ No invite found!")
        return None

    async def _get_min_account_age(self, guild_id: int) -> int:
        """Get minimum account age requirement in days for a guild."""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow('''
                    SELECT min_account_age_days
                    FROM settings
                    WHERE guild_id = $1
                ''', guild_id)

                if row and row['min_account_age_days'] is not None:
                    return row['min_account_age_days']
        except Exception:
            pass

        return 3  # Default to 3 days

    async def _is_suspicious_account(self, member: discord.Member, inviter: Optional[discord.Member], min_age_days: int) -> bool:
        """Check if either the member or inviter account is too new."""
        current_time = datetime.now(timezone.utc)

        # Convert days to seconds
        min_age_seconds = min_age_days * 24 * 60 * 60

        # Check member's account age - use ensure_aware
        member_created = ensure_aware(member.created_at)
        member_age = current_time - member_created
        if member_age.total_seconds() < min_age_seconds:
            return True

        # Check inviter's account age if exists
        if inviter:
            inviter_created = ensure_aware(inviter.created_at)
            inviter_age = current_time - inviter_created
            if inviter_age.total_seconds() < min_age_seconds:
                return True

        return False

    async def _increment_invite_usage(self, guild_id: int, invite_code: str):
        """Increment usage count for a regular invite."""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO invite_uses (guild_id, invite_code, uses, updated_at)
                    VALUES ($1, $2, 1, NOW())
                    ON CONFLICT (guild_id, invite_code) DO UPDATE
                    SET uses = invite_uses.uses + 1,
                        updated_at = NOW()
                """, guild_id, invite_code)
        except Exception as e:
            print(f"Error incrementing invite usage: {e}")

    async def _increment_vanity_usage(self, guild_id: int, invite_code: str):
        """Increment usage count for a vanity invite."""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO invite_uses (guild_id, invite_code, uses, is_vanity, updated_at)
                    VALUES ($1, $2, 1, TRUE, NOW())
                    ON CONFLICT (guild_id, invite_code) DO UPDATE
                    SET uses = invite_uses.uses + 1,
                        updated_at = NOW()
                """, guild_id, invite_code)
        except Exception as e:
            print(f"Error incrementing vanity usage: {e}")

    async def _increment_invite_leave_count(self, guild_id: int, invite_code: str, is_vanity: bool = False):
        """Increment leave count for an invite."""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE invite_uses 
                    SET leaves = COALESCE(leaves, 0) + 1,
                        updated_at = NOW()
                    WHERE guild_id = $1 AND invite_code = $2
                """, guild_id, invite_code)
        except Exception as e:
            print(f"Error incrementing leave count: {e}")

    async def _update_invite_in_database(self, guild_id: int, invite_code: str, uses: int, inviter_id: int):
        """Update or insert invite information in the invite_uses table."""
        try:
            async with self.pool.acquire() as conn:
                # Check if invite already exists
                existing = await conn.fetchrow('''
                    SELECT id FROM invite_uses 
                    WHERE guild_id = $1 AND invite_code = $2
                ''', guild_id, invite_code)

                if existing:
                    # Update existing invite
                    await conn.execute('''
                        UPDATE invite_uses 
                        SET uses = $3, 
                            inviter_id = $4,
                            updated_at = NOW(),
                            deleted = FALSE
                        WHERE guild_id = $1 AND invite_code = $2
                    ''', guild_id, invite_code, uses, inviter_id)
                else:
                    # Insert new invite
                    await conn.execute('''
                        INSERT INTO invite_uses (guild_id, invite_code, uses, inviter_id, created_at, updated_at)
                        VALUES ($1, $2, $3, $4, NOW(), NOW())
                    ''', guild_id, invite_code, uses, inviter_id)

        except asyncpg.exceptions.PostgresError as e:
            raise DatabaseQueryError(
                "Failed to update invite in database",
                context={'guild_id': guild_id, 'invite_code': invite_code},
                original=e
            )
        except Exception as e:
            print(
                f"Error updating invite {invite_code} in guild {guild_id}: {e}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Track member joins and invites."""
        if self.shutting_down:
            return

        # ✅ PRIVACY MODE CHECK - Skip if user has privacy mode enabled
        if await self._is_privacy_mode_enabled(member.id, member.guild.id):
            return

        try:
            await self.update_user_servers_in_db(member.id, member.guild, "add")

            blacklists = await self._get_cached_blacklists(member.guild.id)

            if member.id in blacklists['users']:
                return

            user_role_ids = {role.id for role in member.roles}
            if user_role_ids.intersection(blacklists['roles']):
                return

            current_time = datetime.now(timezone.utc)
            encrypted_username = self.encrypt_username(str(member))
            member_count = self._get_member_count(member.guild)

            await self.redis_batch_write('member_joins', {
                'params': [
                    member.guild.id,
                    member.id,
                    current_time,
                    encrypted_username,
                    member.bot,
                    member_count
                ]
            })

            async with self.metrics_lock:
                self.metrics['member_join_inserts'] = self.metrics.get(
                    'member_join_inserts', 0) + 1

            invite_lock = self._get_invite_lock(member.guild.id)
            async with invite_lock:
                previous_snapshot = self._get_invite_snapshot(member.guild.id)

                if previous_snapshot is None:
                    # No baseline - bot restarted or first ever join in this guild.
                    # Take a snapshot for future joins but we can't determine this invite.
                    fresh_snapshot = await self._take_invite_snapshot(member.guild)
                    self._set_invite_snapshot(member.guild.id, fresh_snapshot)

                    await self._buffer_invite_event(
                        guild_id=member.guild.id,
                        inviter_id=0,
                        invitee_id=member.id,
                        invite_code="unknown",
                        invite_type="unknown",
                        is_vanity=False
                    )
                    return

                # Take current snapshot inside the lock so no concurrent join
                # can read or write the snapshot between our compare and update
                current_snapshot = await self._take_invite_snapshot(member.guild)
                used_invite = await self._find_used_invite_by_comparison(
                    member.guild, previous_snapshot, current_snapshot
                )

                # Update snapshot immediately after comparison, still inside lock
                self._set_invite_snapshot(member.guild.id, current_snapshot)

            # Everything below is safe to run concurrently
            is_vanity = used_invite.get(
                'is_vanity', False) if used_invite else False
            is_uncertain = used_invite.get(
                'uncertain', False) if used_invite else False

            min_age_days = await self._get_min_account_age(member.guild.id)

            inviter = None
            if used_invite and used_invite.get('inviter_id', 0) != 0:
                inviter = member.guild.get_member(used_invite['inviter_id'])

            is_suspicious = await self._is_suspicious_account(member, inviter, min_age_days)

            if used_invite is None:
                invite_type = "unknown"
                invite_code = "unknown"
                inviter_id = 0
                is_vanity = False
            elif is_uncertain:
                # Guessed vanity because nothing else matched - safer to mark unknown
                invite_type = "unknown"
                invite_code = "unknown"
                inviter_id = 0
                is_vanity = False
            elif is_vanity:
                invite_type = "vanity"
                invite_code = used_invite['code']
                inviter_id = used_invite['inviter_id']
            elif is_suspicious:
                invite_type = "suspicious"
                invite_code = used_invite['code']
                inviter_id = used_invite['inviter_id']
            else:
                invite_type = "valid"
                invite_code = used_invite['code']
                inviter_id = used_invite['inviter_id']

            await self._buffer_invite_event(
                guild_id=member.guild.id,
                inviter_id=inviter_id,
                invitee_id=member.id,
                invite_code=invite_code,
                invite_type=invite_type,
                is_vanity=is_vanity
            )

            if used_invite and not is_uncertain:
                if is_vanity:
                    await self._increment_vanity_usage(member.guild.id, invite_code)
                else:
                    await self._increment_invite_usage(member.guild.id, invite_code)

        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                print(f"Error tracking member join for {member.guild.id}: {e}")
                import traceback
                traceback.print_exc()

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Track member leaves - creates 'left' event with original invite code."""
        if self.shutting_down:
            return

        # ✅ PRIVACY MODE CHECK - Skip if user has privacy mode enabled
        if await self._is_privacy_mode_enabled(member.id, member.guild.id):
            return

        try:
            await self.update_user_servers_in_db(member.id, member.guild, "remove")

            blacklists = await self._get_cached_blacklists(member.guild.id)

            if member.id in blacklists['users']:
                return

            user_role_ids = {role.id for role in member.roles}
            if user_role_ids.intersection(blacklists['roles']):
                return

            current_time = datetime.now(timezone.utc)
            encrypted_username = self.encrypt_username(str(member))
            member_count = self._get_member_count(member.guild)

            # Track leave event in member_leaves_hourly
            await self.redis_batch_write('member_leaves', {
                'params': [
                    member.guild.id,
                    member.id,
                    current_time,
                    encrypted_username,
                    member.bot,
                    member_count
                ]
            })

            async with self.metrics_lock:
                self.metrics['member_leave_inserts'] = self.metrics.get(
                    'member_leave_inserts', 0) + 1

            # Get the original invite they used to join
            if self.pool:
                try:
                    async with self.pool.acquire() as conn:
                        row = await conn.fetchrow('''
                            SELECT inviter_id, invite_code, invite_type, is_vanity
                            FROM invite_tracking
                            WHERE guild_id = $1 AND invitee_id = $2
                            ORDER BY created_at DESC
                            LIMIT 1
                        ''', member.guild.id, member.id)

                        if row:
                            # ✅ FIXED: Use the original invite_code, not "left"
                            await self._buffer_invite_event(
                                guild_id=member.guild.id,
                                inviter_id=row['inviter_id'],
                                invitee_id=member.id,
                                # ← FIXED: Use actual code
                                invite_code=row['invite_code'],
                                invite_type="left",
                                is_vanity=row['is_vanity']
                            )

                            # Increment leave count for that invite
                            await self._increment_invite_leave_count(
                                member.guild.id,
                                row['invite_code'],
                                row['is_vanity']
                            )
                        else:
                            # No original invite found - track as unknown left
                            await self._buffer_invite_event(
                                guild_id=member.guild.id,
                                inviter_id=0,
                                invitee_id=member.id,
                                invite_code="unknown",
                                invite_type="left",
                                is_vanity=False
                            )
                except Exception as e:
                    print(
                        f"Error getting original invite for {member.id}: {e}")

        except Exception as e:
            if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
                print(
                    f"Error tracking member leave for {member.guild.id}: {e}")
                import traceback
                traceback.print_exc()

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        """Track invite creation - updates invite_uses table and refreshes snapshot."""
        if self.shutting_down:
            return

        try:
            guild_id = invite.guild.id
            inviter_id = invite.inviter.id if invite.inviter else 0

            if invite.uses is not None:
                await self._update_invite_in_database(
                    guild_id=guild_id,
                    invite_code=invite.code,
                    uses=invite.uses,
                    inviter_id=inviter_id
                )

            invite_lock = self._get_invite_lock(guild_id)
            async with invite_lock:
                snapshot = await self._take_invite_snapshot(invite.guild)
                self._set_invite_snapshot(guild_id, snapshot)

        except Exception as e:
            print(
                f"Error tracking invite creation for guild {invite.guild.id}: {e}")
            import traceback
            traceback.print_exc()

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        """Track invite deletion and update snapshot."""
        if self.shutting_down:
            return

        try:
            guild_id = invite.guild.id

            if self.pool:
                try:
                    async with self.pool.acquire() as conn:
                        await conn.execute("""
                            UPDATE invite_uses 
                            SET deleted = true, updated_at = NOW()
                            WHERE guild_id = $1 AND invite_code = $2
                        """, guild_id, invite.code)
                except Exception as e:
                    print(f"Error marking invite as deleted: {e}")

            invite_lock = self._get_invite_lock(guild_id)
            async with invite_lock:
                snapshot = await self._take_invite_snapshot(invite.guild)
                self._set_invite_snapshot(guild_id, snapshot)

        except Exception as e:
            print(
                f"Error processing invite deletion for guild {invite.guild.id}: {e}")
            import traceback
            traceback.print_exc()

    async def _buffer_invite_event(self, guild_id: int, inviter_id: int,
                                   invitee_id: Optional[int], invite_code: str,
                                   invite_type: str, is_vanity: bool = False):
        """Buffer an invite event for batch processing."""
        if invitee_id is None:
            return

        try:
            current_time = datetime.now(timezone.utc)

            is_bot = False
            encrypted_username = None  # Initialize

            if inviter_id and inviter_id != 0:
                guild = self.bot.get_guild(guild_id)
                if guild:
                    inviter = guild.get_member(inviter_id)
                    if inviter:
                        is_bot = inviter.bot
                        encrypted_username = self.encrypt_username(
                            str(inviter))  # ✅ Add this
            else:
                # If no inviter, try to get invitee info
                guild = self.bot.get_guild(guild_id)
                if guild:
                    invitee = guild.get_member(invitee_id)
                    if invitee:
                        encrypted_username = self.encrypt_username(
                            str(invitee))

            params = [
                guild_id,           # 0
                inviter_id,         # 1
                invitee_id,         # 2
                invite_code,        # 3
                invite_type,        # 4
                current_time,       # 5
                is_bot,             # 6
                is_vanity,          # 7
                encrypted_username  # 8 ✅ ADD THIS
            ]

            await self.redis_batch_write('invites', {'params': params})

            async with self.metrics_lock:
                self.metrics['invite_inserts'] += 1

        except Exception as e:
            print(f"Error buffering invite event: {e}")

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        """Clean up invite lock and snapshot when bot leaves a guild."""
        guild_id = guild.id

        self._clear_invite_snapshot(guild_id)

        lock = self.invite_snapshot_locks.get(guild_id)
        if lock is not None and not lock.locked():
            del self.invite_snapshot_locks[guild_id]

    @commands.Cog.listener()
    async def on_ready(self):
        """Pre-populate invite snapshots for all guilds on startup with rate limiting."""
        # Wait for the bot to fully cache - reduced from 60 to 10 seconds
        await asyncio.sleep(10)

        print(
            f"📋 Taking invite snapshots for {len(self.bot.guilds)} guilds...")

        success = 0
        failed = 0
        rate_limited = 0

        # Process guilds in batches to respect rate limits
        batch_size = 5  # Process 5 guilds at a time
        guild_list = list(self.bot.guilds)

        for i in range(0, len(guild_list), batch_size):
            batch = guild_list[i:i + batch_size]

            # Process batch concurrently but with rate limiting
            tasks = []
            for guild in batch:
                tasks.append(self._safe_take_snapshot(guild))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for guild, result in zip(batch, results):
                if isinstance(result, Exception):
                    if isinstance(result, discord.HTTPException) and result.status == 429:
                        rate_limited += 1
                        print(f"⚠️ Rate limited for {guild.name} ({guild.id})")
                    else:
                        failed += 1
                        print(
                            f"❌ Could not take invite snapshot for {guild.name} ({guild.id}): {result}")
                else:
                    self._set_invite_snapshot(guild.id, result)
                    success += 1

            # Add delay between batches to respect rate limits
            if i + batch_size < len(guild_list):
                await asyncio.sleep(1)  # 1 second between batches

        print(
            f"✅ Invite snapshots complete — {success} succeeded, {failed} failed, {rate_limited} rate limited")

    # But the method doesn't exist. Add it:

    async def _safe_take_snapshot(self, guild: discord.Guild) -> dict:
        """Safely take a snapshot with proper error handling for rate limits."""
        try:
            return await self._take_invite_snapshot(guild)
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = e.retry_after if hasattr(e, 'retry_after') else 5
                print(
                    f"⏳ Rate limited for {guild.name}, retrying in {retry_after}s")
                await asyncio.sleep(min(retry_after, 10))
                return await self._take_invite_snapshot(guild)
            raise

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """Bot joined a new guild - sync everything"""
        try:
            # =========================================================
            # STEP 0: SEND WELCOME MESSAGE (Rate Limited)
            # =========================================================
            try:
                # Acquire rate limit for welcome message
                if await self.rate_limiter.acquire(RateLimitType.MESSAGE, timeout=10.0):
                    # Find a suitable channel to send the message
                    welcome_channel = None

                    # Try to find a general/system channel first
                    if guild.system_channel:
                        welcome_channel = guild.system_channel
                    else:
                        # Look for common channel names
                        for channel in guild.text_channels:
                            channel_name_lower = channel.name.lower()
                            if any(name in channel_name_lower for name in ['general', 'welcome', 'chat', 'main']):
                                welcome_channel = channel
                                break

                        # If no suitable channel found, use the first available text channel
                        if not welcome_channel and guild.text_channels:
                            welcome_channel = guild.text_channels[0]

                    if welcome_channel:
                        # Create the welcome embed
                        embed = discord.Embed(
                            title="Thanks for adding Stats!",
                            color=discord.Color.from_rgb(
                                170, 0, 255)  # RGB: 170, 0, 255
                        )

                        # Set Up section
                        embed.add_field(
                            name="🔧 **Set Up**",
                            value="Stats requires ZERO setup. All tracking immediately starts upon the bot's join as long as it has the correct permissions, you can view the required permissions [here](https://statshq.xyz/docs/?page=setup). Stats does NOT have access to ANY data from before its join date.",
                            inline=False
                        )

                        # Commands section
                        embed.add_field(
                            name="📝 **Commands**",
                            value="Get the full list of commands with a short explanation to each [here](https://statshq.xyz/Commands/)",
                            inline=False
                        )

                        # Dashboard section
                        embed.add_field(
                            name="📊 **Dashboard**",
                            value="Use our simple yet powerful dashboard to view all your statistics in one place at the same time [here](https://statshq.xyz/Dashboard/Messages/)",
                            inline=False
                        )

                        # Support section
                        embed.add_field(
                            name="💬 **Support**",
                            value="For any other issues you might face, use our help command or join our [discord server](https://discord.gg/hreJvck8cK)",
                            inline=False
                        )

                        # Add footer
                        embed.set_footer(
                            text="StatsHQ")

                        await welcome_channel.send(embed=embed)
                        print(
                            f"📨 Sent welcome message to {guild.name} in #{welcome_channel.name}")
                    else:
                        print(
                            f"⚠️ Could not find a suitable channel to send welcome message in {guild.name}")
                else:
                    print(
                        f"⚠️ Rate limit timeout for welcome message on guild: {guild.name}")
            except discord.Forbidden:
                print(
                    f"❌ Missing permissions to send welcome message in {guild.name}")
            except Exception as e:
                print(
                    f"⚠️ Could not send welcome message to {guild.name}: {e}")

            # Sync commands first
            await self.bot.tree.sync(guild=guild)
            print(f"🏠 Synced commands to new guild: {guild.name}")

            if not self.pool:
                print(f"⚠️ No database pool available for guild: {guild.name}")
                return

            # =========================================================
            # STEP 1: TAKE INITIAL INVITE SNAPSHOT (Rate Limited)
            # =========================================================
            try:
                # Acquire rate limit for invite snapshot (uses Discord API calls)
                if await self.rate_limiter.acquire(RateLimitType.SYNCING, timeout=30.0):
                    db_cog = self.bot.get_cog("DatabaseStats")
                    if db_cog and hasattr(db_cog, '_take_invite_snapshot') and hasattr(db_cog, '_set_invite_snapshot'):
                        snapshot = await db_cog._take_invite_snapshot(guild)
                        db_cog._set_invite_snapshot(guild.id, snapshot)
                        print(
                            f"📸 Took initial invite snapshot for {guild.name}")
                    else:
                        print(
                            f"⚠️ DatabaseStats cog not available for invite snapshot")
                else:
                    print(
                        f"⚠️ Rate limit timeout for invite snapshot on guild: {guild.name}")
            except Exception as e:
                print(
                    f"⚠️ Could not take initial invite snapshot for {guild.name}: {e}")

            # =========================================================
            # STEP 2: TAKE INITIAL MEMBER COUNT SNAPSHOT (Rate Limited)
            # =========================================================
            try:
                # Acquire rate limit for member count snapshot (database write)
                if await self.rate_limiter.acquire(RateLimitType.SYNCING, timeout=30.0):
                    now = datetime.now(timezone.utc)
                    member_count = guild.member_count or len(guild.members)
                    async with self.pool.acquire() as conn:
                        await conn.execute("""
                            INSERT INTO server_member_counts (guild_id, recorded_at, member_count)
                            VALUES ($1, $2, $3)
                            ON CONFLICT (guild_id, recorded_at) DO NOTHING
                        """, guild.id, now, member_count)
                    print(
                        f"📊 Recorded initial member count ({member_count}) for {guild.name}")
                else:
                    print(
                        f"⚠️ Rate limit timeout for member count snapshot on guild: {guild.name}")
            except Exception as e:
                print(
                    f"⚠️ Could not record initial member count for {guild.name}: {e}")

            # =========================================================
            # STEP 3: SYNC CHANNELS AND CATEGORIES (Rate Limited)
            # =========================================================
            channels_synced = 0
            try:
                # Acquire rate limit for channel sync (uses API calls)
                if await self.rate_limiter.acquire(RateLimitType.SYNCING, timeout=30.0):
                    channels_synced = await self.sync_guild_channels(guild)
                    print(
                        f"📡 Synced {channels_synced} channels/categories for guild: {guild.name}")
                else:
                    print(
                        f"⚠️ Rate limit timeout for channel sync on guild: {guild.name}")
            except Exception as e:
                print(f"❌ Failed to sync channels for {guild.name}: {e}")

            # =========================================================
            # STEP 4: ADD GUILD SETTINGS (No rate limit - DB only)
            # =========================================================
            try:
                async with self.pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO settings (guild_id)
                        VALUES ($1)
                        ON CONFLICT (guild_id) DO NOTHING
                    """, guild.id)
                    print(f"⚙️ Added settings for guild: {guild.name}")
            except Exception as e:
                print(f"❌ Failed to add settings for {guild.name}: {e}")

            # =========================================================
            # STEP 5: GET WEBSITE USERS (Rate Limited - DB queries)
            # =========================================================
            member_ids = [str(member.id)
                          for member in guild.members if not member.bot]
            website_users = []

            if member_ids:
                try:
                    # Acquire rate limit for database query (COUNTERS type - DB reads)
                    if await self.rate_limiter.acquire(RateLimitType.SYNCING, timeout=30.0):
                        async with self.pool.acquire() as conn:
                            website_users = await conn.fetch("""
                                SELECT discord_id FROM users 
                                WHERE discord_id = ANY($1::text[])
                            """, member_ids)
                    else:
                        print(
                            f"⚠️ Rate limit timeout for fetching website users on guild: {guild.name}")
                except Exception as e:
                    print(f"❌ Failed to fetch website users: {e}")

            # =========================================================
            # STEP 6: SYNC PERMISSIONS FOR WEBSITE USERS (Rate Limited)
            # =========================================================
            if website_users:
                permission_synced_count = 0
                for user_record in website_users:
                    user_id = int(user_record['discord_id'])
                    member = guild.get_member(user_id)

                    if not member:
                        continue

                    try:
                        # Acquire rate limit for each user sync (API calls to Discord)
                        if not await self.rate_limiter.acquire(RateLimitType.API, timeout=10.0):
                            print(
                                f"⚠️ Rate limit timeout for user {user_id} sync")
                            continue

                        # Update user_servers
                        async with self.pool.acquire() as conn:
                            await conn.execute("""
                                UPDATE user_servers 
                                SET member_count = $1, last_updated = NOW()
                                WHERE discord_id = $2 AND guild_id = $3
                            """, guild.member_count, str(user_id), str(guild.id))

                        # Sync role memberships for this user
                        for role in member.roles:
                            if role.is_default():
                                continue
                            await self.redis_batch_write('role_members', {
                                'params': [guild.id, member.id, role.id, role.name, role.color.value,
                                           datetime.now(timezone.utc), member.bot]
                            })

                        permission_synced_count += 1

                        if permission_synced_count % 10 == 0:
                            await asyncio.sleep(0.1)

                    except Exception as e:
                        print(
                            f"⚠️ Failed to sync permissions for user {user_id}: {e}")

                print(
                    f"👤 Synced permissions for {permission_synced_count} website users")

            # =========================================================
            # STEP 7: SYNC ALL ROLE MEMBERSHIPS (FULL GUILD)
            # =========================================================
            try:
                await self._sync_guild_role_memberships(guild)
                print(f"👥 Synced role memberships for guild: {guild.name}")
            except Exception as e:
                print(f"❌ Failed to sync role memberships: {e}")

            # =========================================================
            # STEP 8: SCAN ACTIVE VOICE SESSIONS
            # =========================================================
            try:
                voice_sessions_found = await self.scan_guild_voice_sessions(guild)
                print(
                    f"🎙️ Scanned voice sessions: {voice_sessions_found} active")
            except Exception as e:
                print(f"❌ Failed to scan voice sessions: {e}")

            # =========================================================
            # STEP 9: SCAN ACTIVE ACTIVITY SESSIONS (if ActivityTracker exists)
            # =========================================================
            activity_cog = self.bot.get_cog("ActivityTracker")
            if activity_cog:
                try:
                    activity_sessions_found = await activity_cog.scan_guild_activities(guild)
                    print(
                        f"🎮 Scanned activity sessions: {activity_sessions_found} active")
                except Exception as e:
                    print(f"❌ Failed to scan activity sessions: {e}")

            # =========================================================
            # STEP 10: BATCH INSERT WEBSITE USERS INTO USER_SERVERS (Rate Limited)
            # =========================================================
            if website_users:
                try:
                    # Acquire rate limit for batch database operation
                    if await self.rate_limiter.acquire(RateLimitType.SYNCING, timeout=30.0):
                        values = []
                        for user_record in website_users:
                            user_id = user_record['discord_id']
                            values.append((
                                user_id,
                                str(guild.id),
                                guild.name,
                                guild.icon.key if guild.icon else None,
                                guild.member_count
                            ))

                        async with self.pool.acquire() as conn:
                            await conn.executemany("""
                                INSERT INTO user_servers (discord_id, guild_id, guild_name, guild_icon, member_count)
                                VALUES ($1, $2, $3, $4, $5)
                                ON CONFLICT (discord_id, guild_id) 
                                DO UPDATE SET 
                                    guild_name = EXCLUDED.guild_name,
                                    guild_icon = EXCLUDED.guild_icon,
                                    member_count = EXCLUDED.member_count,
                                    last_updated = CURRENT_TIMESTAMP
                            """, values)

                        print(
                            f"📝 Added/updated {len(website_users)} website users")
                    else:
                        print(
                            f"⚠️ Rate limit timeout for batch insert on guild: {guild.name}")
                except Exception as e:
                    print(f"❌ Failed to batch insert user_servers: {e}")

            # =========================================================
            # SUMMARY
            # =========================================================
            print(f"\n✅ Guild setup complete for: {guild.name}")
            print(f"   - Invite snapshot: taken")
            print(f"   - Member count snapshot: taken")
            print(f"   - Channels synced: {channels_synced}")
            print(f"   - Role memberships synced")
            print(
                f"   - Voice sessions scanned: {voice_sessions_found if 'voice_sessions_found' in locals() else 'N/A'}")
            print(f"   - Website users processed: {len(website_users)}")
            print("=" * 60)

        except Exception as e:
            print(f"❌ Failed guild setup for {guild.name}: {e}")
            import traceback
            traceback.print_exc()

    # ======================================================================
    # METRICS - UNCHANGED
    # ======================================================================

    async def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics."""
        async with self.metrics_lock:
            metrics_copy = self.metrics.copy()

        async with self.voice_lock:
            active_sessions = len(self.active_voice_sessions)

        metrics_copy.update({
            'db_connected': self.db_connected,
            'redis_connected': self.redis_connected,
            'active_voice_sessions': active_sessions,
            'is_timescale_initialized': self.is_timescale_initialized,
            'redis_batch_stats': {
                'last_flush_time': self.last_flush_time,
                'batch_sizes': self.batch_sizes.copy()
            }
        })

        return metrics_copy

    # ======================================================================
    # RATE LIMITING - UNCHANGED
    # ======================================================================

    async def check_rate_limit(self, identifier: int, action: str, limit: int = 100000000000, window: int = 60) -> bool:
        """Check if an action is rate limited."""
        current = datetime.now(timezone.utc)
        key = f"{identifier}:{action}"

        if key not in self.rate_limits:
            self.rate_limits[key] = []

        self.rate_limits[key] = [
            ts for ts in self.rate_limits[key]
            if (current - ts).total_seconds() < window
        ]

        if len(self.rate_limits[key]) >= limit:
            return False

        self.rate_limits[key].append(current)
        return True


# ======================================================================
# SETUP - FIXED EXCEPTION HANDLING
# ======================================================================

async def setup(bot: commands.Bot):
    """Setup function to add the cog to the bot."""
    try:
        cog = DatabaseStats(bot)
        await bot.add_cog(cog)

        if bot.is_ready():
            cog.init_pools.start()

        return cog

    except asyncpg.exceptions.ConnectionDoesNotExistError as e:
        raise DatabaseConnectionError(
            "Database connection does not exist while loading DatabaseStats cog",
            context={'operation': 'setup'},
            original=e
        )
    except asyncpg.exceptions.ConnectionFailureError as e:
        raise DatabaseConnectionError(
            "Database connection failed while loading DatabaseStats cog",
            context={'operation': 'setup'},
            original=e
        )
    except asyncpg.exceptions.QueryCanceledError as e:
        raise DatabaseTimeoutError(
            "Database operation timed out while loading DatabaseStats cog",
            context={'operation': 'setup'},
            original=e
        )
    except asyncpg.exceptions.PostgresError as e:
        raise DatabaseQueryError(
            "Database error while loading DatabaseStats cog",
            context={'operation': 'setup'},
            original=e
        )
    except Exception as e:
        if not isinstance(e, (DatabaseConnectionError, DatabaseTimeoutError, DatabaseQueryError)):
            raise DatabaseConnectionError(
                "Failed to load DatabaseStats cog",
                context={'operation': 'setup'},
                original=e
            )
        raise
