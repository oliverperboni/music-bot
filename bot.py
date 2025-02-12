import discord
from discord.ext import commands
import yt_dlp
import os
import asyncio
from collections import deque
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Set up Discord bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Music queue (stores song info dictionaries for each server)
queues = {}

def get_queue(guild_id):
    """Returns the queue for the guild"""
    if guild_id not in queues:
        queues[guild_id] = deque()
    return queues[guild_id]

def get_playlist_info(playlist_url):
    """Extracts all video information from a YouTube playlist"""
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'force_generic_extractor': True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(playlist_url, download=False)
        
        if "entries" in info:
            return [{
                'url': entry["url"],
                'title': entry.get("title", "Unknown Title"),
                'thumbnail': entry.get("thumbnail", None),
                'duration': entry.get("duration", 0),
                'channel': entry.get("channel", "Unknown Channel")
            } for entry in info["entries"] if entry]

    return []

@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")

async def play_next(ctx):
    """Plays the next song in the queue"""
    guild_id = ctx.guild.id
    queue = get_queue(guild_id)

    if queue:
        song_info = queue.popleft()
        await play_song(ctx, song_info)
    else:
        await ctx.send("🎵 Fila de reprodução vazia, saindo do canal de voz!")
        await ctx.voice_client.disconnect()

async def create_song_embed(song_info, queue_position=None):
    """Creates a rich embed for song information"""
    embed = discord.Embed(
        title=song_info['title'],
        url=song_info['url'],
        color=discord.Color.blue()
    )
    
    if song_info['thumbnail']:
        embed.set_thumbnail(url=song_info['thumbnail'])
    
    embed.add_field(name="Canal", value=song_info['channel'], inline=True)
    
    if song_info['duration']:
        minutes, seconds = divmod(song_info['duration'], 60)
        duration = f"{minutes}:{seconds:02d}"
        embed.add_field(name="Duração", value=duration, inline=True)
    
    if queue_position is not None:
        embed.set_footer(text=f"Posição na fila: {queue_position}")
    else:
        embed.set_footer(text="🎵 Tocando agora")
    
    return embed

async def play_song(ctx, song_info):
    """Plays a song using the provided song information"""
    vc = ctx.voice_client

    if not vc:
        channel = ctx.author.voice.channel
        await channel.connect()
        vc = ctx.voice_client

    FFMPEG_OPTIONS = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn'
    }

    vc.stop()
    vc.play(discord.FFmpegPCMAudio(song_info['url'], **FFMPEG_OPTIONS), 
            after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop))

    embed = await create_song_embed(song_info)
    await ctx.send(embed=embed)

@bot.command()
async def play(ctx, *, query: str):
    """Adds a song or playlist to the queue and plays it"""
    queue = get_queue(ctx.guild.id)

    if "playlist?" in query:
        songs_info = get_playlist_info(query)
        if not songs_info:
            await ctx.send("❌ Não foi possível carregar a playlist.")
            return

        queue.extend(songs_info)
        await ctx.send(f"📋 Adicionadas {len(songs_info)} músicas da playlist à fila.")

        if not ctx.voice_client or not ctx.voice_client.is_playing():
            await play_song(ctx, queue.popleft())
    else:
        ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch:{query}" if "youtube.com" not in query else query, download=False)
            
            if "entries" in info:
                info = info["entries"][0]

            song_info = {
                'url': info["url"],
                'title': info.get("title", "Unknown Title"),
                'thumbnail': info.get("thumbnail", None),
                'duration': info.get("duration", 0),
                'channel': info.get("uploader", "Unknown Channel")
            }

        if ctx.voice_client and ctx.voice_client.is_playing():
            queue.append(song_info)
            embed = await create_song_embed(song_info, len(queue))
            await ctx.send("🎵 Música adicionada à fila:", embed=embed)
        else:
            await play_song(ctx, song_info)

@bot.command()
async def queue(ctx):
    """Shows the current queue"""
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
    """Skips the current song"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭️ Música pulada!")

@bot.command()
async def stop(ctx):
    """Stops the music and clears the queue"""
    queue = get_queue(ctx.guild.id)
    queue.clear()
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
    await ctx.send("⏹️ Reprodução parada e fila limpa!")

bot.run(TOKEN)