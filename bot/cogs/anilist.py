from discord.ext import commands
import aiohttp

import bot as bot_global
import urllib.parse
import discord

from bot.core.context import Context
from bot.core.embed import Embed
from bot.mikro import Mikro
from bot.util import database as db, cache, anilist_util


class AniListCodes(db.Table, table_name="anilist_tokens"):

    user_id = db.Column(db.Integer(big=True), unique=True, index=True)
    token = db.Column(db.String())


class AniList(commands.Cog):

    def __init__(self, bot: Mikro):
        self.bot = bot
        self._waiting_for_access = []

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not isinstance(message.channel, discord.DMChannel):
            return
        if message.author.id not in self._waiting_for_access:
            # Not waiting
            return
        code = message.content.strip()
        if ' ' in code:
            await message.channel.send("Invalid code!")
            return
        token = await self.make_token(code)
        if token is None:
            await message.channel.send("Something went wrong!")
            return
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            await con.execute("INSERT INTO anilist_tokens(user_id, token) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET token = EXCLUDED.token;", message.author.id, token)
        self.get_token.set(token, message.author.id)
        self._waiting_for_access.remove(message.author.id)
        await message.channel.send("Success! Feel free to delete the code you sent.")

    @cache.cache(64)
    async def get_token(self, user_id: int):
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            response = await con.fetchrow("SELECT token FROM anilist_tokens WHERE user_id = $1;", user_id)
            if response:
                return response['token']
            return None

    async def make_token(self, code):
        url = 'https://anilist.co/api/v2/oauth/token'
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }
        body = {
            'grant_type': 'authorization_code',
            'client_id': bot_global.config['anilist_id'],
            'client_secret': bot_global.config['anilist_secret'],
            'redirect_uri': bot_global.config['anilist_redirect'],
            'code': code
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=body) as r:
                data = await r.json()
                if r.status == 200:
                    return data.get('access_token')
                else:
                    print(data)
        return None

    @property
    def authorize_uri(self):
        return 'https://anilist.co/api/v2/oauth/authorize?client_id={client_id}&redirect_uri={redirect_url}&response_type=code'.format(
            client_id=bot_global.config['anilist_id'],
            redirect_url=urllib.parse.quote_plus(bot_global.config['anilist_redirect'])
        )

    def cog_check(self, ctx: Context) -> bool:
        return ctx.guild.id == 753693459369427044 and any((r.id == 753735538938216589 for r in ctx.author.roles))

    @commands.hybrid_group(name='anilist', description='AniList commands')
    async def anilist_group(self, ctx: Context):
        pass

    @anilist_group.command(name='login', description='Log in to AniList')
    async def login_command(self, ctx: Context):
        await ctx.send('Check your DMs!')
        await self.request_access(ctx.author)

    @anilist_group.command(name='search', description="Search for an anime by it's name")
    async def search_command(self, ctx: Context, *, search: str):
        query = anilist_util.ANIME_QUERY
        variables = {
            'search': search
        }
        response = await self.send_request(ctx.author.id, query, variables)
        if response is None:
            await ctx.send("You have to log in! Use `/anilist login`", ephemeral=True)
            return
        if await self.check_response(ctx, response):
            return
        await ctx.send(embed=self.format_anime_embed(response['data']['Media']))

    @anilist_group.command(name='set', description='Modify an entry on your list')
    async def anilist_set(self, ctx: Context, status: str, *, search: str):
        query = anilist_util.ANIME_QUERY
        variables = {
            'search': search
        }
        status = status.upper()
        if status not in ('CURRENT', 'PLANNING', 'COMPLETED', 'DROPPED', 'PAUSED', 'REPEATING'):
            await ctx.send("Status needs to be one of:\n`CURRENT`\n`PLANNING`\n`COMPLETED`\n`DROPPED`\n`PAUSED`\n`REPEATING`")
            return
        response = await self.send_request(ctx.author.id, query, variables)
        if response is None:
            await ctx.send("You have to log in! Use `/anilist login`", ephemeral=True)
            return
        if await self.check_response(ctx, response):
            return
        anime_id = response['data']['Media']['id']
        mutation = anilist_util.ANILIST_STATUS_MUTATION
        variables = {
            'id': anime_id,
            'status': status
        }
        response = await self.send_request(ctx.author.id, mutation, variables)
        if response is None:
            await ctx.send("Something went wrong!", ephemeral=True)
            return
        if await self.check_response(ctx, response):
            return
        await ctx.send("Success!")

    @anilist_group.command(name='id', description='Search for an anime by ID')
    async def id_command(self, ctx: Context, *, id: str):
        try:
            id = int(id)
        except:
            await ctx.send("ID has to be an int", ephemeral=True)
            return
        query = anilist_util.ANIME_QUERY
        variables = {
            'id': id
        }
        response = await self.send_request(ctx.author.id, query, variables)
        if response is None:
            await ctx.send("You have to log in! Use `/anilist login`", ephemeral=True)
            return
        if await self.check_response(ctx, response):
            return
        await ctx.send(embed=self.format_anime_embed(response['data']['Media']))

    def format_title(self, title: dict):
        if 'english' in title:
            if title['english'] == title['romaji']:
                return title['english']

            return '{english} ({romaji})'.format(
                english=title.get('english', ''),
                romaji=title.get('romaji', '')
            )
        return title['romaji']

    def format_date(self, date: dict):
        return '{0}-{1}-{2}'.format(date['year'], date['month'], date['day'])

    def get_date_string(self, content: dict):
        string = ''
        if 'startDate' in content:
            string += 'Start `' + self.format_date(content['startDate']) + '` '
        if 'endDate' in content:
            string += 'End `' + self.format_date(content['endDate']) + '`'
        return string

    def format_anime_embed(self, content: dict):
        embed = Embed(
            title=self.format_title(content['title']),
            inline=True
        )
        embed.url = content['siteUrl']
        embed.set_thumbnail(url=content['coverImage']['extraLarge'])
        embed.set_description(
            content['description'].replace('<br>', '').replace('<i>', '*').replace('</i>', '*')
        )
        embed.set_footer(text='ID: ' + str(content['id']))
        embed.add_field(name='Stats', value="""\n\n
            Average Score: `{score}`
            Length: `{duration} min`
            Episodes: `{episodes}`
            """.replace('\t', '').replace("  ", "").format(
                duration=content['duration'],
                score=content['averageScore'],
                episodes=content['episodes'],
            ) + self.get_date_string(content)
        )
        if content.get('mediaListEntry', None) is not None:
            embed.add_field(
                name='Your Status',
                value=content['mediaListEntry']['status']
            )
        if 'relations' in content and 'edges' in content['relations']:
            relations = []
            for r in content['relations']['edges']:
                if 'SEQUEL' == r['relationType'] or 'PREQUEL' == r['relationType']:
                    relations.append(self.format_title(r['node']['title']))
            embed.add_field(name='Adjacent Seasons', value='\n'.join(relations))
        return embed

    async def check_response(self, ctx: Context, response: dict):
        if 'errors' not in response:
            return False
        errors = response['errors']
        formatted_errors = []
        for e in errors:
            if 'Invalid token' in e.get('message', ''):
                formatted_errors.append("Token expired, use `/anilist login`")
            else:
                formatted_errors.append(e.get('message', str(e.get('status'))))
        await ctx.send('\n'.join(formatted_errors))
        return True

    async def request_access(self, user: discord.User):
        channel = user.dm_channel
        if channel is None:
            channel = await user.create_dm()
        await channel.send("Go to this URL and send me the code back here:\n\n" + self.authorize_uri, suppress_embeds=True)
        self._waiting_for_access.append(user.id)

    async def send_request(self, user_id: int, query, variables):
        token = await self.get_token(user_id)
        if token is None:
            return None
        url = "https://graphql.anilist.co"
        headers = {
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        data = {
            'query': query,
            'variables': variables
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data, headers=headers) as r:
                return await r.json()


async def setup(bot):
    await bot.add_cog(AniList(bot))

