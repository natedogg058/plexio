import { useEffect, useState } from 'react';
import { PlexToken } from '@/hooks/usePlexToken.tsx';
import { getCollections } from '@/services/PMSService.tsx';
import { PlexCollection, PlexSection } from '@/types/plex.tsx';

const usePMSCollections = (
  serverUrl: string,
  plexToken: PlexToken,
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
    if (!enabled || !plexToken || !serverUrl || sections.length === 0) {
      setLoading(false);
      return () => {
        active = false;
      };
    }

    setLoading(true);
    void getCollections(serverUrl, plexToken, sections)
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
  }, [enabled, plexToken, sectionSignature, serverUrl]);

  return { collections, loading };
};

export default usePMSCollections;
