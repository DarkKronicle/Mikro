import discord
from discord.ext import commands

from bot.mikro import Mikro
from bot.util import embed_utils, checks


class Utility(commands.Cog):

    def __init__(self, bot):
        self.bot: Mikro = bot

    @checks.is_admin()
    @commands.command('send')
    async def send_message(self, ctx, channel: discord.TextChannel, *, embed: str):
        embed = embed_utils.deserialize_string(embed)
        await channel.send(embed=embed)

    @checks.is_admin()
    @commands.command('edit')
    async def edit_message(self, ctx, message: discord.Message, *, embed: str):
        embed = embed_utils.deserialize_string(embed)
        await message.edit(embed=embed)

    @commands.is_owner()
    @commands.command('sendimg')
    async def send_image(self, ctx, channel: discord.TextChannel, *, file: str):
        file = discord.File(file)
        await channel.send(file=file)

    @commands.is_owner()
    @commands.command('sync')
    async def sync_commands(self, ctx):
        await self.bot.tree.sync()
        await ctx.send('Done!')

    @commands.is_owner()
    @commands.command('clearcommands')
    async def clear_commands(self, ctx):
        self.bot.tree.clear_commands(guild=None)
        await self.bot.tree.sync()
        await ctx.send('Done!')

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.channel.type != discord.ChannelType.news:
            return
        await message.publish()


async def setup(bot):
    await bot.add_cog(Utility(bot))
