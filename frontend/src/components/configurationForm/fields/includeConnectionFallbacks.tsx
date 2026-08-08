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

export const IncludeConnectionFallbacksField: FC<Props> = ({ form }) => {
  return (
    <FormField
      control={form.control}
      name="includeConnectionFallbacks"
      render={({ field }) => (
        <FormItem className="items-center justify-between flex flex-row rounded-lg border p-2">
          <div className="space-y-0.5">
            <FormLabel className="text-base">
              Include alternate Plex connections
            </FormLabel>
            <FormDescription>
              Offer the server&apos;s other local, remote, and Relay connections
              as clearly labelled Direct Play choices. Playback reporting also
              retries these connections automatically after gateway failures.
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
