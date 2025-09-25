import nextcord
from nextcord.ext import commands
from nextcord.ui import Button, View

class AvatarView(View):
    """A view with buttons to switch between avatar types."""
    def __init__(self, member: nextcord.Member):
        super().__init__(timeout=180)  # View times out after 3 minutes
        self.member = member

        # Add a link button that doesn't have a callback
        self.download_button = Button(label="Download", style=nextcord.ButtonStyle.link, url=member.display_avatar.url)
        self.add_item(self.download_button)

    @nextcord.ui.button(label="Server Avatar", style=nextcord.ButtonStyle.primary, emoji="🌐")
    async def server_avatar_button(self, button: Button, interaction: nextcord.Interaction):
        """Shows the member's server-specific avatar."""
        embed = interaction.message.embeds[0]
        embed.title = f"{self.member.display_name}'s Server Avatar"
        embed.set_image(url=self.member.display_avatar.url)
        # Update the download button's URL
        self.download_button.url = self.member.display_avatar.url
        await interaction.response.edit_message(embed=embed, view=self)

    @nextcord.ui.button(label="Global Avatar", style=nextcord.ButtonStyle.secondary, emoji="🌍")
    async def global_avatar_button(self, button: Button, interaction: nextcord.Interaction):
        """Shows the member's global (default) avatar."""
        # A user might not have a global avatar if they only have a server avatar
        global_avatar_url = self.member.avatar.url if self.member.avatar else self.member.default_avatar.url
        
        embed = interaction.message.embeds[0]
        embed.title = f"{self.member.display_name}'s Global Avatar"
        embed.set_image(url=global_avatar_url)
        # Update the download button's URL
        self.download_button.url = global_avatar_url
        await interaction.response.edit_message(embed=embed, view=self)

class Avatar(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name='avatar', aliases=['av', 'pfp'])
    async def avatar(self, ctx, member: nextcord.Member = None):
        """Displays an interactive avatar embed with buttons."""
        target_member = member or ctx.author
        
        embed = nextcord.Embed(
            title=f"{target_member.display_name}'s Server Avatar",
            color=nextcord.Color.green()
        )
        embed.set_image(url=target_member.display_avatar.url)
        embed.set_footer(text=f"Requested by {ctx.author.display_name}")

        # Send the message with the view (buttons)
        await ctx.send(embed=embed, view=AvatarView(member=target_member))

def setup(bot):
    bot.add_cog(Avatar(bot))