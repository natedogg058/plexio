import os
from contextlib import asynccontextmanager
from pathlib import Path

import aiohttp
import sentry_sdk
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from plexio.cache import init_cache
from plexio.routers.addon import router as addon_router
from plexio.routers.configuration import router as configuration_router
from plexio.routers.plex_proxy import router as plex_proxy_router
from plexio.security import RequestBodyLimitMiddleware, SecurityHeadersMiddleware
from plexio.sessions import init_sessions
from plexio.settings import settings
from plexio.static import SPAStaticFiles


def before_send(event, hint):
    if 'exc_info' in hint:
        exc_type, exc_value, tb = hint['exc_info']
        if isinstance(exc_value, HTTPException) and exc_value.status_code in (502, 504):
            return None
    return event


sentry_sdk.init(before_send=before_send)


@asynccontextmanager
async def lifespan(app: FastAPI):
    plex_client = aiohttp.ClientSession(
        headers={'accept': 'application/json'},
    )
    cache = init_cache(settings)
    sessions = await init_sessions(settings)

    yield {
        'plex_client': plex_client,
        'cache': cache,
        'sessions': sessions,
    }

    await plex_client.close()
    await cache.close()
    if sessions is not None:
        await sessions.close()


app = FastAPI(
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
app.add_middleware(
    RequestBodyLimitMiddleware,
    max_body_size=settings.max_request_body_size,
)
if settings.allowed_host_list:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.allowed_host_list,
    )
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(addon_router)
app.include_router(configuration_router)
app.include_router(plex_proxy_router)

frontend_dir = Path(os.getenv('PLEXIO_FRONTEND_DIR', 'frontend/dist'))
if frontend_dir.is_dir():
    app.mount('/', SPAStaticFiles(directory=frontend_dir, html=True), name='frontend')
