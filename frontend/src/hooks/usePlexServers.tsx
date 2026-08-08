import { useEffect, useState } from 'react';
import { PlexToken } from '@/hooks/usePlexToken.tsx';
import { getPlexServers } from '@/services/PlexService.tsx';
import { PlexServer } from '@/types/plex.tsx';

const usePlexServers = (
  plexToken: PlexToken | null,
  clientIdentifier: string,
) => {
  const [servers, setServers] = useState<PlexServer[]>([]);

  useEffect(() => {
    if (!clientIdentifier || !plexToken) return;

    const fetchPlexServers = async (): Promise<void> => {
      const plexServers = await getPlexServers(plexToken, clientIdentifier);
      setServers(plexServers);
    };

    void fetchPlexServers();
  }, [clientIdentifier, plexToken]);

  return servers;
};

export default usePlexServers;
