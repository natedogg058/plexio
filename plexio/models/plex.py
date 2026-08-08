import os
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from plexio.models.utils import (
    get_flag_emoji,
    guid_to_plexio_id,
    rating_key_to_plexio_id,
    to_camel,
)


class Resolution(str, Enum):
    R480 = '480p'
    R720 = '720p'
    R1080 = '1080p'


RESOLUTION_QUALITY_PARAMS = {
    Resolution.R1080: {
        'name': '1080p',
        'min_width': 1920,
        'plex_args': {
            'videoQuality': 100,
            'maxVideoBitrate': 10,
            'videoResolution': '1920x1080',
        },
    },
    Resolution.R720: {
        'name': '720p',
        'min_width': 1280,
        'plex_args': {
            'videoQuality': 100,
            'maxVideoBitrate': 6.5,
            'videoResolution': '1280x720',
        },
    },
    Resolution.R480: {
        'name': '480p',
        'min_width': 640,
        'plex_args': {
            'videoQuality': 100,
            'maxVideoBitrate': 3.5,
            'videoResolution': '640×480',
        },
    },
}


def _external_subtitles(subtitle_streams, base_url, access_token):
    return [
        {
            'id': str(stream['id']),
            'lang': stream['displayTitle'],
            'url': str(base_url / stream['key'][1:] % {'X-Plex-Token': access_token}),
        }
        for stream in subtitle_streams
    ]


class PlexMediaType(str, Enum):
    show = 'show'
    movie = 'movie'
    episode = 'episode'


class PlexLibrarySection(BaseModel):
    key: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    type: PlexMediaType


