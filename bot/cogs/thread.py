import discord
from discord.ext import commands
from bot.util import cache
import re


class ThreadCommands(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @cache.cache()
    async def get_message(self, channel, message_id):
        return await channel.parent.fetch_message(message_id)

    async def cog_check(self, ctx: commands.Context) -> bool:
        channel: discord.Thread = ctx.channel
        if not isinstance(channel, discord.Thread):
            await ctx.send('You are not in a thread!')
            return False
        if await self.bot.is_owner(ctx.author):
            return True
        message = await self.get_message(channel, channel.id)
        if message.author.id == ctx.author.id:
            return True
        if message.author.id != self.bot.user.id:
            await ctx.send('You are not the owner of the thread!')
            return False
        if len(message.embeds) == 0:
            await ctx.send('You are not the owner of the thread!')
            return False
        if message.embeds[0].description.startswith(ctx.author.mention):
            return True
        await ctx.send('You are not the owner of the thread!')

    @commands.group(name='thread', invoke_without_command=True)
    async def thread_group(self, ctx: commands.Context):
        channel: discord.Thread = ctx.channel
        await ctx.send('Current thread is owned by you and named {0} (id: {1})'.format(channel.name, channel.id))

    @thread_group.command(name='rename')
    async def rename(self, ctx: commands.Context, *, name: str):
        channel: discord.Thread = ctx.channel
        if '[' in name or ']' in name:
            await ctx.send('Sorry, `[` and `]` are not allowed in channel names.')
        if len(name) > 50:
            name = name[:50]
        prefix = re.search(r'\[.+\](\s)?', channel.name)
        if prefix:
            name = prefix.group() + name
        await channel.edit(name=name)

    @thread_group.command(name='pin')
    async def pin(self, ctx: commands.Context, *, pin: discord.Message):
        channel: discord.Thread = ctx.channel
        if isinstance(pin, discord.PartialMessage):
            pin = await pin.fetch()
        if pin.channel.id == channel.id:
            await pin.pin()
        else:
            await channel.send('That message is not in the current thread!')


async def setup(bot):
    await bot.add_cog(ThreadCommands(bot))
