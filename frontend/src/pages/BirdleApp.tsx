// frontend/src/pages/BirdleApp.tsx
import { useState, useCallback, useRef, useEffect } from 'react';
import BirdBackground from '../components/BirdBackground';
import PencilAnnotations from '../components/PencilAnnotations';
import { BirdForm } from '../components/BirdForm';
import DetectiveNotes, { cannedNoteForEvent } from '../components/DetectiveNotes';
import CandidateBoard from '../components/CandidateBoard';
import ResultOverlay from '../components/ResultOverlay';
import { AwaitingInputPrompt } from '../components/AwaitingInputPrompt';
import { identifyBirdStream, resumeIdentificationStream } from '../api/client';
import type {
  ObservationInput,
  RecommendationResponse,
  CandidateInfo,
  AppPhase,
  AwaitingInput,
  StreamEvent,
} from '../types/observation';

// Hardcoded landing bird — Common Kingfisher from Macaulay Library
const LANDING_BIRD_URL = 'https://cdn.download.ams.birds.cornell.edu/api/v2/asset/303899551/1800';

let noteIdCounter = 0;

interface DetectiveNote {
  id: string;
  message: string;
}

export default function BirdleApp() {
  const [phase, setPhase] = useState<AppPhase>('landing');
  const [backgroundSrc, setBackgroundSrc] = useState(LANDING_BIRD_URL);
  const [isLoading, setIsLoading] = useState(false);
  const [notes, setNotes] = useState<DetectiveNote[]>([]);
  const [candidates, setCandidates] = useState<CandidateInfo[]>([]);
  const [result, setResult] = useState<RecommendationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [awaiting, setAwaiting] = useState<AwaitingInput | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const phaseRef = useRef<AppPhase>(phase);
  // Keep ref in sync so the stream callback always sees current phase
  useEffect(() => { phaseRef.current = phase; }, [phase]);

  const addNote = useCallback((message: string) => {
    noteIdCounter++;
    setNotes((prev) => [...prev, { id: `note-${noteIdCounter}`, message }]);
  }, []);

  const handleStreamEvent = useCallback((event: StreamEvent) => {
    switch (event.type) {
      case 'session_id':
        sessionIdRef.current = event.session_id;
        break;
      case 'status': {
        const canned = cannedNoteForEvent('status');
        if (canned && phaseRef.current !== 'thinking') addNote(canned);
        break;
      }
      case 'detective_note':
        addNote(event.message);
        break;
      case 'candidates':
        setCandidates(event.data);
        break;
      case 'tool_call': {
        const canned = cannedNoteForEvent('tool_call', event.tool);
        if (canned) addNote(canned);
        break;
      }
      case 'tool_result': {
        const canned = cannedNoteForEvent('tool_result', undefined, event.summary);
        if (canned) addNote(canned);
        break;
      }
      case 'awaiting_input':
        // Agent paused to ask a clarifying / disambiguation question.
        setAwaiting({ reason: event.reason, question: event.question, options: event.options });
        break;
      case 'result':
        setAwaiting(null);
        // Phase 3: Reveal — crossfade to winner
        if (event.data.top_species?.image_url) {
          setBackgroundSrc(event.data.top_species.image_url);
        }
        setPhase('reveal');
        // Phase 4: Result — after dramatic pause
        setTimeout(() => {
          setResult(event.data);
          setPhase('result');
        }, 1500);
        break;
      case 'error': {
        const canned = cannedNoteForEvent('error');
        if (canned) addNote(canned);
        setError(event.message);
        setAwaiting(null);
        break;
      }
      case 'done':
        setIsLoading(false);
        break;
    }
  }, [addNote]);

  const handleSubmit = async (observation: ObservationInput) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    sessionIdRef.current = null;
    setPhase('thinking');
    setIsLoading(true);
    setNotes([]);
    setCandidates([]);
    setResult(null);
    setError(null);
    setAwaiting(null);

    try {
      await identifyBirdStream(observation, handleStreamEvent, controller.signal);
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(err instanceof Error ? err.message : 'Something went wrong');
      addNote('Hmm, hit a snag...');
      setIsLoading(false);
    }
  };

  const handleAnswer = async (message: string) => {
    const sessionId = sessionIdRef.current;
    if (!sessionId) {
      setError('Lost the session. Please start a new identification.');
      setAwaiting(null);
      return;
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setAwaiting(null);
    setIsLoading(true);
    setError(null);

    try {
      await resumeIdentificationStream(
        { session_id: sessionId, user_message: message },
        handleStreamEvent,
        controller.signal,
      );
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(err instanceof Error ? err.message : 'Something went wrong');
      addNote('Hmm, hit a snag...');
      setIsLoading(false);
    }
  };

  const handleReset = () => {
    abortRef.current?.abort();
    sessionIdRef.current = null;
    setPhase('landing');
    setBackgroundSrc(LANDING_BIRD_URL);
    setNotes([]);
    setCandidates([]);
    setResult(null);
    setError(null);
    setAwaiting(null);
    setIsLoading(false);
  };

  return (
    <div className="relative w-screen h-screen overflow-hidden">
      <BirdBackground src={backgroundSrc} />

      {/* Branding */}
      <h1 className="absolute top-6 left-8 font-hand text-3xl text-primary z-10">
        Birdle
      </h1>

      {/* Phase 1: Landing */}
      {phase === 'landing' && (
        <>
          <PencilAnnotations />
          <div className="absolute inset-0 flex items-end justify-center pb-16">
            <BirdForm onSubmit={handleSubmit} isLoading={isLoading} />
          </div>
        </>
      )}

      {/* Phase 2: Thinking (+ HITL pause) */}
      {(phase === 'thinking' || phase === 'reveal') && (
        <>
          <DetectiveNotes notes={notes} />
          <CandidateBoard candidates={candidates} />

          {/* HITL: the detective turns to ask you a question */}
          {awaiting && !isLoading && (
            <div className="absolute inset-0 flex items-center justify-center p-8 z-20">
              <div className="w-full max-w-lg">
                <AwaitingInputPrompt
                  question={awaiting.question}
                  options={awaiting.options}
                  onAnswer={handleAnswer}
                />
              </div>
            </div>
          )}

          {error && (
            <div className="absolute bottom-8 left-8 right-8">
              <div className="glass rounded-lg p-4 max-w-md">
                <p className="font-hand text-secondary">{error}</p>
                <button
                  onClick={handleReset}
                  className="font-hand text-primary mt-2 hover:underline"
                >
                  Try again
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* Phase 4: Result */}
      {phase === 'result' && result && (
        <ResultOverlay result={result} onReset={handleReset} />
      )}
    </div>
  );
}
