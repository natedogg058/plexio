from itertools import chain
from typing import Annotated

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, HTTPException, Request, status
from redis.asyncio.client import Redis
from yarl import URL

from plexio import __version__
from plexio.dependencies import (
    get_addon_configuration,
    get_cache,
    get_http_client,
    set_sentry_user,
)
from plexio.models import PLEX_TO_STREMIO_MEDIA_TYPE, STREMIO_TO_PLEX_MEDIA_TYPE
from plexio.models.addon import AddonConfiguration
from plexio.models.plex import PlexMediaMeta
from plexio.models.stremio import (
    StremioCatalog,
    StremioCatalogManifest,
    StremioManifest,
    StremioMediaType,
    StremioMetaResponse,
    StremioStreamsResponse,
)
from plexio.models.utils import (
    is_rating_key_plexio_id,
    plexio_id_to_guid,
    plexio_id_to_rating_key,
)
from plexio.plex.media_server_api import (
    SORT_OPTIONS,
    get_all_episodes,
    get_media,
    get_media_by_rating_key,
    get_on_deck,
    get_section_media,
    stremio_to_plex_id,
)
from plexio.plex.playback import b64decode_path, proxy_playback
from plexio.settings import settings

router = APIRouter()
router.dependencies.append(Depends(set_sentry_user))

RECENT_SORT = 'Date Added (desc)'


def _public_base_url(request: Request) -> str:
    """Resolve the externally reachable base URL for playback proxy links."""
    if settings.base_url:
        candidate = settings.base_url
    else:
        forwarded_proto = (
            request.headers.get('x-forwarded-proto')
            if settings.trust_proxy_headers
            else None
        )
        forwarded_host = (
            request.headers.get('x-forwarded-host')
            if settings.trust_proxy_headers
            else None
        )
        scheme = (
            forwarded_proto.split(',', 1)[0].strip()
            if forwarded_proto
            else request.url.scheme
        )
        host = (
            forwarded_host.split(',', 1)[0].strip()
            if forwarded_host
            else (
                getattr(request.url, 'netloc', None)
                or getattr(request.url, 'authority', None)
            )
        )
        candidate = f'{scheme}://{host}'

    try:
        public_url = URL(candidate)
    except (TypeError, ValueError):
        public_url = URL()
    if (
        public_url.scheme not in {'http', 'https'}
        or not public_url.host
        or public_url.user is not None
        or public_url.query_string
        or public_url.fragment
    ):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Unable to determine the public Plexio URL',
        )
    return str(public_url).rstrip('/')


def _sections_of_type(configuration, stremio_type):
    return [
        s
        for s in configuration.sections
        if PLEX_TO_STREMIO_MEDIA_TYPE.get(s.type) == stremio_type
    ]


async def _map_on_deck(http, items, configuration, stremio_type):
    """Map raw Plex On Deck items to Stremio catalog metas of one type.

    In-progress movies map directly; on-deck episodes are mapped up to their
    parent series (deduped) so the row shows shows, not loose episodes."""
    configured = {s.key for s in _sections_of_type(configuration, stremio_type)}
    metas = []
    seen = set()
    for item in items:
        section = str(item.get('librarySectionID', ''))
        if configured and section not in configured:
            continue
        if stremio_type == StremioMediaType.movie and item.get('type') == 'movie':
            if not item.get('guid'):
                continue
            metas.append(PlexMediaMeta(**item).to_stremio_meta_review(configuration))
        elif stremio_type == StremioMediaType.series and item.get('type') == 'episode':
            show_guid = item.get('grandparentGuid')
            if not show_guid or show_guid in seen:
                continue
            seen.add(show_guid)
            resolved = await get_media(
                client=http,
                url=configuration.discovery_url,
                token=configuration.access_token,
                guid=show_guid,
                get_only_first=True,
            )
            if resolved:
                metas.append(resolved[0].to_stremio_meta_review(configuration))
            else:
                show = PlexMediaMeta(
                    guid=show_guid,
                    type='show',
                    title=item.get('grandparentTitle', ''),
                    thumb=item.get('grandparentThumb'),
                    librarySectionID=section,
                    addedAt=item.get('addedAt', 0),
                )
                metas.append(show.to_stremio_meta_review(configuration))
    return metas


