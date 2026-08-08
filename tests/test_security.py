import asyncio
import base64
import json
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

import aiosqlite
from cryptography.fernet import Fernet
from fastapi import HTTPException
from pydantic import ValidationError
from yarl import URL

from plexio.dependencies import get_addon_configuration
from plexio.models.addon import AddonConfiguration
from plexio.plex.media_server_api import check_server_connection
from plexio.plex.plex_tv import is_authorized_connection
from plexio.rate_limit import InMemoryRateLimiter
from plexio.security import RequestBodyLimitMiddleware, SecurityHeadersMiddleware
from plexio.sessions import _CREATE_TABLE, SessionCapacityError, SessionStore
from plexio.settings import settings


def configuration_dict(**overrides):
    config = {
        'accessToken': 'secret',
        'discoveryUrl': 'https://example.plex.direct:32400',
        'streamingUrl': 'http://192.168.1.2:32400',
        'serverName': 'Home',
        'sections': [{'key': '1', 'title': 'Movies', 'type': 'movie'}],
    }
    config.update(overrides)
    return config


class ConfigurationValidationTests(TestCase):
    def test_normalizes_only_validated_fields_for_storage(self):
        model = AddonConfiguration(**configuration_dict())

        stored = model.to_storage_dict()

        self.assertEqual(stored['discoveryUrl'], 'https://example.plex.direct:32400')
        self.assertEqual(stored['streamingUrl'], 'http://192.168.1.2:32400')
        self.assertEqual(stored['accessToken'], 'secret')

    def test_rejects_credentials_queries_and_unknown_fields(self):
        invalid_urls = (
            'http://user:password@localhost:32400',
            'http://localhost:32400/?target=other',
            'file:///etc/passwd',
        )
        for invalid_url in invalid_urls:
            with self.subTest(url=invalid_url), self.assertRaises(ValidationError):
                AddonConfiguration(
                    **configuration_dict(discoveryUrl=invalid_url),
                )
        with self.assertRaises(ValidationError):
            AddonConfiguration(**configuration_dict(unexpected='value'))


class LegacyConfigurationTests(IsolatedAsyncioTestCase):
    async def test_urlsafe_unpadded_legacy_configuration_round_trips(self):
        payload = json.dumps(configuration_dict()).encode()
        encoded = base64.urlsafe_b64encode(payload).decode().rstrip('=')

        with patch.object(settings, 'enable_legacy_urls', True):
            model = await get_addon_configuration(
                SimpleNamespace(),
                base64_cfg=encoded,
            )

        self.assertEqual(model.server_name, 'Home')
        self.assertEqual(model.access_token, 'secret')

    async def test_legacy_configuration_is_disabled_by_default(self):
        with patch.object(settings, 'enable_legacy_urls', False):
            with self.assertRaises(HTTPException) as raised:
                await get_addon_configuration(
                    SimpleNamespace(),
                    base64_cfg='e30',
                )
        self.assertEqual(raised.exception.status_code, 404)


class ConnectionAuthorizationTests(TestCase):
    def test_only_accepts_connection_from_matching_plex_resource(self):
        resources = [
            {
                'name': 'Home',
                'provides': 'server',
                'accessToken': 'server-token',
                'connections': [
                    {'uri': 'https://example.plex.direct:32400/'},
                ],
            }
        ]

        self.assertTrue(
            is_authorized_connection(
                resources,
                server_name='Home',
                url=URL('https://example.plex.direct:32400'),
                server_token='server-token',
            )
        )
        self.assertFalse(
            is_authorized_connection(
                resources,
                server_name='Home',
                url=URL('http://169.254.169.254'),
                server_token='server-token',
            )
        )


class FakeConnectionResponse:
    status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeConnectionClient:
    def __init__(self):
        self.kwargs = None

    def get(self, _url, **kwargs):
        self.kwargs = kwargs
        return FakeConnectionResponse()


class ConnectionProbeTests(IsolatedAsyncioTestCase):
    async def test_connection_probe_does_not_follow_redirects(self):
        client = FakeConnectionClient()

        self.assertTrue(
            await check_server_connection(
                client=client,
                url=URL('https://example.plex.direct:32400'),
                token='secret',
            )
        )

        self.assertFalse(client.kwargs['allow_redirects'])


class RateLimiterTests(IsolatedAsyncioTestCase):
    async def test_rejects_only_within_window(self):
        limiter = InMemoryRateLimiter(requests=2, window_seconds=60)

        self.assertTrue(await limiter.allow('client', now=0))
        self.assertTrue(await limiter.allow('client', now=1))
        self.assertFalse(await limiter.allow('client', now=2))
        self.assertTrue(await limiter.allow('client', now=61))


class SessionCapacityTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = await aiosqlite.connect(':memory:')
        await self.db.execute(_CREATE_TABLE)
        await self.db.commit()
        self.store = SessionStore(
            self.db,
            Fernet(Fernet.generate_key()),
            max_sessions=1,
        )

    async def asyncTearDown(self):
        await self.store.close()

    async def test_deduplicates_before_enforcing_capacity(self):
        config = configuration_dict()
        first = await self.store.create(config)
        duplicate = await self.store.create(config)
        self.assertEqual(first, duplicate)

        with self.assertRaises(SessionCapacityError):
            await self.store.create(configuration_dict(serverName='Other'))


class MiddlewareTests(IsolatedAsyncioTestCase):
    async def _request(self, app, body=b'', content_length=None):
        sent = []
        delivered = False

        async def receive():
            nonlocal delivered
            if delivered:
                await asyncio.sleep(0)
                return {'type': 'http.disconnect'}
            delivered = True
            return {'type': 'http.request', 'body': body, 'more_body': False}

        async def send(message):
            sent.append(message)

        headers = []
        if content_length is not None:
            headers.append((b'content-length', str(content_length).encode()))
        await app(
            {'type': 'http', 'method': 'POST', 'headers': headers},
            receive,
            send,
        )
        return sent

    async def test_request_body_limit_rejects_declared_and_streamed_bodies(self):
        async def inner(_scope, _receive, send):
            await send({'type': 'http.response.start', 'status': 204, 'headers': []})
            await send({'type': 'http.response.body', 'body': b''})

        middleware = RequestBodyLimitMiddleware(inner, max_body_size=4)
        declared = await self._request(middleware, b'', content_length=5)
        streamed = await self._request(middleware, b'12345')

        self.assertEqual(declared[0]['status'], 413)
        self.assertEqual(streamed[0]['status'], 413)

    async def test_security_headers_are_added(self):
        async def inner(_scope, _receive, send):
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            await send({'type': 'http.response.body', 'body': b''})

        sent = await self._request(SecurityHeadersMiddleware(inner))
        headers = dict(sent[0]['headers'])

        self.assertEqual(headers[b'x-content-type-options'], b'nosniff')
        self.assertIn(b"script-src 'self'", headers[b'content-security-policy'])
