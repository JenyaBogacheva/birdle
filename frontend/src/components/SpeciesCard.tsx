/**
 * Component to display a bird species card with image and details.
 */
import { useState } from 'react';
import type { SpeciesInfo } from '../types/observation';

interface SpeciesCardProps {
  species: SpeciesInfo;
  isPrimary?: boolean;
}

export function SpeciesCard({ species, isPrimary = false }: SpeciesCardProps) {
  const [imageError, setImageError] = useState(false);

  const cardBgColor = isPrimary ? 'bg-blue-50' : 'bg-gray-50';
  const cardBorderColor = isPrimary ? 'border-blue-200' : 'border-gray-200';
  const headingColor = isPrimary ? 'text-blue-900' : 'text-gray-900';
  const textColor = isPrimary ? 'text-blue-800' : 'text-gray-700';

  return (
    <div className={`border rounded-lg p-4 ${cardBgColor} ${cardBorderColor}`}>
      {/* Image Section */}
      {species.image_url && !imageError && (
        <div className="mb-3">
          <img
            src={species.image_url}
            alt={species.common_name}
            className="w-full h-48 object-cover rounded-lg"
            onError={() => setImageError(true)}
          />
          {species.image_credit && (
            <p className="text-xs text-gray-500 mt-1">
              Photo by {species.image_credit}
            </p>
          )}
        </div>
      )}

      {/* Header with Name and Confidence Badge */}
      <div className="flex items-center justify-between mb-2">
        <h4 className={`font-semibold text-lg ${headingColor}`}>
          {species.common_name}
        </h4>
        {species.confidence && (
          <span
            className={`px-2 py-1 rounded-full text-xs font-medium ${
              species.confidence === 'high'
                ? 'bg-green-100 text-green-800'
                : species.confidence === 'medium'
                ? 'bg-yellow-100 text-yellow-800'
                : 'bg-orange-100 text-orange-800'
            }`}
          >
            {species.confidence.toUpperCase()}
          </span>
        )}
      </div>

      {/* Scientific Name */}
      <p className={`text-sm italic ${textColor} mb-2`}>
        {species.scientific_name}
      </p>

      {/* Reasoning */}
      {species.reasoning && (
        <p className="text-sm text-gray-600 mb-3">{species.reasoning}</p>
      )}

      {/* eBird Link */}
      <a
        href={species.range_link}
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
  );
}
