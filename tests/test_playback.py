import asyncio
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from yarl import URL

from plexio.plex.playback import _position_ms, _timeline, proxy_playback


class FakeContent:
    def __init__(self, chunks):
        self.chunks = chunks

    async def iter_chunked(self, _size):
        for chunk in self.chunks:
            yield chunk


class FakeResponse:
    def __init__(self, *, headers=None, status=200, chunks=()):
        self.headers = headers or {}
        self.status = status
        self.content = FakeContent(chunks)
        self.closed = False
        self.read_called = False

    def __await__(self):
        async def resolve():
            return self

        return resolve().__await__()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self.close()
        return False

    async def read(self):
        self.read_called = True
        return b''

    def close(self):
        self.closed = True


class FakeClient:
    def __init__(self, stream_response):
        self.stream_response = stream_response
        self.calls = []
        self.timeline_responses = []

    def get(self, url, **kwargs):
        self.calls.append(('GET', url, kwargs))
        if str(url).endswith(':/timeline') or '/:/timeline?' in str(url):
            response = FakeResponse()
            self.timeline_responses.append(response)
            return response
        return self.stream_response

    def head(self, url, **kwargs):
        self.calls.append(('HEAD', url, kwargs))
        return self.stream_response


class FallbackClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def head(self, url, **kwargs):
        self.calls.append(('HEAD', url, kwargs))
        return self.responses.pop(0)


class PlaybackPositionTests(TestCase):
    def test_position_uses_range_offset_and_elapsed_time(self):
        self.assertEqual(
            _position_ms(
                total=1_000,
                start=500,
                duration_ms=100_000,
                started_at=10,
                now=22.5,
            ),
            62_500,
        )

    def test_position_is_capped_at_duration(self):
        self.assertEqual(
            _position_ms(
                total=1_000,
                start=900,
                duration_ms=100_000,
                started_at=10,
                now=30,
            ),
            100_000,
        )


