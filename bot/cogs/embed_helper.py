import traceback
from enum import Enum
from io import StringIO
from typing import Optional, Any, Union

import discord
from discord import Interaction, ButtonStyle, Emoji, PartialEmoji
from discord.ext import commands

from bot.core.context import Context
from bot.core.embed import Embed
from bot.mikro import Mikro
from bot.ui.modals import PromptModal
from bot.ui.select import SelectMenu
from bot.ui.view import MultiView
import aiohttp


class Editables(Enum):

    Title = "Edit the Title"
    Description = "Edit the description"
    Author = "Edit the author"
    # URL = "Edit the URL"
    Image = "Edit the image"
    Thumbnail = "Edit the thumbnail"
    AddField = "Add field"
    DeleteField = "Delete field"
    # Special case for editing fields


class Field(Enum):

    Title = 'Turn on/off the title of the embed'
    Description = 'Turn on/off the description of the embed'
    Author = 'Turn on/off the author field of the embed'
    # URL = 'Turn on/off the URL that clicking on the title goes to'
    Image = 'Turn on/off the main image of the Embed'
    Thumbnail = 'Turn on/off the image in the upper right corner'

    def get_default(self, embed) -> bool:
        match self:
            case Field.Title:
                return embed.active_title
            case Field.Description:
                return embed.active_description
            # case Field.URL:
            #     return embed.active_url
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
            # case Field.URL:
            #     return embed.set_active_url(val)
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
    # embed.url = 'https://darkkronicle.com/qr/embed'
    async with aiohttp.ClientSession() as session:
        async with session.get('https://purrbot.site/api/img/sfw/slap/gif') as r:
            embed.set_image(url=(await r.json())['link'])
        async with session.get('https://purrbot.site/api/img/sfw/icon/img') as r:
            embed.set_thumbnail(url=(await r.json())['link'])
    embed.set_footer(text='{0}'.format(user), icon_url=user.display_avatar.url)
    embed.set_author(name=user.display_name)
    return embed


