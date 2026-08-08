import { FC } from 'react';
import { UseFormReturn } from 'react-hook-form';
import { ConfigurationFormType } from '@/components/configurationForm/formSchema.tsx';
import { Checkbox } from '@/components/ui/checkbox.tsx';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
} from '@/components/ui/form.tsx';
import { Switch } from '@/components/ui/switch.tsx';
import { PlexCollection } from '@/types/plex.tsx';

interface Props {
  form: UseFormReturn<ConfigurationFormType>;
  collections: PlexCollection[];
  loading: boolean;
}

export const CollectionsField: FC<Props> = ({
  form,
  collections,
  loading,
}) => {
  const enabled = form.watch('includeCollections');
  const selectedSections = form.watch('sections');

  return (
    <FormItem className="rounded-lg border p-2">
      <FormField
        control={form.control}
        name="includeCollections"
        render={({ field }) => (
          <div className="items-center justify-between flex flex-row">
            <div className="space-y-0.5">
              <FormLabel className="text-base">
                Include Plex collection catalogs
              </FormLabel>
              <FormDescription>
                Discover collections only when enabled, then choose which ones
                become separate Stremio rows.
              </FormDescription>
            </div>
            <FormControl>
              <Switch checked={field.value} onCheckedChange={field.onChange} />
            </FormControl>
          </div>
        )}
      />

      {enabled && (
        <div className="mt-3 space-y-2 border-t pt-3">
          {selectedSections.length === 0 ? (
            <FormDescription>Select at least one library first.</FormDescription>
          ) : loading ? (
            <FormDescription>Loading collections from Plex…</FormDescription>
          ) : collections.length === 0 ? (
            <FormDescription>
              No collections were found in the selected libraries.
            </FormDescription>
          ) : (
            collections.map((collection) => (
              <FormField
                key={`${collection.sectionKey}-${collection.ratingKey}`}
                control={form.control}
                name="collections"
                render={({ field }) => {
                  const selected = {
                    ratingKey: collection.ratingKey,
                    sectionKey: collection.sectionKey,
                    title: collection.title,
                    type: collection.type,
                  };
                  return (
                    <FormItem className="flex flex-row items-start space-x-3 space-y-0">
                      <FormControl>
                        <Checkbox
                          checked={field.value.some(
                            (item) =>
                              item.ratingKey === collection.ratingKey &&
                              item.sectionKey === collection.sectionKey,
                          )}
                          onCheckedChange={(checked) =>
                            checked
                              ? field.onChange([...field.value, selected])
                              : field.onChange(
                                  field.value.filter(
                                    (item) =>
                                      item.ratingKey !== collection.ratingKey ||
                                      item.sectionKey !== collection.sectionKey,
                                  ),
                                )
                          }
                        />
                      </FormControl>
                      <FormLabel className="font-normal">
                        {collection.title} — {collection.sectionTitle}
                      </FormLabel>
                    </FormItem>
                  );
                }}
              />
            ))
          )}
        </div>
      )}
    </FormItem>
  );
};
