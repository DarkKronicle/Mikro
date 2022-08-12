import aiohttp
import gzip

import discord
from bs4 import BeautifulSoup

HEADERS = {'content-type': 'application/gzip'}


async def upload_crash(file_url):
    zipped = await gzip_crash(file_url)
    if zipped is None:
        return None
    upload_url = "https://europe-west1-crashy-9dd87.cloudfunctions.net/uploadCrash"
    async with aiohttp.ClientSession() as session:
        async with session.post(upload_url, data=zipped, headers=HEADERS) as r:
            if r.status == 200:
                return (await r.json())['crashUrl']
            else:
                if r.content_type == 'text/html':
                    raise discord.InvalidData(await r.text())
                raise discord.InvalidData(await r.json())


async def gzip_crash(url):
    async with aiohttp.ClientSession() as session:
        i = 0
        async with session.get(url) as r:
            if r.status == 200:
                result = bytes()
                while True:
                    chunk = await r.content.read(1024)
                    if not chunk:
                        break
                    result += chunk
                    i += 1
                    if i > 512:
                        # Too big!
                        return None
                return gzip.compress(result)
    return None
