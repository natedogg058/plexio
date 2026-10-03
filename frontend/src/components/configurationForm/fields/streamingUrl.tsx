import { FC, useState } from 'react';
import { UseFormReturn } from 'react-hook-form';
import { ConfigurationFormType } from '@/components/configurationForm/formSchema.tsx';
import { formatConnectionAddress } from '@/components/configurationForm/utils.tsx';
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
import { isServerAliveLocal } from '@/services/PMSService.tsx';
import { PlexServer } from '@/types/plex.tsx';

interface Props {
  form: UseFormReturn<ConfigurationFormType>;
  server: PlexServer;
}

export const StreamingUrlField: FC<Props> = ({ form, server }) => {
  const { toast } = useToast();

  const [testInProgress, setTestInProgress] = useState(false);
  const streamingUrl = form.watch('streamingUrl');

  const testUrl = async () => {
    setTestInProgress(true);
    try {
      const alive = await isServerAliveLocal(streamingUrl, server.accessToken);
      const address = formatConnectionAddress(streamingUrl);
      if (alive) {
        toast({
          title: 'Streaming URL Test Successful!',
          description: `Your device successfully accessed the Streaming URL at ${address}.
                        Streaming will work if accessed from this device.`,
          variant: 'success',
          duration: 30 * 1000,
        });
      } else {
        toast({
          title: 'Streaming URL Test Failed!',
          description: `Your device could not access the Streaming URL at ${address}.
                        If you plan to stream from a different device, this may be expected behavior.
                        Otherwise, please try again or select another URL.
                        If your server is behind a firewall, consider using Plex Relay.`,
          variant: 'destructive',
          duration: 30 * 1000,
        });
      }
    } catch {
      toast({
        title: 'Streaming URL Test Failed!',
        description:
          'Could not test the selected address. Please select another URL or retry.',
        variant: 'destructive',
        duration: 30 * 1000,
      });
    } finally {
      setTestInProgress(false);
    }
  };

  return (
    <FormField
      control={form.control}
      name="streamingUrl"
      render={({ field }) => (
        <FormItem className="rounded-lg border p-2">
          <FormLabel className="text-base">Streaming URL</FormLabel>
          <div className="flex">
            <Select
              onValueChange={field.onChange}
              defaultValue=""
              value={field.value}
            >
              <FormControl>
                <SelectTrigger>
                  <SelectValue placeholder="Select a streaming url" />
                </SelectTrigger>
              </FormControl>
              {server.connections.length > 0 && (
                <SelectContent>
                  {server.connections.map((connection) => (
                    <SelectItem key={connection.uri} value={connection.uri}>
                      {connection.local && (
                        <Badge className="mr-1.5" variant="secondary">
                          local
                        </Badge>
                      )}
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
              disabled={testInProgress || !streamingUrl}
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
            Select the URL of your Plex server for streaming content to Stremio
            clients.
          </FormDescription>
          <FormMessage />
        </FormItem>
      )}
    />
  );
};
