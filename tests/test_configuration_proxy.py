import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

import aiohttp
from fastapi import HTTPException
from yarl import URL

from plexio.routers.configuration import (
    _get_server_json,
    get_plex_collections,
    get_plex_sections,
)


class FakeResponse:
    def __init__(self, payload=None, *, status=200, error=None):
        self.payload = payload
        self.status = status
        self.error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def json(self, *, content_type=None):
        if self.error:
            raise self.error
        return self.payload


class FakeClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return self.response


class ConfigurationProxyTests(IsolatedAsyncioTestCase):
    @patch(
        'plexio.routers.configuration._authorized_server_url',
        new_callable=AsyncMock,
    )
    async def test_sections_are_fetched_server_side_and_sanitized(self, authorize):
        authorize.return_value = URL('http://us.loclx.io:7070')
        client = FakeClient(
            FakeResponse(
                {
                    'MediaContainer': {
                        'Directory': [
                            {'key': '1', 'title': 'Movies', 'type': 'movie'},
                            {'key': '2', 'title': 'TV', 'type': 'show'},
                            {'key': '3', 'title': 'Music', 'type': 'artist'},
                        ]
                    }
                }
            )
        )

        result = await get_plex_sections(
            http=client,
            url='http://us.loclx.io:7070',
            server_name='Home',
            token='server-token',
            account_token='account-token',
            client_identifier='client-id',
        )

        self.assertEqual(
            result,
            {
                'sections': [
                    {'key': '1', 'title': 'Movies', 'type': 'movie'},
                    {'key': '2', 'title': 'TV', 'type': 'show'},
                ]
            },
        )
        requested_url, kwargs = client.calls[0]
        self.assertEqual(str(requested_url), 'http://us.loclx.io:7070/library/sections')
        self.assertEqual(kwargs['headers']['X-Plex-Token'], 'server-token')
        self.assertNotIn('params', kwargs)
        self.assertFalse(kwargs['allow_redirects'])

    @patch(
        'plexio.routers.configuration._authorized_server_url',
        new_callable=AsyncMock,
    )
    async def test_collections_are_fetched_through_authorized_connection(
        self,
        authorize,
    ):
        authorize.return_value = URL('http://us.loclx.io:7070')
        client = FakeClient(
            FakeResponse(
                {
                    'MediaContainer': {
                        'Metadata': [
                            {'ratingKey': '10', 'title': 'Favorites'},
                            {'title': 'Missing key'},
                        ]
                    }
                }
            )
        )

        result = await get_plex_collections(
            http=client,
            url='http://us.loclx.io:7070',
            server_name='Home',
            section_key='1',
            token='server-token',
            account_token='account-token',
            client_identifier='client-id',
        )

        self.assertEqual(
            result,
            {'collections': [{'ratingKey': '10', 'title': 'Favorites'}]},
        )
        self.assertEqual(
            str(client.calls[0][0]),
            'http://us.loclx.io:7070/library/sections/1/collections',
        )

    async def test_upstream_failures_are_mapped_without_leaking_response(self):
        cases = (
            (FakeClient(FakeResponse(status=503)), 502),
            (FakeClient(error=aiohttp.ClientConnectionError()), 502),
            (FakeClient(error=asyncio.TimeoutError()), 504),
        )
        for client, expected_status in cases:
            with self.subTest(expected_status=expected_status):
                with self.assertRaises(HTTPException) as raised:
                    await _get_server_json(
                        http=client,
                        url=URL('https://plex.example.test/library/sections'),
                        server_token='secret',
                    )
                self.assertEqual(raised.exception.status_code, expected_status)
                self.assertNotIn('secret', raised.exception.detail)
