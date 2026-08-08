# Changelog

## Unreleased

- Added a Direct Play switch so shared-server users can choose Plex transcodes
  when original-file playback is unavailable.
- Added optional, labelled Direct Play choices for all authorized local, remote,
  and Plex Relay server connections.
- Playback-reporting streams now retry alternate connections after network
  errors and HTTP 502/503/504 responses.

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
