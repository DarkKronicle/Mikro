import discord
from discord.ext import commands
from . import parse_content


class Responses(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.id == self.bot.user.id:
            return
        kwargs = await parse_content(self.bot, message.content)
        if len(kwargs) == 0:
            return
        suppressed = False
        for d in kwargs:
            if not suppressed and d.pop('suppress', True):
                await message.edit(suppress=True)
                suppressed = True
            await message.reply(allowed_mentions=discord.AllowedMentions.none(), **d)


async def setup(bot):
    await bot.add_cog(Responses(bot))
