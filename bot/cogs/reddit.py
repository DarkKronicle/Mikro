import random

import asyncpraw
from discord.ext import commands

from bot.core.context import Context
from bot.core.embed import Embed
from bot.mikro import Mikro
import bot as bot_global

from asyncpraw.reddit import Submission, Subreddit


# https://github.com/luni3359/koa-bot/blob/ab4a8eab1cc019c641b6d8fea1d5ea3ed2711080/koabot/cogs/site/reddit.py
class RedditCog(commands.Cog):

    def __init__(self, bot: Mikro):
        self.bot = bot
        self.reddit = asyncpraw.Reddit(
            user_agent=bot_global.config['reddit_user_agent'],
            client_id=bot_global.config['reddit_id'],
            client_secret=bot_global.config['reddit_secret'],
        )
        self.subreddits = []
        self.minutes = 30
        self.bot.add_loop()

    async def cog_load(self) -> None:
        self.subreddits = [
            await self.reddit.subreddit("ProgrammerHumor"),
            await self.reddit.subreddit("mathmemes"),
            await self.reddit.subreddit("okbuddyphd"),
            await self.reddit.subreddit("softwaregore"),
            await self.reddit.subreddit("ProgrammingHorror"),
            await self.reddit.subreddit("crazystairs"),
            await self.reddit.subreddit("PheonixSC"),
            await self.reddit.subreddit("UselessFacts"),
            await self.reddit.subreddit("BarbaraWalters4Scale"),
        ]

    async def random_loop(self, time):
        self.minutes -= 1
        if self.minutes > 0:
            return
        self.minutes = random.randint(30, 120)
        if 4 < time.hour < 16:
            return
        sub: Subreddit = random.choice(self.subreddits)
        async for submission in sub.top(limit=1, time_filter="day"):
            submission: Submission
            if submission.over_18:
                # Send a post again
                self.minutes = 0
                return
            subreddit: Subreddit = submission.subreddit
            await subreddit.load()
            await self.bot.get_main_guild().get_channel(753695400182939678).send(embed=self.format_embed(submission))

    def format_embed(self, submission: Submission, *, nsfw=False):
        subreddit: Subreddit = submission.subreddit
        embed = Embed()
        embed.set_author(
            name=submission.subreddit_name_prefixed,
            url=submission.shortlink,
            icon_url=self.get_subreddit_icon(subreddit)
        )
        embed.set_title(submission.title)
        embed.add_field(name='Score', value=f"{submission.score:,}")
        embed.add_field(name='Comments', value=f"{submission.num_comments:,}")
        embed.set_footer(text="r/{0}".format(subreddit.display_name))
        if submission.selftext and not (not nsfw and submission.over_18):
            max_post_length = 1000   # arbitrary maximum
            if len(submission.selftext) > max_post_length:
                # TODO: Disjointed markdown is not cleaned up
                # i.e. the closing ** is cut off
                description = submission.selftext[:max_post_length]
                embed.description = description + "…"
            else:
                embed.description = submission.selftext
        obfuscated_preview = False
        if not nsfw:
            obfuscated_preview = submission.over_18
        if hasattr(submission, 'preview') and 'images' in submission.preview:
            preview_root = submission.preview['images'][0]

            # Use blurred-out previews on NSFW posts in SFW channels
            if obfuscated_preview:
                preview_root = preview_root['variants']['nsfw']
            # Show gifs instead if available
            elif 'variants' in preview_root and 'gif' in preview_root['variants']:
                preview_root = preview_root['variants']['gif']

            post_preview = preview_root['resolutions'][-1]['url']
            embed.set_image(url=post_preview)
        return embed

    def get_subreddit_icon(self, subreddit: Subreddit):
        return subreddit.community_icon if subreddit.community_icon else subreddit.icon_img

    def cog_check(self, ctx: Context) -> bool:
        return ctx.guild.id == 753693459369427044


async def setup(bot):
    await bot.add_cog(RedditCog(bot))
