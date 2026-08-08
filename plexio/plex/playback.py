"""Proxy playback through Plexio and report conservative progress to Plex.

Active only when a configuration has report_playback enabled. The stream handler
emits a token-free /{cfg}/play/... URL pointing here. Direct-play bytes are proxied
from Plex with Range support, while timeline positions advance by elapsed wall time
instead of downloaded bytes. That avoids marking rapidly buffered media as watched
while still recording ongoing watch time for clients that consume the stream during
playback. We do not scrobble; Plex applies its own watched threshold.
"""

import asyncio
import base64
import logging
from time import monotonic

import aiohttp
from fastapi.responses import Response, StreamingResponse

PLEX_PRODUCT = 'Plexio'
CHUNK = 1 << 16  # 64 KiB
PING_INTERVAL = 10.0  # seconds between Plex timeline updates

logger = logging.getLogger(__name__)


def b64decode_path(token: str) -> str:
    token += '=' * (-len(token) % 4)
    return base64.urlsafe_b64decode(token).decode()


def _client_id(identifier: str) -> str:
    return f'plexio-{identifier}'


def _client_headers(identifier: str) -> dict[str, str]:
    return {
        'X-Plex-Client-Identifier': _client_id(identifier),
        'X-Plex-Product': PLEX_PRODUCT,
        'X-Plex-Device-Name': PLEX_PRODUCT,
    }


async def _timeline(
    client,
    *,
    url,
    token,
    rating_key,
    state,
    time_ms,
    duration_ms,
    identifier,
):
    timeline_url = (url / ':/timeline').with_query(
        {
            'ratingKey': rating_key,
            'key': f'/library/metadata/{rating_key}',
            'state': state,
            'time': max(time_ms, 0),
            'duration': max(duration_ms, 0),
            'X-Plex-Token': token,
        }
    )
    try:
        async with client.get(
            timeline_url,
            headers=_client_headers(identifier),
            timeout=aiohttp.ClientTimeout(total=5),
        ) as response:
            await response.read()
            if response.status >= 400:
                logger.warning(
                    'Plex timeline update failed with HTTP %s',
                    response.status,
                )
                return False
        return True
    except Exception:
        # Timeline reporting is optional and must never interrupt playback.
        logger.warning('Unable to send Plex timeline update', exc_info=True)
        return False


async def _playback_heartbeat(
    client,
    *,
    url,
    token,
    rating_key,
    total,
    start,
    duration_ms,
    identifier,
    started_at,
    stopped,
):
    """Report playback independently of downstream media reads.

    External players can fill their own buffer and stop pulling response chunks
    for several minutes. Keeping this loop in its own task prevents that idle
    downstream connection from also pausing Plex timeline updates.
    """
    now = started_at
    while True:
        await _timeline(
            client,
            url=url,
            token=token,
            rating_key=rating_key,
            state='playing',
            time_ms=_position_ms(
                total=total,
                start=start,
                duration_ms=duration_ms,
                started_at=started_at,
                now=now,
            ),
            duration_ms=duration_ms,
            identifier=identifier,
        )
        if stopped.is_set():
            return
        try:
            await asyncio.wait_for(stopped.wait(), timeout=PING_INTERVAL)
            return
        except TimeoutError:
            now = monotonic()


def _total_and_start(resp):
    """Return the full file size and start offset from response headers."""
    cr = resp.headers.get('Content-Range')
    if cr and '/' in cr:
        try:
            rng, total = cr.split(' ', 1)[1].split('/')
            return int(total), int(rng.split('-')[0])
        except (ValueError, IndexError):
            pass
    try:
        return (int(resp.headers.get('Content-Length', 0)) or None), 0
    except ValueError:
        return None, 0


def _position_ms(*, total, start, duration_ms, started_at, now):
    """Estimate playback from the requested byte offset plus elapsed time."""
    if not duration_ms:
        return 0
    initial = int(start / total * duration_ms) if total else 0
    elapsed = max(now - started_at, 0) * 1000
    return min(int(initial + elapsed), duration_ms)


async def _open_playback_response(
    *,
    requester,
    connections,
    part_key,
    access_token,
    headers,
):
    for connection_index, (stream_base, _kind) in enumerate(connections):
        upstream = stream_base / part_key[1:] % {'X-Plex-Token': access_token}
        has_fallback = connection_index < len(connections) - 1
        try:
            response = await requester(
                upstream,
                headers=headers,
                timeout=aiohttp.ClientTimeout(
                    total=None,
                    sock_connect=15,
                    # Buffered external players can intentionally leave the
                    # upstream response idle for minutes. The downstream
                    # connection lifecycle remains the cancellation boundary.
                    sock_read=None,
                ),
            )
        except (aiohttp.ClientError, TimeoutError):
            if has_fallback:
                logger.warning('Plex playback connection failed; trying fallback')
                continue
            raise
        if response.status not in {502, 503, 504} or not has_fallback:
            return response
        await response.read()
        response.close()
        logger.warning(
            'Plex playback returned HTTP %s; trying fallback',
            response.status,
        )
    raise RuntimeError('No Plex playback connection was available')


async def proxy_playback(
    request,
    *,
    client,
    configuration,
    rating_key,
    duration_ms,
    part_key,
    identifier,
):
    fwd = _client_headers(identifier)
    rng = request.headers.get('range')
    if rng:
        fwd['Range'] = rng

    method = request.method.upper()
    requester = client.head if method == 'HEAD' else client.get
    configured_connections = getattr(configuration, 'direct_play_connections', None)
    if configured_connections is None:
        configured_connections = [(configuration.streaming_url, None)]
    resp = await _open_playback_response(
        requester=requester,
        connections=configured_connections,
        part_key=part_key,
        access_token=configuration.access_token,
        headers=fwd,
    )
    total, start = _total_and_start(resp)
    passthrough = {
        h: resp.headers[h]
        for h in (
            'Content-Length',
            'Content-Range',
            'Accept-Ranges',
            'Cache-Control',
            'Content-Disposition',
            'ETag',
            'Last-Modified',
        )
        if h in resp.headers
    }

    if method == 'HEAD':
        resp.close()
        return Response(
            status_code=resp.status,
            headers=passthrough,
            media_type=resp.headers.get('Content-Type'),
        )

    async def streamer():
        started_at = None
        heartbeat = None
        heartbeat_stopped = asyncio.Event()
        try:
            async for chunk in resp.content.iter_chunked(CHUNK):
                if started_at is None:
                    started_at = monotonic()
                    heartbeat = asyncio.create_task(
                        _playback_heartbeat(
                            client,
                            url=configuration.discovery_url,
                            token=configuration.access_token,
                            rating_key=rating_key,
                            total=total,
                            start=start,
                            duration_ms=duration_ms,
                            identifier=identifier,
                            started_at=started_at,
                            stopped=heartbeat_stopped,
                        ),
                        name='plexio-playback-heartbeat',
                    )
                yield chunk
        finally:
            heartbeat_stopped.set()
            resp.close()
            if heartbeat is not None:
                await heartbeat
            if started_at is not None:
                now = monotonic()
                await _timeline(
                    client,
                    url=configuration.discovery_url,
                    token=configuration.access_token,
                    rating_key=rating_key,
                    state='stopped',
                    time_ms=_position_ms(
                        total=total,
                        start=start,
                        duration_ms=duration_ms,
                        started_at=started_at,
                        now=now,
                    ),
                    duration_ms=duration_ms,
                    identifier=identifier,
                )

    return StreamingResponse(
        streamer(),
        status_code=resp.status,
        headers=passthrough,
        media_type=resp.headers.get('Content-Type'),
    )
