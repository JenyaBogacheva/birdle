/**
 * Home page with bird identification form and results.
 */
import { useState } from 'react';
import { BirdForm } from '../components/BirdForm';
import { ResultPanel } from '../components/ResultPanel';
import { identifyBird } from '../api/client';
import type { ObservationInput, RecommendationResponse } from '../types/observation';

export function Home() {
  const [result, setResult] = useState<RecommendationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (observation: ObservationInput) => {
    setIsLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await identifyBird(observation);
      setResult(response);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'An unexpected error occurred. Please try again.'
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      <div className="container mx-auto px-4 py-12">
        <div className="max-w-3xl mx-auto">
          {/* Header */}
          <div className="text-center mb-12">
            <h1 className="text-4xl font-bold text-gray-900 mb-3">
              Bird-ID MVP
            </h1>
            <p className="text-lg text-gray-600">
              Describe your bird observation and get instant identification
            </p>
          </div>

          {/* Main Content */}
          <div className="bg-white rounded-xl shadow-lg p-8 mb-8">
            <BirdForm onSubmit={handleSubmit} isLoading={isLoading} />
          </div>

          {/* Results */}
          {(result || error) && (
            <div className="animate-fade-in">
              <ResultPanel result={result} error={error} />
            </div>
          )}

          {/* Footer */}
          <div className="text-center mt-12 text-gray-500 text-sm">
            <p>
              Powered by FastAPI, React, and OpenAI • Iteration 1 (Stubbed
              Flow)
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
