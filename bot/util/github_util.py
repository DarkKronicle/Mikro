import base64
import datetime
import json
import re
from collections import Counter
from urllib import parse

import aiohttp
from bs4 import BeautifulSoup
import typing

from bot.core.embed import Embed
import bot as bot_global


class GithubClient:

    def __init__(self, owner, repo, url):
        self.embed = Embed()
        self.owner = owner
        self.repo = repo
        self.repo_data = {}
        self.commit_data = {}
        self.url = url
        self.commit = None
        self._session: aiohttp.ClientSession = None

    async def build_blob_embed(self, path, lines):
        await self.build_file_embed(path, blob=True)
        self.embed.title = '{0} {1} from {2}'.format(path[-1], lines, self.repo)
        ref = None
        if len(path[0]) == 40:
            ref = path[0]
        path = path[1:]
        file = path.pop(-1)
        if len(file.split('.')) > 1:
            ext = file.split('.')[1]
        else:
            ext = ''
        nav = '/'.join(path) + '/' + file
        ending = ''
        if ref is not None:
            ending = '?ref={0}'.format(ref)
        file_data = await self.request_file(
            'https://api.github.com/repos/{0}/{1}/contents/{2}'.format(self.owner, self.repo, nav) + ending,
            limit_kb=128
        )
        if file_data is None:
            self.embed.description = 'File too large...'
            return '', self.embed
        raw_text = base64.b64decode(file_data['content']).decode('utf-8').replace(r'\t', '    ')
        if not isinstance(raw_text, str):
            self.embed.description = 'Not a text file'
            return '', self.embed
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
        return content, self.embed

    async def build_file_embed(self, path, blob=False):
        await self.build_embed(use_image=not blob, use_released=False, use_languages=False)
        self.embed.clear_fields()
        self.embed.url = self.url
        self.embed.title = '{0} from {1}'.format(path[-1], self.repo)
        ref = None
        if len(path[0]) == 40:
            ref = path[0]
        path = path[1:]
        quote = parse.quote_plus('/'.join(path))
        if ref:
            ref = '&ref={0}'.format(ref)
        else:
            ref = ''
        data: list[dict] = await self.request(
            'https://api.github.com/repos/{0}/{1}/commits?path={2}&page=1&per_page=1{3}'.format(self.owner, self.repo, quote, ref)
        )
        commit = data[0]['commit']
        self.embed.add_field(name='Updated At', value='<t:{0}:f>'.format(self.iso_to_seconds(commit['committer']['date'])))
        committer = data[0]['committer']
        if committer is not None and isinstance(committer, dict):
            self.embed.set_author(name=committer['login'], icon_url=committer['avatar_url'], url=committer['html_url'])
        self.embed.add_field(name='Message', value=commit['message'])
        return self.embed

    async def build_commit_embed(self, commit):
        self.commit = commit
        await self.build_embed(use_image=False, use_released=False, use_languages=False)
        self.embed.set_image(url=await self.get_image(self.url))
        self.embed.clear_fields()
        self.embed.title = 'Commit {0} at {1}'.format(commit[:8], self.repo)
        self.embed.url = self.url
        commit: dict = await self.get_commit_data()
        files = commit['files']
        statuses = Counter()
        for f in files:
            statuses[f['status']] += 1
        committer = commit['committer']
        if committer is not None and isinstance(committer, dict):
            self.embed.set_author(name=committer['login'], icon_url=committer['avatar_url'], url=committer['html_url'])
        self.embed.set_description(commit['commit']['message'], max_description=1000, truncate_append='...')
        self.embed.add_field(
            name='Stats',
            value='Additions: `{0}`\nDeletions: `{1}`\nTotal: `{2}`'.format(
                commit['stats']['additions'], commit['stats']['deletions'], commit['stats']['total']
            ),
        )
        self.embed.add_field(name='Files',
                             value='\n'.join(['{0}: `{1}`'.format(s.capitalize(), c) for s, c in statuses.items()]))
        self.embed.add_field(name='Updated At',
                             value='<t:{0}:f>'.format(self.iso_to_seconds(commit['commit']['committer']['date'])))
        return self.embed

    async def build_embed(self, *, use_image=True, use_languages=True, use_released=True):
        data: dict = await self.get_repo_data()

        self.embed.title = data['name']
        self.embed.url = data['svn_url']
        self.embed.set_description(data['description'], max_description=500, truncate_append='...')

        owner = data['owner']
        self.embed.set_author(name=owner['login'], icon_url=owner['avatar_url'], url=owner['html_url'])

        if use_image:
            self.embed.set_image(url=await self.get_image(data['svn_url']))

        if use_languages:
            languages = await self.get_formatted_languages()
            self.embed.add_field(name='Languages', value=languages)

        self.embed.add_field(
            name='Time',
            value='Created <t:{0}:f>\nPushed <t:{1}:f>'.format(
                self.iso_to_seconds(data['created_at']), self.iso_to_seconds(data['pushed_at'])
            ),
        )

        license = data.get('license')
        if license:
            name = license.get('name')
            if name:
                self.embed.add_field(name='License', value='[{0}]({1})'.format(license['name'], license['url']),
                                     inline=True)

        self.format_topics()

        if use_released:
            await self.format_recent_release()

        return self.embed

    async def get_commit_data(self):
        self.commit_data = await self.request(
            'https://api.github.com/repos/{0}/{1}/commits/{2}'.format(self.owner, self.repo, self.commit))
        return self.commit_data

    @property
    def session(self):
        if self._session is None:
            raise ValueError('This object has not been entered!')
        return self._session

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(
            auth=aiohttp.BasicAuth(bot_global.config['gh_user'], bot_global.config['gh_token'])
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.session.close()
        return self

    async def request(self, url, *, type='json') -> typing.Union[dict, str, list]:
        async with self.session.get(url) as r:
            if type == 'json':
                return await r.json()
            return await r.text()

    async def request_file(self, url, *, limit_kb=-1):
        i = 0
        result = bytes()
        async with self.session.get(url) as r:
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

    def iso_to_seconds(self, iso):
        date = datetime.datetime.strptime(iso, '%Y-%m-%dT%H:%M:%SZ')
        return int((date - datetime.datetime(1970, 1, 1)).total_seconds())

    def format_topics(self):
        topics = self.repo_data.get('topics')
        if topics:
            topics_string = ''
            for topic in topics:
                if len(topics_string) > 50:
                    topics_string += '...'
                    break
                topics_string += '`{0}` '.format(topic)
            self.embed.description += '\n\n**Topics:** ' + topics_string

    async def get_recent_release(self) -> dict:
        data = await self.request('https://api.github.com/repos/{0}/{1}/releases'.format(self.owner, self.repo))
        if len(data) == 0:
            return None
        return data[0]

    async def format_recent_release(self):
        release = await self.get_recent_release()
        if release:
            timestamp = self.iso_to_seconds(release['created_at'])
            value = '**[{0}]({1})** <t:{2}:f>'.format(release['name'], release['html_url'], timestamp)
            body = release.get('body', None)
            if body:
                if len(body) > 30:
                    body = body[:30]
                value += '\n{0}'.format(body)
            self.embed.add_field(name='Latest Release', value=value, inline=True)

    async def get_image(self, url):
        html = await self.request(url, type='text')
        soup = BeautifulSoup(html, features='html.parser')
        return soup.find('head').find('meta', property='og:image')['content']

    async def get_repo_data(self):
        self.repo_data = await self.request('https://api.github.com/repos/{0}/{1}'.format(self.owner, self.repo))
        return self.repo_data

    async def get_formatted_languages(self):
        languages = await self.get_languages()
        languages_str = ''
        for language, percent in languages.items():
            languages_str += '{percent:.1f}% {language}\n'.format(language=language, percent=percent * 100)
        return languages_str[:-1]

    async def get_languages(self):
        data = await self.request('https://api.github.com/repos/{0}/{1}/languages'.format(self.owner, self.repo))
        total = sum((v for v in data.values()))
        return {k: v / total for k, v in data.items()}
