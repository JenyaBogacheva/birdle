/**
 * Birdle session controller. Owns the conversation state machine and adapts
 * the backend SSE protocol into the redesigned feed model. Both the mobile and
 * desktop layouts consume this hook.
 */
import { useCallback, useMemo, useRef, useState, type CSSProperties } from 'react';
import {
  identifyBird,
  identifyBirdStream,
  resumeIdentificationStream,
  continueIdentificationStream,
} from '../api/client';
import type { ObservationInput, StreamEvent } from '../types/observation';
import { buildVars, DEFAULT_THEME } from '../theme/birdleTheme';
import {
  isSameSpecies,
  toResultCardData,
  type FeedItem,
  type ResultCardData,
} from '../components/birdle/types';

const AMBIENT_PHOTO = "url('/birdle-bg.jpg')";

// The theme is constant in production, so its CSS-var map is built once rather
// than on every render; only --photo-url changes (see `vars` below).
const BASE_VARS = buildVars(DEFAULT_THEME);

let _uid = 0;
const uid = () => ++_uid;

export type Phase = 'compose' | 'conversation';

/** How to re-run a turn on retry. */
type LastTurn =
  | { type: 'start' }
  | { type: 'answer'; message: string }
  | { type: 'followUp'; message: string };

/** Drop a trailing error item (and the now-empty thinking block it replaced) so
 *  a retry can re-run the turn in place rather than stacking duplicates. */
function stripTrailingError(feed: FeedItem[]): FeedItem[] {
  const next = [...feed];
  while (next.length && next[next.length - 1].kind === 'error') next.pop();
  while (
    next.length &&
    next[next.length - 1].kind === 'thinking' &&
    (next[next.length - 1] as { steps: string[] }).steps.length === 0
  ) {
    next.pop();
  }
  return next;
}

export interface BirdleSession {
  phase: Phase;
  desc: string;
  loc: string;
  time: string;
  feed: FeedItem[];
  isLoading: boolean;
  /** Whether the required fields (description + location or coords) are filled. */
  canStart: boolean;
  /** True once the latest turn has concluded — a follow-up can be sent. */
  canFollowUp: boolean;
  /** Latest confident result in the feed, for the desktop poster hero. */
  result: ResultCardData | null;
  vars: CSSProperties;
  coords: { lat: number; lng: number } | null;
  geoStatus: 'idle' | 'locating' | 'on' | 'error';
  setDesc: (v: string) => void;
  setLoc: (v: string) => void;
  setTime: (v: string) => void;
  useMyLocation: () => void;
  clearCoords: () => void;
  start: () => void;
  answer: (message: string) => void;
  followUp: (message: string) => void;
  reset: () => void;
  retry: () => void;
}