async def _recently_added(http, configuration, stremio_type, skip):
    """Recently added top-level items across configured sections of a type,
    merged and sorted by date added. Reuses the section-media call with an
    addedAt:desc sort, so it returns movies/shows, never loose episodes."""
    results = []
    for section in _sections_of_type(configuration, stremio_type):
        results.extend(
            await get_section_media(
                client=http,
                url=configuration.discovery_url,
                token=configuration.access_token,
                section_id=section.key,
                search='',
                skip=skip,
                sort=RECENT_SORT,
            )
        )
    results.sort(key=lambda m: m.added_at, reverse=True)
    return [m.to_stremio_meta_review(configuration) for m in results[:100]]


@router.get('/manifest.json', response_model_exclude_none=True)
@router.get('/{session_id}/manifest.json', response_model_exclude_none=True)
@router.get(
    '/{installation_id}/{base64_cfg}/manifest.json', response_model_exclude_none=True
)
async def get_manifest(
    configuration: Annotated[
        AddonConfiguration | None,
        Depends(get_addon_configuration),
    ],
    installation_id: str | None = None,
    session_id: str | None = None,
) -> StremioManifest:
    catalogs = []
    description = 'Play movies and series from plex.tv.'
    name = 'Plexio'

    if configuration is not None:
        has_movie = any(
            PLEX_TO_STREMIO_MEDIA_TYPE.get(s.type) == StremioMediaType.movie
            for s in configuration.sections
        )
        has_series = any(
            PLEX_TO_STREMIO_MEDIA_TYPE.get(s.type) == StremioMediaType.series
            for s in configuration.sections
        )
        hub_extra = [{'name': 'skip', 'isRequired': False}]
        sv = configuration.server_name
        if has_movie:
            catalogs.append(
                StremioCatalogManifest(
                    id='plexio-ondeck',
                    type=StremioMediaType.movie,
                    name=f'Continue Watching - Movies | {sv}',
                    extra=hub_extra,
                ),
            )
        if has_series:
            catalogs.append(
                StremioCatalogManifest(
                    id='plexio-ondeck',
                    type=StremioMediaType.series,
                    name=f'Continue Watching - Shows | {sv}',
                    extra=hub_extra,
                ),
            )
        if has_movie:
            catalogs.append(
                StremioCatalogManifest(
                    id='plexio-recent',
                    type=StremioMediaType.movie,
                    name=f'Recently Added - Movies | {sv}',
                    extra=hub_extra,
                ),
            )
        if has_series:
            catalogs.append(
                StremioCatalogManifest(
                    id='plexio-recent',
                    type=StremioMediaType.series,
                    name=f'Recently Added - Shows | {sv}',
                    extra=hub_extra,
                ),
            )
        for section in configuration.sections:
            catalogs.append(
                StremioCatalogManifest(
                    id=section.key,
                    type=PLEX_TO_STREMIO_MEDIA_TYPE[section.type],
                    name=f'{section.title} | {configuration.server_name}',
                    extra=[
                        {'name': 'skip', 'isRequired': False},
                        {'name': 'search', 'isRequired': False},
                        {'name': 'sort', 'options': list(SORT_OPTIONS.keys())},
                    ],
                ),
            )

        name += f' ({configuration.server_name})'
        description += f' Your installation ID: {installation_id or session_id}'

    return StremioManifest(
        id='com.stremio.plexio',
        version=__version__,
        description=description,
        name=name,
        resources=[
            'stream',
            'catalog',
            {
                'name': 'meta',
                'types': ['movie', 'series'],
                'idPrefixes': ['plexio'],
            },
        ],
        types=[StremioMediaType.movie, StremioMediaType.series],
        catalogs=catalogs,
        idPrefixes=['tt', 'plexio'],
        behaviorHints={
            'configurable': True,
            'configurationRequired': configuration is None,
        },
    )


