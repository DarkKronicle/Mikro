import asyncio
import logging
from typing import Optional

import discord
from discord.ext import commands

from bot.core.context import Context
from bot.mikro import Mikro
from bot.util import cache
import re
from bot.util import database as db
from tqdm import tqdm


class Threads(db.Table, table_name='threads'):

    guild_id = db.Column(db.Integer(big=True), index=True)
    thread_id = db.Column(db.Integer(big=True), unique=True, index=True)
    owner_id = db.Column(db.Integer(big=True), nullable=False)
    channel_id = db.Column(db.Integer(big=True))
    last_message_id = db.Column(db.Integer(big=True))
    title = db.Column(db.String(), nullable=False)
    starting_message = db.Column(db.String())
    tags = db.Column(db.Array(db.String()), nullable=True)
    description = db.Column(db.String(), nullable=True)
    disable_archive = db.Column(db.Boolean(), default='FALSE')
    public = db.Column(db.Boolean(), default='TRUE')


class ThreadMessages(db.Table, table_name='thread_messages'):

    thread = db.Column(db.ForeignKey('threads', 'thread_id', sql_type=db.Integer(big=True)), index=True)
    message_id = db.Column(db.Integer(big=True), unique=True)
    message_content = db.Column(db.String())
    message_content_tsv = db.Column(db.TSVector())

    @classmethod
    def create_table(cls, *, overwrite=False):
        statement = super().create_table(overwrite=overwrite)

        # create constraints
        sql = 'CREATE INDEX IF NOT EXISTS tsv_idx ON thread_messages USING gin(message_content_tsv);'

        return statement + '\n' + sql


class ThreadData:

    def __init__(self, guild: discord.Guild, thread_id, channel_id, owner_id, title, starting_message, tags, description, disable_archive, public, last_message_id):
        self.guild: discord.Guild = guild
        self.thread_id: int = thread_id
        self.channel_id: int = channel_id
        self.owner_id: int = owner_id
        self.title: str = title
        self.starting_message: str = starting_message
        self.tags: list[str] = tags or []
        self.description: str = description or ''
        self.disable_archive: bool = disable_archive
        self.public: bool = public
        self.last_message_id = last_message_id

    @classmethod
    def from_query(cls, bot: Mikro, row):
        return ThreadData(bot.get_guild(row['guild_id']), row['thread_id'], row['channel_id'], row['owner_id'], row['title'], row['starting_message'], row['tags'], row['description'], row['disable_archive'], row['public'], row['last_message_id'])

    @property
    def args(self):
        return self.guild.id, self.thread_id, self.channel_id, self.owner_id, self.title, self.starting_message, self.tags, self.description, self.disable_archive, self.public, self.last_message_id

    @property
    def owner(self) -> Optional[discord.Member]:
        return self.guild.get_member(self.owner_id)

    @property
    def thread(self) -> Optional[discord.Thread]:
        return self.guild.get_thread(self.thread_id)

    def __eq__(self, other):
        if not isinstance(other, ThreadData):
            return False
        return other.thread_id == self.thread_id

    def __hash__(self):
        return hash(self.thread_id)

    async def update_title(self, title, pool):
        self.title = title
        async with db.MaybeAcquire(pool=pool) as con:
            await con.execute('UPDATE threads SET title=$1 WHERE thread_id = $2;', self.title, self.thread_id)

    async def update_tags(self, tags: list[str], pool):
        self.tags = tags
        async with db.MaybeAcquire(pool=pool) as con:
            await con.execute('UPDATE threads SET tags=$1 WHERE thread_id = $2;', self.tags, self.thread_id)

    async def update_owner(self, owner_id, pool):
        self.owner_id = owner_id
        async with db.MaybeAcquire(pool=pool) as con:
            await con.execute('UPDATE threads SET owner_id=$1 WHERE thread_id = $2;', self.owner_id, self.thread_id)

    async def update_description(self, description, pool):
        self.description = description
        async with db.MaybeAcquire(pool=pool) as con:
            await con.execute('UPDATE threads SET description=$1 WHERE thread_id = $2;', self.owner_id, self.thread_id)

    async def update_disable_archive(self, disable_archive: bool, pool):
        self.disable_archive = disable_archive
        async with db.MaybeAcquire(pool=pool) as con:
            await con.execute('UPDATE threads SET disable_archive=$1 WHERE thread_id = $2;', self.disable_archive, self.thread_id)

    async def update_last_message_id(self, last_message_id: int, pool):
        self.last_message_id = last_message_id
        async with db.MaybeAcquire(pool=pool) as con:
            await con.execute('UPDATE threads SET last_message_id=$1 WHERE thread_id = $2;', self.last_message_id, self.thread_id)

    @classmethod
    async def from_thread(cls, thread: discord.Thread):
        try:
            message = await thread.parent.fetch_message(thread.id)
        except discord.NotFound:
            async for m in thread.history(limit=1, oldest_first=True):
                message = m
                break
        return ThreadData(thread.guild, thread.id, thread.parent.id, thread.owner_id, thread.name, ThreadCommands.get_content(message), [], '', False, ThreadCommands.is_channel_public(thread.parent), thread.last_message_id)


