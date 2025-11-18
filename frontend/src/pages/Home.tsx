/**
 * Home page with bird identification form and results.
 */
import { useState, useEffect, useRef } from 'react';
import { BirdForm } from '../components/BirdForm';
import { ResultPanel } from '../components/ResultPanel';
import { identifyBird } from '../api/client';
import type { ObservationInput, RecommendationResponse } from '../types/observation';

type LoadingStage = 'analyzing' | 'fetching' | 'identifying' | null;

export function Home() {
  const [result, setResult] = useState<RecommendationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingStage, setLoadingStage] = useState<LoadingStage>(null);
  const [elapsedTime, setElapsedTime] = useState(0);
  const [canRetry, setCanRetry] = useState(false);
  const timerRef = useRef<number | null>(null);
  const lastObservationRef = useRef<ObservationInput | null>(null);

  // Timer effect for elapsed time during loading
  useEffect(() => {
    if (isLoading) {
      const startTime = Date.now();
      timerRef.current = window.setInterval(() => {
        setElapsedTime(Math.floor((Date.now() - startTime) / 1000));
      }, 1000);
    } else {
      if (timerRef.current !== null) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      setElapsedTime(0);
    }

    return () => {
      if (timerRef.current !== null) {
        clearInterval(timerRef.current);
      }
    };
  }, [isLoading]);

  // Simulate loading stages (since backend is single call, we approximate timing)
  useEffect(() => {
    if (!isLoading) {
      setLoadingStage(null);
      return;
    }

    setLoadingStage('analyzing');
    const timer1 = setTimeout(() => setLoadingStage('fetching'), 2000);
    const timer2 = setTimeout(() => setLoadingStage('identifying'), 5000);

    return () => {
      clearTimeout(timer1);
      clearTimeout(timer2);
    };
  }, [isLoading]);

  const handleSubmit = async (observation: ObservationInput) => {
    lastObservationRef.current = observation;
    setIsLoading(true);
    setError(null);
    setResult(null);
    setCanRetry(false);

    try {
      const response = await identifyBird(observation);
      setResult(response);
      setCanRetry(false);
    } catch (err) {
      const errorMessage =
        err instanceof Error
          ? err.message
          : 'An unexpected error occurred. Please try again.';
      setError(errorMessage);
      // Allow retry for network errors or timeouts
      setCanRetry(
        errorMessage.includes('timeout') ||
          errorMessage.includes('network') ||
          errorMessage.includes('try again')
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleRetry = () => {
    if (lastObservationRef.current) {
      handleSubmit(lastObservationRef.current);
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

          {/* Loading Indicator with Stages */}
          {isLoading && (
            <div className="bg-white rounded-xl shadow-lg p-8 mb-8">
              <div className="flex flex-col items-center justify-center space-y-4">
                {/* Spinner */}
                <div className="relative">
                  <div className="w-16 h-16 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin"></div>
                </div>

                {/* Loading Stage */}
                <div className="text-center">
                  <p className="text-lg font-medium text-gray-900">
                    {loadingStage === 'analyzing' &&
                      'Analyzing your description...'}
                    {loadingStage === 'fetching' &&
                      'Fetching recent bird sightings...'}
                    {loadingStage === 'identifying' && 'Identifying species...'}
                  </p>
                  <p className="text-sm text-gray-500 mt-2">
                    {elapsedTime > 0 && `${elapsedTime}s elapsed`}
                  </p>
                </div>

                {/* Progress Dots */}
                <div className="flex space-x-2">
                  <div
                    className={`w-2 h-2 rounded-full ${
                      loadingStage === 'analyzing'
                        ? 'bg-blue-600'
                        : 'bg-gray-300'
                    }`}
                  />
                  <div
                    className={`w-2 h-2 rounded-full ${
                      loadingStage === 'fetching' ? 'bg-blue-600' : 'bg-gray-300'
                    }`}
                  />
                  <div
                    className={`w-2 h-2 rounded-full ${
                      loadingStage === 'identifying'
                        ? 'bg-blue-600'
                        : 'bg-gray-300'
                    }`}
                  />
                </div>
              </div>
            </div>
          )}

          {/* Results */}
          {(result || error) && (
            <div className="animate-fade-in">
              <ResultPanel
                result={result}
                error={error}
                canRetry={canRetry}
                onRetry={handleRetry}
              />
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
