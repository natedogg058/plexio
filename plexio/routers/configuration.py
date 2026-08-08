from typing import Annotated

from aiohttp import ClientSession
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from plexio import __version__
from plexio.dependencies import (
    get_addon_configuration,
    get_http_client,
    verify_admin_key,
)
from plexio.models.addon import AddonConfiguration, validate_plex_url
from plexio.plex.media_server_api import check_server_connection
from plexio.plex.plex_tv import fetch_plex_resources, is_authorized_connection
from plexio.rate_limit import limit_public_api
from plexio.sessions import SessionCapacityError
from plexio.settings import settings

router = APIRouter(prefix='/api/v1')


@router.get('/test-connection', dependencies=[Depends(limit_public_api)])
async def test_connection(
    http: Annotated[ClientSession, Depends(get_http_client)],
    url: str = Query(..., min_length=8, max_length=2048),
    server_name: str = Query(..., min_length=1, max_length=255),
    token: str = Header(..., alias='X-Plex-Token', min_length=1, max_length=4096),
    account_token: str = Header(
        ...,
        alias='X-Plex-Account-Token',
        min_length=1,
        max_length=4096,
    ),
    client_identifier: str = Header(
        ...,
        alias='X-Plex-Client-Identifier',
        min_length=1,
        max_length=255,
    ),
):
    try:
        candidate = validate_plex_url(url)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    resources = await fetch_plex_resources(
        http,
        account_token,
        client_identifier,
    )
    if not is_authorized_connection(
        resources,
        server_name=server_name,
        url=candidate,
        server_token=token,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='URL is not an authorized connection for this Plex server',
        )
    success = await check_server_connection(
        client=http,
        url=candidate,
        token=token,
    )
    return {'success': success}


@router.get('/public-config')
async def public_config():
    """
    Return runtime configuration safe to expose to the frontend.

    Currently surfaces base_url so the configure UI can generate install URLs
    using the operator-specified public origin instead of window.location.origin.
    Empty string when unset -- frontend falls back to window.location.origin.
    """
    return {
        'base_url': settings.base_url or '',
        'legacy_urls_enabled': settings.enable_legacy_urls,
    }


@router.get('/health')
async def health(request: Request):
    """Liveness probe: confirm the app is up and its session store (if enabled)
    is reachable. Does not contact any Plex server -- suitable for the container
    healthcheck and uptime monitors. Returns 503 if the store is unreachable."""
    store = getattr(request.state, 'sessions', None)
    sessions_ok = True
    if store is not None:
        try:
            await store.ping()
        except Exception:
            sessions_ok = False
    if not sessions_ok:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='Session store unreachable',
        )
    return {
        'status': 'ok',
        'version': __version__,
        'sessions': {'enabled': store is not None},
    }


@router.get('/health/{session_id}')
async def health_backend(
    request: Request,
    session_id: str,
    http: Annotated[ClientSession, Depends(get_http_client)],
):
    """Deep health check: resolve a session's config and probe whether its Plex
    backend is reachable. Returns reachability only -- never the token. 404 if
    the session is unknown or sessions are disabled. Point an uptime monitor here
    to alert when the backing Plex server goes down, not just the web app."""
    configuration = await get_addon_configuration(request, session_id=session_id)
    reachable = await check_server_connection(
        client=http,
        url=configuration.discovery_url,
        token=configuration.access_token,
    )
    return {'session_id': session_id, 'backend_reachable': reachable}


@router.post('/sessions', dependencies=[Depends(limit_public_api)])
async def create_session(
    request: Request,
    http: Annotated[ClientSession, Depends(get_http_client)],
    config: AddonConfiguration,
    account_token: str = Header(
        ...,
        alias='X-Plex-Account-Token',
        min_length=1,
        max_length=4096,
    ),
    client_identifier: str = Header(
        ...,
        alias='X-Plex-Client-Identifier',
        min_length=1,
        max_length=255,
    ),
    label: str | None = Query(default=None, min_length=1, max_length=255),
):
    """Create a server-side session that stores the addon configuration.

    The request body is the addon configuration as camelCase JSON -- the
    same shape legacy base64 install URLs carry. Optional `label` query
    param tags the install for later identification. Returns the session
    id to embed in the install URL: /{session_id}/manifest.json
    """
    store = getattr(request.state, 'sessions', None)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Sessions are not enabled',
        )
    resources = await fetch_plex_resources(http, account_token, client_identifier)
    urls_authorized = all(
        is_authorized_connection(
            resources,
            server_name=config.server_name,
            url=url,
            server_token=config.access_token,
        )
        for url in (config.discovery_url, config.streaming_url)
    )
    if not urls_authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Configuration contains an unauthorized Plex connection',
        )
    try:
        session_id = await store.create(config.to_storage_dict(), label=label)
    except SessionCapacityError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail='Session capacity reached; revoke an unused session and retry',
        ) from exc
    return {'session_id': session_id}


@router.get('/sessions', dependencies=[Depends(verify_admin_key)])
async def list_sessions(request: Request):
    """List stored sessions (metadata only, never tokens). Requires X-Admin-Key."""
    store = getattr(request.state, 'sessions', None)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Sessions are not enabled',
        )
    return {'sessions': await store.list()}


@router.delete('/sessions/{session_id}', dependencies=[Depends(verify_admin_key)])
async def delete_session(request: Request, session_id: str):
    """Revoke (delete) a stored session by id. Requires X-Admin-Key."""
    store = getattr(request.state, 'sessions', None)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Sessions are not enabled',
        )
    if not await store.delete(session_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Session not found',
        )
    return {'deleted': session_id}
