from . import *


@custom_response(parse.ParseResult)
async def spotify(bot, content: parse.ParseResult):
    if content.netloc != 'open.spotify.com':
        return None
    path = content.path
    if not path:
        return None
    parts = path.split('/')
    if len(parts) < 2:
        # Not a repo
        return None
    if parts[1] == 'track':
        embed = await bot.get_cog('Spotify').get_track_embed(parts[-1])
        if embed is None:
            return None
        return {'embed': embed, 'suppress': False}
