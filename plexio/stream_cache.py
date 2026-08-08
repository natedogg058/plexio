import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar
from urllib.parse import quote

from pydantic import BaseModel

from plexio.models.stremio import StremioStreamsResponse

logger = logging.getLogger(__name__)

ModelT = TypeVar('ModelT', bound=BaseModel)

_TOKEN_PLACEHOLDER = '__PLEXIO_ACCESS_TOKEN__'
_ENCODED_TOKEN_PLACEHOLDER = '__PLEXIO_ENCODED_ACCESS_TOKEN__'


def configuration_cache_namespace(configuration) -> str:
    """Return a secret-safe, configuration-specific cache namespace."""
    if hasattr(configuration, 'to_storage_dict'):
        payload = configuration.to_storage_dict()
    else:
        payload = vars(configuration)
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()


def resource_cache_key(namespace: str, resource: str, identity: str) -> str:
    identity_hash = hashlib.sha256(identity.encode()).hexdigest()
    return f'plexio:{resource}:{namespace}:{identity_hash}'


async def cache_get(cache, key: str) -> str | None:
    if cache is None or not hasattr(cache, 'get'):
        return None
    try:
        return await cache.get(key)
    except Exception:  # pragma: no cover - defensive cache isolation
        logger.warning('Cache read failed for %s', key.split(':', 2)[1])
        return None


async def cache_set(cache, key: str, value: str, *, ttl: int) -> None:
    if cache is None or not hasattr(cache, 'set') or ttl <= 0:
        return
    try:
        await cache.set(key, value, ttl=ttl)
    except Exception:  # pragma: no cover - defensive cache isolation
        logger.warning('Cache write failed for %s', key.split(':', 2)[1])


async def cached_model_list(
    *,
    cache,
    key: str,
    model: type[ModelT],
    loader: Callable[[], Awaitable[list[ModelT]]],
    ttl: int,
) -> tuple[list[ModelT], bool]:
    cached = await cache_get(cache, key) if ttl > 0 else None
    if cached is not None:
        try:
            return [model.model_validate(item) for item in json.loads(cached)], True
        except (TypeError, ValueError):
            logger.warning('Ignoring invalid cached %s value', key.split(':', 2)[1])

    value = await loader()
    serialized = json.dumps(
        [item.model_dump(mode='json', by_alias=True) for item in value],
        separators=(',', ':'),
    )
    await cache_set(cache, key, serialized, ttl=ttl)
    return value, False


def serialize_stream_response(
    response: StremioStreamsResponse,
    access_token: str,
) -> str:
    """Serialize a stream response without persisting the Plex token."""
    serialized = response.model_dump_json(by_alias=True, exclude_none=True)
    if not access_token:
        return serialized
    encoded = quote(access_token, safe='')
    if encoded != access_token:
        serialized = serialized.replace(encoded, _ENCODED_TOKEN_PLACEHOLDER)
    return serialized.replace(access_token, _TOKEN_PLACEHOLDER)


def deserialize_stream_response(
    serialized: str,
    access_token: str,
) -> StremioStreamsResponse:
    if access_token:
        serialized = serialized.replace(_TOKEN_PLACEHOLDER, access_token)
        serialized = serialized.replace(
            _ENCODED_TOKEN_PLACEHOLDER,
            quote(access_token, safe=''),
        )
    return StremioStreamsResponse.model_validate_json(serialized)
