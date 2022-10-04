from __future__ import annotations

import asyncio
import copy
import logging
import re
from typing import Optional, TYPE_CHECKING

import aiohttp
import cachetools
import discord
from discord.ext import commands

from bot.cogs.thread import ThreadData
from bot.core.context import Context
from bot.util.webhooker import Webhooker

from contextlib import asynccontextmanager
from bot.util import cache

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
    thread = db.Column(db.ForeignKey(table='threads', column='thread_id', sql_type=db.Integer(big=True)))
    repository = db.Column(db.ForeignKey(table='repositories', column='id', sql_type=db.Integer(big=True)))
    number = db.Column(db.Integer())
    pull_request = db.Column(db.Boolean())
    closed = db.Column(db.Boolean())
    locked = db.Column(db.Boolean())
    labels = db.Column(db.Array(db.String()))
    author = db.Column(db.ForeignKey(table='github_users', column='id'), sql_type=db.Integer(big=True))
    title = db.Column(db.String())


class IssueComment(db.Table, table_name='issue_comments'):

    issue = db.Column(db.ForeignKey(table='issues', column='id', sql_type=db.Integer(big=True)))
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
            command = "SELECT full_name FROM repositories WHERE installation_id = $1;"
            row = await con.fetchrow(command, self.installation_id)
        self._repo = row['full_name']
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

    async def update_issue_comment_discord(self, message: discord.Message, issue_data):
        async with self.github.get_lock(self.installation_id):
            content = self.github.message_to_content(message)
            comment = await self.github.get_issue_comment(message_id=message.id)
            if not comment:
                logging.warning(f'Message {message.id} not found in issue comments.')
                return
            if comment['github_message']:
                # Don't need to do anything because this should be handled on github's side
                return
            await self.gh.post(f'/repos/{await self.get_repo()}/issues/comments/{comment["id"]}', data={'body': content}, oauth_token=await self.get_token())
            await self.github.update_issue_content_from_discord(content, message)

    async def insert_issue_comment_discord(self, message: discord.Message, issue_data):
        content = self.github.message_to_content(message)
        if not issue_data:
            logging.warning(f'Message {message.id} not found in issue comments.')
            return
        async with self.github.get_lock(self.installation_id):
            # We don't want github to send back the message before we have logged the message in the database
            response = await self.gh.post(f'/repos/{await self.get_repo()}/issues/{issue_data["number"]}/comments', data={'body': content}, oauth_token=await self.get_token())
            await self.github.insert_issue_content_from_discord(response, issue_data, content, message)

    async def insert_issue_comment_github(self, comment_data, issue_data):
        kwargs = self.github.data_to_kwargs(comment_data['body'])
        thread_data = await self.github.bot.thread_handler.get_thread(issue_data['thread_id'])
        thread = thread_data.thread
        if not thread:
            thread = await self.github.bot.get_guild(thread.guild_id).fetch_channel(thread.thread_id)
        webhooker = self.github.get_webhooker(thread.parent)
        message = await webhooker.send(thread=thread, wait=True, **kwargs)
        await self.github.insert_issue_content_from_github(comment_data, issue_data, message)

    async def update_issue_comment_github(self, data: dict, issue_data):
        kwargs = self.github.data_to_kwargs(data)
        webhook: Webhooker = self.github.get_webhooker(await self.github.get_channel(await self.get_repo()))
        await webhook.edit(issue_data['message_id'], **kwargs)
        await self.github.update_issue_content_from_github(kwargs['content'], data['id'])

    async def delete_issue_comment_github(self, update_data, comment_data, issue_data):
        guild = self.github.bot.get_guild(comment_data['guild_id'])
        thread = guild.get_channel(comment_data['channel_id'])
        if not thread:
            thread = await guild.fetch_channel(comment_data['channel_id'])
        partial_message = thread.get_partial_message(comment_data['message_id'])
        message = next((m for m in self.github.bot.cached_messages if m.id == partial_message.id), None)
        if not message:
            message = await partial_message.fetch()
        async with db.MaybeAcquire(pool=self.github.bot.pool) as con:
            await con.execute("DELETE FROM issue_comments WHERE id = $1;", comment_data['id'])
        try:
            await message.delete()
        except:
            pass

    async def delete_issue_comment_discord(self, comment_data, issue_data, repo_data):
        async with db.MaybeAcquire(pool=self.github.bot.pool) as con:
            await con.execute("DELETE FROM issue_comments WHERE id = $1;", comment_data['id'])
        guild = self.github.bot.get_guild(comment_data['guild_id'])
        thread = guild.get_channel(comment_data['channel_id'])
        if not thread:
            thread = await guild.fetch_channel(comment_data['channel_id'])
        partial_message = thread.get_partial_message(comment_data['message_id'])
        message = next((m for m in self.github.bot.cached_messages if m.id == partial_message.id), None)
        if not message:
            message = await partial_message.fetch()
        try:
            await message.delete()
        except:
            pass


