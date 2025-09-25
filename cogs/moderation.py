import nextcord
from nextcord.ext import commands
import aiosqlite
import datetime
import pytimeparse
import os
from utils.katlog import logger  # Assuming katlog is your logging setup
import traceback
import asyncio


# --- Generic Embed Creator ---
# Using a default color for consistency across feedback embeds
def create_base_embed(
    title: str, description: str, color: int = 0x7289DA
) -> nextcord.Embed:
    """Creates a standardized base embed with a default color."""
    embed = nextcord.Embed(title=title, description=description, color=color)
    return embed


class Moderation(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.db_path = "db/moderation.db"
        bot.loop.create_task(self.initial_cog_setup())

    async def initial_cog_setup(self):
        if not os.path.exists("db"):
            try:
                os.makedirs("db")
                logger.info("Moderation database directory 'db/' created.")
            except OSError as e:
                logger.error(
                    f"Failed to create database directory 'db/': {e}", exc_info=True
                )
        else:
            pass

    def _get_guild_table_name(self, guild_id: int, base_name: str) -> str:
        return f"{base_name}_{guild_id}"

    async def _ensure_guild_tables_exist(self, guild_id: int):
        cases_table_name = self._get_guild_table_name(guild_id, "cases")
        mod_log_table_name = self._get_guild_table_name(guild_id, "mod_log_channels")
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {cases_table_name} (
                        case_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        moderator_id INTEGER NOT NULL,
                        action TEXT NOT NULL,
                        reason TEXT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        duration TEXT
                    )
                """
                )
                await db.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {mod_log_table_name} (
                        singleton_id INTEGER PRIMARY KEY DEFAULT 1 CHECK (singleton_id = 1),
                        channel_id INTEGER NOT NULL
                    )
                """
                )
                await db.commit()
            logger.debug(
                f"Ensured tables for guild {guild_id} exist: {cases_table_name}, {mod_log_table_name}"
            )
        except Exception as e:
            logger.error(
                f"Failed to ensure/create tables for guild {guild_id}: {e}",
                exc_info=True,
            )
            # Re-raise if needed, but for setup, logging is often sufficient.
            # raise

    async def create_case(
        self, guild_id, user_id, moderator_id, action, reason=None, duration=None
    ):
        await self._ensure_guild_tables_exist(guild_id)
        table_name = self._get_guild_table_name(guild_id, "cases")
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    f"""INSERT INTO {table_name}
                       (user_id, moderator_id, action, reason, duration)
                       VALUES (?, ?, ?, ?, ?)""",
                    (user_id, moderator_id, action, reason, duration),
                )
                await db.commit()
                case_id = cursor.lastrowid
                logger.info(
                    f"Created case #{case_id} ({action}) for user {user_id} in guild {guild_id} (table {table_name})"
                )
                return case_id
        except Exception as e:
            logger.error(f"Failed to create case in {table_name}: {e}", exc_info=True)
            return None

    async def get_case(self, guild_id: int, case_id: int):
        await self._ensure_guild_tables_exist(guild_id)
        table_name = self._get_guild_table_name(guild_id, "cases")
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    f"SELECT * FROM {table_name} WHERE case_id = ?", (case_id,)
                ) as cursor:
                    case_data = await cursor.fetchone()
                    if case_data:
                        columns = [desc[0] for desc in cursor.description]
                        return dict(zip(columns, case_data))
                    return None
        except Exception as e:
            logger.error(
                f"Failed to get case {case_id} from {table_name}: {e}", exc_info=True
            )
            return None

    async def get_user_cases(self, guild_id: int, user_id: int):
        await self._ensure_guild_tables_exist(guild_id)
        table_name = self._get_guild_table_name(guild_id, "cases")
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    f"SELECT * FROM {table_name} WHERE user_id = ? ORDER BY case_id DESC",
                    (user_id,),
                ) as cursor:
                    cases_data = await cursor.fetchall()
                    if cases_data:
                        columns = [desc[0] for desc in cursor.description]
                        return [dict(zip(columns, case_row)) for case_row in cases_data]
                    return []
        except Exception as e:
            logger.error(
                f"Failed to get user cases for {user_id} from {table_name}: {e}",
                exc_info=True,
            )
            return []

    def _create_mod_log_embed(
        self,
        *,
        ctx: commands.Context,
        title: str,
        description: str,
        member: nextcord.Member | nextcord.User,
        moderator: nextcord.Member | nextcord.User,
        case_id: int,
        color: int = 0xE74C3C,
        **kwargs,
    ) -> nextcord.Embed:
        """Creates the specific embed format for the moderation log channel."""
        embed = nextcord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(
            name="User",
            value=f"{member.mention} ({member.name})\nID: {member.id}",
            inline=True,
        )
        embed.add_field(
            name="Moderator",
            value=f"{moderator.mention} ({moderator.name})\nID: {moderator.id}",
            inline=True,
        )
        for key, value in kwargs.items():
            if value:
                formatted_key = key.replace("_", " ").title()
                embed.add_field(
                    name=formatted_key, value=str(value)[:1024], inline=False
                )
        embed.set_footer(text=f"Case ID: #{case_id} (Guild Local) | {ctx.guild.name}")
        return embed

    # --- New Helper for Command Feedback Embeds ---
    async def _send_feedback_embed(
        self,
        ctx: commands.Context,
        title: str,
        description: str,
        color: int = 0x7289DA,  # Default Discord Blurple
    ):
        """Sends a standardized feedback embed to the user who invoked the command."""
        embed = create_base_embed(title, description, color)
        await ctx.send(embed=embed)

    async def _send_dm_notification(
        self,
        *,
        member: nextcord.Member | nextcord.User,
        guild: nextcord.Guild,
        action_title: str,
        reason: str | None,
        color: int,
        duration: str | None = None,
        expires_timestamp: int | None = None,
    ):
        embed = nextcord.Embed(
            title=f"Your moderation status in {guild.name} has been updated",
            color=color,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        embed.description = f"You have been {action_title}."
        embed.add_field(
            name="Reason", value=reason or "No reason provided.", inline=False
        )
        if duration:
            embed.add_field(name="Duration", value=duration, inline=False)
        if expires_timestamp:
            embed.add_field(
                name="Expires", value=f"<t:{expires_timestamp}:R>", inline=False
            )
        try:
            if hasattr(member, "send"):
                await member.send(embed=embed)
                logger.info(
                    f"Sent DM notification ({action_title}) to {member} ({member.id})"
                )
            else:
                logger.warning(
                    f"Could not send DM notification ({action_title}) to {member} ({member.id}): Object lacks 'send' method (likely User object)."
                )
        except nextcord.Forbidden:
            logger.warning(
                f"Could not send DM notification ({action_title}) to {member} ({member.id}): DMs disabled or bot blocked."
            )
        except Exception as e:
            logger.error(
                f"Failed to send DM notification ({action_title}) to {member} ({member.id}): {e}",
                exc_info=True,
            )

    # Helper for 2-step confirmation
    async def _prompt_confirmation(
        self,
        ctx: commands.Context,
        target_user: nextcord.User | nextcord.Member,
        action_name: str,
        reason: str | None,
        timeout_seconds: int = 30,
    ) -> tuple[bool, nextcord.Message | None]:
        """
        Prompts the user for confirmation for a moderation action.
        Returns a tuple: (confirmed: bool, confirmation_message: nextcord.Message | None)
        """
        confirm_embed = nextcord.Embed(
            title=f"Confirmation: {action_name.title()} User",
            description=f"Are you sure you want to {action_name.lower()} {target_user.mention} ({target_user.id})?",
            color=self.get_action_color(action_name.lower()),
        )
        if reason:
            confirm_embed.add_field(name="Reason", value=reason, inline=False)
        confirm_embed.set_footer(
            text=f"React with ✅ to confirm or ❌ to cancel within {timeout_seconds} seconds."
        )

        confirm_message = None
        try:
            confirm_message = await ctx.send(embed=confirm_embed)
            await confirm_message.add_reaction("✅")
            await confirm_message.add_reaction("❌")
        except nextcord.HTTPException as e:
            logger.error(
                f"Failed to send confirmation message or add reactions for {action_name} on {target_user.id}: {e}"
            )
            await self._send_feedback_embed(
                ctx,
                "Action Failed",
                "Could not send confirmation prompt. Please check my permissions (Send Messages, Add Reactions).",
                nextcord.Color.red(),
            )
            return False, confirm_message  # confirm_message might be None here

        if not confirm_message:  # If sending the message failed
            return False, None

        def check(reaction, user):
            return (
                user == ctx.author
                and reaction.message.id == confirm_message.id
                and str(reaction.emoji) in ["✅", "❌"]
            )

        try:
            reaction, _ = await self.bot.wait_for(
                "reaction_add", timeout=float(timeout_seconds), check=check
            )
            if str(reaction.emoji) == "✅":
                return True, confirm_message
            else:  # ❌
                return False, confirm_message
        except asyncio.TimeoutError:
            return False, confirm_message  # Timed out, treat as cancellation
        except Exception as e:
            logger.error(
                f"Error during {action_name} confirmation wait for {target_user.id}: {e}",
                exc_info=True,
            )
            return False, confirm_message  # Treat as cancellation

    @commands.command()
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(
        kick_members=True, add_reactions=True, manage_messages=True
    )
    async def kick(self, ctx, member: nextcord.Member, *, reason: str = None):
        """Kicks a member from the server with an optional reason."""
        await self._ensure_guild_tables_exist(ctx.guild.id)
        if member == ctx.author:
            return await self._send_feedback_embed(
                ctx, "Action Failed", "You cannot kick yourself.", nextcord.Color.red()
            )
        if member.id == self.bot.user.id:
            return await self._send_feedback_embed(
                ctx, "Action Failed", "I cannot kick myself.", nextcord.Color.red()
            )
        # Note: Type hint is nextcord.Member, so instance check below might be redundant
        # but kept for safety if type hinting is bypassed.
        if not isinstance(member, nextcord.Member):
            logger.warning(
                f"Kick command: Input {member.id} resolved to User, not Member. Check intents."
            )
            return await self._send_feedback_embed(
                ctx,
                "Action Failed",
                f"Could not get full member data for {member.mention}. Ensure I have Member Intents enabled.",
                nextcord.Color.red(),
            )
        if not isinstance(ctx.author, nextcord.Member) or not isinstance(
            ctx.guild.me, nextcord.Member
        ):
            logger.error(
                "Kick command: ctx.author or ctx.guild.me is not a Member object during role check."
            )
            return await self._send_feedback_embed(
                ctx,
                "Internal Error",
                "An internal error occurred (could not verify roles).",
                nextcord.Color.red(),
            )

        member_top_role = member.top_role
        author_top_role = ctx.author.top_role
        me_top_role = ctx.guild.me.top_role

        if not member_top_role or not author_top_role or not me_top_role:
            logger.error("Kick command: Could not determine role hierarchy.")
            return await self._send_feedback_embed(
                ctx,
                "Internal Error",
                "Could not determine role hierarchy.",
                nextcord.Color.red(),
            )
        if (
            member_top_role.position >= author_top_role.position
            and ctx.author.id != ctx.guild.owner_id
        ):
            return await self._send_feedback_embed(
                ctx,
                "Permissions Error",
                "You can't kick someone with a higher or equal role.",
                nextcord.Color.red(),
            )
        if member_top_role.position >= me_top_role.position:
            return await self._send_feedback_embed(
                ctx,
                "Permissions Error",
                "I cannot kick someone with a higher or equal role than me.",
                nextcord.Color.red(),
            )

        confirmed, confirm_msg_obj = await self._prompt_confirmation(
            ctx, member, "kick", reason
        )

        if confirm_msg_obj:
            try:
                await confirm_msg_obj.clear_reactions()
            except (nextcord.Forbidden, nextcord.NotFound, nextcord.HTTPException):
                pass

        if not confirmed:
            if confirm_msg_obj:
                cancelled_embed = create_base_embed(
                    "Action Cancelled",
                    f"Kick action for {member.mention} has been cancelled or timed out.",
                    nextcord.Color.red(),
                )
                await confirm_msg_obj.edit(embed=cancelled_embed, view=None)
            else:  # Confirmation message failed to send initially
                await self._send_feedback_embed(
                    ctx,
                    "Action Cancelled",
                    f"Kick action for {member.mention} was cancelled.",
                    nextcord.Color.red(),
                )
            return

        if confirm_msg_obj:
            processing_embed = create_base_embed(
                "Kick Confirmed",
                f"Processing kick for {member.mention}...",
                nextcord.Color.green(),
            )
            await confirm_msg_obj.edit(embed=processing_embed, view=None)

        case_id = await self.create_case(
            ctx.guild.id, member.id, ctx.author.id, "kick", reason
        )
        if case_id is None:
            await self._send_feedback_embed(
                ctx,
                "Action Failed",
                "Failed to create moderation case. Check logs.",
                nextcord.Color.red(),
            )
            if confirm_msg_obj:
                await confirm_msg_obj.delete()  # Clean up confirmation message
            return

        await self._send_dm_notification(
            member=member,
            guild=ctx.guild,
            action_title="kicked",
            reason=reason,
            color=self.get_action_color("kick"),
        )
        mod_log_embed = self._create_mod_log_embed(
            ctx=ctx,
            title="Member Kicked",
            description=f"{member.mention} kicked.",
            member=member,
            moderator=ctx.author,
            case_id=case_id,
            color=self.get_action_color("kick"),
            reason=reason or "No reason",
        )

        try:
            kick_reason = (
                f"Mod: {ctx.author} ({ctx.author.id}). Reason: {reason or 'None'}"
            )
            await member.kick(reason=kick_reason[:512])
            logger.info(
                f"{ctx.author} kicked {member} from {ctx.guild.name}. Reason: {reason}"
            )
        except nextcord.Forbidden:
            await self._send_feedback_embed(
                ctx,
                "Permissions Error",
                "I don't have permission to kick this member.",
                nextcord.Color.red(),
            )
            if confirm_msg_obj:
                await confirm_msg_obj.delete()
            return
        except nextcord.HTTPException as e:
            await self._send_feedback_embed(
                ctx,
                "API Error",
                f"An API error occurred: {e.text}",
                nextcord.Color.red(),
            )
            if confirm_msg_obj:
                await confirm_msg_obj.delete()
            return
        except Exception as e:
            logger.error(f"Unexpected error during kick: {e}", exc_info=True)
            await self._send_feedback_embed(
                ctx,
                "Internal Error",
                f"An unexpected error occurred: {e}",
                nextcord.Color.red(),
            )
            if confirm_msg_obj:
                await confirm_msg_obj.delete()
            return

        await self.send_mod_log(ctx.guild, mod_log_embed)
        # Final feedback embed
        await self._send_feedback_embed(
            ctx, "Kick Successful", f"Kicked {member.mention}.", nextcord.Color.green()
        )

    @commands.command()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(
        ban_members=True, add_reactions=True, manage_messages=True
    )
    async def ban(self, ctx, user: nextcord.User, *, reason: str = None):
        """Bans a user from the server with an optional reason."""
        await self._ensure_guild_tables_exist(ctx.guild.id)
        if user.id == ctx.author.id:
            return await self._send_feedback_embed(
                ctx, "Action Failed", "You cannot ban yourself.", nextcord.Color.red()
            )
        if user.id == self.bot.user.id:
            return await self._send_feedback_embed(
                ctx, "Action Failed", "I cannot ban myself.", nextcord.Color.red()
            )

        guild_member = ctx.guild.get_member(user.id)
        if not isinstance(ctx.author, nextcord.Member) or not isinstance(
            ctx.guild.me, nextcord.Member
        ):
            logger.error(
                "Ban command: ctx.author or ctx.guild.me is not a Member object during role check."
            )
            return await self._send_feedback_embed(
                ctx,
                "Internal Error",
                "An internal error occurred (could not verify roles).",
                nextcord.Color.red(),
            )

        if isinstance(guild_member, nextcord.Member):
            member_top_role = guild_member.top_role
            author_top_role = ctx.author.top_role
            me_top_role = ctx.guild.me.top_role
            if not member_top_role or not author_top_role or not me_top_role:
                logger.error(
                    "Ban command: Could not determine role hierarchy for guild member."
                )
                return await self._send_feedback_embed(
                    ctx,
                    "Internal Error",
                    "Could not determine role hierarchy.",
                    nextcord.Color.red(),
                )
            if (
                member_top_role.position >= author_top_role.position
                and ctx.author.id != ctx.guild.owner_id
            ):
                return await self._send_feedback_embed(
                    ctx,
                    "Permissions Error",
                    "You can't ban someone with a higher or equal role.",
                    nextcord.Color.red(),
                )
            if member_top_role.position >= me_top_role.position:
                return await self._send_feedback_embed(
                    ctx,
                    "Permissions Error",
                    "I cannot ban someone with a higher or equal role than me.",
                    nextcord.Color.red(),
                )

        confirmed, confirm_msg_obj = await self._prompt_confirmation(
            ctx, user, "ban", reason
        )

        if confirm_msg_obj:
            try:
                await confirm_msg_obj.clear_reactions()
            except (nextcord.Forbidden, nextcord.NotFound, nextcord.HTTPException):
                pass

        if not confirmed:
            if confirm_msg_obj:
                cancelled_embed = create_base_embed(
                    "Action Cancelled",
                    f"Ban action for {user.mention} has been cancelled or timed out.",
                    nextcord.Color.red(),
                )
                await confirm_msg_obj.edit(embed=cancelled_embed, view=None)
            else:  # Confirmation message failed
                await self._send_feedback_embed(
                    ctx,
                    "Action Cancelled",
                    f"Ban action for {user.mention} was cancelled.",
                    nextcord.Color.red(),
                )
            return

        if confirm_msg_obj:
            processing_embed = create_base_embed(
                "Ban Confirmed",
                f"Processing ban for {user.mention}...",
                nextcord.Color.green(),
            )
            await confirm_msg_obj.edit(embed=processing_embed, view=None)

        case_id = await self.create_case(
            ctx.guild.id, user.id, ctx.author.id, "ban", reason
        )
        if case_id is None:
            await self._send_feedback_embed(
                ctx,
                "Action Failed",
                "Failed to create moderation case. Check logs.",
                nextcord.Color.red(),
            )
            if confirm_msg_obj:
                await confirm_msg_obj.delete()
            return

        # Send DM notification BEFORE banning, as the user will no longer be in the guild after.
        await self._send_dm_notification(
            member=user,
            guild=ctx.guild,
            action_title="banned",
            reason=reason,
            color=self.get_action_color("ban"),
        )
        mod_log_embed = self._create_mod_log_embed(
            ctx=ctx,
            title="Member Banned",
            description=f"{user.mention} ({user.id}) banned.",
            member=user,
            moderator=ctx.author,
            case_id=case_id,
            color=self.get_action_color("ban"),
            reason=reason or "No reason",
        )

        try:
            ban_reason = (
                f"Mod: {ctx.author} ({ctx.author.id}). Reason: {reason or 'None'}"
            )
            await ctx.guild.ban(user, reason=ban_reason[:512], delete_message_seconds=0)
            logger.info(
                f"{ctx.author} banned {user} ({user.id}) from {ctx.guild.name}. Reason: {reason}"
            )
        except nextcord.Forbidden:
            await self._send_feedback_embed(
                ctx,
                "Permissions Error",
                "I don't have permission to ban this user.",
                nextcord.Color.red(),
            )
            if confirm_msg_obj:
                await confirm_msg_obj.delete()
            return
        except nextcord.HTTPException as e:
            await self._send_feedback_embed(
                ctx,
                "API Error",
                f"An API error occurred: {e.text}",
                nextcord.Color.red(),
            )
            if confirm_msg_obj:
                await confirm_msg_obj.delete()
            return
        except Exception as e:
            logger.error(f"Unexpected error during ban: {e}", exc_info=True)
            await self._send_feedback_embed(
                ctx,
                "Internal Error",
                f"An unexpected error occurred: {e}",
                nextcord.Color.red(),
            )
            if confirm_msg_obj:
                await confirm_msg_obj.delete()
            return

        await self.send_mod_log(ctx.guild, mod_log_embed)
        # Final feedback embed
        await self._send_feedback_embed(
            ctx,
            "Ban Successful",
            f"Banned {user.mention} ({user.id}).",
            nextcord.Color.green(),
        )

    @commands.command()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx, user: nextcord.User, *, reason: str = None):
        """Unbans a user from the server."""
        await self._ensure_guild_tables_exist(ctx.guild.id)

        if not reason:
            reason = "No reason provided."

        try:
            # Check if the user is actually banned
            await ctx.guild.fetch_ban(user)
        except nextcord.NotFound:
            return await self._send_feedback_embed(
                ctx,
                "Action Failed",
                f"{user.mention} ({user.id}) is not banned from this server.",
                nextcord.Color.red(),
            )
        except nextcord.Forbidden:
            return await self._send_feedback_embed(
                ctx,
                "Permissions Error",
                "I don't have permissions to check bans.",
                nextcord.Color.red(),
            )
        except nextcord.HTTPException as e:
            logger.error(
                f"HTTPException fetching ban for {user.id}: {e}", exc_info=True
            )
            return await self._send_feedback_embed(
                ctx,
                "API Error",
                f"An API error occurred while checking ban status: {e.text}",
                nextcord.Color.red(),
            )
        except Exception as e:
            logger.error(
                f"Unexpected error fetching ban for {user.id}: {e}", exc_info=True
            )
            return await self._send_feedback_embed(
                ctx,
                "Internal Error",
                f"An unexpected error occurred: {e}",
                nextcord.Color.red(),
            )

        case_id = await self.create_case(
            ctx.guild.id, user.id, ctx.author.id, "unban", reason
        )
        if case_id is None:
            return await self._send_feedback_embed(
                ctx,
                "Action Failed",
                "Failed to create moderation case. Check logs.",
                nextcord.Color.red(),
            )

        await self._send_dm_notification(
            member=user,
            guild=ctx.guild,
            action_title="unbanned",
            reason=reason,
            color=self.get_action_color("unban"),
        )

        mod_log_embed = self._create_mod_log_embed(
            ctx=ctx,
            title="Member Unbanned",
            description=f"{user.mention} ({user.id}) has been unbanned.",
            member=user,
            moderator=ctx.author,
            case_id=case_id,
            color=self.get_action_color("unban"),
            reason=reason,
        )

        try:
            unban_reason_audit_log = (
                f"Mod: {ctx.author} ({ctx.author.id}). Reason: {reason}"
            )
            await ctx.guild.unban(user, reason=unban_reason_audit_log[:512])
            logger.info(
                f"{ctx.author} unbanned {user} ({user.id}) from {ctx.guild.name}. Reason: {reason}"
            )
        except nextcord.Forbidden:
            logger.error(f"Forbidden to unban {user} in {ctx.guild.name}.")
            await self._send_feedback_embed(
                ctx,
                "Permissions Error",
                "I don't have permission to unban users.",
                nextcord.Color.red(),
            )
            return
        except nextcord.HTTPException as e:
            logger.error(
                f"HTTPException unbanning {user}: {e.status} {e.code} - {e.text}",
                exc_info=True,
            )
            await self._send_feedback_embed(
                ctx,
                "API Error",
                f"An API error occurred: {e.text}",
                nextcord.Color.red(),
            )
            return
        except Exception as e:
            logger.error(f"Unexpected error during unban: {e}", exc_info=True)
            await self._send_feedback_embed(
                ctx,
                "Internal Error",
                f"An unexpected error occurred: {e}",
                nextcord.Color.red(),
            )
            return

        await self.send_mod_log(ctx.guild, mod_log_embed)
        # Final feedback embed
        await self._send_feedback_embed(
            ctx,
            "Unban Successful",
            f"Unbanned {user.mention} ({user.id}).",
            nextcord.Color.green(),
        )

    @commands.command(aliases=["removetimeout", "unmute"])
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def untimeout(self, ctx, member: nextcord.Member, *, reason: str = None):
        """Removes a timeout from a member."""
        await self._ensure_guild_tables_exist(ctx.guild.id)

        if not reason:
            reason = "No reason provided."

        # Check if user is already not timed out
        if (
            member.timed_out_until is None
            or member.timed_out_until < datetime.datetime.now(datetime.timezone.utc)
        ):
            return await self._send_feedback_embed(
                ctx,
                "Action Failed",
                f"{member.mention} is not currently timed out.",
                nextcord.Color.red(),
            )

        if isinstance(ctx.author, nextcord.Member) and isinstance(
            ctx.guild.me, nextcord.Member
        ):
            if (
                member.top_role.position >= ctx.author.top_role.position
                and ctx.author.id != ctx.guild.owner_id
            ):
                return await self._send_feedback_embed(
                    ctx,
                    "Permissions Error",
                    "You can't remove a timeout from someone with a higher or equal role.",
                    nextcord.Color.red(),
                )
        else:
            logger.warning(
                "Untimeout: ctx.author or ctx.guild.me is not a Member object. Skipping hierarchy check."
            )

        case_id = await self.create_case(
            ctx.guild.id, member.id, ctx.author.id, "untimeout", reason
        )
        if case_id is None:
            return await self._send_feedback_embed(
                ctx,
                "Action Failed",
                "Failed to create moderation case. Check logs.",
                nextcord.Color.red(),
            )

        await self._send_dm_notification(
            member=member,
            guild=ctx.guild,
            action_title="timeout removed",
            reason=reason,
            color=self.get_action_color("untimeout"),  # Use specific untimeout color
        )

        mod_log_embed = self._create_mod_log_embed(
            ctx=ctx,
            title="Timeout Removed",
            description=f"Timeout removed for {member.mention}.",
            member=member,
            moderator=ctx.author,
            case_id=case_id,
            color=self.get_action_color("untimeout"),
            reason=reason,
        )

        try:
            untimeout_reason_audit_log = (
                f"Mod: {ctx.author} ({ctx.author.id}). Reason: {reason}"
            )
            await member.timeout(None, reason=untimeout_reason_audit_log[:512])
            logger.info(
                f"{ctx.author} removed timeout for {member} in {ctx.guild.name}. Reason: {reason}"
            )
        except nextcord.Forbidden:
            logger.error(
                f"Forbidden to remove timeout for {member} in {ctx.guild.name}."
            )
            await self._send_feedback_embed(
                ctx,
                "Permissions Error",
                "I don't have permission to remove timeouts. Check my 'Moderate Members' permission.",
                nextcord.Color.red(),
            )
            return
        except nextcord.HTTPException as e:
            logger.error(
                f"HTTPException removing timeout for {member}: {e.status} {e.code} - {e.text}",
                exc_info=True,
            )
            await self._send_feedback_embed(
                ctx,
                "API Error",
                f"An API error occurred: {e.text}",
                nextcord.Color.red(),
            )
            return
        except Exception as e:
            logger.error(
                f"Unexpected error removing timeout for {member}: {e}", exc_info=True
            )
            await self._send_feedback_embed(
                ctx,
                "Internal Error",
                f"An unexpected error occurred: {e}",
                nextcord.Color.red(),
            )
            return

        await self.send_mod_log(ctx.guild, mod_log_embed)
        # Final feedback embed
        await self._send_feedback_embed(
            ctx,
            "Timeout Removed",
            f"Timeout removed for {member.mention}.",
            nextcord.Color.green(),
        )

    @commands.command(aliases=['mute'])
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def timeout(
        self, ctx, member: nextcord.Member, duration: str, *, reason: str = None
    ):
        """Times out a member for a specified duration with an optional reason."""
        await self._ensure_guild_tables_exist(ctx.guild.id)
        if member == ctx.author:
            return await self._send_feedback_embed(
                ctx,
                "Action Failed",
                "You cannot timeout yourself.",
                nextcord.Color.red(),
            )
        if member.id == self.bot.user.id:
            return await self._send_feedback_embed(
                ctx, "Action Failed", "I cannot timeout myself.", nextcord.Color.red()
            )
        if not isinstance(member, nextcord.Member):
            # Should not happen with correct type hinting, but safety check
            logger.warning(
                f"Timeout command: Input {member.id} resolved to User, not Member. Check intents."
            )
            return await self._send_feedback_embed(
                ctx,
                "Action Failed",
                f"Could not get full member data for {member.mention} to apply timeout.",
                nextcord.Color.red(),
            )

        if isinstance(ctx.author, nextcord.Member) and isinstance(
            ctx.guild.me, nextcord.Member
        ):
            member_top_role = member.top_role
            author_top_role = ctx.author.top_role
            me_top_role = ctx.guild.me.top_role
            if not member_top_role or not author_top_role or not me_top_role:
                logger.error("Timeout command: Could not determine role hierarchy.")
                return await self._send_feedback_embed(
                    ctx,
                    "Internal Error",
                    "Could not determine role hierarchy.",
                    nextcord.Color.red(),
                )
            if (
                member_top_role.position >= author_top_role.position
                and ctx.author.id != ctx.guild.owner_id
            ):
                return await self._send_feedback_embed(
                    ctx,
                    "Permissions Error",
                    "You can't timeout someone with a higher or equal role.",
                    nextcord.Color.red(),
                )
            if member_top_role.position >= me_top_role.position:
                return await self._send_feedback_embed(
                    ctx,
                    "Permissions Error",
                    "I cannot timeout someone with a higher or equal role than me.",
                    nextcord.Color.red(),
                )
        else:
            logger.error(
                "Timeout command: ctx.author or ctx.guild.me is not a Member object during role check."
            )
            return await self._send_feedback_embed(
                ctx,
                "Internal Error",
                "An internal error occurred (could not verify roles).",
                nextcord.Color.red(),
            )

        try:
            seconds = pytimeparse.parse(duration)
            if seconds is None:
                raise ValueError("Invalid duration")
        except ValueError:
            return await self._send_feedback_embed(
                ctx,
                "Invalid Usage",
                "Invalid duration format (e.g., '1h30m', '1d', '30s').",
                nextcord.Color.orange(),
            )
        max_timeout_seconds = 28 * 24 * 60 * 60
        if not (0 < seconds <= max_timeout_seconds):
            return await self._send_feedback_embed(
                ctx,
                "Invalid Duration",
                "Duration must be between 1 second and 28 days.",
                nextcord.Color.orange(),
            )
        try:
            until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
                seconds=seconds
            )
            expires_timestamp = int(until.timestamp())
        except OverflowError:
            return await self._send_feedback_embed(
                ctx,
                "Invalid Duration",
                "Calculated duration is too far in the future.",
                nextcord.Color.orange(),
            )

        duration_str = self.format_duration(seconds)

        case_id = await self.create_case(
            ctx.guild.id, member.id, ctx.author.id, "timeout", reason, duration_str
        )
        if case_id is None:
            return await self._send_feedback_embed(
                ctx,
                "Action Failed",
                "Failed to create moderation case. Check logs.",
                nextcord.Color.red(),
            )

        await self._send_dm_notification(
            member=member,
            guild=ctx.guild,
            action_title="timed out",
            reason=reason,
            color=self.get_action_color("timeout"),
            duration=duration_str,
            expires_timestamp=expires_timestamp,
        )
        mod_log_embed = self._create_mod_log_embed(
            ctx=ctx,
            title="Member Timed Out",
            description=f"{member.mention} timed out.",
            member=member,
            moderator=ctx.author,
            case_id=case_id,
            color=self.get_action_color("timeout"),
            reason=reason or "No reason",
            duration=duration_str,
            expires=f"<t:{expires_timestamp}:R>",
        )

        try:
            timeout_reason = (
                f"Mod: {ctx.author} ({ctx.author.id}). Reason: {reason or 'None'}"
            )
            await member.timeout(until, reason=timeout_reason[:512])
            logger.info(
                f"{ctx.author} timed out {member} for {duration_str}. Reason: {reason}"
            )
        except nextcord.Forbidden:
            await self._send_feedback_embed(
                ctx,
                "Permissions Error",
                f"I don't have permission to timeout {member.mention}. Check my 'Moderate Members' permission.",
                nextcord.Color.red(),
            )
            return
        except nextcord.HTTPException as e:
            await self._send_feedback_embed(
                ctx,
                "API Error",
                f"An API error occurred: {e.text}",
                nextcord.Color.red(),
            )
            return
        except Exception as e:
            logger.error(f"Unexpected error during timeout: {e}", exc_info=True)
            await self._send_feedback_embed(
                ctx,
                "Internal Error",
                f"An unexpected error occurred: {e}",
                nextcord.Color.red(),
            )
            return

        await self.send_mod_log(ctx.guild, mod_log_embed)
        # Final feedback embed
        await self._send_feedback_embed(
            ctx,
            "Timeout Applied",
            f"Timed out {member.mention} for {duration_str}.",
            nextcord.Color.green(),
        )

    @commands.command()
    @commands.has_permissions(moderate_members=True)
    async def warn(self, ctx, member: nextcord.Member, *, reason: str):
        """Warns a member with a mandatory reason."""
        await self._ensure_guild_tables_exist(ctx.guild.id)
        if not reason:
            return await self._send_feedback_embed(
                ctx,
                "Invalid Usage",
                "You must provide a reason for the warning.",
                nextcord.Color.orange(),
            )
        if member == ctx.author:
            return await self._send_feedback_embed(
                ctx, "Action Failed", "You cannot warn yourself.", nextcord.Color.red()
            )
        if member.id == self.bot.user.id:
            return await self._send_feedback_embed(
                ctx, "Action Failed", "You cannot warn the bot.", nextcord.Color.red()
            )
        if not isinstance(member, nextcord.Member):
            logger.warning(
                f"Warn command: Input {member.id} resolved to User, not Member. Check intents."
            )
            # Warning can still proceed, but log it.
        if not isinstance(ctx.author, nextcord.Member):
            logger.error("Warn command: ctx.author is not a Member object.")
            return await self._send_feedback_embed(
                ctx,
                "Internal Error",
                "An internal error occurred (could not verify moderator).",
                nextcord.Color.red(),
            )

        case_id = await self.create_case(
            ctx.guild.id, member.id, ctx.author.id, "warn", reason
        )
        if case_id is None:
            return await self._send_feedback_embed(
                ctx,
                "Action Failed",
                "Failed to create moderation case. Check logs.",
                nextcord.Color.red(),
            )

        await self._send_dm_notification(
            member=member,
            guild=ctx.guild,
            action_title="warned",
            reason=reason,
            color=self.get_action_color("warn"),
        )
        mod_log_embed = self._create_mod_log_embed(
            ctx=ctx,
            title="Member Warned",
            description=f"{member.mention} warned.",
            member=member,
            moderator=ctx.author,
            case_id=case_id,
            color=self.get_action_color("warn"),
            reason=reason,
        )

        logger.info(f"{ctx.author} warned {member}. Reason: {reason}")
        await self.send_mod_log(ctx.guild, mod_log_embed)
        # Final feedback embed
        await self._send_feedback_embed(
            ctx, "Warning Issued", f"Warned {member.mention}.", nextcord.Color.green()
        )

    @commands.command(aliases=["cases", "history"])
    @commands.has_permissions(moderate_members=True)
    async def case(self, ctx, identifier: nextcord.User | int):
        """Retrieves details for a specific case or a user's case history."""
        await self._ensure_guild_tables_exist(ctx.guild.id)

        if isinstance(identifier, int):
            case_id_input = identifier
            case_details = await self.get_case(ctx.guild.id, case_id_input)
            if not case_details:
                return await self._send_feedback_embed(
                    ctx,
                    "Not Found",
                    f"Case #{case_id_input} not found in this guild.",
                    nextcord.Color.red(),
                )

            user_display, mod_display = "Unknown User", "Unknown Mod"
            user_obj = None
            try:
                user_obj = await self.bot.fetch_user(case_details["user_id"])
                user_display = f"{user_obj.mention} ({user_obj.name})"
            except:
                user_display = f"Unknown (ID: {case_details['user_id']})"

            mod_obj = None
            try:
                mod_obj = await self.bot.fetch_user(case_details["moderator_id"])
                mod_display = f"{mod_obj.mention} ({mod_obj.name})"
            except:
                mod_display = f"Unknown (ID: {case_details['moderator_id']})"

            try:
                timestamp = datetime.datetime.fromisoformat(case_details["timestamp"])
            except:
                timestamp = datetime.datetime.now(datetime.timezone.utc)

            embed = nextcord.Embed(
                title=f"Case #{case_details['case_id']} | {case_details['action'].title()}",
                color=self.get_action_color(case_details["action"]),
                timestamp=timestamp,
            )
            if user_obj:
                embed.set_thumbnail(
                    url=user_obj.display_avatar.url
                )  # Add thumbnail if user fetched

            embed.add_field(
                name="User",
                value=f"{user_display}\nID: {case_details['user_id']}",
                inline=True,
            )
            embed.add_field(
                name="Moderator",
                value=f"{mod_display}\nID: {case_details['moderator_id']}",
                inline=True,
            )
            if case_details["reason"]:
                embed.add_field(
                    name="Reason", value=case_details["reason"][:1024], inline=False
                )
            if case_details["duration"]:
                embed.add_field(
                    name="Duration", value=case_details["duration"], inline=False
                )
            embed.set_footer(text=f"Guild: {ctx.guild.name} ({ctx.guild.id})")
            await ctx.send(embed=embed)

        elif isinstance(identifier, (nextcord.User, nextcord.Member)):
            user = identifier
            user_case_list = await self.get_user_cases(ctx.guild.id, user.id)
            if not user_case_list:
                return await self._send_feedback_embed(
                    ctx,
                    "Not Found",
                    f"No cases found for {user.mention} in this guild.",
                    nextcord.Color.blue(),
                )

            embed = nextcord.Embed(
                title=f"Mod History: {user.name}",
                description=f"{len(user_case_list)} case(s) for {user.mention}.",
                color=0x3498DB,
                timestamp=datetime.datetime.now(datetime.timezone.utc),
            )
            embed.set_thumbnail(url=user.display_avatar.url)

            display_count = min(
                len(user_case_list), 5
            )  # Show max 5 cases in history overview

            for i, case_item in enumerate(user_case_list[:display_count]):
                try:
                    case_time = datetime.datetime.fromisoformat(case_item["timestamp"])
                    ts_str = f"<t:{int(case_time.timestamp())}:f>"
                    rel_ts_str = f"<t:{int(case_time.timestamp())}:R>"
                except:
                    ts_str, rel_ts_str = "Invalid Date", ""

                mod_display_in_field = f"Mod: <@{case_item['moderator_id']}>"
                reason_preview = (
                    (
                        case_item["reason"][:100] + "..."
                        if len(case_item.get("reason", "")) > 100
                        else case_item.get("reason")
                    )
                    if case_item.get("reason")
                    else "No reason provided."
                )

                value = f"{mod_display_in_field}\nDate: {ts_str} ({rel_ts_str})\nReason: {reason_preview}"
                if case_item.get("duration"):
                    value += f"\nDuration: {case_item['duration']}"

                embed.add_field(
                    name=f"#{case_item['case_id']} - {case_item['action'].title()}",
                    value=value[:1024],
                    inline=False,
                )

            footer_text = f"User ID: {user.id}" + (
                f" | Showing {display_count} of {len(user_case_list)} most recent cases."
                if len(user_case_list) > display_count
                else ""
            )
            embed.set_footer(text=footer_text)
            await ctx.send(embed=embed)
        else:
            await self._send_feedback_embed(
                ctx,
                "Invalid Input",
                "Please provide a Case ID (number) or mention/ID of a user.",
                nextcord.Color.orange(),
            )

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def modlog(self, ctx, channel: nextcord.TextChannel = None):
        """Sets or displays the moderation log channel for the server."""
        await self._ensure_guild_tables_exist(ctx.guild.id)
        table_name = self._get_guild_table_name(ctx.guild.id, "mod_log_channels")
        async with aiosqlite.connect(self.db_path) as db:
            if channel is None:
                cursor = await db.execute(
                    f"SELECT channel_id FROM {table_name} WHERE singleton_id = 1"
                )
                result = await cursor.fetchone()
                await cursor.close()
                if result and (log_channel := ctx.guild.get_channel(result[0])):
                    await self._send_feedback_embed(
                        ctx,
                        "Modlog Channel",
                        f"Modlog channel for this guild: {log_channel.mention}.",
                        nextcord.Color.blue(),
                    )
                elif result:
                    await self._send_feedback_embed(
                        ctx,
                        "Modlog Channel Not Found",
                        f"Modlog channel ID {result[0]} is set for this guild, but the channel was not found.",
                        nextcord.Color.orange(),
                    )
                else:
                    await self._send_feedback_embed(
                        ctx,
                        "Modlog Not Set",
                        f"Modlog channel not set for this guild. Use `{ctx.prefix}modlog #channel`.",
                        nextcord.Color.orange(),
                    )
            else:
                bot_perms = channel.permissions_for(ctx.guild.me)
                if not bot_perms.send_messages or not bot_perms.embed_links:
                    return await self._send_feedback_embed(
                        ctx,
                        "Permissions Error",
                        f"I need 'Send Messages' & 'Embed Links' permissions in {channel.mention} to set it as the modlog.",
                        nextcord.Color.red(),
                    )
                try:
                    await db.execute(
                        f"INSERT INTO {table_name} (singleton_id, channel_id) VALUES (1, ?) ON CONFLICT(singleton_id) DO UPDATE SET channel_id = excluded.channel_id",
                        (channel.id,),
                    )
                    await db.commit()
                    logger.info(
                        f"Modlog for guild {ctx.guild.id} (table {table_name}) set to channel {channel.id} by {ctx.author}"
                    )
                    await self._send_feedback_embed(
                        ctx,
                        "Modlog Updated",
                        f"✅ Modlog channel for this guild set to {channel.mention}",
                        nextcord.Color.green(),
                    )
                    try:
                        await channel.send(
                            embed=create_base_embed(
                                "Modlog Configured",
                                f"This channel has been set as the moderation log channel by {ctx.author.mention}.",
                                nextcord.Color.green(),
                            )
                        )
                    except Exception as e_test:
                        logger.warning(
                            f"Could not send test msg to new modlog {channel.id} for guild {ctx.guild.id}: {e_test}"
                        )
                except Exception as e:
                    logger.error(
                        f"Failed setting modlog for guild {ctx.guild.id} (table {table_name}): {e}",
                        exc_info=True,
                    )
                    await self._send_feedback_embed(
                        ctx,
                        "Error",
                        "Error updating modlog configuration for this guild.",
                        nextcord.Color.red(),
                    )

    async def send_mod_log(self, guild: nextcord.Guild, embed: nextcord.Embed):
        """Fetches the modlog channel and sends the modlog embed."""
        try:
            await self._ensure_guild_tables_exist(guild.id)
        except Exception as e_ensure:
            logger.error(
                f"Failed to ensure tables before sending mod log for guild {guild.id}: {e_ensure}"
            )
            return

        table_name = self._get_guild_table_name(guild.id, "mod_log_channels")
        channel_id = None
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    f"SELECT channel_id FROM {table_name} WHERE singleton_id = 1"
                ) as cursor:
                    if result := await cursor.fetchone():
                        channel_id = result[0]

            if (
                channel_id
                and (channel := guild.get_channel(channel_id))
                and isinstance(channel, nextcord.TextChannel)
            ):
                bot_perms = channel.permissions_for(guild.me)
                if bot_perms.send_messages and bot_perms.embed_links:
                    await channel.send(embed=embed)
                else:
                    logger.warning(
                        f"Missing send/embed perms in modlog channel {channel_id} for guild {guild.id}"
                    )
            elif channel_id:
                logger.warning(
                    f"Modlog channel {channel_id} (from table {table_name}) not found or not TextChannel for guild {guild.id}."
                )
            else:
                logger.debug(
                    f"No modlog channel set for guild {guild.id}. Skipping modlog send."
                )

        except Exception as e:
            logger.error(
                f"Failed sending mod log to {channel_id} (table {table_name}) for guild {guild.id}: {e}",
                exc_info=True,
            )

    def format_duration(self, total_seconds):
        if total_seconds <= 0:
            return "0s"
        secs = int(total_seconds)
        days, rem = divmod(secs, 86400)
        hours, rem = divmod(rem, 3600)
        mins, secs_final = divmod(rem, 60)
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if mins:
            parts.append(f"{mins}m")
        if secs_final or not parts:
            parts.append(f"{secs_final}s")
        return " ".join(parts) if parts else "0s"

    def get_action_color(self, action: str) -> int:
        colors = {
            "warn": 0xF39C12,  # Orange
            "timeout": 0xF1C40F,  # Yellow
            "kick": 0xE67E22,  # Darker Orange
            "ban": 0xE74C3C,  # Red
            "unban": 0x2ECC71,  # Green
            "untimeout": 0x3498DB,  # Blue
            "removetimeout": 0x3498DB,  # Same as untimeout
        }
        return colors.get(action.lower(), 0x7289DA)


def setup(bot):
    cog_name = Moderation.__name__
    if cog_name not in bot.cogs:
        try:
            bot.add_cog(Moderation(bot))
        except Exception as e:
            logger.error(f"Failed to load cog '{cog_name}': {e}", exc_info=True)
    else:
        logger.warning(f"Cog '{cog_name}' was already loaded.")
