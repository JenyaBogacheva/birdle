/**
 * Birdle session controller. Owns the conversation state machine and adapts
 * the backend SSE protocol into the redesigned feed model. Both the mobile and
 * desktop layouts consume this hook.
 */
import { useCallback, useRef, useState, type CSSProperties } from 'react';
import {
  identifyBird,
  identifyBirdStream,
  resumeIdentificationStream,
  continueIdentificationStream,
} from '../api/client';
import type { ObservationInput, StreamEvent } from '../types/observation';
import { buildVars, DEFAULT_THEME } from '../theme/birdleTheme';
import {
  toResultCardData,
  type FeedItem,
  type ResultCardData,
} from '../components/birdle/types';

const AMBIENT_PHOTO = "url('/birdle-bg.jpg')";

let _uid = 0;
const uid = () => ++_uid;

export type Phase = 'compose' | 'conversation';

export interface BirdleSession {
  phase: Phase;
  desc: string;
  loc: string;
  time: string;
  feed: FeedItem[];
  isLoading: boolean;
  /** Whether the required fields (description + location) are filled. */
  canStart: boolean;
  /** True once the latest turn has concluded — a follow-up can be sent. */
  canFollowUp: boolean;
  /** Latest confident result in the feed, for the desktop poster hero. */
  result: ResultCardData | null;
  vars: CSSProperties;
  setDesc: (v: string) => void;
  setLoc: (v: string) => void;
  setTime: (v: string) => void;
  start: () => void;
  answer: (message: string) => void;
  followUp: (message: string) => void;
  confirm: () => void;
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

  const sessionIdRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const lastObservationRef = useRef<ObservationInput | null>(null);
  const thinkingIdRef = useRef<number | null>(null);
  const gotTerminalRef = useRef(false);
  // Set when the user taps "This is my bird" — locks subsequent follow-ups to
  // conversational answers so the card is never re-shown.
  const confirmedRef = useRef(false);

  const result = feed.reduce<ResultCardData | null>(
    (acc, i) => (i.kind === 'result' ? i.data : acc),
    null,
  );

  const photoUrl = result?.photo ? `url('${result.photo}')` : AMBIENT_PHOTO;
  const vars = { ...buildVars(DEFAULT_THEME), '--photo-url': photoUrl } as CSSProperties;

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

  /** Mark the active thinking block done and append a terminal item. */
  const finishThinking = useCallback((terminal?: FeedItem) => {
    const id = thinkingIdRef.current;
    thinkingIdRef.current = null;
    setFeed((f) => {
      const next = f.map((item) =>
        item.id === id && item.kind === 'thinking' ? { ...item, active: false } : item,
      );
      if (terminal) next.push(terminal);
      return next;
    });
  }, []);

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
          const tId = thinkingIdRef.current;
          thinkingIdRef.current = null;
          setFeed((f) => {
            const next: FeedItem[] = f.map((item) =>
              item.id === tId && item.kind === 'thinking' ? { ...item, active: false } : item,
            );
            if (!card) {
              next.push({
                id: uid(),
                kind: 'inconclusive',
                title: 'Not enough to go on — yet',
                body: event.data.clarification || event.data.message,
              });
              return next;
            }
            // Decide from the feed itself (robust): if the species matches the
            // most recent result — or the user already confirmed it — answer
            // conversationally instead of re-showing the card.
            const norm = (s: string) => s.trim().toLowerCase();
            let prevSci: string | undefined;
            for (let i = f.length - 1; i >= 0; i--) {
              const it = f[i];
              if (it.kind === 'result') { prevSci = it.data.sci; break; }
            }
            const sameSpecies = !!prevSci && norm(prevSci) === norm(card.sci);
            if (confirmedRef.current || sameSpecies) {
              next.push({ id: uid(), kind: 'answer', text: card.summary });
            } else {
              next.push({ id: uid(), kind: 'result', data: card });
            }
            return next;
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

  const start = useCallback(() => {
    const description = desc.trim();
    const location = loc.trim();
    if (!description || !location) return; // backend requires both
    const observation: ObservationInput = {
      description,
      location,
      ...(time.trim() && { observed_at: time.trim() }),
    };
    lastObservationRef.current = observation;
    sessionIdRef.current = null;
    confirmedRef.current = false;

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
  }, [desc, loc, time, beginTurn, handleStreamEvent]);

  const answer = useCallback(
    (message: string) => {
      const trimmed = message.trim();
      if (!trimmed) return;
      const sessionId = sessionIdRef.current;

      // Mark the answered clarify chip, add the user's reply + a new thinking block.
      const { controller, thinkingId } = beginTurn(trimmed);
      setFeed((f) => {
        const next = f.map((item) =>
          item.kind === 'clarify' && item.answered === null
            ? { ...item, answered: trimmed }
            : item,
        );
        next.push({ id: uid(), kind: 'user', text: trimmed });
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

      resumeIdentificationStream(
        { session_id: sessionId, user_message: trimmed },
        handleStreamEvent,
        controller.signal,
      )
        .catch(() => {
          if (controller.signal.aborted || gotTerminalRef.current) return;
          handleStreamEvent({ type: 'error', message: 'The conversation was interrupted. Please try again.' });
        })
        .finally(() => {
          if (!controller.signal.aborted) setIsLoading(false);
        });
    },
    [beginTurn, handleStreamEvent],
  );

  const followUp = useCallback(
    (message: string) => {
      const trimmed = message.trim();
      if (!trimmed) return;
      const sessionId = sessionIdRef.current;

      const { controller, thinkingId } = beginTurn(trimmed);
      setFeed((f) => {
        const next: FeedItem[] = [...f, { id: uid(), kind: 'user', text: trimmed }];
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

      continueIdentificationStream(
        { session_id: sessionId, user_message: trimmed },
        handleStreamEvent,
        controller.signal,
      )
        .catch(() => {
          if (controller.signal.aborted || gotTerminalRef.current) return;
          handleStreamEvent({ type: 'error', message: 'The conversation was interrupted. Please try again.' });
        })
        .finally(() => {
          if (!controller.signal.aborted) setIsLoading(false);
        });
    },
    [beginTurn, handleStreamEvent],
  );

  const reset = useCallback(() => {
    abortRef.current?.abort();
    sessionIdRef.current = null;
    thinkingIdRef.current = null;
    confirmedRef.current = false;
    setIsLoading(false);
    setPhase('compose');
    setFeed([]);
  }, []);

  // The user accepted the identification — lock follow-ups to conversational
  // answers (don't re-show the card).
  const confirm = useCallback(() => {
    confirmedRef.current = true;
  }, []);

  // The form fields still hold the last submission, so re-running start() is
  // enough to retry.
  const retry = useCallback(() => {
    if (lastObservationRef.current) start();
  }, [start]);

  const lastItem = feed[feed.length - 1];
  const canFollowUp =
    phase === 'conversation' &&
    !isLoading &&
    (lastItem?.kind === 'result' ||
      lastItem?.kind === 'inconclusive' ||
      lastItem?.kind === 'answer');

  return {
    phase, desc, loc, time, feed, isLoading, result, vars,
    canStart: !!desc.trim() && !!loc.trim(),
    canFollowUp,
    setDesc, setLoc, setTime, start, answer, followUp, confirm, reset, retry,
  };
}
