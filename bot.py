import discord
from discord.ext import commands
import yt_dlp
import spotipy
import asyncio
import os
import random
from dotenv import load_dotenv
from collections import deque

load_dotenv()

# ── Credentials ────────────────────────────────────────────────────────────────
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

# ── Spotify client (optional, gracefully skipped if creds are missing) ────────
sp = None
if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
    auth_manager = spotipy.SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri="http://127.0.0.1:8888/callback",
        scope="playlist-read-private playlist-read-collaborative",
        cache_path=".spotify_cache"
    )
    sp = spotipy.Spotify(auth_manager=auth_manager, requests_timeout=10, retries=3)

# ── FFmpeg / yt-dlp options ────────────────────────────────────────────────────
FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn -af dynaudnorm=f=150:g=15",
}

YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "extractor_args": {"youtube": {"js_runtimes": ["nodejs:C:\\Program Files\\nodejs\\node.exe"]}},
}

YTDL_PLAYLIST_OPTIONS = {
    "format": "bestaudio/best",
    "extract_flat": "in_playlist",
    "quiet": True,
    "no_warnings": True,
    "source_address": "0.0.0.0",
    "extractor_args": {"youtube": {"js_runtimes": ["nodejs:C:\\Program Files\\nodejs\\node.exe"]}},
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)
ytdl_playlist = yt_dlp.YoutubeDL(YTDL_PLAYLIST_OPTIONS)

# ── Bot setup ──────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ── Per-guild state ────────────────────────────────────────────────────────────
queues: dict[int, deque] = {}
now_playing: dict[int, dict] = {}
idle_timers: dict[int, asyncio.Task] = {}

AUTO_DISCONNECT_SECONDS = 300           # 5 minutes idle before leaving


def get_queue(guild_id: int) -> deque:
    if guild_id not in queues:
        queues[guild_id] = deque()
    return queues[guild_id]


# ── Helpers ────────────────────────────────────────────────────────────────────

def is_spotify_url(url: str) -> bool:
    return "open.spotify.com" in url


def _resolve_spotify_inner(url: str) -> list[str]:
    url = url.split("?")[0].rstrip("/")

    if "/track/" in url:
        track_id = url.split("/track/")[-1]
        track = sp.track(track_id)
        artists = ", ".join(a["name"] for a in track["artists"])
        return [f"{artists} - {track['name']}"]

    elif "/playlist/" in url:
        playlist_id = url.split("/playlist/")[-1]
        results = []
        playlist = sp.playlist_tracks(playlist_id)
        while playlist:
            for item in playlist["items"]:
                track = item.get("item") or item.get("track")
                if track:
                    artists = ", ".join(a["name"] for a in track["artists"])
                    results.append(f"{artists} - {track['name']}")
            playlist = sp.next(playlist) if playlist["next"] else None
        return results

    elif "/album/" in url:
        album_id = url.split("/album/")[-1]
        results = []
        album = sp.album_tracks(album_id)
        while album:
            for track in album["items"]:
                artists = ", ".join(a["name"] for a in track["artists"])
                results.append(f"{artists} - {track['name']}")
            album = sp.next(album) if album["next"] else None
        return results

    raise ValueError("Unsupported Spotify URL type (must be track, album, or playlist)")


def resolve_spotify(url: str) -> list[str]:
    """Resolve a Spotify URL to a list of 'Artist - Title' search strings, with auto-retry on 401."""
    if sp is None:
        raise RuntimeError("Spotify credentials are not configured in .env")
    try:
        return _resolve_spotify_inner(url)
    except spotipy.SpotifyException as e:
        if e.http_status == 401:
            sp._auth_manager.get_access_token(as_dict=False)
            return _resolve_spotify_inner(url)
        raise


async def fetch_audio(search: str) -> dict:
    """Resolve a search string or URL to a streamable audio entry."""
    loop = asyncio.get_event_loop()

    if ("list=" in search or "/playlist" in search) and "spotify" not in search:
        data = await loop.run_in_executor(
            None, lambda: ytdl_playlist.extract_info(search, download=False)
        )
        if "entries" in data:
            entries = []
            for entry in data["entries"]:
                if entry:
                    entries.append({
                        "title": entry.get("title", "Unknown"),
                        "url": None,
                        "_search": f"https://www.youtube.com/watch?v={entry['id']}",
                        "webpage_url": f"https://www.youtube.com/watch?v={entry['id']}",
                    })
            return {"_playlist": True, "entries": entries}

    data = await loop.run_in_executor(
        None, lambda: ytdl.extract_info(search, download=False)
    )
    if "entries" in data:
        data = data["entries"][0]
    return {"title": data["title"], "url": data["url"], "webpage_url": data.get("webpage_url", search)}


