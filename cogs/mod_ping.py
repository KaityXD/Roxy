import nextcord
from nextcord.ext import commands
from nextcord import Interaction, Embed, ButtonStyle, Color, Role
from nextcord.ui import View, Button, Modal, TextInput
import sqlite3
import asyncio
from datetime import datetime, timedelta

class HelpRequestView(View):
    def __init__(self, interaction: Interaction, help_type: str, description: str, categories: list, mod_role_ids: list):
        super().__init__(timeout=None)
        self.interaction = interaction
        self.help_type = help_type
        self.description = description
        self.requester = interaction.user
        self.categories = categories
        self.status = "open"
        self.assigned_helper = None
        self.mod_role_ids = mod_role_ids

    @nextcord.ui.button(label="Assign", style=ButtonStyle.green)
    async def assign_help(self, button: Button, interaction: Interaction):
        # Check if the user has a mod role
        if not any(role.id in self.mod_role_ids for role in interaction.user.roles):
            await interaction.response.send_message(
                "You do not have the necessary permissions to assign help requests.",
                ephemeral=True
            )
            return
        # Prevent self-assignment or multiple assignments
        if interaction.user == self.requester:
            await interaction.response.send_message("You cannot assign help to yourself.", ephemeral=True)
            return


        if self.assigned_helper:
            await interaction.response.send_message(f"This request is already assigned to {self.assigned_helper.mention}.", ephemeral=True)
            return

        # Update the view and message to show assignment
        self.assigned_helper = interaction.user
        self.status = "in-progress"

        # Create an updated embed
        embed = Embed(
            title=f"Help Request: {self.help_type}",
            description=self.description,
            color=Color.green()
        )
        embed.add_field(name="Requester", value=self.requester.mention, inline=True)
        embed.add_field(name="Assigned Helper", value=self.assigned_helper.mention, inline=True)
        embed.add_field(name="Status", value="In Progress", inline=False)
        embed.add_field(name="Categories", value=", ".join(self.categories), inline=False)
        embed.set_footer(text=f"Assigned at {datetime.now().strftime('%Y-%m-%d %H:%M')}")

        await self.interaction.edit_original_message(embed=embed, view=self)
        await interaction.response.send_message(f"You have been assigned to help {self.requester.mention}.", ephemeral=False)

    @nextcord.ui.button(label="Close Request", style=ButtonStyle.red)
    async def close_request(self, button: Button, interaction: Interaction):
        # Only assigned helper or original requester can close
        if interaction.user not in [self.requester, self.assigned_helper]:
            await interaction.response.send_message("You are not authorized to close this request.", ephemeral=True)
            return

        self.status = "closed"

        # Create a closing embed
        embed = Embed(
            title=f"Closed Help Request: {self.help_type}",
            description=self.description,
            color=Color.red()
        )
        embed.add_field(name="Requester", value=self.requester.mention, inline=True)
        embed.add_field(name="Assigned Helper", value=self.assigned_helper.mention if self.assigned_helper else "Unassigned", inline=True)
        embed.add_field(name="Status", value="Closed", inline=False)
        embed.add_field(name="Categories", value=", ".join(self.categories), inline=False)
        embed.set_footer(text=f"Closed by {interaction.user.name} at {datetime.now().strftime('%Y-%m-%d %H:%M')}")

        await self.interaction.edit_original_message(embed=embed, view=None)
        await interaction.response.send_message("Help request has been closed.", ephemeral=False)

