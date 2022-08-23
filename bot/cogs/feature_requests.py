import asyncio
import logging
from enum import Enum
from typing import Any

import discord
from discord import Interaction
from discord.ext import commands
import bot as bot_global
import re

from bot.cogs.thread import ThreadData
from bot.core.context import Context
from bot.core.embed import Embed
from bot.mikro import Mikro
from bot.util import database as db

request_types = {
    'AdvancedChat': ('🗨️', 'AC Suggestion', ['ac', 'Suggestion']),
    'BetterBlockOutline': ('🟥', 'BBO Suggestion', ['bbo', 'Suggestion']),
    'KronHUD': ('⚔️', 'KronHUD mod suggestion', ['kronhud', 'Suggestion']),
    'RCI': ('🔨', 'RCI Suggestion', ['rci', 'Suggestion']),
    'Other Mod': ('⛏️', 'Minecraft mod suggestion', ['mod', 'Suggestion']),
    'Discord': ('🇩', 'Discord server specific suggestion', ['discord', 'Suggestion']),
}


class DecidedType(Enum):

    undecided = 0
    yes = 1
    maybe = 2
    no = 3


class FeatureRequestTable(db.Table, table_name='feature_requests'):

    thread_id = db.Column(db.ForeignKey('threads', 'thread_id', sql_type=db.Integer(big=True), on_delete='NO ACTION'), unique=True)
    upvotes = db.Column(db.Array(db.Integer(big=True)), default='array[]::bigint[]')
    downvotes = db.Column(db.Array(db.Integer(big=True)), default='array[]::bigint[]')
    decided = db.Column(db.Integer(small=True), default='0')
    message = db.Column(db.String(), default='')
    description = db.Column(db.String())
    description_tsv = db.Column(db.TSVector())


class RequestTagsDropdown(discord.ui.Select):

    def __init__(self, bot, owner_id, thread, message):
        self.bot = bot
        self.thread = thread
        self.message = message
        self.owner_id = owner_id
        options = []
        for key, value in request_types.items():
            options.append(discord.SelectOption(label=key, description=value[1], emoji=value[0]))
        super().__init__(options=options, placeholder='Suggestion type', max_values=1, min_values=1)

    async def callback(self, interaction: Interaction) -> Any:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("You're not the owner!")
            return
        await self.message.delete()
        await self.thread.edit(name=FeatureRequests.get_type_name(self.values[0], self.thread))
        thread = await self.bot.thread_handler.get_thread(self.thread.id)
        await thread.update_tags(request_types[self.values[0]][2], pool=self.bot.pool)
        await interaction.response.send_message('Done!')


class RequestTagsView(discord.ui.View):

    def __init__(self, bot, owner_id, thread):
        super().__init__()
        self.owner_id = owner_id
        self.drop = RequestTagsDropdown(bot, owner_id, thread, None)
        self.add_item(self.drop)

    def set_message(self, message):
        self.drop.message = message


class ButtonType(Enum):

    upvote = 1
    downvote = -1
    retract = 0

    @classmethod
    def get_name(cls, button):
        if button == ButtonType.upvote:
            return '⬆️', 'Upvote'
        if button == ButtonType.downvote:
            return '⬇️', 'Downvote'
        return '🗑️', 'Retract'

    @classmethod
    def get_style(cls, button):
        if button == ButtonType.upvote:
            return discord.ButtonStyle.blurple
        if button == ButtonType.downvote:
            return discord.ButtonStyle.blurple
        return discord.ButtonStyle.red


