import os
import asyncpg
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Select, View, Button, Modal, TextInput
from typing import Optional, List
import asyncio
from datetime import datetime
from .ratelimiter import RateLimiter, RateLimitType, rate_limited, get_rate_limiter


# BLACKLIST VIEW

class BlacklistView(View):
    def __init__(self, cog, guild_id, initial_type="user"):
        super().__init__(timeout=120)
        self.cog = cog
        self.guild_id = guild_id
        self.initial_type = initial_type
        self.rate_limiter = get_rate_limiter()

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except:
            pass


# BLACKLIST VIEW MENU

class TypeSelect(Select):
    def __init__(self, cog, guild_id, current_type="user"):
        self.cog = cog
        self.guild_id = guild_id
        self.rate_limiter = get_rate_limiter()
        options = [
            discord.SelectOption(
                label="Users", description="Show blacklisted users", emoji="👤", value="user"),
            discord.SelectOption(
                label="Channels", description="Show blacklisted channels", emoji="📝", value="channel"),
            discord.SelectOption(
                label="Categories", description="Show blacklisted categories", emoji="📁", value="category"),
            discord.SelectOption(
                label="Roles", description="Show blacklisted roles", emoji="🎭", value="role"),
        ]

        for option in options:
            option.default = (option.value == current_type)

        super().__init__(
            placeholder=f"Type: {current_type.capitalize()}s", options=options, min_values=1, max_values=1)

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

        selected_type = self.values[0]
        blacklist_items = await self.cog.get_blacklist(self.guild_id)

        if not blacklist_items:
            embed = discord.Embed(
                title="🛑 Blacklist",
                description="This server's blacklist is currently empty.",
                color=discord.Color.red()
            )
        else:
            filtered_items = [
                item for item in blacklist_items if item['type'] == selected_type]

            if not filtered_items:
                embed = discord.Embed(
                    title=f"🛑 Blacklist - {selected_type.capitalize()}s",
                    description=f"No blacklisted {selected_type}s found.",
                    color=discord.Color.orange()
                )
            else:
                embed = await self.cog.create_blacklist_embed(interaction.guild, filtered_items, selected_type)

        view = BlacklistView(self.cog, self.guild_id, selected_type)
        view.add_item(TypeSelect(self.cog, self.guild_id, selected_type))

        try:
            await interaction.edit_original_response(embed=embed, view=view)
        except discord.NotFound:
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            print(f"Error updating blacklist view: {e}")
            await interaction.followup.send("❌ Failed to update blacklist view.", ephemeral=True)


class BlacklistIntroView(View):
    def __init__(self, cog, guild_id):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.rate_limiter = get_rate_limiter()

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except:
            pass


# BUTTONS

class AddButton(Button):
    def __init__(self):
        super().__init__(label="Add", style=discord.ButtonStyle.success, emoji="➕")
        self.rate_limiter = get_rate_limiter()

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

        # Check permission based on settings
        if not await self.view.cog.check_blacklist_permission(interaction):
            await self.view.cog.send_permission_error(interaction)
            return

        cog = interaction.client.get_cog("Blacklist")
        if cog:
            await cog.show_type_selection(interaction, "add")


class RemoveButton(Button):
    def __init__(self):
        super().__init__(label="Remove", style=discord.ButtonStyle.danger, emoji="➖")
        self.rate_limiter = get_rate_limiter()

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

        # Check permission based on settings
        if not await self.view.cog.check_blacklist_permission(interaction):
            await self.view.cog.send_permission_error(interaction)
            return

        cog = interaction.client.get_cog("Blacklist")
        if cog:
            await cog.show_type_selection(interaction, "remove")


class BlacklistTypeSelectView(View):
    def __init__(self, cog, guild_id, action):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.action = action
        self.rate_limiter = get_rate_limiter()
        self.add_item(TypeSelectionDropdown(action))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except:
            pass


# BLACKLIST MENU

class TypeSelectionDropdown(Select):
    def __init__(self, action):
        self.action = action
        self.rate_limiter = get_rate_limiter()
        options = [
            discord.SelectOption(label="User", value="user", emoji="👤"),
            discord.SelectOption(label="Channel", value="channel", emoji="📝"),
            discord.SelectOption(
                label="Category", value="category", emoji="📁"),
            discord.SelectOption(label="Role", value="role", emoji="🎭"),
        ]
        placeholder = f"Choose what to {action}..." if action == "add" else f"Choose what to {action} from blacklist..."
        super().__init__(placeholder=placeholder, options=options, min_values=1, max_values=1)

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

        # Check permission based on settings
        if not await self.view.cog.check_blacklist_permission(interaction):
            await self.view.cog.send_permission_error(interaction)
            return

        cog = interaction.client.get_cog("Blacklist")
        if cog:
            await cog.show_menu_step2(interaction, self.values[0], self.action)


class BlacklistMenuStep2(View):
    def __init__(self, cog, guild, entity_type, action, selected_ids=None):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.entity_type = entity_type
        self.action = action
        self.selected_ids = selected_ids or []
        self.rate_limiter = get_rate_limiter()

        self.add_item(TargetSelect(entity_type, guild, action))
        self.add_item(InputIdButton(entity_type, action))
        self.add_item(BackToTypeSelectionButton())
        self.add_item(NextButton(action))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except:
            pass


