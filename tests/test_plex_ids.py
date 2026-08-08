from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException, Response
from yarl import URL

from plexio.cache import MemoryCache
from plexio.models.plex import PlexEpisodeMeta, PlexMediaMeta
from plexio.models.stremio import StremioMediaType
from plexio.models.utils import (
    guid_to_plexio_id,
    is_rating_key_plexio_id,
    plexio_id_to_guid,
    plexio_id_to_rating_key,
    rating_key_to_plexio_id,
)
from plexio.routers.addon import _public_base_url, get_meta, get_stream
from plexio.settings import settings

CONFIGURATION = SimpleNamespace(
    discovery_url=URL('https://plex.example.test'),
    streaming_url=URL('https://plex.example.test'),
    access_token='secret',
)

STREAM_CONFIGURATION = SimpleNamespace(
    **vars(CONFIGURATION),
    server_name='Test server',
    include_transcode_original=False,
    include_transcode_down=False,
    transcode_down_qualities=[],
    include_plex_tv=False,
    report_playback=False,
)


def streamable_media(
    rating_key: str,
    media_type: str = 'movie',
    duration: int | None = None,
):
    return PlexMediaMeta(
        guid=f'local://{media_type}/{rating_key}',
        type=media_type,
        title='Personal media',
        ratingKey=rating_key,
        key=f'/library/metadata/{rating_key}',
        librarySectionTitle='Personal',
        duration=duration,
        Media=[
            {
                'Part': [
                    {
                        'file': '/media/personal.mkv',
                        'key': '/library/parts/1/file.mkv',
                        'size': 1024,
                    }
                ],
                'videoResolution': '1080',
                'width': 1920,
            }
        ],
    )


