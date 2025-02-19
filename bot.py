import signal
import threading
import discord
from discord.ext import commands
from database import engine
import yt_dlp
import os
import asyncio
from collections import deque
from dotenv import load_dotenv
from fastapi import FastAPI
import uvicorn
from pydantic import BaseModel

from database import Base

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

async def fetch_song_info(query):
    """Asynchronously fetch song or playlist info."""
    ydl_opts = {'format': 'bestaudio/best', 'quiet': True}
    loop = asyncio.get_running_loop()
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = await loop.run_in_executor(None, lambda: ydl.extract_info(query, download=False))

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
        return [{
            'url': info["url"],
            'title': info.get("title", "Unknown Title"),
            'thumbnail': info.get("thumbnail", None),
            'duration': info.get("duration", 0),
            'channel': info.get("uploader", "Unknown Channel")
        }]

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
    
    # Fetch songs asynchronously
    songs = await fetch_song_info(f"ytsearch:{query}" if "youtube.com" not in query else query)
    queue.extend(songs)

    if not ctx.voice_client or not ctx.voice_client.is_playing():
        await play_next()
     
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


@app.get("/start/")
async def api_start():
    """Set the global context for the bot."""
    global globalCtx
    if not globalCtx:
        return {"error": "No Discord context set. Run !start in Discord."}
    await globalCtx.invoke(bot.get_command("start"))
    return {"status": "Global context set."}
    
   

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


@app.get("/queue/")
async def api_queue():
    global globalCtx
    if not globalCtx:
        return {"error": "No Discord context set. Run !start in Discord."}

    queue = get_queue(globalCtx.guild.id)
    if not queue:
        return {"message": "Queue is empty."}

    return {
        "queue": queue 
    }

async def close_bot():
    """Gracefully closes the bot."""
    print("Shutting down bot...")
    for guild in bot.guilds:
        voice_client = guild.voice_client
        if voice_client:
            queue = get_queue(guild.id)
            queue.clear()  # Clear the queue before disconnecting
            await voice_client.disconnect()
    await bot.close()

async def start_discord_bot():
    """Starts and manages the Discord bot."""
    try:
        await bot.start(TOKEN)
    except Exception as e:
        print(f"Bot startup error: {e}")
    finally:  # Ensure cleanup even if there's an error
        await close_bot()

def signal_handler(sig, frame):
    """Handles Ctrl+C or program termination."""
    print('You pressed Ctrl+C or the program terminated!')
    asyncio.create_task(close_bot()) # Schedule the bot closure

async def start_discord_bot():
    """Starts the Discord bot asynchronously."""
    await bot.start(TOKEN)

def start_fastapi():
    """Starts the FastAPI server in a separate thread."""
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    # Start FastAPI in a separate thread
    Base.metadata.create_all(bind=engine)
    fastapi_thread = threading.Thread(target=start_fastapi, daemon=True)
    fastapi_thread.start()

    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler) # Program termination

    # Run the bot in a try-except-finally block
    try:
        asyncio.run(start_discord_bot())  # Now starts properly
    except KeyboardInterrupt:
        print("Bot terminated by user.")
    finally:
        print("Bot shutdown complete.")