# Security policy

## Supported releases

Security fixes are applied to the latest maintained release.

## Reporting a vulnerability

Please use GitHub's private **Report a vulnerability** flow in the Security tab
of this repository. Do not open a public issue for an unpatched vulnerability.

Include the affected version, deployment shape, reproduction steps, and impact.
Remove all Plex access tokens, session IDs, private hostnames, and media paths.

## Operator guidance

- Keep server-side sessions enabled and legacy configuration URLs disabled.
- Set `BASE_URL` and, where practical, `ALLOWED_HOSTS` on public deployments.
- Trust forwarded headers only behind a proxy you control.
- Protect `/api/v1/sessions` with a strong `ADMIN_KEY` and network controls.
- Back up `/data/session.key` with the session database; rotate/revoke leaked
  session IDs and Plex tokens promptly.
