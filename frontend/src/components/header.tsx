import { FC } from 'react';
import { Icons } from '@/components/icons.tsx';
import { ThemeToggle } from '@/components/themeToggle.tsx';
import { Avatar, AvatarImage } from '@/components/ui/avatar.tsx';
import { Button } from '@/components/ui/button.tsx';
import { PlexUser } from '@/types/plex.tsx';

interface Props {
  plexUser: PlexUser | null | undefined;
  setPlexToken: (token: string | null) => void;
}

const Header: FC<Props> = ({ plexUser, setPlexToken }) => {
  const handleLogout = () => {
    setPlexToken(null);
  };

  return (
    <div className="flex h-12 items-center">
      <Button asChild variant="ghost" size="icon">
        <a
          aria-label="Plexio source code"
          href="https://github.com/natedogg058/plexio"
        >
          <Icons.gitHub className="h-5 w-5" />
        </a>
      </Button>
      <div className="flex flex-1 items-center justify-end">
        {plexUser && (
          <>
            <a
              className="flex items-center justify-end"
              href={'https://app.plex.tv/desktop/#!/u/' + plexUser.username}
            >
              <Avatar className="h-7 w-7">
                <AvatarImage src={plexUser.thumb} />
              </Avatar>
              <span className="m-2"> {plexUser.username} </span>
            </a>
            <Button onClick={handleLogout} variant="ghost" size="icon">
              <Icons.exit className="h-5 w-5" />
            </Button>
          </>
        )}
        <ThemeToggle />
      </div>
    </div>
  );
};

export default Header;
