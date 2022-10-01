import json
import math
from pathlib import Path

import aiohttp
import discord
import emoji

from discord.ext import commands

from bot.core.context import Context

from io import BytesIO
from PIL import Image

import itertools


EMOJI_DATA = json.loads(Path("config/emojis.json").read_text())


def get_emoji(text):
    return emoji.distinct_emoji_list(text)


def get_hex_from_char(f):
    return ['{0:x}'.format(ord(str(c))) for c in f]


def get_emoji_url(emoji1: list[str], emoji2: list[str]):
    femoji_1 = '-'.join(emoji1)
    femoji_2 = '-'.join(emoji2)
    data = EMOJI_DATA.get(femoji_1, None)
    if not data:
        return None
    date = None
    one_first = True
    for obj in data:
        if obj['leftEmoji'] == femoji_2:
            one_first = False
            date = obj['date']
            break
        if obj['rightEmoji'] == femoji_2:
            date = obj['date']
            break
    if date is None:
        return None

    formatted_emoji1 = '-'.join(['u' + e for e in emoji1])
    formatted_emoji2 = '-'.join(['u' + e for e in emoji2])
    url = 'https://www.gstatic.com/android/keyboard/emojikitchen/{0}/{1}/{1}_{2}.png'
    if one_first:
        return url.format(date, formatted_emoji1, formatted_emoji2)
    return url.format(date, formatted_emoji2, formatted_emoji1)


def get_n_urls(emojis, *, n=9):
    urls = []
    for pair in itertools.combinations(emojis, 2):
        if len(urls) >= n:
            break
        url = get_emoji_url(pair[0], pair[1])
        if url is not None:
            urls.append(url)
    return urls


async def create_grid(urls, *, rows=5, cols=5):
    imgs = []
    for url in urls:
        data = await fetch_emoji(url)
        with Image.open(BytesIO(data)).convert("RGBA") as image:
            image = image.resize((50, 50), Image.ADAPTIVE)
            imgs.append(image)
    w, h = 55, 55
    img_w, img_h = 50, 50

    grid = Image.new("RGBA", size=(w * cols - (img_w - w), h * rows - (img_h - h)))
    for i, img in enumerate(imgs):
        grid.paste(img, box=(i % cols * w, i // cols * h))

    output_buffer = BytesIO()
    grid.save(output_buffer, "png")
    output_buffer.seek(0)
    grid.close()
    return discord.File(output_buffer, filename="emojis.png")


async def get_and_format(url, *, filename):
    data = await fetch_emoji(url)
    with Image.open(BytesIO(data)).convert("RGBA") as image:
        output_buffer = BytesIO()
        image = image.resize((100, 100), Image.ADAPTIVE)
        image.save(output_buffer, "png")
        output_buffer.seek(0)
    return discord.File(output_buffer, filename=filename)


async def fetch_emoji(url):
    if url is None:
        return None
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as r:
            if r.status == 404:
                return None
            result = bytes()
            while True:
                chunk = await r.content.read(1024)
                if not chunk:
                    break
                result += chunk
            return result


class Emojis(commands.Cog):

    def __init__(self, bot):
        self.bot = bot


async def setup(bot):
    await bot.add_cog(Emojis(bot))
