import { useEffect, useState } from 'react';
import { getCollections } from '@/services/BackendService.tsx';
import { PlexCollection, PlexSection, PlexServer } from '@/types/plex.tsx';

const usePMSCollections = (
  serverUrl: string,
  server: PlexServer | undefined,
  accountToken: string,
  clientIdentifier: string,
  sections: PlexSection[],
  enabled: boolean,
) => {
  const [collections, setCollections] = useState<PlexCollection[]>([]);
  const [loading, setLoading] = useState(false);
  const sectionSignature = sections
    .map((section) => `${section.key}:${section.type}`)
    .sort()
    .join(',');

  useEffect(() => {
    let active = true;
    setCollections([]);
    if (
      !enabled ||
      !server ||
      !serverUrl ||
      !accountToken ||
      !clientIdentifier ||
      sections.length === 0
    ) {
      setLoading(false);
      return () => {
        active = false;
      };
    }

    setLoading(true);
    void getCollections(
      {
        serverUrl,
        serverName: server.name,
        serverToken: server.accessToken,
        accountToken,
        clientIdentifier,
      },
      sections,
    )
      .then((items) => {
        if (active) {
          setCollections(items);
        }
      })
      .catch((error: unknown) => {
        console.error('Error fetching Plex collections:', error);
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
    // sectionSignature deliberately captures section identity without making
    // this effect depend on a newly allocated array each render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    accountToken,
    clientIdentifier,
    enabled,
    sectionSignature,
    server,
    serverUrl,
  ]);

  return { collections, loading };
};

export default usePMSCollections;
