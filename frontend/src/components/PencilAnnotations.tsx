// frontend/src/components/PencilAnnotations.tsx
interface Annotation {
  text: string;
  x: string;      // CSS position (e.g., '10%')
  y: string;
  rotation: number; // degrees
  opacity: number;
  size: string;    // Tailwind text size class
}

const LANDING_ANNOTATIONS: Annotation[] = [
  { text: 'What colors did you see?', x: '5%', y: '12%', rotation: -3, opacity: 0.5, size: 'text-2xl' },
  { text: 'How big was it?', x: '65%', y: '8%', rotation: 2, opacity: 0.45, size: 'text-xl' },
  { text: 'Where did you see it?', x: '70%', y: '25%', rotation: -1, opacity: 0.55, size: 'text-lg' },
  { text: 'What was it doing?', x: '8%', y: '55%', rotation: 1, opacity: 0.4, size: 'text-xl' },
  { text: 'Remember the colors?', x: '72%', y: '50%', rotation: -2, opacity: 0.35, size: 'text-lg' },
  { text: '- - - →', x: '25%', y: '40%', rotation: 0, opacity: 0.3, size: 'text-2xl' },
  { text: '↗', x: '60%', y: '35%', rotation: 15, opacity: 0.3, size: 'text-3xl' },
];

interface PencilAnnotationsProps {
  annotations?: Annotation[];
  show?: boolean;
}

export default function PencilAnnotations({ annotations = LANDING_ANNOTATIONS, show = true }: PencilAnnotationsProps) {
  if (!show) return null;

  return (
    <div className="absolute inset-0 pointer-events-none overflow-hidden">
      {annotations.map((ann, i) => (
        <span
          key={i}
          className={`absolute font-hand text-white animate-fade-in ${ann.size}`}
          style={{
            left: ann.x,
            top: ann.y,
            transform: `rotate(${ann.rotation}deg)`,
            opacity: ann.opacity,
            animationDelay: `${i * 0.15}s`,
            animationFillMode: 'backwards',
          }}
        >
          {ann.text}
        </span>
      ))}
    </div>
  );
}