class ThreadCommands(commands.Cog):

    def __init__(self, bot):
        self.bot: Mikro = bot
        # self.bot.add_loop('update_threads', self.update_threads)
        self.bot.add_on_load(self.update_threads)
        self.setup = False
        self.lock = asyncio.Lock()
        self.pin = []

    @staticmethod
    def is_channel_public(channel: discord.TextChannel):
        default = channel.guild.default_role
        perms = channel.permissions_for(default)
        return perms.view_channel and perms.read_message_history

    async def update_threads(self, *args) -> None:

        if self.bot.debug:
            return

        time = args[0] if len(args) > 0 else None
        if time is not None and (not self.setup or time.minute != 0 or time.hour % 6 != 0):
            return
        self.setup = True
        command = 'INSERT INTO threads(guild_id, thread_id, channel_id, owner_id, title, public) VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (thread_id) DO UPDATE SET title = EXCLUDED.title, channel_id = EXCLUDED.channel_id;'
        values = []
        guild = self.bot.get_main_guild()
        guild_threads = []
        for channel in guild.text_channels:
            logging.info('Gathering threads from {0}'.format(channel.name))
            guild_threads.extend(channel.threads)
            async for thread in channel.archived_threads(limit=None, private=False):
                guild_threads.append(thread)
            if channel.type != discord.ChannelType.news:
                async for thread in channel.archived_threads(limit=None, private=True):
                    guild_threads.append(thread)
        for thread in guild_threads:
            values.append((thread.guild.id, thread.id, thread.parent_id, thread.owner_id, thread.name, self.is_channel_public(thread.parent)))
        logging.info('Found {0} threads'.format(len(values)))
        if not values:
            return
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            await con.executemany(command, values)
        logging.info('Finished finding missing threads!')
        await self.update_blank_start()
        await self.update_history(guild_threads)

    async def update_history(self, all_threads):
        logging.info('Starting history')
        command = 'SELECT guild_id, thread_id, last_message_id FROM threads;'
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            rows = await con.fetch(command)
        for row in tqdm(rows):
            thread: discord.Thread = next((t for t in all_threads if t.id == row['thread_id']), None)
            if not thread:
                continue
            last_message_id = thread.last_message_id
            if thread.last_message_id is None:
                await self._update_thread_history(thread)
                continue
            if last_message_id != row['last_message_id']:
                await self._update_thread_history(thread, row['last_message_id'])

    async def _update_thread_history(self, thread: discord.Thread, last_message_id: Optional[int] = None):
        command = 'INSERT INTO thread_messages(thread, message_id, message_content, message_content_tsv) VALUES ($1, $2, $3, to_tsvector($3)) ON CONFLICT DO NOTHING;'
        values = []
        async for message in thread.history(limit=None, after=discord.Object(last_message_id) if last_message_id else None, oldest_first=True):
            values.append((thread.id, message.id, self.get_content(message)))
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            await con.executemany(command, values)
            await con.execute('UPDATE threads SET last_message_id = $1 WHERE thread_id = $2;', thread.last_message_id, thread.id)

    @staticmethod
    def get_content(message: discord.Message, owners: Optional[list] = None, thread_id: Optional[int] = None):
        if not message.content:
            if len(message.embeds) > 0:
                embed = message.embeds[0]
                if embed.description:
                    message = embed.description
                    if owners is not None:
                        match = re.match(r'<@(\d+)>', embed.description)
                        if match:
                            owners.append((thread_id, int(match.group(1))))
                elif embed.title:
                    message = embed.title
                else:
                    message = '[None]'
            elif len(message.attachments) > 0:
                message = message.attachments[0].filename
                message = message or '[None]'
            else:
                message = '[None]'
        else:
            message = message.content
        return message

    async def update_blank_start(self):
        logging.info('Starting updating blank starting messages...')
        command = 'SELECT guild_id, thread_id FROM threads WHERE starting_message IS NULL;'
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            rows = await con.fetch(command)
        if len(rows) == 0:
            logging.info('None found!')
            return
        messages = 'UPDATE threads SET starting_message = $2 WHERE thread_id = $1;'
        owner_command = 'UPDATE threads SET owner_id = $2 WHERE thread_id = $1;'
        descriptions = []
        owners = []
        for thread in tqdm(rows):
            thread = dict(thread)
            guild = self.bot.get_guild(thread['guild_id'])
            channel: discord.Thread = await guild.fetch_channel(thread['thread_id'])
            try:
                message = await channel.parent.fetch_message(channel.id)
            except discord.NotFound:
                async for m in channel.history(limit=1, oldest_first=True):
                    message = m
                    break
            descriptions.append((thread['thread_id'], self.get_content(message, owners, thread['thread_id'])))
        if descriptions:
            async with db.MaybeAcquire(pool=self.bot.pool) as con:
                await con.executemany(messages, descriptions)
        if owners:
            async with db.MaybeAcquire(pool=self.bot.pool) as con:
                logging.info('Modified {0} owners'.format(len(owners)))
                await con.executemany(owner_command, owners)
        logging.info('Done!')

    @cache.cache(maxsize=1024)
    async def get_thread(self, thread_id) -> ThreadData:
        command = 'SELECT * FROM threads WHERE thread_id = $1;'
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            row = await con.fetchrow(command, thread_id)
        if row is None:
            thread = await self.bot.fetch_channel(thread_id)
            await self.sync_thread(await ThreadData.from_thread(thread), update_if_exists=False)
            return await self.get_thread(thread_id)
        return ThreadData.from_query(self.bot, row)

    async def sync_thread(self, thread: ThreadData, update_if_exists=True):
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            command = 'INSERT INTO threads(guild_id, thread_id, channel_id, owner_id, title, starting_message, tags, description, disable_archive, public, last_message_id) VALUES ' \
                      '($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11) ON CONFLICT '

            if update_if_exists:
                command += '(thread_id) DO UPDATE SET ' \
                      'title = excluded.title, ' \
                      'starting_message = excluded.starting_message, ' \
                      'tags = excluded.tags, ' \
                      'description = excluded.description, ' \
                      'disable_archive = excluded.disable_archive, ' \
                      'public = excluded.public, ' \
                      'last_message_id = excluded.last_message_id;'
            else:
                command += 'DO NOTHING;'
            await con.execute(command, *thread.args)
        self.get_thread.set(thread, thread.thread_id)

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        self.pin.append(thread.id)
        message = await thread.send("""{0} feel free to use `/thread` to customize this thread!""".format(thread.owner.mention).replace('\t', '').replace('  ', ''))
        await message.pin()
        async with self.lock:
            if self.get_thread.exists(thread.id):
                return
            await self.sync_thread(await ThreadData.from_thread(thread), update_if_exists=False)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not isinstance(message.channel, discord.Thread):
            return
        await asyncio.sleep(0.3)
        command = 'INSERT INTO thread_messages(thread, message_id, message_content, message_content_tsv) VALUES ($1, $2, $3, to_tsvector($3)) ON CONFLICT DO NOTHING;'
        async with self.lock:
            thread: ThreadData = await self.get_thread(message.channel.id)
            if thread is None:
                logging.error("Thread with name {0} does not exist!!!".format(message.channel.name))
                return
            async with db.MaybeAcquire(pool=self.bot.pool) as con:
                await con.execute(command, message.channel.id, message.id, self.get_content(message))
                await thread.update_last_message_id(message.id, pool=self.bot.pool)

    @commands.Cog.listener()
    async def on_raw_thread_update(self, payload: discord.RawThreadUpdateEvent):
        thread_data: ThreadData = await self.get_thread(payload.thread_id)
        thread: discord.Thread = self.bot.get_channel(thread_data.thread_id)
        if thread is None:
            thread = await self.bot.fetch_channel(thread_data.thread_id)
        if thread_data.disable_archive:
            if thread.archived:
                await thread.edit(archived=False, reason="Disabled archive")
        if thread.name != thread_data.title:
            await thread_data.update_title(thread.name, pool=self.bot.pool)

    @commands.Cog.listener()
    async def on_raw_thread_delete(self, payload: discord.RawThreadDeleteEvent):
        command = 'DELETE FROM threads WHERE thread_id = $1;'
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            await con.execute(command, payload.thread_id)

    async def check(self, ctx: Context) -> bool:
        channel: discord.Thread = ctx.channel
        if not isinstance(channel, discord.Thread):
            await ctx.send('You are not in a thread!')
            return False
        if await self.bot.is_owner(ctx.author):
            return True
        thread: ThreadData = await self.get_thread(ctx.channel.id)
        if thread.owner_id == ctx.author.id:
            return True
        await ctx.send('You are not the owner of the thread!')
        return False

    @commands.hybrid_group(name='thread')
    async def thread_group(self, ctx: Context):
        pass

    @thread_group.command(name='rename', description='Renames the current thread')
    async def rename(self, ctx: Context, *, name: str):
        if not await self.check(ctx):
            return
        channel: discord.Thread = ctx.channel
        if '[' in name or ']' in name:
            await ctx.send('Sorry, `[` and `]` are not allowed in channel names.')
        if len(name) > 50:
            name = name[:50]
        prefix = re.search(r'\[.+\](\s)?', channel.name)
        if prefix:
            name = prefix.group() + name
        await channel.edit(name=name)
        await ctx.send('Updated!', ephemeral=True)

    @thread_group.command(name='pin', description='Pins a message in the current thread')
    async def pin(self, ctx: Context, *, pin: discord.Message):
        if not self.check(ctx):
            return
        channel: discord.Thread = ctx.channel
        if isinstance(pin, discord.PartialMessage):
            pin = await pin.fetch()
        if pin.channel.id == channel.id:
            await pin.pin()
        else:
            await channel.send('That message is not in the current thread!')
        await ctx.send('Pinned!', ephemeral=True)

    @thread_group.command(name='persistent', description='Makes it so a thread never archives (if you have perms)')
    async def set_persistent(self, ctx: Context, *, value: bool):
        if not await self.bot.is_owner(ctx.author):
            await ctx.send("You don't have perms!")
            return
        thread: ThreadData = await self.get_thread(ctx.channel.id)
        thread.disable_archive = value
        await self.sync_thread(thread)
        await ctx.send('Done!')


async def setup(bot):
    await bot.add_cog(ThreadCommands(bot))