@router.get(
    '/{session_id}/catalog/{stremio_type}/{catalog_id}.json',
    response_model_exclude_none=True,
)
@router.get(
    '/{session_id}/catalog/{stremio_type}/{catalog_id}/{extra}.json',
    response_model_exclude_none=True,
)
@router.get(
    '/{installation_id}/{base64_cfg}/catalog/{stremio_type}/{catalog_id}.json',
    response_model_exclude_none=True,
)
@router.get(
    '/{installation_id}/{base64_cfg}/catalog/{stremio_type}/{catalog_id}/{extra}.json',
    response_model_exclude_none=True,
)
async def get_catalog(
    http: Annotated[ClientSession, Depends(get_http_client)],
    configuration: Annotated[AddonConfiguration, Depends(get_addon_configuration)],
    stremio_type: StremioMediaType,
    catalog_id: str,
    extra: str = '',
) -> StremioCatalog:
    extras = dict(e.split('=') for e in extra.split('&') if e)
    skip = extras.get('skip', 0)
    if catalog_id == 'plexio-ondeck':
        items = await get_on_deck(
            client=http,
            url=configuration.discovery_url,
            token=configuration.access_token,
        )
        metas = await _map_on_deck(http, items, configuration, stremio_type)
    elif catalog_id == 'plexio-recent':
        metas = await _recently_added(http, configuration, stremio_type, skip)
    else:
        media = await get_section_media(
            client=http,
            url=configuration.discovery_url,
            token=configuration.access_token,
            section_id=catalog_id,
            search=extras.get('search', ''),
            skip=skip,
            sort=extras.get('sort', 'Title'),
        )
        metas = [m.to_stremio_meta_review(configuration) for m in media]
    return StremioCatalog(metas=metas)


@router.get(
    '/{session_id}/meta/{stremio_type}/{plex_id:path}.json',
    response_model_exclude_none=True,
)
@router.get(
    '/{installation_id}/{base64_cfg}/meta/{stremio_type}/{plex_id:path}.json',
    response_model_exclude_none=True,
)
async def get_meta(
    http: Annotated[ClientSession, Depends(get_http_client)],
    configuration: Annotated[AddonConfiguration, Depends(get_addon_configuration)],
    stremio_type: StremioMediaType,
    plex_id: str,
) -> StremioMetaResponse:
    if not plex_id.startswith('plexio:'):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    if is_rating_key_plexio_id(plex_id):
        media = await get_media_by_rating_key(
            client=http,
            url=configuration.discovery_url,
            token=configuration.access_token,
            rating_key=plexio_id_to_rating_key(plex_id),
        )
    else:
        # Backward compatibility for previously generated plexio:<base64-guid>
        # links.
        try:
            guid = plexio_id_to_guid(plex_id)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from None
        media = await get_media(
            client=http,
            url=configuration.discovery_url,
            token=configuration.access_token,
            guid=guid,
            get_only_first=True,
        )
    if not media:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    media = media[0]

    meta = media.to_stremio_meta(configuration)

    if stremio_type == StremioMediaType.series:
        episodes = await get_all_episodes(
            client=http,
            url=configuration.discovery_url,
            token=configuration.access_token,
            key=media.key,
        )
        meta.videos = [e.to_stremio_video_meta(configuration) for e in episodes]
    return StremioMetaResponse(meta=meta)


