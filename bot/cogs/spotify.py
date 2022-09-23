from datetime import datetime

import httpx
import pytz
from discord.ext import commands
import tekore as tk
import bot as bot_global
from bot.core.context import Context
from bot.core.embed import Embed
from bot.util.human import combine_list_and, format_code
from bot.util.time_util import ms_to_time
from bot.util import ansi


class SpotifyCommands(commands.Cog, name='Spotify'):

    def __init__(self, bot):
        self.bot = bot
        self.sp: tk.Spotify = None

    async def cog_load(self) -> None:
        trans = httpx.AsyncHTTPTransport(retries=3)
        client = httpx.AsyncClient(timeout=120, transport=trans)
        sender = tk.CachingSender(512, tk.AsyncSender(client=client))
        token = tk.request_client_token(client_id=bot_global.config['sp_id'], client_secret=bot_global.config['sp_secret'])
        self.sp = tk.Spotify(token=token, sender=sender, chunked_on=True)

    @commands.hybrid_group(name='spotify')
    async def spotify(self, ctx: Context):
        pass

    @spotify.command(name='track')
    async def spotify(self, ctx: Context, *, name: str):
        tracks = await self.sp.search(query=name, limit=1)
        if not tracks:
            await ctx.send("Couldn't find track!", ephemeral=True)
            return
        embed = await self.get_track_embed(tracks[0].id)
        if embed is None:
            await ctx.send("Something went wrong!", ephemeral=True)
            return
        await ctx.send(embed=embed)

    async def get_track_embed(self, track_id):
        try:
            track: tk.model.FullTrack = await self.sp.track(track_id)
            album: tk.model.FullAlbum = await self.sp.album(track.album.id)
            features: tk.model.AudioFeatures = await self.sp.track_audio_features(track_id)
            artist: tk.model.FullArtist = await self.sp.artist(track.artists[0].id)
        except:
            return None

        embed = Embed(inline=True)
        embed.set_title(title=track.name, url=track.external_urls['spotify'])
        embed.set_author(
            url=artist.external_urls['spotify'],
            name=f'{artist.name} · {artist.followers.total} Followers',
            icon_url=artist.images[0].url if len(artist.images) > 0 else None,
        )
        embed.set_thumbnail(url=album.images[0].url if len(album.images) > 0 else None)
        embed.add_field(name='Duration', value=ms_to_time(track.duration_ms))
        embed.add_field(name='Popularity', value=str(track.popularity))
        genres = album.genres if len(album.genres) > 0 else artist.genres
        if genres:
            embed.add_field(name='Genres', value=combine_list_and(genres))
        date = None
        if album.release_date_precision == 'day':
            date = datetime.strptime(album.release_date, '%Y-%m-%d')
        elif album.release_date_precision == 'month':
            date = datetime.strptime(album.release_date, '%Y-%m')
        elif album.release_date_precision == 'day':
            date = datetime.strptime(album.release_date, '%Y-%m-%m')
            date = date.replace(tzinfo=pytz.timezone('UTC'))
        if date is not None:
            embed.timestamp = date

        embed.description = self.get_ansi_block(features)

        embed.set_footer()

        return embed

    def get_ansi_block(self, features: tk.model.AudioFeatures):
        formatted = []
        formatted.append(f'{ansi.RESET}{ansi.format_attributes(ansi.WHITE, ansi.UNDERLINE)}Features')
        formatted.append('')
        features_in = ['acousticness', 'danceability', 'energy', 'instrumentalness', 'liveness', 'speechiness', 'tempo', 'loudness']
        i = 0
        for feature in features_in:
            i += 1
            color = None
            value = getattr(features, feature)
            if feature == 'loudness':
                suffix = ' dB'
            elif feature == 'tempo':
                formatted.append('')
                i += 1
                suffix = ' BMP'
            else:
                # It's percent
                if value < .3:
                    color = ansi.BLUE
                elif value < .7:
                    color = None
                else:
                    color = ansi.PINK
                value = value * 100
                suffix = ' %'
            suffix = ansi.format_attributes(ansi.GRAY) + suffix
            value = '{0:>4.1f}'.format(value).rjust(5)
            formatted.append(
                f'{ansi.RESET}{ansi.format_attributes(ansi.CYAN, ansi.BG_FIREFLY_DARK_BLUE if i % 2 == 0 else None)}'
                f'{format_code(feature):<18} '
                f'{ansi.RESET}{ansi.format_attributes(color, ansi.BG_FIREFLY_DARK_BLUE if i % 2 == 0 else None)}'
                f'{value + suffix:<9}'
            )
        return '```ANSI\n{0}\n```'.format('\n'.join(formatted))


async def setup(bot):
    cog = SpotifyCommands(bot)
    await bot.add_cog(cog)