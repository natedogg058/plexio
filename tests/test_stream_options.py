from types import SimpleNamespace
from unittest import TestCase

from yarl import URL

from plexio.models.addon import PlexConnectionKind
from plexio.models.plex import PlexMediaMeta


def media():
    return PlexMediaMeta(
        guid='local://movie/1',
        type='movie',
        title='Example',
        ratingKey='1',
        key='/library/metadata/1',
        librarySectionTitle='Movies',
        Media=[
            {
                'videoResolution': '1080',
                'width': 1920,
                'Part': [
                    {
                        'file': '/media/Example.mkv',
                        'key': '/library/parts/1/file.mkv',
                        'size': 1234,
                        'Stream': [],
                    }
                ],
            }
        ],
    )


def configuration(**overrides):
    values = {
        'server_name': 'Home',
        'streaming_url': URL('https://primary.plex.direct:32400'),
        'direct_play_connections': [
            (URL('https://primary.plex.direct:32400'), PlexConnectionKind.remote),
            (URL('https://relay.plex.direct'), PlexConnectionKind.relay),
        ],
        'access_token': 'secret',
        'include_direct_play': True,
        'include_transcode_original': False,
        'include_transcode_down': False,
        'transcode_down_qualities': [],
        'include_plex_tv': False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class StreamOptionTests(TestCase):
    def test_can_disable_direct_play(self):
        streams = media().get_stremio_streams(configuration(include_direct_play=False))
        self.assertEqual(streams, [])

    def test_alternate_connections_are_labelled(self):
        streams = media().get_stremio_streams(configuration())

        self.assertEqual(len(streams), 2)
        self.assertIn('Primary Remote', streams[0].description)
        self.assertIn('Alternate Relay', streams[1].description)
        self.assertEqual(URL(streams[0].url).host, 'primary.plex.direct')
        self.assertEqual(URL(streams[1].url).host, 'relay.plex.direct')

    def test_playback_proxy_emits_one_automatic_fallback_stream(self):
        streams = media().get_stremio_streams(
            configuration(),
            play_prefix='https://plexio.example.test/session/play',
        )

        self.assertEqual(len(streams), 1)
        self.assertIn('Automatic connection fallback', streams[0].description)
