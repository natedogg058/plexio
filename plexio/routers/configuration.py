from typing import Annotated

from aiohttp import ClientSession
from fastapi import APIRouter, Depends
from yarl import URL

from plexio.dependencies import get_http_client
from plexio.plex.media_server_api import check_server_connection
from plexio.settings import settings

router = APIRouter(prefix='/api/v1')


@router.get('/test-connection')
async def test_connection(
    http: Annotated[ClientSession, Depends(get_http_client)],
    url: str,
    token: str,
):
    success = await check_server_connection(
        client=http,
        url=URL(url),
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
    return {'base_url': settings.base_url or ''}
