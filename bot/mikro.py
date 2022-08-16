import math
import typing

import bot as bot_global
import logging
import traceback

import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from pytz import timezone

from bot import response
from bot.core.context import Context

startup_extensions = (
    'bot.cogs.suggestions',
    'bot.cogs.thread',
    'bot.cogs.utility',
    'bot.cogs.reaction',
    'bot.cogs.reply',
    'bot.cogs.voice',
    'bot.cogs.conversation',
    'bot.cogs.minecraft',
    'bot.cogs.chat',
    'bot.response.response_cog',
)


def get_time_until_minute():
    return 60 - datetime.now().second


def round_time(time_object=None, round_to=30 * 60):
    """
    Round a datetime object to any time lapse in seconds
    dt : datetime.datetime object, default now.
    roundTo : Closest number of seconds to round to, default 1 minute.
    Author: Thierry Husson 2012 - Use it as you want but don't blame me.
    """
    if time_object is None:
        zone = timezone('UTC')
        utc = timezone('UTC')
        time_object = utc.localize(datetime.now())
        time_object = time_object.astimezone(zone)

    stripped_dt = time_object.replace(tzinfo=None, hour=0, minute=0, second=0)
    seconds = (time_object.replace(tzinfo=None) - stripped_dt).seconds
    rounding = (seconds + round_to / 2) // round_to * round_to
    return time_object + timedelta(0, rounding - seconds, -time_object.microsecond)


class Mikro(commands.Bot):

    def __init__(self):
        allowed_mentions = discord.AllowedMentions(roles=False, everyone=False, users=True)
        intents = discord.Intents(
            guilds=True,
            members=True,
            bans=True,
            emojis=True,
            voice_states=True,
            messages=True,
            reactions=True,
            message_content=True,
        )
        super().__init__(
            command_prefix='&',
            intents=intents,
            case_insensitive=True,
            owner_id=523605852557672449,
            allowed_mentions=allowed_mentions,
            tags=False,
        )
        self.boot = datetime.now()
        self.loops = {}

    def get_main_guild(self):
        return self.get_guild(753693459369427044)

    async def setup_hook(self) -> None:
        for extension in startup_extensions:
            try:
                await self.load_extension(extension)
            except (discord.ClientException, ModuleNotFoundError):
                logging.warning('Failed to load extension {0}.'.format(extension))
                traceback.print_exc()
        response.load_all()
        self.loop.create_task(self.run_once_when_ready())

    def run(self):
        super().run(bot_global.config['bot_token'], reconnect=True)

    def add_loop(self, name, function):
        """
        Adds a loop to the thirty minute loop. Needs to take in a function with a parameter time with async.
        """
        self.loops[name] = function

    def remove_loop(self, name):
        """
        Removes a loop based off of a time.
        """
        if name in self.loops:
            self.loops.pop(name)

    @tasks.loop(minutes=1)
    async def time_loop(self):
        time = round_time(round_to=60)
        for _, function in self.loops.items():
            try:
                await function(time)
            except Exception as error:
                if isinstance(error, (discord.Forbidden, discord.errors.Forbidden)):
                    return
                traceback.print_exc()

    first_loop = True

    @tasks.loop(seconds=get_time_until_minute())
    async def setup_loop(self):
        # Probably one of the most hacky ways to get a loop to run every thirty minutes based
        # off of starting on one of them.
        if Mikro.first_loop:
            Mikro.first_loop = False
            return
        self.time_loop.start()
        self.setup_loop.stop()

    async def run_once_when_ready(self):
        await self.wait_until_ready()
        self.setup_loop.start()
        print('Ready!')

    async def on_command_error(self, ctx, error, *, raise_err=True):  # noqa: WPS217
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.CheckFailure):
            return
        if isinstance(error, commands.CommandOnCooldown):
            if await self.is_owner(ctx.author):
                # We don't want the owner to be on cooldown.
                await ctx.reinvoke()
                return
            # Let people know when they can retry
            embed = ctx.create_embed(
                title='Command On Cooldown!',
                description='This command is currently on cooldown. Try again in `{0}` seconds.'.format(math.ceil(error.retry_after)),
                error=True,
            )
            await ctx.delete()
            await ctx.send(embed=embed, delete_after=5)
            return
        if raise_err:
            raise error

    async def get_context(self, origin: typing.Union[discord.Interaction, discord.Message], /, *, cls=Context) -> Context:
        return await super().get_context(origin, cls=cls)
