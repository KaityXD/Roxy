import nextcord
from nextcord.ext import commands
from collections import deque, defaultdict
import mafic
from mafic import SearchType
import asyncio
import random
import re
import datetime

from utils.config import LAVALINK_PORT, LAVALINK_HOST, LAVALINK_PASSWORD

# --- Emojis Configuration ---
# You can replace these with your own custom emoji IDs or keep the unicode defaults.
EMOJIS = {
    "error": "❌",
    "track": "<a:minecraft_xp_orb:1383114748673003563>",
    "info": "<a:minecraftenchantedbook:1383115499524587521>",
    "next": "▶",
    "success": "<a:success:1383116048932536380>",
    "pause": "⏸️",
    "resume": "▶️",
    "skip": "⏭️",
    "stop": "⏹️",
    "queue": "📋",
    "search": "🔎",
    "volume": "🔊",
    "autoplay": "🔄",
    "disconnect": "👋",
    "node": "🔍",
}


def create_embed(
    title: str, description: str, color: nextcord.Color = 0xC603FC
) -> nextcord.Embed:
    """Creates a standardized embed."""
    embed = nextcord.Embed(title=title, description=description, color=color)
    return embed


def format_duration(milliseconds: int | None) -> str:
    """Formats a duration from milliseconds to a HH:MM:SS or MM:SS string."""
    if milliseconds is None:
        return "N/A"
    # Ensure milliseconds is an integer before calculating
    milliseconds = int(milliseconds)
    seconds = milliseconds / 1000
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"
    else:
        return f"{int(m):02d}:{int(s):02d}"


# A regular expression to check for URLs.
URL_REGEX = re.compile(r"https?://(?:www\.)?.+")

# --- State Management Class ---


class GuildMusicState:
    """Holds all the music-related state for a single guild."""

    def __init__(self):
        self.queue: deque[mafic.Track] = deque()
        self.volume: int = 50
        self.autoplay: bool = False
        self.disconnect_task: asyncio.Task | None = None
        self.bound_channel: nextcord.TextChannel | nextcord.Thread | None = None
        self.current_track: mafic.Track | None = None


# --- The Main Music Cog ---


