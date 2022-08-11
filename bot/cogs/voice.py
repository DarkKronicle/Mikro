import random

import discord
import json
from discord.ext import commands

import pafy
from discord import FFmpegPCMAudio
import asyncio
from bot.util.func_utils import store_func


FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}


class Voice(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        with open('config/voice.json', 'r') as f:
            self.config = json.load(f)

    def after(self, voice_client: discord.VoiceClient, error):
        coro = voice_client.disconnect()
        fut = asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
        fut.result()

    def get_user_audio(self, user_id):
        return self.config.get('join_sound', {}).get(str(user_id), None)

    # @commands.Cog.listener() disable for now
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if not (before.channel is None and after.channel is not None):
            return

        data = self.get_user_audio(member.id)
        if data is None:
            return
        data = random.choice(data)
        url = data[0]

        voice = after.channel
        voice_client: discord.VoiceClient = discord.utils.get(self.bot.voice_clients, guild=voice.guild)

        if voice_client is None:
            voice_client = await voice.connect()
        else:
            await voice_client.move_to(voice)

        source = discord.PCMVolumeTransformer(self.get_source(url), data[1])
        after_func = store_func(self.after, voice_client)
        voice_client.play(source, after=after_func)

    def get_source(self, url: str):
        if url.startswith('https://www.youtube.com/') or url.startswith('https://youtube.com/'):
            return self.get_youtube_source(url)
        return FFmpegPCMAudio(url, **FFMPEG_OPTIONS)

    def get_youtube_source(self, url):
        song = pafy.new(url)
        audio = song.getbestaudio()
        return FFmpegPCMAudio(audio.url, **FFMPEG_OPTIONS)


async def setup(bot):
    await bot.add_cog(Voice(bot))
