import base64
import datetime
import json
import re
import typing
from collections import Counter

import bot as bot_global

import aiohttp
import discord

from . import custom_response
from urllib import parse
from bs4 import BeautifulSoup


@custom_response(parse.ParseResult)
async def github(content: parse.ParseResult):
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
    async with aiohttp.ClientSession(auth=aiohttp.BasicAuth(bot_global.config['gh_user'], bot_global.config['gh_token'])) as session:
        if len(parts) > 3:
            if parts[3] == 'blob' and len(parts) > 4:
                if content.fragment and 'L' in content.fragment:
                    content, embed = await build_blob_embed(session, content.geturl(), owner, repo, parts[4:], content.fragment)
                    return {'embed': embed, 'content': content}
                else:
                    embed = await build_file_embed(session, content.geturl(), owner, repo, parts[4:])
                    return {'embed': embed}
            if parts[3] == 'commit':
                embed = await build_commit_embed(session, content.geturl(), owner, repo, parts[4])
                return {'embed': embed}
        else:
            async with aiohttp.ClientSession() as session:
                embed = await build_embed(session, owner, repo)
                return {'embed': embed}
    return None


async def build_blob_embed(session, url, owner, repo, blob_path, lines):
    embed = await build_file_embed(session, url, owner, repo, blob_path, blob=True)
    embed.title = '{0} {1} from {2}'.format(blob_path[-1], lines, repo)
    path = blob_path
    ref = None
    if len(path[0]) == 40:
        ref = path[0]
    path = path[1:]
    file = path[-1]
    path = path[:-1]
    if len(file.split('.')) > 1:
        ext = file.split('.')[1]
    else:
        ext = ''
    nav = '/'.join(path) + '/' + file
    ending = ''
    if ref is not None:
        ending = '?ref={0}'.format(ref)
    file_data = await request_file(
        session, 'https://api.github.com/repos/{0}/{1}/contents/{2}'.format(owner, repo, nav) + ending,
        limit_kb=128
    )
    if file_data is None:
        embed.description = 'File too large...'
        return '', embed
    raw_text = base64.b64decode(file_data['content']).decode('utf-8').replace(r'\t', '    ')
    if not isinstance(raw_text, str):
        embed.description = 'Not a text file'
        return '', embed
    text = raw_text.split('\n')

    matches = re.findall(r'\d+', lines)
    start = int(matches[0]) - 1
    if len(matches) > 1:
        end = int(matches[1]) + 1
    else:
        end = start

    if end > len(text):
        end = len(text)
    if start < 0:
        start = 0

    if end < start:
        inter = end
        end = start
        start = inter

    end_lines = text[start:end]
    min_white = -1
    for t in end_lines:
        size = t.lstrip()
        if len(size) == 0:
            continue
        if min_white < 0:
            min_white = len(t) - len(size)
        else:
            min_white = min(min_white, len(t) - len(size))
    if min_white > 0:
        new_text = []
        for t in end_lines:
            if len(t) > min_white:
                new_text.append(t[min_white:])
            else:
                new_text.append(t)
        end_lines = new_text

    formatted = '\n'.join(end_lines)
    formatted = formatted.replace('```', '` ` `')
    if len(formatted) > 2000 - 20:
        formatted = formatted[:1977] + '...'

    content = "```{ext}\n{content}\n```".format(ext=ext, content=formatted)
    return content, embed


async def build_file_embed(session, url, owner, repo, path, blob=False):
    embed = await build_embed(session, owner, repo, use_image=not blob, use_released=False, use_languages=False)
    embed.clear_fields()
    embed.url = url
    embed.title = '{0} from {1}'.format(path[-1], repo)
    ref = None
    if len(path[0]) == 40:
        ref = path[0]
    path = path[1:]
    quote = parse.quote_plus('/'.join(path))
    if ref:
        ref = '&ref={0}'.format(ref)
    else:
        ref = ''
    data: list[dict] = await request(session, 'https://api.github.com/repos/{0}/{1}/commits?path={2}&page=1&per_page=1{3}'.format(owner, repo, quote, ref))
    commit = data[0]['commit']
    embed.add_field(name='Updated At', value='<t:{0}:f>'.format(iso_to_seconds(commit['committer']['date'])))
    committer = data[0]['committer']
    if committer is not None and isinstance(committer, dict):
        embed.set_author(name=committer['login'], icon_url=committer['avatar_url'], url=committer['html_url'])
    embed.add_field(name='Message', value=commit['message'])
    return embed


