import asyncio
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

import aiohttp
from fastapi import HTTPException
from yarl import URL

from plexio.routers.plex_proxy import (
    _plex_request,
    _request_origin,
    create_plex_pin,
    get_plex_resources,
)
from plexio.settings import settings


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def json(self):
        return self.payload


class FakeClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if self.error:
            raise self.error
        return self.response


class PlexProxyTests(IsolatedAsyncioTestCase):
    async def test_request_forwards_only_expected_values(self):
        client = FakeClient(FakeResponse({'id': 42}))

        result = await _plex_request(
            client,
            'POST',
            '/pins',
            headers={'X-Plex-Client-Identifier': 'client-id'},
            params={'strong': 'true'},
        )

        self.assertEqual(result, {'id': 42})
        method, url, kwargs = client.calls[0]
        self.assertEqual((method, url), ('POST', 'https://plex.tv/api/v2/pins'))
        self.assertEqual(kwargs['params'], {'strong': 'true'})
        self.assertEqual(kwargs['timeout'], settings.plex_requests_timeout)
        self.assertEqual(
            kwargs['headers']['X-Plex-Client-Identifier'],
            'client-id',
        )

    async def test_upstream_error_is_mapped_to_bad_gateway(self):
        client = FakeClient(FakeResponse({'error': 'private'}, status=401))

        with self.assertRaises(HTTPException) as raised:
            await _plex_request(
                client,
                'GET',
                '/resources',
                headers={'X-Plex-Token': 'secret'},
            )

        self.assertEqual(raised.exception.status_code, 502)
        self.assertNotIn('secret', raised.exception.detail)
        self.assertNotIn('private', raised.exception.detail)

    async def test_network_and_timeout_errors_are_mapped_to_bad_gateway(self):
        for error in (aiohttp.ClientConnectionError(), asyncio.TimeoutError()):
            with self.subTest(error=type(error).__name__):
                client = FakeClient(error=error)
                with self.assertRaises(HTTPException) as raised:
                    await _plex_request(
                        client,
                        'GET',
                        '/resources',
                        headers={},
                    )
                self.assertEqual(raised.exception.status_code, 502)

    async def test_pin_endpoint_uses_backend_proxy(self):
        client = FakeClient(FakeResponse({'id': 42, 'code': 'abcd'}))
        request = SimpleNamespace(
            headers={'origin': 'https://plexio.example.test'},
            url=URL('http://internal.test/api/v1/plex-pin'),
        )

        result = await create_plex_pin(
            request=request,
            http=client,
            client_identifier='client-id',
        )

        self.assertEqual(result['id'], 42)
        _, _, kwargs = client.calls[0]
        self.assertEqual(kwargs['params'], {'strong': 'true'})
        self.assertEqual(kwargs['headers']['Origin'], 'https://plexio.example.test')

    def test_pin_origin_uses_forwarded_public_host_when_browser_origin_missing(self):
        request = SimpleNamespace(
            headers={
                'x-forwarded-proto': 'https',
                'x-forwarded-host': 'plexio.example.test',
            },
            url=URL('http://internal.test/api/v1/plex-pin'),
        )

        with patch.object(settings, 'trust_proxy_headers', True):
            self.assertEqual(
                _request_origin(request),
                'https://plexio.example.test',
            )

    async def test_resources_endpoint_keeps_token_out_of_query_string(self):
        client = FakeClient(FakeResponse([]))

        await get_plex_resources(
            http=client,
            client_identifier='client-id',
            token='secret',
            include_https=1,
            include_relay=0,
        )

        _, _, kwargs = client.calls[0]
        self.assertEqual(
            kwargs['params'],
            {'includeHttps': 1, 'includeRelay': 0},
        )
        self.assertEqual(kwargs['headers']['X-Plex-Token'], 'secret')
        self.assertNotIn('X-Plex-Token', kwargs['params'])