class TargetSelect(Select):
    def __init__(self, entity_type, guild, action):
        self.entity_type = entity_type
        self.guild = guild
        self.action = action
        self.rate_limiter = get_rate_limiter()

        options = self.get_options()

        # CRITICAL FIX: Always have at least one option
        if not options:
            options = [discord.SelectOption(
                label=f"No {entity_type}s available",
                value="none",
                description=f"This server has no {entity_type}s to select",
                emoji="⚠️"
            )]

        super().__init__(
            placeholder=f"Select {entity_type}s to {action}...",
            options=options,
            min_values=1,
            max_values=min(25, len(options)),
            disabled=len(options) == 0 or (len(options) ==
                                           1 and options[0].value == "none")
        )

    def get_options(self):
        options = []

        if self.entity_type == "user":
            for member in self.guild.members[:25]:
                options.append(discord.SelectOption(
                    label=member.display_name[:100],
                    value=str(member.id),
                    description=f"ID: {member.id}"[:100],
                    emoji="👤"
                ))

        elif self.entity_type == "channel":
            channels = [ch for ch in self.guild.text_channels if ch.permissions_for(
                self.guild.me).view_channel]
            for channel in channels[:25]:
                options.append(discord.SelectOption(
                    label=f"#{channel.name}"[:100],
                    value=str(channel.id),
                    description=f"ID: {channel.id}"[:100],
                    emoji="📝"
                ))

        elif self.entity_type == "category":
            categories = [cat for cat in self.guild.categories if cat.permissions_for(
                self.guild.me).view_channel]
            for category in categories[:25]:
                options.append(discord.SelectOption(
                    label=category.name[:100],
                    value=str(category.id),
                    description=f"ID: {category.id}"[:100],
                    emoji="📁"
                ))

        elif self.entity_type == "role":
            # FIX: Include all roles except @everyone
            roles = [role for role in self.guild.roles if role.name != "@everyone"]
            for role in roles[:25]:
                options.append(discord.SelectOption(
                    label=role.name[:100],
                    value=str(role.id),
                    description=f"ID: {role.id}"[:100],
                    emoji="🎭"
                ))

        return options

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def callback(self, interaction: discord.Interaction):
        # Handle the "none" option
        if self.values[0] == "none":
            await interaction.response.send_message(f"❌ No {self.entity_type}s available to {self.action}.", ephemeral=True)
            return

        await interaction.response.defer()

        if not await self.view.cog.check_blacklist_permission(interaction):
            await self.view.cog.send_permission_error(interaction)
            return

        cog = interaction.client.get_cog("Blacklist")
        if cog:
            if not hasattr(self.view, 'selected_ids'):
                self.view.selected_ids = []

            for value in self.values:
                if value not in self.view.selected_ids:
                    self.view.selected_ids.append(value)

            await cog.update_menu_step2(interaction, self.view)


class InputIdButton(Button):
    def __init__(self, entity_type, action):
        label = f"Input ID to {action}"
        super().__init__(label=label, style=discord.ButtonStyle.secondary, emoji="🔢")
        self.entity_type = entity_type
        self.action = action
        self.rate_limiter = get_rate_limiter()

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def callback(self, interaction: discord.Interaction):
        # Check permission based on settings
        if not await self.view.cog.check_blacklist_permission(interaction):
            await self.view.cog.send_permission_error(interaction)
            return

        modal = InputIdModal(self.entity_type, self.view, self.action)
        await interaction.response.send_modal(modal)


class InputIdModal(Modal):
    def __init__(self, entity_type, parent_view, action):
        title = f"Input {entity_type.capitalize()} ID to {action}"
        super().__init__(title=title)
        self.entity_type = entity_type
        self.parent_view = parent_view
        self.action = action
        self.rate_limiter = get_rate_limiter()

        self.id_input = TextInput(
            label=f"{entity_type.capitalize()} ID",
            placeholder="Enter the ID here...",
            max_length=20,
            required=True
        )
        self.add_item(self.id_input)

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

        # Check permission based on settings
        if not await self.parent_view.cog.check_blacklist_permission(interaction):
            await self.parent_view.cog.send_permission_error(interaction)
            return

        try:
            entity_id = int(self.id_input.value)

            cog = interaction.client.get_cog("Blacklist")
            if cog:
                target = await cog.validate_target(interaction.guild, self.entity_type, entity_id)
                if target:
                    if hasattr(self.parent_view, 'selected_ids'):
                        if str(entity_id) not in self.parent_view.selected_ids:
                            self.parent_view.selected_ids.append(
                                str(entity_id))
                    else:
                        self.parent_view.selected_ids = [str(entity_id)]

                    await cog.update_menu_step2(interaction, self.parent_view)
                else:
                    await interaction.followup.send(f"❌ {self.entity_type.capitalize()} with ID {entity_id} not found in this server.", ephemeral=True)
        except ValueError:
            await interaction.followup.send("❌ Invalid ID format. Please enter a numeric ID.", ephemeral=True)


class BackToTypeSelectionButton(Button):
    def __init__(self):
        super().__init__(label="Back", style=discord.ButtonStyle.secondary, emoji="⬅️")
        self.rate_limiter = get_rate_limiter()

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

        # Check permission based on settings
        if not await self.view.cog.check_blacklist_permission(interaction):
            await self.view.cog.send_permission_error(interaction)
            return

        cog = interaction.client.get_cog("Blacklist")
        if cog:
            await cog.show_type_selection(interaction, self.view.action, is_returning=True)


class NextButton(Button):
    def __init__(self, action):
        label = "Next"
        emoji = "➡️"
        super().__init__(label=label, style=discord.ButtonStyle.primary, emoji=emoji)
        self.action = action
        self.rate_limiter = get_rate_limiter()

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

        # Check permission based on settings
        if not await self.view.cog.check_blacklist_permission(interaction):
            await self.view.cog.send_permission_error(interaction)
            return

        cog = interaction.client.get_cog("Blacklist")
        if cog:
            if hasattr(self.view, 'selected_ids') and self.view.selected_ids:
                await cog.show_menu_step3(interaction, self.view.entity_type, self.view.selected_ids, self.action)
            else:
                await interaction.followup.send("❌ Please select at least one item before proceeding.", ephemeral=True)


class BlacklistMenuStep3(View):
    def __init__(self, cog, guild, entity_type, selected_ids, action):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.entity_type = entity_type
        self.selected_ids = selected_ids
        self.action = action
        self.rate_limiter = get_rate_limiter()

        self.add_item(ApplyButton(action))
        self.add_item(BackToStep2Button())

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except:
            pass


class ApplyButton(Button):
    def __init__(self, action):
        label = "Apply"
        emoji = "✅"
        super().__init__(label=label, style=discord.ButtonStyle.success, emoji=emoji)
        self.action = action
        self.rate_limiter = get_rate_limiter()

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

        # Check permission based on settings
        if not await self.view.cog.check_blacklist_permission(interaction):
            await self.view.cog.send_permission_error(interaction)
            return

        cog = interaction.client.get_cog("Blacklist")
        if cog:
            await cog.apply_blacklist_changes(interaction, self.view.entity_type, self.view.selected_ids, self.action)


class BackToStep2Button(Button):
    def __init__(self):
        super().__init__(label="Back", style=discord.ButtonStyle.secondary, emoji="⬅️")
        self.rate_limiter = get_rate_limiter()

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

        # Check permission based on settings
        if not await self.view.cog.check_blacklist_permission(interaction):
            await self.view.cog.send_permission_error(interaction)
            return

        cog = interaction.client.get_cog("Blacklist")
        if cog:
            await cog.show_menu_step2(interaction, self.view.entity_type, self.view.action, self.view.selected_ids, is_returning=True)


