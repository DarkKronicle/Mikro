from typing import Any, Optional, List

import discord
from discord import Interaction, SelectOption
from discord.utils import MISSING


class SelectMenu(discord.ui.Select):

    def __init__(self, *, custom_id: str = MISSING, placeholder: Optional[str] = None, min_values: int = 1,
                 max_values: int = 1, options: List[SelectOption] = MISSING, disabled: bool = False,
                 row: Optional[int] = None) -> None:
        super().__init__(custom_id=custom_id, placeholder=placeholder, min_values=min_values, max_values=max_values,
                         options=options, disabled=disabled, row=row)
        self.interaction: discord.Interaction = None

    async def callback(self, interaction: Interaction) -> Any:
        self.interaction = interaction
        self.view.stop()