def make_np_embed(entry: dict, requester: discord.Member) -> discord.Embed:
    embed = discord.Embed(
        title="🎵 Now Playing",
        description=f"**[{entry['title']}]({entry.get('webpage_url', '')})**",
        color=discord.Color.green(),
    )
    embed.set_footer(text=f"Requested by {requester.display_name}", icon_url=requester.display_avatar.url)
    return embed


def make_queue_embed(guild_id: int) -> discord.Embed:
    q = get_queue(guild_id)
    embed = discord.Embed(title="📋 Queue", color=discord.Color.blurple())
    np = now_playing.get(guild_id)
    if np:
        embed.add_field(
            name="Now Playing",
            value=f"**{np['title']}** — requested by {np['requester'].display_name}",
            inline=False,
        )
    if q:
        lines = []
        for i, item in enumerate(list(q)[:10], 1):
            lines.append(f"`{i}.` {item['title']} — {item['requester'].display_name}")
        if len(q) > 10:
            lines.append(f"*...and {len(q) - 10} more*")
        embed.add_field(name="Up Next", value="\n".join(lines), inline=False)
    else:
        embed.add_field(name="Up Next", value="The queue is empty.", inline=False)
    return embed


def cancel_idle_timer(guild_id: int):
    if guild_id in idle_timers:
        idle_timers[guild_id].cancel()
        del idle_timers[guild_id]


async def start_idle_timer(guild_id: int, vc: discord.VoiceClient):
    await asyncio.sleep(AUTO_DISCONNECT_SECONDS)
    if vc and vc.is_connected() and not vc.is_playing():
        get_queue(guild_id).clear()
        now_playing.pop(guild_id, None)
        await vc.disconnect()


async def play_next(ctx: commands.Context):
    """Play the next track in the queue, lazily fetching audio as needed."""
    cancel_idle_timer(ctx.guild.id)
    q = get_queue(ctx.guild.id)

    if not q:
        now_playing.pop(ctx.guild.id, None)
        await ctx.send("✅ Queue finished. Leaving voice channel.")
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
        return

    entry = q.popleft()

    # Fetch for entries that only have a search term
    if entry.get("url") is None and entry.get("_search"):
        try:
            fetched = await fetch_audio(entry["_search"])
            entry["url"] = fetched["url"]
            entry["title"] = fetched["title"]
            entry["webpage_url"] = fetched.get("webpage_url", "")
        except Exception as e:
            await ctx.send(f"⚠️ Skipping **{entry['title']}** — could not fetch: {e}")
            await play_next(ctx)
            return

    now_playing[ctx.guild.id] = entry
    source = discord.FFmpegPCMAudio(entry["url"], **FFMPEG_OPTIONS)
    source = discord.PCMVolumeTransformer(source, volume=0.5)

    def after_play(error):
        if error:
            print(f"Playback error: {error}")
        asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)

    ctx.voice_client.play(source, after=after_play)
    await ctx.send(embed=make_np_embed(entry, entry["requester"]))


# ── Commands ───────────────────────────────────────────────────────────────────

@bot.command(name="play", aliases=["p"])
async def play(ctx: commands.Context, *, query: str):
    """Play a YouTube URL, Spotify track/album/playlist, or search YouTube."""
    if not ctx.author.voice:
        return await ctx.send("❌ You need to be in a voice channel first.")
    vc = ctx.voice_client
    if vc is None:
        vc = await ctx.author.voice.channel.connect()
    elif vc.channel != ctx.author.voice.channel:
        await vc.move_to(ctx.author.voice.channel)

    cancel_idle_timer(ctx.guild.id)
    q = get_queue(ctx.guild.id)

    async with ctx.typing():
        try:
            if is_spotify_url(query):
                search_terms = resolve_spotify(query)
                if not search_terms:
                    return await ctx.send("❌ Couldn't find any playable tracks from that Spotify link.")
                if len(search_terms) > 1:
                    await ctx.send(f"🔍 Queueing **{len(search_terms)} tracks** from Spotify...")
                for term in search_terms:
                    q.append({"title": term, "url": None, "_search": term, "requester": ctx.author})
                if not vc.is_playing() and not vc.is_paused():
                    await play_next(ctx)
                return
            else:
                result = await fetch_audio(query)
                if result.get("_playlist"):
                    playlist_entries = result["entries"]
                    await ctx.send(f"🔍 Queueing **{len(playlist_entries)} tracks** from playlist...")
                    for e in playlist_entries:
                        e["requester"] = ctx.author
                        q.append(e)
                    if not vc.is_playing() and not vc.is_paused():
                        await play_next(ctx)
                    return
                else:
                    result["requester"] = ctx.author
                    entries = [result]

        except Exception as e:
            return await ctx.send(f"❌ Error: {e}")

    for entry in entries:
        if vc.is_playing() or vc.is_paused() or q:
            q.append(entry)
            await ctx.send(f"➕ Added to queue: **{entry['title']}**")
        else:
            q.append(entry)
            await play_next(ctx)


