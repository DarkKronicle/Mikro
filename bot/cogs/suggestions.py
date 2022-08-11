from typing import Any

import discord
from discord import Interaction
from discord.ext import commands
import bot as bot_global
import re


suggestion_types = {
    'Mod': ('⛏️', 'Minecraft mod suggestion'),
    'Discord': ('🇩', 'Discord server specific suggestion'),
}


class SuggestionDropdown(discord.ui.Select):

    def __init__(self, thread, message):
        self.thread = thread
        self.message = message
        options = []
        for key, value in suggestion_types.items():
            options.append(discord.SelectOption(label=key, description=value[1], emoji=value[0]))
        super().__init__(options=options, placeholder='Suggestion type', max_values=1, min_values=1)

    async def callback(self, interaction: Interaction) -> Any:
        await self.message.delete()
        await self.thread.edit(name=Suggestions.get_type_name(self.values[0], self.thread))
        await interaction.response.send_message('Done!')


class SuggestionView(discord.ui.View):

    def __init__(self, thread):
        super().__init__()
        self.drop = SuggestionDropdown(thread, None)
        self.add_item(self.drop)

    def set_message(self, message):
        self.drop.message = message


class Suggestions(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.channel_id = bot_global.config['suggestions_channel']

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.channel.id != self.channel_id:
            return
        await message.delete()
        await self.create_suggestion(message)

    async def create_suggestion(self, message):
        embed = discord.Embed(color=discord.Color(0x9d0df0))
        embed.description = '{user}\n\n{content}'.format(user=message.author.mention, content=message.content)
        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
        thread_message = await message.channel.send(embed=embed)
        await thread_message.add_reaction(':upvote:907364653330489374')
        await thread_message.add_reaction(':downvote:907364688529072180')
        thread = await thread_message.create_thread(name=self.get_name(message.content))
        await thread.send(
            'Hey {0} this is your suggestion thread! Please `&thread rename <name>` if there is a better name for this thread, and fill it with more context if you have any.'
            .format(message.author.mention)
        )
        view = SuggestionView(thread)
        message = await thread.send('What type of suggestion is this?', view=view)
        view.set_message(message)

    @staticmethod
    def get_type_name(sug_type, thread: discord.Thread):
        name = thread.name
        match = re.search(r'\[.+\]\s+', name)
        if match:
            name = name[match.end():]
        name = '[{0}] {1}'.format(sug_type, name)
        return name

    @staticmethod
    def get_name(content):
        content = content.replace('[', '').replace(']', '')
        data = re.split(r'\s', content)
        if len(data) > 3:
            data = data[:3]
        data = ' '.join(data)
        if len(data) > 15:
            data = data[:15]
        return data


async def setup(bot):
    await bot.add_cog(Suggestions(bot))
