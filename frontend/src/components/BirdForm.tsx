/**
 * Form component for bird observation input.
 */
import { useState } from 'react';
import type { ObservationInput } from '../types/observation';

interface BirdFormProps {
  onSubmit: (observation: ObservationInput) => void;
  isLoading: boolean;
}

export function BirdForm({ onSubmit, isLoading }: BirdFormProps) {
  const [description, setDescription] = useState('');
  const [location, setLocation] = useState('');
  const [observedAt, setObservedAt] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!description.trim()) {
      return;
    }

    const observation: ObservationInput = {
      description: description.trim(),
      ...(location.trim() && { location: location.trim() }),
      ...(observedAt.trim() && { observed_at: observedAt.trim() }),
    };

    onSubmit(observation);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div>
        <label
          htmlFor="description"
          className="block text-sm font-medium text-gray-700 mb-2"
        >
          Bird Description *
        </label>
        <textarea
          id="description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Describe the bird you observed (e.g., small red bird with black mask, long tail...)"
          className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
          rows={5}
          required
          disabled={isLoading}
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label
            htmlFor="location"
            className="block text-sm font-medium text-gray-700 mb-2"
          >
            Location (optional)
          </label>
          <input
            id="location"
            type="text"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            placeholder="e.g., New York, NY"
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            disabled={isLoading}
          />
        </div>

        <div>
          <label
            htmlFor="observedAt"
            className="block text-sm font-medium text-gray-700 mb-2"
          >
            Observed At (optional)
          </label>
          <input
            id="observedAt"
            type="text"
            value={observedAt}
            onChange={(e) => setObservedAt(e.target.value)}
            placeholder="e.g., Today morning, Yesterday"
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            disabled={isLoading}
          />
        </div>
      </div>

      <button
        type="submit"
        disabled={isLoading || !description.trim()}
        className="w-full bg-blue-600 text-white py-3 px-6 rounded-lg font-medium hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {isLoading ? 'Identifying...' : 'Identify Bird'}
      </button>
    </form>
  );
}