class PlaybackProxyTests(IsolatedAsyncioTestCase):
    async def test_head_probe_retries_gateway_error_on_alternate_connection(self):
        failed = FakeResponse(status=503)
        succeeded = FakeResponse(
            status=206,
            headers={
                'Content-Length': '1000',
                'Content-Range': 'bytes 0-999/1000',
                'Content-Type': 'video/x-matroska',
            },
        )
        client = FallbackClient([failed, succeeded])
        request = SimpleNamespace(method='HEAD', headers={})
        configuration = SimpleNamespace(
            streaming_url=URL('https://primary.example.test'),
            direct_play_connections=[
                (URL('https://primary.example.test'), None),
                (URL('https://relay.example.test'), None),
            ],
            discovery_url=URL('https://primary.example.test'),
            access_token='secret',
        )

        response = await proxy_playback(
            request,
            client=client,
            configuration=configuration,
            rating_key='42',
            duration_ms=60_000,
            part_key='/library/parts/1/file.mkv',
            identifier='session-id',
        )

        self.assertEqual(response.status_code, 206)
        self.assertTrue(failed.read_called)
        self.assertTrue(failed.closed)
        self.assertEqual(
            [call[1].host for call in client.calls],
            ['primary.example.test', 'relay.example.test'],
        )

    async def test_timeline_sends_query_and_releases_response(self):
        client = FakeClient(FakeResponse())

        sent = await _timeline(
            client,
            url=URL('https://plex.example.test'),
            token='secret',
            rating_key='42',
            state='playing',
            time_ms=12_000,
            duration_ms=60_000,
            identifier='session-id',
        )

        self.assertTrue(sent)
        _, url, kwargs = client.calls[0]
        self.assertEqual(url.path, '/:/timeline')
        self.assertEqual(url.query['ratingKey'], '42')
        self.assertEqual(url.query['time'], '12000')
        self.assertEqual(url.query['X-Plex-Token'], 'secret')
        self.assertEqual(
            kwargs['headers']['X-Plex-Client-Identifier'],
            'plexio-session-id',
        )
        self.assertTrue(client.timeline_responses[0].read_called)
        self.assertTrue(client.timeline_responses[0].closed)

    @patch('plexio.plex.playback.monotonic')
    async def test_proxy_reports_elapsed_progress_and_forwards_range(
        self,
        monotonic,
    ):
        monotonic.side_effect = [100.0, 112.0]
        upstream = FakeResponse(
            headers={
                'Content-Length': '1000',
                'Accept-Ranges': 'bytes',
                'Content-Type': 'video/x-matroska',
            },
            chunks=(b'first', b'second'),
        )
        client = FakeClient(upstream)
        configuration = SimpleNamespace(
            streaming_url=URL('https://plex.example.test'),
            discovery_url=URL('https://plex.example.test'),
            access_token='secret',
        )
        request = SimpleNamespace(
            method='GET',
            headers={'range': 'bytes=0-'},
        )

        response = await proxy_playback(
            request,
            client=client,
            configuration=configuration,
            rating_key='42',
            duration_ms=60_000,
            part_key='/library/parts/1/file.mkv',
            identifier='session-id',
        )
        body = b''.join([chunk async for chunk in response.body_iterator])

        self.assertEqual(body, b'firstsecond')
        self.assertTrue(upstream.closed)
        self.assertEqual(client.calls[0][2]['headers']['Range'], 'bytes=0-')
        self.assertEqual(
            client.calls[0][2]['headers']['X-Plex-Client-Identifier'],
            'plexio-session-id',
        )
        self.assertIsNone(client.calls[0][2]['timeout'].sock_read)
        timeline_urls = [url for _, url, _ in client.calls if '/:/timeline' in str(url)]
        self.assertEqual(
            [url.query['state'] for url in timeline_urls],
            ['playing', 'stopped'],
        )
        self.assertEqual(
            [url.query['time'] for url in timeline_urls],
            ['0', '12000'],
        )

    @patch('plexio.plex.playback.PING_INTERVAL', 0.01)
    async def test_heartbeat_continues_while_downstream_is_idle(self):
        upstream = FakeResponse(
            headers={
                'Content-Length': '1000',
                'Content-Type': 'video/x-matroska',
            },
            chunks=(b'first', b'second'),
        )
        client = FakeClient(upstream)
        configuration = SimpleNamespace(
            streaming_url=URL('https://plex.example.test'),
            discovery_url=URL('https://plex.example.test'),
            access_token='secret',
        )
        request = SimpleNamespace(method='GET', headers={})

        response = await proxy_playback(
            request,
            client=client,
            configuration=configuration,
            rating_key='42',
            duration_ms=60_000,
            part_key='/library/parts/1/file.mkv',
            identifier='session-id',
        )
        iterator = response.body_iterator

        self.assertEqual(await anext(iterator), b'first')
        await asyncio.sleep(0.045)

        states = [
            url.query['state']
            for _, url, _ in client.calls
            if '/:/timeline' in str(url)
        ]
        self.assertGreaterEqual(states.count('playing'), 2)

        await iterator.aclose()
        states = [
            url.query['state']
            for _, url, _ in client.calls
            if '/:/timeline' in str(url)
        ]
        self.assertEqual(states[-1], 'stopped')
        self.assertTrue(upstream.closed)

    async def test_head_probe_returns_headers_without_streaming_or_timeline(self):
        upstream = FakeResponse(
            status=206,
            headers={
                'Content-Length': '1000',
                'Content-Range': 'bytes 0-999/1000',
                'Content-Type': 'video/x-matroska',
            },
        )
        client = FakeClient(upstream)
        request = SimpleNamespace(method='HEAD', headers={})
        configuration = SimpleNamespace(
            streaming_url=URL('https://plex.example.test'),
            discovery_url=URL('https://plex.example.test'),
            access_token='secret',
        )

        response = await proxy_playback(
            request,
            client=client,
            configuration=configuration,
            rating_key='42',
            duration_ms=60_000,
            part_key='/library/parts/1/file.mkv',
            identifier='session-id',
        )

        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.headers['content-range'], 'bytes 0-999/1000')
        self.assertTrue(upstream.closed)
        self.assertEqual([method for method, _, _ in client.calls], ['HEAD'])
