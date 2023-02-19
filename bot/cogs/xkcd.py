from datetime import datetime

import aiohttp
from discord.ext import commands

from bot.core.context import Context
from bot.core.embed import Embed
from bot.mikro import Mikro


class XKCD(commands.Cog):

    def __init__(self, bot: Mikro):
        self.bot = bot
        self.bot.add_loop("xkcd", self.xkcd_loop)

    async def get_current(self):
        async with aiohttp.ClientSession() as session:
            async with session.get("https://xkcd.com/info.0.json") as r:
                if r.status != 200:
                    return None
                return await r.json()

    async def xkcd_loop(self, time: datetime):
        if time.minute != 0:
            return
        if time.hour != 18:
            return
        comic = await self.get_current()
        if comic is None or time.day != int(comic['day']):
            return
        embed = self.format_embed(comic)
        channel = self.bot.get_guild(753693459369427044).get_channel(753695400182939678)
        await channel.send(embed=embed)

    @commands.hybrid_command(name="xkcd", description="Get an XKCD comic")
    async def xkcd_command(self, ctx: Context, *, number: int):
        async with aiohttp.ClientSession() as session:
            async with session.get("https://xkcd.com/{0}/info.0.json".format(number)) as r:
                if r.status != 200:
                    await ctx.send("An error occurred! Maybe that comic doesn't exist?", ephemeral=True)
                    return
                comic = await r.json()
        embed = self.format_embed(comic)
        await ctx.send(embed=embed)

    @classmethod
    def format_embed(cls, comic: dict):
        embed = Embed()
        embed.set_title(comic['title'])
        embed.url = "https://xkcd.com/{0}/".format(comic['num'])
        embed.set_footer(text='{0}-{1}-{2} #{3}'.format(comic['year'], comic['month'], comic['day'], comic['num']))
        embed.set_image(url=comic['img'])
        return embed


async def setup(bot):
    await bot.add_cog(XKCD(bot))
