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
          <div className="space-y-0.5">
            <FormLabel className="text-base">
              Route streams through Plexio
            </FormLabel>
            <FormDescription>
              Off sends Direct Play URLs straight to your Plex server so Plexio
              does not carry video bandwidth. Watch progress then relies on
              Plex&apos;s native playback tracking from the client. On keeps
              Plexio&apos;s playback proxy for reliable progress sync while
              external players pause reads after buffering.
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
