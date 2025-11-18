/**
 * Component to display bird identification results.
 */
import type { RecommendationResponse } from '../types/observation';

interface ResultPanelProps {
  result: RecommendationResponse | null;
  error: string | null;
}

export function ResultPanel({ result, error }: ResultPanelProps) {
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

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-6 space-y-4">
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-2">
          Identification Result
        </h3>
        <p className="text-gray-700 leading-relaxed">{result.message}</p>
      </div>

      {result.top_species && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-md font-semibold text-blue-900">Top Match</h4>
            {result.top_species.confidence && (
              <span
                className={`px-2 py-1 rounded-full text-xs font-medium ${
                  result.top_species.confidence === 'high'
                    ? 'bg-green-100 text-green-800'
                    : result.top_species.confidence === 'medium'
                    ? 'bg-yellow-100 text-yellow-800'
                    : 'bg-orange-100 text-orange-800'
                }`}
              >
                {result.top_species.confidence.toUpperCase()} CONFIDENCE
              </span>
            )}
          </div>
          <dl className="space-y-2">
            <div>
              <dt className="text-sm font-medium text-blue-800">
                Common Name
              </dt>
              <dd className="text-base text-blue-900">
                {result.top_species.common_name}
              </dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-blue-800">
                Scientific Name
              </dt>
              <dd className="text-base italic text-blue-900">
                {result.top_species.scientific_name}
              </dd>
            </div>
            {result.top_species.reasoning && (
              <div>
                <dt className="text-sm font-medium text-blue-800">
                  Reasoning
                </dt>
                <dd className="text-sm text-blue-900">
                  {result.top_species.reasoning}
                </dd>
              </div>
            )}
            <div>
              <a
                href={result.top_species.range_link}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center text-sm font-medium text-blue-600 hover:text-blue-800 hover:underline"
              >
                View on eBird
                <svg
                  className="ml-1 h-4 w-4"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                  />
                </svg>
              </a>
            </div>
          </dl>
        </div>
      )}

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
