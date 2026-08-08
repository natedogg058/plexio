import axios from 'axios';

interface TestConnectionResponse {
  success: boolean;
}

interface PublicConfigResponse {
  base_url?: string;
  legacy_urls_enabled?: boolean;
}

interface SessionResponse {
  session_id?: string;
}

export const isServerAliveRemote = async (
  serverUrl: string,
  serverName: string,
  serverToken: string,
  accountToken: string,
  clientIdentifier: string,
) => {
  try {
    const response = await axios.get<TestConnectionResponse>(
      `${window.location.origin}/api/v1/test-connection`,
      {
        timeout: 25000,
        params: {
          url: serverUrl,
          server_name: serverName,
        },
        headers: {
          'X-Plex-Token': serverToken,
          'X-Plex-Account-Token': accountToken,
          'X-Plex-Client-Identifier': clientIdentifier,
        },
      },
    );
    return response.data.success;
  } catch (error) {
    console.error('Error while ping PMS remote:', error);
    return false;
  }
};

export const getPublicConfig = async (): Promise<{
  baseUrl: string;
  legacyUrlsEnabled: boolean;
}> => {
  try {
    const response = await axios.get<PublicConfigResponse>(
      `${window.location.origin}/api/v1/public-config`,
      { timeout: 5000 },
    );
    return {
      baseUrl: response.data.base_url ?? '',
      legacyUrlsEnabled: response.data.legacy_urls_enabled ?? false,
    };
  } catch (error) {
    console.error('Error fetching public config:', error);
    return { baseUrl: '', legacyUrlsEnabled: false };
  }
};

export const createSession = async (
  configuration: object,
  accountToken: string,
  clientIdentifier: string,
  label?: string,
): Promise<string | null> => {
  try {
    const url =
      `${window.location.origin}/api/v1/sessions` +
      (label ? `?label=${encodeURIComponent(label)}` : '');
    const response = await axios.post<SessionResponse>(url, configuration, {
      timeout: 15000,
      headers: {
        'X-Plex-Account-Token': accountToken,
        'X-Plex-Client-Identifier': clientIdentifier,
      },
    });
    return response.data.session_id ?? null;
  } catch (error) {
    // Sessions disabled (404) or unreachable: caller falls back to base64.
    console.error('Error creating session:', error);
    return null;
  }
};
