from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from yarl import URL

from plexio.models.plex import PlexLibrarySection, PlexMediaType, Resolution
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


class PlexCollectionCatalog(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra='forbid',
        populate_by_name=True,
    )

    rating_key: str = Field(pattern=r'^[0-9]+$')
    section_key: str = Field(pattern=r'^[A-Za-z0-9._-]+$', max_length=128)
    title: str = Field(min_length=1, max_length=255)
    type: PlexMediaType

    @property
    def catalog_id(self) -> str:
        return f'plexio-collection-{self.section_key}-{self.rating_key}'


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
    include_collections: bool = False
    collections: list[PlexCollectionCatalog] = Field(
        default_factory=list,
        max_length=200,
    )
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

    @model_validator(mode='after')
    def validate_collections(self):
        section_types = {section.key: section.type for section in self.sections}
        seen = set()
        for collection in self.collections:
            if section_types.get(collection.section_key) != collection.type:
                raise ValueError('Collection must belong to a configured section')
            if collection.catalog_id in seen:
                raise ValueError('Collections must be unique')
            seen.add(collection.catalog_id)
        return self

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

    @property
    def configured_collections(self) -> list[PlexCollectionCatalog]:
        return self.collections if self.include_collections else []
