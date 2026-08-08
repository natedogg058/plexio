import axios from 'axios';
import { PlexSection } from '@/types/plex.tsx';

interface SectionsResponse {
  MediaContainer?: {
    Directory?: PlexSection[];
  };
}

export const isServerAliveLocal = async (serverUrl: string, token: string) => {
  try {
    const response = await axios.get(serverUrl, {
      timeout: 25000,
      headers: {
        'X-Plex-Token': token,
      },
    });
    return response.status === 200;
  } catch (error) {
    console.error('Error while ping PMS:', error);
    return false;
  }
};

export const getSections = async (
  serverUrl: string,
  token: string,
): Promise<PlexSection[]> => {
  try {
    const response = await axios.get<SectionsResponse>(
      `${serverUrl}/library/sections`,
      {
        timeout: 25000,
        headers: {
          'X-Plex-Token': token,
        },
      },
    );

    const sections = response.data.MediaContainer?.Directory;

    if (!Array.isArray(sections)) {
      throw new Error('Invalid response from server');
    }

    return sections.filter((section) =>
      ['show', 'movie'].includes(section.type),
    );
  } catch (error) {
    console.error('Error fetching Plex servers:', error);
    throw error;
  }
};
