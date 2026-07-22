# Plexio — CORS Fix Fork

This is a fork of [natedogg058/plexio](https://github.com/natedogg058/plexio) that fixes Plex auth on self-hosted instances.

## What was broken

Plex blocked direct browser calls to `plex.tv/api/v2/pins`, causing `code=undefined` in the OAuth redirect and breaking login on every self-hosted Plexio instance.

## What this fixes

Three Plex API calls are now proxied through the backend instead of the browser:
- PIN creation
- Token exchange
- Server list

## Quick start

```yaml
services:
  plexio:
    image: ghcr.io/senserpro/plexio:latest
    container_name: plexio
    restart: unless-stopped
    volumes:
      - plexio-data:/data
    environment:
      - CORS_ORIGIN_REGEX=https?:\/\/localhost:\d+|.*strem.io|.*stremio.com|.*YOUR-DOMAIN.com
      - PLEX_REQUESTS_TIMEOUT=20
      - CACHE_TYPE=redis
      - REDIS_URL=redis://plexio-redis:6379/0
      - BASE_URL=https://plexio.YOUR-DOMAIN.com
      # Only needed if using a shared Plex server you do not own:
      # - PLEX_MATCHING_TOKEN=your_plex_token_here
    depends_on:
      - redis

  redis:
    image: redis:alpine
    container_name: plexio-redis
    restart: unless-stopped
    volumes:
      - /opt/plexio/redis-data:/data

volumes:
  plexio-data:
```

Replace `YOUR-DOMAIN.com` with your own domain. Add your reverse proxy labels (Traefik, Nginx Proxy Manager, etc.) as needed.

## Credits

- Original: [vanchaxy/plexio](https://github.com/vanchaxy/plexio)
- Maintained fork: [natedogg058/plexio](https://github.com/natedogg058/plexio)
- CORS fix: [senserpro/plexio](https://github.com/senserpro/plexio)
