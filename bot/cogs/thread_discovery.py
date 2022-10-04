import asyncio

from discord.ext import commands
import discord

from bot.cogs import stats
from bot.cogs.thread import ThreadData
from bot.core.embed import Embed
from bot.mikro import Mikro


class ThreadDiscovery(commands.Cog):

    def __init__(self, bot):
        self.bot: Mikro = bot

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        if thread.guild.id != 753693459369427044:
            return

        # Give DB time to update
        if not self.bot.thread_handler.is_channel_public(thread.parent):
            # Private stuff
            return
        await asyncio.sleep(2)
        embed = Embed()
        embed.title = 'New Thread'
        embed.color = discord.Colour.green()
        data: ThreadData = await self.bot.thread_handler.get_thread(thread.id)
        owner: discord.Member = data.owner
        embed.set_author(icon_url=owner.display_avatar.url, name=owner.display_name)
        embed.description = '{0}\n\n'.format(thread.mention) + data.starting_message
        embed.timestamp = thread.created_at
        embed.url = thread.jump_url
        await self.discovery_channel.send(embed=embed)

    # This is called from stats
    async def on_message(self, message: discord.Message):
        if not isinstance(message.channel, discord.Thread):
            return
        if message.guild is None or message.guild.id != 753693459369427044:
            return
        if not await self.bot.thread_handler.exists(message.channel.id):
            return
        thread: discord.Thread = message.channel
        if not self.bot.thread_handler.is_channel_public(thread.parent):
            # Private stuff
            return
        data = await self.bot.thread_handler.get_thread(thread.id)
        s: stats.Stats = self.bot.get_cog('Stats')
        amount = await s.get_messages_in_cooldown(message.guild.id, channel_id=message.channel.id, interval=stats.CooldownInterval.hours_3)
        if amount > 0:
            # Don't need to declare that there is new stuff yet
            return
        embed = Embed()
        embed.set_author(name='New Activity', url=thread.jump_url, icon_url=message.author.display_avatar.url)
        embed.description = '{0}\n`{1}` created by {2}'.format(thread.mention, thread.name, data.owner.mention if data.owner is not None else '`Unknown`')
        embed.timestamp = message.created_at
        embed.color = discord.Colour(0x9d0df0)
        await self.discovery_channel.send(embed=embed)

    @property
    def discovery_channel(self):
        return self.bot.get_main_guild().get_channel(1020028115751292938)


async def setup(bot):
    await bot.add_cog(ThreadDiscovery(bot))
