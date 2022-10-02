from functools import wraps

from urllib import parse
import re
from collections import defaultdict
import importlib
import pathlib
import traceback
import typing

import discord

import emoji as emoji_lib

_converter_types = {}

_converters = defaultdict(list)

URL_REGEX = re.compile(r'\b((?:https?://)?(?:(?:www\.)?(?:[\da-z\.-]+)\.(?:[a-z]{2,6}))(?:/[^\s]*)*/?)(?!>)\b')


async def parse_content(bot, content: str):
    kwargs_list = []
    for key, value in _converters.items():
        key: CustomResponse
        value: list[CustomResponse]
        processed = await value[0].convert(content)
        for p in processed:
            for v in value:
                try:
                    data = await v.process(bot, p)
                    if data is not None:
                        kwargs_list.append(data)
                except Exception as e:
                    print(e)
                    traceback.print_exception(e)
    return kwargs_list


class CustomResponse:

    def __init__(self, func):
        self.func = func

    async def process(self, bot, content: typing.Any) -> dict:
        return await self.func(content=content)

    @classmethod
    async def convert(cls, content: str) -> list[typing.Any]:
        raise NotImplementedError


def response_type(content_type: type):

    def decorator(cls):

        _converter_types[content_type] = cls

        class Wrapper:
            pass

        return Wrapper

    return decorator


def custom_response(content_type: type):

    def decorator(func):
        clazz = _converter_types.get(content_type)
        if not clazz:
            raise TypeError('Custom response for type {0} does not exist!'.format(clazz))

        _converters[content_type].append(clazz(func))

        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Don't need to do anything if manual call
            return await func(*args, **kwargs)

        return wrapper

    return decorator


@response_type(discord.Emoji)
class EmojiResponse(CustomResponse):

    def __init__(self, func):
        super().__init__(func)

    async def process(self, bot, content: list[str]) -> None:
        return await self.func(bot, content)

    @classmethod
    async def convert(cls, content: str):
        emojis = [e['emoji'] for e in emoji_lib.emoji_list(content)]
        return [emojis] if len(emojis) > 0 else []


@response_type(parse.ParseResult)
class UrlResponse(CustomResponse):

    def __init__(self, func):
        super().__init__(func)

    async def process(self, bot, content: parse.ParseResult) -> None:
        return await self.func(bot, content)

    @classmethod
    async def convert(cls, content: str):
        matches = URL_REGEX.finditer(content)
        converted = []
        for match in matches:
            address = match.group(0)
            if not re.search(r'^[A-Za-z0-9+.\-]+://', address):
                address = 'https://{0}'.format(address)
            converted.append(parse.urlparse(address))
        return converted


def load_all():
    for file in pathlib.Path('bot/response').glob('**/*.py'):
        if '__init__' not in file.name and 'response_cog' not in file.name:
            importlib.import_module(str(file).split('.')[0].replace('/', '.').replace('\\', '.'))
