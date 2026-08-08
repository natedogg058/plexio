# Plexio

Plexio is a self-hosted Stremio addon for discovering and streaming media from
Plex. This repository is the actively maintained fork of
[vanchaxy/plexio](https://github.com/vanchaxy/plexio).

Plexio is independent and is not affiliated with Plex or Stremio.

## Highlights

- Configurable Direct Play and optional Plex transcoding streams.
- Local, remote, shared-server, and Plex Relay connections.
- Clearly labelled alternate-connection streams, with automatic proxy fallback.
- Continue Watching, Recently Added, searchable library, and sort catalogs.
- IMDb IDs when available, with Plex-native IDs for personal or unmatched media.
- Stremio stream metadata including filename and file size.
- Server-side Plex authentication for reliable self-hosted sign-in.
- Short install URLs backed by encrypted, revocable SQLite sessions.
- Optional playback reporting through a range-aware playback proxy.
- Multi-architecture Docker images for `linux/amd64` and `linux/arm64`.

## Quick start

```bash
docker run -d \
  --name plexio \
  -p 7777:80 \
  -v plexio-data:/data \
  --restart unless-stopped \
  ghcr.io/natedogg058/plexio:latest
```

Open `http://localhost:7777`, sign in to Plex, choose the server connections and
libraries you want, then install the generated manifest in Stremio.

Use a named volume as shown above. The container runs as unprivileged UID/GID
`999`; if you use a bind mount, make its directory writable by that identity.

## Configuration

Copy [`.env.example`](.env.example) when deploying through Compose or another
orchestrator. Common settings are:

| Variable | Default | Purpose |
| --- | --- | --- |
| `BASE_URL` | unset | Canonical public Plexio URL, strongly recommended behind a proxy. |
| `ALLOWED_HOSTS` | unset | Comma-separated HTTP Host allowlist, for example `plexio.example.com`. |
| `TRUST_PROXY_HEADERS` | `false` | Trust `X-Forwarded-Proto/Host`; enable only behind your own proxy. |
| `ENABLE_SESSIONS` | `true` | Store encrypted configuration outside install URLs. |
| `SESSION_DB_PATH` | `/data/sessions.db` | SQLite session database. |
| `SESSION_ENCRYPTION_KEY` | auto-generated | Stable Fernet key; back it up if supplied manually. |
| `MAX_SESSIONS` | `1000` | Maximum stored installs; identical configs are deduplicated. |
| `ADMIN_KEY` | unset | Enables authenticated session list/revoke endpoints. |
| `ENABLE_LEGACY_URLS` | `false` | Opt in to token-bearing legacy URLs when sessions are disabled. |
| `MAX_REQUEST_BODY_SIZE` | `65536` | Maximum POST/PUT/PATCH body size in bytes. |
| `PUBLIC_API_RATE_LIMIT` | `60` | Per-client connection-test/session requests per minute. |
| `PLEX_REQUESTS_TIMEOUT` | `20` | Plex request timeout in seconds. |
| `PLEX_MATCHING_TOKEN` | unset | Token from an owned server for metadata matching on shared servers. |
| `CACHE_TYPE` | `memory` | `memory` or `redis`. |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection URL. |
| `CORS_ORIGIN_REGEX` | built-in | Override allowed configure-page browser origins. |

Session administration uses the `X-Admin-Key` header:

```bash
curl -H 'X-Admin-Key: your-key' https://plexio.example.com/api/v1/sessions
curl -X DELETE -H 'X-Admin-Key: your-key' \
  https://plexio.example.com/api/v1/sessions/SESSION_ID
```

Legacy configuration URLs expose the Plex access token in browser history,
reverse-proxy logs, and the Stremio addon URL. Leave them disabled unless you
understand that tradeoff.

## Reverse proxies

Set `BASE_URL=https://plexio.example.com` and proxy to container port `80`.
Detailed Nginx, Caddy, Cloudflare Tunnel, Tailscale, and troubleshooting examples
are in [the reverse-proxy guide](docs/reverse-proxy.md).

If you enable “Report playback to Plex”, Direct Play streams pass through
Plexio. The public URL must then be reachable by every Stremio device and your
proxy must permit byte-range requests and long-running responses.

## Playback controls

Direct Play is enabled by default. You can turn it off when a shared server
rejects original-file playback and offer only Plex transcodes instead. Enable
“Include alternate Plex connections” to expose the selected server's other
local, remote, and Relay URLs as labelled Direct Play choices.

When playback reporting is also enabled, Plexio presents one Direct Play choice
and automatically retries those authorized connections after connection errors
or HTTP 502/503/504 responses. It does not bypass Plex account or remote-play
permissions.

## Shared servers and Plex Pass

For media matching on a server shared with you, set `PLEX_MATCHING_TOKEN` to an
access token from a Plex server you own. Plexio does not bypass Plex remote-play
rules; depending on Plex policy, remote personal-video playback may require Plex
Pass or Remote Watch Pass. Never post access tokens in issues or logs.

## Health checks

- `GET /api/v1/health` checks Plexio and its session store.
- `GET /api/v1/health/{session_id}` also checks that install's Plex server.

The deep health response reports reachability only and never returns a token.

## Development

```bash
uv run --extra dev ruff check .
uv run --extra dev python -m unittest discover -s tests -v
cd frontend
npm ci
npm run lint
npm run build
```

For the live development stack, copy `.env.example` to `.env` and run:

```bash
docker compose up --build
```

## Support and roadmap

Use [GitHub Issues](https://github.com/natedogg058/plexio/issues) for support and
feature requests. Include sanitized logs and diagnostics, but never a Plex token
or a complete media URL.

Current roadmap themes are richer stream metadata and Plex collection catalogs.

See [CHANGELOG.md](CHANGELOG.md) for maintained-fork release history.
