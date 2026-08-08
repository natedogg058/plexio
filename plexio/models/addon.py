from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator
from yarl import URL

from plexio.models.plex import PlexLibrarySection, Resolution
from plexio.models.utils import to_camel


def validate_plex_url(value: str | URL) -> URL:
    if not isinstance(value, (str, URL)):
        raise ValueError('Plex URL must be a string')
    if len(str(value)) > 2048:
        raise ValueError('Plex URL is too long')
    url = URL(value)
    if (
        url.scheme not in {'http', 'https'}
        or not url.host
        or url.user is not None
        or url.password is not None
        or url.query_string
        or url.fragment
    ):
        raise ValueError('Plex URL must be an HTTP(S) origin without credentials')
    return url


class PlexConnectionKind(str, Enum):
    local = 'local'
    remote = 'remote'
    relay = 'relay'


class PlexStreamingConnection(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        arbitrary_types_allowed=True,
        extra='forbid',
        populate_by_name=True,
    )

    url: URL
    kind: PlexConnectionKind = PlexConnectionKind.remote

    @field_validator('url', mode='before')
    @classmethod
    def validate_url(cls, value):
        return validate_plex_url(value)


class AddonConfiguration(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        arbitrary_types_allowed=True,
        extra='forbid',
        populate_by_name=True,
    )

    access_token: str = Field(min_length=1, max_length=4096)
    discovery_url: URL
    streaming_url: URL
    streaming_connection_kind: PlexConnectionKind = PlexConnectionKind.remote
    streaming_connections: list[PlexStreamingConnection] = Field(
        default_factory=list,
        max_length=20,
    )
    server_name: str = Field(min_length=1, max_length=255)
    version: str = Field(default='0.0.1', min_length=1, max_length=64)
    sections: list[PlexLibrarySection] = Field(default_factory=list, max_length=100)
    include_direct_play: bool = True
    include_connection_fallbacks: bool = False
    include_transcode_original: bool = False
    include_transcode_down: bool = False
    transcode_down_qualities: list[Resolution] = Field(default_factory=list)
    include_plex_tv: bool = False
    report_playback: bool = False

    @field_validator('discovery_url', 'streaming_url', mode='before')
    @classmethod
    def validate_plex_url(cls, value):
        return validate_plex_url(value)

    def to_storage_dict(self) -> dict:
        config = self.model_dump(by_alias=True)
        config['discoveryUrl'] = str(self.discovery_url).rstrip('/')
        config['streamingUrl'] = str(self.streaming_url).rstrip('/')
        config['streamingConnections'] = [
            {
                'url': str(connection.url).rstrip('/'),
                'kind': connection.kind.value,
            }
            for connection in self.streaming_connections
        ]
        return config

    @property
    def direct_play_connections(self) -> list[tuple[URL, PlexConnectionKind]]:
        connections = [(self.streaming_url, self.streaming_connection_kind)]
        if self.include_connection_fallbacks:
            connections.extend(
                (connection.url, connection.kind)
                for connection in self.streaming_connections
            )
        deduplicated = []
        seen = set()
        for url, kind in connections:
            key = str(url).rstrip('/')
            if key not in seen:
                seen.add(key)
                deduplicated.append((URL(key), kind))
        return deduplicated