class PlexMediaMeta(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)

    guid: str
    type: PlexMediaType
    title: str
    added_at: int = 0

    rating_key: str | None = None
    key: str | None = None
    studio: str | None = None
    title_sort: str | None = None
    library_section_title: str | None = None
    library_sectionID: str | None = None
    library_section_key: str | None = None
    content_rating: str | None = None
    summary: str = ''
    rating: float | None = None
    audience_rating: float | None = None
    year: int | None = None
    tagline: str | None = None
    thumb: str | None = None
    art: str | None = None
    duration: int | None = None
    originally_available_at: str | None = None
    updated_at: int | None = None
    audience_rating_image: str | None = None
    has_premium_primary_extra: str | None = None
    rating_image: str | None = None
    media: list = Field(alias='Media', default_factory=list)
    genre: list = Field(alias='Genre', default_factory=list)
    country: list = Field(alias='Country', default_factory=list)
    guids: list = Field(alias='Guid', default_factory=list)
    ratings: list = Field(alias='Ratings', default_factory=list)
    director: list = Field(alias='Director', default_factory=list)
    writer: list = Field(alias='Writer', default_factory=list)
    role: list = Field(alias='Role', default_factory=list)
    producer: list = Field(alias='Producer', default_factory=list)

    def get_year(self):
        if self.year:
            return str(self.year)
        return datetime.fromtimestamp(self.added_at).strftime('%Y')

    def to_stremio_meta(self, configuration):
        from plexio.models import PLEX_TO_STREMIO_MEDIA_TYPE
        from plexio.models.stremio import StremioMeta

        return StremioMeta(
            id=(
                rating_key_to_plexio_id(self.rating_key)
                if self.rating_key
                else guid_to_plexio_id(self.guid)
            ),
            type=PLEX_TO_STREMIO_MEDIA_TYPE[self.type],
            name=self.title,
            releaseInfo=self.get_year(),
            imdbRating=self.audience_rating,
            description=self.summary,
            poster=str(
                configuration.streaming_url
                / self.thumb[1:]
                % {'X-Plex-Token': configuration.access_token},
            )
            if self.thumb
            else None,
            background=str(
                configuration.streaming_url
                / (self.art or self.thumb)[1:]
                % {'X-Plex-Token': configuration.access_token},
            )
            if (self.art or self.thumb)
            else None,
            genres=[g['tag'] for g in self.genre],
        )

    def to_stremio_meta_review(self, configuration):
        from plexio.models import PLEX_TO_STREMIO_MEDIA_TYPE
        from plexio.models.stremio import StremioMetaPreview

        # Prefer IMDb when Plex has a valid IMDb GUID. This lets Fusion and
        # other metadata addons provide their normal metadata while Plexio
        # continues to resolve streams through its IMDb matching path.
        stremio_id = next(
            (
                guid.get('id', '')[7:]
                for guid in self.guids
                if guid.get('id', '').startswith('imdb://')
            ),
            None,
        )

        # Personal, unmatched and custom-agent media without IMDb metadata
        # use a Plex-native rating-key ID and Plexio's own metadata endpoint.
        if not stremio_id:
            if self.rating_key:
                stremio_id = rating_key_to_plexio_id(self.rating_key)
            elif '://' in self.guid:
                stremio_id = guid_to_plexio_id(self.guid)
            else:
                stremio_id = self.guid

        return StremioMetaPreview(
            id=stremio_id,
            name=self.title,
            releaseInfo=str(self.year),
            poster=str(
                configuration.streaming_url
                / self.thumb[1:]
                % {'X-Plex-Token': configuration.access_token},
            )
            if self.thumb
            else None,
            type=PLEX_TO_STREMIO_MEDIA_TYPE[self.type],
            imdbRating=self.audience_rating,
            description=self.summary,
            genres=[g['tag'] for g in self.genre],
        )

    def get_stremio_streams(self, configuration, play_prefix=None):  # noqa: C901
        import base64

        from plexio.models.stremio import StremioStream

        streams = []
        for i, media in enumerate(self.media):
            name = f'{configuration.server_name} {self.library_section_title}'
            filename = os.path.basename(media['Part'][0]['file'])
            video_size = media['Part'][0].get('size')

            audio_languages = set()
            subtitles_languages = set()
            subtitle_streams = []
            for part_stream in media['Part'][0].get('Stream', []):
                if part_stream['streamType'] == 2:
                    audio_languages.add(
                        get_flag_emoji(part_stream.get('languageTag', 'Unknown')),
                    )
                elif part_stream['streamType'] == 3:
                    subtitles_languages.add(
                        get_flag_emoji(part_stream.get('languageTag', 'Unknown')),
                    )
                    if 'key' in part_stream:
                        subtitle_streams.append(part_stream)

            description_template = '{filename}\n{quality}\n{languages}'
            languages = '/'.join(sorted(audio_languages))
            if subtitles_languages:
                languages += f' ({"/".join(sorted(subtitles_languages))})'

            if getattr(configuration, 'include_direct_play', True):
                connections = getattr(
                    configuration,
                    'direct_play_connections',
                    [(configuration.streaming_url, None)],
                )
                for connection_index, (stream_base, connection_kind) in enumerate(
                    connections
                ):
                    kind_label = getattr(
                        connection_kind,
                        'value',
                        'remote',
                    ).capitalize()
                    if play_prefix:
                        if connection_index > 0:
                            break
                        rk = self.key.rsplit('/', 1)[-1]
                        pk = (
                            base64.urlsafe_b64encode(media['Part'][0]['key'].encode())
                            .rstrip(b'=')
                            .decode()
                        )
                        direct_play_url = (
                            f'{play_prefix}/{rk}/'
                            f'{self.duration or media.get("duration") or 0}/{pk}'
                        )
                        connection_label = (
                            'Automatic connection fallback'
                            if len(connections) > 1
                            else kind_label
                        )
                    else:
                        direct_play_url = str(
                            stream_base
                            / media['Part'][0]['key'][1:]
                            % {'X-Plex-Token': configuration.access_token},
                        )
                        connection_label = (
                            f'Primary {kind_label}'
                            if connection_index == 0
                            else f'Alternate {kind_label}'
                        )
                    quality_description = (
                        f'Direct Play {media.get("videoResolution", "")} '
                        f'· {connection_label}'
                    )
                    streams.append(
                        StremioStream(
                            name=name,
                            description=description_template.format(
                                filename=filename,
                                quality=quality_description,
                                languages=languages,
                            ),
                            url=direct_play_url,
                            subtitles=_external_subtitles(
                                subtitle_streams,
                                stream_base,
                                configuration.access_token,
                            ),
                            behaviorHints={
                                'bingeGroup': quality_description,
                                'filename': filename,
                                'videoSize': video_size,
                            },
                        ),
                    )

            transcode_url = (
                configuration.streaming_url
                / 'video/:/transcode/universal/start.m3u8'
                % {
                    'path': self.key,
                    'mediaIndex': i,
                    'protocol': 'hls',
                    'fastSeek': 1,
                    'copyts': 1,
                    'autoAdjustQuality': 0,
                    'X-Plex-Platform': 'Chrome',
                    'X-Plex-Token': configuration.access_token,
                }
            )
            if configuration.include_transcode_original:
                quality_description = (
                    f'Transcode {media.get("videoResolution", "")} (original)'
                )
                streams.append(
                    StremioStream(
                        name=name,
                        description=description_template.format(
                            filename=filename,
                            quality=quality_description,
                            languages=languages,
                        ),
                        url=str(transcode_url % {'videoQuality': 100}),
                        subtitles=_external_subtitles(
                            subtitle_streams,
                            configuration.streaming_url,
                            configuration.access_token,
                        ),
                        behaviorHints={
                            'bingeGroup': quality_description,
                            'filename': filename,
                            'videoSize': video_size,
                        },
                    ),
                )

            if configuration.include_transcode_down:
                for quality in configuration.transcode_down_qualities:
                    quality_params = RESOLUTION_QUALITY_PARAMS[quality]
                    if media['width'] <= quality_params['min_width']:
                        continue
                    quality_description = f'Transcode {quality_params["name"]}'
                    streams.append(
                        StremioStream(
                            name=name,
                            description=description_template.format(
                                filename=filename,
                                quality=quality_description,
                                languages=languages,
                            ),
                            url=str(transcode_url % quality_params['plex_args']),
                            subtitles=_external_subtitles(
                                subtitle_streams,
                                configuration.streaming_url,
                                configuration.access_token,
                            ),
                            behaviorHints={
                                'bingeGroup': quality_description,
                                'filename': filename,
                                'videoSize': video_size,
                            },
                        ),
                    )

            if configuration.include_plex_tv and self.guid.startswith('plex:'):
                streams.append(
                    StremioStream(
                        name=name,
                        description='Open on plex.tv (external)',
                        externalUrl=f'https://app.plex.tv/#!/provider/tv.plex.provider.metadata/details?key=/library/metadata/{self.guid.split("/")[-1]}',
                    ),
                )

        return streams


