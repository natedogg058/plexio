import os
import ssl
import tempfile
from unittest import TestCase
from unittest.mock import patch

from plexio.main import build_plex_ssl_context
from plexio.settings import Settings

# Self-signed test CA. Only its presence in the trust store is checked, so the
# private key was discarded when it was generated.
TEST_CA_PEM = """\
-----BEGIN CERTIFICATE-----
MIIBiTCCAS+gAwIBAgIUDJl3j+x08oSoJ4SPlu7A0+3II/QwCgYIKoZIzj0EAwIw
GTEXMBUGA1UEAwwOUGxleGlvIFRlc3QgQ0EwIBcNMjYxMTIxMTYwNjUyWhgPMjEy
NjEwMjgxNjA2NTJaMBkxFzAVBgNVBAMMDlBsZXhpbyBUZXN0IENBMFkwEwYHKoZI
zj0CAQYIKoZIzj0DAQcDQgAEvzc/ycX/RL/LIzt6wSpQDxR/3GCnG3qw9jTMe7tx
CI3ADdPS9MfTWwKCRYdjSjBzKh8OQ2f/NS5I8toRIIeLxKNTMFEwHQYDVR0OBBYE
FKaUKEVdeFMwCHYsOwT5M/VT4EV6MB8GA1UdIwQYMBaAFKaUKEVdeFMwCHYsOwT5
M/VT4EV6MA8GA1UdEwEB/wQFMAMBAf8wCgYIKoZIzj0EAwIDSAAwRQIgVXLFvs01
9wU10d0bQVdsf5sFXMY2oS52Y6TDq9GptqACIQD6JH81H8FEYtvQEd+U++gM1cpP
xEuoRSbHP1037bC0yg==
-----END CERTIFICATE-----
"""


class PlexCaBundleSettingsTests(TestCase):
    def test_defaults_to_none(self):
        with patch.dict(os.environ, clear=False) as env:
            env.pop('PLEX_CA_BUNDLE', None)
            self.assertIsNone(Settings().plex_ca_bundle)

    def test_reads_environment(self):
        with patch.dict(os.environ, {'PLEX_CA_BUNDLE': '/etc/ssl/custom-ca.pem'}):
            self.assertEqual(Settings().plex_ca_bundle, '/etc/ssl/custom-ca.pem')


class PlexSslContextTests(TestCase):
    def test_no_bundle_keeps_aiohttp_default(self):
        self.assertIsNone(build_plex_ssl_context(None))
        self.assertIsNone(build_plex_ssl_context(''))

    def test_bundle_adds_to_system_roots_and_verifies(self):
        with tempfile.NamedTemporaryFile('w', suffix='.pem', delete=False) as f:
            f.write(TEST_CA_PEM)
        self.addCleanup(os.unlink, f.name)

        baseline = ssl.create_default_context().cert_store_stats()['x509_ca']
        context = build_plex_ssl_context(f.name)

        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.cert_store_stats()['x509_ca'], baseline + 1)
        subjects = [dict(x[0] for x in ca['subject']) for ca in context.get_ca_certs()]
        self.assertIn({'commonName': 'Plexio Test CA'}, subjects)

    def test_missing_bundle_fails_closed(self):
        with self.assertRaises(OSError):
            build_plex_ssl_context('/this/ca/bundle/does/not/exist.pem')

    def test_invalid_bundle_fails_closed(self):
        with tempfile.NamedTemporaryFile('w', suffix='.pem', delete=False) as f:
            f.write('not a certificate\n')
        self.addCleanup(os.unlink, f.name)
        with self.assertRaises(ssl.SSLError):
            build_plex_ssl_context(f.name)
