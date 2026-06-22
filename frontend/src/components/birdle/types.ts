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
  summary: string;
  level: ConfidenceLevel;
  photo?: string;
  imageCredit?: string;
  rangeLink: string;
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
    summary: top.reasoning || res.message,
    level: confidenceLevel(top.confidence),
    photo: top.image_url,
    imageCredit: top.image_credit,
    rangeLink: top.range_link,
    alternates: res.alternate_species ?? [],
  };
}
