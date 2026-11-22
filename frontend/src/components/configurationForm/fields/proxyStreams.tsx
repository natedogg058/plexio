import { FC } from 'react';
import { UseFormReturn } from 'react-hook-form';
import { ConfigurationFormType } from '@/components/configurationForm/formSchema.tsx';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
} from '@/components/ui/form.tsx';
import { Switch } from '@/components/ui/switch.tsx';

interface Props {
  form: UseFormReturn<ConfigurationFormType>;
}

export const ProxyStreamsField: FC<Props> = ({ form }) => {
  return (
    <FormField
      control={form.control}
      name="proxyStreams"
      render={({ field }) => (
        <FormItem className="items-center justify-between flex flex-row rounded-lg border p-2 ml-4">
          <div className="flex flex-col gap-0.5">
            <FormLabel className="text-base">
              Route streams through Plexio
            </FormLabel>
            <FormDescription>
              Off keeps Direct Play URLs on your Plex server so Plexio
              carries no video bandwidth, and only the watch-progress
              heartbeats run through Plexio. On fetches the stream through
              Plexio for progress that stays accurate across long buffering
              pauses.
            </FormDescription>
          </div>
          <FormControl>
            <Switch checked={field.value} onCheckedChange={field.onChange} />
          </FormControl>
        </FormItem>
      )}
    />
  );
};
