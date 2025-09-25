import nextcord
from nextcord.ext import commands
import asyncio
from typing import Dict, List, Optional
import datetime
import logging


class PurgeCog(commands.Cog, name="Purge"):

    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("PurgeCog")

    def store_channel_settings(self, channel) -> Dict:
        """Store all channel settings for recreation"""
        settings = {
            "name": channel.name,
            "topic": getattr(channel, "topic", None),
            "position": channel.position,
            "nsfw": getattr(channel, "nsfw", False),
            "category_id": channel.category_id,
            "slowmode_delay": channel.slowmode_delay,
            "type": channel.type,
            "overwrites": channel.overwrites,
            "bitrate": getattr(channel, "bitrate", None),
            "user_limit": getattr(channel, "user_limit", None),
            "rtc_region": getattr(channel, "rtc_region", None),
            "video_quality_mode": getattr(channel, "video_quality_mode", None),
            "default_auto_archive_duration": getattr(
                channel, "default_auto_archive_duration", None
            ),
            "permissions_synced": getattr(channel, "permissions_synced", False),
        }
        return settings

    async def get_channel_webhooks(self, channel) -> List[Dict]:
        """Get all webhooks from the channel"""
        try:
            webhooks = await channel.webhooks()
            webhook_data = []
            for webhook in webhooks:
                webhook_info = {
                    "name": webhook.name,
                    "avatar": await webhook.avatar.read() if webhook.avatar else None,
                }
                webhook_data.append(webhook_info)
            return webhook_data
        except nextcord.Forbidden:
            self.logger.warning(f"Cannot access webhooks in channel {channel.id}")
            return []
        except Exception as e:
            self.logger.error(f"Error getting webhooks: {str(e)}")
            return []

    @commands.command(name="purge", aliases=["clear"])
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int = None):
        """
        Clear messages from the channel
        Usage: !purge <number_of_messages>
        """
        if amount is None:
            await ctx.send("⚠️ Please specify the number of messages to delete!")
            return

        if amount <= 0:
            await ctx.send("⚠️ Please specify a positive number!")
            return

        try:
            deleted = await ctx.channel.purge(limit=amount + 1)
            embed = nextcord.Embed(
                title="✅ Messages Purged",
                description=f"Successfully deleted {len(deleted) - 1} messages!",
                color=0x00FF00,
                timestamp=datetime.datetime.utcnow(),
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}")
            confirm_message = await ctx.send(embed=embed)
            await asyncio.sleep(3)
            await confirm_message.delete()
        except nextcord.Forbidden:
            await ctx.send("❌ I don't have permission to delete messages!")
        except nextcord.HTTPException as e:
            await ctx.send(f"❌ An error occurred while deleting messages: {str(e)}")

    @commands.command(name="hardpurge")
    @commands.has_permissions(manage_channels=True, manage_roles=True)
    async def hardpurge(self, ctx):
        """
        Delete and recreate the channel with identical settings
        Usage: !hardpurge
        """
        try:
            # Store the channel's settings
            channel = ctx.channel
            settings = self.store_channel_settings(channel)
            webhook_data = await self.get_channel_webhooks(channel)

            # Create confirmation embed
            embed = nextcord.Embed(
                title="⚠️ Hard Purge Confirmation",
                description=(
                    "This will delete and recreate the channel with identical settings.\n\n"
                    "**The following will be preserved:**\n"
                    "✓ Channel permissions\n"
                    "✓ Role settings\n"
                    "✓ Channel settings (topic, slowmode, etc.)\n"
                    "✓ Webhooks\n"
                    "✓ Category and position\n\n"
                    "React with ✅ to confirm or ❌ to cancel."
                ),
                color=0xFF9900,
                timestamp=datetime.datetime.utcnow(),
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}")

            confirm_msg = await ctx.send(embed=embed)
            await confirm_msg.add_reaction("✅")
            await confirm_msg.add_reaction("❌")

            def check(reaction, user):
                return (
                    user == ctx.author
                    and str(reaction.emoji) in ["✅", "❌"]
                    and reaction.message.id == confirm_msg.id
                )

            try:
                reaction, user = await self.bot.wait_for(
                    "reaction_add", timeout=30.0, check=check
                )
                if str(reaction.emoji) == "❌":
                    await confirm_msg.delete()
                    await ctx.send("❌ Hard purge cancelled.", delete_after=5)
                    return
            except asyncio.TimeoutError:
                await confirm_msg.delete()
                await ctx.send(
                    "❌ Hard purge cancelled due to timeout.", delete_after=5
                )
                return

            # Create new channel
            new_channel = await ctx.guild.create_text_channel(
                name=settings["name"],
                category=ctx.guild.get_channel(settings["category_id"]),
                topic=settings["topic"],
                position=settings["position"],
                nsfw=settings["nsfw"],
                slowmode_delay=settings["slowmode_delay"],
                overwrites=settings["overwrites"],
                reason=f"Hard purge initiated by {ctx.author} (ID: {ctx.author.id})",
            )

            # Restore webhooks
            for webhook_info in webhook_data:
                try:
                    await new_channel.create_webhook(
                        name=webhook_info["name"],
                        avatar=webhook_info["avatar"],
                        reason="Restoring webhook after hard purge",
                    )
                except Exception as e:
                    self.logger.error(f"Error recreating webhook: {str(e)}")

            # Delete old channel
            await channel.delete(reason=f"Hard purge initiated by {ctx.author}")

            # Send confirmation
            embed = nextcord.Embed(
                title="✅ Channel Successfully Purged",
                description=(
                    "This channel has been recreated with all previous settings preserved.\n"
                    f"Purge completed at: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                ),
                color=0x00FF00,
            )
            embed.add_field(
                name="Initiated By",
                value=f"{ctx.author.mention} ({ctx.author.name}#{ctx.author.discriminator})",
            )
            await new_channel.send(embed=embed)

        except nextcord.Forbidden:
            await ctx.send(
                "❌ I don't have the required permissions to manage this channel!"
            )
        except nextcord.HTTPException as e:
            await ctx.send(f"❌ An error occurred: {str(e)}")
        except Exception as e:
            self.logger.error(f"Unexpected error in hardpurge: {str(e)}")
            await ctx.send(f"❌ An unexpected error occurred: {str(e)}")

    @purge.error
    @hardpurge.error
    async def purge_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            missing_perms = ", ".join(error.missing_permissions)
            await ctx.send(
                f"❌ You need the following permissions to use this command: {missing_perms}"
            )
        elif isinstance(error, commands.BadArgument):
            await ctx.send("❌ Please provide a valid number of messages to delete!")
        else:
            self.logger.error(f"Unexpected error: {str(error)}")
            await ctx.send(f"❌ An error occurred: {str(error)}")


def setup(bot):
    bot.add_cog(PurgeCog(bot))
