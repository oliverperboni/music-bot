import threading
import discord
from discord.ext import commands
import yt_dlp
import os
import asyncio
from collections import deque
from dotenv import load_dotenv
from fastapi import FastAPI
import uvicorn
from pydantic import BaseModel

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
globalCtx = None
queues = {}


class SongRequest(BaseModel):
    song: str

# FastAPI setup
app = FastAPI()

def get_queue(guild_id):
    if guild_id not in queues:
        queues[guild_id] = deque()
    return queues[guild_id]

async def play_song(song_info):
    global globalCtx
    if not globalCtx:
        return

    vc = globalCtx.voice_client
    if not vc:
        channel = globalCtx.author.voice.channel
        await channel.connect()
        vc = globalCtx.voice_client

    if vc.is_playing() or vc.is_paused():
        vc.stop()
        await asyncio.sleep(1)

    FFMPEG_OPTIONS = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn'
    }

    vc.play(discord.FFmpegPCMAudio(song_info['url'], **FFMPEG_OPTIONS),
            after=lambda e: asyncio.run_coroutine_threadsafe(play_next(), bot.loop))

    embed = discord.Embed(title=song_info['title'], url=song_info['url'], color=discord.Color.blue())
    if song_info['thumbnail']:
        embed.set_thumbnail(url=song_info['thumbnail'])
    embed.add_field(name="Canal", value=song_info['channel'], inline=True)
    await globalCtx.send(embed=embed)

async def play_next():
    global globalCtx
    if not globalCtx:
        return
    guild_id = globalCtx.guild.id
    queue = get_queue(guild_id)

    if queue:
        song_info = queue.popleft()
        await play_song(song_info)
    else:
        await globalCtx.send("🎵 Fila vazia, saindo do canal de voz!")
        await globalCtx.voice_client.disconnect()

@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")

@bot.command()
async def start(ctx):
    global globalCtx
    globalCtx = ctx
    await ctx.send("🎶 Contexto global definido!")

@bot.command()
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ Música pausada!")

@bot.command()
async def unpause(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Música retomada!")

@bot.command()
async def play(ctx, *, query: str):
    global globalCtx
    globalCtx = ctx
    queue = get_queue(ctx.guild.id)

    async def fetch_song_info(query):
        """Extract song or playlist info."""
        ydl_opts = {'format': 'bestaudio/best', 'quiet': True}
        loop = asyncio.get_event_loop()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(query, download=False))

            # If it's a playlist, return all songs
            if "entries" in info:
                return [
                    {
                        'url': entry["url"],
                        'title': entry.get("title", "Unknown Title"),
                        'thumbnail': entry.get("thumbnail", None),
                        'duration': entry.get("duration", 0),
                        'channel': entry.get("uploader", "Unknown Channel")
                    }
                    for entry in info["entries"]
                ]
            # Otherwise, return a single song
            return [{
                'url': info["url"],
                'title': info.get("title", "Unknown Title"),
                'thumbnail': info.get("thumbnail", None),
                'duration': info.get("duration", 0),
                'channel': info.get("uploader", "Unknown Channel")
            }]

    # Fetch song(s) from query
    songs = await fetch_song_info(f"ytsearch:{query}" if "youtube.com" not in query else query)

    # Add all songs to queue
    queue.extend(songs)

    # If the bot isn't already playing, start playing
    if not ctx.voice_client or not ctx.voice_client.is_playing():
        await play_next()

    # Respond to user
    if len(songs) > 1:
        await ctx.send(f"🎶 Playlist adicionada à fila: **{len(songs)} músicas**!")
    else:
        await ctx.send(f"🎵 Música adicionada à fila: **{songs[0]['title']}**")


@bot.command()
async def queue(ctx):
    queue = get_queue(ctx.guild.id)
    if not queue:
        await ctx.send("❌ A fila está vazia!")
        return

    embed = discord.Embed(
        title="🎵 Fila de Reprodução",
        color=discord.Color.blue()
    )

    for i, song_info in enumerate(queue, 1):
        embed.add_field(
            name=f"{i}. {song_info['title']}", 
            value=f"Canal: {song_info['channel']}", 
            inline=False
        )

    await ctx.send(embed=embed)

@bot.command()
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭️ Música pulada!")

@bot.command()
async def stop(ctx):
    queue = get_queue(ctx.guild.id)
    queue.clear()
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
    await ctx.send("⏹️ Reprodução parada e fila limpa!")

# === API ENDPOINTS ===
@app.get("/")
async def root():
    return {"message": "Discord Bot API is running!"}

@app.post("/play/")
async def api_play(request: SongRequest):
    global globalCtx
    
    if not globalCtx:
        return {"error": "Bot is not connected to a server yet."}

    command = bot.get_command("play")
    if not command:
        return {"error": "Play command not found."}

    # Schedule the command inside the bot's event loop
    bot.loop.create_task(globalCtx.invoke(command, query=request.song))
    
    return {"status": "Playing song request received!"}

@app.post("/pause/")
async def api_pause():
    """Pause the music"""
    global globalCtx
    if not globalCtx:
        return {"error": "No Discord context set. Run !start in Discord."}

    await globalCtx.invoke(bot.get_command("pause"))
    return {"status": "Music paused"}

@app.post("/unpause/")
async def api_unpause():
    """Unpause the music"""
    global globalCtx
    if not globalCtx:
        return {"error": "No Discord context set. Run !start in Discord."}

    await globalCtx.invoke(bot.get_command("unpause"))
    return {"status": "Music resumed"}

@app.post("/skip/")
async def api_skip():
    """Skip the current song"""
    global globalCtx
    if not globalCtx:
        return {"error": "No Discord context set. Run !start in Discord."}

    if globalCtx.voice_client and globalCtx.voice_client.is_playing():
        globalCtx.voice_client.stop()
        return {"status": "Song skipped"}
    return {"error": "No song is playing"}

@app.post("/stop/")
async def api_stop():
    """Stop music and clear the queue"""
    global globalCtx
    if not globalCtx:
        return {"error": "No Discord context set. Run !start in Discord."}

    queue = get_queue(globalCtx.guild.id)
    queue.clear()
    if globalCtx.voice_client:
        await globalCtx.voice_client.disconnect()
    return {"status": "Playback stopped and queue cleared"}

async def start_discord_bot():
    """Starts the Discord bot asynchronously."""
    await bot.start(TOKEN)

def start_fastapi():
    """Starts the FastAPI server in a separate thread."""
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    # Start FastAPI in a separate thread
    fastapi_thread = threading.Thread(target=start_fastapi, daemon=True)
    fastapi_thread.start()

    # Start the Discord bot in the main async event loop
    asyncio.run(start_discord_bot())
