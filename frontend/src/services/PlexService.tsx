import axios from 'axios';
import { AuthPin, PlexServer, PlexUser } from '@/types/plex.tsx';

const PLEX_PRODUCT_NAME = 'Plexio';
const PLEX_API_URL = 'https://plex.tv/api/v2';

export const createAuthPin = async (
  clientIdentifier: string,
): Promise<AuthPin> => {
  try {
    const response = await axios.post<AuthPin>('/api/v1/plex-pin', null, {
      headers: {
        'X-Plex-Client-Identifier': clientIdentifier,
      },
    });

    return response.data;
  } catch (error) {
    console.error('Error fetching users:', error);
    throw error;
  }
};

export const getAuthToken = async (
  authPin: AuthPin,
  clientIdentifier: string,
): Promise<string> => {
  try {
    const response = await axios.get<{ authToken: string }>(
      `/api/v1/plex-token/${authPin.id}`,
      {
        params: {
          code: authPin.code,
        },
        headers: {
          'X-Plex-Client-Identifier': clientIdentifier,
        },
      },
    );
    return response.data.authToken;
  } catch (error) {
    console.error('Error auth token:', error);
    throw error;
  }
};

export const getPlexUser = async (
  token: string,
  clientIdentifier: string,
): Promise<PlexUser | null> => {
  try {
    const response = await axios.get<PlexUser>(`${PLEX_API_URL}/user`, {
      headers: {
        'X-Plex-Product': PLEX_PRODUCT_NAME,
        'X-Plex-Client-Identifier': clientIdentifier,
        'X-Plex-Token': token,
      },
    });

    if (response.status !== 200) {
      return null;
    }

    return response.data;
  } catch (error) {
    console.error('Error fetching user:', error);
    return null;
  }
};

export const getPlexServers = async (
  token: string,
  clientIdentifier: string,
): Promise<PlexServer[]> => {
  try {
    const response = await axios.get<PlexServer[]>('/api/v1/plex-resources', {
      params: {
        includeHttps: 1,
        includeRelay: 1,
      },
      headers: {
        'X-Plex-Token': token,
        'X-Plex-Client-Identifier': clientIdentifier,
      },
    });

    if (!response.data || !Array.isArray(response.data)) {
      throw new Error('Invalid response from server');
    }

    return response.data.filter(
      (server) =>
        server.provides.includes('server') && Boolean(server.accessToken),
    );
  } catch (error) {
    console.error('Error fetching Plex servers:', error);
    throw error;
  }
};
