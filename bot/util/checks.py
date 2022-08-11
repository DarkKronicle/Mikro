from discord.ext import commands
import enum


# https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/utils/checks.py#L11
# MPL-2.0


class FilterType(enum.Enum):

    guild = 0
    channel = 1
    user = 2
    role = 3
    category = 4

    @classmethod
    def from_object(cls, obj):
        if isinstance(obj, (discord.Guild,)):
            return FilterType.guild
        if isinstance(obj, (discord.VoiceChannel, discord.TextChannel, discord.StageChannel)):
            return FilterType.channel
        if isinstance(obj, (discord.User, discord.Member)):
            return FilterType.user
        if isinstance(obj, (discord.Role,)):
            return FilterType.role
        if isinstance(obj, (discord.CategoryChannel,)):
            return FilterType.category

    @classmethod
    def format_type(cls, obj):
        stat_type = FilterType.from_object(obj)
        if stat_type == FilterType.guild:
            return 'Guild {0}'.format(obj.name)
        if stat_type == FilterType.channel:
            return 'Channel {0}'.format(obj.mention)
        if stat_type == FilterType.user:
            return 'User {0}'.format(obj.mention)
        if stat_type == FilterType.role:
            return 'Role {0}'.format(obj.mention)
        if stat_type == FilterType.category:
            return 'Category {0}'.format(obj.name)
        return str(object)


async def check_permissions(ctx, perms, *, check=all, channel=None):
    is_owner = await ctx.bot.is_owner(ctx.author)
    if is_owner:
        return True

    if channel is None:
        channel = ctx.channel
    resolved = channel.permissions_for(ctx.author)
    perms_given = []
    for name, perm in perms.items():
        perms_given.append(getattr(resolved, name, None) == perm)
    return check(perms_given)


async def check_guild_permissions(ctx, perms, *, check=all):
    is_owner = await ctx.bot.is_owner(ctx.author)
    if is_owner:
        return True

    if ctx.guild is None:
        return True

    resolved = ctx.author.guild_permissions
    perms_given = []
    for name, perm in perms.items():
        perms_given.append(getattr(resolved, name, None) == perm)
    return check(perms_given)


async def get_command_config(ctx):
    cog = ctx.bot.get_config('CommandSettings')
    if cog is None:
        return None
    return await cog.get_command_config(ctx.guild.id)


async def raw_is_admin_or_perms(ctx):
    if ctx.guild is None:
        return True
    allowed = await check_guild_permissions(ctx, {'administrator': True})
    if allowed:
        return allowed
    return False


def is_admin_or_perms():
    async def predicate(ctx):   # noqa: WPS430
        return await raw_is_admin_or_perms(ctx)

    return commands.check(predicate)


async def raw_is_admin(ctx):
    if ctx.guild is None:
        return True
    return await check_guild_permissions(ctx, {'administrator': True})


def is_admin():
    async def predicate(ctx):
        return await raw_is_admin(ctx)

    return commands.check(predicate)


async def raw_is_manager_or_perms(ctx):
    if ctx.guild is None:
        return True
    if await raw_is_admin_or_perms(ctx):
        return True
    allowed = await check_guild_permissions(ctx, {'manage_server': True})
    if allowed:
        return allowed
    return False


def is_manager_or_perms():
    async def predicate(ctx):   # noqa: WPS430
        return await raw_is_manager_or_perms(ctx)

    return commands.check(predicate)


async def raw_is_manager(ctx):
    if ctx.guild is None:
        return True
    if await raw_is_admin(ctx):
        return True
    return await check_guild_permissions(ctx, {'manage_server': True})


def is_manager():
    async def predicate(ctx):   # noqa: WPS430
        return await raw_is_manager(ctx)

    return commands.check(predicate)


def guild(*args):
    async def predicate(ctx):   # noqa: WPS430
        if ctx.guild is None:
            return False
        return ctx.guild.id in args

    return commands.check(predicate)


def owner_or(*args):
    async def predicate(ctx):   # noqa: WPS430
        if ctx.author.id in args:
            return True
        return await ctx.bot.is_owner(ctx.author)

    return commands.check(predicate)