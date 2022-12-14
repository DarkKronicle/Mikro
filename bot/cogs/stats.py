import random
from datetime import datetime, timedelta
from typing import Optional

import discord
from discord.ext import commands

from bot.core.context import Context
from bot.core.embed import Embed
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


class MessageCooldown(db.Table, table_name='message_cooldown'):
    guild_id = db.Column(db.Integer(big=True), index=True)
    channel_id = db.Column(db.Integer(big=True), index=True)
    user_id = db.Column(db.Integer(big=True), index=True)
    time = db.Column(db.Datetime(), default="now() at time zone 'utc'")
    period = db.Column(db.Interval())
    amount = db.Column(db.Integer(), default='1')

    @classmethod
    def create_table(cls, *, overwrite=False):
        statement = super().create_table(overwrite=overwrite)

        # create constraints
        sql = 'ALTER TABLE message_cooldown DROP CONSTRAINT IF EXISTS unique_cool;' \
              'ALTER TABLE message_cooldown ADD CONSTRAINT unique_cool UNIQUE (guild_id, channel_id, user_id, period);'

        return statement + '\n' + sql


class Message:

    def __init__(self, guild_id, channel_id, author_id, message_id, time: datetime, type: MessageType):
        self.guild_id: int = guild_id
        self.channel_id: int = channel_id
        self.author_id: int = author_id
        self.message_id: int = message_id
        self.time: datetime = time
        self.type = type

    def __str__(self):
        return '({0}, {1}, {2}, {3}, {4}, {5})'.format(
            self.guild_id, self.channel_id, self.author_id, self.message_id, self.time.strftime("'%Y-%m-%d %H:%M:%S'"), self.type.value
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


class MessagePeriod:

    def __init__(self, minutes, *, messages: Optional[list[Message]] = None):
        self._messages: list[Message] = messages or []
        self.minutes = minutes

    def __iter__(self):
        self._verify_integrity()
        dup = self._messages.copy()
        for m in dup:
            # Yield could have weird waiting implications
            # Also don't want to have concurrent modification exception
            if self._message_valid(m):
                yield m

    def __len__(self):
        self._verify_integrity()
        return len(self._messages)

    def append(self, message: Message):
        self._messages.append(message)
        self._verify_integrity()

    def extend(self, messages: list[Message]):
        self._messages.extend(messages)
        self._verify_integrity()

    def remove(self, message: Message):
        self._messages.remove(message)

    def __add__(self, other):
        if isinstance(other, MessagePeriod):
            self._messages.extend(other._messages)
            return self
        if isinstance(other, list):
            self._messages.extend(other)
            return self
        if isinstance(other, Message):
            self._messages.append(other)
            return self
        raise TypeError('Cannot add {0} to MessagePeriod'.format(other))

    def __getitem__(self, item):
        self._verify_integrity()
        return self._messages[item]

    def _message_valid(self, x: Message):
        now = time_util.get_utc()
        return (x.time - now).total_seconds() / 60 > self.minutes

    def _verify_integrity(self):
        self._messages = list(filter(lambda x: self._message_valid(x), self._messages))


class CooldownInterval(Enum):
    minutes_10 = '10 MINUTES'
    hours_1 = '1 HOURS'
    hours_3 = '3 HOURS'
    hours_6 = '6 HOURS'
    hours_24 = '24 HOURS'

    @staticmethod
    def from_delta(delta: timedelta):
        minutes = delta.total_seconds() // 60
        if minutes == 10:
            return CooldownInterval.minutes_10
        hours = minutes // 60
        if hours == 1:
            return CooldownInterval.hours_1
        if hours == 3:
            return CooldownInterval.hours_3
        if hours == 6:
            return CooldownInterval.hours_6
        if hours == 24:
            return CooldownInterval.hours_24
        return None


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
            await self.update_top()

    async def cog_unload(self) -> None:
        await self.push()

    async def update_top(self):
        command = "SELECT user_id, count(*) amount FROM messages WHERE time >= NOW() at time zone 'utc' - interval '1 WEEKS' AND guild_id = 753693459369427044 " \
                  "group by user_id order by count(*) desc;"
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            rows = await con.fetch(command)
        if not rows:
            return
        message = []
        i = 0
        for r in rows:
            if i >= 10:
                break
            user_id = r['user_id']
            amount = r['amount']
            user: discord.Member = self.bot.get_main_guild().get_member(user_id)
            if not user:
                continue
            if any([ro.id == 839214547646152757 for ro in user.roles]):
                continue
            i += 1
            message.append(f"`{i}.` {user.mention} {amount} messages")
        embed = Embed()
        embed.set_description('\n'.join(message))
        await self.bot.get_main_guild().get_channel(753693459369427047).send(embed=embed)

    @commands.is_owner()
    @commands.command(name="updatetop")
    async def cmd_update_top(self, ctx: Context):
        await self.update_top()
        await ctx.send("Done!", ephemeral=True)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        start = member.joined_at
        channel = self.bot.get_main_guild().get_channel(878363458708570133)
        the_message = None
        async for message in channel.history(after=start - timedelta(seconds=1), limit=2, oldest_first=True):
            if message.author.id == member.id:
                the_message = message
                break
        if not the_message:
            return
        choice = random.choice(['<:omg:1025976523339075676>', '????'])
        await the_message.add_reaction(choice)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.channel is None or message.author.bot or message.guild.id != 753693459369427044:
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
        await self.bot.get_cog('ThreadDiscovery').on_message(message)
        self.cache.append(sm)
        await self.update_interval(sm)

    async def get_messages_in_cooldowns(self, guild_id, *, channel_id=0, user_id=0) -> dict[CooldownInterval, int]:
        command = "DELETE FROM message_cooldown WHERE now() at time zone 'utc' >= time + period;"
        fetch = "SELECT period, amount FROM message_cooldown WHERE guild_id = {0} and channel_id = {1} and user_id = {2};"\
            .format(guild_id, channel_id, user_id)
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            await con.execute(command)
            rows = await con.fetch(fetch)
        data = {}
        if rows:
            for r in rows:
                data[CooldownInterval.from_delta(r['period'])] = r['amount']
        return data

    async def get_messages_in_cooldown(self, guild_id, *, channel_id=None, user_id=None, interval: CooldownInterval) -> int:
        if channel_id is None:
            channel_id = 0
        if user_id is None:
            user_id = 0
        command = "DELETE FROM message_cooldown WHERE now() at time zone 'utc' >= time + period;"
        fetch = "SELECT amount FROM message_cooldown WHERE guild_id = {0} and channel_id = {1} and user_id = {2} " \
                "and period = INTERVAL '{3}';".format(guild_id, channel_id, user_id, interval.value)
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            await con.execute(command)
            row = await con.fetchrow(fetch)
        if row:
            return row['amount']
        return 0

    async def update_interval(self, message: Message):
        command = 'INSERT INTO message_cooldown(guild_id, channel_id, user_id, period) VALUES {0} ' \
                  'ON CONFLICT ON CONSTRAINT unique_cool DO UPDATE SET amount = message_cooldown.amount + 1;'
        val = "({0}, {1}, {2}, INTERVAL '{3}')"
        values = []
        for interval in CooldownInterval:
            values.append(val.format(message.guild_id, message.channel_id, message.author_id, interval.value))
        for interval in CooldownInterval:
            values.append(val.format(message.guild_id, message.channel_id, 0, interval.value))
        for interval in CooldownInterval:
            values.append(val.format(message.guild_id, 0, message.author_id, interval.value))
        command = command.format(', '.join(values))
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            await con.execute(command)

    async def remove_old(self):
        interval = f"INTERVAL '7 DAYS'"
        command = f"DELETE FROM messages WHERE time <= NOW() at time zone 'utc' - {interval};"
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            await con.execute(command)

    async def push(self):
        if len(self.cache) == 0:
            return
        insert = [str(m) for m in self.cache]

        command = 'INSERT INTO messages(guild_id, channel_id, user_id, message_id, time, type) VALUES {0} ON CONFLICT DO NOTHING;'
        command = command.format(', '.join(insert))
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            await con.execute(command)
        self.cache.clear()


async def setup(bot):
    await bot.add_cog(Stats(bot))
