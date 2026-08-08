import { useEffect, useState } from 'react';

export type PlexToken = string | null;

export type SetPlexToken = (token: PlexToken) => void;

const usePlexToken = (): [PlexToken, SetPlexToken] => {
  const [token, setToken] = useState<PlexToken>(() =>
    sessionStorage.getItem('plexToken'),
  );

  useEffect(() => {
    if (token) {
      sessionStorage.setItem('plexToken', token);
    } else {
      sessionStorage.removeItem('plexToken');
    }
  }, [token]);

  return [token, setToken];
};

export default usePlexToken;
