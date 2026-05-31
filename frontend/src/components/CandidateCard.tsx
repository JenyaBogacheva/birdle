// frontend/src/components/CandidateCard.tsx
import { useEffect, useRef } from 'react';
import rough from 'roughjs';
import type { CandidateInfo } from '../types/observation';

interface CandidateCardProps {
  candidate: CandidateInfo;
}

export default function CandidateCard({ candidate }: CandidateCardProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const prevStatusRef = useRef(candidate.status);
  const isEliminated = candidate.status === 'eliminated';

  useEffect(() => {
    if (!svgRef.current) return;
    // Only redraw when status changes (or on first mount)
    if (prevStatusRef.current === candidate.status && svgRef.current.childElementCount > 0) return;
    prevStatusRef.current = candidate.status;

    const rc = rough.svg(svgRef.current);
    const w = svgRef.current.clientWidth || 160;
    const h = svgRef.current.clientHeight || 200;

    // Hand-drawn border
    const rect = rc.rectangle(2, 2, w - 4, h - 4, {
      stroke: 'rgba(255,255,255,0.6)',
      strokeWidth: 1.5,
      roughness: 2,
      fill: 'none',
    });
    svgRef.current.appendChild(rect);

    // Cross-out for eliminated candidates
    if (isEliminated) {
      const line1 = rc.line(4, 4, w - 4, h - 4, {
        stroke: 'rgba(255,255,255,0.5)',
        strokeWidth: 2,
        roughness: 1.5,
      });
      const line2 = rc.line(w - 4, 4, 4, h - 4, {
        stroke: 'rgba(255,255,255,0.5)',
        strokeWidth: 2,
        roughness: 1.5,
      });

      // Animate cross-out
      [line1, line2].forEach((node, idx) => {
        node.querySelectorAll('path').forEach((path) => {
          const len = path.getTotalLength();
          path.style.strokeDasharray = `${len}`;
          path.style.strokeDashoffset = `${len}`;
          path.style.animation = `drawIn 0.5s ease-out ${idx * 0.3}s forwards`;
        });
      });

      svgRef.current.appendChild(line1);
      svgRef.current.appendChild(line2);
    }
  // Intentionally only re-run when elimination status changes; candidate.status and other
  // derived vars (rc, w, h) are read from the DOM at effect time and should not cause redraws.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isEliminated]);

  return (
    <div
      className={`relative w-40 transition-opacity duration-500 ${
        isEliminated ? 'opacity-30' : 'opacity-100'
      }`}
    >
      <div className="relative overflow-hidden rounded-lg">
        {candidate.image_url ? (
          <img
            src={candidate.image_url}
            alt={candidate.name}
            className="w-40 h-48 object-cover"
          />
        ) : (
          <div className="w-40 h-48 bg-white/5 flex items-center justify-center">
            <span className="font-hand text-secondary text-lg">?</span>
          </div>
        )}
        <svg
          ref={svgRef}
          className="absolute inset-0 pointer-events-none"
          width="100%"
          height="100%"
        />
      </div>
      <p className={`font-hand text-center mt-2 ${isEliminated ? 'text-faded line-through' : 'text-secondary'}`}>
        {candidate.name}
      </p>
    </div>
  );
}
