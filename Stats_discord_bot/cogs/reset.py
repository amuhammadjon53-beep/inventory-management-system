import discord
from discord import app_commands
from discord.ui import View, Select, Button, Modal, TextInput
from discord.ext import commands
from typing import Optional, Literal
import asyncpg
import os
from dotenv import load_dotenv
import logging
import traceback
from pathlib import Path
from .ratelimiter import RateLimiter, RateLimitType, rate_limited, get_rate_limiter

# CONFIGURATION

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent


class DatabaseManager:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def ensure_tables_exist(self, guild_id: int):
        """Check if required tables exist."""
        async with self.pool.acquire() as conn:
            tables = await conn.fetch("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            table_names = [t['table_name'] for t in tables]

            required_tables = [
                'message_tracking_hourly',
                'voice_session_history_hourly',
                'emoji_usage_hourly',
                'user_mentions_hourly',
                'invite_tracking',
                'activity_sessions_hourly',
                'daily_activity_log',
                'activity_streaks',
                'role_growth_hourly',
                'member_joins_hourly',
                'member_leaves_hourly'
            ]

            missing_tables = [
                t for t in required_tables if t not in table_names]
            if missing_tables:
                logger.warning(f"Missing tables: {missing_tables}")
                return False
            return True

    # ======================================================================
    # SERVER DELETION LOGIC
    # ======================================================================

    async def delete_server_all(self, guild_id: int,
                                channel_id: Optional[int] = None,
                                category_id: Optional[int] = None):

        try:

            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    conditions = ["guild_id = $1"]
                    params = [guild_id]
                    param_counter = 2

                    if channel_id:
                        conditions.append(f"channel_id = ${param_counter}")
                        params.append(channel_id)
                        param_counter += 1

                    if category_id:
                        conditions.append(f"category_id = ${param_counter}")
                        params.append(category_id)
                        param_counter += 1

                    where_clause = " AND ".join(conditions)

                    # Tables that can be filtered by channel/category
                    tables_with_channel_category = [
                        'message_tracking_hourly',
                        'voice_session_history_hourly',
                        'emoji_usage_hourly',
                        'user_mentions_hourly'
                    ]

                    deleted_counts = {}

                    for table in tables_with_channel_category:
                        try:
                            result = await conn.execute(f"DELETE FROM {table} WHERE {where_clause}", *params)
                            deleted_counts[table] = result.split()[-1]
                        except Exception as e:
                            logger.warning(f"Error deleting from {table}: {e}")
                            deleted_counts[table] = "0 (error)"

                    # Delete from tables that don't have channel/category columns (server-wide only)
                    if not channel_id and not category_id:
                        server_tables = [
                            'invite_tracking',
                            'activity_sessions_hourly',
                            'daily_activity_log',
                            'activity_streaks',
                            'role_growth_hourly',
                            'member_joins_hourly',
                            'member_leaves_hourly'
                        ]

                        for table in server_tables:
                            try:
                                result = await conn.execute(f"DELETE FROM {table} WHERE guild_id = $1", guild_id)
                                deleted_counts[table] = result.split()[-1]
                            except Exception as e:
                                logger.warning(
                                    f"Error deleting from {table}: {e}")
                                deleted_counts[table] = "0 (error)"

                    return deleted_counts

        except Exception as e:
            logger.error(f"Error in delete_server_all: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_server_messages(self, guild_id: int,
                                     channel_id: Optional[int] = None,
                                     category_id: Optional[int] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    conditions = ["guild_id = $1"]
                    params = [guild_id]
                    param_counter = 2

                    if channel_id:
                        conditions.append(f"channel_id = ${param_counter}")
                        params.append(channel_id)
                        param_counter += 1

                    if category_id:
                        conditions.append(f"category_id = ${param_counter}")
                        params.append(category_id)
                        param_counter += 1

                    where_clause = " AND ".join(conditions)
                    result = await conn.execute(f"DELETE FROM message_tracking_hourly WHERE {where_clause}", *params)
                    deleted_count = result.split()[-1]
                    return int(deleted_count) if deleted_count.isdigit() else 0

        except Exception as e:
            logger.error(f"Error in delete_server_messages: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_server_voice(self, guild_id: int,
                                  channel_id: Optional[int] = None,
                                  category_id: Optional[int] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    conditions = ["guild_id = $1"]
                    params = [guild_id]
                    param_counter = 2

                    if channel_id:
                        conditions.append(f"channel_id = ${param_counter}")
                        params.append(channel_id)
                        param_counter += 1

                    if category_id:
                        conditions.append(f"category_id = ${param_counter}")
                        params.append(category_id)
                        param_counter += 1

                    where_clause = " AND ".join(conditions)

                    deleted_counts = {}
                    result1 = await conn.execute(f"DELETE FROM voice_session_history_hourly WHERE {where_clause}", *params)
                    deleted_counts['voice_session_history_hourly'] = result1.split(
                    )[-1]
                    return deleted_counts

        except Exception as e:
            logger.error(f"Error in delete_server_voice: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_server_invites(self, guild_id: int):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    result = await conn.execute(f"DELETE FROM invite_tracking WHERE guild_id = $1", guild_id)
                    deleted_count = result.split()[-1]
                    return int(deleted_count) if deleted_count.isdigit() else 0

        except Exception as e:
            logger.error(f"Error in delete_server_invites: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_server_emoji(self, guild_id: int,
                                  channel_id: Optional[int] = None,
                                  category_id: Optional[int] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    conditions = ["guild_id = $1"]
                    params = [guild_id]
                    param_counter = 2

                    if channel_id:
                        conditions.append(f"channel_id = ${param_counter}")
                        params.append(channel_id)
                        param_counter += 1

                    if category_id:
                        conditions.append(f"category_id = ${param_counter}")
                        params.append(category_id)
                        param_counter += 1

                    where_clause = " AND ".join(conditions)
                    result = await conn.execute(f"DELETE FROM emoji_usage_hourly WHERE {where_clause}", *params)
                    deleted_count = result.split()[-1]
                    return int(deleted_count) if deleted_count.isdigit() else 0

        except Exception as e:
            logger.error(f"Error in delete_server_emoji: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_server_activity(self, guild_id: int):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    deleted_counts = {}
                    result1 = await conn.execute(f"DELETE FROM activity_sessions_hourly WHERE guild_id = $1", guild_id)
                    deleted_counts['activity_sessions_hourly'] = result1.split(
                    )[-1]
                    result2 = await conn.execute(f"DELETE FROM daily_activity_log WHERE guild_id = $1", guild_id)
                    deleted_counts['daily_activity_log'] = result2.split()[-1]
                    result3 = await conn.execute(f"DELETE FROM activity_streaks WHERE guild_id = $1", guild_id)
                    deleted_counts['activity_streaks'] = result3.split()[-1]
                    return deleted_counts

        except Exception as e:
            logger.error(f"Error in delete_server_activity: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_server_mentions(self, guild_id: int,
                                     channel_id: Optional[int] = None,
                                     category_id: Optional[int] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    conditions = ["guild_id = $1"]
                    params = [guild_id]
                    param_counter = 2

                    if channel_id:
                        conditions.append(f"channel_id = ${param_counter}")
                        params.append(channel_id)
                        param_counter += 1

                    if category_id:
                        conditions.append(f"category_id = ${param_counter}")
                        params.append(category_id)
                        param_counter += 1

                    where_clause = " AND ".join(conditions)
                    result = await conn.execute(f"DELETE FROM user_mentions_hourly WHERE {where_clause}", *params)
                    deleted_count = result.split()[-1]
                    return int(deleted_count) if deleted_count.isdigit() else 0

        except Exception as e:
            logger.error(f"Error in delete_server_mentions: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_server_role_growth(self, guild_id: int):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    result = await conn.execute(f"DELETE FROM role_growth_hourly WHERE guild_id = $1", guild_id)
                    deleted_count = result.split()[-1]
                    return int(deleted_count) if deleted_count.isdigit() else 0

        except Exception as e:
            logger.error(f"Error in delete_server_role_growth: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_server_member_growth(self, guild_id: int):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    deleted_counts = {}
                    result1 = await conn.execute(f"DELETE FROM member_joins_hourly WHERE guild_id = $1", guild_id)
                    deleted_counts['member_joins_hourly'] = result1.split()[-1]
                    result2 = await conn.execute(f"DELETE FROM member_leaves_hourly WHERE guild_id = $1", guild_id)
                    deleted_counts['member_leaves_hourly'] = result2.split()[-1]
                    return deleted_counts

        except Exception as e:
            logger.error(f"Error in delete_server_member_growth: {e}")
            logger.error(traceback.format_exc())
            raise

    # ======================================================================
    # USER DELETION LOGIC
    # ======================================================================

    async def delete_user_all(self, guild_id: int, user_id: int,
                              channel_id: Optional[int] = None,
                              category_id: Optional[int] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    conditions = ["guild_id = $1", "user_id = $2"]
                    params = [guild_id, user_id]
                    param_counter = 3

                    if channel_id:
                        conditions.append(f"channel_id = ${param_counter}")
                        params.append(channel_id)
                        param_counter += 1

                    if category_id:
                        conditions.append(f"category_id = ${param_counter}")
                        params.append(category_id)
                        param_counter += 1

                    where_clause = " AND ".join(conditions)

                    deleted_counts = {}

                    # Tables with user_id column that can be filtered by channel/category
                    tables_with_user_and_channel = [
                        'message_tracking_hourly',
                        'voice_session_history_hourly',
                        'emoji_usage_hourly'
                    ]

                    for table in tables_with_user_and_channel:
                        try:
                            result = await conn.execute(f"DELETE FROM {table} WHERE {where_clause}", *params)
                            deleted_counts[table] = result.split()[-1]
                        except Exception as e:
                            logger.warning(f"Error deleting from {table}: {e}")
                            deleted_counts[table] = "0 (error)"

                    # Tables with mentioner/mentioned relationships
                    mention_conditions = [
                        "guild_id = $1", "(mentioned_user_id = $2 OR mentioner_user_id = $2)"]
                    mention_params = [guild_id, user_id]
                    mention_counter = 3

                    if channel_id:
                        mention_conditions.append(
                            f"channel_id = ${mention_counter}")
                        mention_params.append(channel_id)
                        mention_counter += 1

                    if category_id:
                        mention_conditions.append(
                            f"category_id = ${mention_counter}")
                        mention_params.append(category_id)
                        mention_counter += 1

                    mention_where = " AND ".join(mention_conditions)
                    result = await conn.execute(f"DELETE FROM user_mentions_hourly WHERE {mention_where}", *mention_params)
                    deleted_counts['user_mentions_hourly'] = result.split()[-1]

                    # Tables that only have user_id (server-wide only)
                    if not channel_id and not category_id:
                        # Role growth (server-wide only)
                        result = await conn.execute(f"DELETE FROM role_growth_hourly WHERE guild_id = $1 AND user_id = $2",
                                                    guild_id, user_id)
                        deleted_counts['role_growth_hourly'] = result.split(
                        )[-1]

                        # Invite tracking
                        result = await conn.execute(f"""
                            DELETE FROM invite_tracking 
                            WHERE guild_id = $1 AND (inviter_id = $2 OR invitee_id = $2)
                        """, guild_id, user_id)
                        deleted_counts['invite_tracking'] = result.split()[-1]

                        # Activity tracking (server-wide only)
                        result1 = await conn.execute(f"DELETE FROM activity_sessions_hourly WHERE guild_id = $1 AND user_id = $2",
                                                     guild_id, user_id)
                        deleted_counts['activity_sessions_hourly'] = result1.split(
                        )[-1]

                        result2 = await conn.execute(f"DELETE FROM daily_activity_log WHERE guild_id = $1 AND user_id = $2",
                                                     guild_id, user_id)
                        deleted_counts['daily_activity_log'] = result2.split(
                        )[-1]

                        result3 = await conn.execute(f"DELETE FROM activity_streaks WHERE guild_id = $1 AND user_id = $2",
                                                     guild_id, user_id)
                        deleted_counts['activity_streaks'] = result3.split()[-1]

                        # Member joins/leaves (server-wide only)
                        result4 = await conn.execute(f"DELETE FROM member_joins_hourly WHERE guild_id = $1 AND user_id = $2",
                                                     guild_id, user_id)
                        deleted_counts['member_joins_hourly'] = result4.split(
                        )[-1]

                        result5 = await conn.execute(f"DELETE FROM member_leaves_hourly WHERE guild_id = $1 AND user_id = $2",
                                                     guild_id, user_id)
                        deleted_counts['member_leaves_hourly'] = result5.split(
                        )[-1]

                    return deleted_counts

        except Exception as e:
            logger.error(f"Error in delete_user_all: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_user_messages(self, guild_id: int, user_id: int,
                                   channel_id: Optional[int] = None,
                                   category_id: Optional[int] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    conditions = ["guild_id = $1", "user_id = $2"]
                    params = [guild_id, user_id]
                    param_counter = 3

                    if channel_id:
                        conditions.append(f"channel_id = ${param_counter}")
                        params.append(channel_id)
                        param_counter += 1

                    if category_id:
                        conditions.append(f"category_id = ${param_counter}")
                        params.append(category_id)
                        param_counter += 1

                    where_clause = " AND ".join(conditions)
                    result = await conn.execute(f"DELETE FROM message_tracking_hourly WHERE {where_clause}", *params)
                    deleted_count = result.split()[-1]
                    return int(deleted_count) if deleted_count.isdigit() else 0

        except Exception as e:
            logger.error(f"Error in delete_user_messages: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_user_voice(self, guild_id: int, user_id: int,
                                channel_id: Optional[int] = None,
                                category_id: Optional[int] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    conditions = ["guild_id = $1", "user_id = $2"]
                    params = [guild_id, user_id]
                    param_counter = 3

                    if channel_id:
                        conditions.append(f"channel_id = ${param_counter}")
                        params.append(channel_id)
                        param_counter += 1

                    if category_id:
                        conditions.append(f"category_id = ${param_counter}")
                        params.append(category_id)
                        param_counter += 1

                    where_clause = " AND ".join(conditions)
                    deleted_counts = {}
                    result1 = await conn.execute(f"DELETE FROM voice_session_history_hourly WHERE {where_clause}", *params)
                    deleted_counts['voice_session_history_hourly'] = result1.split(
                    )[-1]
                    return deleted_counts

        except Exception as e:
            logger.error(f"Error in delete_user_voice: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_user_invites(self, guild_id: int, user_id: int):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    result = await conn.execute(f"""
                        DELETE FROM invite_tracking 
                        WHERE guild_id = $1 AND (inviter_id = $2 OR invitee_id = $2)
                    """, guild_id, user_id)
                    deleted_count = result.split()[-1]
                    return int(deleted_count) if deleted_count.isdigit() else 0

        except Exception as e:
            logger.error(f"Error in delete_user_invites: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_user_emoji(self, guild_id: int, user_id: int,
                                channel_id: Optional[int] = None,
                                category_id: Optional[int] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    conditions = ["guild_id = $1", "user_id = $2"]
                    params = [guild_id, user_id]
                    param_counter = 3

                    if channel_id:
                        conditions.append(f"channel_id = ${param_counter}")
                        params.append(channel_id)
                        param_counter += 1

                    if category_id:
                        conditions.append(f"category_id = ${param_counter}")
                        params.append(category_id)
                        param_counter += 1

                    where_clause = " AND ".join(conditions)
                    result = await conn.execute(f"DELETE FROM emoji_usage_hourly WHERE {where_clause}", *params)
                    deleted_count = result.split()[-1]
                    return int(deleted_count) if deleted_count.isdigit() else 0

        except Exception as e:
            logger.error(f"Error in delete_user_emoji: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_user_activity(self, guild_id: int, user_id: int):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    deleted_counts = {}
                    result1 = await conn.execute(f"DELETE FROM activity_sessions_hourly WHERE guild_id = $1 AND user_id = $2",
                                                 guild_id, user_id)
                    deleted_counts['activity_sessions_hourly'] = result1.split(
                    )[-1]
                    result2 = await conn.execute(f"DELETE FROM daily_activity_log WHERE guild_id = $1 AND user_id = $2",
                                                 guild_id, user_id)
                    deleted_counts['daily_activity_log'] = result2.split()[-1]
                    result3 = await conn.execute(f"DELETE FROM activity_streaks WHERE guild_id = $1 AND user_id = $2",
                                                 guild_id, user_id)
                    deleted_counts['activity_streaks'] = result3.split()[-1]
                    return deleted_counts

        except Exception as e:
            logger.error(f"Error in delete_user_activity: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_user_mentions(self, guild_id: int, user_id: int,
                                   channel_id: Optional[int] = None,
                                   category_id: Optional[int] = None):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    conditions = [
                        "guild_id = $1", "(mentioned_user_id = $2 OR mentioner_user_id = $2)"]
                    params = [guild_id, user_id]
                    param_counter = 3

                    if channel_id:
                        conditions.append(f"channel_id = ${param_counter}")
                        params.append(channel_id)
                        param_counter += 1

                    if category_id:
                        conditions.append(f"category_id = ${param_counter}")
                        params.append(category_id)
                        param_counter += 1

                    where_clause = " AND ".join(conditions)
                    result = await conn.execute(f"DELETE FROM user_mentions_hourly WHERE {where_clause}", *params)
                    deleted_count = result.split()[-1]
                    return int(deleted_count) if deleted_count.isdigit() else 0

        except Exception as e:
            logger.error(f"Error in delete_user_mentions: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_user_role_growth(self, guild_id: int, user_id: int):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    result = await conn.execute(f"DELETE FROM role_growth_hourly WHERE guild_id = $1 AND user_id = $2",
                                                guild_id, user_id)
                    deleted_count = result.split()[-1]
                    return int(deleted_count) if deleted_count.isdigit() else 0

        except Exception as e:
            logger.error(f"Error in delete_user_role_growth: {e}")
            logger.error(traceback.format_exc())
            raise

    async def delete_user_member_growth(self, guild_id: int, user_id: int):

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    deleted_counts = {}
                    result1 = await conn.execute(f"DELETE FROM member_joins_hourly WHERE guild_id = $1 AND user_id = $2",
                                                 guild_id, user_id)
                    deleted_counts['member_joins_hourly'] = result1.split()[-1]
                    result2 = await conn.execute(f"DELETE FROM member_leaves_hourly WHERE guild_id = $1 AND user_id = $2",
                                                 guild_id, user_id)
                    deleted_counts['member_leaves_hourly'] = result2.split()[-1]
                    return deleted_counts

        except Exception as e:
            logger.error(f"Error in delete_user_member_growth: {e}")
            logger.error(traceback.format_exc())
            raise

    # ======================================================================
    # RESET METHODS
    # ======================================================================

    async def reset_server_stats(self, guild_id: int, stat_type: str,
                                 channel_id: Optional[int] = None,
                                 category_id: Optional[int] = None):

        try:
            stat_type_lower = stat_type.lower()
            result = None

            if stat_type_lower == "all":
                result = await self.delete_server_all(guild_id, channel_id, category_id)
            elif stat_type_lower == "messages":
                result = await self.delete_server_messages(guild_id, channel_id, category_id)
            elif stat_type_lower == "voice activity":
                result = await self.delete_server_voice(guild_id, channel_id, category_id)
            elif stat_type_lower == "invite tracking":
                result = await self.delete_server_invites(guild_id)
            elif stat_type_lower == "emoji stats":
                result = await self.delete_server_emoji(guild_id, channel_id, category_id)
            elif stat_type_lower == "activity":
                result = await self.delete_server_activity(guild_id)
            elif stat_type_lower == "mentions":
                result = await self.delete_server_mentions(guild_id, channel_id, category_id)
            elif stat_type_lower == "role growth":
                result = await self.delete_server_role_growth(guild_id)
            elif stat_type_lower == "member growth":
                result = await self.delete_server_member_growth(guild_id)

            return result

        except Exception as e:
            logger.error(f"Failed to reset server stats: {e}")
            logger.error(traceback.format_exc())
            raise

    async def reset_user_stats(self, guild_id: int, user_id: int, stat_type: str,
                               channel_id: Optional[int] = None,
                               category_id: Optional[int] = None):

        try:
            stat_type_lower = stat_type.lower()
            result = None

            if stat_type_lower == "all":
                result = await self.delete_user_all(guild_id, user_id, channel_id, category_id)
            elif stat_type_lower == "messages":
                result = await self.delete_user_messages(guild_id, user_id, channel_id, category_id)
            elif stat_type_lower == "voice activity":
                result = await self.delete_user_voice(guild_id, user_id, channel_id, category_id)
            elif stat_type_lower == "invite tracking":
                result = await self.delete_user_invites(guild_id, user_id)
            elif stat_type_lower == "emoji stats":
                result = await self.delete_user_emoji(guild_id, user_id, channel_id, category_id)
            elif stat_type_lower == "activity":
                result = await self.delete_user_activity(guild_id, user_id)
            elif stat_type_lower == "mentions":
                result = await self.delete_user_mentions(guild_id, user_id, channel_id, category_id)
            elif stat_type_lower == "role growth":
                result = await self.delete_user_role_growth(guild_id, user_id)
            elif stat_type_lower == "member growth":
                result = await self.delete_user_member_growth(guild_id, user_id)

            return result

        except Exception as e:
            logger.error(f"Failed to reset user stats: {e}")
            logger.error(traceback.format_exc())
            raise


# =========================================================
# INPUT ID BUTTON
# =========================================================

class IDInputModal(Modal, title="Enter Channel/Category ID"):

    def __init__(self, scope: str, view):
        super().__init__(timeout=300)
        self.scope = scope
        self.view = view

        self.id_input = TextInput(
            label=f"Enter {scope.capitalize()} ID",
            placeholder=f"Paste the {scope} ID here...",
            max_length=30,
            required=True
        )
        self.add_item(self.id_input)

    async def on_submit(self, interaction: discord.Interaction):

        try:
            id_str = self.id_input.value.strip()
            if not id_str.isdigit():
                await interaction.response.send_message(
                    f"❌ Invalid ID! Please enter a valid numeric ID.",
                    ephemeral=True
                )
                return

            channel_id = int(id_str)

            if self.scope == "channel":
                channel = interaction.guild.get_channel(channel_id)
                if not channel or not isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
                    await interaction.response.send_message(
                        f"❌ Channel not found! Make sure the ID is correct and the channel exists in this server.",
                        ephemeral=True
                    )
                    return

                self.view.channel_id = channel_id
                self.view.selected_channel = channel

            else:
                category = discord.utils.get(
                    interaction.guild.categories, id=channel_id)
                if not category:
                    await interaction.response.send_message(
                        f"❌ Category not found! Make sure the ID is correct and the category exists in this server.",
                        ephemeral=True
                    )
                    return

                self.view.category_id = channel_id
                self.view.selected_category = category

            await interaction.response.defer()
            await self.view.show_page_3()

        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid ID format! Please enter a valid numeric ID.",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in ID input modal: {e}")
            await interaction.response.send_message(
                f"❌ An error occurred: {str(e)[:200]}",
                ephemeral=True
            )


# =========================================================
# UI COMPONENTS
# =========================================================

class ResetView(View):
    def __init__(self, interaction: discord.Interaction, db_manager: DatabaseManager,
                 command_type: Literal["server", "user"], target_user_id: Optional[int] = None):
        super().__init__(timeout=300)
        self.interaction = interaction
        self.db_manager = db_manager
        self.command_type = command_type
        self.target_user_id = target_user_id
        self.scope = None
        self.stat_type = None
        self.channel_id = None
        self.category_id = None
        self.current_page = 1
        self.selected_channel = None
        self.selected_category = None

    def create_embed(self, title: str, description: str, color: int = 0xff0000) -> discord.Embed:

        embed = discord.Embed(
            title=title,
            description=description,
            color=color
        )
        embed.set_footer(text="Stats Reset System")
        return embed

    # PAGE 1: SELECT SCOPE

    async def show_page_1(self):

        self.clear_items()
        self.current_page = 1

        if self.command_type == "server":
            title = "Reset Server Stats"
            description = "**Page 1/4**\n**Where do you want to reset statistics?**\n\nSelect from the dropdown below:"
        else:
            user_text = f"<@{self.target_user_id}>" if self.target_user_id else "your"
            title = f"Reset {user_text.capitalize()} Stats"
            description = f"**Page 1/4**\n**Where do you want to reset {user_text} statistics?**\n\nSelect from the dropdown below:"

        embed = self.create_embed(title, description)

        select = Select(
            placeholder="Select scope...",
            options=[
                discord.SelectOption(
                    label="Server", value="server", description="Reset stats for entire server"),
                discord.SelectOption(label="Channel", value="channel",
                                     description="Reset stats for a specific channel"),
                discord.SelectOption(label="Category", value="category",
                                     description="Reset stats for a specific category")
            ]
        )

        async def scope_callback(interaction: discord.Interaction):
            if interaction.user.id != self.interaction.user.id:
                await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
                return

            self.scope = select.values[0]

            if self.scope == "server":
                await interaction.response.defer()
                await self.show_page_3()
            else:
                await interaction.response.defer()
                await self.show_page_2()

        select.callback = scope_callback
        self.add_item(select)

        await self.interaction.edit_original_response(embed=embed, view=self)

    # PAGE 2: SELECT CHANNEL/CATEGORY

    async def show_page_2(self):

        self.clear_items()
        self.current_page = 2

        if self.scope == "channel":
            title = "Select Channel"
            description = "**Page 2/4**\n**Select a channel to reset statistics from:**\n\nChoose from the dropdown below **OR** click 'Input ID' to enter a channel ID manually."
            placeholder = "Choose a channel..."
            input_button_label = "📝 Input Channel ID"

            channels = [ch for ch in self.interaction.guild.channels
                        if isinstance(ch, (discord.TextChannel, discord.VoiceChannel))]

            options = []
            for channel in channels[:25]:
                channel_type = "📝" if isinstance(
                    channel, discord.TextChannel) else "🔊"
                options.append(discord.SelectOption(
                    label=f"{channel_type} {channel.name}",
                    value=str(channel.id),
                    description=f"{channel.name[:50]}"
                ))

        else:
            title = "Select Category"
            description = "**Page 2/4**\n**Select a category to reset statistics from:**\n\nChoose from the dropdown below **OR** click 'Input ID' to enter a category ID manually."
            placeholder = "Choose a category..."
            input_button_label = "📝 Input Category ID"

            categories = self.interaction.guild.categories[:25]
            options = []
            for category in categories:
                options.append(discord.SelectOption(
                    label=f"📁 {category.name}",
                    value=str(category.id),
                    description=f"{category.name[:50]}"
                ))

        if not options:
            embed = self.create_embed(
                "Error", f"No {self.scope}s found in this server!")
            await self.interaction.edit_original_response(embed=embed, view=None)
            return

        embed = self.create_embed(title, description)

        select = Select(placeholder=placeholder, options=options)

        async def selection_callback(interaction: discord.Interaction):
            if interaction.user.id != self.interaction.user.id:
                await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
                return

            selected_id = int(select.values[0])
            if self.scope == "channel":
                self.channel_id = selected_id
                self.selected_channel = interaction.guild.get_channel(
                    selected_id)
            else:
                self.category_id = selected_id
                self.selected_category = discord.utils.get(
                    interaction.guild.categories, id=selected_id)

            await interaction.response.defer()
            await self.show_page_3()

        select.callback = selection_callback
        self.add_item(select)

        input_id_button = Button(
            label=input_button_label,
            style=discord.ButtonStyle.secondary,
            emoji="🔢"
        )

        async def input_id_callback(interaction: discord.Interaction):
            if interaction.user.id != self.interaction.user.id:
                await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
                return

            modal = IDInputModal(self.scope, self)
            await interaction.response.send_modal(modal)

        input_id_button.callback = input_id_callback
        self.add_item(input_id_button)

        back_button = Button(
            label="Back", style=discord.ButtonStyle.gray, emoji="⬅️")

        async def back_callback(interaction: discord.Interaction):
            if interaction.user.id != self.interaction.user.id:
                await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
                return

            await interaction.response.defer()
            await self.show_page_1()

        back_button.callback = back_callback
        self.add_item(back_button)

        await self.interaction.edit_original_response(embed=embed, view=self)

    # PAGE 3: SELECT STAT TYPE

    async def show_page_3(self):

        self.clear_items()
        self.current_page = 3

        scope_text = ""
        if self.scope == "server":
            scope_text = "the entire server"
        elif self.scope == "channel" and self.selected_channel:
            scope_text = f"channel #{self.selected_channel.name}"
        elif self.scope == "category" and self.selected_category:
            scope_text = f"category {self.selected_category.name}"

        if self.command_type == "server":
            title = "Select Stat Type"
            description = f"**Page 3/4**\n**Which type of statistics do you want to reset from {scope_text}?**\n\nSelect from the dropdown below:"
        else:
            user_text = f"<@{self.target_user_id}>" if self.target_user_id else "your"
            title = "Select Stat Type"
            description = f"**Page 3/4**\n**Which type of {user_text} statistics do you want to reset from {scope_text}?**\n\nSelect from the dropdown below:"

        embed = self.create_embed(title, description)

        # Define options based on command type and scope
        if self.command_type == "server":
            if self.scope == "server":
                # Server-wide reset options (all tables available)
                options = [
                    discord.SelectOption(
                        label="All", value="all", description="Reset ALL statistics (irreversible!)", emoji="⚠️"),
                    discord.SelectOption(
                        label="Messages", value="messages", description="Reset message tracking", emoji="💬"),
                    discord.SelectOption(label="Voice Activity", value="voice activity",
                                         description="Reset voice session history", emoji="🔊"),
                    discord.SelectOption(label="Invite Tracking", value="invite tracking",
                                         description="Reset invite tracking", emoji="📨"),
                    discord.SelectOption(
                        label="Emoji Stats", value="emoji stats", description="Reset emoji usage", emoji="😀"),
                    discord.SelectOption(label="Activity", value="activity",
                                         description="Reset activity tracking (sessions, streaks, logs)", emoji="🎮"),
                    discord.SelectOption(
                        label="Mentions", value="mentions", description="Reset user mentions", emoji="📢"),
                    discord.SelectOption(label="Role Growth", value="role growth",
                                         description="Reset role growth tracking", emoji="👥"),
                    discord.SelectOption(label="Member Growth", value="member growth",
                                         description="Reset member join/leave tracking", emoji="📈")
                ]
            else:
                # Channel or category reset (NO role growth, NO member growth, NO activity, NO invite tracking)
                options = [
                    discord.SelectOption(
                        label="All", value="all", description="Reset ALL statistics", emoji="⚠️"),
                    discord.SelectOption(
                        label="Messages", value="messages", description="Reset message tracking", emoji="💬"),
                    discord.SelectOption(label="Voice Activity", value="voice activity",
                                         description="Reset voice activity", emoji="🔊"),
                    discord.SelectOption(
                        label="Emoji Stats", value="emoji stats", description="Reset emoji usage", emoji="😀"),
                    discord.SelectOption(
                        label="Mentions", value="mentions", description="Reset user mentions", emoji="📢")
                ]
        else:
            # Reset user stats
            if self.scope == "server":
                # User stats server-wide (all tables with user_id)
                options = [
                    discord.SelectOption(
                        label="All", value="all", description="Reset ALL statistics", emoji="⚠️"),
                    discord.SelectOption(
                        label="Messages", value="messages", description="Reset message tracking", emoji="💬"),
                    discord.SelectOption(label="Voice Activity", value="voice activity",
                                         description="Reset voice activity", emoji="🔊"),
                    discord.SelectOption(label="Activity", value="activity",
                                         description="Reset activity tracking (sessions, streaks, logs)", emoji="🎮"),
                    discord.SelectOption(label="Invite Tracking", value="invite tracking",
                                         description="Reset invite tracking", emoji="📨"),
                    discord.SelectOption(
                        label="Emoji Stats", value="emoji stats", description="Reset emoji usage", emoji="😀"),
                    discord.SelectOption(
                        label="Mentions", value="mentions", description="Reset mentions", emoji="📢"),
                    discord.SelectOption(label="Role Growth", value="role growth",
                                         description="Reset role growth tracking", emoji="👥"),
                    discord.SelectOption(label="Member Growth", value="member growth",
                                         description="Reset member join/leave tracking", emoji="📈")
                ]
            else:
                # User stats in channel/category (NO role growth, NO member growth, NO activity, NO invite tracking)
                options = [
                    discord.SelectOption(
                        label="All", value="all", description="Reset ALL statistics", emoji="⚠️"),
                    discord.SelectOption(
                        label="Messages", value="messages", description="Reset message tracking", emoji="💬"),
                    discord.SelectOption(label="Voice Activity", value="voice activity",
                                         description="Reset voice activity", emoji="🔊"),
                    discord.SelectOption(
                        label="Emoji Stats", value="emoji stats", description="Reset emoji usage", emoji="😀"),
                    discord.SelectOption(
                        label="Mentions", value="mentions", description="Reset mentions", emoji="📢")
                ]

        select = Select(placeholder="Select stat type...", options=options)

        async def stat_callback(interaction: discord.Interaction):
            if interaction.user.id != self.interaction.user.id:
                await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
                return

            self.stat_type = select.values[0]
            await interaction.response.defer()
            await self.show_page_4()

        select.callback = stat_callback
        self.add_item(select)

        back_button = Button(
            label="Back", style=discord.ButtonStyle.gray, emoji="⬅️")

        async def back_callback(interaction: discord.Interaction):
            if interaction.user.id != self.interaction.user.id:
                await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
                return

            await interaction.response.defer()
            if self.scope == "server":
                await self.show_page_1()
            else:
                await self.show_page_2()

        back_button.callback = back_callback
        self.add_item(back_button)

        await self.interaction.edit_original_response(embed=embed, view=self)

    # PAGE 4: CONFIRMATION

    async def show_page_4(self):

        self.clear_items()
        self.current_page = 4

        scope_text = ""
        if self.scope == "server":
            scope_text = "the entire server"
        elif self.scope == "channel" and self.selected_channel:
            scope_text = f"channel #{self.selected_channel.name}"
        elif self.scope == "category" and self.selected_category:
            scope_text = f"category {self.selected_category.name}"

        if self.command_type == "server":
            title = "⚠️ Confirm Server Stats Reset"
            description = f"**Page 4/4 - FINAL CONFIRMATION**\n\n**Are you sure you want to delete `{self.stat_type}` from {scope_text}?**\n\n🚨 **This action is PERMANENT and CANNOT be undone!** 🚨"
        else:
            user_text = f"<@{self.target_user_id}>" if self.target_user_id else "your"
            title = "⚠️ Confirm User Stats Reset"
            description = f"**Page 4/4 - FINAL CONFIRMATION**\n\n**Are you sure you want to delete `{self.stat_type}` for {user_text} stats from {scope_text}?**\n\n🚨 **This action is PERMANENT and CANNOT be undone!** 🚨"

        embed = self.create_embed(title, description)

        confirm_button = Button(label="✅ Confirm Reset",
                                style=discord.ButtonStyle.danger, emoji="⚠️")

        async def confirm_callback(interaction: discord.Interaction):
            if interaction.user.id != self.interaction.user.id:
                await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
                return

            for item in self.children:
                item.disabled = True

            await interaction.response.edit_message(view=self)

            processing_embed = self.create_embed(
                "🔄 Processing...",
                "Deleting statistics. This may take a moment..."
            )
            await interaction.edit_original_response(embed=processing_embed)

            try:
                if self.command_type == "server":
                    result = await self.db_manager.reset_server_stats(
                        guild_id=interaction.guild.id,
                        stat_type=self.stat_type,
                        channel_id=self.channel_id,
                        category_id=self.category_id
                    )

                    if isinstance(result, dict):
                        result_text = "\n".join(
                            [f"• {table}: {count} rows deleted" for table, count in result.items()])
                        total = sum(int(str(count).split()[0]) if str(
                            count).isdigit() else 0 for count in result.values())
                    else:
                        result_text = f"• {result} rows deleted" if isinstance(
                            result, int) else f"• {result}"
                        total = result if isinstance(result, int) else 0

                    success_embed = self.create_embed(
                        "✅ Reset Successful!",
                        f"Successfully deleted **{self.stat_type}** from **{scope_text}**!\n\n" +
                        f"✅ **Total: {total} records deleted.**"
                    )
                else:
                    target_user = self.target_user_id if self.target_user_id else interaction.user.id

                    result = await self.db_manager.reset_user_stats(
                        guild_id=interaction.guild.id,
                        user_id=target_user,
                        stat_type=self.stat_type,
                        channel_id=self.channel_id,
                        category_id=self.category_id
                    )

                    if isinstance(result, dict):
                        result_text = "\n".join(
                            [f"• {table}: {count} rows deleted" for table, count in result.items()])
                        total = sum(int(str(count).split()[0]) if str(
                            count).isdigit() else 0 for count in result.values())
                    else:
                        result_text = f"• {result} rows deleted" if isinstance(
                            result, int) else f"• {result}"
                        total = result if isinstance(result, int) else 0

                    user_text = f"<@{target_user}>" if self.target_user_id else "your"
                    success_embed = self.create_embed(
                        "✅ Reset Successful!",
                        f"Successfully deleted **{self.stat_type}** for {user_text} stats from **{scope_text}**!\n\n" +
                        f"✅ **Total: {total} records deleted.**"
                    )

                await interaction.edit_original_response(embed=success_embed, view=None)

            except Exception as e:
                logger.error(f"Reset failed: {e}")
                logger.error(traceback.format_exc())

                error_embed = self.create_embed(
                    "❌ Reset Failed!",
                    f"An error occurred while deleting statistics:\n```{str(e)[:1000]}```\n\nPlease try again or contact support."
                )
                await interaction.edit_original_response(embed=error_embed, view=None)

        confirm_button.callback = confirm_callback
        self.add_item(confirm_button)

        back_button = Button(
            label="Back", style=discord.ButtonStyle.gray, emoji="⬅️")

        async def back_callback(interaction: discord.Interaction):
            if interaction.user.id != self.interaction.user.id:
                await interaction.response.send_message("You cannot use this menu!", ephemeral=True)
                return

            await interaction.response.defer()
            await self.show_page_3()

        back_button.callback = back_callback
        self.add_item(back_button)

        await self.interaction.edit_original_response(embed=embed, view=self)


# =========================================================
# INTERNAL FUNCTION FOR BOTH COMMAND TYPES
# =========================================================
@rate_limited(RateLimitType.MESSAGE, timeout=30.0)
async def _handle_reset_command(self, ctx_or_interaction, command_type: str, target_user: Optional[discord.User] = None, is_interaction: bool = False):
    """Internal function to handle reset commands for both command types"""
    try:
        # Get context parameters
        if is_interaction:
            user = ctx_or_interaction.user
            guild = ctx_or_interaction.guild
            send_method = ctx_or_interaction.response.send_message
        else:
            user = ctx_or_interaction.author
            guild = ctx_or_interaction.guild
            send_method = ctx_or_interaction.send

        # Check database connection
        if not self.db_manager or not self.db_pool:
            if is_interaction:
                await send_method(
                    "⚠️ Database connection not ready. Please try again in a moment.\n"
                    "If this persists, contact the bot administrator.",
                    ephemeral=True
                )
            else:
                await send_method(
                    "⚠️ Database connection not ready. Please try again in a moment.\n"
                    "If this persists, contact the bot administrator.",
                    delete_after=10
                )
            return

        # Test database connection
        try:
            async with self.db_pool.acquire() as conn:
                await conn.fetchval('SELECT 1')
        except Exception as e:
            if is_interaction:
                await send_method(
                    f"❌ Database connection error: {str(e)[:200]}\n"
                    "Please contact the bot administrator.",
                    ephemeral=True
                )
            else:
                await send_method(
                    f"❌ Database connection error: {str(e)[:200]}\n"
                    "Please contact the bot administrator.",
                    delete_after=10
                )
            return

        # Check permissions
        has_permission = await self.check_reset_permissions(ctx_or_interaction if is_interaction else guild, user, command_type, target_user)
        if not has_permission:
            # Get required permission based on server settings
            settings_cog = self.bot.get_cog("Settings")
            if settings_cog:
                settings = await settings_cog.get_guild_settings(guild.id)
                permission_level = settings.get('permission_level', 'Default')

                if permission_level == "Moderator":
                    required_permission = "Manage Server"
                else:
                    required_permission = "Administrator"

                embed = discord.Embed(
                    title="❌ Permission Denied",
                    description=f"Sorry! You need the `{required_permission}` permission to access this command.",
                    color=discord.Color.red()
                )
                if is_interaction:
                    await send_method(embed=embed, ephemeral=True)
                else:
                    await send_method(embed=embed, delete_after=10)
                return
            else:
                embed = discord.Embed(
                    title="❌ Permission Denied",
                    description="Sorry! You need the `Administrator` permission to access this command.",
                    color=discord.Color.red()
                )
                if is_interaction:
                    await send_method(embed=embed, ephemeral=True)
                else:
                    await send_method(embed=embed, delete_after=10)
                return

        # For user reset command with target user
        target_user_id = None
        if command_type == "user":
            target_user_id = target_user.id if target_user else user.id

        # For prefix commands, we need to create a fake interaction
        if not is_interaction:
            # Create a message to use as the base for the view
            embed = discord.Embed(
                title=f"🔧 {'Server' if command_type == 'server' else 'User'} Stats Reset",
                description="This command allows you to reset statistics. Please follow the 4-step process.\n\n"
                "**Note:** This action is irreversible!",
                color=0xff0000
            )
            embed.set_footer(text="Stats Reset System")

            # Send initial message
            message = await send_method(embed=embed)

            # Create a fake interaction object for the view
            class FakeInteraction:
                def __init__(self, guild, user, message):
                    self.guild = guild
                    self.user = user
                    self.response = type('obj', (object,), {
                                         'edit_message': lambda **kwargs: message.edit(**kwargs)})()
                    self.edit_original_response = message.edit
                    self.original_response = lambda: message

            fake_interaction = FakeInteraction(guild, user, message)

            # Create view
            view = ResetView(fake_interaction, self.db_manager,
                             command_type, target_user_id)

            # Store session
            self.active_sessions[message.id] = {
                'guild_id': guild.id,
                'user_id': user.id,
                'target_user_id': target_user_id,
                'command_type': command_type,
                'view': view
            }

            await view.show_page_1()

        else:
            # For slash commands
            view = ResetView(ctx_or_interaction, self.db_manager,
                             command_type, target_user_id)
            embed = view.create_embed(
                f"🔧 {'Server' if command_type == 'server' else 'User'} Stats Reset",
                "This command allows you to reset statistics. Please follow the 4-step process.\n\n"
                "**Note:** This action is irreversible!"
            )
            await send_method(embed=embed, view=view, ephemeral=True)

            await view.show_page_1()

            message = await ctx_or_interaction.original_response()
            self.active_sessions[message.id] = {
                'guild_id': guild.id,
                'user_id': user.id,
                'target_user_id': target_user_id,
                'command_type': command_type,
                'view': view
            }

    except Exception as e:
        logger.error(f"Error in _handle_reset_command: {e}")
        if is_interaction:
            try:
                await ctx_or_interaction.followup.send("❌ An error occurred while setting up the reset command.", ephemeral=True)
            except:
                pass
        else:
            try:
                await ctx_or_interaction.send("❌ An error occurred while setting up the reset command.", delete_after=10)
            except:
                pass


# =========================================================
# INITIALIZATION
# =========================================================

class ResetStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_pool = None
        self.db_manager = None
        self.active_sessions = {}
        self.rate_limiter = get_rate_limiter()

    async def create_db_pool(self):

        try:
            db_host = os.getenv('DB_HOST', 'localhost')
            db_port = int(os.getenv('DB_PORT', 5432))
            db_user = os.getenv('DB_USER')
            db_password = os.getenv('DB_PASSWORD')
            db_name = os.getenv('DB_NAME')

            if not all([db_user, db_password, db_name]):
                logger.error("Missing database environment variables!")
                return False

            self.db_pool = await asyncpg.create_pool(
                host=db_host,
                port=db_port,
                user=db_user,
                password=db_password,
                database=db_name,
                min_size=1,
                max_size=10,
                command_timeout=60
            )

            async with self.db_pool.acquire() as conn:
                version = await conn.fetchval('SELECT version()')

            self.db_manager = DatabaseManager(self.db_pool)

            return True

        except Exception as e:
            logger.error(f"❌ Failed to create database pool: {e}")
            logger.error(traceback.format_exc())
            self.db_pool = None
            self.db_manager = None
            return False

    async def cog_load(self):

        success = await self.create_db_pool()
        if not success:
            logger.error("Failed to establish database connection!")

    async def cog_unload(self):

        if self.db_pool:
            await self.db_pool.close()

    # PERMISSION CHECKING METHODS

    async def check_reset_permissions(self, interaction_or_guild, user: discord.Member, command_type: str, target_user: Optional[discord.User] = None) -> bool:
        """Check if user has permission to use reset commands based on server settings"""

        # Extract guild from parameter
        if isinstance(interaction_or_guild, discord.Interaction):
            guild = interaction_or_guild.guild
        else:
            guild = interaction_or_guild

        # Users with administrator permission can always use commands
        if user.guild_permissions.administrator:
            return True

        # Get server settings
        settings_cog = self.bot.get_cog("Settings")
        if not settings_cog:
            return False

        settings = await settings_cog.get_guild_settings(guild.id)
        permission_level = settings.get('permission_level', 'Default')

        if command_type == "server":
            # Server reset command permissions
            if permission_level == "All":
                return True
            elif permission_level == "Default":
                return False  # Server reset requires admin in default
            elif permission_level == "User Restriction":
                return False  # Server reset requires admin in user restriction
            elif permission_level == "Admin":
                return False  # Server reset requires admin
            elif permission_level == "Moderator":
                return user.guild_permissions.manage_guild
            return False

        elif command_type == "user":
            # User reset command permissions
            if permission_level == "All":
                return True
            elif permission_level == "Default":
                # Can reset own stats only
                if target_user and target_user.id != user.id:
                    return False
                return True
            elif permission_level == "User Restriction":
                # Can only reset own stats
                if target_user and target_user.id != user.id:
                    return False
                return True
            elif permission_level == "Admin":
                return False  # User reset requires admin
            elif permission_level == "Moderator":
                return user.guild_permissions.manage_guild
            return False

        return False

    # =========================================================
    # PREFIX COMMAND GROUP
    # =========================================================
    @commands.group(name="reset", invoke_without_command=True)
    async def reset_group_prefix(self, ctx: commands.Context):
        """Reset statistics commands"""
        await ctx.send("Available commands:\n- `reset server` - Reset server statistics\n- `reset user [member]` - Reset user statistics\n- `rs` - Shortcut for reset server\n- `ru [member]` - Shortcut for reset user")

    # =========================================================
    # PREFIX COMMAND - RESET SERVER
    # =========================================================
    @reset_group_prefix.command(name="server")
    async def reset_server_prefix(self, ctx: commands.Context):
        """Reset server statistics via prefix command"""
        await _handle_reset_command(self, ctx, "server", is_interaction=False)

    # =========================================================
    # PREFIX COMMAND - RESET USER
    # =========================================================
    @reset_group_prefix.command(name="user")
    async def reset_user_prefix(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """Reset user statistics via prefix command"""
        await _handle_reset_command(self, ctx, "user", member, is_interaction=False)

    # =========================================================
    # SHORTCUT COMMAND - RS (RESET SERVER)
    # =========================================================
    @commands.command(name="rs")
    async def reset_server_shortcut(self, ctx: commands.Context):
        """Shortcut command for reset server - same as reset server"""
        await _handle_reset_command(self, ctx, "server", is_interaction=False)

    # =========================================================
    # SHORTCUT COMMAND - RU (RESET USER)
    # =========================================================
    @commands.command(name="ru")
    async def reset_user_shortcut(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """Shortcut command for reset user - same as reset user"""
        await _handle_reset_command(self, ctx, "user", member, is_interaction=False)

    # =========================================================
    # SLASH COMMAND GROUP
    # =========================================================
    reset_group = app_commands.Group(
        name="reset",
        description="Reset statistics commands"
    )

    # =========================================================
    # SLASH COMMAND - RESET SERVER
    # =========================================================
    @reset_group.command(name="server", description="Reset server statistics")
    async def reset_server(self, interaction: discord.Interaction):
        await _handle_reset_command(self, interaction, "server", is_interaction=True)

    # =========================================================
    # SLASH COMMAND - RESET USER
    # =========================================================
    @reset_group.command(name="user", description="Reset user statistics")
    @app_commands.describe(user="Optional: User to reset stats for")
    async def reset_user(self, interaction: discord.Interaction, user: Optional[discord.User] = None):
        await _handle_reset_command(self, interaction, "user", user, is_interaction=True)

    # ERROR HANDLING
    @reset_server.error
    async def reset_server_error(self, interaction: discord.Interaction, error):
        logger.error(f"Reset server error: {error}")
        logger.error(traceback.format_exc())
        embed = discord.Embed(
            title="❌ Error",
            description=f"An error occurred: ```{str(error)[:500]}```",
            color=0xff0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @reset_user.error
    async def reset_user_error(self, interaction: discord.Interaction, error):
        logger.error(f"Reset user error: {error}")
        logger.error(traceback.format_exc())
        embed = discord.Embed(
            title="❌ Error",
            description=f"An error occurred: ```{str(error)[:500]}```",
            color=0xff0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# =========================================================
# SETUP
# =========================================================

async def setup(bot):
    cog = ResetStats(bot)
    await bot.add_cog(cog)
