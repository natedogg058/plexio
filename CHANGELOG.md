# Changelog

## v0.10.1

- Moved Plex timeline heartbeats into an independent playback task so external
  players remain active when their downstream buffers pause media reads.
- Removed the playback proxy's fixed upstream read timeout and attached the
  same stable Plex client identity to media and timeline requests.

## v0.10.0

- Added expiring, token-scrubbed complete stream-response caching and short-lived
  Plex media/episode metadata caching, with configurable TTLs.
- Added persistent Redis deployment support for cache entries that survive
  Plexio updates and restarts.
- Parallelized matching media-detail requests across Plex libraries.
- Prioritized broadly compatible, moderate-bitrate Direct Play versions ahead
  of very large/high-bitrate remuxes while preserving quality metadata.
- Added sanitized stream timing logs plus `Server-Timing` and cache-status
  response headers for playback-start diagnostics.
- Reduced the default Plex API timeout to 10 seconds and disabled raw uvicorn
  access logs so rejected legacy URLs cannot persist embedded Plex tokens.

## v0.9.0

- Added a Direct Play switch so shared-server users can choose Plex transcodes
  when original-file playback is unavailable.
- Added optional, labelled Direct Play choices for all authorized local, remote,
  and Plex Relay server connections.
- Playback-reporting streams now retry alternate connections after network
  errors and HTTP 502/503/504 responses.
- Stream descriptions now normalize source resolution, video/audio codecs,
  Dolby Vision and HDR variants, audio channels, bitrate, languages, subtitles,
  and human-readable file size while retaining Stremio filename/size hints.
- Added opt-in discovery and individual selection of Plex movie/show
  collections as stable, paginated Stremio catalogs.

## v0.8.2

- Updated and hash-locked the Python runtime dependencies; both Python and npm
  vulnerability audits now run in CI.
- Replaced archived NGINX Unit with a current Python/uvicorn runtime while
  retaining port `80`, UID/GID `999`, and multi-architecture compatibility.
- Restricted public connection probes and session creation to connections
  authorized by the signed-in Plex account; tokens now travel in headers.
- Added strict configuration schemas, request-size limits, per-client rate
  limits, a session quota, no-redirect connection probes, trusted-host support,
  and browser security headers.
- Changed browser token persistence from local storage to tab-scoped session
  storage. Legacy token-bearing install URLs are now opt-in and use URL-safe
  Base64 when enabled.
- Added container smoke tests, CodeQL, Dependabot, SBOM/provenance publication,
  support templates, security policy, deployment documentation, and fork-owned
  branding.

## v0.8.1

- Fixed self-hosted Plex Auth App origin handling.
- Added elapsed-time playback reporting and reliable HEAD/range proxy behavior.
- Published multi-architecture `amd64` and `arm64` images.

## v0.8.0

- Added server-side Plex authentication and server discovery.
- Added hybrid IMDb/Plex-native IDs for unmatched personal media.
- Added stream filenames for Stremio-compatible release fingerprinting.

Earlier maintained-fork changes are summarized in the GitHub releases and commit
history.
