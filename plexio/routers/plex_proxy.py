from typing import Annotated

from aiohttp import ClientSession
from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Path,
    Query,
    Request,
    status,
)
from yarl import URL

from plexio.dependencies import get_http_client
from plexio.plex.plex_tv import (
    fetch_plex_resources,
    plex_request as _plex_request,
)
from plexio.settings import settings

router = APIRouter(prefix='/api/v1')


def _request_origin(request: Request) -> str:
    """Return the public browser origin Plex should bind to a new PIN."""
    candidates = [
        request.headers.get('origin'),
        request.headers.get('referer'),
        settings.base_url,
    ]
    forwarded_proto = request.headers.get('x-forwarded-proto')
    forwarded_host = request.headers.get('x-forwarded-host')
    if settings.trust_proxy_headers and forwarded_proto and forwarded_host:
        candidates.append(
            f'{forwarded_proto.split(",", 1)[0].strip()}://'
            f'{forwarded_host.split(",", 1)[0].strip()}'
        )
    candidates.append(str(request.url))

    for candidate in candidates:
        if not candidate or candidate == 'null':
            continue
        try:
            origin = URL(candidate).origin()
        except (TypeError, ValueError):
            continue
        if origin.scheme in {'http', 'https'} and origin.host:
            return str(origin)

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail='Unable to determine a valid public origin',
    )


@router.post('/plex-pin')
async def create_plex_pin(
    request: Request,
    http: Annotated[ClientSession, Depends(get_http_client)],
    client_identifier: str = Header(
        ...,
        alias='X-Plex-Client-Identifier',
        min_length=1,
        max_length=255,
    ),
):
    return await _plex_request(
        http,
        'POST',
        '/pins',
        headers={
            'X-Plex-Client-Identifier': client_identifier,
            # Plex validates the Auth App forwardUrl hostname against the
            # origin recorded when the PIN is created.
            'Origin': _request_origin(request),
        },
        params={'strong': 'true'},
    )


@router.get('/plex-token/{pin_id}')
async def get_plex_token(
    http: Annotated[ClientSession, Depends(get_http_client)],
    pin_id: int = Path(..., gt=0),
    client_identifier: str = Header(
        ...,
        alias='X-Plex-Client-Identifier',
        min_length=1,
        max_length=255,
    ),
    code: str = Query(..., min_length=1, max_length=255),
):
    return await _plex_request(
        http,
        'GET',
        f'/pins/{pin_id}',
        headers={'X-Plex-Client-Identifier': client_identifier},
        params={'code': code},
    )


@router.get('/plex-resources')
async def get_plex_resources(
    http: Annotated[ClientSession, Depends(get_http_client)],
    client_identifier: str = Header(
        ...,
        alias='X-Plex-Client-Identifier',
        min_length=1,
        max_length=255,
    ),
    token: str = Header(
        ...,
        alias='X-Plex-Token',
        min_length=1,
        max_length=4096,
    ),
    include_https: int = Query(1, alias='includeHttps', ge=0, le=1),
    include_relay: int = Query(1, alias='includeRelay', ge=0, le=1),
):
    if include_https == 1 and include_relay == 1:
        return await fetch_plex_resources(http, token, client_identifier)
    return await _plex_request(
        http,
        'GET',
        '/resources',
        headers={
            'X-Plex-Client-Identifier': client_identifier,
            'X-Plex-Token': token,
        },
        params={'includeHttps': include_https, 'includeRelay': include_relay},
    )
