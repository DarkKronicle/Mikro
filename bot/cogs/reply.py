import discord
from discord.ext import commands
from discord import app_commands
import re
import typing


MESSAGE_REGEX = r'http(?:s?):\/\/(?:(?:canary\.)|(?:ptb\.))?discord\.com\/channels\/(\d+)\/(\d+)\/(\d+)(?:\/?)'


class Reply(commands.Cog):

    def __init__(self, bot):
        self.bot: commands.Bot = bot

    @commands.hybrid_group(name='reply')
    async def reply(self, ctx: commands.Context, *, content: discord.Message):
        await ctx.defer(ephemeral=True)
        kwargs = await self.get_found_message(ctx.message, re.match(MESSAGE_REGEX, content.jump_url, re.RegexFlag.MULTILINE), reply=False)
        if kwargs is not None:
            await ctx.send(**kwargs)
        else:
            await ctx.send("Couldn't find message!")

    @reply.command(name='message', description='Reply to a message link')
    async def reply_message(self, ctx: commands.Context, *, content: discord.Message):
        await ctx.defer()
        kwargs = await self.get_found_message(ctx.message, re.match(MESSAGE_REGEX, content.jump_url, re.RegexFlag.MULTILINE), reply=False)
        if isinstance(kwargs, dict):
            await ctx.send(**kwargs)
        else:
            await ctx.send(kwargs)

    @reply.command(name='channel', description='Reply to the most recent message in a channel')
    async def reply_channel(self, ctx: commands.Context, *, channel: discord.TextChannel):
        await ctx.defer()
        message = None
        async for mes in channel.history(limit=1, oldest_first=False):
            message = mes
            break
        kwargs = await self.get_found_message(ctx.message, re.match(MESSAGE_REGEX, message.jump_url, re.RegexFlag.MULTILINE), reply=False)
        if isinstance(kwargs, dict):
            await ctx.send(**kwargs)
        else:
            await ctx.send(kwargs)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.content.startswith('&'):
            return
        matches = list(re.finditer(MESSAGE_REGEX, message.content, re.RegexFlag.MULTILINE))
        if not matches:
            return
        delete = len(matches) == 1 and len(message.content.strip()) == len(matches[0].group(0))
        for match in matches:
            kwargs = await self.get_found_message(message, match, reply=not delete)
            if not isinstance(kwargs, dict):
                delete = False
            else:
                await message.channel.send(**kwargs)
        if delete:
            await message.delete()

    async def get_found_message(self, message: discord.Message, match, *, reply=True):
        if message.guild is None or message.guild.id != int(match.group(1)):
            return "Message not in same guild!"
        channel = message.guild.get_channel(int(match.group(2)))
        if channel is None:
            return "Channel was not found!"
        if channel.is_nsfw() and not message.channel.is_nsfw():
            return "NSFW post cannot go to non NSFW!"
        perms: discord.Permissions = channel.permissions_for(message.author)
        if not perms.view_channel or not perms.read_message_history:
            return "You don't have permission for that!"
        return await self.create_message_context(message, await channel.fetch_message(int(match.group(3))), reply=reply)

    async def create_message_context(self, message: discord.Message, original: discord.Message, *, reply=True):
        content = original.content
        if len(content) == 0:
            if len(original.embeds) == 0:
                content = '*[Blank]*'
            else:
                em = original.embeds[0]
                if em.title:
                    content = '__**{0}**__\n'.format(em.title)
                content = content + em.description
        if len(content) > 500:
            content = content[:497] + '...'
        content = '**[Link from:]({0})** {1}'.format(original.jump_url, content)
        embed = discord.Embed(
            description=content,
        )
        embed.set_author(
            name=original.author.display_name,
            url=original.jump_url,
            icon_url=original.author.display_avatar.url
        )
        if len(original.attachments) > 0:
            for attach in original.attachments:
                if attach.content_type.startswith('image'):
                    embed.set_image(url=attach.url)
        embed.set_footer(text='From #{0} requested by {1}'.format(
            original.channel.name,
            message.author.display_name),
            icon_url=message.author.display_avatar.url,
        )
        embed.timestamp = original.created_at
        reference = message
        if not reply:
            reference = None
        return {'embed': embed, 'reference': reference, 'allowed_mentions': discord.AllowedMentions.none()}


async def setup(bot):
    await bot.add_cog(Reply(bot))
