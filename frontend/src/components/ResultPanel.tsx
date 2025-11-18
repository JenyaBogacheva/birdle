/**
 * Component to display bird identification results with enhanced error handling.
 */
import { useState } from 'react';
import type { RecommendationResponse } from '../types/observation';
import { SpeciesCard } from './SpeciesCard';

interface ResultPanelProps {
  result: RecommendationResponse | null;
  error: string | null;
  canRetry?: boolean;
  onRetry?: () => void;
}

export function ResultPanel({
  result,
  error,
  canRetry = false,
  onRetry,
}: ResultPanelProps) {
  const [showAlternates, setShowAlternates] = useState(false);

  if (error) {
    // Determine error type for better messaging
    const isTimeout = error.toLowerCase().includes('timeout');
    const isNetwork =
      error.toLowerCase().includes('network') ||
      error.toLowerCase().includes('failed to fetch');
    const isRateLimit = error.toLowerCase().includes('rate limit');

    let errorTitle = 'Error';
    let errorHint = '';

    if (isTimeout) {
      errorTitle = 'Request Timeout';
      errorHint =
        'The request took too long to complete. This might be due to high server load or slow network. Please try again.';
    } else if (isNetwork) {
      errorTitle = 'Network Error';
      errorHint =
        'Could not connect to the server. Please check your internet connection and try again.';
    } else if (isRateLimit) {
      errorTitle = 'Rate Limit Exceeded';
      errorHint = 'Too many requests. Please wait a moment before trying again.';
    }

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
          <div className="ml-3 flex-1">
            <h3 className="text-sm font-medium text-red-800">{errorTitle}</h3>
            <p className="mt-2 text-sm text-red-700">{error}</p>
            {errorHint && (
              <p className="mt-2 text-sm text-red-600 italic">{errorHint}</p>
            )}
            {canRetry && onRetry && (
              <button
                onClick={onRetry}
                className="mt-4 px-4 py-2 bg-red-600 text-white text-sm font-medium rounded-lg hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 transition-colors"
              >
                Try Again
              </button>
            )}
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

      {/* Clarification Question - Emphasized for low confidence */}
      {result.clarification && (
        <div className="bg-yellow-50 border-2 border-yellow-400 rounded-lg p-5 shadow-sm">
          <div className="flex items-start">
            <div className="flex-shrink-0">
              <svg
                className="h-6 w-6 text-yellow-600"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
            </div>
            <div className="ml-3">
              <h4 className="text-base font-semibold text-yellow-900 mb-2">
                💡 Need More Information
              </h4>
              <p className="text-sm text-yellow-800 leading-relaxed">
                {result.clarification}
              </p>
              <p className="text-xs text-yellow-700 mt-3 italic">
                Tip: Provide more specific details about size, colors, behavior,
                or habitat to improve identification accuracy.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
