import nextcord
from nextcord.ext import commands
from nextcord.ui import View, Button, Select
from typing import Optional, Dict, List, Tuple


class HelpCogSelect(Select):
    """The dropdown menu to select a command category (Cog)."""

    def __init__(self, bot: commands.Bot, parent_view: "HelpMenu", cog_emojis: Dict[str, str]):
        self.bot = bot
        self.parent_view = parent_view
        self.cog_emojis = cog_emojis

        options = [
            nextcord.SelectOption(
                label="All Commands",
                description="Show all available commands.",
                emoji="📚",
                value="All Commands"
            )
        ]

        sorted_cogs = sorted(self.bot.cogs.items())

        for cog_name, cog in sorted_cogs:
            # Only show cogs that have at least one non-hidden command
            cog_commands_for_check = [cmd for cmd in cog.get_commands() if not cmd.hidden]
            if cog_commands_for_check:
                description = (
                    cog.description or f"Commands from the {cog_name} category."
                )
                # Ensure description is within Discord's limit
                max_desc_length = 90
                if len(description) > max_desc_length:
                    description = description[:max_desc_length] + "..."

                emoji = self.cog_emojis.get(cog_name)

                options.append(
                    nextcord.SelectOption(
                        label=cog_name,
                        description=description,
                        emoji=emoji,
                        value=cog_name
                    )
                )

        # Determine placeholder and disabled state based on final options list
        placeholder = "Choose a category..."
        select_disabled = (len(options) == 1 and options[0].value == "No Categories")
        if select_disabled:
             placeholder = "No categories available"


        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options,
            custom_id="help_cog_select",
            disabled = select_disabled
        )


    async def callback(self, interaction: nextcord.Interaction):
        try:
            if interaction.user != self.parent_view.ctx.author:
                return await interaction.response.send_message(
                    "This menu is not for you!", ephemeral=True
                )

            await interaction.response.defer()

            selected_cog = self.values[0]
            if selected_cog in self.parent_view.cog_commands:
                await self.parent_view.update_for_selection(selected_cog, interaction)
        except nextcord.errors.NotFound:
            # This can happen if the interaction or the original message is deleted.
            pass



