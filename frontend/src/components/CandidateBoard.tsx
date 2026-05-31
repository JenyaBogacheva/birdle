// frontend/src/components/CandidateBoard.tsx
import type { CandidateInfo } from '../types/observation';
import CandidateCard from './CandidateCard';

interface CandidateBoardProps {
  candidates: CandidateInfo[];
}

export default function CandidateBoard({ candidates }: CandidateBoardProps) {
  if (candidates.length === 0) return null;

  return (
    <div className="absolute bottom-32 right-8 flex gap-4 flex-wrap justify-end max-w-md">
      {candidates.map((c) => (
        <div key={c.species_code} className="animate-fade-in">
          <CandidateCard candidate={c} />
        </div>
      ))}
    </div>
  );
}
