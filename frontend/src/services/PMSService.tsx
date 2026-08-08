import axios from 'axios';
import { PlexCollection, PlexSection } from '@/types/plex.tsx';

interface SectionsResponse {
  MediaContainer?: {
    Directory?: PlexSection[];
  };
}

interface RawCollection {
  ratingKey?: string | number;
  title?: string;
}

interface CollectionsResponse {
  MediaContainer?: {
    Metadata?: RawCollection[];
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

export const getCollections = async (
  serverUrl: string,
  token: string,
  sections: PlexSection[],
): Promise<PlexCollection[]> => {
  const responses = await Promise.all(
    sections.map(async (section) => {
      try {
        const response = await axios.get<CollectionsResponse>(
          `${serverUrl}/library/sections/${encodeURIComponent(section.key)}/collections`,
          {
            timeout: 25000,
            headers: {
              'X-Plex-Token': token,
            },
          },
        );
        const collections = response.data.MediaContainer?.Metadata ?? [];
        return collections.flatMap((collection) =>
          collection.ratingKey && collection.title
            ? [
                {
                  ratingKey: String(collection.ratingKey),
                  sectionKey: section.key,
                  sectionTitle: section.title,
                  title: collection.title,
                  type: section.type,
                },
              ]
            : [],
        );
      } catch (error) {
        console.error(`Error fetching collections for ${section.title}:`, error);
        return [];
      }
    }),
  );
  return responses.flat().sort(
    (a, b) =>
      a.sectionTitle.localeCompare(b.sectionTitle) ||
      a.title.localeCompare(b.title),
  );
};
