import asyncio
from typing import Any

import aiohttp
from aiohttp import ClientSession
from fastapi import HTTPException, status
from yarl import URL

from plexio.settings import settings

PLEX_API_URL = 'https://plex.tv/api/v2'
PLEX_HEADERS = {
    'Accept': 'application/json',
    'X-Plex-Product': 'Plexio',
    'X-Plex-Version': '1.0.0',
}


async def plex_request(
    http: ClientSession,
    method: str,
    path: str,
    *,
    headers: dict[str, str],
    params: dict[str, str | int] | None = None,
) -> Any:
    try:
        async with http.request(
            method,
            f'{PLEX_API_URL}{path}',
            headers={**PLEX_HEADERS, **headers},
            params=params,
            timeout=settings.plex_requests_timeout,
            allow_redirects=False,
        ) as response:
            if response.status >= 400:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f'Plex API returned HTTP {response.status}',
                )
            return await response.json()
    except HTTPException:
        raise
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail='Unable to reach the Plex API',
        ) from exc


async def fetch_plex_resources(
    http: ClientSession,
    token: str,
    client_identifier: str,
) -> list[dict]:
    resources = await plex_request(
        http,
        'GET',
        '/resources',
        headers={
            'X-Plex-Client-Identifier': client_identifier,
            'X-Plex-Token': token,
        },
        params={'includeHttps': 1, 'includeRelay': 1},
    )
    return resources if isinstance(resources, list) else []


def is_authorized_connection(
    resources: list[dict],
    *,
    server_name: str,
    url: URL,
    server_token: str,
) -> bool:
    requested = str(url).rstrip('/')
    for resource in resources:
        if resource.get('name') != server_name or 'server' not in str(
            resource.get('provides', '')
        ).split(','):
            continue
        resource_token = resource.get('accessToken')
        if resource_token and resource_token != server_token:
            continue
        for connection in resource.get('connections') or []:
            try:
                candidate = URL(connection.get('uri', ''))
            except (TypeError, ValueError):
                continue
            if str(candidate).rstrip('/') == requested:
                return True
    return False
