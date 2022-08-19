import typing

from discord.ext import commands
import discord
from discord.ext.commands import Context
from discord.ext.commands._types import BotT

from bot.util.webhooker import Webhooker


class Conversation(commands.Cog):

    def __init__(self, bot):
        self.bot: commands.Bot = bot

    def cog_check(self, ctx: Context[BotT]) -> bool:
        if ctx.guild.id != 753693459369427044:
            return False
        if isinstance(ctx.channel, discord.Thread):
            return False
        return any([r.id == 753735598854111334 for r in ctx.author.roles])

    @commands.group('move')
    async def move(self, ctx):
        pass

    @move.command(name='from')
    async def move_channel(self, ctx: commands.Context, target: typing.Union[discord.TextChannel, discord.Message], destination: typing.Optional[discord.TextChannel] = None, amount: int = 10):
        if amount > 30:
            amount = 20
        if amount < 1:
            return
        if destination is None:
            destination = ctx.channel

        messages = []

        if isinstance(target, discord.TextChannel):
            channel = target
        else:
            channel = target.channel
            if isinstance(target, discord.PartialMessage):
                target = await target.fetch()
            amount = amount - 1
            messages.append(target)

        perms: discord.Permissions = destination.permissions_for(ctx.author)
        if not perms.view_channel or not perms.read_message_history:
            await ctx.send("You don't have permission for that!")
            return

        perms: discord.Permissions = channel.permissions_for(ctx.author)
        if not perms.view_channel or not perms.read_message_history:
            await ctx.send("You don't have permission for that!")
            return

        webhooker = Webhooker(destination)
        async for message in channel.history(limit=amount, oldest_first=False):
            messages.append(message)
        messages.reverse()
        await webhooker.create_thread_with_messages(messages, creator=ctx.author)

    @move.command(name='reply')
    async def move_replies(self, ctx, message: discord.Message, channel: discord.TextChannel = None, lookback: int = 80):
        if isinstance(message, discord.PartialMessage):
            message = await message.fetch()
        if channel is None:
            channel = message.channel
        webhooker = Webhooker(channel)
        messages = await webhooker.get_reply_chain(message, depth=lookback, loose=False)
        await webhooker.create_thread_with_messages(messages, creator=ctx.author)

    @move.command(name='convo')
    async def move_confo(self, ctx, message: discord.Message, channel: discord.TextChannel = None, lookback: int = 80):
        if lookback > 80:
            lookback = 80
        if lookback < 10:
            lookback = 10
        if isinstance(message, discord.PartialMessage):
            message = await message.fetch()
        if channel is None:
            channel = message.channel
        webhooker = Webhooker(channel)
        messages = await webhooker.get_reply_chain(message, lookback=lookback, loose=True, depth=5, build_depth=4)
        await webhooker.create_thread_with_messages(messages, creator=ctx.author)


async def setup(bot):
    await bot.add_cog(Conversation(bot))
