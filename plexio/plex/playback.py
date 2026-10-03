"""Report playback progress to Plex, with or without proxying media.

Two modes, both active only when a configuration has report_playback enabled.
The stream handler emits a token-free /{cfg}/play/... or /{cfg}/keepalive/... URL
pointing here.

Proxy mode sends media through Plexio with Range support. Keepalive mode
redirects the player straight to Plex and only sends timeline updates, so no
video crosses Plexio at all. In both, timeline positions advance by elapsed
wall time instead of downloaded bytes. That avoids marking rapidly buffered
media as watched while still recording ongoing watch time. We do not scrobble;
Plex applies its own watched threshold.
"""

import asyncio
import base64
import json
import logging
from time import monotonic

import aiohttp
from fastapi.responses import RedirectResponse, Response, StreamingResponse

PLEX_PRODUCT = 'Plexio'
CHUNK = 1 << 16  # 64 KiB
PING_INTERVAL = 10.0  # seconds between Plex timeline updates
UPSTREAM_READ_TIMEOUT = 30.0  # seconds waiting for a requested media chunk
TIMELINE_TIMEOUT = 10.0  # seconds for one timeline update against a remote server
KEEPALIVE_GRACE = 600.0  # extra seconds past the runtime before giving up

# Background keepalives need a strong reference or the event loop may drop them.
_KEEPALIVE_TASKS: set[asyncio.Task] = set()

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


def _playback_state(body: bytes) -> str | None:
    """Read the playbackState Plex reports for a timeline update.

    Plex answers 'progress' while it still tracks the session and 'ignore'
    once it has dropped it. On servers that block /status/sessions this is the
    only signal that says whether the keepalive is still holding a live
    session, so it has to be read from every update rather than discarded.
    """
    try:
        return json.loads(body)['MediaContainer'].get('playbackState')
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


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
) -> str | None:
    """Send one timeline update and return the playbackState Plex reported.

    Returns None when the update could not be read at all, which callers must
    treat as "unknown" rather than "finished".
    """
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
            timeout=aiohttp.ClientTimeout(total=TIMELINE_TIMEOUT),
        ) as response:
            body = await response.read()
            if response.status >= 400:
                logger.warning(
                    'Plex timeline update failed with HTTP %s',
                    response.status,
                )
                return None
        return _playback_state(body)
    except Exception:
        # Timeline reporting is optional and must never interrupt playback.
        logger.warning('Unable to send Plex timeline update', exc_info=True)
        return None


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
    stream_base,
    part_key,
    access_token,
    headers,
):
    upstream = stream_base / part_key[1:] % {'X-Plex-Token': access_token}
    return await requester(
        upstream,
        headers=headers,
        timeout=aiohttp.ClientTimeout(
            total=None,
            sock_connect=15,
            # aiohttp's socket timer keeps running when Plexio is backpressured
            # by a full downstream player buffer. Keep it disabled here and
            # time only active media reads in the response iterator instead.
            sock_read=None,
        ),
    )


async def _read_playback_chunk(resp):
    """Read one requested upstream chunk without timing downstream idle time."""
    try:
        async with asyncio.timeout(UPSTREAM_READ_TIMEOUT):
            return await resp.content.read(CHUNK)
    except TimeoutError:
        logger.warning(
            'Plex playback upstream produced no media for %.0f seconds',
            UPSTREAM_READ_TIMEOUT,
        )
        raise


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
    resp = await _open_playback_response(
        requester=requester,
        # Plex-discovered alternates describe routes available to playback
        # clients, not necessarily routes available from Plexio's container.
        # The selected streaming URL is the only upstream explicitly chosen
        # for server-side proxying, so never leave it for a .plex.direct route.
        stream_base=configuration.streaming_url,
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
            while chunk := await _read_playback_chunk(resp):
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


def direct_play_url(*, configuration, part_key, identifier):
    """Build a Plex part URL that attributes the session to this install.

    Plex reaps any session it never observes as playing. Carrying the client
    identity in the query string means the player's own request creates the
    session, so keepalive updates land on that session instead of creating a
    second, disconnected one.
    """
    return str(
        configuration.streaming_url
        / part_key[1:]
        % {
            'X-Plex-Token': configuration.access_token,
            'X-Plex-Client-Identifier': _client_id(identifier),
            'X-Plex-Product': PLEX_PRODUCT,
            'X-Plex-Device-Name': PLEX_PRODUCT,
            'X-Plex-Platform': 'Stremio',
        }
    )


async def _keepalive_loop(
    client,
    *,
    url,
    token,
    rating_key,
    duration_ms,
    identifier,
):
    """Hold a Plex session open as playing without touching media bytes.

    The player was redirected straight to Plex, so this only sends timeline
    updates. It ends once Plex stops reporting the session as in progress, or
    when the runtime is well past the item duration so a closed player cannot
    leave a phantom session behind on a shared server.

    Two consecutive unreadable progress states are required before giving up,
    so a single blip during a seek does not abandon a live session.
    """
    started_at = monotonic()
    deadline = started_at + max(duration_ms, 0) / 1000 + KEEPALIVE_GRACE

    def position(now):
        return _position_ms(
            total=None,
            start=0,
            duration_ms=duration_ms,
            started_at=started_at,
            now=now,
        )

    now = started_at
    untracked = 0
    while True:
        playback_state = await _timeline(
            client,
            url=url,
            token=token,
            rating_key=rating_key,
            state='playing',
            time_ms=position(now),
            duration_ms=duration_ms,
            identifier=identifier,
        )
        untracked = 0 if playback_state in (None, 'progress') else untracked + 1
        await asyncio.sleep(PING_INTERVAL)
        now = monotonic()
        if now >= deadline or untracked >= 2:
            break

    await _timeline(
        client,
        url=url,
        token=token,
        rating_key=rating_key,
        state='stopped',
        time_ms=position(now),
        duration_ms=duration_ms,
        identifier=identifier,
    )


def start_keepalive(
    *,
    client,
    configuration,
    rating_key,
    duration_ms,
    part_key,
    identifier,
):
    """Redirect the player to Plex and keep its session marked as playing.

    No media crosses Plexio. Only the background timeline task does work, so
    this is the mode for a self-hosted Plexio sitting away from the server.
    """
    target = direct_play_url(
        configuration=configuration,
        part_key=part_key,
        identifier=identifier,
    )
    task = asyncio.create_task(
        _keepalive_loop(
            client,
            url=configuration.discovery_url,
            token=configuration.access_token,
            rating_key=rating_key,
            duration_ms=duration_ms,
            identifier=identifier,
        ),
        name='plexio-playback-keepalive',
    )
    _KEEPALIVE_TASKS.add(task)
    task.add_done_callback(_KEEPALIVE_TASKS.discard)
    logger.info('Started Plex keepalive for a %d ms item', duration_ms)
    return RedirectResponse(target, status_code=302)
