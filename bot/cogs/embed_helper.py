from typing import Optional, List, Any

import discord
from discord import Interaction
from discord.ext import commands

from bot.core.context import Context
from bot.core.embed import Embed
from bot.mikro import Mikro
from bot.ui.view import MultiView


FIELDS = {
    'Title': 'Title of the embed',
    'Description': 'Description of the embed',
    'Author': 'Author field of the embed',
    'Color': 'Color of the embed',
    'URL': 'URL that clicking on the title goes to'
}


def get_default_embed():
    return Embed(title="Embed creator!", description="Format me!")


class ToggleDropdown(discord.ui.Select):

    def __init__(self):
        options = []
        for name, data in FIELDS.items():
            options.append(discord.SelectOption(label=name, description=data, emoji='<:green_arrow_right:906675760645951548>'))
        super().__init__(min_values=1, max_values=20, options=options)

    async def callback(self, interaction: Interaction) -> Any:
        pass


class EmbedEditor(MultiView):

    def __init__(self, bot: Mikro, user: discord.User, message: discord.Message, embed: Embed):
        super().__init__(message)
        self.bot: Mikro = bot
        self.user: discord.User = user
        self.message: discord.Message = message
        self.embed = embed
        self.add_item(ToggleDropdown())


class EmbedHelper(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx: Context) -> bool:
        return ctx.interaction is not None

    @commands.hybrid_group(name='embed', description='Embed utility')
    async def embed(self, ctx: Context):
        pass

    @embed.command(name='create', description='Opens an interactive menu to create an embed')
    async def create(self, ctx: Context):
        embed = get_default_embed()
        view = EmbedEditor(self.bot, ctx.author, None, embed)
        message = await ctx.send(embed=embed, view=view)
        view.message = message


async def setup(bot):
    await bot.add_cog(EmbedHelper(bot))
