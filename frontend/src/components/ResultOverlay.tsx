// frontend/src/components/ResultOverlay.tsx
import { useEffect, useRef } from 'react';
import rough from 'roughjs';
import FrostedPanel from './FrostedPanel';
import AlternateSpecies from './AlternateSpecies';
import type { RecommendationResponse } from '../types/observation';

interface ResultOverlayProps {
  result: RecommendationResponse;
  onReset: () => void;
}

export default function ResultOverlay({ result, onReset }: ResultOverlayProps) {
  const underlineRef = useRef<SVGSVGElement>(null);

  const species = result.top_species;
  const confidence = species?.confidence ?? 'medium';

  // Rough.js underline with weight based on confidence
  useEffect(() => {
    if (!underlineRef.current || !species) return;
    // Clear any previous SVG nodes to avoid duplicates on re-run
    underlineRef.current.innerHTML = '';
    const rc = rough.svg(underlineRef.current);
    const strokeWidth = confidence === 'high' ? 3 : confidence === 'medium' ? 2 : 1;
    const line = rc.line(0, 10, 300, 10, {
      stroke: 'rgba(255,255,255,0.7)',
      strokeWidth,
      roughness: 1.5,
    });
    line.querySelectorAll('path').forEach((path) => {
      const len = path.getTotalLength();
      path.style.strokeDasharray = `${len}`;
      path.style.strokeDashoffset = `${len}`;
      path.style.animation = 'drawIn 1s ease-out 0.3s forwards';
    });
    underlineRef.current.appendChild(line);
  }, [species, confidence]);

  if (!species) return null;

  return (
    <div className="absolute inset-0 flex items-center justify-center p-8 animate-fade-in">
      {/* Species name with rough underline */}
      <div className="absolute top-16 left-8 right-8 text-center">
        <h1 className="font-hand text-5xl text-primary font-bold">
          {species.common_name}
        </h1>
        <svg ref={underlineRef} className="mx-auto mt-1" width="300" height="20" />
      </div>

      {/* Info panel */}
      <FrostedPanel className="max-w-lg w-full mt-24 animate-slide-up">
        <p className="font-hand text-secondary text-lg italic mb-4">
          {species.scientific_name}
        </p>

        <p className="text-primary leading-relaxed mb-6">
          {result.message}
        </p>

        {species.reasoning && (
          <p className="font-hand text-secondary text-lg mb-6">
            {species.reasoning}
          </p>
        )}

        {result.clarification && (
          <div className="glass rounded-lg p-4 mb-6">
            <p className="font-hand text-secondary">{result.clarification}</p>
          </div>
        )}

        <AlternateSpecies species={result.alternate_species ?? []} />

        <div className="flex items-center justify-between mt-6 pt-4 border-t border-white/10">
          <a
            href={species.range_link}
            target="_blank"
            rel="noopener noreferrer"
            className="font-hand text-secondary hover:text-primary transition-colors"
          >
            View on eBird →
          </a>
          <button
            onClick={onReset}
            className="glass rounded-lg px-6 py-2 font-hand text-lg text-primary hover:bg-white/10 transition-colors"
          >
            Investigate another
          </button>
        </div>
      </FrostedPanel>
    </div>
  );
}
