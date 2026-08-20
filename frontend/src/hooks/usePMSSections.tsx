import { useEffect, useState } from 'react';
import { getSections } from '@/services/BackendService.tsx';
import { PlexSection, PlexServer } from '@/types/plex.tsx';

const usePMSSections = (
  serverUrl: string,
  server: PlexServer | undefined,
  accountToken: string,
  clientIdentifier: string,
) => {
  const [sections, setSections] = useState<PlexSection[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    setSections([]);
    setError(false);
    if (!server || !serverUrl || !accountToken || !clientIdentifier) {
      setLoading(false);
      return () => {
        active = false;
      };
    }

    setLoading(true);
    void getSections({
      serverUrl,
      serverName: server.name,
      serverToken: server.accessToken,
      accountToken,
      clientIdentifier,
    })
      .then((items) => {
        if (active) {
          setSections(items);
        }
      })
      .catch((requestError: unknown) => {
        console.error('Error fetching Plex library sections:', requestError);
        if (active) {
          setError(true);
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [accountToken, clientIdentifier, server, serverUrl]);

  return { sections, loading, error };
};

export default usePMSSections;
