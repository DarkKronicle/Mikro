from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

import aiohttp
import cachetools
import discord
from discord.ext import commands

from bot.core.context import Context
from bot.util.webhooker import Webhooker

if TYPE_CHECKING:
    from bot.mikro import Mikro

from bot.util import database as db
from gidgethub import aiohttp as gh_aiohttp
from gidgethub import apps

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
    github_message = db.Column(db.Boolean())
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
    installation_id = db.Column(db.Integer(big=True))


class GithubSession:

    def __init__(self, github, installation_id, repo=None):
        self.session: aiohttp.ClientSession = None
        self.gh: gh_aiohttp.GitHubAPI = None
        self.installation_id = installation_id
        self.token = None
        self.github: Github = github
        self._repo = None

    async def get_repo(self):
        if self._repo is not None:
            return self._repo
        async with db.MaybeAcquire(pool=self.github.bot.pool) as con:
            command = "SELECT name FROM repositories WHERE installation_id = $1;"
            row = await con.fetchrow(command, self.installation_id)
        self._repo = row['name']
        return self._repo

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

    async def __aenter__(self) -> GithubSession:
        self.session = aiohttp.ClientSession()
        self.gh = gh_aiohttp.GitHubAPI(self.session, "mikro-discord-link", cache=request_cache)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.session.close()

    async def update_issue_comment_discord(self, message: discord.Message):
        content = self.github.message_to_content(message)
        issue_data = await self.github.get_issue_information(message_id=message.id)
        if not issue_data:
            logging.warning(f'Message {message.id} not found in issue comments.')
            return
        await self.gh.post(f'/repos/{await self.get_repo()}/issues/comments/{issue_data["id"]}', data=content)
        await self.github.update_issue_content_from_discord(content, message)

    async def update_issue_comment_github(self, data: dict):
        kwargs = self.github.data_to_kwargs(data)
        issue_data = await self.github.get_issue_information(issue_comment_id=data['id'])
        if not issue_data:
            logging.warning(f'Issue comment {data["id"]} not found.')
            return
        webhook: Webhooker = self.github.get_webhooker(await self.github.get_channel(await self.get_repo()))
        await webhook.edit(issue_data['message_id'], **kwargs)
        await self.github.update_issue_content_from_github(kwargs['content'], data['id'])


class Github(commands.Cog):

    def __init__(self, bot):
        self.bot: Mikro = bot

    def data_to_kwargs(self, data):
        return {
            'username': data['user']['login'],
            'content': data['body'],
            'avatar_url': data['user']['avatar_url']
        }

    def message_to_content(self, message: discord.Message):
        return f'`Comment from: {message.author}`\n{message.content}'

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not isinstance(message.channel, discord.Thread) or not isinstance(message.channel.parent, discord.ForumChannel):
            return
        thread: discord.Thread = message.channel
        issue_data = await self.get_issue(thread)
        if not issue_data:
            return

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        if not payload.data.content:
            return
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            issue_com = "SELECT * FROM issue_comments WHERE message_id = $1;"
            comment = await con.fetchrow(issue_com, payload.message_id)
            if not comment:
                return
        if payload.cached_message:
            message = payload.cached_message
        else:
            thread = self.bot.get_guild(payload.guild_id).get_thread(comment['thread'])
            if not thread:
                thread = await self.bot.get_guild(payload.guild_id).fetch_channel(comment['thread'])
            message = await thread.fetch_message(payload.message_id)
        async with GithubSession(self) as gh:
            await gh.update_issue_comment_discord(message)

    async def get_issue(self, thread: discord.Thread) -> Optional[dict]:
        command = "SELECT * FROM issues WHERE thread = $1;"
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            return await con.fetchrow(command, thread.id)

    async def get_channel(self, repo) -> Optional[discord.ForumChannel]:
        command = 'SELECT link_guild, link_channel FROM repositories WHERE name = $1;'
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            row = await con.fetchrow(command, repo)
        if not row:
            return None
        guild = self.bot.get_guild(row['link_guild'])
        return guild.get_channel(row['link_channel'])

    def get_webhooker(self, channel: discord.ForumChannel) -> Webhooker:
        return Webhooker(self.bot, channel)

    async def get_issue_information(self, *, message_id: Optional[int] = None, issue_comment_id: Optional[int] = None):
        if message_id is None and issue_comment_id is None:
            return None
        if message_id is not None:
            command = "SELECT * FROM issue_comments WHERE message_id = $1;"
            async with db.MaybeAcquire(pool=self.bot.pool) as con:
                return await con.fetchrow(command, message_id)

        command = "SELECT * FROM issue_comments WHERE id = $1;"
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            return await con.fetchrow(command, issue_comment_id)

    async def add_issue_comment(self, repo_id, issue_id, repo: str, issue_number: int, message: discord.Message):
        content = f'[Message from {message.author}]({message.jump_url})\n\n{message.content}'
        async with GithubSession() as gh:
            response = await gh.gh.post(f'/{repo}/issues/{issue_number}/comments', data=content)
        await self.set_issue_db(repo_id, issue_id, response)

    async def set_issue_db(self, issue_id, body, message: discord.Message):
        command = "INSERT INTO issue_comments(issue, guild_id, channel_id, message_id, content) VALUES ($1, $2, $3, $4, $5);"
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            await con.execute(command, issue_id, message.guild.id, message.channel.id, message.id, body)

    async def update_issue_content_from_discord(self, body, message: discord.Message):
        command = "UPDATE issue_comments SET body = $1 WHERE message_id = $2;"
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            await con.execute(command, body, message.id)

    async def update_issue_content_from_github(self, body, comment_id):
        command = "UPDATE issue_comments SET content = $1 WHERE id = $2;"
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            await con.execute(command, body, comment_id)

    async def sync_full_issue(self, repo_data, issue: int):
        forum: discord.ForumChannel = self.bot.get_guild(repo_data['link_guild']).get_channel(repo_data['link_channel'])
        webhook = self.get_webhooker(forum)
        await webhook.create_thread()

    @commands.is_owner()
    @commands.group(name='github')
    async def github_cmd(self, ctx: Context):
        pass

    @github_cmd.command(name='sync_issue')
    async def sync_issue(self, ctx: Context, repo: str, issue: int):
        command = "SELECT * FROM repositories WHERE name = $1;"
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            repository = await con.fetchrow(command, repo)
        if not repository:
            await ctx.send("Repo " + repo + " does not exist in the database!")
            return
        await self.sync_full_issue(repository, issue)

    @github_cmd.command(name='add')
    async def add_repo(self, ctx: Context, repo: str, channel: discord.ForumChannel):
        if repo.count('/') != 1:
            return await ctx.send('Format repo in `owner/repo`')
        async with GithubSession(installation_id=None) as gh:
            try:
                repo = await gh.gh.getitem("/repos/" + repo)
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
