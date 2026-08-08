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

    def test_stream_description_includes_normalized_source_details(self):
        item = media()
        item.media[0].update(
            {
                'videoResolution': '4k',
                'videoCodec': 'hevc',
                'bitrate': 17_862,
            }
        )
        part = item.media[0]['Part'][0]
        part['size'] = 25 * 1024**3
        part['Stream'] = [
            {
                'streamType': 1,
                'codec': 'hevc',
                'displayTitle': '4K HDR10 (HEVC Main 10)',
                'colorTrc': 'smpte2084',
                'DOVIPresent': True,
            },
            {
                'streamType': 2,
                'codec': 'eac3',
                'channels': 6,
                'languageTag': 'en',
            },
            {
                'streamType': 2,
                'codec': 'aac',
                'channels': 2,
                'languageTag': 'ja',
            },
            {
                'streamType': 3,
                'id': 7,
                'key': '/library/streams/7',
                'displayTitle': 'English (SRT)',
                'languageTag': 'en',
            },
        ]

        stream = item.get_stremio_streams(configuration())[0]

        self.assertIn('Direct Play 4K · Primary Remote', stream.description)
        self.assertIn(
            'Source: HEVC · Dolby Vision / HDR10 · E-AC-3 5.1 / AAC 2.0 · 17.9 Mbps',
            stream.description,
        )
        self.assertIn('Audio: 🇬🇧/🇯🇵', stream.description)
        self.assertIn('Subtitles: 🇬🇧', stream.description)
        self.assertIn('25.0 GB', stream.description)
        self.assertNotIn('/media/', stream.description)
        self.assertNotIn('secret', stream.description)
        self.assertEqual(stream.behavior_hints.filename, 'Example.mkv')
        self.assertEqual(stream.behavior_hints.video_size, 25 * 1024**3)

    def test_stream_description_handles_missing_and_partial_metadata(self):
        item = media()
        item.media[0].pop('videoResolution')
        item.media[0]['height'] = 'not-a-number'
        item.media[0]['bitrate'] = 'unknown'
        item.media[0]['Part'][0].pop('size')
        item.media[0]['Part'][0]['Stream'] = [
            {'streamType': 2, 'channels': 'unknown'},
            {'streamType': 3},
        ]

        stream = item.get_stremio_streams(configuration())[0]

        self.assertEqual(
            stream.description,
            'Example.mkv\nDirect Play · Primary Remote\n'
            'Audio: Unknown · Subtitles: Unknown',
        )
        self.assertIsNone(stream.behavior_hints.video_size)
