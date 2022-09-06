import discord
import typing
from functools import wraps
import re
from collections import defaultdict


def build_dict(messages: list[discord.Message], *, loose=False, depth=-1) -> dict[int, list[discord.Message]]:
    pairs = defaultdict(list)
    last_found = None
    d = depth
    for m in messages:
        if m.reference is not None:
            found = next((s for s in messages if s.id == m.reference.message_id), None)
            if found is not None:
                pairs[found.id].append(m)
                last_found = found.id
                d = depth
        else:
            if d == 0:
                continue
            d = d - 1
            if loose and last_found is not None:
                pairs[last_found].append(m)
                last_found = m.id
    return pairs


def get_referenced_from(reference: int, message_dict: dict[int, list[discord.Message]]) -> typing.Optional[int]:
    for key, value in message_dict.items():
        found = next((s for s in value if s.id == reference), None)
        if found is not None:
            return key
    return None


def get_first_referenced(reference: int, message_dict: dict[int, list[discord.Message]]) -> int:
    found = get_referenced_from(reference, message_dict)
    f = None
    while found is not None:
        f = found
        found = get_referenced_from(found, message_dict)
    return f


def extend_all(reference: int, message_dict: dict[int, list[discord.Message]], arr: list[discord.Message], depth=-1, orig_depth=-1) -> None:
    if depth == 0:
        return
    for r in message_dict[reference]:
        is_in = next((s for s in arr if s.id == r.id), None)
        if is_in:
            continue
        arr.append(r)
        if r.reference is not None:
            depth = orig_depth
        extend_all(r.id, message_dict, arr, depth - 1, orig_depth)


def ensure_webhook(func):
    @wraps(func)
    async def wrapped(self, *args, **kwargs):
        await self.setup_webhook()
        return await func(self, *args, **kwargs)
    return wrapped


def get_name(content):
    content = content.replace('[', '').replace(']', '')
    data = re.split(r'\s', content)
    if len(data) > 5:
        data = data[:5]
    data = ' '.join(data)
    if len(data) > 30:
        data = data[:30]
    return data


class Webhooker:

    def __init__(self, channel: discord.TextChannel):
        self.webhook: discord.Webhook = None
        self.channel = channel

    async def setup_webhook(self):
        if self.webhook is not None:
            return
        webhooks = await self.channel.webhooks()
        for webhook in webhooks:
            if webhook.name == 'Mikro Sender':
                self.webhook = webhook
                return
        self.webhook = await self.channel.create_webhook(name='Mikro Sender')

    async def send_message(self, message: discord.Message, *, thread=None, **kwargs) -> typing.Optional[discord.WebhookMessage]:
        files = []
        for attachment in message.attachments:
            files.append(await attachment.to_file())
        if thread is None:
            thread = discord.utils.MISSING
        return await self.mimic_user(
            member=message.author,
            content=message.content,
            embeds=message.embeds,
            allowed_mentions=discord.AllowedMentions.none(),
            thread=thread,
            files=files,
            **kwargs,
        )

    @ensure_webhook
    async def mimic_user(self, member: discord.Member, **kwargs) -> typing.Optional[discord.WebhookMessage]:
        new_kwargs = {}
        for key, value in kwargs.items():
            if value is not None:
                if isinstance(value, str) and len(value) == 0:
                    continue
                new_kwargs[key] = value
        return await self.webhook.send(
            username=member.display_name,
            avatar_url=member.display_avatar.url,
            **new_kwargs,
        )

    async def get_reply_chain(self, message: discord.Message, *, loose=False, lookback=80, depth=-1, build_depth=-1):
        if message.reference is None:
            return [message]
        if isinstance(message, discord.PartialMessage):
            message = await message.fetch()
        messages = [message]
        async for m in message.channel.history(limit=lookback, before=message, oldest_first=False):
            messages.append(m)
        messages.reverse()
        replied = build_dict(messages, loose=loose, depth=build_depth)
        if message.reference.message_id not in replied:
            return [message]

        first = get_first_referenced(message.id, replied)
        all_replied: list[discord.Message] = [next(mes for mes in messages if mes.id == first)]
        extend_all(first, replied, all_replied, depth=depth, orig_depth=depth)
        all_replied.sort(key=lambda x: x.created_at)
        return all_replied

    @ensure_webhook
    async def create_thread_with_messages(self, messages: list[discord.Message], *, creator: discord.Member = None, interaction: discord.Interaction = None):
        if creator is None:
            creator = messages[0].author
        embed = discord.Embed(
            description="{0} Pulled {1} messages starting from **[here]({2})**".format(
                creator.mention,
                len(messages),
                messages[0].jump_url),
            timestamp=messages[0].created_at,
        )
        embed.set_author(icon_url=creator.display_avatar.url, name='Requested by {0}'.format(creator.display_name))
        # Send through channel so we get good-looking message
        if interaction is not None:
            m = await interaction.edit_original_response(embed=embed)
        else:
            m = await self.channel.send(embed=embed)
        name = messages[0].content
        if not name:
            name = 'Blank'
        thread = await m.create_thread(name=get_name(name))
        for mes in messages:
            await self.send_message(mes, thread=thread)

