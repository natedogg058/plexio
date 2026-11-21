# Trusting a custom Plex HTTPS CA bundle

Plexio verifies HTTPS certificates when connecting to Plex. If your Plex server uses a certificate chain that is not in the container's trust store, supply a PEM CA bundle with `PLEX_CA_BUNDLE`. Do not disable TLS verification.

Example Docker options:

```sh
-v /path/to/ca-bundle.pem:/etc/ssl/plexio-ca.pem:ro \
-e PLEX_CA_BUNDLE=/etc/ssl/plexio-ca.pem
```

The certificates in the bundle are trusted in addition to the system's public CA roots, so it only needs the extra root (and any intermediates) for your Plex certificate. plex.tv and other publicly trusted hosts keep working unchanged.

The bundle must be readable by the Plexio container's unprivileged user (UID 999). Plexio fails at startup if the specified CA bundle is missing or invalid. Without `PLEX_CA_BUNDLE`, the default system TLS verification behavior is unchanged.
