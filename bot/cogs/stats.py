from datetime import datetime

import discord
from discord.ext import commands

from bot.mikro import Mikro
from bot.util import database as db, cache
from bot.util import time_util
from enum import Enum


class MessageType(Enum):

    simple = 0
    long = 1
    attachment = 2


class Messages(db.Table, table_name='messages'):
    guild_id = db.Column(db.Integer(big=True), index=True)
    channel_id = db.Column(db.Integer(big=True), index=True)
    user_id = db.Column(db.Integer(big=True), index=True)
    message_id = db.Column(db.Integer(big=True), unique=True)
    time = db.Column(db.Datetime(), default="now() at time zone 'utc'", index=True)
    type = db.Column(db.Integer(small=True))


class Message:

    def __init__(self, guild_id, channel_id, author_id, message_id, time: datetime, type: MessageType):
        self.guild_id: int = guild_id
        self.channel_id: int = channel_id
        self.author_id: int = author_id
        self.message_id: int = message_id
        self.time: str = time.strftime("'%Y-%m-%d %H:%M:%S'")
        self.type = type

    def __str__(self):
        return '({0}, {1}, {2}, {3}, {4}, {5})'.format(
            self.guild_id, self.channel_id, self.author_id, self.message_id, self.time, self.type.value
        )

    def __eq__(self, other):
        if not isinstance(other, Message):
            return False
        return self.message_id == other.message_id

    def __hash__(self):
        return hash(self.message_id)

    @staticmethod
    def from_db(data, *, author_id=None, guild_id=None, channel_id=None):
        author_id = author_id or data['author_id']
        guild_id = guild_id or data['guild_id']
        channel_id = channel_id or data['channel_id']
        return Message(guild_id, channel_id, author_id, data['message_id'], data['time'], MessageType(data['type']))


class Stats(commands.Cog):

    def __init__(self, bot):
        self.bot: Mikro = bot
        self.bot.add_loop('messagepush', self.update_loop)
        self.cache: list[Message] = []
        self.cooldown = cache.ExpiringDict(seconds=20)

    async def update_loop(self, time):
        if time.minute % 5 == 0:
            await self.push()
        if time.minute == 0 and time.hour == 0:
            await self.remove_old()

    async def cog_unload(self) -> None:
        await self.push()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.channel is None or message.author.bot:
            return
        if (message.guild.id, message.author.id) in self.cooldown:
            return
        self.cooldown[(message.guild.id, message.author.id)] = 1
        if message.attachments:
            type = MessageType.attachment
        elif len(message.content) > 150:
            type = MessageType.long
        else:
            type = MessageType.simple
        sm = Message(message.guild.id, message.channel.id, message.author.id, message.id, time_util.get_utc(), type)
        await self.bot.get_cog('Tree').on_message(sm)
        (await self.user_day_messages(sm.guild_id, sm.author_id)).append(sm)
        self.cache.append(sm)

    @cache.cache(maxsize=512)
    async def user_day_messages(self, guild_id, user_id):
        interval = "INTERVAL '1 DAYS'"
        command = "SELECT channel_id, message_id, time, type FROM messages WHERE guild_id = {0} AND user_id = {1} AND time >= NOW() at time zone 'utc' - {2};".format(guild_id, user_id, interval)
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            messages = await con.fetch(command)
        return [Message.from_db(m, author_id=user_id, guild_id=guild_id) for m in messages]

    async def remove_old(self):
        interval = f"INTERVAL '7 DAYS'"
        command = f"DELETE FROM messages WHERE time <= NOW() at time zone 'utc' - {interval};"
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            await con.execute(command)

    async def push(self):
        if len(self.cache) == 0:
            return
        insert = [str(m) for m in self.cache]

        command = 'INSERT INTO messages(guild_id, channel_id, user_id, message_id, time, type) VALUES {0};'
        command = command.format(', '.join(insert))
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            await con.execute(command)
        self.cache.clear()


async def setup(bot):
    await bot.add_cog(Stats(bot))
