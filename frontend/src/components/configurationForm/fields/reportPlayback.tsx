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

export const ReportPlaybackField: FC<Props> = ({ form }) => {
  return (
    <FormField
      control={form.control}
      name="reportPlayback"
      render={({ field }) => (
        <FormItem className="items-center justify-between flex flex-row rounded-lg border p-2">
          <div className="flex flex-col gap-0.5">
            <FormLabel className="text-base">Report playback to Plex</FormLabel>
            <FormDescription>
              Sync watch progress to Plex. When route-through-Plexio is off,
              Direct Play URLs go straight to your Plex server and Plex tracks
              playback natively. When route-through is on, Plexio proxies the
              stream so progress stays accurate while players buffer. Set
              BASE_URL when using a reverse proxy that does not preserve
              forwarded headers.
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
