import math
from datetime import datetime
from typing import Union

import discord

from bot.cogs import stats
from bot.core.context import Context
from bot.core.embed import Embed
from bot.util import time_util, cache

from discord.ext import commands
from bot.util import database as db
from enum import Enum
import random


class TreeType(Enum):

    guild = 0
    channel = 1
    user = 2


class TreeStorage(db.Table, table_name='tree_storage'):
    guild_id = db.Column(db.Integer(big=True), index=True)
    object_id = db.Column(db.Integer(big=True), index=True)
    type = db.Column(db.Integer(small=True))
    height = db.Column(db.Float())
    last_height = db.Column(db.Datetime())
    last_water = db.Column(db.Datetime())
    last_care = db.Column(db.Datetime())
    water = db.Column(db.Integer())
    care = db.Column(db.Integer())

    @classmethod
    def create_table(cls, *, overwrite=False):
        statement = super().create_table(overwrite=overwrite)

        # create constraints
        sql = 'ALTER TABLE tree_storage DROP CONSTRAINT IF EXISTS unique_tree;' \
              'ALTER TABLE tree_storage ADD CONSTRAINT unique_tree UNIQUE (guild_id, object_id);'

        return statement + '\n' + sql


class TreeObject:

    def __init__(self, guild_id, object_id, type, height, last_height, last_water, last_care, water, care, *, water_equation=None, care_equation=None):
        self.guild_id: int = guild_id
        self.object_id: int = object_id
        self.type: TreeType = TreeType(type)
        self._height: float = height
        self.last_height: datetime = last_height
        self.last_water: datetime = last_water
        self.last_care: datetime = last_care
        self._water: int = water
        self._care: int = care
        self.water_equation = water_equation
        if self.water_equation is None:
            self.water_equation = TreeObject.default_water
        self.care_equation = care_equation
        if self.care_equation is None:
            self.care_equation = TreeObject.default_care

    @property
    def height(self):
        if (time_util.get_utc() - self.last_height).total_seconds() < 5:
            return self._height
        val = self.water + self.care - 1000
        if val < 0:
            val = math.ceil(val / 2)
        # Get it between -1 and 1
        val = val / 1000 * 2
        if val < 0:
            val = (.5 / (1 + math.exp(-5 * val)) - .25) / 5
        h = self._height + val * (((time_util.get_utc() - self.last_height).total_seconds() / 60) / 12)
        return max(0.0, h)

    def update_height(self, val):
        self._height = val
        self.last_height = time_util.get_utc()

    @staticmethod
    def default_water(x: int, updated: datetime, slow_factor):
        if x < 10:
            return x
        return x - (math.pow(1.01, (time_util.get_utc() - updated).total_seconds() / 60) * 10) / slow_factor

    @staticmethod
    def default_care(x: int, updated: datetime, slow_factor):
        if x < 10:
            return x
        # We want 1.01 ^ (minutes since)
        main = math.pow(1.01, (time_util.get_utc() - updated).total_seconds() / 60)
        return x - (main * 10) / slow_factor

    def get_slow_factor(self):
        if self.type == TreeType.guild:
            return 1
        if self.type == TreeType.channel:
            return 2
        if self.type == TreeType.user:
            return 4

    @property
    def water(self) -> int:
        return math.ceil(
            max(0, min(
                self.water_equation(self._water, self.last_water, self.get_slow_factor()), 1000
            ))
        )

    @property
    def care(self):
        val = self.care_equation(self._care, self.last_care, self.get_slow_factor())
        return math.ceil(
            max(0, min(
                val, 1000
            ))
        )

    def update_care(self, value):
        self.last_care = time_util.get_utc()
        self._care = value
        self.update_height(self.height)

    def update_water(self, value):
        self.last_water = time_util.get_utc()
        self._water = value
        self.update_height(self.height)

    async def add_water(self, stats_obj: stats.Stats, message: stats.Message):
        if message.type == stats.MessageType.long:
            val = random.randint(40, 60)
        elif message.type == stats.MessageType.attachment:
            val = random.randint(40, 60)
        else:
            val = random.randint(10, 20)
        match self.type:
            case TreeType.user:
                val = val * 4
            case TreeType.channel:
                val = val * 3
        self.update_water(self.water + val)

    async def add_care(self, stats_obj: stats.Stats, message: stats.Message):
        author: dict[stats.CooldownInterval, int] = await stats_obj.get_messages_in_cooldowns(message.guild_id, user_id=message.author_id)
        if author.get(stats.CooldownInterval.hours_24, 0) == 0:
            val = random.randint(40, 70)
        elif author.get(stats.CooldownInterval.hours_1, 0) <= 2:
            val = random.randint(10, 30)
        else:
            val = random.randint(0, 3)
        match self.type:
            case TreeType.user:
                val = val * 4
            case TreeType.channel:
                val = val * 3
        self.update_care(self.care + val)

    def __eq__(self, other):
        if not isinstance(other, TreeObject):
            return False
        return self.object_id == other.object_id and self.guild_id == other.guild_id

    def __hash__(self):
        return hash(self.object_id)

    def __str__(self):
        care_time: str = self.last_care.strftime("'%Y-%m-%d %H:%M:%S'")
        water_time: str = self.last_water.strftime("'%Y-%m-%d %H:%M:%S'")
        height_time: str = self.last_height.strftime("'%Y-%m-%d %H:%M:%S'")
        return '({0}, {1}, {2}, {3}, {4}, {5}, {6}, {7}, {8})'.format(self.guild_id, self.object_id, self.type.value, self.height, height_time, water_time, care_time, self.water, self.care)


