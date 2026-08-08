import asyncio
import hashlib
from http import HTTPStatus

from aiohttp import ClientConnectorError, ClientSession
from yarl import URL

from plexio.models.plex import (
    PlexEpisodeMeta,
    PlexMediaMeta,
    PlexMediaType,
)
from plexio.plex.utils import get_json
from plexio.settings import settings
from plexio.stream_cache import cached_model_list, resource_cache_key

SORT_OPTIONS = {
    'Title': 'title',
    'Title (desc)': 'title:desc',
    'Year': 'year',
    'Year (desc)': 'year:desc',
    'Release Date': 'originallyAvailableAt',
    'Release Date (desc)': 'originallyAvailableAt:desc',
    'Critic Rating': 'rating',
    'Critic Rating (desc)': 'rating:desc',
    'Audience Rating': 'audienceRating',
    'Audience Rating (desc)': 'audienceRating:desc',
    'Rating': 'userRating',
    'Rating (desc)': 'userRating:desc',
    'Content Rating': 'contentRating',
    'Content Rating (desc)': 'contentRating:desc',
    'Duration': 'duration',
    'Duration (desc)': 'duration:desc',
    'Progress': 'viewOffset',
    'Progress (desc)': 'viewOffset:desc',
    'Plays': 'viewCount',
    'Plays (desc)': 'viewCount:desc',
    'Date Added': 'addedAt',
    'Date Added (desc)': 'addedAt:desc',
    'Date Viewed': 'lastViewedAt',
    'Date Viewed (desc)': 'lastViewedAt:desc',
    'ResolutionSelected': 'mediaHeight',
    'ResolutionSelected (desc)': 'mediaHeight:desc',
    'Bitrate': 'mediaBitrate',
    'Bitrate (desc)': 'mediaBitrate:desc',
    'Randomly': 'random',
}


async def check_server_connection(
    *,
    client: ClientSession,
    url: URL,
    token: str,
) -> bool:
    try:
        async with client.get(
            url,
            params={
                'X-Plex-Token': token,
            },
            timeout=settings.plex_requests_timeout,
            allow_redirects=False,
        ) as response:
            if response.status != HTTPStatus.OK:
                return False
            return True
    except (TimeoutError, ClientConnectorError):
        return False


async def get_section_media(
    *,
    client: ClientSession,
    url: URL,
    token: str,
    section_id: str,
    skip: int,
    search: str,
    sort: str,
) -> list[PlexMediaMeta]:
    params = {
        'includeGuids': 1,
        'X-Plex-Container-Start': skip,
        'X-Plex-Container-Size': 100,
        'X-Plex-Token': token,
    }
    if search:
        params['title'] = search
    if sort:
        params['sort'] = SORT_OPTIONS[sort]
    json = await get_json(
        client=client,
        url=url / 'library/sections' / section_id / 'all',
        params=params,
    )
    metadata = json['MediaContainer'].get('Metadata', [])
    return [PlexMediaMeta(**meta) for meta in metadata]


async def get_collection_media(
    *,
    client: ClientSession,
    url: URL,
    token: str,
    rating_key: str,
    skip: int,
) -> list[PlexMediaMeta]:
    json = await get_json(
        client=client,
        url=url / 'library/collections' / rating_key / 'items',
        params={
            'includeGuids': 1,
            'X-Plex-Container-Start': skip,
            'X-Plex-Container-Size': 100,
            'X-Plex-Token': token,
        },
    )
    metadata = json['MediaContainer'].get('Metadata', [])
    media = []
    seen = set()
    for item in metadata:
        if item.get('type') not in {'movie', 'show'}:
            continue
        identity = str(item.get('ratingKey') or item.get('guid') or '')
        if not identity or identity in seen:
            continue
        seen.add(identity)
        media.append(PlexMediaMeta(**item))
    return media


async def get_on_deck(
    *,
    client: ClientSession,
    url: URL,
    token: str,
) -> list[dict]:
    """Return raw On Deck (continue watching / next up) items from Plex.

    A mix of in-progress movies and next-up/in-progress episodes; the caller
    maps them to Stremio catalog metas (episodes -> their parent series)."""
    json = await get_json(
        client=client,
        url=url / 'library/onDeck',
        params={
            'includeGuids': 1,
            'X-Plex-Token': token,
        },
    )
    return json['MediaContainer'].get('Metadata', [])


def _server_cache_namespace(url: URL, token: str) -> str:
    return hashlib.sha256(f'{url}\0{token}'.encode()).hexdigest()


async def _fetch_media_by_rating_key(
    *,
    client: ClientSession,
    url: URL,
    token: str,
    rating_key: str,
) -> list[PlexMediaMeta]:
    json = await get_json(
        client=client,
        url=url / 'library/metadata' / rating_key,
        params={
            'X-Plex-Token': token,
            'includeElements': 'Stream',
            'includeGuids': 1,
        },
    )
    metadata = json['MediaContainer'].get('Metadata', [])
    return [
        PlexMediaMeta(**item)
        for item in metadata
        if item.get('type') in ('show', 'movie', 'episode')
    ]


