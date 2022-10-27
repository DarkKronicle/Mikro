import discord
from discord.ext import commands

from bot.cogs.thread import ThreadData
from bot.core.context import Context


FORUM_ID = 1019685136343773354


class SupportForum(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    def cog_check(self, ctx: Context) -> bool:
        if not isinstance(ctx.channel, discord.Thread):
            return False
        if ctx.channel.parent.id != FORUM_ID:
            return False
        return True

    @staticmethod
    def is_support(user: discord.Member):
        return any([r.id == 753735598854111334 for r in user.roles])

    @commands.hybrid_command(name="solved")
    async def mark_solved(self, ctx: Context):
        thread_data: ThreadData = await self.bot.thread_handler.get_thread(ctx.channel)
        if not thread_data.owner_id == ctx.author.id and not self.is_support(ctx.author):
            await ctx.send("You're not allowed to do that!", ephemeral=True)
            return
        thread: discord.Thread = ctx.channel
        forum: discord.ForumChannel = thread.parent
        chosen = None
        for tag in forum.available_tags:
            if tag.name == "Solved":
                chosen = tag
                break
        if chosen is not None:
            await thread.add_tags(chosen)
        await thread.edit(archived=True, locked=True)
        await ctx.send("This thread is marked as solved ✅")


async def setup(bot):
    await bot.add_cog(SupportForum(bot))
