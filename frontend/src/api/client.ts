/**
 * API client for backend communication.
 */
import type {
  ObservationInput,
  RecommendationResponse,
  ResumeInput,
  StreamEvent,
} from '../types/observation';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

/**
 * Coerce a FastAPI error `detail` into a readable string. `detail` may be a
 * plain string, or (for 422 validation errors) an array of {loc, msg} objects.
 */
function formatErrorDetail(detail: unknown, fallback: string): string {
  if (typeof detail === 'string' && detail) return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (d && typeof d === 'object' && 'msg' in d ? String((d as { msg: unknown }).msg) : ''))
      .filter(Boolean);
    if (msgs.length) return msgs.join('; ');
  }
  return fallback || 'API request failed';
}

/**
 * Reverse-geocode a coordinate to a short place label (for the "use my
 * location" field). Returns '' on any failure — callers keep the coordinates.
 */
export async function reverseGeocode(lat: number, lng: number): Promise<string> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/geocode/reverse?lat=${lat}&lng=${lng}`);
    if (!res.ok) return '';
    const data = (await res.json()) as { label?: string };
    return data.label ?? '';
  } catch {
    return '';
  }
}

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
      throw new Error(formatErrorDetail(errorData.detail, response.statusText));
    }

    return response.json();
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('Request timed out after 95 seconds. Please try again.');
    }
    if (error instanceof TypeError && error.message.includes('fetch')) {
      throw new Error('Cannot connect to server. Please ensure the backend is running at ' + API_BASE_URL);
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}

/** Read an SSE response body, dispatching each `data:` event to onEvent. */
async function consumeSSEStream(
  response: Response,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let receivedDone = false;

  let reading = true;
  while (reading) {
    const { done, value } = await reader.read();
    if (done) {
      reading = false;
      break;
    }
    buffer += decoder.decode(value, { stream: true });

    const parts = buffer.split('\n\n');
    buffer = parts.pop() || '';
    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith('data: ')) continue; // skip comments / keepalives
      let event: StreamEvent;
      try {
        event = JSON.parse(line.slice(6)) as StreamEvent;
      } catch {
        // Malformed or partial frame — skip it rather than aborting the whole
        // stream (a parse throw here would strand the UI mid-turn).
        continue;
      }
      onEvent(event);
      if (event.type === 'done') receivedDone = true;
    }
  }

  if (!receivedDone) {
    throw new Error('Stream ended unexpectedly');
  }
}

/** POST a JSON body to an SSE endpoint and stream the events. */
async function streamSSE(
  path: string,
  body: unknown,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const controller = new AbortController();
  const connectionTimeout = setTimeout(() => controller.abort(), 5_000);

  // Link external signal to our controller
  const onAbort = () => controller.abort();
  signal?.addEventListener('abort', onAbort);

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    clearTimeout(connectionTimeout);

    if (!response.ok) {
      throw new Error(`Stream request failed: ${response.status}`);
    }

    await consumeSSEStream(response, onEvent);
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

export function identifyBirdStream(
  observation: ObservationInput,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return streamSSE('/api/identify/stream', observation, onEvent, signal);
}

export function resumeIdentificationStream(
  payload: ResumeInput,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return streamSSE('/api/identify/resume', payload, onEvent, signal);
}

/** Follow-up turn after a result: another turn in the same session. */
export function continueIdentificationStream(
  payload: ResumeInput,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return streamSSE('/api/identify/continue', payload, onEvent, signal);
}
