import nextcord
from nextcord.ext import commands
import random
from typing import Optional

# A tuple of classic Magic 8-Ball responses
_EIGHT_BALL_ANSWERS = (
    # Affirmative Answers
    "It is certain.",
    "It is decidedly so.",
    "Without a doubt.",
    "Yes, definitely.",
    "You may rely on it.",
    "As I see it, yes.",
    "Most likely.",
    "Outlook good.",
    "Yes.",
    "Signs point to yes.",
    # Non-committal Answers
    "Reply hazy, try again.",
    "Ask again later.",
    "Better not tell you now.",
    "Cannot predict now.",
    "Concentrate and ask again.",
    # Negative Answers
    "Don't count on it.",
    "My reply is no.",
    "My sources say no.",
    "Outlook not so good.",
    "Very doubtful.",
)


class FunCog(commands.Cog, name="Fun"):
    """
    A collection of fun, miscellaneous commands for everyone to enjoy.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(
        name="ball", aliases=["8ball"], help="Asks the magic 8-ball a question."
    )
    async def eight_ball(
        self, ctx: commands.Context, *, question: Optional[str] = None
    ):
        """
        Consult the magic 8-ball for answers.

        Usage:
        - `!ball Is today a good day?`
        """
        if not question:
            embed = nextcord.Embed(
                title="❓ You need to ask a question!",
                description="The magic 8-ball can't answer if it doesn't know the question.",
                color=nextcord.Color.orange(),
            )
            return await ctx.send(embed=embed)

        answer = random.choice(_EIGHT_BALL_ANSWERS)
        embed_description = f"```\nQ: {question}\nA: {answer}\n```"

        embed = nextcord.Embed(
            color=nextcord.Color.blurple(), description=embed_description
        )
        embed.set_author(
            name="The Magic 8-Ball has spoken!", icon_url=self.bot.user.avatar.url
        )
        embed.set_footer(text=f"Asked by {ctx.author.display_name}")
        await ctx.send(embed=embed)

    @commands.command(
        name="love",
        aliases=["ship"],
        help="Calculates the love compatibility between two users.",
    )
    async def love_calculator(
        self,
        ctx: commands.Context,
        user1: Optional[nextcord.Member] = None,
        user2: Optional[nextcord.Member] = None,
    ):
        """
        Calculates a love percentage between you and another user, or between two other users.

        Usage:
        - `!love @KaiTy_Ez` (ships you with KaiTy_Ez)
        - `!love @user1 @user2` (ships user1 with user2)
        """
        # --- Determine the two people to be shipped ---
        if user1 is None:
            return await ctx.send(
                "You need to mention at least one person to calculate the love!"
            )
        elif user2 is None:
            # Ship the author with the mentioned user
            member1 = ctx.author
            member2 = user1
        else:
            # Ship the two mentioned users
            member1 = user1
            member2 = user2

        # --- Calculate a consistent percentage based on user IDs ---
        # By combining and seeding, the result is always the same for the same pair.
        seed_value = member1.id + member2.id
        random.seed(seed_value)
        love_percentage = random.randint(0, 100)
        random.seed()  # Reset the seed for other commands

        # --- Determine the remark and color based on the percentage ---
        if love_percentage <= 10:
            remark = "Not a great match... awkward."
            color = nextcord.Color.red()
        elif love_percentage <= 30:
            remark = "Maybe just friends?"
            color = nextcord.Color.orange()
        elif love_percentage <= 60:
            remark = "There's a chance! It could work."
            color = nextcord.Color.gold()
        elif love_percentage <= 80:
            remark = "Things are looking pretty spicy! 🔥"
            color = nextcord.Color.magenta()
        elif love_percentage <= 99:
            remark = "A match made in heaven! 💖"
            color = nextcord.Color.fuchsia()
        else:  # 100%
            remark = "SOULMATES! It's destiny! ❤️"
            color = nextcord.Color.from_rgb(255, 105, 180)  # Hot Pink

        if love_percentage == 69:
            remark = "Nice."

        # --- Create the visual love meter ---
        filled_blocks = int(love_percentage / 10)
        empty_blocks = 25 - filled_blocks
        love_meter = "■" * filled_blocks + "□" * empty_blocks

        # --- Build and send the final embed ---
        embed = nextcord.Embed(
            title=f"💖 Love Calculator 💖",
            description=(
                f"Let's see the compatibility between **{member1.display_name}** and **{member2.display_name}**!\n\n"
                f"**`{love_meter}`**\n\n"
                f"Their compatibility is **{love_percentage}%**!\n\n"
                f"> *{remark}*"
            ),
            color=color,
        )
        embed.set_footer(text=f"Requested by {ctx.author.display_name}")
        await ctx.send(embed=embed)


def setup(bot: commands.Bot):
    """Adds the cog to the bot."""
    bot.add_cog(FunCog(bot))
