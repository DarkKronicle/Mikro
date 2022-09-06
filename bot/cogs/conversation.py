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
        return any([r.id == 905237148704329770 for r in ctx.author.roles])

    @commands.hybrid_group(name='move')
    async def move(self, ctx):
        pass

    @move.command(name='between')
    async def movebefore(self, ctx: commands.Context, first: discord.Message, second: discord.Message,):
        """Moves messages between two message to a thread.

        :param first: First message
        :param second: Last message
        """
        destination = ctx.channel
        if isinstance(first, discord.PartialMessage):
            first = await first.fetch()
        if isinstance(second, discord.PartialMessage):
            second = await second.fetch()

        if first.channel.id != second.channel.id:
            await ctx.send("The messages have to be in the same channel!", ephemeral=True)
            return

        if first.created_at > second.created_at:
            inter = first
            first = second
            second = inter

        messages = [second]

        perms: discord.Permissions = destination.permissions_for(ctx.author)
        if not perms.view_channel or not perms.read_message_history:
            await ctx.send("You don't have permission for that!", ephemeral=True)
            return

        perms: discord.Permissions = first.channel.permissions_for(ctx.author)
        if not perms.view_channel or not perms.read_message_history:
            await ctx.send("You don't have permission for that!", ephemeral=True)
            return

        await ctx.defer(ephemeral=False)

        webhooker = Webhooker(self.bot, destination)
        async for m in first.channel.history(limit=100, oldest_first=False, before=second, after=first):
            messages.append(m)
        messages.append(first)
        messages.reverse()
        await webhooker.create_thread_with_messages(messages, creator=ctx.author, interaction=ctx.interaction)

    @move.command(name='before')
    async def move_before(self, ctx: commands.Context, message: discord.Message, amount: commands.Range[int, 0, 100]):
        """Moves a message from before a message into a thread.

        :param message: Last message to grab
        :param amount: Amount to grab
        """
        if amount > 100:
            amount = 100
        if amount < 0:
            amount = 0
        destination = ctx.channel
        messages = [message]

        if isinstance(message, discord.PartialMessage):
            message = await message.fetch()

        perms: discord.Permissions = destination.permissions_for(ctx.author)
        if not perms.view_channel or not perms.read_message_history:
            await ctx.send("You don't have permission for that!", ephemeral=True)
            return

        perms: discord.Permissions = message.channel.permissions_for(ctx.author)
        if not perms.view_channel or not perms.read_message_history:
            await ctx.send("You don't have permission for that!", ephemeral=True)
            return

        await ctx.defer(ephemeral=False)

        webhooker = Webhooker(self.bot, destination)
        if amount > 0:
            async for m in message.channel.history(limit=amount, oldest_first=False, before=message):
                messages.append(m)
            messages.reverse()
        await webhooker.create_thread_with_messages(messages, creator=ctx.author, interaction=ctx.interaction)

    @move.command(name='from')
    async def move_channel(self, ctx: commands.Context, channel: discord.TextChannel, amount: commands.Range[int, 1, 100]):
        """Moves messages from a channel into a thread.

        :param channel: Channel to grab from
        :param amount: Amount to grab
        """
        if amount > 100:
            amount = 100
        if amount < 1:
            amount = 1
        destination = ctx.channel
        messages = []

        perms: discord.Permissions = destination.permissions_for(ctx.author)
        if not perms.view_channel or not perms.read_message_history:
            await ctx.send("You don't have permission for that!", ephemeral=True)
            return

        perms: discord.Permissions = channel.permissions_for(ctx.author)
        if not perms.view_channel or not perms.read_message_history:
            await ctx.send("You don't have permission for that!", ephemeral=True)
            return

        await ctx.defer(ephemeral=False)

        webhooker = Webhooker(self.bot, destination)
        async for message in channel.history(limit=amount, oldest_first=False):
            messages.append(message)
        messages.reverse()
        await webhooker.create_thread_with_messages(messages, creator=ctx.author, interaction=ctx.interaction)

    @move.command(name='replychain')
    async def move_replies(self, ctx, message: discord.Message, lookback: commands.Range[int, 10, 80] = 80):
        """Moves a reply chain into a thread

        :param message: Last message of the chain
        :param lookback: Amount of messages to look for
        """
        if lookback > 80:
            lookback = 80
        if lookback < 10:
            lookback = 10
        if isinstance(message, discord.PartialMessage):
            message = await message.fetch()
        destination = ctx.channel

        perms: discord.Permissions = destination.permissions_for(ctx.author)
        if not perms.view_channel or not perms.read_message_history:
            await ctx.send("You don't have permission for that!", ephemeral=True)
            return

        perms: discord.Permissions = message.channel.permissions_for(ctx.author)
        if not perms.view_channel or not perms.read_message_history:
            await ctx.send("You don't have permission for that!", ephemeral=True)
            return

        await ctx.defer(ephemeral=False)
        webhooker = Webhooker(self.bot, destination)
        messages = await webhooker.get_reply_chain(message, depth=lookback, loose=False)
        await webhooker.create_thread_with_messages(messages, creator=ctx.author, interaction=ctx.interaction)

    @move.command(name='conversation')
    async def move_confo(self, ctx, message: discord.Message, lookback: commands.Range[int, 10, 80] = 80):
        """Attempts to find a nested conversation and move it to a thread

        :param message: Last message of the conversation
        :param lookback: Amount of messages to search
        """
        if lookback > 80:
            lookback = 80
        if lookback < 10:
            lookback = 10
        if isinstance(message, discord.PartialMessage):
            message = await message.fetch()

        destination = ctx.channel

        perms: discord.Permissions = destination.permissions_for(ctx.author)
        if not perms.view_channel or not perms.read_message_history:
            await ctx.send("You don't have permission for that!", ephemeral=True)
            return

        perms: discord.Permissions = message.channel.permissions_for(ctx.author)
        if not perms.view_channel or not perms.read_message_history:
            await ctx.send("You don't have permission for that!", ephemeral=True)
            return

        await ctx.defer(ephemeral=False)
        webhooker = Webhooker(self.bot, destination)
        messages = await webhooker.get_reply_chain(message, lookback=lookback, loose=True, depth=6, build_depth=4)
        await webhooker.create_thread_with_messages(messages, creator=ctx.author, interaction=ctx.interaction)


async def setup(bot):
    await bot.add_cog(Conversation(bot))
