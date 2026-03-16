/**
 * API client for backend communication.
 */
import type { ObservationInput, RecommendationResponse } from '../types/observation';

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
