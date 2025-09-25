import nextcord
from nextcord.ext import commands
import time


class Ping(commands.Cog, name="Utility"):
    """
    A cog with utility commands, including a detailed ping command.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(
        name="ping",
        help="Checks the bot's latency and response time.",
        short_doc="Check bot latency.",
    )
    async def _ping(self, ctx: commands.Context):
        """
        Calculates and displays the bot's WebSocket and API latency.

        - API Latency (RTT): The time it takes for a message to be sent and acknowledged by Discord.
        - WebSocket Latency: The bot's heartbeat latency to Discord.
        """

        # --- Create the initial "Pinging..." embed ---
        initial_embed = nextcord.Embed(
            title="🏓 Pinging...",
            description="Calculating latency...",
            color=nextcord.Color.light_grey(),
        )

        # --- Send the message and record the time ---
        # time.monotonic() is a reliable way to measure time intervals
        start_time = time.monotonic()
        message = await ctx.send(embed=initial_embed)
        end_time = time.monotonic()

        # --- Calculate the latencies ---
        # Round Trip Time (API Latency)
        api_latency = round((end_time - start_time) * 1000)

        # WebSocket Latency
        ws_latency = round(self.bot.latency * 1000)

        # --- Determine the embed color based on API latency ---
        if api_latency < 150:
            color = nextcord.Color.green()
        elif api_latency < 300:
            color = nextcord.Color.yellow()
        else:
            color = nextcord.Color.red()

        # --- Create the final, detailed embed ---
        final_embed = nextcord.Embed(title="🏓 Pong!", color=color)
        final_embed.add_field(
            name="API Latency (RTT)",
            value=f"**`{api_latency}ms`**\n*(Time to send and edit a message)*",
            inline=True,
        )
        final_embed.add_field(
            name="WebSocket Latency",
            value=f"**`{ws_latency}ms`**\n*(Bot's heartbeat connection)*",
            inline=True,
        )
        final_embed.set_footer(
            text=f"Requested by {ctx.author.display_name}",
            icon_url=ctx.author.display_avatar.url,
        )

        # --- Edit the original message with the final embed ---
        await message.edit(embed=final_embed)


def setup(bot: commands.Bot):
    bot.add_cog(Ping(bot))
