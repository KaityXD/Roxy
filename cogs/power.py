import nextcord
from nextcord.ext import commands
import random
import asyncio
import os
import sys


class PowerCog(commands.Cog, name="Power"):
    """
    Provides secure commands to restart or shut down the bot.
    Only the bot owner can use these commands.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(
        name="restart",
        help="Restarts the bot after a confirmation.",
        brief="Restarts the bot.",
    )
    @commands.is_owner()
    async def restart_command(self, ctx: commands.Context):
        """
        Shuts down and restarts the bot.
        A confirmation code is required to prevent accidental restarts.
        """
        confirmation_code = str(random.randint(100000, 999999))

        prompt_embed = nextcord.Embed(
            title="⚠️ Bot Restart Confirmation",
            description=(
                f"Please type the following code to confirm the **restart**:\n\n"
                f"**`{confirmation_code}`**\n\n"
                f"*You have 15 seconds to respond. This action is irreversible.*"
            ),
            color=nextcord.Color.orange(),
        )
        await ctx.send(embed=prompt_embed)

        def check(message: nextcord.Message) -> bool:
            return message.author == ctx.author and message.channel == ctx.channel

        try:
            response_message: nextcord.Message = await self.bot.wait_for(
                "message", timeout=15.0, check=check
            )

            if response_message.content == confirmation_code:
                await ctx.send(
                    embed=nextcord.Embed(
                        title="✅ Restarting...",
                        description="Confirmation accepted. The bot will now restart.",
                        color=nextcord.Color.green(),
                    )
                )
                # This command replaces the current process with a new one.
                os.execv(sys.executable, ["python"] + sys.argv)
            else:
                await ctx.send(
                    embed=nextcord.Embed(
                        title="❌ Incorrect Code",
                        description="Restart cancelled.",
                        color=nextcord.Color.red(),
                    )
                )
        except asyncio.TimeoutError:
            await ctx.send(
                embed=nextcord.Embed(
                    title="⏰ Timed Out",
                    description="Restart cancelled.",
                    color=nextcord.Color.red(),
                )
            )

    @commands.command(
        name="shutdown",
        aliases=["poweroff", "turnoff"],
        help="Shuts down the bot after a confirmation.",
        brief="Shuts down the bot.",
    )
    @commands.is_owner()
    async def shutdown_command(self, ctx: commands.Context):
        """
        Shuts down the bot completely.
        A confirmation code is required to prevent accidental shutdowns.
        """
        confirmation_code = str(random.randint(100000, 999999))

        prompt_embed = nextcord.Embed(
            title="🛑 Bot Shutdown Confirmation",
            description=(
                f"Please type the following code to confirm the **shutdown**:\n\n"
                f"**`{confirmation_code}`**\n\n"
                f"**Warning:** This action is final. The bot will go offline and must be started manually."
            ),
            color=nextcord.Color.dark_red(),
        )
        await ctx.send(embed=prompt_embed)

        def check(message: nextcord.Message) -> bool:
            return message.author == ctx.author and message.channel == ctx.channel

        try:
            response_message: nextcord.Message = await self.bot.wait_for(
                "message", timeout=15.0, check=check
            )

            if response_message.content == confirmation_code:
                await ctx.send(
                    embed=nextcord.Embed(
                        title="✅ Shutting Down...",
                        description="Confirmation accepted. Goodbye!",
                        color=nextcord.Color.green(),
                    )
                )
                # This command gracefully closes the bot's connection and stops the script.
                await self.bot.close()
            else:
                await ctx.send(
                    embed=nextcord.Embed(
                        title="❌ Incorrect Code",
                        description="Shutdown cancelled.",
                        color=nextcord.Color.red(),
                    )
                )
        except asyncio.TimeoutError:
            await ctx.send(
                embed=nextcord.Embed(
                    title="⏰ Timed Out",
                    description="Shutdown cancelled.",
                    color=nextcord.Color.red(),
                )
            )


def setup(bot: commands.Bot):
    """Adds the cog to the bot."""
    bot.add_cog(PowerCog(bot))
