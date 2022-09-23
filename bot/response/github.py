from . import *

from urllib import parse
from bot.util.github_util import GithubClient


@custom_response(parse.ParseResult)
async def github(bot, content: parse.ParseResult):
    if content.netloc != 'github.com':
        return None
    path = content.path
    if not path:
        return None
    parts = path.split('/')
    if len(parts) < 3:
        # Not a repo
        return None
    owner = parts[1]
    repo = parts[2]
    async with GithubClient(owner, repo, content.geturl()) as client:
        client: GithubClient
        if len(parts) > 3:
            if parts[3] == 'blob' and len(parts) > 4:
                if content.fragment and 'L' in content.fragment:
                    content, embed = await client.build_blob_embed(parts[4:], content.fragment)
                    return {'embed': embed, 'content': content}
                else:
                    embed = await client.build_file_embed(parts[4:])
                    return {'embed': embed}
            if parts[3] == 'commit':
                embed = await client.build_commit_embed(parts[4])
                return {'embed': embed}
            if parts[3] == 'tree' and len(parts) == 4:
                embed = await client.build_embed()
                return {'embed': embed}
        else:
            embed = await client.build_embed()
            return {'embed': embed}
    return None

