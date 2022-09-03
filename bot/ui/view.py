from __future__ import annotations

from typing import Optional

import discord


class MultiView(discord.ui.View):

    def __init__(self, message: discord.Message, *, timeout: Optional[float] = 180.0):
        super().__init__(timeout=timeout)
        self.message: discord.Message = message
        self._views: list[MultiView] = []
        self._parent_interaction: discord.Interaction = None

    async def on_timeout(self) -> None:
        await self.clean_up()

    async def clean_up(self):
        self.stop()
        for v in self._views:
            if v.is_finished():
                continue
            await v.clean_up()
        try:
            if self._parent_interaction is not None:
                await self._parent_interaction.delete_original_response()
            else:
                await self.message.delete()
        except:
            # If the message is already deleted don't worry
            pass

    async def reply(self, *, interaction: discord.Interaction = None, view: MultiView = None, **message_kwargs):
        if view is not None:
            self._views.append(view)
        if interaction:
            view._parent_interaction = interaction
            return await interaction.response.send_message(view=view, **message_kwargs)
        return await self.message.channel.send(view=view, **message_kwargs, reference=self.message)
