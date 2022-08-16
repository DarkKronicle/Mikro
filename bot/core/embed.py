import discord
from typing import Optional, Any, Tuple, Callable, Union
from bot.util import formatter


class Embed(discord.Embed):

    def __init__(
            self,
            *,
            inline=True,
            max_description=4096,
            max_field=1024,
            truncate_append='',
            fields: Union[Tuple[Any, Any], Any] = (),
            description_formatter: Optional[Callable] = None,
            value_formatter: Optional[Callable] = None,
            **kwargs,
    ):
        desc = kwargs.pop('description', '')
        self._description = desc
        self.max_description = max_description
        self.description_formatter = description_formatter
        self.max_field = max_field
        self.inline = inline
        self.truncate_append = truncate_append
        self.field_formatter = value_formatter
        super().__init__(**kwargs)
        self.set_fields(fields)

    def set_fields(self, fields: Union[Tuple[Any, Any], Any], *, value_formatter: Optional[Callable] = None, inline: Optional[bool] = None):
        self.clear_fields()
        self.append_fields(fields, value_formatter=value_formatter, inline=inline)

    def append_fields(self, fields: Tuple[Any, Any], *, value_formatter: Optional[Callable] = None, inline: Optional[bool] = None):
        for f in fields:
            if isinstance(f, tuple):
                self.add_field(name=f[0], value=f[1], value_formatter=value_formatter, inline=inline)
            else:
                self.add_field(name=f.name, value=f.value, value_formatter=value_formatter, inline=inline)

    @property
    def description(self):
        return self._description

    @description.setter
    def description(self, description):
        self.set_description(description)

    def set_description(
            self, description: str, *, max_description: Optional[int] = None, truncate_append: Optional[str] = None, description_formatter: Optional[str] = None,
    ):
        if description is None:
            self._description = ''
            return
        if description_formatter is None:
            description_formatter = self.description_formatter

        if description_formatter is None:
            description_formatter = formatter.blank_formatter

        if max_description is None:
            max_description = self.max_description

        if truncate_append is None:
            truncate_append = self.truncate_append

        if len(description) > max_description:
            description = description[:(max_description - len(truncate_append))]
            description += truncate_append

        description = description_formatter(description)

        self._description = description

    def add_field(self, *, name: Any, value: Any, max_field: Optional[int] = None, truncate_append: Optional[str] = None, value_formatter: Optional[Callable] = None, inline: Optional[bool] = None):
        if inline is None:
            inline = self.inline
        if value_formatter is None:
            value_formatter = self.field_formatter

        if value_formatter is None:
            value_formatter = formatter.blank_formatter

        if max_field is None:
            max_field = self.max_field

        if truncate_append is None:
            truncate_append = self.truncate_append

        if len(value) > self.max_description:
            value = value[:(max_field - len(truncate_append))]
            value += truncate_append

        value = value_formatter(value)

        return super().add_field(name=name, value=value, inline=inline)

    def set_author(
            self, *, name: Any, url: Optional[Any] = None, icon_url: Optional[Any] = None, author: Optional[discord.User] = None
    ):
        if author is None:
            return super(Embed, self).set_author(name=name, icon_url=icon_url, url=url)
        else:
            return super(Embed, self).set_author(name=author.display_name, icon_url=author.display_avatar.url, url=url)

    def sort_fields(self, key, reverse=False):
        fields = self.fields
        fields.sort(key=key, reverse=reverse)
        self.set_fields(fields)