class Github(commands.Cog):

    def __init__(self, bot):
        self.bot: Mikro = bot
        self.locks = {}

    def data_to_kwargs(self, data):
        return {
            'username': data['user']['login'],
            'content': data['body'],
            'avatar_url': data['user']['avatar_url']
        }

    @asynccontextmanager
    async def get_lock(self, installation_id):
        # https://stackoverflow.com/questions/66994203/create-asyncio-lock-with-name
        if installation_id not in self.locks:
            self.locks[installation_id] = asyncio.Lock()
        async with self.locks[installation_id]:
            yield
        if self.locks[installation_id]._waiters is None or len(self.locks[installation_id]._waiters) == 0:
            del self.locks[installation_id]

    def message_to_content(self, message: discord.Message):
        return f'`Comment from: {message.author}`\n{message.content}'

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not isinstance(message.channel, discord.Thread) or not isinstance(message.channel.parent, discord.ForumChannel):
            return
        if message.guild is None or message.guild.id != 753693459369427044:
            return
        thread: discord.Thread = message.channel
        issue_data = await self.get_issue(thread)
        if not issue_data:
            return
        if message.author is None or message.author.bot or message.webhook_id is not None:
            return
        installation_id = await self.get_installation_id(issue_data['repository'])
        async with GithubSession(installation_id=installation_id, github=self) as gh:
            await gh.insert_issue_comment_discord(message, issue_data=issue_data)

    @commands.Cog.listener()
    async def on_raw_thread_update(self, payload: discord.RawThreadUpdateEvent):
        if payload.guild_id is None or payload.guild_id != 753693459369427044:
            return
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            issue_data = await con.fetchrow("SELECT * FROM issues WHERE thread = $1;", payload.thread_id)
            if issue_data is None:
                return
            repo_data = await con.fetchrow("SELECT * FROM repositories WHERE id = $1;", issue_data['repository'])
        if payload.thread:
            thread = payload.thread
            thread = copy.copy(thread)
            thread._update(payload.data)
        else:
            thread = self.bot.get_guild(payload.guild_id).get_thread(payload.thread_id)
            if not thread:
                thread = await self.bot.get_guild(payload.guild_id).fetch_channel(payload.thread_id)
        async with self.get_lock(repo_data['installation_id']):
            if not (thread.locked and issue_data['locked']):
                async with GithubSession(installation_id=repo_data['installation_id'], github=self) as gh:
                    url = f"/repos/{repo_data['full_name']}/issues/{issue_data['number']}/{'lock' if thread.locked else 'unlock'}"
                    try:
                        await gh.gh.put(
                            url,
                            data={'lock_reason': 'resolved'},
                            oauth_token=await gh.get_token(),
                        )
                    except:
                        logging.warning("Mismatch on issue url " + url)
                async with db.MaybeAcquire(pool=self.bot.pool) as con:
                    await con.execute('UPDATE issues SET locked = $1 WHERE id = $2;', thread.locked, issue_data['id'])
            if not (thread.archived and issue_data['closed']):
                async with GithubSession(installation_id=repo_data['installation_id'], github=self) as gh:
                    await gh.gh.post(
                        f"/repos/{repo_data['full_name']}/issues/{issue_data['number']}",
                        data={'state': "closed" if thread.archived else "open"},
                        oauth_token=await gh.get_token(),
                    )
                async with db.MaybeAcquire(pool=self.bot.pool) as con:
                    await con.execute('UPDATE issues SET closed = $1 WHERE id = $2;', thread.archived, issue_data['id'])
            if not (issue_data['title'] in thread.name):
                match = re.match('^\\[.*?\\]', thread.name)
                if match:
                    title_comp = thread.name[match.end():]
                    async with GithubSession(installation_id=repo_data['installation_id'], github=self) as gh:
                        await gh.gh.post(
                            f"/repos/{repo_data['full_name']}/issues/{issue_data['number']}", data={'title': title_comp},
                            oauth_token=await gh.get_token(),
                        )
                    async with db.MaybeAcquire(pool=self.bot.pool) as con:
                        await con.execute('UPDATE issues SET title = $1 WHERE id = $2;', title_comp, issue_data['id'])
                else:
                    # Reset the name since it doesn't follow the type
                    new_title = '[{0}] {1}'.format(repo_data['name'], issue_data['title'])
                    await thread.edit(name=new_title)
            thread_tags = set([tag.name for tag in thread.applied_tags])
            db_tags = set(issue_data['labels'])
            if thread_tags != db_tags:
                async with self.get_lock(repo_data['installation_id']):
                    command = "UPDATE issues SET labels = $1;"
                    async with db.MaybeAcquire(pool=self.bot.pool) as con:
                        await con.execute(command, list(thread_tags))
                    async with GithubSession(github=self, installation_id=repo_data['installation_id']) as gh:
                        await gh.gh.post(f"/repos/{repo_data['full_name']}/issues/{issue_data['number']}", data={'labels': list(thread_tags)})

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        if payload.guild_id is None or payload.guild_id != 753693459369427044:
            return
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            issue_com = "SELECT * FROM issue_comments WHERE message_id = $1;"
            comment_data = await con.fetchrow(issue_com, payload.message_id)
            if comment_data is None:
                return
            issue_data = await con.fetchrow("SELECT * FROM issues WHERE id = $1;", comment_data['issue']);
            repo_data = await con.fetchrow("SELECT * FROM repositories WHERE id = $1;", issue_data['repository'])

        async with self.get_lock(repo_data['installation_id']):
            async with GithubSession(self, repo_data['installation_id']) as gh:
                await gh.delete_issue_comment_discord(comment_data, issue_data, repo_data)


    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        if payload.guild_id is None or payload.guild_id != 753693459369427044:
            return
        if 'content' not in payload.data:
            return
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            issue_com = "SELECT * FROM issue_comments WHERE message_id = $1;"
            comment = await con.fetchrow(issue_com, payload.message_id)
            if comment is None:
                return
        if payload.cached_message:
            message = payload.cached_message
            thread = message.channel
            message = copy.copy(message)
            message._update(payload.data)
        else:
            thread = self.bot.get_guild(payload.guild_id).get_thread(comment['channel_id'])
            if not thread:
                thread = await self.bot.get_guild(payload.guild_id).fetch_channel(comment['thread'])
            message = await thread.fetch_message(payload.message_id)
        installation_id = await self.get_installation_id(thread=thread)
        issue_data = await self.get_issue(thread)
        async with GithubSession(self, installation_id=installation_id) as gh:
            await gh.update_issue_comment_discord(message, issue_data)

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

    async def get_issue_comment(self, *, message_id: Optional[int] = None, issue_comment_id: Optional[int] = None):
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

    async def insert_issue_content_from_discord(self, comment, issue_data, content, message: discord.Message):
        command = "INSERT INTO issue_comments(issue, id, github_message, guild_id, channel_id, message_id, content) VALUES ($1, $2, $3, $4, $5, $6, $7);"
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            await con.execute(command, issue_data['id'], comment['id'], False, message.guild.id, message.channel.id, message.id, message.content)

    async def update_issue_content_from_discord(self, body, message: discord.Message):
        command = "UPDATE issue_comments SET content = $1 WHERE message_id = $2;"
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            await con.execute(command, body, message.id)

    async def insert_issue_content_from_github(self, comment, issue_data, message: discord.Message):
        command = "INSERT INTO issue_comments(issue, id, github_message, guild_id, channel_id, message_id, content) VALUES ($1, $2, $3, $4, $5, $6, $7);"
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            await con.execute(command, issue_data['id'], comment['id'], True, message.guild.id, message.channel.id, message.id, message.content)

    async def update_issue_content_from_github(self, body, comment_id):
        command = "UPDATE issue_comments SET content = $1 WHERE id = $2;"
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            await con.execute(command, body, comment_id)

    @cache.cache(maxsize=512)
    async def get_installation_id(self, repo_id=None, thread=None):
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            if repo_id is None:
                row = await con.fetchrow('SELECT repository FROM issues WHERE thread = $1;', thread.id)
                if not row:
                    return None
                repo_id = row['repository']

            row = await con.fetchrow('SELECT installation_id FROM repositories WHERE id = $1;', repo_id)
            if row is None:
                return
            return row['installation_id']

    async def sync_full_issue(self, repo_data, issue: int):
        forum: discord.ForumChannel = self.bot.get_guild(repo_data['link_guild']).get_channel(repo_data['link_channel'])
        webhook = self.get_webhooker(forum)
        async with GithubSession(installation_id=repo_data['installation_id'], github=self) as gh:
            issue_data = await gh.gh.getitem(f'/repos/{repo_data["full_name"]}/issues/{issue}', oauth_token=await gh.get_token())
            thread = await self.create_or_get_issue_thread(repo_data, issue_data, webhook, gh)
            await thread.edit(slowmode_delay=15)
            issue_comments = await gh.gh.getitem(f'/repos/{repo_data["full_name"]}/issues/{issue}/comments', oauth_token=await gh.get_token())
            for comment in issue_comments:
                await self.create_issue_comment(webhook, thread, repo_data, issue_data, comment)

    async def sync_labels(self, repo_fullname, channel: discord.ForumChannel):
        async with GithubSession(github=self, installation_id=None) as gh:
            tag_names = [tag.name for tag in channel.available_tags]
            async for label in gh.gh.getiter(f"/repos/{repo_fullname}/labels"):
                if label['name'] in tag_names:
                    continue
                await channel.create_tag(name=label['name'], moderated=True)

    async def create_issue_comment(self, webhooker: Webhooker, thread: discord.Thread, repo_data: dict, issue_data: dict, comment_data: dict):
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            row = await con.fetchrow('SELECT id FROM issue_comments WHERE id = $1 AND issue = $2;', comment_data['id'], issue_data['id'])
            if row:
                # Already exists
                return
        kwargs = self.data_to_kwargs(comment_data)
        message = await webhooker.send(thread=thread, wait=True, **kwargs)
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            await con.execute(
                "INSERT INTO issue_comments(issue, id, github_message, guild_id, channel_id, message_id, content) VALUES ($1, $2, $3, $4, $5, $6, $7);",
                issue_data['id'], comment_data['id'], True, message.guild.id, message.channel.id, message.id, issue_data['body'],
            )

    async def create_or_get_issue_thread(self, repo_data: dict, issue_data: dict, webhooker: Webhooker, gh: GithubSession):
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            row = await con.fetchrow('SELECT thread FROM issues WHERE id = $1;', issue_data['id'])
            if row:
                data: ThreadData = await self.bot.thread_handler.get_thread(row['thread'])
                if data.thread:
                    return data.thread
                return await data.guild.fetch_channel(data.thread_id)
        command = "INSERT INTO issues(id, thread, repository, number, pull_request, closed, locked, labels, author, title) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10);"
        message: discord.WebhookMessage = await webhooker.create_thread(f"[{repo_data['name']}] {issue_data['title']}", wait=True, **self.data_to_kwargs(issue_data))
        thread: discord.Thread = next(thread for thread in message.channel.threads if thread.id == message.id)
        labels = [label['name'] for label in issue_data['labels']]

        available_tags = thread.parent.available_tags
        tags = []

        for label in labels:
            tag = next((t for t in available_tags if t.name == label), None)
            if tag:
                tags.append(tag)

        if tags:
            await thread.add_tags(*tags)

        # Give thread time to register
        await asyncio.sleep(3)
        async with db.MaybeAcquire(pool=self.bot.pool) as con:
            await con.execute('INSERT INTO github_users(id, name, icon) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING;', issue_data['user']['id'], issue_data['user']['login'], issue_data['user']['avatar_url'])
            await con.execute(
                command,
                issue_data['id'], thread.id, repo_data['id'], issue_data['number'],
                'pull_request' in issue_data,
                issue_data['state'] == 'closed', issue_data['locked'],
                labels,
                issue_data['user']['id'],
                issue_data['title'],
            )
            await con.execute(
                "INSERT INTO issue_comments(issue, id, github_message, guild_id, channel_id, message_id, content) VALUES ($1, $2, $3, $4, $5, $6, $7);",
                issue_data['id'], 0, True, message.guild.id, message.channel.id, message.id, issue_data['body'],
            )
        return thread

    @commands.is_owner()
    @commands.group(name='github')
    async def github_cmd(self, ctx: Context):
        pass

    @github_cmd.command(name='sync_issue')
    async def sync_issue(self, ctx: Context, repo: str, issue: int):
        command = "SELECT * FROM repositories WHERE full_name = $1;"
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
        async with GithubSession(installation_id=None, github=self) as gh:
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
        await self.sync_labels(repo['full_name'], channel)
        await ctx.send("Created!")


async def setup(bot):
    await bot.add_cog(Github(bot))