@bot.command(name="skip", aliases=["s"])
async def skip(ctx: commands.Context):
    """Skip the current track."""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭ Skipped.")
    else:
        await ctx.send("❌ Nothing is playing.")


@bot.command(name="pause")
async def pause(ctx: commands.Context):
    """Pause playback."""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸ Paused.")
    else:
        await ctx.send("❌ Nothing is playing.")


@bot.command(name="resume", aliases=["r"])
async def resume(ctx: commands.Context):
    """Resume playback."""
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Resumed.")
    else:
        await ctx.send("❌ Nothing is paused.")


@bot.command(name="stop")
async def stop(ctx: commands.Context):
    """Stop playback and clear the queue."""
    if ctx.voice_client:
        cancel_idle_timer(ctx.guild.id)
        get_queue(ctx.guild.id).clear()
        now_playing.pop(ctx.guild.id, None)
        ctx.voice_client.stop()
        await ctx.send("⏹ Stopped and queue cleared.")
    else:
        await ctx.send("❌ Not connected.")


@bot.command(name="queue", aliases=["q"])
async def queue_cmd(ctx: commands.Context):
    """Show the current queue."""
    await ctx.send(embed=make_queue_embed(ctx.guild.id))


@bot.command(name="shuffle")
async def shuffle(ctx: commands.Context):
    """Shuffle the queue."""
    q = get_queue(ctx.guild.id)
    if len(q) < 2:
        return await ctx.send("❌ Not enough tracks in the queue to shuffle.")
    q_list = list(q)
    random.shuffle(q_list)
    queues[ctx.guild.id] = deque(q_list)
    await ctx.send("🔀 Queue shuffled!")


@bot.command(name="remove", aliases=["rm"])
async def remove(ctx: commands.Context, index: int):
    """Remove a track from the queue by its position number."""
    q = get_queue(ctx.guild.id)
    if not q:
        return await ctx.send("❌ The queue is empty.")
    if index < 1 or index > len(q):
        return await ctx.send(f"❌ Invalid position. Queue has {len(q)} tracks.")
    q_list = list(q)
    removed = q_list.pop(index - 1)
    queues[ctx.guild.id] = deque(q_list)
    await ctx.send(f"🗑️ Removed **{removed['title']}** from the queue.")


@bot.command(name="volume", aliases=["vol"])
async def volume(ctx: commands.Context, vol: int):
    """Set volume (0–100)."""
    if not ctx.voice_client or not ctx.voice_client.source:
        return await ctx.send("❌ Nothing is playing.")
    if not 0 <= vol <= 100:
        return await ctx.send("❌ Volume must be between 0 and 100.")
    ctx.voice_client.source.volume = vol / 100
    await ctx.send(f"🔊 Volume set to **{vol}%**")


@bot.command(name="leave", aliases=["disconnect", "dc"])
async def leave(ctx: commands.Context):
    """Disconnect the bot from voice."""
    if ctx.voice_client:
        cancel_idle_timer(ctx.guild.id)
        get_queue(ctx.guild.id).clear()
        now_playing.pop(ctx.guild.id, None)
        await ctx.voice_client.disconnect()
    else:
        await ctx.send("❌ Not connected.")


@bot.command(name="nowplaying", aliases=["np"])
async def nowplaying(ctx: commands.Context):
    """Show what's currently playing."""
    np = now_playing.get(ctx.guild.id)
    if np:
        await ctx.send(embed=make_np_embed(np, np["requester"]))
    else:
        await ctx.send("❌ Nothing is playing right now.")


# ── Auto disconnect on voice state change ──────────────────────────────────────

@bot.event
async def on_voice_state_update(member, before, after):
    """Start idle timer if bot is left alone in a voice channel."""
    if member.bot:
        return
    guild = member.guild
    vc = guild.voice_client
    if vc is None:
        return
    members = [m for m in vc.channel.members if not m.bot]
    if len(members) == 0:
        task = asyncio.create_task(start_idle_timer(guild.id, vc))
        idle_timers[guild.id] = task
    else:
        cancel_idle_timer(guild.id)


# ── Events ─────────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument. Usage: `!{ctx.command.name} <query>`")
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        await ctx.send(f"❌ An error occurred: {error}")
        raise error


# ── Run ────────────────────────────────────────────────────────────────────────
bot.run(DISCORD_TOKEN)