class Tree(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.bot.add_loop('update_trees', self.update_trees)
        self.updated_trees: set[TreeObject] = set()

    @property
    def stats_obj(self) -> stats.Stats:
        return self.bot.get_cog('Stats')

    @staticmethod
    def gen_tree(ctx: Context, tree: TreeObject):
        embed = Embed(inline=True)
        match tree.type:
            case TreeType.guild:
                embed.title = ctx.guild.name
            case TreeType.user:
                embed.title = ctx.author.display_name
            case TreeType.channel:
                embed.title = '#' + ctx.channel.name
        embed.add_field(name='Water', value='{0}%'.format(tree.water // 100))
        embed.add_field(name='Care', value='{0}%'.format(tree.care // 100))
        embed.add_field(name='Height', value=str(tree.height))
        embed.title = ctx.guild.name
        return embed

    @commands.command(name='guildtree')
    @commands.guild_only()
    async def guild_tree_stats(self, ctx: Context):
        tree = await self.get_tree(ctx.guild.id, ctx.guild.id, TreeType.guild)
        embed = self.gen_tree(ctx, tree)
        await ctx.send(embed=embed)

    @commands.command(name='tree')
    @commands.guild_only()
    async def tree_stats(self, ctx: Context, *, tree: Union[discord.Member, discord.TextChannel]):
        if isinstance(tree, discord.Member):
            tree = await self.get_tree(ctx.guild.id, ctx.author.id, TreeType.user)
        else:
            tree = await self.get_tree(ctx.guild.id, ctx.channel.id, TreeType.channel)
        embed = self.gen_tree(ctx, tree)
        await ctx.send(embed=embed)

    @commands.is_owner()
    @commands.command(name='pushtree')
    async def push_tree(self, ctx):
        await self.update_trees(None)

    async def update_trees(self, time):
        if len(self.updated_trees) == 0:
            return
        if time is not None and time.minute % 5 != 0:
            return
        values = [str(tree) for tree in self.updated_trees]
        command = "INSERT INTO tree_storage(guild_id, object_id, type, height, last_height, last_water, last_care, water, care)" \
                  " VALUES {0} " \
                  "ON CONFLICT ON CONSTRAINT unique_tree DO UPDATE SET " \
                  "guild_id = EXCLUDED.guild_id, " \
                  "object_id = EXCLUDED.object_id, " \
                  "type = EXCLUDED.type, " \
                  "height = EXCLUDED.height, " \
                  "last_height = EXCLUDED.last_height, " \
                  "last_water = EXCLUDED.last_water, " \
                  "last_care = EXCLUDED.last_care, " \
                  "water = EXCLUDED.water, " \
                  "care = EXCLUDED.care;".format(', '.join(values))
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            await con.execute(command)
        self.updated_trees.clear()
        await self.set_status()

    async def on_message(self, message: stats.Message):
        # This is called from stats
        await self.guild_tree(message)
        await self.user_tree(message)
        await self.channel_tree(message)

    async def guild_tree(self, message: stats.Message) -> None:
        s = self.stats_obj
        tree = await self.get_tree(message.guild_id, message.guild_id, TreeType.guild)
        await tree.add_water(s, message)
        await tree.add_care(s, message)
        self.updated_trees.add(tree)

    async def user_tree(self, message: stats.Message) -> None:
        s = self.stats_obj
        tree = await self.get_tree(message.guild_id, message.author_id, TreeType.user)
        await tree.add_water(s, message)
        await tree.add_care(s, message)
        self.updated_trees.add(tree)

    async def channel_tree(self, message: stats.Message) -> None:
        s = self.stats_obj
        tree = await self.get_tree(message.guild_id, message.channel_id, TreeType.channel)
        await tree.add_water(s, message)
        await tree.add_care(s, message)
        self.updated_trees.add(tree)

    async def get_tree(self, guild_id, object_id, type, *, connection=None) -> TreeObject:
        for t in self.updated_trees:
            if t.guild_id == guild_id and t.object_id == object_id:
                return t
        return await self._get_tree(guild_id, object_id, type, connection=connection)

    @cache.cache(maxsize=2048)
    async def _get_tree(self, guild_id, object_id, type, *, connection=None) -> TreeObject:
        con = connection or self.bot.pool
        command = 'SELECT type, height, last_height, last_water, last_care, water, care FROM tree_storage WHERE guild_id = {0} AND object_id = {1};'.format(guild_id, object_id)
        row = await con.fetchrow(command)
        if not row:
            return TreeObject(guild_id, object_id, type, 0, time_util.get_utc(), time_util.get_utc(), time_util.get_utc(), 0, 0)
        return TreeObject(guild_id, object_id, TreeType(row['type']), row['height'], row['last_height'], row['last_water'], row['last_care'], row['water'], row['care'])

    async def set_status(self):
        tree = await self.get_tree(753693459369427044, 753693459369427044, TreeType.guild)
        activity = discord.Activity(
            type=discord.ActivityType.playing,
            name='with chat tree | {0}% Water | {1}% Care'.format(tree.water // 100, tree.care // 100),
        )
        await self.bot.change_presence(status=discord.Status.online, activity=activity)


async def setup(bot):
    await bot.add_cog(Tree(bot))
