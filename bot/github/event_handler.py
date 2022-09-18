import logging
import traceback

from aiohttp import web
from gidgethub import routing, sansio, aiohttp
import asyncio
import bot as bot_global
from bot.github import github_handler
from bot.util import database as db

router = routing.Router()


def register(event_type, **data_detail):

    def decorator(func):

        func.register = (event_type, data_detail)

        return func

    return decorator


class Register(object):

    def __init__(self):
        super().__init__()
        object_methods = [method_name for method_name in dir(self) if callable(getattr(self, method_name))]
        for method_name in object_methods:
            func = getattr(self, method_name)
            register = getattr(func, 'register', None)
            if not register:
                continue

            async def inner_method(*args, **kwargs):
                await func(self, *args, **kwargs)

            router.add(inner_method, event_type=register[0], **register[1])


class WebhookReceiver(Register):

    def __init__(self, bot):
        self.bot = bot
        super().__init__()

    @property
    def github(self) -> github_handler.Github:
        return self.bot.get_cog('Github')

    @register('issue_comment', action='created')
    async def created_issue(self, event: sansio.Event, gh: aiohttp.GitHubAPI, *arg, **kwargs):
        pass

    @register('issue_comment', action='edited')
    async def edited_issue(self, event: sansio.Event, gh: aiohttp.GitHubAPI, *arg, **kwargs):
        pass

    @register('issue_comment', action='deleted')
    async def deleted_issue(self, event: sansio.Event, gh: aiohttp.GitHubAPI, *arg, **kwargs):
        pass

    @register('issues', action='reopened')
    async def reopened_issue(self, event: sansio.Event, gh: aiohttp.GitHubAPI, *arg, **kwargs):
        pass

    @register('issues', action='labeled')
    async def labeled_issue(self, event: sansio.Event, gh: aiohttp.GitHubAPI, *arg, **kwargs):
        pass

    @register('issues', action='unlabled')
    async def unlabeled_issue(self, event: sansio.Event, gh: aiohttp.GitHubAPI, *arg, **kwargs):
        pass

    @register('issues', action='locked')
    async def locked_issue(self, event: sansio.Event, gh: aiohttp.GitHubAPI, *arg, **kwargs):
        pass

    @register('issues', action='unlocked')
    async def unlocked_issue(self, event: sansio.Event, gh: aiohttp.GitHubAPI, *arg, **kwargs):
        pass

    @register('issues', action='pinned')
    async def pinned_issue(self, event: sansio.Event, gh: aiohttp.GitHubAPI, *arg, **kwargs):
        pass

    @register('issues', action='unpinned')
    async def unpinned_issue(self, event: sansio.Event, gh: aiohttp.GitHubAPI, *arg, **kwargs):
        pass

    @register('issues', action='opened')
    async def opened_issue(self, event: sansio.Event, gh: aiohttp.GitHubAPI, *arg, **kwargs):
        pass

    @register('issues', action='closed')
    async def closed_issue(self, event: sansio.Event, gh: aiohttp.GitHubAPI, *arg, **kwargs):
        pass

    @register('pull_request', action='closed')
    async def closed_pr(self, event: sansio.Event, gh: aiohttp.GitHubAPI, *arg, **kwargs):
        pass

    @register("pull_request", action="opened")
    async def opened_pr(self, event, gh, *arg, **kwargs):
        pass

    @register("pull_request", action="labeled")
    async def labeled_pr(self, event, gh, *arg, **kwargs):
        pass

    @register("pull_request", action="unlabeled")
    async def unlabeled_pr(self, event, gh, *arg, **kwargs):
        pass

    @register("pull_request", action="locked")
    async def locked_pr(self, event, gh, *arg, **kwargs):
        pass

    @register("pull_request", action="unlocked")
    async def unlocked_pr(self, event, gh, *arg, **kwargs):
        pass

    @register("pull_request", action="edited")
    async def edited_pr(self, event, gh, *arg, **kwargs):
        pass

    async def on_request(self, request: web.Request):
        print('WOOOO')
        try:
            body = await request.read()
            secret = bot_global.config['gh_secret']
            event = sansio.Event.from_http(request.headers, body, secret=secret)
            if event.event == "ping":
                return web.Response(status=200)
            installation = event.data['installation']['id']
            logging.info(f"Installation ID: {installation}")
            if event.data['repository']:
                async with db.MaybeAcquire(pool=self.bot.pool) as con:
                    command = 'UPDATE repositories SET installation_id = $1 WHERE id = $2;'
                    await con.execute(command, installation, event.data['repository']['id'])
            async with github_handler.GithubSession(github=self.bot.get_cog('Github'), installation_id=installation) as gh:
                # Give GitHub some time to reach internal consistency.
                await asyncio.sleep(1)
                await router.dispatch(event, gh)
            return web.Response(status=200)
        except:
            traceback.print_exc()
            return web.Response(status=500)


async def run_webhook(bot):
    receiver = WebhookReceiver(bot)
    app = web.Application()
    app.router.add_post(r"/webhook", receiver.on_request)
    port = bot_global.config["gh_port"]
    if port is not None:
        port = int(port)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, bot_global.config['gh_host'], port)
    await site.start()
    print('Webhook open at port ' + str(port))
