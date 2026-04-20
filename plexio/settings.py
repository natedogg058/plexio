from pydantic_settings import BaseSettings

from plexio.cache import CacheType


class Settings(BaseSettings):
    # Expanded default to cover common self-hosted scenarios:
    # - localhost and 127.0.0.1 on any port
    # - private LAN ranges (192.168.x.x, 10.x.x.x, 172.16-31.x.x)
    # - Tailscale tailnet domains (*.ts.net)
    # - app.strem.io (the official web client)
    # - original upstream matches (plexio.stream, strem.io, stremio.com)
    cors_origin_regex: str = (
        r'https?:\/\/localhost(:\d+)?'
        r'|https?:\/\/127\.0\.0\.1(:\d+)?'
        r'|https?:\/\/192\.168\.\d+\.\d+(:\d+)?'
        r'|https?:\/\/10\.\d+\.\d+\.\d+(:\d+)?'
        r'|https?:\/\/172\.(1[6-9]|2\d|3[01])\.\d+\.\d+(:\d+)?'
        r'|https?:\/\/.*\.ts\.net(:\d+)?'
        r'|https?:\/\/app\.strem\.io'
        r'|.*plexio\.stream|.*strem\.io|.*stremio\.com'
    )
    plex_requests_timeout: int = 20
    cache_type: CacheType = CacheType.memory
    redis_url: str = 'redis://redis:6399/0'
    plex_matching_token: str | None = None


settings = Settings()
