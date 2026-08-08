import asyncio
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from fastapi import Response
from yarl import URL

from plexio.cache import MemoryCache
from plexio.models.addon import AddonConfiguration
from plexio.models.plex import PlexMediaMeta
from plexio.models.stremio import (
    StremioMediaType,
    StremioStream,
    StremioStreamsResponse,
)
from plexio.plex.media_server_api import get_media
from plexio.routers.addon import get_stream
from plexio.stream_cache import (
    deserialize_stream_response,
    serialize_stream_response,
)


def streamable_media() -> PlexMediaMeta:
    return PlexMediaMeta(
        guid='local://movie/1',
        type='movie',
        title='Example',
        ratingKey='1',
        key='/library/metadata/1',
        librarySectionTitle='Movies',
        Media=[
            {
                'videoResolution': '1080',
                'width': 1920,
                'Part': [
                    {
                        'file': '/media/Example.mkv',
                        'key': '/library/parts/1/file.mkv',
                        'size': 1234,
                        'Stream': [],
                    }
                ],
            }
        ],
    )


class MemoryCacheTests(IsolatedAsyncioTestCase):
    async def test_expired_values_are_not_returned(self):
        cache = MemoryCache()
        with patch('plexio.cache.time.monotonic', side_effect=[10, 10.5, 11.1]):
            await cache.set('key', 'value', ttl=1)
            self.assertEqual(await cache.get('key'), 'value')
            self.assertIsNone(await cache.get('key'))


class StreamCacheTests(IsolatedAsyncioTestCase):
    def test_cached_stream_response_does_not_persist_token(self):
        token = 'private-token'
        response = StremioStreamsResponse(
            streams=[
                StremioStream(
                    name='Plex',
                    description='Direct Play',
                    url=f'https://plex.example/file?X-Plex-Token={token}',
                )
            ]
        )

        serialized = serialize_stream_response(response, token)
        restored = deserialize_stream_response(serialized, token)

        self.assertNotIn(token, serialized)
        self.assertEqual(restored, response)

    @patch('plexio.routers.addon._resolve_stream_media', new_callable=AsyncMock)
    async def test_second_stream_request_uses_full_response_cache(self, resolve):
        resolve.return_value = [streamable_media()]
        configuration = AddonConfiguration(
            accessToken='private-token',
            discoveryUrl='https://plex.example',
            streamingUrl='https://plex.example',
            serverName='Home',
            sections=[{'key': '1', 'title': 'Movies', 'type': 'movie'}],
        )
        cache = MemoryCache()

        first_headers = Response()
        first = await get_stream(
            request=SimpleNamespace(),
            response=first_headers,
            http=object(),
            cache=cache,
            configuration=configuration,
            stremio_type=StremioMediaType.movie,
            media_id='plexio:rk-1',
        )
        second_headers = Response()
        second = await get_stream(
            request=SimpleNamespace(),
            response=second_headers,
            http=object(),
            cache=cache,
            configuration=configuration,
            stremio_type=StremioMediaType.movie,
            media_id='plexio:rk-1',
        )

        self.assertEqual(second, first)
        self.assertEqual(first_headers.headers['X-Plexio-Cache'], 'MISS')
        self.assertEqual(second_headers.headers['X-Plexio-Cache'], 'HIT')
        self.assertIn('plex;dur=', first_headers.headers['Server-Timing'])
        resolve.assert_awaited_once()
        cached_values = [value for value, _expires_at in cache._cache.values()]
        self.assertFalse(any('private-token' in value for value in cached_values))


class ParallelLookupTests(IsolatedAsyncioTestCase):
    async def test_matching_library_details_are_fetched_concurrently(self):
        active = 0
        maximum_active = 0

        async def fake_get_json(*, url, **_kwargs):
            nonlocal active, maximum_active
            if str(url).endswith('/library/all'):
                return {
                    'MediaContainer': {
                        'Metadata': [
                            {'type': 'movie', 'ratingKey': '1'},
                            {'type': 'movie', 'ratingKey': '2'},
                        ]
                    }
                }
            active += 1
            maximum_active = max(maximum_active, active)
            await asyncio.sleep(0)
            active -= 1
            rating_key = str(url).rsplit('/', 1)[-1]
            return {
                'MediaContainer': {
                    'Metadata': [
                        {
                            'guid': f'local://movie/{rating_key}',
                            'type': 'movie',
                            'title': f'Movie {rating_key}',
                            'ratingKey': rating_key,
                        }
                    ]
                }
            }

        with patch(
            'plexio.plex.media_server_api.get_json',
            side_effect=fake_get_json,
        ):
            media = await get_media(
                client=object(),
                url=URL('https://plex.example'),
                token='secret',
                guid='plex://movie/1',
            )

        self.assertEqual([item.rating_key for item in media], ['1', '2'])
        self.assertEqual(maximum_active, 2)