export function useBirdleSession(): BirdleSession {
  const [phase, setPhase] = useState<Phase>('compose');
  const [desc, setDesc] = useState('');
  const [loc, setLoc] = useState('');
  const [time, setTime] = useState('');
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [geoStatus, setGeoStatus] = useState<'idle' | 'locating' | 'on' | 'error'>('idle');

  const useMyLocation = useCallback(() => {
    if (!('geolocation' in navigator)) { setGeoStatus('error'); return; }
    setGeoStatus('locating');
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        setGeoStatus('on');
      },
      () => setGeoStatus('error'),
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 600000 },
    );
  }, []);

  const clearCoords = useCallback(() => { setCoords(null); setGeoStatus('idle'); }, []);

  const sessionIdRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const lastTurnRef = useRef<LastTurn | null>(null);
  const thinkingIdRef = useRef<number | null>(null);
  const gotTerminalRef = useRef(false);

  const result = useMemo<ResultCardData | null>(() => {
    for (let i = feed.length - 1; i >= 0; i--) {
      const item = feed[i];
      if (item.kind === 'result') return item.data;
    }
    return null;
  }, [feed]);

  const photoUrl = result?.photo ? `url('${result.photo}')` : AMBIENT_PHOTO;
  const vars = useMemo(
    () => ({ ...BASE_VARS, '--photo-url': photoUrl }) as CSSProperties,
    [photoUrl],
  );

  /** Append a step line to the active thinking block (de-duping repeats). */
  const pushStep = useCallback((line: string) => {
    const id = thinkingIdRef.current;
    if (id == null) return;
    setFeed((f) =>
      f.map((item) => {
        if (item.id !== id || item.kind !== 'thinking') return item;
        if (item.steps[item.steps.length - 1] === line) return item;
        return { ...item, steps: [...item.steps, line] };
      }),
    );
  }, []);

  /** Mark the active thinking block done and append a terminal item. `terminal`
   *  may be a builder that derives the item from the (pre-update) feed. */
  const finishThinking = useCallback(
    (terminal?: FeedItem | ((feed: FeedItem[]) => FeedItem | null)) => {
      const id = thinkingIdRef.current;
      thinkingIdRef.current = null;
      setFeed((f) => {
        const next = f.map((item) =>
          item.id === id && item.kind === 'thinking' ? { ...item, active: false } : item,
        );
        const item = typeof terminal === 'function' ? terminal(f) : terminal;
        if (item) next.push(item);
        return next;
      });
    },
    [],
  );

  const handleStreamEvent = useCallback(
    (event: StreamEvent) => {
      switch (event.type) {
        case 'session_id':
          sessionIdRef.current = event.session_id;
          break;
        case 'status':
          pushStep(event.message);
          break;
        case 'tool_call':
          pushStep(`Checking ${event.tool.replace(/_/g, ' ')}…`);
          break;
        case 'tool_result':
          if (event.summary) pushStep(event.summary);
          break;
        case 'awaiting_input':
          gotTerminalRef.current = true;
          finishThinking({
            id: uid(),
            kind: 'clarify',
            text: event.question,
            options: event.options ?? [],
            answered: null,
          });
          break;
        case 'result': {
          gotTerminalRef.current = true;
          const card = toResultCardData(event.data);
          finishThinking((f): FeedItem => {
            if (!card) {
              const message = event.data.message || '';
              const clarification = event.data.clarification || '';
              return {
                id: uid(),
                kind: 'inconclusive',
                title: 'Not enough to go on — yet',
                // Lead with the agent's own explanation; surface the "what would
                // help" examples as a separate hint. Only fall back to the
                // clarification as the body when there's no message at all, so
                // the same text never renders twice.
                body: message || clarification,
                clarification: message ? clarification : undefined,
              };
            }
            // If this turn identifies the same bird as the most recent result,
            // answer conversationally instead of re-showing the card; a changed
            // or first identification shows the card.
            let prev: ResultCardData | undefined;
            for (let i = f.length - 1; i >= 0; i--) {
              const it = f[i];
              if (it.kind === 'result') { prev = it.data; break; }
            }
            if (prev && isSameSpecies(prev, card)) {
              return { id: uid(), kind: 'answer', text: card.summary };
            }
            return { id: uid(), kind: 'result', data: card };
          });
          break;
        }
        case 'error':
          gotTerminalRef.current = true;
          finishThinking({ id: uid(), kind: 'error', text: event.message, canRetry: true });
          break;
        case 'thinking':
        case 'detective_note':
        case 'candidates':
        case 'done':
          break;
      }
    },
    [pushStep, finishThinking],
  );

  const beginTurn = useCallback((userText: string) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    gotTerminalRef.current = false;
    const thinkingId = uid();
    thinkingIdRef.current = thinkingId;
    setIsLoading(true);
    return { controller, thinkingId, userText };
  }, []);

  /** Wire a stream promise's catch/finally to the turn's loading + error UI. */
  const runStream = useCallback(
    (promise: Promise<void>, controller: AbortController) => {
      promise
        .catch(() => {
          if (controller.signal.aborted || gotTerminalRef.current) return;
          handleStreamEvent({
            type: 'error',
            message: 'The conversation was interrupted. Please try again.',
          });
        })
        .finally(() => {
          if (!controller.signal.aborted) setIsLoading(false);
        });
    },
    [handleStreamEvent],
  );

  const start = useCallback(() => {
    const description = desc.trim();
    const location = loc.trim();
    if (!description || (!location && !coords)) return; // need a description plus either a typed location or coordinates
    const observation: ObservationInput = {
      description,
      ...(location && { location }),
      ...(coords && { lat: coords.lat, lng: coords.lng }),
      ...(time.trim() && { observed_at: time.trim() }),
    };
    lastTurnRef.current = { type: 'start' };
    sessionIdRef.current = null;

    const { controller, thinkingId } = beginTurn(description);
    setPhase('conversation');
    setFeed([
      { id: uid(), kind: 'user', text: description },
      { id: thinkingId, kind: 'thinking', steps: [], active: true },
    ]);

    identifyBirdStream(observation, handleStreamEvent, controller.signal)
      .catch(async () => {
        if (controller.signal.aborted || gotTerminalRef.current) return;
        try {
          const res = await identifyBird(observation);
          handleStreamEvent({ type: 'result', data: res });
        } catch (err) {
          const msg = err instanceof Error ? err.message : 'Something went wrong. Please try again.';
          handleStreamEvent({ type: 'error', message: msg });
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false);
      });
  }, [desc, loc, time, coords, beginTurn, handleStreamEvent]);

  /**
   * Shared driver for the two post-start turn kinds: answering a pending
   * clarify (via /resume) and a follow-up after a conclusion (via /continue).
   * On a retry (`replaceUser`) the existing user bubble is kept and a trailing
   * error dropped, rather than appending a duplicate reply.
   */
  const sessionTurn = useCallback(
    (message: string, via: 'resume' | 'continue', opts: { replaceUser?: boolean } = {}) => {
      const trimmed = message.trim();
      if (!trimmed) return;
      const sessionId = sessionIdRef.current;
      lastTurnRef.current = { type: via === 'resume' ? 'answer' : 'followUp', message: trimmed };

      const { controller, thinkingId } = beginTurn(trimmed);
      setFeed((f) => {
        let next = opts.replaceUser ? stripTrailingError(f) : [...f];
        // Answering a clarify marks its chip (idempotent if already marked).
        if (via === 'resume') {
          next = next.map((item) =>
            item.kind === 'clarify' && item.answered === null
              ? { ...item, answered: trimmed }
              : item,
          );
        }
        if (!opts.replaceUser) {
          next.push({ id: uid(), kind: 'user', text: trimmed });
        }
        if (!sessionId) {
          next.push({
            id: uid(),
            kind: 'error',
            text: 'Lost the session — please start a new identification.',
            canRetry: false,
          });
          thinkingIdRef.current = null;
        } else {
          next.push({ id: thinkingId, kind: 'thinking', steps: [], active: true });
        }
        return next;
      });

      if (!sessionId) {
        controller.abort();
        setIsLoading(false);
        return;
      }

      const stream = via === 'resume' ? resumeIdentificationStream : continueIdentificationStream;
      runStream(
        stream({ session_id: sessionId, user_message: trimmed }, handleStreamEvent, controller.signal),
        controller,
      );
    },
    [beginTurn, handleStreamEvent, runStream],
  );

  const answer = useCallback((message: string) => sessionTurn(message, 'resume'), [sessionTurn]);
  const followUp = useCallback((message: string) => sessionTurn(message, 'continue'), [sessionTurn]);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    sessionIdRef.current = null;
    thinkingIdRef.current = null;
    lastTurnRef.current = null;
    setIsLoading(false);
    setPhase('compose');
    setFeed([]);
  }, []);

  // Re-run the turn that failed: turn 1 restarts from the form fields; a
  // clarify answer or follow-up re-streams in place (its user bubble already
  // sits in the feed, so the trailing error is dropped, not duplicated).
  const retry = useCallback(() => {
    const last = lastTurnRef.current;
    if (!last) return;
    if (last.type === 'start') {
      start();
    } else {
      sessionTurn(last.message, last.type === 'answer' ? 'resume' : 'continue', { replaceUser: true });
    }
  }, [start, sessionTurn]);

  const lastItem = feed[feed.length - 1];
  const canFollowUp =
    phase === 'conversation' &&
    !isLoading &&
    (lastItem?.kind === 'result' ||
      lastItem?.kind === 'inconclusive' ||
      lastItem?.kind === 'answer');

  return {
    phase, desc, loc, time, feed, isLoading, result, vars,
    canStart: !!desc.trim() && (!!loc.trim() || !!coords),
    canFollowUp,
    coords, geoStatus, useMyLocation, clearCoords,
    setDesc, setLoc, setTime, start, answer, followUp, reset, retry,
  };
}