class HelpRequestCog(commands.Cog, name="Mod ping"):
    def __init__(self, bot):
        self.bot = bot
        # Use a more robust database connection
        self.conn = sqlite3.connect("db/help_requests.db")
        self.create_tables()

    def create_tables(self):
        with self.conn:
            # Table to store help request categories
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS help_categories (
                guild_id INTEGER,
                category_name TEXT,
                PRIMARY KEY (guild_id, category_name)
            )
            """)

            # Table to store mod roles for each guild
            self.conn.execute("""
            CREATE TABLE IF NOT EXISTS mod_roles (
                guild_id INTEGER,
                role_id INTEGER,
                PRIMARY KEY (guild_id, role_id)
            )
            """)

    def get_mod_roles(self, guild_id):
        """Retrieve mod role IDs for a specific guild."""
        with self.conn:
            roles = self.conn.execute(
                "SELECT role_id FROM mod_roles WHERE guild_id = ?",
                (guild_id,)
            ).fetchall()
        return [role[0] for role in roles]

    @nextcord.slash_command(name="modping", description="Manage help request system.")
    async def help_system(self, interaction: Interaction):
        pass

    @help_system.subcommand(name="role", description="Add a mod role for help requests.")
    async def add_mod_role(self, interaction: Interaction, role: Role):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Only administrators can add mod roles.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        with self.conn:
            # Remove the previous mod role for this guild
            self.conn.execute("DELETE FROM mod_roles WHERE guild_id = ?", (guild_id,))

            # Insert the new mod role
            self.conn.execute("""
                INSERT INTO mod_roles (guild_id, role_id)
                VALUES (?, ?)
            """, (guild_id, role.id))

        await interaction.response.send_message(
            f"Mod role updated to '{role.name}'. Previous role (if any) has been removed.",
            ephemeral=True
        )

    @help_system.subcommand(name="addcategory", description="Add a help request category.")
    async def add_category(self, interaction: Interaction, category: str):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Only administrators can add categories.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        with self.conn:
            self.conn.execute("INSERT OR IGNORE INTO help_categories (guild_id, category_name) VALUES (?, ?)",
                               (guild_id, category.lower()))

        await interaction.response.send_message(f"Category '{category}' added to help system.", ephemeral=True)

    @help_system.subcommand(name="listcategories", description="List available help categories.")
    async def list_categories(self, interaction: Interaction):
        guild_id = interaction.guild.id
        with self.conn:
            categories = self.conn.execute("SELECT category_name FROM help_categories WHERE guild_id = ?",
                                           (guild_id,)).fetchall()

        if not categories:
            await interaction.response.send_message("No help categories have been set up.", ephemeral=True)
            return

        category_list = [cat[0] for cat in categories]
        embed = Embed(title="Help Categories", description="\n".join(category_list), color=Color.blue())
        await interaction.response.send_message(embed=embed, ephemeral=False)

    @nextcord.slash_command(name="helprequest", description="Create a help request.")
    async def help_request(self, interaction: Interaction):
        # Fetch available categories for this guild
        guild_id = interaction.guild.id
        with self.conn:
            categories = self.conn.execute("SELECT category_name FROM help_categories WHERE guild_id = ?",
                                           (guild_id,)).fetchall()

        if not categories:
            await interaction.response.send_message("No help categories are available. Ask an admin to set up categories first.", ephemeral=True)
            return

        # Get mod roles for this guild
        mod_role_ids = self.get_mod_roles(guild_id)

        # Create a modal for detailed help request
        class HelpRequestModal(Modal):
            def __init__(self, categories):
                super().__init__("Help Request Details", timeout=300)

                self.help_type = TextInput(
                    label="Help Type",
                    style=nextcord.TextInputStyle.short,
                    placeholder="Briefly describe the type of help",
                    max_length=50,
                    required=True
                )
                self.add_item(self.help_type)

                self.description = TextInput(
                    label="Detailed Description",
                    style=nextcord.TextInputStyle.paragraph,
                    placeholder="Provide detailed information about your help request",
                    max_length=500,
                    required=True
                )
                self.add_item(self.description)

                self.selected_categories = TextInput(
                    label="Categories (comma-separated)",
                    style=nextcord.TextInputStyle.short,
                    placeholder=f"Choose from: {', '.join([cat[0] for cat in categories])}",
                    max_length=100,
                    required=True
                )
                self.add_item(self.selected_categories)

            async def callback(self, interaction: Interaction):
                # Validate categories
                input_categories = [cat.strip().lower() for cat in self.selected_categories.value.split(',')]
                valid_categories = [cat[0] for cat in categories]

                invalid_categories = set(input_categories) - set(valid_categories)
                if invalid_categories:
                    await interaction.response.send_message(
                        f"Invalid categories: {', '.join(invalid_categories)}. Please choose from available categories.",
                        ephemeral=True
                    )
                    return

                # Create help request embed and view
                embed = Embed(
                    title=f"Ping Request: {self.help_type.value}",
                    description=self.description.value,
                    color=Color.orange()
                )
                embed.add_field(name="Requester", value=interaction.user.mention, inline=True)
                embed.add_field(name="Categories", value=", ".join(input_categories), inline=True)
                embed.set_footer(text=f"Requested at {datetime.now().strftime('%Y-%m-%d %H:%M')}")

                view = HelpRequestView(
                    interaction,
                    self.help_type.value,
                    self.description.value,
                    input_categories,
                    mod_role_ids
                )

                # Send the help request message
                response_message = await interaction.response.send_message(embed=embed, view=view)

                # Ping mod roles if any exist
                if mod_role_ids:
                    # Construct ping message for mod roles
                    mod_mentions = " ".join([f"<@&{role_id}>" for role_id in mod_role_ids])
                    await interaction.followup.send(f"Attention moderators: {mod_mentions}", ephemeral=False)

        # Show the modal
        modal = HelpRequestModal(categories)
        await interaction.response.send_modal(modal)

    def cog_unload(self):
        # Properly close the database connection when the cog is unloaded
        self.conn.close()

def setup(bot):
    bot.add_cog(HelpRequestCog(bot))