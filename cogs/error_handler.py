import nextcord
import traceback
import uuid
import os
from datetime import datetime
from nextcord.ext import commands
from utils.katlog import logger  # MODIFIED: Using your LazyLogger

# --- Configuration Constants ---
ERROR_LOG_DIR = "errors"
DEV_CONTACT_INFO = "the bot developer or support server"

# --- Embed Colors ---
ERROR_COLOR = nextcord.Color.red()
WARN_COLOR = nextcord.Color.orange()
INFO_COLOR = nextcord.Color.blue()

# --- Embed Titles (for consistency) ---
TITLE_MISSING_ARGUMENT = "❌ Missing Argument"
TITLE_INVALID_ARGUMENT = "❌ Invalid Argument"
TITLE_CONVERSION_ERROR = "⚠️ Input Error"
TITLE_MISSING_PERMISSIONS = "🚫 Missing Permissions"
TITLE_BOT_MISSING_PERMISSIONS = "🤖 Bot Missing Permissions"
TITLE_CHECK_FAILED = "🚫 Check Failed"
TITLE_MISSING_ROLE = "🚫 Missing Role(s)"
TITLE_BOT_MISSING_ROLE = "🤖 Bot Missing Role(s)"
TITLE_SERVER_ONLY = "🚫 Server Only Command"
TITLE_COMMAND_DISABLED = "⚙️ Command Disabled"
TITLE_COOLDOWN = "⏳ Cooldown!"
TITLE_MAX_CONCURRENCY = "🚦 Command Busy"
TITLE_NSFW_REQUIRED = "🔞 NSFW Channel Required"
TITLE_UNEXPECTED_ERROR = "🔥 Unexpected Error"


# --- Helper Functions ---
def _get_command_invocation_string(ctx: commands.Context) -> str:
    """Attempts to reconstruct the command invocation string."""
    prefix = ctx.clean_prefix
    command_display_name = (
        ctx.command.qualified_name if ctx.command else ctx.invoked_with
    )

    args_part = ""
    if ctx.command and ctx.message.content:
        prefix_and_command = prefix + ctx.invoked_with
        if ctx.message.content.startswith(prefix_and_command):
            args_part = ctx.message.content[len(prefix_and_command) :].strip()
    elif not ctx.command and ctx.message.content:
        if ctx.message.content.startswith(prefix + ctx.invoked_with):
            args_part = ctx.message.content[len(prefix + ctx.invoked_with) :].strip()

    full_invocation = (
        f"`{prefix}{command_display_name}{(' ' + args_part) if args_part else ''}`"
    )

    if len(full_invocation) > 1020:
        full_invocation = full_invocation[:1020] + "...`"
    return full_invocation


def create_base_embed(
    ctx: commands.Context, title: str, color: nextcord.Color
) -> nextcord.Embed:
    """Creates a base embed with author, timestamp, and context."""
    embed = nextcord.Embed(title=title, color=color, timestamp=ctx.message.created_at)
    embed.set_author(
        name=f"{ctx.author.display_name} ({ctx.author.id})",
        icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None,
    )

    embed.add_field(
        name="Command Triggered",
        value=_get_command_invocation_string(ctx),
        inline=False,
    )

    location = "Direct Message"
    if ctx.guild:
        location = f"Guild: {ctx.guild.name} ({ctx.guild.id})\nChannel: #{ctx.channel.name} ({ctx.channel.id})"
    embed.add_field(name="Location", value=location, inline=False)

    embed.set_footer(text=f"Bot: {ctx.bot.user.name}")
    return embed


async def _log_unhandled_error_to_file(
    ctx: commands.Context,
    original_error: Exception,
    error_id: uuid.UUID,
    log_prefix_str: str,  # This log_prefix_str is for the katlog console message
):
    """Logs detailed information about an unhandled error to a file."""
    os.makedirs(ERROR_LOG_DIR, exist_ok=True)
    log_file_path = os.path.join(ERROR_LOG_DIR, f"{error_id}.log")

    command_name_for_log = (
        ctx.command.qualified_name if ctx.command else ctx.invoked_with
    )
    location_log_str = "Direct Message"
    if ctx.guild:
        location_log_str = f"Guild: {ctx.guild.name} ({ctx.guild.id}), Channel: #{ctx.channel.name} ({ctx.channel.id})"

    raw_input_content = (
        ctx.message.content if ctx.message else "N/A (No message context)"
    )

    detailed_log_message = (
        f"Timestamp: {datetime.utcnow().isoformat()}Z\n"
        f"Error ID: {error_id}\n"
        f"User: {ctx.author} ({ctx.author.id})\n"
        f"Command Name: {command_name_for_log}\n"
        f"Invoked With: {ctx.invoked_with}\n"
        f"Clean Prefix: {ctx.clean_prefix}\n"
        f"Raw Message Content: {raw_input_content}\n"
        f"Location: {location_log_str}\n"
        f"Error Type: {type(original_error).__name__}\n"
        f"Error Message: {str(original_error)}\n\n"
        f"--- Traceback ---\n"
        f"{''.join(traceback.format_exception(type(original_error), original_error, original_error.__traceback__))}"
    )

    try:
        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write(detailed_log_message)
        # Using your katlog logger here
        logger.error(
            f"{log_prefix_str}Unhandled Exception | Error ID: {error_id} | Type: {type(original_error).__name__}. Details logged to: {log_file_path}"
        )
    except IOError as e:
        # Using your katlog logger here
        logger.error(
            f"{log_prefix_str}Unhandled Exception | Error ID: {error_id} | Type: {type(original_error).__name__}. FAILED TO WRITE TO LOG FILE {log_file_path}: {e}"
        )
        # Using your katlog logger here for fallback
        logger.error(
            f"Fallback Log for Error ID {error_id} (due to file write failure):\n{detailed_log_message}"
        )


