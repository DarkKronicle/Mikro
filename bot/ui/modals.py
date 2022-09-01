from typing import Optional, Callable, Union, Coroutine, Any

import discord
from discord import Interaction
from discord.ui import Item
from discord.utils import maybe_coroutine


class PromptModal(discord.ui.Modal):

    def __init__(
            self,
            *,
            title: str = 'Title',
            inputs: list[discord.ui.TextInput],
            timeout: Optional[float] = None,
            check: Optional[Callable[[Any, Interaction], Union[Coroutine[Any, Any, bool], bool]]] = None,
    ) -> None:
        super().__init__(title=title, timeout=timeout)
        self._check = check
        self.interaction: Interaction = None
        self.done = False
        self.inputs = inputs
        for i in self.inputs:
            self.add_item(i)

    async def on_timeout(self) -> None:
        return await super().on_timeout()

    def _init_children(self) -> list[Item]:
        return []

    async def interaction_check(self, interaction: Interaction) -> bool:
        if self._check:
            allow = await maybe_coroutine(self._check, self, interaction)
            return allow

        return True

    async def on_submit(self, interaction: Interaction) -> None:
        self.done = True
        self.interaction = interaction
        self.stop()