class FeatureRequest:

    def __init__(self, bot, thread_id, message, upvotes: list[int], downvotes: list[int], decided: DecidedType, description: str):
        self.bot = bot
        self.thread_id = thread_id
        self.message: str = message
        self._upvotes = upvotes
        self._downvotes = downvotes
        self.decided = decided
        self.description = description

    @classmethod
    def from_query(cls, bot, row):
        return FeatureRequest(bot, row['thread_id'], row['message'], row['upvotes'], row['downvotes'], DecidedType(row['decided']), row['description'])

    @property
    def upvotes(self):
        return len(self._upvotes)

    @property
    def downvotes(self):
        return len(self._downvotes)

    @property
    def total(self):
        return self.upvotes - self.downvotes

    async def edit_embed(self):
        embed = await self.get_embed()
        message = await self.get_starting_message()
        if not message:
            logging.error("The starting message for thread {0} does not exist!".format(self.thread_id))
            return
        await message.edit(embed=embed)

    async def get_embed(self) -> Embed:
        embed = Embed()
        data = await self.get_thread()

        match self.decided:
            case DecidedType.undecided:
                embed.color = discord.Colour(1)
            case DecidedType.yes:
                embed.color = discord.Colour.green()
            case DecidedType.no:
                embed.color = discord.Colour.red()
            case DecidedType.maybe:
                embed.color = discord.Colour.dark_blue()

        owner = data.owner
        embed.description = "{mention}\n\n{description}\n\n**Upvotes:** {upvotes}\n**Downvotes:** {downvotes}\n**Total:** {total}".format(
            mention=owner.mention,
            description=self.description,
            upvotes=self.upvotes,
            downvotes=self.downvotes,
            total=self.total
        )
        if self.decided != DecidedType.undecided:
            embed.description += "**Status:** {0}".format(self.decided.name.capitalize())
        if self.message:
            embed.description += "\n\n__**Response:**__\n{0}".format(self.message)
        embed.set_author(icon_url=owner.display_avatar.url, name=owner.display_name)
        return embed

    async def update_description(self, description):
        self.description = description
        command = "UPDATE feature_requests SET description = $1 and description_tsv = to_tsvector($1) WHERE thread_id = $2;"
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            await con.execute(command, self.description, self.thread_id)
        await self.edit_embed()

    async def update_message(self, message):
        self.message = message
        command = "UPDATE feature_requests SET message = $1 WHERE thread_id = $2;"
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            await con.execute(command, self.message, self.thread_id)
        await self.edit_embed()

    async def _sync_upvotes(self):
        print(self._upvotes)
        command = 'UPDATE feature_requests SET upvotes = $1 WHERE thread_id = $2;'
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            await con.execute(command, self._upvotes, self.thread_id)

    async def _sync_downvotes(self):
        print(self._downvotes)
        command = 'UPDATE feature_requests SET downvotes = $1 WHERE thread_id = $2;'
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            await con.execute(command, self._downvotes, self.thread_id)

    async def add_score(self, user_id, value):
        if user_id == (await self.get_thread()).owner_id:
            return False
        if value == 0:
            if user_id in self._upvotes:
                self._upvotes.remove(user_id)
                await self._sync_upvotes()
            if user_id in self._downvotes:
                self._upvotes.remove(user_id)
                await self._sync_downvotes()
            return True
        if value == 1:
            if user_id in self._downvotes:
                self._downvotes.remove(user_id)
                await self._sync_downvotes()
            if user_id not in self._upvotes:
                self._upvotes.append(user_id)
                await self._sync_upvotes()
            return True
        if value == -1:
            if user_id in self._upvotes:
                self._upvotes.remove(user_id)
                await self._sync_upvotes()
            if user_id not in self._downvotes:
                self._downvotes.append(user_id)
                await self._sync_downvotes()
            return True

    async def get_thread(self) -> ThreadData:
        return await self.bot.thread_handler.get_thread(self.thread_id)

    async def get_starting_message(self) -> discord.Message:
        data = await self.get_thread()
        thread = data.thread
        if not data.thread:
            thread = (await data.guild.fetch_channel(self.thread_id))
        return await thread.parent.fetch_message(self.thread_id)


class RequestVoteButton(discord.ui.Button):

    def __init__(self, feature_request: FeatureRequest, message_id: int, button_type: ButtonType):
        super().__init__(
            label=ButtonType.get_name(button_type)[1],
            emoji=ButtonType.get_name(button_type)[0],
            custom_id='fq:{0}:{1}'.format(button_type.value, message_id),
            style=ButtonType.get_style(button_type)
        )
        self.feature_request = feature_request
        self.button_type = button_type

    async def callback(self, interaction: Interaction) -> Any:
        result = await self.feature_request.add_score(interaction.user.id, self.button_type.value)
        await self.feature_request.edit_embed()
        if result:
            await interaction.response.send_message('Vote recorded!', ephemeral=True)
        else:
            await interaction.response.send_message("You can't vote for you own!", ephemeral=True)


