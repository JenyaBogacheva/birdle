// frontend/src/components/DetectiveNotes.tsx
import TypewriterText from './TypewriterText';

interface DetectiveNote {
  id: string;
  message: string;
}

// Canned note mappings for non-LLM events
const CANNED_NOTES: Record<string, string> = {
  'stream_start': "Let's find this bird...",
  'get_regional_birds': 'Checking the local records...',
  'web_search': 'Digging deeper...',
  'error': 'Hmm, hit a snag...',
};

// eslint-disable-next-line react-refresh/only-export-components -- intentional: named helper + default component co-located
export function cannedNoteForEvent(
  eventType: string,
  toolName?: string,
  toolSummary?: string,
): string | null {
  if (eventType === 'status' && toolName === undefined) return CANNED_NOTES['stream_start'];
  if (eventType === 'tool_call' && toolName) return CANNED_NOTES[toolName] ?? null;
  if (eventType === 'tool_result' && toolSummary) {
    const match = toolSummary.match(/Found (\d+) species/);
    if (match) return `${match[1]} species in the area. Let's narrow it down.`;
    return null;
  }
  if (eventType === 'error') return CANNED_NOTES['error'];
  return null;
}

// Stagger positions for organic notebook feel
const POSITIONS = [
  { x: '5%', y: '0', rotation: -2 },
  { x: '15%', y: '0', rotation: 1 },
  { x: '3%', y: '0', rotation: -1 },
  { x: '20%', y: '0', rotation: 2 },
  { x: '8%', y: '0', rotation: -3 },
  { x: '12%', y: '0', rotation: 0 },
];

interface DetectiveNotesProps {
  notes: DetectiveNote[];
}

export default function DetectiveNotes({ notes }: DetectiveNotesProps) {
  return (
    <div className="absolute inset-0 pointer-events-none overflow-y-auto p-8">
      <div className="flex flex-col gap-6 max-w-lg">
        {notes.map((note, i) => {
          const pos = POSITIONS[i % POSITIONS.length];
          return (
            <div
              key={note.id}
              className="animate-fade-in"
              style={{
                marginLeft: pos.x,
                transform: `rotate(${pos.rotation}deg)`,
                animationDelay: '0.1s',
                animationFillMode: 'backwards',
              }}
            >
              <TypewriterText
                text={note.message}
                speed={35}
                className="text-xl text-secondary"
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}
