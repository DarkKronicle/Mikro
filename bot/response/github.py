import datetime
import typing

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
    if len(path.split('/')) != 3:
        # Probably has issues or smth
        return None
    owner = path.split('/')[1]
    repo = path.split('/')[2]

    async with aiohttp.ClientSession() as session:
        embed = await build_embed(session, owner, repo)

    return {'embed': embed}


async def build_embed(session, owner, repo):
    embed = discord.Embed()
    data = await get_raw_data(session, owner, repo)

    embed.title = data['name']
    embed.url = data['svn_url']
    description = data['description']
    if len(description) > 500:
        description = description[:497] + '...'
    embed.description = description
    embed.set_author(name=data['owner']['login'], icon_url=data['owner']['avatar_url'], url=data['owner']['html_url'])
    embed.set_image(url=await get_image(session, data['svn_url']))

    languages = await get_formatted_languages(session, owner, repo)
    embed.add_field(name='Languages', value=languages, inline=True)

    embed.add_field(
        name='Time',
        value='Created <t:{0}:f>\nUpdated <t:{1}:f>'.format(
            iso_to_seconds(data['created_at']), iso_to_seconds(data['updated_at'])
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
            if topics_string > 30:
                topics_string += '...'
                break
            topics_string += '`{0}` '.format(topic)
        embed.description += '\n\n**Topics:** ' + topics_string

    release = await get_recent_release(session, owner, repo)
    if release:
        timestamp = iso_to_seconds(release['created_at'])
        value = '**[{0}]({1})** <t:{2}:f>'.format(release['name'], release['html_url'], timestamp)
        body = release.get('body', None)
        if body:
            if len(body) > 30:
                body = body[:30]
            value += '\n{0}'.format(body)
        embed.add_field(name='Latest Release', value=value, inline=False)

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


def iso_to_seconds(iso):
    date = datetime.datetime.strptime(iso, '%Y-%m-%dT%H:%M:%SZ')
    return int((date - datetime.datetime(1970, 1, 1)).total_seconds())
