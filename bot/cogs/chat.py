import json
from datetime import datetime

from discord.ext import commands
import discord
from bot.mikro import Mikro
import traceback
from bot.util import cache


class Chat(commands.Cog):

    def __init__(self, bot):
        self.bot: Mikro = bot
        self.bot.add_loop('status', self.update_status)
        self.score = 0
        self.users = cache.ExpiringDict(30)

    async def cog_load(self) -> None:
        try:
            with open('storage.json', 'r') as f:
                self.score = json.load(f)['chat_score']
        except:
            pass

    async def cog_unload(self) -> None:
        try:
            with open('storage.json', 'w') as f:
                json.dump({'chat_score': self.score}, f, indent=4)
        except Exception as e:
            traceback.print_exc()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.guild.id is None or message.guild.id != 753693459369427044:
            return
        if message.author.id not in self.users:
            self.score += 1
            self.users[message.author.id] = 1

    async def update_status(self, time: datetime):
        if time.minute % 5 == 0:
            self.score -= 1
            await self.set_status()

    async def set_status(self):
        activity = discord.Activity(
            type=discord.ActivityType.playing,
            name='with {0} chat HP'.format(self.score),
        )
        await self.bot.change_presence(status=discord.Status.online, activity=activity)


async def setup(bot):
    await bot.add_cog(Chat(bot))