class ErrorHandler(commands.Cog):
    """Handles and logs command errors globally with enhanced feedback."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ):
        """Main listener for command errors."""

        if hasattr(ctx.command, "on_error"):
            return

        cog = ctx.cog
        if cog and cog._get_overridden_method(cog.cog_command_error) is not None:
            return

        original_error = getattr(error, "original", error)
        command_name = ctx.command.qualified_name if ctx.command else ctx.invoked_with
        display_prefix = ctx.clean_prefix

        # Constructing a prefix for console logs via katlog
        log_prefix_katlog = f"Usr:{ctx.author.id} | Cmd:'{command_name}' | Gld:{ctx.guild.id if ctx.guild else 'DM'} | Chn:{ctx.channel.id} | "

        if isinstance(error, commands.CommandNotFound):
            logger.info(  # Using your katlog logger
                f"{log_prefix_katlog}CommandNotFound: Invoked with '{ctx.invoked_with}', Full: '{ctx.message.content}'"
            )
            return

        elif isinstance(error, commands.NotOwner):
            logger.warning(
                f"{log_prefix_katlog}NotOwner: Attempt by non-owner."
            )  # Using your katlog logger
            return

        elif isinstance(error, commands.DisabledCommand):
            embed = create_base_embed(ctx, TITLE_COMMAND_DISABLED, INFO_COLOR)
            embed.description = f"The command `{command_name}` is currently disabled."
            logger.warning(  # Using your katlog logger
                f"{log_prefix_katlog}DisabledCommand: User tried to use disabled command."
            )
            await ctx.send(embed=embed)

        elif isinstance(error, commands.CommandOnCooldown):
            embed = create_base_embed(ctx, TITLE_COOLDOWN, INFO_COLOR)
            embed.description = f"This command is on cooldown.\nPlease try again in **{error.retry_after:.2f} seconds**."
            embed.add_field(
                name="Cooldown Scope",
                value=f"Per `{error.cooldown.type.name.capitalize()}`",
                inline=True,
            )
            embed.add_field(
                name="Rate",
                value=f"{error.cooldown.rate} time(s) per {error.cooldown.per:.0f}s",
                inline=True,
            )
            logger.info(  # Using your katlog logger
                f"{log_prefix_katlog}CommandOnCooldown: {error.retry_after:.2f}s left (Scope: {error.cooldown.type.name})"
            )
            await ctx.send(embed=embed, delete_after=max(5.0, error.retry_after))

        elif isinstance(error, commands.MaxConcurrencyReached):
            embed = create_base_embed(ctx, TITLE_MAX_CONCURRENCY, WARN_COLOR)
            embed.description = f"The command `{command_name}` has reached its maximum concurrent usage limit. Please wait and try again."
            embed.add_field(
                name="Limit", value=f"{error.number} concurrent use(s)", inline=True
            )
            embed.add_field(
                name="Scope", value=f"Per `{error.per.name.capitalize()}`", inline=True
            )
            logger.warning(  # Using your katlog logger
                f"{log_prefix_katlog}MaxConcurrencyReached: Limit {error.number}/{error.per.name}"
            )
            await ctx.send(embed=embed)

        elif isinstance(error, commands.MissingRequiredArgument):
            embed = create_base_embed(ctx, TITLE_MISSING_ARGUMENT, WARN_COLOR)
            param_name = error.param.name
            embed.description = f"You missed the required argument: `{param_name}`."
            if ctx.command:
                signature = f"{display_prefix}{ctx.command.qualified_name} {ctx.command.signature or ''}".strip()
                embed.add_field(
                    name="Correct Usage", value=f"```\n{signature}\n```", inline=False
                )
            logger.warning(
                f"{log_prefix_katlog}MissingRequiredArgument: {param_name}"
            )  # Using your katlog logger
            await ctx.send(embed=embed)

        elif isinstance(error, (commands.MemberNotFound, commands.UserNotFound)):
            embed = create_base_embed(ctx, TITLE_CONVERSION_ERROR, WARN_COLOR)
            entity = "member" if isinstance(error, commands.MemberNotFound) else "user"
            embed.description = (
                f"Could not find a {entity} matching `{error.argument}`."
            )
            logger.warning(  # Using your katlog logger
                f"{log_prefix_katlog}{type(error).__name__}: Argument '{error.argument}'"
            )
            await ctx.send(embed=embed)

        elif isinstance(
            error,
            (
                commands.ChannelNotFound,
                commands.RoleNotFound,
                commands.EmojiNotFound,
                commands.MessageNotFound,
            ),
        ):
            embed = create_base_embed(ctx, TITLE_CONVERSION_ERROR, WARN_COLOR)
            entity_map = {
                commands.ChannelNotFound: "channel",
                commands.RoleNotFound: "role",
                commands.EmojiNotFound: "emoji",
                commands.MessageNotFound: "message",
            }
            entity = entity_map.get(type(error), "item")
            embed.description = (
                f"Could not find a {entity} matching `{error.argument}`."
            )
            logger.warning(  # Using your katlog logger
                f"{log_prefix_katlog}{type(error).__name__}: Argument '{error.argument}'"
            )
            await ctx.send(embed=embed)

        elif isinstance(error, commands.BadUnionArgument):
            embed = create_base_embed(ctx, TITLE_INVALID_ARGUMENT, WARN_COLOR)
            param_name = error.param.name
            embed.description = f"The argument `{param_name}` was not a valid type."
            types_expected = [t.__name__ for t in error.converters]
            embed.add_field(
                name="Expected one of",
                value=f"`{'`, `'.join(types_expected)}`",
                inline=False,
            )
            if ctx.command:
                signature = f"{display_prefix}{ctx.command.qualified_name} {ctx.command.signature or ''}".strip()
                embed.add_field(
                    name="Correct Usage", value=f"```\n{signature}\n```", inline=False
                )
            logger.warning(  # Using your katlog logger
                f"{log_prefix_katlog}BadUnionArgument for {param_name}: {original_error}"
            )
            await ctx.send(embed=embed)

        elif isinstance(error, (commands.BadArgument, commands.UserInputError)):
            embed = create_base_embed(ctx, TITLE_INVALID_ARGUMENT, WARN_COLOR)
            error_details = str(original_error)
            param_name_str = None

            if hasattr(error, "param") and error.param:
                param_name_str = error.param.name
            elif hasattr(ctx, "current_parameter") and ctx.current_parameter:
                param_name_str = ctx.current_parameter.name

            embed.description = f"The value provided {f'for argument `{param_name_str}` ' if param_name_str else ''}was not valid."

            if len(error_details) < 1000:
                embed.add_field(
                    name="Reason", value=f"```\n{error_details}\n```", inline=False
                )
            else:
                embed.add_field(
                    name="Reason",
                    value="Invalid input provided (details too long).",
                    inline=False,
                )

            if ctx.command:
                signature = f"{display_prefix}{ctx.command.qualified_name} {ctx.command.signature or ''}".strip()
                embed.add_field(
                    name="Correct Usage", value=f"```\n{signature}\n```", inline=False
                )
            logger.warning(
                f"{log_prefix_katlog}BadArgument/UserInputError: {original_error}"
            )  # Using your katlog logger
            await ctx.send(embed=embed)

        elif isinstance(error, commands.NoPrivateMessage):
            embed = create_base_embed(ctx, TITLE_SERVER_ONLY, WARN_COLOR)
            embed.description = (
                f"The command `{command_name}` can only be used within a server."
            )
            logger.warning(
                f"{log_prefix_katlog}NoPrivateMessage: Command used in DM."
            )  # Using your katlog logger
            await ctx.send(embed=embed)

        elif isinstance(error, commands.MissingPermissions):
            embed = create_base_embed(ctx, TITLE_MISSING_PERMISSIONS, WARN_COLOR)
            perms = [
                f"`{p.replace('_', ' ').title()}`" for p in error.missing_permissions
            ]
            embed.description = f"You lack the required permission(s) to run this command:\n{', '.join(perms)}"
            logger.warning(  # Using your katlog logger
                f"{log_prefix_katlog}MissingPermissions: User lacks {error.missing_permissions}"
            )
            await ctx.send(embed=embed)

        elif isinstance(error, commands.BotMissingPermissions):
            embed = create_base_embed(ctx, TITLE_BOT_MISSING_PERMISSIONS, ERROR_COLOR)
            perms = [
                f"`{p.replace('_', ' ').title()}`" for p in error.missing_permissions
            ]
            embed.description = f"I lack the required permission(s) to perform this action:\n{', '.join(perms)}"
            embed.add_field(
                name="Required By", value=f"Command `{command_name}`.", inline=False
            )
            logger.error(  # Using your katlog logger
                f"{log_prefix_katlog}BotMissingPermissions: Bot lacks {error.missing_permissions}"
            )
            try:
                await ctx.send(embed=embed)
            except nextcord.Forbidden:
                logger.error(  # Using your katlog logger
                    f"{log_prefix_katlog}BotMissingPermissions: Cannot send message in channel {ctx.channel.id} due to Send Messages/Embed Links perm."
                )

        elif isinstance(error, (commands.MissingRole, commands.MissingAnyRole)):
            embed = create_base_embed(ctx, TITLE_MISSING_ROLE, WARN_COLOR)
            missing_roles_input = getattr(
                error, "missing_roles", [getattr(error, "missing_role", "Unknown Role")]
            )
            role_mentions = [f"`{str(role)}`" for role in missing_roles_input]
            conjunction = "any of" if isinstance(error, commands.MissingAnyRole) else ""
            embed.description = f"You need {conjunction} the following role(s) to use this command: {', '.join(role_mentions)}"
            logger.warning(  # Using your katlog logger
                f"{log_prefix_katlog}MissingRole/MissingAnyRole: User lacks {missing_roles_input}"
            )
            await ctx.send(embed=embed)

        elif isinstance(error, (commands.BotMissingRole, commands.BotMissingAnyRole)):
            embed = create_base_embed(ctx, TITLE_BOT_MISSING_ROLE, ERROR_COLOR)
            missing_roles_input = getattr(
                error, "missing_roles", [getattr(error, "missing_role", "Unknown Role")]
            )
            role_mentions = [f"`{str(role)}`" for role in missing_roles_input]
            conjunction = (
                "any of" if isinstance(error, commands.BotMissingAnyRole) else ""
            )
            embed.description = f"I need {conjunction} the following role(s) to perform this action: {', '.join(role_mentions)}"
            embed.add_field(
                name="Required By", value=f"Command `{command_name}`.", inline=False
            )
            logger.error(  # Using your katlog logger
                f"{log_prefix_katlog}BotMissingRole/BotMissingAnyRole: Bot lacks {missing_roles_input}"
            )
            await ctx.send(embed=embed)

        elif isinstance(error, commands.NSFWChannelRequired):
            embed = create_base_embed(ctx, TITLE_NSFW_REQUIRED, WARN_COLOR)
            embed.description = f"The command `{command_name}` can only be used in a channel marked as NSFW."
            logger.warning(  # Using your katlog logger
                f"{log_prefix_katlog}NSFWChannelRequired: Channel {ctx.channel.name} ({ctx.channel.id}) is not NSFW."
            )
            await ctx.send(embed=embed)

        elif isinstance(error, commands.CheckFailure):
            embed = create_base_embed(ctx, TITLE_CHECK_FAILED, WARN_COLOR)
            check_details = (
                str(error)
                if str(error)
                else "You do not meet the necessary conditions to run this command."
            )
            embed.description = check_details
            logger.warning(  # Using your katlog logger
                f"{log_prefix_katlog}Generic CheckFailure ({type(error).__name__}): {check_details}"
            )
            await ctx.send(embed=embed)

        else:
            error_id = uuid.uuid4()
            embed = create_base_embed(ctx, TITLE_UNEXPECTED_ERROR, ERROR_COLOR)
            embed.description = (
                "An unexpected internal error occurred. This issue has been logged.\n"
                f"If this persists, please report it to {DEV_CONTACT_INFO}."
            )
            embed.add_field(name="Error ID", value=f"`{error_id}`", inline=False)
            embed.add_field(
                name="Error Type",
                value=f"`{type(original_error).__name__}`",
                inline=False,
            )

            await _log_unhandled_error_to_file(
                ctx,
                original_error,
                error_id,
                log_prefix_katlog,  # Pass the katlog prefix
            )

            try:
                await ctx.send(embed=embed)
            except nextcord.Forbidden:
                logger.error(  # Using your katlog logger
                    f"{log_prefix_katlog}Cannot send final error message (ID: {error_id}) due to permissions."
                )
            except Exception as e_send:
                logger.error(  # Using your katlog logger
                    f"{log_prefix_katlog}FAILED TO SEND FINAL ERROR MESSAGE (ID: {error_id}): {e_send}"
                )


def setup(bot: commands.Bot):
    # No need for logging.basicConfig here as katlog handles its own setup
    bot.add_cog(ErrorHandler(bot))
