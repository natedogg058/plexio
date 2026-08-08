import { FC, useState } from 'react';
import { UseFormReturn } from 'react-hook-form';
import { ConfigurationFormType } from '@/components/configurationForm/formSchema.tsx';
import { parseUrlToIpPort } from '@/components/configurationForm/utils.tsx';
import { Badge } from '@/components/ui/badge.tsx';
import { Button } from '@/components/ui/button.tsx';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form.tsx';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select.tsx';
import { useToast } from '@/hooks/useToast';
import { PlexToken } from '@/hooks/usePlexToken.tsx';
import { isServerAliveRemote } from '@/services/BackendService.tsx';
import { PlexServer } from '@/types/plex.tsx';

interface Props {
  form: UseFormReturn<ConfigurationFormType>;
  server: PlexServer;
  accountToken: PlexToken;
  clientIdentifier: string;
}

export const DiscoveryUrlField: FC<Props> = ({
  form,
  server,
  accountToken,
  clientIdentifier,
}) => {
  const { toast } = useToast();

  const [testInProgress, setTestInProgress] = useState(false);
  const discoveryUrl = form.watch('discoveryUrl');

  const testUrl = async () => {
    setTestInProgress(true);
    try {
      const alive = await isServerAliveRemote(
        discoveryUrl,
        server.name,
        server.accessToken,
        accountToken ?? '',
        clientIdentifier,
      );
      const ipPort = parseUrlToIpPort(discoveryUrl);
      if (alive) {
        toast({
          title: 'Discovery URL Test Successful!',
          description: `Plexio backend successfully accessed your server at ${ipPort}.`,
          variant: 'success',
          duration: 30 * 1000,
        });
      } else {
        toast({
          title: 'Discovery URL Test Failed!',
          description: `Plexio backend could not access your server at ${ipPort}. 
                        Please try again or select another URL. Ensure your server is accessible publicly, 
                        or consider using Plex Relay if the server is behind a firewall.`,
          variant: 'destructive',
          duration: 30 * 1000,
        });
      }
    } finally {
      setTestInProgress(false);
    }
  };

  return (
    <FormField
      control={form.control}
      name="discoveryUrl"
      render={({ field }) => (
        <FormItem className="rounded-lg border p-2">
          <FormLabel className="text-base">Discovery URL</FormLabel>
          <div className="flex">
            <Select
              onValueChange={field.onChange}
              defaultValue=""
              value={field.value}
            >
              <FormControl>
                <SelectTrigger>
                  <SelectValue placeholder="Select a discovery url" />
                </SelectTrigger>
              </FormControl>
              {server.connections.filter((connection) => !connection.local)
                .length > 0 && (
                <SelectContent>
                  {server.connections
                    .filter((connection) => !connection.local)
                    .map((connection) => (
                      <SelectItem key={connection.uri} value={connection.uri}>
                        {connection.relay && (
                          <Badge className="mr-1.5" variant="secondary">
                            relay
                          </Badge>
                        )}
                        {`${connection.address}:${connection.port}`}
                      </SelectItem>
                    ))}
                </SelectContent>
              )}
            </Select>
            <Button
              className="ml-2.5 h-10 w-16"
              type="button"
              disabled={testInProgress || !discoveryUrl}
              onClick={() => {
                void testUrl();
              }}
            >
              {testInProgress ? (
                <div className="w-5 h-5 rounded-full animate-spin border-t-2" />
              ) : (
                'Test'
              )}
            </Button>
          </div>
          <FormDescription>
            Select the public URL of your Plex server.
          </FormDescription>
          <FormMessage />
        </FormItem>
      )}
    />
  );
};
