import { z } from 'zod';

export const formSchema = z.object({
  serverName: z.string().min(1).max(255),
  discoveryUrl: z.string().url().max(2048),
  streamingUrl: z.string().url().max(2048),
  sections: z
    .array(
      z.object({
        key: z.string().min(1).max(128),
        title: z.string().min(1).max(255),
        type: z.string(),
      }),
    ),
  includeDirectPlay: z.boolean(),
  includeConnectionFallbacks: z.boolean(),
  includeTranscodeOriginal: z.boolean(),
  includeTranscodeDown: z.boolean(),
  transcodeDownQualities: z.array(z.string()).optional(),
  includePlexTv: z.boolean(),
  reportPlayback: z.boolean(),
});

export type ConfigurationFormType = z.infer<typeof formSchema>;
