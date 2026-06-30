import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import Button, View

# Import the rate limiter
from .ratelimiter import RateLimiter, RateLimitType, rate_limited, get_rate_limiter


class HelpView(View):
    """View class for help command buttons"""

    def __init__(self):
        super().__init__(timeout=60)

        # Row 1
        invite_button = Button(
            label="Invite Bot",
            url="https://discord.com/oauth2/authorize?client_id=1481328229909270568&permissions=414734863601&integration_type=0&scope=bot+applications.commands",
            style=discord.ButtonStyle.link
        )
        self.add_item(invite_button)

        setup_button = Button(
            label="Bot Setup Guide",
            url="https://statshq.xyz/docs/?page=bot-setup",
            style=discord.ButtonStyle.link
        )
        self.add_item(setup_button)

        dashboard_setup_button = Button(
            label="Dashboard Setup Guide",
            url="https://statshq.xyz/docs/?page=dashboard-setup",
            style=discord.ButtonStyle.link
        )
        self.add_item(dashboard_setup_button)

        docs_button = Button(
            label="Documentation",
            url="https://statshq.xyz/docs/",
            style=discord.ButtonStyle.link
        )
        self.add_item(docs_button)

        # Row 2 (explicitly set row=1)
        dashboard_button = Button(
            label="Dashboard",
            url="https://statshq.xyz/Dashboard/Messages/",
            style=discord.ButtonStyle.link,
            row=1
        )
        self.add_item(dashboard_button)

        commands_button = Button(
            label="Commands",
            url="https://statshq.xyz/Commands/",
            style=discord.ButtonStyle.link,
            row=1
        )
        self.add_item(commands_button)

        premium_button = Button(
            label="Premium",
            url="https://statshq.xyz/Premium/",
            style=discord.ButtonStyle.link,
            row=1
        )
        self.add_item(premium_button)

        faq_button = Button(
            label="FAQ",
            url="https://statshq.xyz/docs/?page=faq",
            style=discord.ButtonStyle.link,
            row=1
        )
        self.add_item(faq_button)

        # Row 3 (explicitly set row=2)
        vote_button = Button(
            label="Vote for Bot",
            url="https://top.gg/bot/1481328229909270568/vote",
            style=discord.ButtonStyle.link,
            row=2
        )
        self.add_item(vote_button)

        support_button = Button(
            label="Support",
            url="https://discord.gg/hreJvck8cK",
            style=discord.ButtonStyle.link,
            row=2
        )
        self.add_item(support_button)