class ViewBlacklistButton(Button):
    def __init__(self):
        super().__init__(label="View Blacklist", style=discord.ButtonStyle.primary, emoji="📋")
        self.rate_limiter = get_rate_limiter()

    @rate_limited(RateLimitType.MESSAGE_WITH_HASH, timeout=30.0)
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # Get cog from interaction instead of view
        cog = interaction.client.get_cog("Blacklist")
        if not cog:
            await interaction.followup.send("❌ Blacklist cog not found.", ephemeral=True)
            return

        # Check permission based on settings
        if not await cog.check_blacklist_permission(interaction):
            await cog.send_permission_error(interaction)
            return

        await cog.send_blacklist_view(interaction)


# INITIALIZATION

class Blacklist(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = None
        self.rate_limiter = get_rate_limiter()

    async def cog_load(self):
        await self.initialize_db()

    async def initialize_db(self):
        try:
            self.db = await asyncpg.create_pool(
                host=os.getenv('DB_HOST'),
                port=int(os.getenv('DB_PORT')),
                database=os.getenv('DB_NAME'),
                user=os.getenv('DB_USER'),
                password=os.getenv('DB_PASSWORD'),
                min_size=1,
                max_size=10,
                command_timeout=60,
                # Critical for Hetzner:
                server_settings={
                    'application_name': 'statshq_bot',
                    'timezone': 'UTC'
                }
            )

            # Test the connection
            async with self.db.acquire() as conn:
                await conn.execute("SELECT 1")
                print("✅ Database connected for blacklist tables")

            await self.create_tables()

        except Exception as e:
            print(f"Database connection failed: {e}")
            self.db = None

    # TABLE INITIALIZATION

    async def create_tables(self):
        async with self.db.acquire() as conn:
            create_table_sql = """
            -- Create separate tables for each blacklist type ONLY if they don't exist
            CREATE TABLE IF NOT EXISTS blacklisted_users (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                added_by BIGINT NOT NULL DEFAULT 0,
                added_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS blacklisted_channels (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                added_by BIGINT NOT NULL DEFAULT 0,
                added_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(guild_id, channel_id)
            );

            CREATE TABLE IF NOT EXISTS blacklisted_categories (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                category_id BIGINT NOT NULL,
                added_by BIGINT NOT NULL DEFAULT 0,
                added_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(guild_id, category_id)
            );

            CREATE TABLE IF NOT EXISTS blacklisted_roles (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                role_id BIGINT NOT NULL,
                added_by BIGINT NOT NULL DEFAULT 0,
                added_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(guild_id, role_id)
            );
            """
            await conn.execute(create_table_sql)

            # ALTER existing tables to add missing columns
            alter_queries = [
                # Add added_by column if missing
                """
                ALTER TABLE blacklisted_users 
                ADD COLUMN IF NOT EXISTS added_by BIGINT NOT NULL DEFAULT 0
                """,
                """
                ALTER TABLE blacklisted_channels 
                ADD COLUMN IF NOT EXISTS added_by BIGINT NOT NULL DEFAULT 0
                """,
                """
                ALTER TABLE blacklisted_categories 
                ADD COLUMN IF NOT EXISTS added_by BIGINT NOT NULL DEFAULT 0
                """,
                """
                ALTER TABLE blacklisted_roles 
                ADD COLUMN IF NOT EXISTS added_by BIGINT NOT NULL DEFAULT 0
                """,

                # Add added_at column if missing
                """
                ALTER TABLE blacklisted_users 
                ADD COLUMN IF NOT EXISTS added_at TIMESTAMP DEFAULT NOW()
                """,
                """
                ALTER TABLE blacklisted_channels 
                ADD COLUMN IF NOT EXISTS added_at TIMESTAMP DEFAULT NOW()
                """,
                """
                ALTER TABLE blacklisted_categories 
                ADD COLUMN IF NOT EXISTS added_at TIMESTAMP DEFAULT NOW()
                """,
                """
                ALTER TABLE blacklisted_roles 
                ADD COLUMN IF NOT EXISTS added_at TIMESTAMP DEFAULT NOW()
                """
            ]

            for query in alter_queries:
                try:
                    await conn.execute(query)
                except Exception as e:
                    # Column might already exist, that's fine
                    print(f"Alter query result: {e}")

            # INDEXES
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_blacklisted_users_guild ON blacklisted_users(guild_id);
                CREATE INDEX IF NOT EXISTS idx_blacklisted_channels_guild ON blacklisted_channels(guild_id);
                CREATE INDEX IF NOT EXISTS idx_blacklisted_categories_guild ON blacklisted_categories(guild_id);
                CREATE INDEX IF NOT EXISTS idx_blacklisted_roles_guild ON blacklisted_roles(guild_id);
                
                -- Indexes for added_by column
                CREATE INDEX IF NOT EXISTS idx_blacklisted_users_added_by ON blacklisted_users(added_by);
                CREATE INDEX IF NOT EXISTS idx_blacklisted_channels_added_by ON blacklisted_channels(added_by);
                CREATE INDEX IF NOT EXISTS idx_blacklisted_categories_added_by ON blacklisted_categories(added_by);
                CREATE INDEX IF NOT EXISTS idx_blacklisted_roles_added_by ON blacklisted_roles(added_by);
                
                -- Indexes for added_at column (for sorting/filtering)
                CREATE INDEX IF NOT EXISTS idx_blacklisted_users_added_at ON blacklisted_users(added_at);
                CREATE INDEX IF NOT EXISTS idx_blacklisted_channels_added_at ON blacklisted_channels(added_at);
                CREATE INDEX IF NOT EXISTS idx_blacklisted_categories_added_at ON blacklisted_categories(added_at);
                CREATE INDEX IF NOT EXISTS idx_blacklisted_roles_added_at ON blacklisted_roles(added_at);
            """)

            print("✅ Created/Updated Blacklist Tables with added_by and added_at columns")

    # PERMISSION MANAGEMENT

    async def get_guild_settings(self, guild_id: int):
        """Get settings for a guild from Settings cog"""
        settings_cog = self.bot.get_cog("Settings")
        if settings_cog:
            return await settings_cog.get_guild_settings(guild_id)

        # Default settings if Settings cog is not available
        return {
            'guild_id': guild_id,
            'prefix': 's!',
            'timezone': 'UTC',
            'voice_states': [],
            'permission_level': 'Default',
            'bot_filter': False,
            'created_at': None
        }

    async def check_blacklist_permission(self, interaction_or_context) -> bool:
        """Check if user has permission to use blacklist command based on server permission level"""
        if hasattr(interaction_or_context, 'user'):
            user = interaction_or_context.user
            guild = interaction_or_context.guild
        else:
            user = interaction_or_context.author
            guild = interaction_or_context.guild

        if user.guild_permissions.administrator:
            return True

        settings = await self.get_guild_settings(guild.id)
        permission_level = settings.get('permission_level', 'Default')

        if permission_level == 'All':
            return True
        elif permission_level == 'Admin':
            return user.guild_permissions.administrator
        elif permission_level == 'Moderator':
            return user.guild_permissions.manage_guild
        elif permission_level == 'Default':
            return user.guild_permissions.administrator or user.guild_permissions.manage_guild
        elif permission_level == 'User Restriction':
            return user.guild_permissions.administrator or user.guild_permissions.manage_guild

        return user.guild_permissions.administrator

    async def send_permission_error(self, ctx_or_interaction):
        """Send permission error message"""
        if hasattr(ctx_or_interaction, 'user'):
            user = ctx_or_interaction.user
            guild = ctx_or_interaction.guild
        else:
            user = ctx_or_interaction.author
            guild = ctx_or_interaction.guild

        settings = await self.get_guild_settings(guild.id)
        permission_level = settings.get('permission_level', 'Default')

        if permission_level == 'Admin':
            required_permission = "Administrator"
        elif permission_level == 'Moderator':
            required_permission = "Manage Server"
        elif permission_level in ['Default', 'User Restriction']:
            required_permission = "Administrator or Manage Server"
        else:
            required_permission = "Administrator"

        embed = discord.Embed(
            title="❌ Permission Denied",
            description=f"Sorry! You need the `{required_permission}` permission to access this command.",
            color=discord.Color.red()
        )

        if hasattr(ctx_or_interaction, 'response'):
            await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await ctx_or_interaction.send(embed=embed, ephemeral=True)

    # =========================================================
    # INTERNAL FUNCTIONS FOR BOTH COMMAND TYPES
    # =========================================================
    @rate_limited(RateLimitType.MESSAGE, timeout=30.0)
    async def _handle_blacklist_menu(self, ctx_or_interaction, is_interaction=False):
        """Internal function to handle blacklist menu for both command types"""
        try:
            if not self.db:
                if is_interaction:
                    await ctx_or_interaction.response.send_message("❌ Database connection is not available.", ephemeral=True)
                else:
                    await ctx_or_interaction.send("❌ Database connection is not available.", ephemeral=True)
                return

            # Check permission based on settings
            if not await self.check_blacklist_permission(ctx_or_interaction):
                await self.send_permission_error(ctx_or_interaction)
                return

            embed = discord.Embed(
                title="**BLACKLIST MENU**",
                description="Welcome to the Blacklist Menu. In this menu, you will be able to exclude specific users, channels, categories or roles from commands on Stats.\n\n"
                "Would you like to add or remove an entry from the blacklist?",
                color=discord.Color.from_rgb(0, 0, 0)
            )

            view = BlacklistIntroView(self, ctx_or_interaction.guild.id)
            view.add_item(AddButton())
            view.add_item(RemoveButton())

            if is_interaction:
                await ctx_or_interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            else:
                await ctx_or_interaction.send(embed=embed, view=view, ephemeral=True)
            view.message = await ctx_or_interaction.original_response() if is_interaction else None

        except Exception as e:
            print(f"Error in _handle_blacklist_menu: {e}")
            if is_interaction:
                try:
                    await ctx_or_interaction.followup.send("❌ An error occurred while opening the blacklist menu.", ephemeral=True)
                except:
                    pass
            else:
                try:
                    await ctx_or_interaction.send("❌ An error occurred while opening the blacklist menu.", ephemeral=True)
                except:
                    pass

    @rate_limited(RateLimitType.MESSAGE, timeout=30.0)
    async def _handle_blacklist_view(self, ctx_or_interaction, is_interaction=False):
        try:
            if not self.db:
                if is_interaction:
                    await ctx_or_interaction.response.send_message("❌ Database connection is not available.", ephemeral=True)
                else:
                    await ctx_or_interaction.send("❌ Database connection is not available.", ephemeral=True)
                return

            if not await self.check_blacklist_permission(ctx_or_interaction):
                await self.send_permission_error(ctx_or_interaction)
                return

            guild_id = ctx_or_interaction.guild.id
            blacklist_items = await self.get_blacklist(guild_id)

            # Debug print to see what's being returned
            print(
                f"Blacklist items for guild {guild_id}: {len(blacklist_items)} items")
            # Print first 5 items for debugging
            for item in blacklist_items[:5]:
                print(f"  Item: {item}")

            if not blacklist_items:
                embed = discord.Embed(
                    title="🛑 Blacklist",
                    description="This server's blacklist is currently empty.",
                    color=discord.Color.red()
                )
                if is_interaction:
                    await ctx_or_interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    await ctx_or_interaction.send(embed=embed, ephemeral=True)
                return

            # Find first type with items
            initial_type = "user"
            type_counts = {}
            for t in ['user', 'channel', 'category', 'role']:
                count = len(
                    [item for item in blacklist_items if item.get('type') == t])
                type_counts[t] = count
                if count > 0 and initial_type == "user":
                    initial_type = t

            print(f"Type counts: {type_counts}")
            print(f"Initial type selected: {initial_type}")

            filtered_items = [
                item for item in blacklist_items if item.get('type') == initial_type]

            print(f"Filtered items for {initial_type}: {len(filtered_items)}")

            type_display = {'user': 'Users', 'channel': 'Channels',
                            'category': 'Categories', 'role': 'Roles'}
            emoji = {'user': '👤', 'channel': '📝', 'category': '📁', 'role': '🎭'}

            embed = discord.Embed(
                title=f"🛑 {ctx_or_interaction.guild.name} Blacklist - {type_display[initial_type]}",
                description=f"Total blacklisted {initial_type}s: {len(filtered_items)}",
                color=discord.Color.red()
            )

            items_text = []
            for item in filtered_items[:25]:
                entity_id = item.get('entity_id')
                if not entity_id:
                    continue

                try:
                    entity_id = int(entity_id)
                except (ValueError, TypeError):
                    items_text.append(
                        f"{emoji[initial_type]} Invalid ID (`{entity_id}`)")
                    continue

                if initial_type == 'user':
                    member = ctx_or_interaction.guild.get_member(entity_id)
                    if member:
                        name = member.display_name
                    else:
                        try:
                            if hasattr(ctx_or_interaction.guild, 'fetch_member'):
                                member = await ctx_or_interaction.guild.fetch_member(entity_id)
                                name = member.display_name
                        except:
                            name = f"Unknown User"
                    items_text.append(
                        f"{emoji[initial_type]} {name} (`{entity_id}`)")

                elif initial_type == 'channel':
                    channel = ctx_or_interaction.guild.get_channel(entity_id)
                    name = f"#{channel.name}" if channel else f"Unknown Channel"
                    items_text.append(
                        f"{emoji[initial_type]} {name} (`{entity_id}`)")

                elif initial_type == 'category':
                    category = ctx_or_interaction.guild.get_channel(entity_id)
                    name = category.name if category else f"Unknown Category"
                    items_text.append(
                        f"{emoji[initial_type]} {name} (`{entity_id}`)")

                elif initial_type == 'role':
                    role = ctx_or_interaction.guild.get_role(entity_id)
                    name = role.name if role else f"Unknown Role"
                    items_text.append(
                        f"{emoji[initial_type]} {name} (`{entity_id}`)")

            if items_text:
                embed.add_field(name=f"Blacklisted {type_display[initial_type]}",
                                value="\n".join(items_text),
                                inline=False)
                if len(filtered_items) > 25:
                    embed.add_field(
                        name="⚠️ Note",
                        value=f"There are {len(filtered_items) - 25} more {initial_type}s in the blacklist.",
                        inline=False)
            else:
                embed.description = f"Could not load {initial_type} details."

            embed.set_footer(
                text="Use the dropdown to view other types • Use /blacklist menu to modify")

            view = BlacklistView(self, guild_id, initial_type)
            view.add_item(TypeSelect(self, guild_id, initial_type))

            if is_interaction:
                await ctx_or_interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            else:
                await ctx_or_interaction.send(embed=embed, view=view, ephemeral=True)
            view.message = await ctx_or_interaction.original_response() if is_interaction else None

        except Exception as e:
            print(f"Error in _handle_blacklist_view: {e}")
            import traceback
            traceback.print_exc()
            if is_interaction:
                try:
                    await ctx_or_interaction.response.send_message("❌ An error occurred.", ephemeral=True)
                except:
                    pass
   # COMMANDS

   # BLACKLIST VIEW

    blacklist_group = app_commands.Group(
        name="blacklist", description="Manage the server blacklist")

    @blacklist_group.command(name="view", description="View the current blacklist")
    async def blacklist_view(self, interaction: discord.Interaction):
        await self._handle_blacklist_view(interaction, is_interaction=True)

    # BLACKLIST MENU

    @blacklist_group.command(name="menu", description="Interactive blacklist management menu")
    async def blacklist_menu(self, interaction: discord.Interaction):
        await self._handle_blacklist_menu(interaction, is_interaction=True)

    # =========================================================
    # PREFIX COMMANDS GROUP
    # =========================================================
    @commands.group(name="blacklist", invoke_without_command=True)
    async def blacklist_group_prefix(self, ctx: commands.Context):
        """Manage the server blacklist"""
        await ctx.send("Available commands:\n- `blacklist menu` - Interactive blacklist management menu\n- `blacklist view` - View current blacklist\n- `bm` - Shortcut for blacklist menu\n- `bv` - Shortcut for blacklist view")

    @blacklist_group_prefix.command(name="menu")
    async def blacklist_menu_prefix(self, ctx: commands.Context):
        """Interactive blacklist management menu"""
        await self._handle_blacklist_menu(ctx, is_interaction=False)

    @blacklist_group_prefix.command(name="view")
    async def blacklist_view_prefix(self, ctx: commands.Context):
        """View the current blacklist"""
        await self._handle_blacklist_view(ctx, is_interaction=False)

    # =========================================================
    # SHORTCUT COMMANDS
    # =========================================================
    @commands.command(name="bm")
    async def blacklist_menu_shortcut(self, ctx: commands.Context):
        """Shortcut command for blacklist menu"""
        await self._handle_blacklist_menu(ctx, is_interaction=False)

    @commands.command(name="bv")
    async def blacklist_view_shortcut(self, ctx: commands.Context):
        """Shortcut command for blacklist view"""
        await self._handle_blacklist_view(ctx, is_interaction=False)

    async def send_blacklist_view(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        blacklist_items = await self.get_blacklist(guild_id)

        if not blacklist_items:
            embed = discord.Embed(
                title="🛑 Blacklist",
                description="This server's blacklist is currently empty.",
                color=discord.Color.red()
            )
            return await interaction.followup.send(embed=embed, ephemeral=True)

        user_items = [
            item for item in blacklist_items if item['type'] == 'user']

        if user_items:
            embed = await self.create_blacklist_embed(interaction.guild, user_items, "user")
            initial_type = "user"
        else:
            for type_val in ['channel', 'category', 'role']:
                filtered_items = [
                    item for item in blacklist_items if item['type'] == type_val]
                if filtered_items:
                    embed = await self.create_blacklist_embed(interaction.guild, filtered_items, type_val)
                    initial_type = type_val
                    break
            else:
                embed = discord.Embed(
                    title="🛑 Blacklist",
                    description="No blacklisted items found.",
                    color=discord.Color.red()
                )
                initial_type = "user"

        view = BlacklistView(self, guild_id, initial_type)
        view.add_item(TypeSelect(self, guild_id, initial_type))

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def show_intro_page(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="**BLACKLIST MENU**",
            description="Welcome to the Blacklist Menu. In this menu, you will be able to exclude specific users, channels, categories or roles from commands on Stats.\n\n"
            "Would you like to add or remove an entry from the blacklist?",
            color=discord.Color.from_rgb(0, 0, 0)
        )

        view = BlacklistIntroView(self, interaction.guild.id)
        view.add_item(AddButton())
        view.add_item(RemoveButton())

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.message = await interaction.original_response()

    async def show_type_selection(self, interaction: discord.Interaction, action: str, is_returning: bool = False):
        to_from = "to" if action == "add" else "from"

        embed = discord.Embed(
            title=f"Blacklist - {action.capitalize()}",
            description=f"Please choose what you would like to {action} {to_from} the blacklist through the dropdown menu below:",
            color=discord.Color.from_rgb(0, 0, 0)
        )

        view = BlacklistTypeSelectView(self, interaction.guild.id, action)

        if is_returning:
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.edit_original_response(embed=embed, view=view)
        view.message = await interaction.original_response()

    async def show_menu_step2(self, interaction: discord.Interaction, entity_type: str, action: str, selected_ids: List[str] = None, is_returning: bool = False):
        type_display = {
            'user': ['user', 'users'],
            'channel': ['channel', 'channels'],
            'category': ['category', 'categories'],
            'role': ['role', 'roles']
        }

        selected_count = len(selected_ids) if selected_ids else 0
        if selected_count == 0:
            entity_text = type_display[entity_type][0]
        else:
            entity_text = type_display[entity_type][0] if selected_count == 1 else type_display[entity_type][1]

        to_from = "to" if action == "add" else "from"
        has_have = "has" if selected_count == 1 else "have"

        embed = discord.Embed(
            title=f"Blacklist {type_display[entity_type][1].title()} - {action.capitalize()}",
            description=f"You {has_have} chosen to {action} a {type_display[entity_type][0]} {to_from} the blacklist.\n\n"
            f"Please use either the dropdown menu to select a {entity_text} or the \"Input Id\" button to {action} a {entity_text} {to_from} the Blacklist",
            color=discord.Color.from_rgb(0, 0, 0)
        )

        if selected_ids:
            items_list = []
            for entity_id in selected_ids:
                try:
                    target = await self.validate_target(interaction.guild, entity_type, int(entity_id))
                    if target:
                        items_list.append(self.get_target_name(target))
                except:
                    pass

            if items_list:
                embed.add_field(
                    name=f"Selected {type_display[entity_type][1].title()}:",
                    value="\n".join(items_list),
                    inline=False
                )

        # CRITICAL FIX: Create the view properly
        view = BlacklistMenuStep2(
            self, interaction.guild, entity_type, action, selected_ids or [])

        if is_returning:
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.edit_original_response(embed=embed, view=view)
        view.message = await interaction.original_response()

    async def update_menu_step2(self, interaction: discord.Interaction, view):
        entity_type = view.entity_type
        action = view.action
        selected_ids = view.selected_ids

        type_display = {
            'user': ['user', 'users'],
            'channel': ['channel', 'channels'],
            'category': ['category', 'categories'],
            'role': ['role', 'roles']
        }

        selected_count = len(selected_ids) if selected_ids else 0
        if selected_count == 0:
            entity_text = type_display[entity_type][0]
        else:
            entity_text = type_display[entity_type][0] if selected_count == 1 else type_display[entity_type][1]

        to_from = "to" if action == "add" else "from"
        has_have = "has" if selected_count == 1 else "have"

        embed = discord.Embed(
            title=f"Blacklist {type_display[entity_type][1].title()} - {action.capitalize()}",
            description=f"You {has_have} chosen to {action} a {type_display[entity_type][0]} {to_from} the blacklist.\n\n"
            f"Please use either the dropdown menu to select a {entity_text} or the \"Input Id\" button to {action} a {entity_text} {to_from} the Blacklist",
            color=discord.Color.from_rgb(0, 0, 0)
        )

        if selected_ids:
            items_list = []
            for entity_id in selected_ids:
                try:
                    target = await self.validate_target(interaction.guild, entity_type, int(entity_id))
                    if target:
                        items_list.append(self.get_target_name(target))
                except:
                    pass

            if items_list:
                embed.add_field(
                    name=f"Selected {type_display[entity_type][1].title()}:",
                    value="\n".join(items_list),
                    inline=False
                )

        await interaction.edit_original_response(embed=embed, view=view)

    async def show_menu_step3(self, interaction: discord.Interaction, entity_type: str, selected_ids: List[str], action: str):
        type_display = {
            'user': ['user', 'users'],
            'channel': ['channel', 'channels'],
            'category': ['category', 'categories'],
            'role': ['role', 'roles']
        }

        items_list = []
        for entity_id in selected_ids:
            try:
                target = await self.validate_target(interaction.guild, entity_type, int(entity_id))
                if target:
                    items_list.append(self.get_target_name(target))
            except:
                items_list.append(f"Unknown (ID: {entity_id})")

        items_text = "\n".join(items_list)

        selected_count = len(selected_ids)
        if selected_count == 1:
            choice_text = type_display[entity_type][0]
            is_are = "is"
            this_these = "this"
        else:
            choice_text = type_display[entity_type][1]
            is_are = "are"
            this_these = "these"

        if action == "add":
            confirmation_text = f"Are you sure you want to blacklist {this_these} {choice_text}? If so, apply the changes."
        else:
            confirmation_text = f"Are you sure you want to remove {this_these} {choice_text} from the blacklist? If so, apply the changes."

        embed = discord.Embed(
            title="Confirmation",
            description=f"The selected {choice_text} {is_are}:\n\n{items_text}\n\n{confirmation_text}",
            color=discord.Color.from_rgb(0, 0, 0)
        )

        view = BlacklistMenuStep3(
            self, interaction.guild, entity_type, selected_ids, action)
        await interaction.edit_original_response(embed=embed, view=view)
        view.message = await interaction.original_response()

    async def apply_blacklist_changes(self, interaction: discord.Interaction, entity_type: str, selected_ids: List[str], action: str):
        success_count = 0
        already_count = 0
        not_found_count = 0
        error_count = 0

        for entity_id_str in selected_ids:
            try:
                entity_id = int(entity_id_str)

                if action == "add":
                    result = await self.add_to_blacklist(
                        interaction.guild.id,
                        entity_type,
                        entity_id,
                        interaction.user.id
                    )

                    if result == "added":
                        success_count += 1
                    elif result == "exists":
                        already_count += 1
                    else:
                        error_count += 1

                elif action == "remove":
                    result = await self.remove_from_blacklist(
                        interaction.guild.id,
                        entity_type,
                        entity_id
                    )

                    if result == "removed":
                        success_count += 1
                    elif result == "not_found":
                        not_found_count += 1
                    else:
                        error_count += 1

            except Exception as e:
                print(f"Error processing {entity_type} {entity_id_str}: {e}")
                error_count += 1

        type_display = {
            'user': ['user', 'users'],
            'channel': ['channel', 'channels'],
            'category': ['category', 'categories'],
            'role': ['role', 'roles']
        }

        def get_plural(count, type_val):
            if count == 1:
                return type_display[type_val][0]
            return type_display[type_val][1]

        def get_was_were(count):
            return "was" if count == 1 else "were"

        message_parts = []
        if success_count > 0:
            entity_text = get_plural(success_count, entity_type)
            if action == "add":
                message_parts.append(
                    f"✅ Successfully blacklisted {success_count} {entity_text}.")
            else:
                message_parts.append(
                    f"✅ Successfully removed {success_count} {entity_text} from the blacklist.")

        if already_count > 0 and action == "add":
            entity_text = get_plural(already_count, entity_type)
            was_were = get_was_were(already_count)
            message_parts.append(
                f"⚠️ {already_count} {entity_text} {was_were} already blacklisted.")

        if not_found_count > 0 and action == "remove":
            entity_text = get_plural(not_found_count, entity_type)
            was_were = get_was_were(not_found_count)
            message_parts.append(
                f"❌ {not_found_count} {entity_text} {was_were} not found in the blacklist.")

        if error_count > 0:
            entity_text = get_plural(error_count, entity_type)
            was_were = get_was_were(error_count)
            message_parts.append(
                f"❌ Failed to process {error_count} {entity_text}.")

        embed = discord.Embed(
            title=f"Blacklist {action.capitalize()} Applied",
            description="\n".join(message_parts),
            color=discord.Color.from_rgb(0, 0, 0)
        )

        view = discord.ui.View(timeout=60)
        view.add_item(ViewBlacklistButton())

        await interaction.edit_original_response(embed=embed, view=view)

    # SHOW BLACKLIST VIEW

    async def show_blacklist(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        blacklist_items = await self.get_blacklist(guild_id)

        if not blacklist_items:
            embed = discord.Embed(
                title="🛑 Blacklist",
                description="This server's blacklist is currently empty.",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        user_items = [
            item for item in blacklist_items if item['type'] == 'user']

        if user_items:
            embed = await self.create_blacklist_embed(interaction.guild, user_items, "user")
            initial_type = "user"
        else:
            for type_val in ['channel', 'category', 'role']:
                filtered_items = [
                    item for item in blacklist_items if item['type'] == type_val]
                if filtered_items:
                    embed = await self.create_blacklist_embed(interaction.guild, filtered_items, type_val)
                    initial_type = type_val
                    break
            else:
                embed = discord.Embed(
                    title="🛑 Blacklist",
                    description="No blacklisted items found.",
                    color=discord.Color.red()
                )
                initial_type = "user"

        view = BlacklistView(self, guild_id, initial_type)
        view.add_item(TypeSelect(self, guild_id, initial_type))

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.message = await interaction.original_response()

    # EMBED CREATION

    async def create_blacklist_embed(self, guild: discord.Guild, items: list, type_val: str) -> discord.Embed:
        type_display = {
            'user': 'Users',
            'channel': 'Channels',
            'category': 'Categories',
            'role': 'Roles'
        }

        emoji = {
            'user': '👤',
            'channel': '📝',
            'category': '📁',
            'role': '🎭'
        }

        embed = discord.Embed(
            title=f"🛑 {guild.name} Blacklist - {type_display[type_val]}",
            description=f"Total blacklisted {type_val}s: {len(items)}",
            color=discord.Color.red()
        )

        item_list = []
        for item in items[:15]:
            try:
                # CRITICAL FIX: Get entity_id consistently
                entity_id = item.get('entity_id')
                if not entity_id:
                    print(f"Warning: No entity_id found in item: {item}")
                    continue

                # Convert to int if it's a string
                try:
                    entity_id = int(entity_id)
                except (ValueError, TypeError):
                    print(f"Warning: Could not convert {entity_id} to int")
                    continue

                # Get display name
                if type_val == 'user':
                    member = guild.get_member(entity_id)
                    if member:
                        display_name = f"{emoji[type_val]} {member.display_name} (`{entity_id}`)"
                    else:
                        # Try to fetch the user if not in cache
                        try:
                            member = await guild.fetch_member(entity_id)
                            display_name = f"{emoji[type_val]} {member.display_name} (`{entity_id}`)"
                        except:
                            display_name = f"{emoji[type_val]} Unknown User (`{entity_id}`)"

                elif type_val == 'channel':
                    channel = guild.get_channel(entity_id)
                    if channel:
                        display_name = f"{emoji[type_val]} {channel.mention} (`{entity_id}`)"
                    else:
                        display_name = f"{emoji[type_val]} Unknown Channel (`{entity_id}`)"

                elif type_val == 'category':
                    category = guild.get_channel(entity_id)
                    if category:
                        display_name = f"{emoji[type_val]} {category.name} (`{entity_id}`)"
                    else:
                        display_name = f"{emoji[type_val]} Unknown Category (`{entity_id}`)"

                elif type_val == 'role':
                    role = guild.get_role(entity_id)
                    if role:
                        display_name = f"{emoji[type_val]} {role.name} (`{entity_id}`)"
                    else:
                        display_name = f"{emoji[type_val]} Unknown Role (`{entity_id}`)"
                else:
                    display_name = f"{emoji[type_val]} Unknown (`{entity_id}`)"

                item_list.append(display_name)

            except Exception as e:
                print(f"Error processing item {item}: {e}")
                continue

        if item_list:
            embed.add_field(
                name=f"Blacklisted {type_display[type_val]}",
                value="\n".join(item_list[:20]),
                inline=False
            )

            if len(items) > 15:
                embed.add_field(
                    name="⚠️ Note",
                    value=f"There are {len(items) - 15} more {type_val}s in the blacklist.",
                    inline=False
                )
        else:
            embed.description = f"No {type_val}s found in blacklist (or unable to load details)."

        embed.set_footer(
            text="Use the dropdown to view other types • Use /blacklist menu to modify")
        return embed

    # HELPER FUNCTIONS

    async def get_entity_display_name(self, guild: discord.Guild, type_val: str, entity_id: int) -> str:
        try:
            if type_val == 'user':
                member = guild.get_member(entity_id)
                if member:
                    return f"{member.display_name} (`{entity_id}`)"
                else:
                    return f"Unknown User (`{entity_id}`)"

            elif type_val == 'channel':
                channel = guild.get_channel(entity_id)
                if channel:
                    return f"{channel.mention} (`{entity_id}`)"
                else:
                    return f"Unknown Channel (`{entity_id}`)"

            elif type_val == 'category':
                category = guild.get_channel(entity_id)
                if category:
                    return f"{category.name} (`{entity_id}`)"
                else:
                    return f"Unknown Category (`{entity_id}`)"

            elif type_val == 'role':
                role = guild.get_role(entity_id)
                if role:
                    return f"{role.name} (`{entity_id}`)"
                else:
                    return f"Unknown Role (`{entity_id}`)"

        except Exception as e:
            print(f"Error getting entity display name: {e}")
            return f"Unknown (`{entity_id}`)"

    async def validate_target(self, guild: discord.Guild, type_val: str, entity_id: int):
        try:
            if type_val == 'user':
                member = guild.get_member(entity_id)
                if not member:
                    try:
                        member = await guild.fetch_member(entity_id)
                    except (discord.NotFound, discord.HTTPException):
                        return None
                return member

            elif type_val == 'channel':
                channel = guild.get_channel(entity_id)
                if channel and isinstance(channel, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel, discord.Thread)):
                    return channel
                return None

            elif type_val == 'category':
                channel = guild.get_channel(entity_id)
                if channel and isinstance(channel, discord.CategoryChannel):
                    return channel
                return None

            elif type_val == 'role':
                role = guild.get_role(entity_id)
                return role

        except Exception as e:
            print(f"Error validating target: {e}")
            return None

    def get_target_name(self, target_obj) -> str:
        if isinstance(target_obj, discord.Member):
            return f"👤 {target_obj.display_name} (id:{target_obj.id})"
        elif isinstance(target_obj, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel, discord.Thread)):
            return f"📝 #{target_obj.name} (id:{target_obj.id})"
        elif isinstance(target_obj, discord.CategoryChannel):
            return f"📁 {target_obj.name} (id:{target_obj.id})"
        elif isinstance(target_obj, discord.Role):
            return f"🎭 {target_obj.name} (id:{target_obj.id})"
        else:
            return str(target_obj)

    # BLACKLIST LOGIC

    async def add_to_blacklist(self, guild_id: int, type_val: str, entity_id: int, added_by: int) -> str:
        try:
            async with self.db.acquire() as conn:
                async with conn.transaction():
                    table_name = f"blacklisted_{type_val}s" if type_val != 'category' else "blacklisted_categories"

                    column_mapping = {
                        'user': 'user_id',
                        'channel': 'channel_id',
                        'category': 'category_id',
                        'role': 'role_id'
                    }
                    column_name = column_mapping[type_val]

                    # Check if exists
                    exists = await conn.fetchval(
                        f"SELECT 1 FROM {table_name} WHERE guild_id = $1 AND {column_name} = $2",
                        guild_id, entity_id
                    )

                    if exists:
                        return "exists"

                    # Insert with added_by and added_at
                    await conn.execute(
                        f"INSERT INTO {table_name} (guild_id, {column_name}, added_by, added_at) VALUES ($1, $2, $3, NOW())",
                        guild_id, entity_id, added_by
                    )

                    return "added"

        except Exception as e:
            print(f"Error adding to blacklist: {e}")
            return "error"

    async def remove_from_blacklist(self, guild_id: int, type_val: str, entity_id: int) -> str:
        try:
            async with self.db.acquire() as conn:
                table_name = f"blacklisted_{type_val}s" if type_val != 'category' else "blacklisted_categories"

                if type_val == 'user':
                    column_name = 'user_id'
                elif type_val == 'channel':
                    column_name = 'channel_id'
                elif type_val == 'category':
                    column_name = 'category_id'
                elif type_val == 'role':
                    column_name = 'role_id'

                result = await conn.execute(
                    f"DELETE FROM {table_name} WHERE guild_id = $1 AND {column_name} = $2",
                    guild_id, entity_id
                )

                if "DELETE 1" in result:
                    return "removed"
                else:
                    return "not_found"
        except Exception as e:
            print(f"Error removing from blacklist: {e}")
            return "error"

    async def is_blacklisted(self, guild_id: int, type_val: str, entity_id: int) -> bool:
        if not self.db:
            return False

        try:
            async with self.db.acquire() as conn:
                table_name = f"blacklisted_{type_val}s" if type_val != 'category' else "blacklisted_categories"

                column_mapping = {
                    'user': 'user_id',
                    'channel': 'channel_id',
                    'category': 'category_id',
                    'role': 'role_id'
                }
                column_name = column_mapping[type_val]

                exists = await conn.fetchval(
                    f"SELECT 1 FROM {table_name} WHERE guild_id = $1 AND {column_name} = $2",
                    guild_id, entity_id
                )
                return exists is not None
        except Exception:
            return False

    async def get_blacklist(self, guild_id: int) -> list:
        if not self.db:
            return []

        try:
            async with self.db.acquire() as conn:
                all_items = []

                # Get users with added_by
                users = await conn.fetch("SELECT user_id, added_by, added_at FROM blacklisted_users WHERE guild_id = $1", guild_id)
                for u in users:
                    all_items.append({
                        'type': 'user',
                        'entity_id': u['user_id'],
                        'added_by': u['added_by'],
                        'added_at': u['added_at']
                    })

                # Get channels with added_by
                channels = await conn.fetch("SELECT channel_id, added_by, added_at FROM blacklisted_channels WHERE guild_id = $1", guild_id)
                for c in channels:
                    all_items.append({
                        'type': 'channel',
                        'entity_id': c['channel_id'],
                        'added_by': c['added_by'],
                        'added_at': c['added_at']
                    })

                # Get categories with added_by
                categories = await conn.fetch("SELECT category_id, added_by, added_at FROM blacklisted_categories WHERE guild_id = $1", guild_id)
                for cat in categories:
                    all_items.append({
                        'type': 'category',
                        'entity_id': cat['category_id'],
                        'added_by': cat['added_by'],
                        'added_at': cat['added_at']
                    })

                # Get roles with added_by
                roles = await conn.fetch("SELECT role_id, added_by, added_at FROM blacklisted_roles WHERE guild_id = $1", guild_id)
                for r in roles:
                    all_items.append({
                        'type': 'role',
                        'entity_id': r['role_id'],
                        'added_by': r['added_by'],
                        'added_at': r['added_at']
                    })

                all_items.sort(
                    key=lambda x: x['added_at'] or datetime.min, reverse=True)
                return all_items

        except Exception as e:
            print(f"get_blacklist error: {e}")
            return []

    async def cog_unload(self):
        if self.db:
            await self.db.close()
            print("Blacklist cog: Database connection closed")


# SETUP

async def setup(bot):
    await bot.add_cog(Blacklist(bot))
