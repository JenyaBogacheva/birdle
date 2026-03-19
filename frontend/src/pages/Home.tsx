/**
 * Home page with bird identification form and results.
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { BirdForm } from '../components/BirdForm';
import { ResultPanel } from '../components/ResultPanel';
import { identifyBird, identifyBirdStream } from '../api/client';
import type { ObservationInput, RecommendationResponse, StreamEvent } from '../types/observation';

export function Home() {
  const [result, setResult] = useState<RecommendationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState('');
  const [thinkingText, setThinkingText] = useState('');
  const [showThinking, setShowThinking] = useState(false);
  const [elapsedTime, setElapsedTime] = useState(0);
  const [canRetry, setCanRetry] = useState(false);
  const timerRef = useRef<number | null>(null);
  const lastObservationRef = useRef<ObservationInput | null>(null);
  const abortRef = useRef<AbortController | null>(null);

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

  const handleStreamEvent = useCallback((event: StreamEvent) => {
    switch (event.type) {
      case 'status':
        setStatusMessage(event.message);
        break;
      case 'thinking':
        setThinkingText((prev) => prev + event.content);
        break;
      case 'result':
        setResult(event.data);
        break;
      case 'error':
        setError(event.message);
        setCanRetry(true);
        break;
      case 'tool_call':
        setStatusMessage(`Calling ${event.tool}...`);
        break;
      case 'tool_result':
        setStatusMessage(event.summary);
        break;
      case 'done':
        break;
    }
  }, []);

  const handleSubmit = async (observation: ObservationInput) => {
    // Abort any in-flight stream
    abortRef.current?.abort();
    const abortController = new AbortController();
    abortRef.current = abortController;

    lastObservationRef.current = observation;
    setIsLoading(true);
    setError(null);
    setResult(null);
    setCanRetry(false);
    setStatusMessage('');
    setThinkingText('');
    setShowThinking(false);

    try {
      // Try streaming first
      await identifyBirdStream(observation, handleStreamEvent, abortController.signal);
    } catch {
      // Fallback to non-streaming if stream fails
      if (abortController.signal.aborted) return; // User cancelled
      try {
        setStatusMessage('Identifying your bird...');
        const response = await identifyBird(observation);
        setResult(response);
      } catch (err) {
        const errorMessage =
          err instanceof Error
            ? err.message
            : 'An unexpected error occurred. Please try again.';
        setError(errorMessage);
        setCanRetry(
          errorMessage.includes('timeout') ||
            errorMessage.includes('network') ||
            errorMessage.includes('try again')
        );
      }
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
    <div className="min-h-screen bg-gradient-to-br from-pink-100 via-orange-50 to-yellow-100 relative overflow-hidden">
      {/* Decorative bird emojis - hidden on mobile, visible on tablet+ */}
      {/* Top corners */}
      <div className="hidden sm:block fixed top-[8%] left-[6%] text-6xl opacity-25 animate-bounce-slow pointer-events-none">
        🦆
      </div>
      <div className="hidden sm:block fixed top-[8%] right-[6%] text-6xl opacity-25 animate-bounce-slow pointer-events-none" style={{ animationDelay: '1s' }}>
        🦢
      </div>

      {/* Middle sides */}
      <div className="hidden sm:block fixed top-[40%] left-[3%] text-5xl opacity-[0.15] animate-bounce-slow pointer-events-none" style={{ animationDelay: '0.5s' }}>
        🪶
      </div>
      <div className="hidden sm:block fixed top-[40%] right-[3%] text-5xl opacity-[0.15] animate-bounce-slow pointer-events-none" style={{ animationDelay: '1.5s' }}>
        🐓
      </div>

      {/* Bottom corners */}
      <div className="hidden sm:block fixed bottom-[10%] left-[8%] text-6xl opacity-25 animate-bounce-slow pointer-events-none" style={{ animationDelay: '0.8s' }}>
        🦚
      </div>
      <div className="hidden sm:block fixed bottom-[10%] right-[8%] text-6xl opacity-25 animate-bounce-slow pointer-events-none" style={{ animationDelay: '2s' }}>
        🦤
      </div>

      <div className="container mx-auto px-4 py-12 relative z-10">
        <div className="max-w-3xl mx-auto">
          {/* Header */}
          <div className="text-center mb-12">
            <div className="flex items-center justify-center gap-2 sm:gap-3 mb-3">
              <span className="text-4xl sm:text-5xl">🦜</span>
              <h1 className="text-4xl sm:text-5xl font-bold text-gray-900">
                birdle-ai ✨
              </h1>
              <span className="text-4xl sm:text-5xl">🦩</span>
            </div>
            <p className="text-lg sm:text-xl text-gray-700">
              spotted a bird? let's figure out what it is!
            </p>
          </div>

          {/* Main Content */}
          <div className="bg-white rounded-xl shadow-lg p-8 mb-8">
            <BirdForm onSubmit={handleSubmit} isLoading={isLoading} />
          </div>

          {/* Loading Indicator with Streaming Status */}
          {isLoading && (
            <div className="bg-white rounded-xl shadow-lg p-8 mb-8">
              <div className="flex flex-col items-center justify-center space-y-4">
                {/* Spinner */}
                <div className="relative">
                  <div className="w-16 h-16 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin"></div>
                </div>

                {/* Status Message */}
                <div className="text-center">
                  <p className="text-lg font-medium text-gray-900">
                    {statusMessage || 'Starting...'}
                  </p>
                  <p className="text-sm text-gray-500 mt-2">
                    {elapsedTime > 0 && `${elapsedTime}s elapsed`}
                  </p>
                </div>
              </div>

              {/* Thinking Block (collapsible) */}
              {thinkingText && (
                <div className="mt-6 border-t pt-4">
                  <button
                    onClick={() => setShowThinking(!showThinking)}
                    className="text-sm text-gray-500 hover:text-gray-700 flex items-center gap-1"
                  >
                    <span className="text-xs">{showThinking ? '▼' : '▶'}</span>
                    {showThinking ? 'Hide thinking' : 'Show thinking'}
                  </button>
                  {showThinking && (
                    <div className="mt-2 p-3 bg-gray-50 rounded-lg text-sm text-gray-700 whitespace-pre-wrap max-h-64 overflow-y-auto">
                      {thinkingText}
                      <span className="inline-block w-2 h-4 bg-gray-400 animate-pulse ml-0.5" />
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Thinking Block (persists after result) */}
          {!isLoading && thinkingText && (result || error) && (
            <div className="bg-white rounded-xl shadow-lg p-4 mb-4">
              <button
                onClick={() => setShowThinking(!showThinking)}
                className="text-sm text-gray-500 hover:text-gray-700 flex items-center gap-1"
              >
                <span className="text-xs">{showThinking ? '▼' : '▶'}</span>
                {showThinking ? 'Hide thinking' : 'Show thinking'}
              </button>
              {showThinking && (
                <div className="mt-2 p-3 bg-gray-50 rounded-lg text-sm text-gray-700 whitespace-pre-wrap max-h-64 overflow-y-auto">
                  {thinkingText}
                </div>
              )}
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
          <div className="text-center mt-12 text-gray-600 text-sm">
            <p>
              powered by fastapi, react, claude, and vibes ⚡✨
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