class BotLinks(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.rate_limiter = get_rate_limiter()  # Add rate limiter

    # =========================================================
    # INTERNAL FUNCTION FOR BOTH COMMAND TYPES
    # =========================================================
    @rate_limited(RateLimitType.MESSAGE, timeout=10.0)
    async def _handle_links_command(self, ctx_or_interaction, option=None, is_interaction=False):
        """Internal function to handle links for both command types"""

        # Defer for interactions to prevent timeout while rate limiting
        if is_interaction:
            await ctx_or_interaction.response.defer()

        embed = discord.Embed(color=discord.Color.from_str("#FFFFFF"))

        if option is None:
            embed.title = "Bot Links"
            embed.description = "Here are all the important links for this bot:"

            embed.add_field(
                name="🤖 Bot Invite Link",
                value="[Click here to invite the bot to your server!](https://discord.com/oauth2/authorize?client_id=1481328229909270568&permissions=414734863600&integration_type=0&scope=bot+applications.commands)",
                inline=False
            )

            embed.add_field(
                name="🌐 Website",
                value="[Click here to visit our website!](https://statshq.xyz)",
                inline=False
            )

            embed.add_field(
                name="⚙️ Bot Setup Guide",
                value="[Click here for the setup guide!](https://statshq.xyz/docs/?page=bot-setup)",
                inline=False
            )

            embed.add_field(
                name="🛠️ Dashboard Setup Guide",
                value="[Click here for the dashboard setup guide!](https://statshq.xyz/docs/?page=dashboard-setup)",
                inline=False
            )

            embed.add_field(
                name="📚 Documentation",
                value="[Click here to read the documentation!](https://statshq.xyz/docs/)",
                inline=False
            )

            embed.add_field(
                name="📊 Dashboard",
                value="[Click here to access your dashboard!](https://statshq.xyz/Dashboard/Messages/)",
                inline=False
            )

            embed.add_field(
                name="💎 Premium",
                value="[Click here to view Premium!](https://statshq.xyz/Premium/)",
                inline=False
            )

            embed.add_field(
                name="❓ FAQ",
                value="[Click here to read the FAQ!](https://statshq.xyz/docs/?page=faq)",
                inline=False
            )

            embed.add_field(
                name="🗳️ Vote for Bot",
                value="[Click here to vote for the bot on top.gg!](https://top.gg/bot/1481328229909270568/vote)",
                inline=False
            )

            embed.add_field(
                name="🆘 Support Server",
                value="[Click here to join our support server!](https://discord.gg/hreJvck8cK)",
                inline=False
            )

            embed.add_field(
                name="📧 Email",
                value="[statshqofficial@gmail.com](mailto:statshqofficial@gmail.com)",
                inline=False
            )

            embed.set_footer(
                text="Use /links with an option to see only one link")

        elif option == "invite":
            embed.title = "Bot Invite Link"
            embed.description = "Invite this bot to your server!"

            embed.add_field(
                name="Invite Link",
                value="[Click here to invite the bot!](https://discord.com/oauth2/authorize?client_id=1481328229909270568&permissions=414734863600&integration_type=0&scope=bot+applications.commands)",
                inline=False
            )

        elif option == "support":
            embed.title = "Support Server"
            embed.description = "Contact the developers directly and get help!"

            embed.add_field(
                name="Support Server",
                value="[Click here to join our support server!](https://discord.gg/hreJvck8cK)",
                inline=False
            )

        elif option == "website":
            embed.title = "Website"
            embed.description = "Visit our official website!"

            embed.add_field(
                name="Website",
                value="[Click here to visit our website!](https://statshq.xyz)",
                inline=False
            )

        elif option == "docs":
            embed.title = "Documentation"
            embed.description = "Read the documentation to learn more about the bot!"

            embed.add_field(
                name="Documentation",
                value="[Click here to read the documentation!](https://statshq.xyz/docs/)",
                inline=False
            )

        elif option == "dashboard":
            embed.title = "Dashboard"
            embed.description = "Access your server's dashboard!"

            embed.add_field(
                name="Dashboard",
                value="[Click here to access the dashboard!](https://statshq.xyz/Dashboard/Messages/)",
                inline=False
            )

        elif option == "setup":
            embed.title = "Bot Setup Guide"
            embed.description = "Learn how to set up the bot on your server!"

            embed.add_field(
                name="Bot Setup Guide",
                value="[Click here for the setup guide!](https://statshq.xyz/docs/?page=bot-setup)",
                inline=False
            )

        elif option == "dashboard-setup":
            embed.title = "Dashboard Setup Guide"
            embed.description = "Learn how to log in and set up the dashboard!"

            embed.add_field(
                name="Dashboard Setup Guide",
                value="[Click here for the dashboard setup guide!](https://statshq.xyz/docs/?page=dashboard-setup)",
                inline=False
            )

        elif option == "vote":
            embed.title = "Vote for Bot"
            embed.description = "Support the bot by voting on top.gg!"

            embed.add_field(
                name="Vote Link",
                value="[Click here to vote for the bot!](https://top.gg/bot/1481328229909270568/vote)",
                inline=False
            )

        elif option == "premium":
            embed.title = "Premium"
            embed.description = "Unlock premium features for the bot!"

            embed.add_field(
                name="Premium",
                value="[Click here to view Premium!](https://statshq.xyz/Premium/)",
                inline=False
            )

        elif option == "faq":
            embed.title = "FAQ"
            embed.description = "Frequently asked questions about the bot!"

            embed.add_field(
                name="FAQ",
                value="[Click here to read the FAQ!](https://statshq.xyz/docs/?page=faq)",
                inline=False
            )

        elif option == "email":
            embed.title = "Email"
            embed.description = "Get in touch with us via email!"

            embed.add_field(
                name="Email",
                value="[statshqofficial@gmail.com](mailto:statshqofficial@gmail.com)",
                inline=False
            )

        # Send the response
        if is_interaction:
            await ctx_or_interaction.followup.send(embed=embed)
        else:
            await ctx_or_interaction.send(embed=embed)

    # =========================================================
    # INTERNAL FUNCTION FOR GET ID COMMAND
    # =========================================================
    @rate_limited(RateLimitType.MESSAGE, timeout=10.0)
    async def _handle_get_id_command(self, ctx_or_interaction, role=None, user=None, channel=None, category=None, is_interaction=False):
        """Internal function to handle get_id for both command types"""

        # Defer for interactions to prevent timeout while rate limiting
        if is_interaction:
            await ctx_or_interaction.response.defer()

        embed = discord.Embed(
            title="🔍 ID Information",
            color=discord.Color.from_str("#FFFFFF")
        )

        if is_interaction:
            guild = ctx_or_interaction.guild
            author = ctx_or_interaction.user
            current_channel = ctx_or_interaction.channel
        else:
            guild = ctx_or_interaction.guild
            author = ctx_or_interaction.author
            current_channel = ctx_or_interaction.channel

        # Check if any specific target was provided
        if role or user or channel or category:
            id_info = ""

            if role:
                embed.description = f"**Role:** {role.mention}\n**ID:** `{role.id}`"
                embed.add_field(name="Role Name", value=role.name, inline=True)
                embed.add_field(
                    name="Role ID", value=f"`{role.id}`", inline=True)
                if guild:
                    embed.add_field(
                        name="Guild", value=guild.name, inline=True)

            elif user:
                embed.description = f"**User:** {user.mention}\n**ID:** `{user.id}`"
                embed.add_field(name="Username", value=user.name, inline=True)
                if isinstance(user, discord.Member) and user.nick:
                    embed.add_field(name="Nickname",
                                    value=user.nick, inline=True)
                embed.add_field(
                    name="User ID", value=f"`{user.id}`", inline=True)

            elif channel:
                embed.description = f"**Channel:** {channel.mention}\n**ID:** `{channel.id}`"
                embed.add_field(name="Channel Name",
                                value=channel.name, inline=True)
                embed.add_field(name="Channel ID",
                                value=f"`{channel.id}`", inline=True)
                if hasattr(channel, 'category') and channel.category:
                    embed.add_field(name="Category",
                                    value=channel.category.name, inline=True)

            elif category:
                embed.description = f"**Category:** {category.name}\n**ID:** `{category.id}`"
                embed.add_field(name="Category Name",
                                value=category.name, inline=True)
                embed.add_field(name="Category ID",
                                value=f"`{category.id}`", inline=True)
                embed.add_field(name="Channels", value=str(
                    len(category.channels)), inline=True)
        else:
            # Show all IDs when no specific target is provided
            if guild:
                embed.description = f"**Server Information**"
                embed.add_field(name="Server Name",
                                value=guild.name, inline=True)
                embed.add_field(name="Server ID",
                                value=f"`{guild.id}`", inline=True)

            # User information
            embed.add_field(name="Your Name", value=author.name, inline=True)
            embed.add_field(
                name="Your ID", value=f"`{author.id}`", inline=True)

            if current_channel:
                # Channel information
                embed.add_field(name="Channel Name",
                                value=f"#{current_channel.name}", inline=True)
                embed.add_field(name="Channel ID",
                                value=f"`{current_channel.id}`", inline=True)

                # Category information
                if hasattr(current_channel, 'category') and current_channel.category:
                    embed.add_field(
                        name="Category Name", value=current_channel.category.name, inline=True)
                    embed.add_field(
                        name="Category ID", value=f"`{current_channel.category.id}`", inline=True)
                else:
                    embed.add_field(name="Category",
                                    value="None (No category)", inline=True)
                    # Empty field for spacing
                    embed.add_field(name="", value="", inline=True)

            embed.set_footer(
                text="To get a specific ID, mention a role, user, or channel")

        # Send the response
        if is_interaction:
            await ctx_or_interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await ctx_or_interaction.send(embed=embed)

    # =========================================================
    # INTERNAL FUNCTION FOR HELP COMMAND
    # =========================================================
    @rate_limited(RateLimitType.MESSAGE, timeout=10.0)
    async def _handle_help_command(self, ctx_or_interaction, is_interaction=False):
        """Internal function to handle help command for both command types"""

        # Defer for interactions to prevent timeout while rate limiting
        if is_interaction:
            await ctx_or_interaction.response.defer()

        # Create purple embed
        embed = discord.Embed(
            description="Use the links below to get started on Stats!",
            color=discord.Color.purple()
        )

        # Create view with buttons
        view = HelpView()

        # Send the response
        if is_interaction:
            await ctx_or_interaction.followup.send(embed=embed, view=view)
        else:
            await ctx_or_interaction.send(embed=embed, view=view)

    # =========================================================
    # SHORTCUT COMMANDS
    # =========================================================
    @commands.command(name="support", aliases=["support server", "discord server"])
    async def support_shortcut(self, ctx: commands.Context):
        """Show the support server link"""
        await self._handle_links_command(ctx, option="support", is_interaction=False)

    @commands.command(name="bot", aliases=["bot invite link", "bot invite"])
    async def invite_shortcut(self, ctx: commands.Context):
        """Show the bot's invite link"""
        await self._handle_links_command(ctx, option="invite", is_interaction=False)

    @commands.command(name="website", aliases=["site"])
    async def website_shortcut(self, ctx: commands.Context):
        """Show the bot's website link"""
        await self._handle_links_command(ctx, option="website", is_interaction=False)

    @commands.command(name="docs", aliases=["documentation"])
    async def docs_shortcut(self, ctx: commands.Context):
        """Show the documentation link"""
        await self._handle_links_command(ctx, option="docs", is_interaction=False)

    @commands.command(name="dashboard", aliases=["dash"])
    async def dashboard_shortcut(self, ctx: commands.Context):
        """Show the dashboard link"""
        await self._handle_links_command(ctx, option="dashboard", is_interaction=False)

    @commands.command(name="setup", aliases=["guide", "setting up"])
    async def setup_shortcut(self, ctx: commands.Context):
        """Show the setup guide link"""
        await self._handle_links_command(ctx, option="setup", is_interaction=False)

    @commands.command(name="dashboardsetup", aliases=["dashboard setup", "dash setup"])
    async def dashboard_setup_shortcut(self, ctx: commands.Context):
        """Show the dashboard setup guide link"""
        await self._handle_links_command(ctx, option="dashboard-setup", is_interaction=False)

    @commands.command(name="vote", aliases=["voting", "topgg"])
    async def vote_shortcut(self, ctx: commands.Context):
        """Show the vote link for the bot on top.gg"""
        await self._handle_links_command(ctx, option="vote", is_interaction=False)

    @commands.command(name="premium", aliases=["prem"])
    async def premium_shortcut(self, ctx: commands.Context):
        """Show the premium link"""
        await self._handle_links_command(ctx, option="premium", is_interaction=False)

    @commands.command(name="faq", aliases=["questions"])
    async def faq_shortcut(self, ctx: commands.Context):
        """Show the FAQ link"""
        await self._handle_links_command(ctx, option="faq", is_interaction=False)

    @commands.command(name="email", aliases=["contact", "mail"])
    async def email_shortcut(self, ctx: commands.Context):
        """Show the contact email"""
        await self._handle_links_command(ctx, option="email", is_interaction=False)

    # =========================================================
    # HELP COMMAND
    # =========================================================

    # Prefix help command (no shortcut version)
    @commands.command(name="help", aliases=["h"])
    async def help_prefix(self, ctx: commands.Context):
        """Get help with the bot and access important links"""
        await self._handle_help_command(ctx, is_interaction=False)

    # =========================================================
    # GET ID COMMAND GROUP (NESTED GROUPING)
    # =========================================================

    # Prefix command group
    @commands.group(name="get", invoke_without_command=True)
    async def get_group_prefix(self, ctx: commands.Context):
        """Get various information"""
        await ctx.send("Available commands:\n- `get id [target]` - Get IDs of roles, users, channels, or show all current IDs")

    # Prefix command for get id
    @get_group_prefix.command(name="id", aliases=["ids"])
    async def get_id_prefix(self, ctx: commands.Context, *, target=None):
        """Get the ID of a role, user, channel, or show all current IDs

        Examples:
        - `get id @user` - Get user's ID
        - `get id @role` - Get role's ID
        - `get id #channel` - Get channel's ID
        - `get id server` - Show server ID
        - `get id channel` - Show current channel ID
        - `get id category` - Show current category ID
        - `get id` - Show all current IDs (server, your ID, channel, category)
        """
        # Try to parse the target
        role = None
        user = None
        channel = None
        category = None

        if target:
            target_lower = target.lower()

            # Check for special keywords
            if target_lower == "server":
                # Show server ID only
                embed = discord.Embed(
                    title="🔍 Server ID",
                    color=discord.Color.from_str("#FFFFFF")
                )
                if ctx.guild:
                    embed.description = f"**Server:** {ctx.guild.name}"
                    embed.add_field(name="Server Name",
                                    value=ctx.guild.name, inline=True)
                    embed.add_field(name="Server ID",
                                    value=f"`{ctx.guild.id}`", inline=True)
                    await ctx.send(embed=embed)
                else:
                    await ctx.send("❌ This command can only be used in a server.", delete_after=10)
                return

            elif target_lower == "channel":
                # Show current channel ID only
                embed = discord.Embed(
                    title="🔍 Channel ID",
                    color=discord.Color.from_str("#FFFFFF")
                )
                embed.description = f"**Channel:** #{ctx.channel.name}"
                embed.add_field(name="Channel Name",
                                value=f"#{ctx.channel.name}", inline=True)
                embed.add_field(name="Channel ID",
                                value=f"`{ctx.channel.id}`", inline=True)
                await ctx.send(embed=embed)
                return

            elif target_lower == "category":
                # Show current category ID only
                embed = discord.Embed(
                    title="🔍 Category ID",
                    color=discord.Color.from_str("#FFFFFF")
                )
                if hasattr(ctx.channel, 'category') and ctx.channel.category:
                    embed.description = f"**Category:** {ctx.channel.category.name}"
                    embed.add_field(name="Category Name",
                                    value=ctx.channel.category.name, inline=True)
                    embed.add_field(
                        name="Category ID", value=f"`{ctx.channel.category.id}`", inline=True)
                    await ctx.send(embed=embed)
                else:
                    await ctx.send("❌ This channel doesn't have a category.", delete_after=10)
                return

            elif target_lower == "me" or target_lower == "myself":
                # Show user's own ID only
                embed = discord.Embed(
                    title="🔍 Your ID",
                    color=discord.Color.from_str("#FFFFFF")
                )
                embed.description = f"**User:** {ctx.author.mention}"
                embed.add_field(name="Your Name",
                                value=ctx.author.name, inline=True)
                embed.add_field(
                    name="Your ID", value=f"`{ctx.author.id}`", inline=True)
                await ctx.send(embed=embed)
                return

            # Check if target is a mention
            if ctx.message.role_mentions:
                role = ctx.message.role_mentions[0]
            elif ctx.message.mentions:
                user = ctx.message.mentions[0]
            elif ctx.message.channel_mentions:
                channel = ctx.message.channel_mentions[0]
            else:
                # Try to parse as user ID
                try:
                    user_id = int(target)
                    user = ctx.guild.get_member(user_id)
                    if not user:
                        # Try to fetch user
                        try:
                            user = await ctx.guild.fetch_member(user_id)
                        except:
                            pass
                except ValueError:
                    # Try to parse as channel ID
                    try:
                        channel_id = int(target)
                        channel = ctx.guild.get_channel(channel_id)
                    except ValueError:
                        # Try to parse as role ID
                        try:
                            role_id = int(target)
                            role = ctx.guild.get_role(role_id)
                        except ValueError:
                            await ctx.send("❌ Could not find the specified target. Please mention a role, user, or channel, or provide a valid ID.\n\n**Keywords you can use:**\n- `server` - Show server ID\n- `channel` - Show current channel ID\n- `category` - Show current category ID\n- `me` - Show your own ID", delete_after=15)
                            return

        await self._handle_get_id_command(ctx, role=role, user=user, channel=channel, category=category, is_interaction=False)

    # =========================================================
    # MAIN PREFIX COMMAND
    # =========================================================
    @commands.command(name="links", aliases=["link"])
    async def links_prefix(self, ctx: commands.Context, *, option: str = None):
        """Get the most important links regarding teh bot

        Parameters:
        - `invite` or `bot`: Show only the bot invite link
        - `website` or `site`: Show only the website link
        - `setup` or `guide`: Show only the setup guide link
        - `dashboardsetup` or `dashboard setup`: Show only the dashboard setup guide link
        - `docs` or `documentation`: Show only the documentation link
        - `dashboard` or `dash`: Show only the dashboard link
        - `premium` or `prem`: Show only the premium link
        - `faq` or `question`: Show only the FAQ link
        - `support` or `server`: Show only the support server link
        - `email` or `contact`: Show only the email
        """
        # Map parameter strings to options
        if option:
            option_lower = option.lower()
            if "invite" in option_lower or "bot" in option_lower:
                await self._handle_links_command(ctx, option="invite", is_interaction=False)
                return
            elif "website" in option_lower or "site" in option_lower:
                await self._handle_links_command(ctx, option="website", is_interaction=False)
                return
            elif "dashboardsetup" in option_lower or "dashboard setup" in option_lower or "dash setup" in option_lower:
                await self._handle_links_command(ctx, option="dashboard-setup", is_interaction=False)
                return
            elif "setup" in option_lower or "guide" in option_lower:
                await self._handle_links_command(ctx, option="setup", is_interaction=False)
                return
            elif "docs" in option_lower or "documentation" in option_lower:
                await self._handle_links_command(ctx, option="docs", is_interaction=False)
                return
            elif "dashboard" in option_lower or "dash" in option_lower:
                await self._handle_links_command(ctx, option="dashboard", is_interaction=False)
                return
            elif "premium" in option_lower or "prem" in option_lower:
                await self._handle_links_command(ctx, option="premium", is_interaction=False)
                return
            elif "faq" in option_lower or "question" in option_lower:
                await self._handle_links_command(ctx, option="faq", is_interaction=False)
                return
            elif "support" in option_lower or "server" in option_lower:
                await self._handle_links_command(ctx, option="support", is_interaction=False)
                return
            elif "email" in option_lower or "contact" in option_lower or "mail" in option_lower:
                await self._handle_links_command(ctx, option="email", is_interaction=False)
                return
            elif "vote" in option_lower or "topgg" in option_lower:
                await self._handle_links_command(ctx, option="vote", is_interaction=False)
                return

        # If no valid option specified, show full menu
        await self._handle_links_command(ctx, option=None, is_interaction=False)

    # =========================================================
    # SLASH COMMAND GROUPS
    # =========================================================

    # Create slash command group for get commands
    get_group = app_commands.Group(
        name="get",
        description="Get various information"
    )

    @get_group.command(
        name="id",
        description="Get the ID of a role, user, channel, category, or show all current IDs"
    )
    @app_commands.describe(
        role="Get the ID of a role",
        user="Get the ID of a user",
        channel="Get the ID of a channel",
        category="Get the ID of a category"
    )
    async def get_id_slash(
        self,
        interaction: discord.Interaction,
        role: discord.Role = None,
        user: discord.User = None,
        channel: discord.TextChannel = None,
        category: discord.CategoryChannel = None
    ):
        await self._handle_get_id_command(interaction, role=role, user=user, channel=channel, category=category, is_interaction=True)

    @app_commands.command(
        name="links",
        description="Get the most important links regarding the bot"
    )
    @app_commands.choices(option=[
        app_commands.Choice(name="Bot Invite Link", value="invite"),
        app_commands.Choice(name="Website", value="website"),
        app_commands.Choice(name="Bot Setup Guide", value="setup"),
        app_commands.Choice(name="Dashboard Setup Guide",
                            value="dashboard-setup"),
        app_commands.Choice(name="Documentation", value="docs"),
        app_commands.Choice(name="Dashboard", value="dashboard"),
        app_commands.Choice(name="Premium", value="premium"),
        app_commands.Choice(name="FAQ", value="faq"),
        app_commands.Choice(name="Vote for Bot", value="vote"),
        app_commands.Choice(name="Support Server", value="support"),
        app_commands.Choice(name="Email", value="email")
    ])
    async def links_command(
        self,
        interaction: discord.Interaction,
        option: app_commands.Choice[str] = None
    ):
        option_value = option.value if option else None
        await self._handle_links_command(interaction, option=option_value, is_interaction=True)

    @app_commands.command(
        name="help",
        description="Get help with the bot and access important links"
    )
    async def help_command(self, interaction: discord.Interaction):
        """Slash command version of help"""
        await self._handle_help_command(interaction, is_interaction=True)


async def setup(bot):
    await bot.add_cog(BotLinks(bot))
