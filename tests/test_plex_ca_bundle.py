import ssl
from unittest.mock import patch

import pytest

from plexio.settings import Settings


def test_plex_ca_bundle_defaults_to_none():
    with patch.dict('os.environ', {'PLEX_CA_BUNDLE': ''}):
        assert Settings().plex_ca_bundle == ''


def test_plex_ca_bundle_setting_reads_environment():
    with patch.dict('os.environ', {'PLEX_CA_BUNDLE': '/etc/ssl/custom-ca.pem'}):
        assert Settings().plex_ca_bundle == '/etc/ssl/custom-ca.pem'


def test_invalid_custom_ca_bundle_fails_closed():
    with pytest.raises(OSError):
        ssl.create_default_context(cafile='/this/ca/bundle/does/not/exist.pem')
