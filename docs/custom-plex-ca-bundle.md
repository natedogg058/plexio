# Trusting a custom Plex HTTPS CA bundle

Plexio verifies HTTPS certificates when connecting to Plex. If your Plex server uses a certificate chain not present in the container's trust store, supply a PEM CA bundle with `PLEX_CA_BUNDLE`. Do not disable TLS verification.

Example Docker options:

```sh
-v /path/to/ca-bundle.pem:/etc/ssl/plexio-ca.pem:ro \
-e PLEX_CA_BUNDLE=/etc/ssl/plexio-ca.pem
```

The bundle must be readable by the Plexio container's unprivileged user (UID 999), and should include the standard public CA roots as well as any additional root needed for your Plex certificate. Plexio will fail at startup if the specified CA bundle is missing or invalid. Without `PLEX_CA_BUNDLE`, the default system TLS verification behavior is unchanged.