class HelpMenu(View):
    """The main view for the help command, including pagination and a cog-selection dropdown."""

    def __init__(self, ctx, bot, commands_per_page=5, cog_emojis: Dict[str, str] = None):
        super().__init__(timeout=180.0)
        self.ctx = ctx
        self.bot = bot
        self.commands_per_page = commands_per_page
        self.current_page = 0
        self.selected_cog = "All Commands"
        self.cog_emojis = cog_emojis or {}


        self.cog_commands: Dict[str, List[Tuple[commands.Command, str]]] = {
            "All Commands": []
        }
        all_commands_list = []

        for cog_name, cog in sorted(bot.cogs.items(), key=lambda i: i[0]):
            cog_list = []
            cog_cmds = sorted(cog.get_commands(), key=lambda c: c.name)

            for cmd in cog_cmds:
                if cmd.hidden:
                    continue

                if isinstance(cmd, commands.Group):
                    cog_list.append((cmd, "group"))
                    all_commands_list.append((cmd, "group"))
                    for subcmd in sorted(cmd.commands, key=lambda sc: sc.name):
                        if not subcmd.hidden:
                            cog_list.append((subcmd, "subcommand"))
                            all_commands_list.append((subcmd, "subcommand"))
                elif cmd.parent is None: # Only add top-level commands
                    cog_list.append((cmd, "command"))
                    all_commands_list.append((cmd, "command"))

            if cog_list:
                self.cog_commands[cog_name] = cog_list


        # Build the "All Commands" list, removing duplicates and sorting
        seen_command_names = set()
        unique_all_commands_list = []
        for cmd_tuple in all_commands_list:
            cmd = cmd_tuple[0]
            if cmd.qualified_name not in seen_command_names:
                seen_command_names.add(cmd.qualified_name)
                unique_all_commands_list.append(cmd_tuple)

        self.cog_commands["All Commands"] = sorted(unique_all_commands_list, key=lambda t: t[0].qualified_name)


        self.add_item(HelpCogSelect(bot, self, cog_emojis=self.cog_emojis))

        self.update_command_list()


    def update_command_list(self):
        """Filters the command list based on the selected cog and updates pagination."""
        if self.selected_cog == "No Categories":
             self.current_commands = []
        else:
            self.current_commands = self.cog_commands.get(self.selected_cog, self.cog_commands.get("All Commands", []))

        num_commands = len(self.current_commands) if isinstance(self.current_commands, list) else 0

        self.max_pages = max(
            1, (num_commands - 1) // self.commands_per_page + 1
        )
        self.current_page = max(0, min(self.current_page, self.max_pages - 1))

        self.update_button_states()

    def _format_command_name(self, cmd: commands.Command, cmd_type: str) -> str:
        """Formats the command name for the embed, showing group/subcommand structure."""
        indent = ""
        icon = "📄"

        if cmd_type == "group":
            full_name = cmd.name
            icon = "📁"
        elif cmd_type == "subcommand":
             indent = "  "
             full_name = cmd.qualified_name
        else:
             full_name = cmd.name

        return f"{indent}{icon} `{self.ctx.prefix}{full_name}`"


    async def update_embed(self) -> nextcord.Embed:
        """Creates and returns the updated help embed with structured command list."""
        start = self.current_page * self.commands_per_page
        end = start + self.commands_per_page
        paginated_commands = self.current_commands[start:end]

        cog_desc = ""
        if self.selected_cog in self.bot.cogs:
             cog = self.bot.get_cog(self.selected_cog)
             if cog and cog.description:
                 cog_desc = f"\n\n*{cog.description}*"

        embed = nextcord.Embed(
            title=f"Help: {self.selected_cog}",
            description=f"Use `{self.ctx.prefix}help <command>` for detailed information." + cog_desc,
            color=nextcord.Color.blue(),
        )

        if not paginated_commands:
             if self.selected_cog != "All Commands" and self.selected_cog != "No Categories":
                 embed.description += f"\n\nNo commands found in the '{self.selected_cog}' category."
             elif self.selected_cog == "All Commands":
                 embed.description += "\n\nNo commands found across all categories."
        else:
            for cmd, cmd_type in paginated_commands:
                name = self._format_command_name(cmd, cmd_type)
                value = cmd.short_doc or "No description provided."

                if cmd_type == "group":
                    sub_count = len([c for c in cmd.commands if not c.hidden])
                    value = (cmd.short_doc or "No description provided.") + f"\n*This is a group with {sub_count} subcommand(s).*"

                embed.add_field(name=name, value=value, inline=False)

        embed.set_footer(text=f"Page {self.current_page + 1}/{self.max_pages}")
        return embed

    async def update_for_selection(
        self, selected_cog: str, interaction: nextcord.Interaction
    ):
        """Handles the logic when a new cog is selected from the dropdown."""
        self.selected_cog = selected_cog
        self.update_command_list()
        embed = await self.update_embed()
        try:
            await interaction.edit_original_message(embed=embed, view=self)
        except nextcord.errors.NotFound:
            pass


    def update_button_states(self):
        """Enables or disables pagination buttons."""
        is_single_page = self.max_pages <= 1
        has_commands = len(self.current_commands) > 0

        self.previous_page.disabled = self.current_page == 0 or is_single_page or not has_commands
        self.next_page.disabled = self.current_page >= self.max_pages - 1 or is_single_page or not has_commands


    @nextcord.ui.button(label="◀ Prev", style=nextcord.ButtonStyle.blurple, custom_id="help_prev_page")
    async def previous_page(self, button: Button, interaction: nextcord.Interaction):
        try:
            if interaction.user != self.ctx.author:
                return await interaction.response.send_message(
                    "This menu is not for you!", ephemeral=True
                )
            if button.disabled:
                return await interaction.response.defer()

            await interaction.response.defer()

            self.current_page -= 1
            self.update_button_states()
            await interaction.edit_original_message(
                embed=await self.update_embed(), view=self
            )
        except nextcord.errors.NotFound:
            pass

    @nextcord.ui.button(label="Next ▶", style=nextcord.ButtonStyle.blurple, custom_id="help_next_page")
    async def next_page(self, button: Button, interaction: nextcord.Interaction):
        try:
            if interaction.user != self.ctx.author:
                return await interaction.response.send_message(
                    "This menu is not for you!", ephemeral=True
                )
            if button.disabled:
                return await interaction.response.defer()

            await interaction.response.defer()

            self.current_page += 1
            self.update_button_states()
            await interaction.edit_original_message(
                embed=await self.update_embed(), view=self
            )
        except nextcord.errors.NotFound:
            pass


