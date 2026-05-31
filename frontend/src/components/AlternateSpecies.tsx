// frontend/src/components/AlternateSpecies.tsx
import type { SpeciesInfo } from '../types/observation';

interface AlternateSpeciesProps {
  species: SpeciesInfo[];
}

export default function AlternateSpecies({ species }: AlternateSpeciesProps) {
  if (species.length === 0) return null;

  return (
    <div>
      <p className="font-hand text-secondary text-lg mb-3">Also considered:</p>
      <div className="flex gap-3">
        {species.map((s) => (
          <div key={s.common_name} className="text-center">
            {s.image_url ? (
              <img
                src={s.image_url}
                alt={s.common_name}
                className="w-16 h-16 object-cover rounded-lg border border-white/10"
              />
            ) : (
              <div className="w-16 h-16 bg-white/5 rounded-lg flex items-center justify-center">
                <span className="font-hand text-faded">?</span>
              </div>
            )}
            <p className="font-hand text-faded text-sm mt-1">{s.common_name}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