async def get_media_by_rating_key(
    *,
    client: ClientSession,
    url: URL,
    token: str,
    rating_key: str,
    cache=None,
    cache_namespace: str | None = None,
) -> list[PlexMediaMeta]:
    namespace = cache_namespace or _server_cache_namespace(url, token)
    key = resource_cache_key(namespace, 'media-rating-key', str(rating_key))
    media, _ = await cached_model_list(
        cache=cache,
        key=key,
        model=PlexMediaMeta,
        loader=lambda: _fetch_media_by_rating_key(
            client=client,
            url=url,
            token=token,
            rating_key=rating_key,
        ),
        ttl=settings.plex_metadata_cache_ttl,
    )
    return media


async def get_media(
    *,
    client: ClientSession,
    url: URL,
    token: str,
    guid: str,
    get_only_first=False,
    cache=None,
    cache_namespace: str | None = None,
) -> list[PlexMediaMeta]:
    async def load() -> list[PlexMediaMeta]:
        json = await get_json(
            client=client,
            url=url / 'library/all',
            params={
                'guid': guid,
                'X-Plex-Token': token,
            },
        )
        sections = [
            section
            for section in json['MediaContainer'].get('Metadata', [])
            if section.get('type') in ('show', 'movie', 'episode')
        ]
        if get_only_first:
            sections = sections[:1]
        groups = await asyncio.gather(
            *(
                _fetch_media_by_rating_key(
                    client=client,
                    url=url,
                    token=token,
                    rating_key=section['ratingKey'],
                )
                for section in sections
            )
        )
        return [media for group in groups for media in group]

    namespace = cache_namespace or _server_cache_namespace(url, token)
    key = resource_cache_key(
        namespace,
        'media-guid-first' if get_only_first else 'media-guid',
        guid,
    )
    media, _ = await cached_model_list(
        cache=cache,
        key=key,
        model=PlexMediaMeta,
        loader=load,
        ttl=settings.plex_metadata_cache_ttl,
    )
    return media


async def get_all_episodes(
    *,
    client: ClientSession,
    url: URL,
    token: str,
    key: str,
    cache=None,
    cache_namespace: str | None = None,
) -> list[PlexEpisodeMeta]:
    async def load() -> list[PlexEpisodeMeta]:
        json = await get_json(
            client=client,
            url=str(url / key[1:]).replace('/children', '/allLeaves'),
            params={
                'X-Plex-Token': token,
            },
        )
        metadata = json['MediaContainer'].get('Metadata', [])
        episodes = []
        for i, meta in enumerate(metadata):
            meta.setdefault('index', i)
            episodes.append(PlexEpisodeMeta(**meta))
        return episodes

    namespace = cache_namespace or _server_cache_namespace(url, token)
    cache_key = resource_cache_key(namespace, 'episodes', key)
    episodes, _ = await cached_model_list(
        cache=cache,
        key=cache_key,
        model=PlexEpisodeMeta,
        loader=load,
        ttl=settings.plex_metadata_cache_ttl,
    )
    return episodes


async def imdb_to_plex_id(
    *,
    client: ClientSession,
    imdb_id: str,
    media_type: PlexMediaType,
    token: str,
) -> str:
    json = await get_json(
        client=client,
        url='https://metadata.provider.plex.tv/library/metadata/matches',
        params={
            'X-Plex-Token': settings.plex_matching_token or token,
            'type': 1 if media_type is PlexMediaType.movie else 2,
            'title': f'imdb-{imdb_id}',
            'guid': f'com.plexapp.agents.imdb://{imdb_id}?lang=en',
        },
    )
    media_container = json['MediaContainer']
    if media_container['totalSize']:
        return media_container['Metadata'][0]['guid']


async def get_episode_guid(
    *,
    client: ClientSession,
    url: URL,
    token: str,
    show_guid: str,
    season: str,
    episode: str,
    cache=None,
    cache_namespace: str | None = None,
) -> str:
    all_episodes = await get_all_episodes(
        client=client,
        url=url,
        token=token,
        key=show_guid,
        cache=cache,
        cache_namespace=cache_namespace,
    )
    for metadata in all_episodes:
        if str(metadata.parent_index) == season and str(metadata.index) == episode:
            return metadata.guid


async def stremio_to_plex_id(
    *,
    client: ClientSession,
    url: URL,
    token: str,
    cache,
    stremio_id: str,
    media_type: PlexMediaType,
    cache_namespace: str | None = None,
) -> str | None:
    namespace = cache_namespace or _server_cache_namespace(url, token)
    match_key = resource_cache_key(namespace, 'match', stremio_id)
    if cached_plex_id := await cache.get(match_key):
        return cached_plex_id

    if media_type == PlexMediaType.show:
        id_season_episode = stremio_id.split(':')
        if len(id_season_episode) != 3:
            return None
        imdb_id, season, episode = id_season_episode
    else:
        imdb_id = stremio_id

    plex_id = await imdb_to_plex_id(
        client=client,
        imdb_id=imdb_id,
        media_type=media_type,
        token=token,
    )
    if not plex_id:
        return None

    if media_type == PlexMediaType.show:
        media = await get_media(
            client=client,
            url=url,
            token=token,
            guid=plex_id,
            cache=cache,
            cache_namespace=namespace,
        )
        for meta in media:
            plex_id = await get_episode_guid(
                client=client,
                url=url,
                token=token,
                show_guid=meta.key,
                season=season,
                episode=episode,
                cache=cache,
                cache_namespace=namespace,
            )
            if plex_id:
                break
        else:
            return None

    if plex_id:
        await cache.set(
            match_key,
            plex_id,
            ttl=settings.plex_match_cache_ttl,
        )
    return plex_id