class EditDropdown(discord.ui.Select):

    def __init__(self, embed_editor):
        self.embed_editor: EmbedEditor = embed_editor
        super().__init__(placeholder='Select field to edit', min_values=0, max_values=1)
        self.build_options()

    def build_options(self):
        embed = self.embed_editor.embed
        for edit in Editables:
            if edit == Editables.AddField and len(embed.fields) >= 25:
                continue
            if edit == Editables.DeleteField and len(embed.fields) == 0:
                continue
            self.append_option(
                discord.SelectOption(
                    label=edit.name,
                    description=edit.value,
                    emoji='<:green_arrow_right:906675760645951548>',
                    default=False
                )
            )
        for i, field in enumerate(self.embed_editor.embed.fields):
            self.append_option(
                discord.SelectOption(
                    label='#1'.format(i + 1),
                    description=field.name,
                    value=str(i),
                    default=False,
                )
            )

    async def callback(self, interaction: Interaction) -> Any:
        if interaction.user.id != self.embed_editor.user.id:
            await interaction.response.send_message(content="This isn't your embed!", ephemeral=True)
            return
        old_embed = self.embed_editor.embed.copy()
        if len(self.values) == 0:
            await interaction.response.send_message('Updated...')
            await interaction.delete_original_response()
            return

        try:
            edit = Editables[self.values[0]]
        except:
            edit = None

        if edit is None:
            index = int(self.values[0])
            field = self.embed_editor.embed.fields[index]
            name = discord.ui.TextInput(label='Name', style=discord.TextStyle.long, placeholder='Title here...', min_length=1, max_length=256, default=field.name)
            value = discord.ui.TextInput(label='Value', style=discord.TextStyle.long, placeholder='Value here...', min_length=1, max_length=1024, default=field.value)
            inline = discord.ui.TextInput(label='Inline (y/n)', style=discord.TextStyle.short, placeholder='y/n', min_length=1, max_length=1, default='y' if field.inline else 'n')
            modal = PromptModal(title='Edit Field'.format(field.name), inputs=[name, value, inline], timeout=120)
            await interaction.response.send_modal(modal)
            await modal.wait()
            if not modal.done:
                await modal.interaction.response.send("Timed out!")
                return
            self.embed_editor.embed.set_field_at(index, name=name.value, value=value.value, inline=field.value.lower() == 'y')
        elif edit == Editables.AddField:
            name = discord.ui.TextInput(label='Name', style=discord.TextStyle.long, placeholder='Title here...', min_length=1,max_length=256)
            value = discord.ui.TextInput(label='Value', style=discord.TextStyle.long, placeholder='Value here...', min_length=1, max_length=1024)
            inline = discord.ui.TextInput(label='Inline (y/n)', style=discord.TextStyle.short, placeholder='y/n', min_length=1, max_length=1, default='y')
            modal = PromptModal(title='Add Field'.format(edit.name), inputs=[name, value, inline], timeout=120)
            await interaction.response.send_modal(modal)
            await modal.wait()
            if not modal.done:
                await modal.interaction.response.send("Timed out!")
                return
            await modal.interaction.response.send_message('Added field!')
            await modal.interaction.delete_original_response()
            self.embed_editor.embed.add_field(name=name.value, value=value.value, inline=inline.value.lower() == 'y')
        elif edit == Editables.DeleteField:
            view = MultiView(None)
            options = [discord.SelectOption(label='Cancel', description='Cancel deletion', emoji='<:no:907013638068527114>')]
            options.extend([discord.SelectOption(label='#{0}'.format(i + 1), value=str(i), description=field.name) for i, field in enumerate(self.embed_editor.embed.fields)])
            select = SelectMenu(min_values=1, max_values=1, options=options)
            view.add_item(select)
            message = await self.embed_editor.reply(interaction=interaction, content='Which value to delete?', view=view)
            view.message = message
            value = await view.wait()
            if value:
                await view.clean_up()
                return
            if select.values[0] == 'Cancel':
                await view.clean_up()
                return
            self.embed_editor.embed.remove_field(int(select.values[0]))
            await view.clean_up()
        else:
            limit = 256
            default = ''
            set_val = lambda editor, val: None
            match edit:
                case Editables.Description:
                    limit = 4000
                    default = self.embed_editor.embed.description
                    set_val = lambda editor, val: editor.embed.set_description(val)
                case Editables.Title:
                    limit = 256
                    default = self.embed_editor.embed.title
                    set_val = lambda editor, val: editor.embed.set_title(val)
                case Editables.Author:
                    limit = 256
                    default = self.embed_editor.embed.author.name
                    set_val = lambda editor, val: editor.embed.set_author(name=val)
                case Editables.Thumbnail:
                    limit = 100
                    default = self.embed_editor.embed.thumbnail.url
                    set_val = lambda editor, val: editor.embed.set_thumbnail(url=val)
                case Editables.Image:
                    default = self.embed_editor.embed.image.url
                    set_val = lambda editor, val: editor.embed.set_image(url=val)

            prompt = discord.ui.TextInput(label='{0}'.format(self.values[0]), style=discord.TextStyle.long, placeholder='Edit value here', min_length=1, max_length=limit, default=default)
            modal = PromptModal(title='Edit {0}'.format(edit.name), inputs=[prompt], timeout=180)
            await interaction.response.send_modal(modal)
            await modal.wait()
            if not modal.done:
                await modal.interaction.response.send("Timed out!")
                return
            await modal.interaction.response.send_message("Updated...")
            await modal.interaction.delete_original_response()
            set_val(self.embed_editor, prompt.value)
        self._underlying.options.clear()
        self.build_options()
        try:
            await self.embed_editor.update()
        except:
            await interaction.channel.send('Invalid update!')
            self.embed_editor.embed = old_embed
            self._underlying.options.clear()
            self.build_options()
            await self.embed_editor.update()