class HelpCog(commands.Cog, name="Help"):
    """Provides a detailed, interactive help command."""

    # Define your cog-to-emoji mapping here
    # Use the EXACT names of your Cogs as keys.
    # Values can be Unicode emojis (e.g., "👑") or custom server emojis.
    COG_EMOJIS = {
        "AI": "🤖",
        "Admin": "👑",
        "Moderation": "🔨",
        "Music": "🎶",
        "Utility": "🔧",
        "Fun": "😂",
        "Purge": "🧹",
        "Help": "❓",
        "Dynamic Prefix": "🎯",
        "System Stats": "💻",
        "Power": "⚡",
    }

    def __init__(self, bot):
        self.bot = bot
        self._original_help_command = bot.help_command
        self.bot.remove_command("help")

    def cog_unload(self):
        """Called when the cog is unloaded. Restore the original help command."""
        if self._original_help_command:
             self.bot.help_command = self._original_help_command


    def get_detailed_command_help(
        self, ctx: commands.Context, command: commands.Command
    ) -> nextcord.Embed:
        """Generates a detailed embed for a specific command, including subcommands and permissions."""
        embed = nextcord.Embed(
            title=f"Help: {command.qualified_name}", color=nextcord.Color.gold()
        )

        embed.add_field(
            name="Description",
            value=command.help or "No detailed description provided.",
            inline=False,
        )

        usage = command.usage or f"{command.qualified_name} {command.signature}"
        embed.add_field(name="Usage", value=f"```\n{ctx.prefix}{usage.strip()}\n```", inline=False)


        if isinstance(command, commands.Group):
            subcommands_list = [
                f"`{sub.name}` - {sub.short_doc or 'No description'}"
                for sub in command.commands
                if not sub.hidden
            ]
            if subcommands_list:
                 embed.add_field(name="Subcommands", value="\n".join(subcommands_list), inline=False)


        if command.aliases:
            embed.add_field(
                name="Aliases",
                value=", ".join(f"`{a}`" for a in command.aliases),
                inline=False,
            )

        # Get check names, excluding the internal `Command.can_run` check proxy
        checks = [check.__qualname__.split('.')[-1] for check in command.checks if not getattr(check, "__commands_internal__", False)]

        if checks:
             embed.add_field(name="Permissions/Checks", value="\n".join(f"- {check}" for check in checks), inline=False)

        embed.set_footer(text="<> = Required | [] = Optional")
        return embed

    @commands.command(
        name="help",
        help="Shows this help menu or details for a specific command.",
        short_doc="Shows help for commands.",
    )
    async def help_command(self, ctx, *, command_name: Optional[str] = None):
        """Shows an interactive help menu or detailed help for a specific command/subcommand."""
        if command_name:
            command = self.bot.get_command(command_name)
            can_run = False
            if command:
                try:
                    can_run = await command.can_run(ctx)
                except commands.CommandError:
                    can_run = False
                except Exception as e:
                    print(f"Error checking command permission for {command.qualified_name}: {e}")
                    can_run = False

            if not command or command.hidden or not can_run:
                 return await ctx.send(f"❌ Command or subcommand `{command_name}` not found or you do not have permission to see it.")

            await ctx.send(embed=self.get_detailed_command_help(ctx, command))
        else:
            menu = HelpMenu(ctx, self.bot, cog_emojis=self.COG_EMOJIS)

            select_item = next((item for item in menu.children if isinstance(item, HelpCogSelect)), None)
            # Check if the select is disabled or there are no current commands
            if (select_item and select_item.disabled) or not menu.current_commands:
                 await ctx.send("No commands or command categories found.")
                 return

            message = await ctx.send(embed=await menu.update_embed(), view=menu)
            menu.message = message


def setup(bot):
    bot.add_cog(HelpCog(bot))
