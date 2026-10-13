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
              Sync watch progress to Plex. With route-through-Plexio off,
              Plexio sends only the heartbeats and the video goes straight to
              your server. With it on, Plexio also fetches the stream so
              progress stays accurate while players buffer. Plex drops a
              session it never sees as playing, so leaving this off can end a
              stream early on servers that limit how long a session may sit
              paused. Set BASE_URL when using a reverse proxy that does not
              preserve forwarded headers.
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
