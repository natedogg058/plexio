import { FC, useEffect, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { Base64 } from 'js-base64';
import { SubmitHandler, useForm } from 'react-hook-form';
import { v4 as uuidv4 } from 'uuid';
import {
  DiscoveryUrlField,
  IncludeTranscodeOriginalField,
  IncludeDirectPlayField,
  IncludeConnectionFallbacksField,
  SectionsField,
  ServerNameField,
  StreamingUrlField,
  IncludeTranscodeDownFields,
  IncludePlexTvField,
  ReportPlaybackField,
} from '@/components/configurationForm/fields';
import {
  formSchema,
  ConfigurationFormType,
} from '@/components/configurationForm/formSchema.tsx';
import { Icons } from '@/components/icons';
import { Button } from '@/components/ui/button.tsx';
import { Form } from '@/components/ui/form';
import usePMSSections from '@/hooks/usePMSSections.tsx';
import { createSession, getPublicConfig } from '@/services/BackendService.tsx';
import { PlexServer } from '@/types/plex.tsx';

interface Props {
  servers: PlexServer[];
  accountToken: string;
  clientIdentifier: string;
}

const ConfigurationForm: FC<Props> = ({
  servers,
  accountToken,
  clientIdentifier,
}) => {
  const [baseUrl, setBaseUrl] = useState<string | null>(null);
  const [legacyUrlsEnabled, setLegacyUrlsEnabled] = useState(false);

  useEffect(() => {
    // Fetch once at mount. If the backend doesn't respond or BASE_URL isn't set,
    // baseUrl stays null and we fall back to window.location.origin below.
    void getPublicConfig().then(({ baseUrl, legacyUrlsEnabled }) => {
      setBaseUrl(baseUrl.length > 0 ? baseUrl : null);
      setLegacyUrlsEnabled(legacyUrlsEnabled);
    });
  }, []);

  const form = useForm<ConfigurationFormType>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      includeDirectPlay: true,
      includeConnectionFallbacks: false,
      includeTranscodeOriginal: false,
      includeTranscodeDown: false,
      includePlexTv: false,
      reportPlayback: false,
      sections: [],
    },
  });

  const serverName = form.watch('serverName');
  const server = servers.find((candidate) => candidate.name === serverName);

  const discoveryUrl = form.watch('discoveryUrl');
  const sections = usePMSSections(discoveryUrl, server?.accessToken ?? null);

  const onSubmit: SubmitHandler<ConfigurationFormType> = async (
    configuration,
    event,
  ) => {
    if (!server) {
      return;
    }

    // Read which button submitted before any await (the native event's
    // submitter must be captured synchronously).
    const nativeEvent = event?.nativeEvent;
    const submitter =
      nativeEvent instanceof SubmitEvent ? nativeEvent.submitter : null;
    const action = submitter instanceof HTMLButtonElement ? submitter.name : '';
    const includeConnectionFallbacks =
      configuration.includeDirectPlay &&
      configuration.includeConnectionFallbacks;

    const normalizedConfiguration = {
      ...configuration,
      includeConnectionFallbacks,
      version: __APP_VERSION__,
      accessToken: server.accessToken,
      streamingConnectionKind: (() => {
        const selected = server.connections.find(
          (connection) => connection.uri === configuration.streamingUrl,
        );
        return selected?.relay ? 'relay' : selected?.local ? 'local' : 'remote';
      })(),
      streamingConnections: includeConnectionFallbacks
        ? server.connections
            .filter((connection) => connection.uri !== configuration.streamingUrl)
            .map((connection) => ({
              url: connection.uri,
              kind: connection.relay
                ? 'relay'
                : connection.local
                  ? 'local'
                  : 'remote',
            }))
        : [],
      sections: configuration.sections.filter((item) =>
        sections.some((section) => section.key === item.key),
      ),
    };

    // Prefer operator-configured BASE_URL when set (for reverse-proxy deployments
    // where window.location.origin may not match the public-facing URL).
    // Falls back to window.location.origin for default localhost deployments.
    const origin = baseUrl ?? window.location.origin;

    // Prefer a server-side session so the Plex token never appears in the URL.
    // Fall back to the legacy base64 install URL if sessions are disabled (404)
    // or the request fails.
    const sessionId = await createSession(
      normalizedConfiguration,
      accountToken,
      clientIdentifier,
      normalizedConfiguration.serverName,
    );
    let addonUrl: string;
    if (sessionId) {
      addonUrl = `${origin}/${sessionId}/manifest.json`;
    } else if (legacyUrlsEnabled) {
      const encodedConfiguration = Base64.encodeURI(
        JSON.stringify(normalizedConfiguration),
      );
      addonUrl = `${origin}/${uuidv4()}/${encodedConfiguration}/manifest.json`;
    } else {
      window.alert(
        'Plexio could not create a secure install session. Please retry or check the server logs.',
      );
      return;
    }

    if (action === 'clipboard') {
      try {
        await navigator.clipboard.writeText(addonUrl);
      } catch {
        window.prompt('Copy your Plexio install URL:', addonUrl);
      }
    } else {
      window.location.href = addonUrl.replace(/https?:\/\//, 'stremio://');
    }
  };

  return (
    <Form {...form}>
      <form
        onSubmit={(event) => {
          void form.handleSubmit(onSubmit)(event);
        }}
        className="space-y-2 p-2 rounded-lg border"
      >
        <ServerNameField form={form} servers={servers} />
        {server && (
          <>
            <DiscoveryUrlField
              form={form}
              server={server}
              accountToken={accountToken}
              clientIdentifier={clientIdentifier}
            />
            <StreamingUrlField form={form} server={server} />
          </>
        )}
        {discoveryUrl && (
          <SectionsField form={form} sections={sections}></SectionsField>
        )}
        <IncludeDirectPlayField form={form} />
        {form.watch('includeDirectPlay') && (
          <IncludeConnectionFallbacksField form={form} />
        )}
        <IncludeTranscodeOriginalField form={form} />
        <IncludeTranscodeDownFields form={form} />
        <IncludePlexTvField form={form} />
        <ReportPlaybackField form={form} />

        <div className="flex items-center space-x-1 justify-center p-3">
          <Button className="h-11 w-10 p-2" type="submit" name="clipboard">
            <Icons.clipboard />
          </Button>
          <Button
            className="h-11 rounded-md px-8 text-xl"
            type="submit"
            name="install"
          >
            Install
          </Button>
        </div>
      </form>
    </Form>
  );
};

export default ConfigurationForm;