class PlexEpisodeMeta(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)

    guid: str
    title: str
    index: int
    parent_index: int = 0
    added_at: int = 0

    type: str | None = None
    rating_key: str | None = None
    key: str | None = None
    parent_rating_key: str | None = None
    grandparent_rating_key: str | None = None
    studio: str | None = None
    grandparent_key: str | None = None
    parent_key: str | None = None
    grandparent_title: str | None = None
    parent_title: str | None = None
    content_rating: str | None = None
    summary: str = ''
    year: int | None = None
    thumb: str | None = None
    art: str | None = None
    parent_thumb: str | None = None
    grandparent_thumb: str | None = None
    grandparent_art: str | None = None
    grandparent_theme: str | None = None
    duration: int | None = None
    originally_available_at: str | None = None
    updated_at: int | None = None
    media: list = Field(default_factory=list)

    def to_stremio_video_meta(self, configuration):
        from plexio.models.stremio import StremioVideoMeta

        if self.originally_available_at:
            released = f'{self.originally_available_at}T00:00:00.000Z'
        else:
            released = datetime.fromtimestamp(self.added_at).strftime(
                '%Y-%m-%dT%H:%M:%S.%fZ',
            )

        return StremioVideoMeta(
            id=(
                rating_key_to_plexio_id(self.rating_key)
                if self.rating_key
                else guid_to_plexio_id(self.guid)
            ),
            title=self.title,
            released=released,
            thumbnail=str(
                configuration.streaming_url
                / self.thumb[1:]
                % {'X-Plex-Token': configuration.access_token},
            )
            if self.thumb
            else None,
            episode=self.index,
            season=self.parent_index,
            overview=self.summary,
        )