class RequestVoteView(discord.ui.View):

    def __init__(self, feature_request: FeatureRequest, bot: Mikro, message: int):
        self.bot = bot
        self.message = message
        super().__init__(timeout=None)
        for button in ButtonType:
            self.add_item(RequestVoteButton(feature_request, message, button))


class FeatureRequests(commands.Cog):

    def __init__(self, bot):
        self.bot: Mikro = bot
        self.bot.add_on_load(self.setup_all_views)
        self.channel_id = bot_global.config['requests_channel']
        self.requests: dict[int, FeatureRequest] = {}

    async def setup_all_views(self):
        command = 'SELECT * FROM feature_requests;'
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            rows = await con.fetch(command)
        for row in rows:
            request = FeatureRequest.from_query(self.bot, row)
            self.requests[row['thread_id']] = request
            self.bot.add_view(RequestVoteView(request, self.bot, row['thread_id']))

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
        embed.description = 'Loading feature...'
        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)

        request = FeatureRequest(self.bot, None, "", [], [], DecidedType.undecided, message.content)

        thread_message = await message.channel.send(embed=embed)
        async with self.bot.thread_handler.lock:
            thread = await thread_message.create_thread(name=self.get_name(message.content))
            request.thread_id = thread.id
            data = await ThreadData.from_thread(thread)
            data.owner_id = message.author.id
            await self.bot.thread_handler.sync_thread(data)
        command = 'INSERT INTO feature_requests(thread_id, description, description_tsv) values ($1, $2, to_tsvector($2));'
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            await con.execute(command, thread.id, message.content)
        starter = await thread.send(
            'Hey {0} this is your suggestion thread! Please `/thread rename <name>` if there is a better name for this thread, and fill it with more context if you have any.\n\n'
            'If you need to change anything use the `/feature` command.'
            .format(message.author.mention)
        )
        await thread_message.edit(embed=await request.get_embed(), view=RequestVoteView(request, self.bot, thread_message.id))
        self.requests[thread.id] = request
        async with thread.typing():
            await asyncio.sleep(2)
            await starter.edit(content=starter.content + '\n\nLet me get <@523605852557672449> in on this!')
            await asyncio.sleep(1)
            view = RequestTagsView(self.bot, message.author.id, thread)
            type_message = await thread.send('What type of suggestion is this?', view=view)
            view.set_message(type_message)

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

    async def is_feature_owner(self, thread: discord.Thread, member: discord.Member):
        thread: ThreadData = await self.requests[thread.id].get_thread()
        return thread.owner_id == member.id

    @commands.hybrid_group(name='feature')
    async def feature_group(self, ctx: Context):
        pass

    @feature_group.command(name='description', description="Change the description of the feature request")
    async def description_command(self, ctx: Context, *, description: str):
        if not isinstance(ctx.channel, discord.Thread):
            await ctx.defer(ephemeral=True)
            await ctx.send('You are not in a thread!')
            return
        if not await self.is_feature_owner(ctx.channel, ctx.author):
            await ctx.defer(ephemeral=True)
            await ctx.send('You are not the owner of this thread!')
            return
        await ctx.defer(ephemeral=False)
        await self.requests[ctx.channel.id].update_description(description)
        await ctx.send('Updated description!')

    @feature_group.command(name='message', description="Change the staff message")
    async def description_command(self, ctx: Context, *, message: str):
        if not isinstance(ctx.channel, discord.Thread):
            await ctx.defer(ephemeral=True)
            await ctx.send('You are not in a thread!')
            return
        if not ctx.author.id not in self.bot.owner_ids:
            await ctx.defer(ephemeral=True)
            await ctx.send('You are not staff!')
            return
        await ctx.defer(ephemeral=False)
        await self.requests[ctx.channel.id].update_message(message)
        await ctx.send('Staff message changed!')


async def setup(bot):
    await bot.add_cog(FeatureRequests(bot))
