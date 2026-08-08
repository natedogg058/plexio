from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from pydantic import ValidationError
from yarl import URL

from plexio.models.addon import AddonConfiguration
from plexio.models.plex import PlexMediaMeta
from plexio.models.stremio import StremioMediaType
from plexio.plex.media_server_api import get_collection_media
from plexio.routers.addon import get_catalog, get_manifest


def configuration_dict(**overrides):
    values = {
        'accessToken': 'secret',
        'discoveryUrl': 'https://plex.example.test',
        'streamingUrl': 'https://plex.example.test',
        'serverName': 'Home',
        'sections': [{'key': '1', 'title': 'Movies', 'type': 'movie'}],
        'includeCollections': True,
        'collections': [
            {
                'ratingKey': '42',
                'sectionKey': '1',
                'title': 'Favourites',
                'type': 'movie',
            }
        ],
    }
    values.update(overrides)
    return values


def movie(rating_key='7'):
    return PlexMediaMeta(
        guid=f'local://movie/{rating_key}',
        ratingKey=rating_key,
        type='movie',
        title='Example movie',
    )


class CollectionConfigurationTests(IsolatedAsyncioTestCase):
    async def test_manifest_only_includes_opted_in_collections_with_stable_ids(self):
        enabled = AddonConfiguration(**configuration_dict())
        disabled = AddonConfiguration(
            **configuration_dict(includeCollections=False),
        )

        enabled_manifest = await get_manifest(enabled, session_id='session')
        disabled_manifest = await get_manifest(disabled, session_id='session')

        collection = next(
            catalog
            for catalog in enabled_manifest.catalogs
            if catalog.id.startswith('plexio-collection-')
        )
        self.assertEqual(collection.id, 'plexio-collection-1-42')
        self.assertEqual(collection.type, StremioMediaType.movie)
        self.assertEqual(collection.name, 'Collection: Favourites (Movies) | Home')
        self.assertEqual(collection.extra, [{'name': 'skip', 'isRequired': False}])
        self.assertFalse(
            any(
                catalog.id.startswith('plexio-collection-')
                for catalog in disabled_manifest.catalogs
            )
        )

    async def test_collection_must_match_a_configured_section_and_be_unique(self):
        invalid_collections = (
            [
                {
                    'ratingKey': '42',
                    'sectionKey': '2',
                    'title': 'Wrong section',
                    'type': 'movie',
                }
            ],
            [
                {
                    'ratingKey': '42',
                    'sectionKey': '1',
                    'title': 'Wrong type',
                    'type': 'show',
                }
            ],
            configuration_dict()['collections'] * 2,
        )
        for collections in invalid_collections:
            with (
                self.subTest(collections=collections),
                self.assertRaises(ValidationError),
            ):
                AddonConfiguration(
                    **configuration_dict(collections=collections),
                )


class CollectionCatalogTests(IsolatedAsyncioTestCase):
    @patch('plexio.routers.addon.get_collection_media', new_callable=AsyncMock)
    async def test_catalog_fetches_configured_collection_page(self, fetch):
        fetch.return_value = [movie()]
        configuration = AddonConfiguration(**configuration_dict())
        http = SimpleNamespace()

        catalog = await get_catalog(
            http=http,
            configuration=configuration,
            stremio_type=StremioMediaType.movie,
            catalog_id='plexio-collection-1-42',
            extra='skip=20',
        )

        self.assertEqual([item.name for item in catalog.metas], ['Example movie'])
        fetch.assert_awaited_once_with(
            client=http,
            url=URL('https://plex.example.test'),
            token='secret',
            rating_key='42',
            skip=20,
        )

    async def test_catalog_rejects_unconfigured_or_wrong_type_collection(self):
        configuration = AddonConfiguration(**configuration_dict())
        for catalog_id, media_type in (
            ('plexio-collection-1-999', StremioMediaType.movie),
            ('plexio-collection-1-42', StremioMediaType.series),
        ):
            with self.subTest(catalog_id=catalog_id, media_type=media_type):
                with self.assertRaises(HTTPException) as raised:
                    await get_catalog(
                        http=SimpleNamespace(),
                        configuration=configuration,
                        stremio_type=media_type,
                        catalog_id=catalog_id,
                    )
                self.assertEqual(raised.exception.status_code, 404)


class CollectionMediaTests(IsolatedAsyncioTestCase):
    @patch('plexio.plex.media_server_api.get_json', new_callable=AsyncMock)
    async def test_collection_media_is_paginated_top_level_and_deduplicated(
        self,
        fetch,
    ):
        item = {
            'guid': 'local://movie/7',
            'ratingKey': '7',
            'type': 'movie',
            'title': 'Example movie',
        }
        fetch.return_value = {
            'MediaContainer': {
                'Metadata': [
                    item,
                    dict(item),
                    {
                        'guid': 'local://episode/8',
                        'ratingKey': '8',
                        'type': 'episode',
                        'title': 'Loose episode',
                    },
                ]
            }
        }

        media = await get_collection_media(
            client=SimpleNamespace(),
            url=URL('https://plex.example.test'),
            token='secret',
            rating_key='42',
            skip=100,
        )

        self.assertEqual([item.rating_key for item in media], ['7'])
        self.assertEqual(
            fetch.await_args.kwargs['url'].path,
            '/library/collections/42/items',
        )
        self.assertEqual(
            fetch.await_args.kwargs['params']['X-Plex-Container-Start'],
            100,
        )
        self.assertEqual(
            fetch.await_args.kwargs['params']['X-Plex-Container-Size'],
            100,
        )
