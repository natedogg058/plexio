import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion.tsx';

const QUESTIONS = [
  {
    id: 'what-is-plexio',
    question: `What is Plexio?`,
    answer: `Plexio is an addon that connects Plex with Stremio, enabling you to stream your Plex content directly 
             within the Stremio interface. It allows you to integrate Plex's media library, manage metadata, and enjoy
             seamless streaming across devices.`,
  },
  {
    id: 'is-plexio-secure',
    question: `Is Plexio secure?`,
    answer: `Plexio is designed to keep your Plex password out of the addon and stores install configuration in encrypted,
             revocable server-side sessions by default. The source is public for review. You can revoke Plex access from
             the "Authorized Devices" tab in your Plex account settings. Like any self-hosted service, keep it updated.`,
  },
  {
    id: 'how-plexio-work',
    question: `How does Plexio work?`,
    answer: `Plexio uses the Plex API to match Stremio IMDb data to the corresponding Plex media and provide catalogs,
             metadata, and streams. Direct Play normally goes from Stremio to Plex. Transcoding is handled by Plex, and
             the optional playback-reporting mode proxies Direct Play through Plexio so it can report progress.`,
  },
  {
    id: 'where-find-support',
    question: `Where can I find support?`,
    answer: `Open an issue in the maintained Plexio GitHub repository using the link in the top-left corner. Never post
             Plex tokens, session IDs, complete stream URLs, or private media paths.`,
  },
  {
    id: 'can-self-host',
    question: `Can I self-host?`,
    answer: `Yes, you can self-host Plexio. Instructions are available in the source code repository's README file.`,
  },
  {
    id: 'what-is-transcoded',
    question: `What is a transcoded stream?`,
    answer: `A transcoded stream is a version of your media that’s converted to a different format or resolution to suit
             your device or network. Direct play is usually better, as it streams the original file without 
             modification. Use transcoding if the original file isn’t compatible with your device or if your network 
             needs a lower bitrate for smoother playback.`,
  },
];

const FAQ = () => {
  return (
    <div className="mt-5 mb-5 border rounded-lg p-6">
      <h2 className="text-md font-semibold">Frequently Asked Questions</h2>
      <Accordion type="multiple" className="mt-4">
        {QUESTIONS.map((item) => (
          <AccordionItem value={item.id} key={item.id}>
            <AccordionTrigger>{item.question}</AccordionTrigger>
            <AccordionContent>{item.answer}</AccordionContent>
          </AccordionItem>
        ))}
      </Accordion>
    </div>
  );
};

export default FAQ;
