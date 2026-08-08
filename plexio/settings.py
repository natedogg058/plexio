from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from plexio.cache import CacheType


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

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
    redis_url: str = 'redis://redis:6379/0'
    plex_matching_token: str | None = None
    # Public-facing URL behind a reverse proxy or tunnel. The configure page
    # falls back to window.location.origin when this is unset.
    base_url: str | None = None
    # Forwarded headers are only trustworthy when Plexio is behind a reverse
    # proxy controlled by the operator. BASE_URL remains the safer default.
    trust_proxy_headers: bool = False
    # Comma-separated host names accepted by the ASGI Host middleware. Unset
    # preserves self-hosted setups that use changing local/tunnel host names.
    allowed_hosts: str | None = None
    max_request_body_size: int = Field(default=65_536, ge=1024, le=1_048_576)
    public_api_rate_limit: int = Field(default=60, ge=1, le=10_000)

    # Server-side session storage (0.4.0): store config/token in SQLite keyed
    # by session id in the URL, instead of base64 in the install URL itself.
    session_db_path: str = '/data/sessions.db'
    # Gates session list/revoke endpoints; those endpoints return 403 if unset.
    admin_key: str | None = None
    enable_sessions: bool = True
    # Legacy URLs expose the Plex token in the URL. They remain available only
    # as an explicit compatibility escape hatch for sessions-disabled installs.
    enable_legacy_urls: bool = False
    max_sessions: int = Field(default=1000, ge=1, le=100_000)
    # Fernet key; an adjacent key file is created when this is unset.
    session_encryption_key: str | None = None

    @property
    def allowed_host_list(self) -> list[str]:
        if not self.allowed_hosts:
            return []
        return [host.strip() for host in self.allowed_hosts.split(',') if host.strip()]


settings = Settings()
