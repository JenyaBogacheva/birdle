/**
 * API client for backend communication.
 */
import type { ObservationInput, RecommendationResponse, StreamEvent } from '../types/observation';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export async function identifyBird(
  observation: ObservationInput
): Promise<RecommendationResponse> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 95_000);

  try {
    const response = await fetch(`${API_BASE_URL}/api/identify`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(observation),
      signal: controller.signal,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const errorMessage = errorData.detail || response.statusText || 'API request failed';
      throw new Error(errorMessage);
    }

    return response.json();
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('Request timed out after 45 seconds. Please try again.');
    }
    if (error instanceof TypeError && error.message.includes('fetch')) {
      throw new Error('Cannot connect to server. Please ensure the backend is running at ' + API_BASE_URL);
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function identifyBirdStream(
  observation: ObservationInput,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const controller = new AbortController();
  const connectionTimeout = setTimeout(() => controller.abort(), 5_000);

  // Link external signal to our controller
  const onAbort = () => controller.abort();
  signal?.addEventListener('abort', onAbort);

  try {
    const response = await fetch(`${API_BASE_URL}/api/identify/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(observation),
      signal: controller.signal,
    });
    clearTimeout(connectionTimeout);

    if (!response.ok) {
      throw new Error(`Stream request failed: ${response.status}`);
    }

    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let receivedDone = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const parts = buffer.split('\n\n');
      buffer = parts.pop() || '';
      for (const part of parts) {
        const line = part.trim();
        if (line.startsWith('data: ')) {
          const event = JSON.parse(line.slice(6)) as StreamEvent;
          onEvent(event);
          if (event.type === 'done') receivedDone = true;
        }
      }
    }

    if (!receivedDone) {
      throw new Error('Stream ended unexpectedly');
    }
  } catch (error) {
    clearTimeout(connectionTimeout);
    if (error instanceof DOMException && error.name === 'AbortError') {
      // If it was our connection timeout, throw a specific message
      if (!signal?.aborted) {
        throw new Error('Could not connect to streaming endpoint');
      }
      // If it was the caller's abort, just return silently
      return;
    }
    throw error;
  } finally {
    signal?.removeEventListener('abort', onAbort);
  }
}
