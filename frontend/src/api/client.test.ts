import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { identifyBirdStream } from './client';
import type { StreamEvent } from '../types/observation';

/** Build a fake fetch Response whose body streams the given SSE text chunks. */
function sseResponse(chunks: string[], ok = true, status = 200): Response {
  let i = 0;
  const reader = {
    read() {
      if (i < chunks.length) {
        const value = new TextEncoder().encode(chunks[i++]);
        return Promise.resolve({ done: false, value });
      }
      return Promise.resolve({ done: true, value: undefined });
    },
  };
  return { ok, status, body: { getReader: () => reader } } as unknown as Response;
}

function dataLine(event: object): string {
  return `data: ${JSON.stringify(event)}\n\n`;
}

describe('identifyBirdStream', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('POSTs to the stream endpoint and delivers each parsed event', async () => {
    vi.mocked(fetch).mockResolvedValue(
      sseResponse([
        dataLine({ type: 'session_id', session_id: 's-1' }),
        dataLine({ type: 'status', message: 'Checking...' }),
        dataLine({ type: 'done' }),
      ]),
    );

    const events: StreamEvent[] = [];
    await identifyBirdStream({ description: 'red bird', location: 'NY' }, (e) =>
      events.push(e),
    );

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/identify/stream'),
      expect.objectContaining({ method: 'POST' }),
    );
    expect(events.map((e) => e.type)).toEqual(['session_id', 'status', 'done']);
  });

  it('handles events split across read() chunks', async () => {
    vi.mocked(fetch).mockResolvedValue(
      sseResponse([
        'data: {"type":"sta',
        'tus","message":"hi"}\n\n' + dataLine({ type: 'done' }),
      ]),
    );

    const events: StreamEvent[] = [];
    await identifyBirdStream({ description: 'x', location: 'y' }, (e) => events.push(e));

    expect(events).toEqual([
      { type: 'status', message: 'hi' },
      { type: 'done' },
    ]);
  });

  it('throws when the stream ends without a done event', async () => {
    vi.mocked(fetch).mockResolvedValue(
      sseResponse([dataLine({ type: 'status', message: 'hi' })]),
    );

    await expect(
      identifyBirdStream({ description: 'x', location: 'y' }, () => {}),
    ).rejects.toThrow('Stream ended unexpectedly');
  });

  it('throws on a non-ok response', async () => {
    vi.mocked(fetch).mockResolvedValue(sseResponse([], false, 500));

    await expect(
      identifyBirdStream({ description: 'x', location: 'y' }, () => {}),
    ).rejects.toThrow('Stream request failed: 500');
  });

  it('returns silently when the caller aborts', async () => {
    const controller = new AbortController();
    vi.mocked(fetch).mockImplementation(() => {
      controller.abort();
      return Promise.reject(new DOMException('Aborted', 'AbortError'));
    });

    await expect(
      identifyBirdStream({ description: 'x', location: 'y' }, () => {}, controller.signal),
    ).resolves.toBeUndefined();
  });

  it('throws a connection error when the internal timeout aborts', async () => {
    vi.mocked(fetch).mockRejectedValue(new DOMException('Aborted', 'AbortError'));

    await expect(
      identifyBirdStream({ description: 'x', location: 'y' }, () => {}),
    ).rejects.toThrow('Could not connect to streaming endpoint');
  });
});
