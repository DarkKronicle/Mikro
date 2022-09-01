import discord
from discord.ext import commands


# MPL v2 https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/utils/context.py

from bot.ui.modals import PromptModal


class _ContextDBAcquire:
    __slots__ = ('ctx', 'timeout')

    def __init__(self, ctx, timeout):
        self.ctx = ctx
        self.timeout = timeout

    def __await__(self):
        return self.ctx._acquire(self.timeout).__await__()

    async def __aenter__(self):
        await self.ctx._acquire(self.timeout)
        return self.ctx.db

    async def __aexit__(self, *args):
        await self.ctx.release()


class Context(commands.Context):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.connection = None
        self._db = None
        self.pool = self.bot.pool

    @property
    def db(self):
        return self._db if self._db else self.pool

    def acquire(self, *, timeout=300.0):
        """Acquires a database connection from the pool. e.g. ::
            async with ctx.acquire():
                await ctx.db.execute(...)
        or: ::
            await ctx.acquire()
            try:
                await ctx.db.execute(...)
            finally:
                await ctx.release()
        """
        return _ContextDBAcquire(self, timeout)

    async def release(self):
        """Releases the database connection from the pool.
        Useful if needed for "long" interactive commands where
        we want to release the connection and re-acquire later.
        Otherwise, this is called automatically by the bot.
        """
        # from source digging asyncpg source, releasing an already
        # released connection does nothing

        if self._db is not None:
            await self.bot.pool.release(self._db)
            self._db = None

    async def _acquire(self, timeout):
        if self._db is None:
            self._db = await self.pool.acquire(timeout=timeout)
        return self._db

    async def prompt(
            self,
            *,
            title="Text",
            placeholder="Enter here...",
            default_text="",
            label="Label",
            text_style: discord.TextStyle = discord.TextStyle.long,
            timeout: int = 30,
            min_length: int = 1,
            max_length=4000,
    ):
        if self.interaction is None:
            raise commands.CommandError("There is no interaction in this context!")

        def user_check(prompt_modal: PromptModal, prompt_interaction: discord.Interaction):
            return prompt_interaction.user.id == self.author.id

        response: discord.InteractionResponse = self.interaction.response
        text_input = discord.ui.TextInput(
            label=label, style=text_style, required=True, placeholder=placeholder, default=default_text, min_length=min_length, max_length=max_length
        )
        modal = PromptModal(
            title=title,
            timeout=timeout,
            check=user_check,
            inputs=[text_input]
        )
        await response.send_modal(modal)
        await modal.wait()
        if not modal.done:
            modal.stop()
            return None, None
        return text_input.value, modal.interaction


