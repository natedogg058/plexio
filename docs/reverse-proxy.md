# Reverse proxy guide

Plexio listens on container port `80`. Set `BASE_URL` to the exact origin users
and Stremio devices can reach:

```env
BASE_URL=https://plexio.example.com
ALLOWED_HOSTS=plexio.example.com
```

`BASE_URL` avoids relying on client-supplied forwarding headers. Leave
`TRUST_PROXY_HEADERS=false` unless requests can only arrive through a proxy you
control.

## Nginx

```nginx
server {
    listen 443 ssl http2;
    server_name plexio.example.com;

    location / {
        proxy_pass http://127.0.0.1:7777;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 1h;
        proxy_request_buffering off;
        proxy_buffering off;
    }
}
```

If `TRUST_PROXY_HEADERS=true`, restrict direct access to Plexio's port so clients
cannot forge `X-Forwarded-Host` or `X-Forwarded-Proto`.

## Caddy

```caddyfile
plexio.example.com {
    reverse_proxy 127.0.0.1:7777 {
        flush_interval -1
    }
}
```

## Cloudflare Tunnel

Point the tunnel at Plexio's internal HTTP service:

```yaml
ingress:
  - hostname: plexio.example.com
    service: http://plexio:80
  - service: http_status:404
```

Do not put an interactive Cloudflare Access login in front of manifest, catalog,
metadata, stream, or playback routes; Stremio cannot complete that browser login.
Use Plexio's session IDs as secrets and protect only administrative endpoints at
the network/proxy layer if additional controls are needed.

Cloudflare 502/520/522-style pages mean the tunnel or proxy did not receive a
valid response from Plexio. Check, in order:

1. `GET /api/v1/health` directly on the container network.
2. The tunnel service target and port (`80` in the container).
3. Plexio and tunnel logs at the same timestamp.
4. TLS mode and origin certificate settings if the origin service itself uses HTTPS.
5. Whether the error concerns Plexio's hostname or the selected Plex server URL.

The selected Discovery URL is a separate connection from the URL hosting Plexio.
Its **Test** button verifies that the Plexio backend can reach that exact Plex
connection. The Streaming URL test verifies reachability from the browser/device.

## Tailscale

For a tailnet-only install, set `BASE_URL` to the machine's HTTPS tailnet name,
for example `https://plexio.example.ts.net`, and proxy or serve container port
`80` through Tailscale Serve. Every Stremio device must be on the same tailnet.

## Path prefixes

An origin such as `https://example.com/plexio` works only if the proxy strips the
`/plexio` prefix before forwarding to Plexio. Host-based routing is simpler and
recommended.

## Playback proxy notes

The optional playback-reporting mode carries the video response through Plexio.
The proxy must preserve `Range` requests and response headers, avoid buffering,
allow long-lived downloads, and permit the size/bandwidth of your media. Test a
copied stream URL with the Plex token removed before sharing diagnostics.
