/**
 * Component to display bird identification results.
 */
import { useState } from 'react';
import type { RecommendationResponse } from '../types/observation';
import { SpeciesCard } from './SpeciesCard';

interface ResultPanelProps {
  result: RecommendationResponse | null;
  error: string | null;
}

export function ResultPanel({ result, error }: ResultPanelProps) {
  const [showAlternates, setShowAlternates] = useState(false);

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-6">
        <div className="flex items-start">
          <div className="flex-shrink-0">
            <svg
              className="h-6 w-6 text-red-600"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          </div>
          <div className="ml-3">
            <h3 className="text-sm font-medium text-red-800">Error</h3>
            <p className="mt-2 text-sm text-red-700">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  if (!result) {
    return null;
  }

  const hasAlternates =
    result.alternate_species && result.alternate_species.length > 0;

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-6 space-y-4">
      {/* Summary Message */}
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-2">
          Identification Result
        </h3>
        <p className="text-gray-700 leading-relaxed">{result.message}</p>
      </div>

      {/* Top Match */}
      {result.top_species && (
        <div>
          <h4 className="text-md font-semibold text-gray-900 mb-3 flex items-center">
            🎯 Top Match
          </h4>
          <SpeciesCard species={result.top_species} isPrimary={true} />
        </div>
      )}

      {/* Alternative Matches */}
      {hasAlternates && (
        <div>
          <button
            onClick={() => setShowAlternates(!showAlternates)}
            className="flex items-center justify-between w-full text-left text-md font-semibold text-gray-900 hover:text-gray-700"
          >
            <span>
              Alternative Matches ({result.alternate_species!.length})
            </span>
            <svg
              className={`h-5 w-5 transform transition-transform ${
                showAlternates ? 'rotate-180' : ''
              }`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 9l-7 7-7-7"
              />
            </svg>
          </button>

          {showAlternates && (
            <div className="mt-3 space-y-3">
              {result.alternate_species!.map((species, index) => (
                <SpeciesCard key={index} species={species} isPrimary={false} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Clarification Question */}
      {result.clarification && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
          <h4 className="text-sm font-medium text-yellow-900 mb-2">
            Need More Information
          </h4>
          <p className="text-sm text-yellow-800">{result.clarification}</p>
        </div>
      )}
    </div>
  );
}
