from __future__ import annotations
from typing import Optional, TYPE_CHECKING

import aiohttp
import cachetools
import discord
from discord.ext import commands

from bot.core.context import Context

if TYPE_CHECKING:
    from bot.mikro import Mikro

from bot.util import database as db
from gidgethub import aiohttp as gh_aiohttp
from gidgethub import apps

import secrets
from bot.util import cache
import bot as bot_global


request_cache = cachetools.LRUCache(maxsize=500)


class GithubUser(db.Table, table_name='github_users'):

    id = db.Column(db.Integer(big=True), unique=True)
    name = db.Column(db.String())
    icon = db.Column(db.String())


class Issue(db.Table, table_name='issues'):

    id = db.Column(db.Integer(big=True), unique=True)
    thread = db.Column(db.ForeignKey(table='threads', column='thread_id'))
    repository = db.Column(db.ForeignKey(table='repositories', column='id'))
    number = db.Integer()
    pull_request = db.Column(db.Boolean())
    closed = db.Column(db.Boolean())
    locked = db.Column(db.Boolean())
    labels = db.Column(db.Array(db.String()))
    author = db.Column(db.ForeignKey(table='github_users', column='id'))
    title = db.String()


class IssueComment(db.Table, table_name='issue_comments'):

    issue = db.Column(db.ForeignKey(table='issues', column='id'))
    id = db.Column(db.Integer(big=True))
    guild_id = db.Column(db.Integer(big=True))
    channel_id = db.Column(db.Integer(big=True))
    message_id = db.Column(db.Integer(big=True), unique=True)
    content = db.Column(db.String())


class Repository(db.Table, table_name='repositories'):

    id = db.Column(db.Integer(big=True), unique=True)
    name = db.Column(db.String())
    full_name = db.Column(db.String(), unique=True)
    link_guild = db.Column(db.Integer(big=True))
    link_channel = db.Column(db.Integer(big=True))


class GithubSession:

    def __init__(self, installation_id):
        self.session: aiohttp.ClientSession = None
        self.gh: gh_aiohttp.GitHubAPI = None
        self.installation_id = installation_id
        self.token = None

    def get_jwt(self):
        return apps.get_jwt(app_id=bot_global.config["gh_id"], private_key=bot_global.config["gh_private_key"])

    async def get_token(self):
        if self.token is not None:
            return self.token
        self.token = (await apps.get_installation_access_token(
            self.gh,
            installation_id=self.installation_id,
            app_id=bot_global.config["gh_id"],
            private_key=bot_global.config["gh_private_key"]
        ))['token']
        return self.token

    async def __aenter__(self) -> gh_aiohttp.GitHubAPI:
        self.session = aiohttp.ClientSession()
        self.gh = gh_aiohttp.GitHubAPI(self.session, "mikro-discord-link", cache=request_cache)
        return self.gh

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.session.close()


class Github(commands.Cog):

    def __init__(self, bot):
        self.bot: Mikro = bot

    async def add_issue_comment(self, repo_id, issue_id, repo: str, issue_number: int, message: discord.Message):
        content = f'[Message from {message.author}]({message.jump_url})\n\n{message.content}'
        async with GithubSession() as gh:
            response = await gh.post(f'/{repo}/issues/{issue_number}/comments', data=content)
        await self.set_issue_db(repo_id, issue_id, response)

    async def set_issue_db(self, issue_id, body, message: discord.Message):
        command = "INSERT INTO issue_comments(issue, guild_id, channel_id, message_id, content) VALUES ($1, $2, $3, $4, $5);"
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            await con.execute(command, issue_id, message.guild.id, message.channel.id, message.id, body)

    async def _update_issue_content_from_discord(self, body, message: discord.Message):
        command = "UPDATE issue_comments SET body = $1 WHERE message_id = $2;"
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            await con.execute(command, body, message.id)

    async def _update_issue_content_from_github(self, body, comment_id):
        command = "UPDATE issue_comments SET content = $1 WHERE id = $2;"
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            await con.execute(command, body, comment_id)

    @commands.is_owner()
    @commands.group(name='github')
    async def github_cmd(self, ctx: Context):
        pass

    @github_cmd.command(name='add')
    async def add_repo(self, ctx: Context, repo: str, channel: discord.ForumChannel):
        if repo.count('/') != 1:
            return await ctx.send('Format repo in `owner/repo`')
        async with GithubSession() as gh:
            try:
                repo = await gh.getitem("/repos/" + repo)
            except:
                await ctx.send("Invalid repository!")
                return
        id = repo['id']
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            exists = "SELECT id FROM repositories WHERE id = $1;"
            row = await con.fetchrow(exists, id)
            if row:
                return await ctx.send("This repository already exists!")

            create = "INSERT INTO repositories(id, name, full_name, link_guild, link_channel) VALUES ($1, $2, $3, $4, $5);"
            await con.execute(create, id, repo['name'], repo['full_name'], channel.guild.id, channel.id)
        await ctx.send("Created!")


async def setup(bot):
    await bot.add_cog(Github(bot))