async def build_commit_embed(session, url, owner, repo, commit):
    embed = await build_embed(session, owner, repo, use_image=False, use_released=False, use_languages=False)
    embed.set_image(url=await get_image(session, url))
    embed.clear_fields()
    embed.title = 'Commit {0} at {1}'.format(commit[:8], repo)
    embed.url = url
    commit = await request(session, 'https://api.github.com/repos/{0}/{1}/commits/{2}'.format(owner, repo, commit))
    files = commit['files']
    statuses = Counter()
    for f in files:
        statuses[f['status']] += 1
    committer = commit['committer']
    if committer is not None and isinstance(committer, dict):
        embed.set_author(name=committer['login'], icon_url=committer['avatar_url'], url=committer['html_url'])
    embed.description = commit['commit']['message']
    embed.add_field(
        name='Stats',
        value='Additions: `{0}`\nDeletions: `{1}`\nTotal: `{2}`'.format(
            commit['stats']['additions'], commit['stats']['deletions'], commit['stats']['total']
        ),
    )
    embed.add_field(name='Files', value='\n'.join(['{0}: `{1}`'.format(s.capitalize(), c) for s, c in statuses.items()]))
    embed.add_field(name='Updated At', value='<t:{0}:f>'.format(iso_to_seconds(commit['commit']['committer']['date'])))
    return embed


async def build_embed(session, owner, repo, *, use_image=True, use_languages=True, use_released=True):
    embed = discord.Embed()
    data = await get_raw_data(session, owner, repo)

    embed.title = data['name']
    embed.url = data['svn_url']
    description = data['description']
    if len(description) > 500:
        description = description[:497] + '...'
    embed.description = description
    embed.set_author(name=data['owner']['login'], icon_url=data['owner']['avatar_url'], url=data['owner']['html_url'])
    if use_image:
        embed.set_image(url=await get_image(session, data['svn_url']))

    if use_languages:
        languages = await get_formatted_languages(session, owner, repo)
        embed.add_field(name='Languages', value=languages, inline=True)

    embed.add_field(
        name='Time',
        value='Created <t:{0}:f>\nPushed <t:{1}:f>'.format(
            iso_to_seconds(data['created_at']), iso_to_seconds(data['pushed_at'])
        ),
        inline=True
    )

    license = data.get('license')
    if license:
        name = license.get('name')
        if name:
            embed.add_field(name='License', value='[{0}]({1})'.format(license['name'], license['url']), inline=True)

    topics = data.get('topics')
    if topics:
        topics_string = ''
        for topic in topics:
            if len(topics_string) > 50:
                topics_string += '...'
                break
            topics_string += '`{0}` '.format(topic)
        embed.description += '\n\n**Topics:** ' + topics_string

    if use_released:
        release = await get_recent_release(session, owner, repo)
    else:
        release = None
    if release:
        timestamp = iso_to_seconds(release['created_at'])
        value = '**[{0}]({1})** <t:{2}:f>'.format(release['name'], release['html_url'], timestamp)
        body = release.get('body', None)
        if body:
            if len(body) > 30:
                body = body[:30]
            value += '\n{0}'.format(body)
        embed.add_field(name='Latest Release', value=value, inline=True)

    return embed


async def get_recent_release(session, owner, repo) -> dict:
    data = await request(session, 'https://api.github.com/repos/{0}/{1}/releases'.format(owner, repo))
    if len(data) == 0:
        return None
    return data[0]


async def get_image(session, url):
    html = await request(session, url, type='text')
    soup = BeautifulSoup(html, features='html.parser')
    return soup.find('head').find('meta', property='og:image')['content']


async def get_raw_data(session, owner, repo):
    return await request(session, 'https://api.github.com/repos/{0}/{1}'.format(owner, repo))


async def get_formatted_languages(session, owner, repo):
    languages = await get_languages(session, owner, repo)
    languages_str = ''
    for language, percent in languages.items():
        languages_str += '{percent:.1f}% {language}\n'.format(language=language, percent=percent * 100)
    return languages_str[:-1]


async def get_languages(session, owner, repo):
    data = await request(session, 'https://api.github.com/repos/{0}/{1}/languages'.format(owner, repo))
    total = sum((v for v in data.values()))
    return {k: v / total for k, v in data.items()}


async def request(session, url, *, type='json') -> typing.Union[dict, str, list]:
    async with session.get(url) as r:
        if type == 'json':
            return await r.json()
        return await r.text()


async def request_file(session, url, *, limit_kb=-1):
    i = 0
    result = bytes()
    async with session.get(url) as r:
        while True:
            chunk = await r.content.read(1024)
            if not chunk:
                break
            result += chunk
            i += 1
            if 0 < limit_kb < i:
                # Too big!
                return None
    return json.loads(result.decode('utf-8'))


def iso_to_seconds(iso):
    date = datetime.datetime.strptime(iso, '%Y-%m-%dT%H:%M:%SZ')
    return int((date - datetime.datetime(1970, 1, 1)).total_seconds())
