import discord
from discord.ext import commands
from bot.util import crash
import re


class Minecraft(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.is_owner()
    @commands.command('crash')
    async def upload_crash(self, ctx, *, url: str):
        if not url.startswith('https://cdn.discordapp.com/attachments'):
            await ctx.send('Not discord :/')
            return
        try:
            result = await crash.upload_crash(url)
        except discord.InvalidData as e:
            await ctx.send('Error! ' + str(e))
            return
        await ctx.send(embed=self.get_crashy_embed(result))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if len(message.attachments) == 0:
            return
        attachment = None
        for a in message.attachments:
            if 'text' in a.content_type and re.match(r"crash-\d{4}-\d{2}-\d{2}_\d{2}\.\d{2}\.\d{2}-client\.txt", a.filename):
                attachment = a
                break
        if attachment is None:
            return
        if not attachment.url.startswith('https://cdn.discordapp.com/attachments'):
            # Only want to download from trusted discord source
            return
        result = await crash.upload_crash(attachment.url)
        await message.reply(embed=self.get_crashy_embed(result), allowed_mentions=discord.AllowedMentions.none())

    def get_crashy_embed(self, url):
        embed = discord.Embed(
            description="Here's a **[formatted crash]({0})**!".format(url),
        )
        return embed


async def setup(bot):
    await bot.add_cog(Minecraft(bot))
