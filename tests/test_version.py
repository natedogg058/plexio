import json
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase

from plexio import __version__
from plexio.routers.addon import get_manifest


class VersionTests(TestCase):
    def test_frontend_and_backend_versions_match(self):
        package_json = Path(__file__).parents[1] / 'frontend' / 'package.json'
        frontend_version = json.loads(package_json.read_text())['version']

        self.assertEqual(frontend_version, __version__)


class ManifestVersionTests(IsolatedAsyncioTestCase):
    async def test_manifest_reports_package_version(self):
        manifest = await get_manifest(None)

        self.assertEqual(manifest.version, __version__)
