import base64
import json

from aiohttp import ClientSession
from fastapi import Header, HTTPException, Request, status
from sentry_sdk import set_user

from plexio.models.addon import AddonConfiguration
from plexio.settings import settings


def get_http_client(request: Request) -> ClientSession:
    return request.state.plex_client


def get_cache(request: Request):
    return request.state.cache


async def get_addon_configuration(
    request: Request,
    base64_cfg: str | None = None,
    session_id: str | None = None,
) -> AddonConfiguration | None:
    # Legacy form: the full config is base64-encoded in the URL itself.
    if base64_cfg is not None:
        if not settings.enable_legacy_urls:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Legacy configuration URLs are disabled',
            )
        try:
            padding = '=' * (-len(base64_cfg) % 4)
            decoded = base64.urlsafe_b64decode(base64_cfg + padding)
            return AddonConfiguration(**json.loads(decoded))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Invalid legacy configuration URL',
            ) from exc
    # Session form: config is stored server-side, keyed by session id.
    if session_id is not None:
        store = getattr(request.state, 'sessions', None)
        if store is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Sessions are not enabled',
            )
        configuration = await store.get_config(session_id)
        if configuration is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Session not found',
            )
        return configuration
    # Unconfigured: bare manifest with no install context.
    return None


def set_sentry_user(
    installation_id: str | None = None,
    session_id: str | None = None,
) -> None:
    identifier = installation_id or session_id
    if identifier:
        set_user({'id': identifier})


def verify_admin_key(x_admin_key: str | None = Header(default=None)) -> None:
    """Gate session administration (list/revoke) behind the ADMIN_KEY header.

    Closed by default: if ADMIN_KEY is unset the endpoints are disabled (403),
    so sessions can never be enumerated or deleted without an explicit key.
    """
    if not settings.admin_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Session administration is disabled (ADMIN_KEY unset)',
        )
    if x_admin_key != settings.admin_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid or missing admin key',
        )