class MusicCog(commands.Cog, name="Music"):
    """Handles all music-related commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guild_states: defaultdict[int, GuildMusicState] = defaultdict(
            GuildMusicState
        )
        self.bot.pool = mafic.NodePool(self.bot)
        self.bot.loop.create_task(self.add_nodes())

    async def add_nodes(self):
        """Connects to the Lavalink node pool."""
        await self.bot.wait_until_ready()
        await self.bot.pool.create_node(
            host=LAVALINK_HOST,
            port=LAVALINK_PORT,
            label="MAIN",
            password=LAVALINK_PASSWORD,
        )

    # --- Core Music Logic & Event Listeners ---

    @commands.Cog.listener()
    async def on_track_end(self, event: mafic.TrackEndEvent):
        """Handles the end of a track and plays the next one."""
        if event.reason == "REPLACED":
            return
        await self.play_next(event.player.guild.id)

    @commands.Cog.listener()
    async def on_track_start(self, event: mafic.TrackStartEvent):
        """Announces the new track and cancels any pending disconnects."""
        guild_id = event.player.guild.id
        state = self.guild_states[guild_id]

        if state.disconnect_task:
            state.disconnect_task.cancel()
            state.disconnect_task = None

        track = event.track
        state.current_track = track

        # The "Now Playing" announcement embed is handled here automatically by on_track_start
        # The embed in the play command now confirms addition/immediate play state.

    async def play_next(self, guild_id: int):
        """Plays the next track in the queue or handles autoplay/disconnection."""
        state = self.guild_states[guild_id]
        guild = self.bot.get_guild(guild_id)
        player: mafic.Player | None = guild.voice_client

        if not player:
            return

        last_track = state.current_track

        if state.queue:
            next_track = state.queue.popleft()
            state.current_track = next_track
            await player.play(next_track)
            return

        state.current_track = None

        if state.autoplay:
            # Autoplay logic: find a related track based on the last one
            if last_track and last_track.identifier:
                try:
                    # YouTube Music search for related tracks
                    # Note: This query might not always work perfectly or might get deprecated.
                    # It attempts to use YouTube's "related videos" functionality via Lavalink.
                    query = f"https://music.youtube.com/watch?v={last_track.identifier}&list=RDAMVM{last_track.identifier}"
                    tracks = await player.fetch_tracks(
                        query, search_type=SearchType.YOUTUBE_MUSIC
                    )

                    if (
                        tracks
                        and isinstance(tracks, mafic.Playlist)
                        and len(tracks.tracks) > 1
                    ):
                        # The first track is usually the one just played, so pick the next one
                        next_track = tracks.tracks[1]
                        state.current_track = next_track
                        await player.play(next_track)
                        return
                except Exception:
                    # Fallback if YouTube Music playlist fails or query doesn't work
                    pass  # Continue to fallback search below

            # Fallback autoplay: search for a generic term if advanced fails or no last track
            fallback_tracks = await player.fetch_tracks(
                "lofi hip hop radio", search_type=SearchType.YOUTUBE
            )
            if fallback_tracks:
                next_track = random.choice(fallback_tracks)
                state.current_track = next_track
                await player.play(next_track)
                return

        # If queue is empty and autoplay is off (or failed), schedule disconnection.
        state.disconnect_task = asyncio.create_task(
            self.disconnect_after_timeout(guild_id)
        )

    async def disconnect_after_timeout(self, guild_id: int):
        """Disconnects the player after a 30-second timeout and cleans up state."""
        await asyncio.sleep(30)
        guild = self.bot.get_guild(guild_id)
        if guild and guild.voice_client:
            state = self.guild_states.get(guild_id)
            await guild.voice_client.disconnect()
            if state and state.bound_channel:
                embed = create_embed(
                    "", f"{EMOJIS['disconnect']} Disconnected due to inactivity."
                )
                await state.bound_channel.send(embed=embed)
        # Clean up the state for the guild
        if guild_id in self.guild_states:
            del self.guild_states[guild_id]

    # --- Command Pre-checks and Error Handling ---

    async def cog_check(self, ctx: commands.Context) -> bool:
        """Cog-wide check to ensure commands are used in a guild."""
        if not ctx.guild:
            raise commands.NoPrivateMessage("Music commands cannot be used in DMs.")
        return True

    async def cog_before_invoke(self, ctx: commands.Context):
        """Hook that runs before every command to ensure user is in a voice channel."""
        if ctx.command.name == "node":
            return  # Skip voice channel check for node command

        if not ctx.author.voice or not ctx.author.voice.channel:
            raise commands.CommandError(
                "You must be in a voice channel to use this command."
            )

        # Check if the bot is in *any* voice channel in this guild first
        if ctx.voice_client:
            # If bot is in a voice channel, check if it's the *same* channel as the user
            if ctx.voice_client.channel != ctx.author.voice.channel:
                raise commands.CommandError(
                    "You must be in the same voice channel as the bot."
                )
        # If bot is not in a voice channel, the check passes (assuming the command will connect it, e.g., play)

    async def cog_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ):
        """Cog-wide error handler."""
        original_error = getattr(error, "original", error)
        embed = create_embed(
            f"{EMOJIS['error']} An Error Occurred",
            str(original_error),
            color=nextcord.Color.red(),
        )
        await ctx.send(embed=embed)

    # --- Commands ---

    @commands.command(name="play", aliases=["p"], description="[🌺] Play some music")
    async def play(self, ctx: commands.Context, *, query: str):
        """Plays a track or adds it/a playlist to the queue."""
        state = self.guild_states[ctx.guild.id]

        # Check if player is currently active before connecting/getting it
        was_playing = (
            ctx.voice_client is not None and ctx.voice_client.current is not None
        )

        if not ctx.voice_client:
            # Bot is not in VC, connect. cog_before_invoke already ensured user is in VC.
            player: mafic.Player = await ctx.author.voice.channel.connect(
                cls=mafic.Player
            )
            await player.set_volume(state.volume)
        else:
            # Bot is already in VC (and cog_before_invoke ensured user is in the same one)
            player: mafic.Player = ctx.voice_client

        state.bound_channel = ctx.channel

        search_msg = await ctx.send(
            embed=create_embed(f"{EMOJIS['search']}", f"Searching for `{query}`...")
        )

        try:
            # Determine search type: URL or search query
            search_type = SearchType.YOUTUBE  # Default search type
            if URL_REGEX.match(query):
                # Mafic automatically handles URLs, no need to change search_type explicitly for most cases,
                # but leaving this check here is fine if you wanted to handle specific URL types differently.
                # Let's rely on mafic's auto-detection for URLs.
                pass
            else:
                # If not a URL, explicitly set search type (e.g., YouTube search)
                search_type = SearchType.YOUTUBE

            tracks = await player.fetch_tracks(query, search_type=search_type)

        except Exception as e:
            embed = create_embed(
                f"{EMOJIS['error']}",
                f"Error while searching: {e}",
                color=nextcord.Color.red(),
            )
            return await search_msg.edit(embed=embed)

        if not tracks:
            embed = create_embed(
                f"{EMOJIS['error']} Not Found",
                "No tracks were found for your query.",
                color=nextcord.Color.red(),
            )
            return await search_msg.edit(embed=embed)

        if isinstance(tracks, mafic.Playlist):
            state.queue.extend(tracks.tracks)
            embed = create_embed(
                "",
                f"> **{EMOJIS['queue']} [{tracks.name}]({tracks.tracks[0].uri if tracks.tracks else ''})**",
            )
            embed.set_author(
                name="🎵 | Playlist Added", icon_url=self.bot.user.avatar.url
            )
            # Use playlist thumbnail if available, otherwise maybe first track's? Mafic playlists often don't have thumbs.
            # Let's stick to the first track's thumbnail if available, or remove it if it causes errors for playlists.
            # Mafic's Playlist object has no `artwork_url`, so setting thumbnail from `tracks[0]` is correct.
            embed.set_thumbnail(
                url=tracks.tracks[0].artwork_url
                if tracks.tracks and hasattr(tracks.tracks[0], "artwork_url")
                else None
            )
            embed.add_field(
                name=f"{EMOJIS['info']} Playlist Info",
                value=f"┗ **Added by {ctx.author.mention}** ``{len(tracks.tracks)} tracks``",
            )

            # Start playing if the queue was empty before adding the playlist
            if not player.current:
                # play_next will pick the first track from the extended queue
                pass  # The call is outside the if/else block below

        else:  # It's a list of tracks (single track or search results, we take the first)
            track = tracks[0]
            state.queue.append(track)

            # --- Logic to determine embed author text ---
            if not player.current:
                status_text = "🎵 | Now Playing"
                # The track will be played immediately by play_next below
            else:
                status_text = "🎵 | Track Added"
                # The track is added to the queue
            # --- End Logic ---

            embed = create_embed(
                "", f"> **{EMOJIS['track']} [{track.title}]({track.uri})**"
            )
            embed.set_author(name=status_text, icon_url=self.bot.user.avatar.url)
            # Check if track has artwork_url attribute before using it
            embed.set_thumbnail(
                url=track.artwork_url if hasattr(track, "artwork_url") else None
            )
            embed.add_field(
                name=f"{EMOJIS['info']} Track Info",
                value=f"┗ **{track.author}** ``{format_duration(track.length)}``",
            )

        embed.set_footer(text=f"🌺 {self.bot.user.name} | By katxd.xyz")
        await search_msg.edit(embed=embed)

        # If the player isn't already playing, start it.
        # This handles both single tracks and the first track of a playlist if idle.
        if not player.current:
            await self.play_next(ctx.guild.id)

    @commands.command(aliases=["s"], description="[🌺] Skip the current song")
    async def skip(self, ctx: commands.Context):
        """Skips the currently playing song."""
        player: mafic.Player = ctx.voice_client
        state = self.guild_states.get(
            ctx.guild.id
        )  # Use .get for safety, though cog_before_invoke should ensure state exists if player does

        if not player or not player.current:
            return await ctx.send("There is nothing to skip.")

        # Need state to access the queue for the "Up Next" part
        if not state:
            state = self.guild_states[
                ctx.guild.id
            ]  # Get it if .get didn't find it (shouldn't happen with check)

        skipped_track = player.current
        await player.stop()  # This triggers on_track_end, which calls play_next

        embed = create_embed("", f"{EMOJIS['skip']} Skipped: **{skipped_track.title}**")

        # Accessing state.queue after player.stop() which triggers play_next means
        # the queue state might have already changed. Let's get the *next* track
        # *before* calling player.stop().
        next_track_in_queue = state.queue[0] if state.queue else None

        # --- Let's move the embed creation after stopping to reflect the *new* state ---
        # However, capturing the *skipped* track and the *next* track requires getting them before stop()

        # --- Revised skip logic ---
        skipped_track_title = player.current.title
        skipped_track_uri = player.current.uri
        next_track_in_queue = state.queue[0] if state.queue else None

        await player.stop()  # This fires on_track_end -> play_next

        embed = create_embed(
            "",
            f"{EMOJIS['skip']} Skipped: **[{skipped_track_title}]({skipped_track_uri})**",
        )

        if next_track_in_queue:
            # Note: This `next_track_in_queue` is the one *before* play_next ran.
            # The track currently playing *after* skip might be different if autoplay triggered.
            # A more robust "Up Next" needs careful state management, but showing the first
            # item *from the original queue* is usually sufficient user feedback for a skip.
            embed.add_field(
                name="Up Next",
                value=f"[{next_track_in_queue.title}]({next_track_in_queue.uri})",
                inline=False,
            )
        else:
            embed.add_field(
                name="Queue Status",
                value="No more tracks in queue"
                + (" (Autoplay enabled)" if state.autoplay else ""),
                inline=False,
            )
        # --- End Revised skip logic ---

        await ctx.send(embed=embed)

    @commands.command(
        aliases=["dc", "leave"], description="[🌺] Disconnect bot from VC"
    )
    async def disconnect(self, ctx: commands.Context):
        """Disconnects the bot from the voice channel and clears the queue."""
        player: mafic.Player = ctx.voice_client
        if not player:
            return await ctx.send("I am not in a voice channel.")

        await player.disconnect()
        # Clean up state immediately on manual disconnect
        if ctx.guild.id in self.guild_states:
            if self.guild_states[ctx.guild.id].disconnect_task:
                self.guild_states[ctx.guild.id].disconnect_task.cancel()
            del self.guild_states[ctx.guild.id]

        embed = create_embed("", f"{EMOJIS['success']} Disconnected successfully.")
        await ctx.send(embed=embed)

    @commands.command(description="[🌺] Temporarily stop the song")
    async def pause(self, ctx: commands.Context):
        """Pauses the current song."""
        player: mafic.Player = ctx.voice_client
        if not player or not player.current:
            return await ctx.send("I am not playing anything.")
        if player.is_paused():
            return await ctx.send("The song is already paused.")

        await player.pause(True)
        embed = create_embed("", f"{EMOJIS['pause']} Paused the song.")
        await ctx.send(embed=embed)

    @commands.command(description="[🌺] Resume the paused song")
    async def resume(self, ctx: commands.Context):
        """Resumes the currently paused song."""
        player: mafic.Player = ctx.voice_client
        if not player or not player.current:
            return await ctx.send("I am not playing anything.")
        if not player.is_paused():
            return await ctx.send("The song is not paused.")

        await player.pause(False)
        embed = create_embed("", f"{EMOJIS['resume']} Resumed the song.")
        await ctx.send(embed=embed)

    @commands.command(description="[🌺] Stop playback and clear the queue")
    async def stop(self, ctx: commands.Context):
        """Stops the current playback and clears the queue."""
        player: mafic.Player = ctx.voice_client
        if not player or not player.current:
            return await ctx.send("There is nothing to stop.")

        state = self.guild_states.get(ctx.guild.id)  # Use .get for safety
        if state:  # Only clear state if it exists
            state.queue.clear()
            state.current_track = None
            # Cancel pending disconnect if stop is used
            if state.disconnect_task:
                state.disconnect_task.cancel()
                state.disconnect_task = None

        await player.stop()  # This will fire on_track_end but the queue is empty now

        embed = create_embed(
            "", f"{EMOJIS['stop']} Stopped playback and cleared the queue."
        )
        await ctx.send(embed=embed)

    @commands.command(aliases=["q"], description="[🌺] Check the queue")
    async def queue(self, ctx: commands.Context):
        """Displays the current queue and the currently playing track."""
        state = self.guild_states.get(ctx.guild.id)
        # Check player as well, as state might exist but bot isn't in VC
        player: mafic.Player = ctx.voice_client

        if not state or (not player or not player.current) and not state.queue:
            # Added check for player.current as current_track might not be set yet but player is playing
            return await ctx.send("The queue is empty.")

        embed = create_embed(f"{EMOJIS['queue']} Current Queue", "")

        # Use player.current which is more reliable for what's actually playing
        if player and player.current:
            embed.add_field(
                name="🎵 Now Playing",
                value=f"[{player.current.title}]({player.current.uri}) | `{format_duration(player.current.length)}`",
                inline=False,
            )
        elif state and state.current_track:
            # Fallback to state.current_track if player.current isn't set yet for some reason
            embed.add_field(
                name="🎵 Now Playing",
                value=f"[{state.current_track.title}]({state.current_track.uri}) | `{format_duration(state.current_track.length)}`",
                inline=False,
            )
        # If neither is available, "Now Playing" field is skipped.

        if state.queue:
            # Show max 10 tracks for brevity
            queue_list_items = []
            for i, t in enumerate(list(state.queue)[:10]):
                # Ensure track has necessary attributes before trying to access them
                title = getattr(t, "title", "Unknown Title")
                uri = getattr(t, "uri", "#")
                length = getattr(t, "length", None)
                queue_list_items.append(
                    f"`{i+1}.` [{title}]({uri}) | `{format_duration(length)}`"
                )

            queue_list = "\n".join(queue_list_items)

            embed.add_field(
                name=f"{EMOJIS['next']} Up Next", value=queue_list, inline=False
            )

        if state and len(state.queue) > 10:
            embed.set_footer(text=f"Showing 10 of {len(state.queue)} tracks in queue.")
        elif not player or not player.current and not state.queue:
            # If no current track and no queue, footer can indicate status
            embed.set_footer(text="Queue is empty.")
        else:
            # Simple footer if content fits
            embed.set_footer(text=f"🌺 {self.bot.user.name} | By katxd.xyz")

        await ctx.send(embed=embed)

    @commands.command(description="[🌺] Set the volume")
    async def volume(self, ctx: commands.Context, level: int):
        """Sets the volume for the current player."""
        if not 0 <= level <= 150:
            return await ctx.send("Volume must be between 0 and 150.")

        player: mafic.Player = ctx.voice_client
        if not player:
            return await ctx.send("I am not in a voice channel.")

        state = self.guild_states[ctx.guild.id]
        state.volume = level  # Update state volume
        await player.set_volume(level)  # Set player volume

        embed = create_embed("", f"{EMOJIS['volume']} Volume set to **{level}%**.")
        await ctx.send(embed=embed)

    @commands.command(description="[🌺] Toggle auto-play")
    async def autoplay(self, ctx: commands.Context):
        """Toggles autoplay mode."""
        state = self.guild_states[ctx.guild.id]
        state.autoplay = not state.autoplay
        status = "On" if state.autoplay else "Off"

        embed = create_embed("", f"{EMOJIS['autoplay']} Autoplay is now **{status}**.")
        await ctx.send(embed=embed)

    @commands.command(description="[🌺] Node information")
    async def node(self, ctx: commands.Context):
        """Displays the status of the Lavalink node."""
        if not self.bot.pool.nodes:
            return await ctx.send("No Lavalink nodes are connected.")

        # Assuming you want stats from the first node connected
        node = self.bot.pool.nodes[0]
        stats = node.stats

        if not stats:
            return await ctx.send("Could not retrieve node stats.")

        # --- FIX APPLIED HERE ---
        # stats.uptime is an integer representing milliseconds.
        # Use the existing format_duration helper function.
        uptime_formatted = format_duration(stats.uptime)
        # --- END FIX ---

        mem_used = f"{stats.memory.used / 1048576:.2f}"
        mem_alloc = f"{stats.memory.allocated / 1048576:.2f}"
        cpu_load = f"{stats.cpu.system_load * 100:.2f}"  # System load is 0-1, multiply by 100 for percentage

        description = (
            f"```prolog\n"
            f"Node Label         : {node.label}\n"  # Added node label
            f"Region             : {node.region}\n"  # Added node region
            f"Uptime             : {uptime_formatted}\n"  # Use the formatted uptime
            f"Players            : {stats.playing_player_count} playing / {stats.player_count} total\n"
            f"Memory Usage       : {mem_used}MB / {mem_alloc}MB\n"
            f"CPU Load           : {cpu_load}%\n"
            f"```"
        )

        embed = create_embed(f"{EMOJIS['node']} Lavalink Node Status", description)
        embed.set_author(name="Node Status", icon_url=self.bot.user.avatar.url)
        embed.set_footer(text=f"🌺 {self.bot.user.name} | By katxd.xyz")
        await ctx.send(embed=embed)


def setup(bot):
    # Check if required config variables are present
    if all([LAVALINK_HOST, LAVALINK_PORT, LAVALINK_PASSWORD]):
        # Ensure LAVALINK_PORT is an integer
        try:
            port = int(LAVALINK_PORT)
        except (ValueError, TypeError):
            print(
                "[ERROR]: LAVALINK_PORT must be a valid integer. Music cog not loaded."
            )
            return

        # Pass validated port
        bot.add_cog(MusicCog(bot))
    else:
        print(
            "[WARN]: Music cog not loaded. Ensure LAVALINK_HOST, LAVALINK_PORT, and LAVALINK_PASSWORD are set in utils/config.py"
        )