class ToggleDropdown(discord.ui.Select):

    def __init__(self, embed_editor):
        self.embed_editor: EmbedEditor = embed_editor
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
        if interaction.user.id != self.embed_editor.user.id:
            await interaction.response.send_message(content="This isn't your embed!", ephemeral=True)
            return
        old_embed = self.embed_editor.embed.copy()
        self.embed_editor.embed.set_everything(False)
        for f in (Field[v] for v in self.values):
            f.modify_embed(self.embed_editor.embed, True)
        self._underlying.options.clear()
        self.build_options()
        try:
            await self.embed_editor.update()
        except:
            await interaction.response.send_message('Invalid update!', ephemeral=True)
            self.embed_editor.embed = old_embed
            self._underlying.options.clear()
            self.build_options()
            await self.embed_editor.update()
            return
        await interaction.response.send_message('Updated...')
        await interaction.delete_original_response()


class DoneButton(discord.ui.Button):

    def __init__(self, embed_editor, *, row: Optional[int] = None):
        super().__init__(style=ButtonStyle.green, label='Done', row=row)
        self.embed_editor = embed_editor

    async def callback(self, interaction: Interaction) -> Any:
        if interaction.user.id != self.embed_editor.user.id:
            await interaction.response.send_message(content="This isn't your embed!", ephemeral=True)
            return
        await self.embed_editor.complete(interaction)


class EmbedEditor(MultiView):

    def __init__(self, bot: Mikro, user: discord.User, message: discord.Message, embed: Embed):
        super().__init__(message)
        self.bot: Mikro = bot
        self.user: discord.User = user
        self.message: discord.Message = message
        self.embed = embed
        self.add_item(ToggleDropdown(self))
        self.add_item(EditDropdown(self))
        self.add_item(DoneButton(self))

    async def update(self):
        await self.message.edit(embed=self.embed, view=self)

    async def complete(self, interaction: Interaction):
        await self.clean_up()
        buffer = StringIO()
        buffer.write(self.embed.to_base64())
        buffer.seek(0)
        file = discord.File(fp=buffer, filename="embed.txt")
        await interaction.response.send_message(
            file=file, content='Here is the encoded embed. Use `/embed send` to send the embed.', embed=self.embed
        )


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

    @embed.command(name='send', description='Send base 64 encoded embed')
    async def send(self, ctx: Context, *, data: str):
        try:
            embed = Embed.from_base64(data)
        except:
            traceback.print_exc()
            await ctx.send('Something went wrong!')
            return
        embed.set_active_url(False)
        embed.set_footer(text='{0}'.format(ctx.author), icon_url=ctx.author.display_avatar.url)
        embed.timestamp = None
        try:
            await ctx.send(embed=embed)
        except:
            await ctx.send('Something went wrong!')

    @embed.command(name='sendfile', description='Send embed from file')
    async def send_from_file(self, ctx: Context, *, file: discord.Attachment):
        if not 'text' in file.content_type:
            await ctx.send("File has to be a text file!")
            return
        if not file.url.startswith('https://cdn.discordapp.com/attachments') and not file.url.startswith('https://cdn.discordapp.com/ephemeral-attachments/'):
            # Only want to download from trusted discord source
            await ctx.send('URL has to be from discord!')
            return
        data = await self.download_text(file.url)
        if data is None:
            await ctx.send("That file was invalid!")
            return
        try:
            embed = Embed.from_base64(data)
            embed.set_active_url(False)
            embed.set_footer(text='{0}'.format(ctx.author), icon_url=ctx.author.display_avatar.url)
            embed.timestamp = None
            await ctx.send(embed=embed)
        except:
            await ctx.send("That embed was invalid!")

    @staticmethod
    async def download_text(url) -> Optional[str]:
        async with aiohttp.ClientSession() as session:
            i = 0
            async with session.get(url) as r:
                if r.status == 200:
                    result = bytes()
                    while True:
                        chunk = await r.content.read(1024)
                        if not chunk:
                            break
                        result += chunk
                        i += 1
                        if i > 64:
                            # Too big!
                            return None
                    return result.decode('utf-8')
        return None


async def setup(bot):
    await bot.add_cog(EmbedHelper(bot))
