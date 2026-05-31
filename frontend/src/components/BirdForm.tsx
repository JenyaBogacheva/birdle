/**
 * Form component for bird observation input.
 */
import { useState, FormEvent } from 'react';
import FrostedPanel from './FrostedPanel';
import type { ObservationInput } from '../types/observation';

interface BirdFormProps {
  onSubmit: (observation: ObservationInput) => void;
  isLoading: boolean;
}

export function BirdForm({ onSubmit, isLoading }: BirdFormProps) {
  const [description, setDescription] = useState('');
  const [location, setLocation] = useState('');
  const [observedAt, setObservedAt] = useState('');

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();

    if (!description.trim() || !location.trim()) {
      return;
    }

    const observation: ObservationInput = {
      description: description.trim(),
      location: location.trim(),
      ...(observedAt.trim() && { observed_at: observedAt.trim() }),
    };

    onSubmit(observation);
  };

  return (
    <FrostedPanel className="w-full max-w-lg animate-slide-up">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="font-hand text-secondary text-lg block mb-1">
            Tell me what you saw...
          </label>
          <textarea
            id="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            disabled={isLoading}
            className="w-full bg-white/5 border border-dashed border-white/20 rounded-lg p-3 text-primary placeholder-white/30 focus:outline-none focus:border-white/40 resize-none disabled:opacity-50"
            placeholder="A small bird with bright blue feathers..."
            required
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="font-hand text-secondary block mb-1">
              Where?
            </label>
            <input
              id="location"
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              disabled={isLoading}
              className="w-full bg-white/5 border border-dashed border-white/20 rounded-lg p-3 text-primary placeholder-white/30 focus:outline-none focus:border-white/40 disabled:opacity-50"
              placeholder="Central Park, NY"
              required
            />
          </div>
          <div>
            <label className="font-hand text-secondary block mb-1">
              When?
            </label>
            <input
              id="observedAt"
              type="text"
              value={observedAt}
              onChange={(e) => setObservedAt(e.target.value)}
              disabled={isLoading}
              className="w-full bg-white/5 border border-dashed border-white/20 rounded-lg p-3 text-primary placeholder-white/30 focus:outline-none focus:border-white/40 disabled:opacity-50"
              placeholder="This morning"
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={!description.trim() || !location.trim() || isLoading}
          className="w-full glass rounded-lg py-3 font-hand text-xl text-primary hover:bg-white/10 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        >
          {isLoading ? 'Investigating...' : 'Investigate →'}
        </button>
      </form>
    </FrostedPanel>
  );
}
