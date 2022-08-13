import bot as bot_global
import logging
import traceback

import discord
from discord.ext import commands
from datetime import datetime

from bot import response

startup_extensions = (
    'bot.cogs.suggestions',
    'bot.cogs.thread',
    'bot.cogs.utility',
    'bot.cogs.reaction',
    'bot.cogs.reply',
    'bot.cogs.voice',
    'bot.cogs.conversation',
    'bot.cogs.minecraft',
    'bot.response.response_cog',
)


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

    async def run_once_when_ready(self):
        await self.wait_until_ready()
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
