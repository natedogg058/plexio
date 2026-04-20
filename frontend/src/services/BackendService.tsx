import axios from 'axios';

export const isServerAliveRemote = async (serverUrl: string, token: string) => {
  try {
    const response = await axios.get(
      `${window.location.origin}/api/v1/test-connection`,
      {
        timeout: 25000,
        params: {
          url: serverUrl,
          token: token,
        },
      },
    );
    return response.data?.success;
  } catch (error) {
    console.error('Error while ping PMS remote:', error);
    return false;
  }
};

export const getPublicConfig = async (): Promise<{ baseUrl: string }> => {
  try {
    const response = await axios.get(
      `${window.location.origin}/api/v1/public-config`,
      { timeout: 5000 },
    );
    return { baseUrl: response.data?.base_url || '' };
  } catch (error) {
    console.error('Error fetching public config:', error);
    return { baseUrl: '' };
  }
};