@router.get(
    '/{session_id}/stream/{stremio_type}/{media_id:path}.json',
    response_model_exclude_none=True,
)
@router.get(
    '/{installation_id}/{base64_cfg}/stream/{stremio_type}/{media_id:path}.json',
    response_model_exclude_none=True,
)
async def get_stream(
    request: Request,
    http: Annotated[ClientSession, Depends(get_http_client)],
    cache: Annotated[Redis, Depends(get_cache)],
    configuration: Annotated[AddonConfiguration, Depends(get_addon_configuration)],
    stremio_type: StremioMediaType,
    media_id: str,
) -> StremioStreamsResponse:
    if media_id.startswith('tt'):
        plex_id = await stremio_to_plex_id(
            client=http,
            url=configuration.discovery_url,
            token=configuration.access_token,
            cache=cache,
            stremio_id=media_id,
            media_type=STREMIO_TO_PLEX_MEDIA_TYPE[stremio_type],
        )
        if not plex_id:
            return StremioStreamsResponse()

        media = await get_media(
            client=http,
            url=configuration.discovery_url,
            token=configuration.access_token,
            guid=plex_id,
        )
    elif is_rating_key_plexio_id(media_id):
        rating_key_value = plexio_id_to_rating_key(media_id)
        parts = rating_key_value.split(':')

        if stremio_type == StremioMediaType.series and len(parts) == 3:
            show_rating_key, season, episode = parts

            shows = await get_media_by_rating_key(
                client=http,
                url=configuration.discovery_url,
                token=configuration.access_token,
                rating_key=show_rating_key,
            )
            if not shows:
                return StremioStreamsResponse()

            show = shows[0]
            episodes = await get_all_episodes(
                client=http,
                url=configuration.discovery_url,
                token=configuration.access_token,
                key=show.key,
            )

            episode_rating_key = next(
                (
                    item.rating_key
                    for item in episodes
                    if str(item.parent_index) == season and str(item.index) == episode
                ),
                None,
            )
            if not episode_rating_key:
                return StremioStreamsResponse()

            media = await get_media_by_rating_key(
                client=http,
                url=configuration.discovery_url,
                token=configuration.access_token,
                rating_key=episode_rating_key,
            )
        else:
            media = await get_media_by_rating_key(
                client=http,
                url=configuration.discovery_url,
                token=configuration.access_token,
                rating_key=rating_key_value,
            )
    elif media_id.startswith('plexio:'):
        # Backward compatibility for legacy GUID-based internal IDs.
        try:
            plex_id = plexio_id_to_guid(media_id)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND) from None
        media = await get_media(
            client=http,
            url=configuration.discovery_url,
            token=configuration.access_token,
            guid=plex_id,
        )
    else:
        media = await get_media(
            client=http,
            url=configuration.discovery_url,
            token=configuration.access_token,
            guid=media_id,
        )
    play_prefix = None
    if configuration.report_playback:
        base = _public_base_url(request)
        cfg_path = request.url.path.split('/stream/')[0]
        play_prefix = f'{base}{cfg_path}/play'
    return StremioStreamsResponse(
        streams=chain.from_iterable(
            meta.get_stremio_streams(configuration, play_prefix) for meta in media
        ),
    )


@router.api_route(
    '/{session_id}/play/{rating_key}/{duration}/{part_b64}',
    methods=['GET', 'HEAD'],
)
@router.api_route(
    '/{installation_id}/{base64_cfg}/play/{rating_key}/{duration}/{part_b64}',
    methods=['GET', 'HEAD'],
)
async def get_play(
    request: Request,
    http: Annotated[ClientSession, Depends(get_http_client)],
    configuration: Annotated[AddonConfiguration, Depends(get_addon_configuration)],
    rating_key: str,
    duration: int,
    part_b64: str,
    session_id: str | None = None,
    installation_id: str | None = None,
):
    if configuration is None or not configuration.report_playback:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return await proxy_playback(
        request,
        client=http,
        configuration=configuration,
        rating_key=rating_key,
        duration_ms=duration,
        part_key=b64decode_path(part_b64),
        identifier=session_id or installation_id or 'plexio',
    )
