from enum import Enum
from typing import Optional, Any

import discord
from discord import Interaction
from discord.ext import commands

from bot.core.context import Context
from bot.core.embed import Embed
from bot.mikro import Mikro
from bot.ui.view import MultiView
import aiohttp


class Field(Enum):
    Title = 'Turn on/off the title of the embed'
    Description = 'Turn on/off the description of the embed'
    Author = 'Turn on/off the author field of the embed'
    URL = 'Turn on/off the URL that clicking on the title goes to'
    Image = 'Turn on/off the main image of the Embed'
    Thumbnail = 'Turn on/off the image in the upper right corner'

    def get_default(self, embed) -> bool:
        match self:
            case Field.Title:
                return embed.active_title
            case Field.Description:
                return embed.active_description
            case Field.URL:
                return embed.active_url
            case Field.Image:
                return embed.active_image
            case Field.Thumbnail:
                return embed.active_thumbnail
            case Field.Author:
                return embed.active_author

    def modify_embed(self, embed: Embed, val: bool):
        match self:
            case Field.Title:
                return embed.set_active_title(val)
            case Field.Description:
                return embed.set_active_description(val)
            case Field.URL:
                return embed.set_active_url(val)
            case Field.Image:
                return embed.set_active_image(val)
            case Field.Thumbnail:
                return embed.set_active_thumbnail(val)
            case Field.Author:
                return embed.set_active_author(val)


async def get_default_embed(user: discord.User):
    embed = Embed(
        title="Embed Creator",
        description="Use the first dropdown below to toggle specific elements, "
                    "and then use the second to modify the values.",
        color=discord.Color.blurple()
    )
    embed.url = 'https://github.com/DarkKronicle/'
    async with aiohttp.ClientSession() as session:
        async with session.get('https://purrbot.site/api/img/sfw/slap/gif') as r:
            embed.set_image(url=(await r.json())['link'])
        async with session.get('https://purrbot.site/api/img/sfw/icon/img') as r:
            embed.set_thumbnail(url=(await r.json())['link'])
    embed.set_footer(text='{0}'.format(user), icon_url=user.display_avatar.url)
    embed.set_author(name='Mikro Embed Creator 10000')
    return embed


class ToggleDropdown(discord.ui.Select):

    def __init__(self, embed_editor):
        self.embed_editor = embed_editor
        super().__init__(min_values=1, placeholder='Toggle certain elements')
        self.build_options()

    def build_options(self):
        embed = self.embed_editor.embed
        for name in Field:
            self.append_option(
                discord.SelectOption(
                    label=name.name,
                    description=name.value,
                    emoji='<:green_arrow_right:906675760645951548>',
                    default=name.get_default(embed)
                )
            )
        self.max_values = len(self.options)

    async def callback(self, interaction: Interaction) -> Any:
        self.embed_editor.embed.set_everything(False)
        for f in (Field[v] for v in self.values):
            f.modify_embed(self.embed_editor.embed, True)
        self._underlying.options.clear()
        self.build_options()
        await self.embed_editor.update()
        await interaction.response.send_message('Updated...')
        await interaction.delete_original_response()


class EmbedEditor(MultiView):

    def __init__(self, bot: Mikro, user: discord.User, message: discord.Message, embed: Embed):
        super().__init__(message)
        self.bot: Mikro = bot
        self.user: discord.User = user
        self.message: discord.Message = message
        self.embed = embed
        self.add_item(ToggleDropdown(self))

    async def update(self):
        await self.message.edit(embed=self.embed, view=self)


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
        embed = await get_default_embed(ctx.author)
        view = EmbedEditor(self.bot, ctx.author, None, embed)
        message = await ctx.send(embed=embed, view=view)
        view.message = message


async def setup(bot):
    await bot.add_cog(EmbedHelper(bot))