class PlexIdTests(TestCase):
    def test_guid_id_round_trip(self):
        guid = 'com.plexapp.agents.imdb://tt1234567?lang=en'
        self.assertEqual(plexio_id_to_guid(guid_to_plexio_id(guid)), guid)

    def test_malformed_guid_id_is_rejected(self):
        for value in ('not-plexio', 'plexio:', 'plexio:%2Fetc%2Fpasswd'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                plexio_id_to_guid(value)

    def test_rating_key_id_round_trip(self):
        plexio_id = rating_key_to_plexio_id(123)
        self.assertEqual(plexio_id, 'plexio:rk-123')
        self.assertTrue(is_rating_key_plexio_id(plexio_id))
        self.assertEqual(plexio_id_to_rating_key(plexio_id), '123')

    def test_rating_key_id_rejects_unsafe_paths(self):
        for value in (
            'plexio:rk-',
            'plexio:rk-../status',
            'plexio:rk-12:1',
            'plexio:rk-١٢٣',
        ):
            with self.subTest(value=value):
                self.assertFalse(is_rating_key_plexio_id(value))
                with self.assertRaises(ValueError):
                    plexio_id_to_rating_key(value)

    def test_catalog_prefers_imdb_id(self):
        media = PlexMediaMeta(
            guid='plex://movie/abc',
            type='movie',
            title='Matched movie',
            ratingKey='123',
            Guid=[{'id': 'imdb://tt1234567'}],
        )
        self.assertEqual(
            media.to_stremio_meta_review(CONFIGURATION).id,
            'tt1234567',
        )

    def test_catalog_falls_back_to_rating_key_id(self):
        media = PlexMediaMeta(
            guid='local://movie/abc',
            type='movie',
            title='Personal movie',
            ratingKey='123',
        )
        self.assertEqual(
            media.to_stremio_meta_review(CONFIGURATION).id,
            'plexio:rk-123',
        )

    def test_episode_video_uses_rating_key_id(self):
        episode = PlexEpisodeMeta(
            guid='local://episode/abc',
            title='Episode 1',
            index=1,
            ratingKey='456',
        )
        self.assertEqual(
            episode.to_stremio_video_meta(CONFIGURATION).id,
            'plexio:rk-456',
        )


class PlexIdRouteTests(IsolatedAsyncioTestCase):
    def test_public_base_url_uses_forwarded_https_origin(self):
        request = SimpleNamespace(
            headers={
                'x-forwarded-proto': 'https',
                'x-forwarded-host': 'plexio.example.test',
            },
            url=URL('http://internal.test/session/stream/movie/id.json'),
        )

        with patch.object(settings, 'trust_proxy_headers', True):
            self.assertEqual(
                _public_base_url(request),
                'https://plexio.example.test',
            )

    @patch('plexio.routers.addon.get_media_by_rating_key', new_callable=AsyncMock)
    async def test_meta_route_resolves_rating_key(self, get_by_rating_key):
        http = object()
        get_by_rating_key.return_value = [
            PlexMediaMeta(
                guid='local://movie/abc',
                type='movie',
                title='Personal movie',
                ratingKey='123',
            )
        ]

        response = await get_meta(
            http=http,
            configuration=CONFIGURATION,
            stremio_type=StremioMediaType.movie,
            plex_id='plexio:rk-123',
        )

        self.assertEqual(response.meta.id, 'plexio:rk-123')
        get_by_rating_key.assert_awaited_once_with(
            client=http,
            url=CONFIGURATION.discovery_url,
            token='secret',
            rating_key='123',
        )

    async def test_meta_route_rejects_malformed_internal_id(self):
        with self.assertRaises(HTTPException) as raised:
            await get_meta(
                http=object(),
                configuration=CONFIGURATION,
                stremio_type=StremioMediaType.movie,
                plex_id='plexio:%2Fetc%2Fpasswd',
            )
        self.assertEqual(raised.exception.status_code, 404)

    @patch('plexio.routers.addon.get_media_by_rating_key', new_callable=AsyncMock)
    async def test_stream_route_resolves_rating_key(self, get_by_rating_key):
        http = object()
        get_by_rating_key.return_value = [streamable_media('123')]

        response = await get_stream(
            request=SimpleNamespace(),
            response=Response(),
            http=http,
            cache=MemoryCache(),
            configuration=STREAM_CONFIGURATION,
            stremio_type=StremioMediaType.movie,
            media_id='plexio:rk-123',
        )

        self.assertEqual(len(response.streams), 1)
        self.assertIn('/library/parts/1/file.mkv', response.streams[0].url)
        get_by_rating_key.assert_awaited_once()
        kwargs = get_by_rating_key.await_args.kwargs
        self.assertEqual(kwargs['client'], http)
        self.assertEqual(kwargs['url'], CONFIGURATION.discovery_url)
        self.assertEqual(kwargs['token'], 'secret')
        self.assertEqual(kwargs['rating_key'], '123')

    @patch('plexio.routers.addon.get_all_episodes', new_callable=AsyncMock)
    @patch('plexio.routers.addon.get_media_by_rating_key', new_callable=AsyncMock)
    async def test_series_stream_resolves_composite_episode_id(
        self,
        get_by_rating_key,
        get_all_episodes,
    ):
        show = PlexMediaMeta(
            guid='local://show/100',
            type='show',
            title='Personal show',
            ratingKey='100',
            key='/library/metadata/100/children',
        )
        get_by_rating_key.side_effect = [
            [show],
            [streamable_media('200', media_type='episode')],
        ]
        get_all_episodes.return_value = [
            PlexEpisodeMeta(
                guid='local://episode/200',
                title='Episode 3',
                index=3,
                parentIndex=2,
                ratingKey='200',
            )
        ]

        response = await get_stream(
            request=SimpleNamespace(),
            response=Response(),
            http=object(),
            cache=MemoryCache(),
            configuration=STREAM_CONFIGURATION,
            stremio_type=StremioMediaType.series,
            media_id='plexio:rk-100:2:3',
        )

        self.assertEqual(len(response.streams), 1)
        self.assertEqual(get_by_rating_key.await_count, 2)
        self.assertEqual(
            get_by_rating_key.await_args_list[1].kwargs['rating_key'],
            '200',
        )

    @patch('plexio.routers.addon.get_media_by_rating_key', new_callable=AsyncMock)
    async def test_playback_stream_uses_public_origin_and_media_duration(
        self,
        get_by_rating_key,
    ):
        get_by_rating_key.return_value = [streamable_media('123', duration=120_000)]
        configuration = SimpleNamespace(
            **{
                key: value
                for key, value in vars(STREAM_CONFIGURATION).items()
                if key != 'report_playback'
            },
            report_playback=True,
        )
        request = SimpleNamespace(
            headers={
                'x-forwarded-proto': 'https',
                'x-forwarded-host': 'plexio.example.test',
            },
            url=URL('http://internal.test/session-id/stream/movie/plexio:rk-123.json'),
        )

        with patch.object(settings, 'trust_proxy_headers', True):
            response = await get_stream(
                request=request,
                response=Response(),
                http=object(),
                cache=MemoryCache(),
                configuration=configuration,
                stremio_type=StremioMediaType.movie,
                media_id='plexio:rk-123',
            )

        self.assertEqual(len(response.streams), 1)
        self.assertTrue(
            response.streams[0].url.startswith(
                'https://plexio.example.test/session-id/play/123/120000/'
            )
        )
