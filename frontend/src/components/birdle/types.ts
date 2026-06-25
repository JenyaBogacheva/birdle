/**
 * Conversation feed model for the redesigned Birdle UI.
 * The orchestrator (useBirdleSession) translates backend SSE events into
 * these items; the layout components render them.
 */
import type { RecommendationResponse, SpeciesInfo } from '../../types/observation';
import type { ConfidenceLevel } from './primitives';

export interface UserItem { id: number; kind: 'user'; text: string; }

/** A live "thinking" block. `steps` grows as status/tool events arrive. */
export interface ThinkingItem { id: number; kind: 'thinking'; steps: string[]; active: boolean; }

/** A clarifying question (backend `awaiting_input`); answering resumes the session. */
export interface ClarifyItem {
  id: number;
  kind: 'clarify';
  text: string;
  options: string[];
  answered: string | null;
}

/** A confident-enough identification (backend `result` with top_species). */
export interface ResultItem {
  id: number;
  kind: 'result';
  data: ResultCardData;
}

/** A terminal "not enough to go on" answer (backend `result` without a top match). */
export interface InconclusiveItem {
  id: number;
  kind: 'inconclusive';
  title: string;
  body: string;
  /** Optional "what would help" guidance, shown as a hint below the body. */
  clarification?: string;
}

export interface ErrorItem { id: number; kind: 'error'; text: string; canRetry: boolean; }

/** A conversational reply to a follow-up that didn't change the identification. */
export interface AnswerItem { id: number; kind: 'answer'; text: string; }

export type FeedItem =
  | UserItem | ThinkingItem | ClarifyItem | ResultItem | InconclusiveItem | ErrorItem | AnswerItem;

/** Shape consumed by ResultCard, derived from a SpeciesInfo + message. */
export interface ResultCardData {
  name: string;
  sci: string;
  /** eBird species code, when known — the stable identity used to detect
   *  whether a follow-up changed the species. */
  code?: string;
  summary: string;
  level: ConfidenceLevel;
  photo?: string;
  /** Hero focal point "x% y%" for background-position; absent → static crop. */
  photoFocus?: { x: number; y: number };
  imageCredit?: string;
  rangeLink: string;
  /** A clarifying question the agent attached to a confident-enough result. */
  clarification?: string;
  alternates: SpeciesInfo[];
}

export function confidenceLevel(c?: string): ConfidenceLevel {
  if (c === 'high') return 'confident';
  if (c === 'medium') return 'likely';
  return 'uncertain';
}

/** Build ResultCardData from a backend recommendation that has a top species. */
export function toResultCardData(res: RecommendationResponse): ResultCardData | null {
  const top = res.top_species;
  if (!top) return null;
  return {
    name: top.common_name,
    sci: top.scientific_name,
    code: top.species_code,
    summary: top.reasoning || res.message,
    level: confidenceLevel(top.confidence),
    photo: top.image_url,
    photoFocus: top.image_focus,
    imageCredit: top.image_credit,
    rangeLink: top.range_link,
    clarification: res.clarification || undefined,
    alternates: res.alternate_species ?? [],
  };
}

/**
 * Whether two results identify the same bird. Prefer the eBird species code
 * (stable); fall back to the scientific name only when both codes are absent —
 * and never match on the "Unknown" placeholder, so two unnamed birds aren't
 * collapsed into one.
 */
export function isSameSpecies(a: ResultCardData, b: ResultCardData): boolean {
  if (a.code && b.code) return a.code === b.code;
  const norm = (s: string) => s.trim().toLowerCase();
  const sa = norm(a.sci);
  return !!sa && sa !== 'unknown' && sa === norm(b.sci);
}
