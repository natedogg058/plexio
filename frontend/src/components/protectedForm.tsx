import { FC } from 'react';
import ConfigurationForm from '@/components/configurationForm';
import Loading from '@/components/loading.tsx';
import Login from '@/components/login.tsx';
import useClientIdentifier from '@/hooks/useClientIdentifier.tsx';
import usePlexServers from '@/hooks/usePlexServers.tsx';
import { PlexUser } from '@/types/plex.tsx';

interface Props {
  plexToken: string | null;
  plexUser: PlexUser | null | undefined;
}

const ProtectedForm: FC<Props> = ({ plexToken, plexUser }) => {
  const clientIdentifier = useClientIdentifier();
  const servers = usePlexServers(plexToken, clientIdentifier);

  if (plexUser === null) {
    return <Login />;
  }

  if (plexUser === undefined || !plexToken || !servers.length) {
    return <Loading />;
  }

  return (
    <ConfigurationForm
      servers={servers}
      accountToken={plexToken}
      clientIdentifier={clientIdentifier}
    />
  );
};

export default ProtectedForm;
