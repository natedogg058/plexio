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
from fastapi import HTTPException, status
from fastapi.responses import RedirectResponse, Response, StreamingResponse

PLEX_PRODUCT = 'Plexio'
CHUNK = 1 << 16  # 64 KiB
PING_INTERVAL = 10.0  # seconds between Plex timeline updates
UPSTREAM_READ_TIMEOUT = 30.0  # seconds waiting for a requested media chunk
TIMELINE_TIMEOUT = 10.0  # seconds for one timeline update against a remote server
KEEPALIVE_GRACE = 600.0  # extra seconds past the runtime before giving up
# Keepalive URLs are public, so their duration cannot be trusted to bound the
# loop. Eight hours covers any single film or episode.
MAX_KEEPALIVE_DURATION_MS = 8 * 60 * 60 * 1000
MAX_FAILED_UPDATES = 6  # consecutive failed timeline requests before giving up
MAX_KEEPALIVES = 256  # concurrent keepalive loops across all installs

# Returned by _timeline when the request itself failed, as opposed to None for
# a reply whose playbackState could not be read.
TIMELINE_FAILED = 'plexio:timeline-failed'

# Running keepalives keyed by (identifier, rating_key). Holding the task here
# also gives it the strong reference the event loop needs to keep it alive.
_KEEPALIVE_TASKS: dict[tuple[str, str], asyncio.Task] = {}

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

    Returns TIMELINE_FAILED when the request failed or Plex answered with an
    error, and None when Plex answered but the state could not be read. Callers
    must treat None as "unknown" rather than "finished".
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
                return TIMELINE_FAILED
        return _playback_state(body)
    except Exception:
        # Timeline reporting is optional and must never interrupt playback.
        logger.warning('Unable to send Plex timeline update', exc_info=True)
        return TIMELINE_FAILED


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
    try:
        # Bound only the handshake and header phase. aiohttp's own timers
        # cannot be used for this: `total` would also cover the streaming
        # body and kill long playback, while `sock_read` would fire while a
        # legitimately buffering player backpressures Plexio. A server that
        # accepts the connection but never answers headers is a hard hang.
        async with asyncio.timeout(UPSTREAM_READ_TIMEOUT):
            return await requester(
                upstream,
                headers=headers,
                timeout=aiohttp.ClientTimeout(
                    total=None,
                    sock_connect=15,
                    # aiohttp's socket timer keeps running when Plexio is
                    # backpressured by a full downstream player buffer. Keep it
                    # disabled here and time only active media reads in the
                    # response iterator instead.
                    sock_read=None,
                ),
            )
    except TimeoutError:
        logger.warning(
            'Plex playback produced no response headers for %.0f seconds',
            UPSTREAM_READ_TIMEOUT,
        )
        raise


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
    try:
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
    except TimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail='Plex server did not start playback in time',
        ) from exc
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
    updates. It ends once Plex stops reporting the session as in progress,
    once Plex has been unreachable for MAX_FAILED_UPDATES updates in a row, or
    when the runtime is well past the item duration so a closed player cannot
    leave a phantom session behind on a shared server.

    Two consecutive non-progress states are required before giving up, so a
    single blip during a seek does not abandon a live session.
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
    failed = 0
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
        if playback_state == TIMELINE_FAILED:
            failed += 1
        else:
            failed = 0
            untracked = 0 if playback_state in (None, 'progress') else untracked + 1
        if untracked >= 2 or failed >= MAX_FAILED_UPDATES:
            break
        await asyncio.sleep(PING_INTERVAL)
        now = monotonic()
        if now >= deadline:
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
    method='GET',
):
    """Redirect the player to Plex and keep its session marked as playing.

    No media crosses Plexio. Only the background timeline task does work, so
    this is the mode for a self-hosted Plexio sitting away from the server.

    Keepalive URLs are unauthenticated beyond the install, so every request is
    bounded: HEAD probes only redirect, a repeat request for an item that is
    already being kept alive reuses the running loop (players re-open the URL
    on seek or reconnect), the duration is clamped, and the total number of
    loops is capped.
    """
    target = RedirectResponse(
        direct_play_url(
            configuration=configuration,
            part_key=part_key,
            identifier=identifier,
        ),
        status_code=302,
    )
    if method.upper() == 'HEAD':
        return target

    key = (identifier, str(rating_key))
    running = _KEEPALIVE_TASKS.get(key)
    if running is not None and not running.done():
        return target
    if len(_KEEPALIVE_TASKS) >= MAX_KEEPALIVES:
        logger.warning(
            'Not starting Plex keepalive: %d already running',
            len(_KEEPALIVE_TASKS),
        )
        return target

    duration_ms = min(max(duration_ms, 0), MAX_KEEPALIVE_DURATION_MS)
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
    _KEEPALIVE_TASKS[key] = task

    def _forget(done, key=key):
        if _KEEPALIVE_TASKS.get(key) is done:
            del _KEEPALIVE_TASKS[key]

    task.add_done_callback(_forget)
    logger.info('Started Plex keepalive for a %d ms item', duration_ms)
    return target


async def stop_keepalives():
    """Cancel running keepalives, e.g. before the shared HTTP client closes."""
    tasks = list(_KEEPALIVE_TASKS.values())
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    _KEEPALIVE_TASKS.clear()
