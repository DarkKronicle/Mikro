import math

from . import *

from bot.cogs import emoji


@custom_response(discord.Emoji)
async def emoji_kitchen(bot, content: list[str]):
    if len(content) < 2:
        return None

    found = [emoji.get_hex_from_char(f) for f in set(content)]
    urls = emoji.get_n_urls(found, n=25)
    if len(urls) == 0:
        return None
    if len(urls) == 1:
        return {'file': await emoji.get_and_format(urls[0], filename='emoji.png')}
    return {'file': await emoji.create_grid(urls, rows=math.ceil(len(urls) / 5), cols=5)}
