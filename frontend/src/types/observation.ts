/**
 * TypeScript types mirroring backend Pydantic schemas.
 */

export interface ObservationInput {
  description: string;
  location?: string;
  observed_at?: string;
}

export interface SpeciesInfo {
  scientific_name: string;
  common_name: string;
  species_code?: string;
  range_link: string;
  confidence?: string;
  reasoning?: string;
  image_url?: string;
  image_credit?: string;
}

export interface RecommendationResponse {
  message: string;
  top_species?: SpeciesInfo;
  alternate_species?: SpeciesInfo[];
  clarification?: string;
}

export interface CandidateInfo {
  name: string;
  species_code: string;
  status: 'considering' | 'eliminated';
  reason?: string;
  image_url?: string;
  image_credit?: string;
}

export type AppPhase = 'landing' | 'thinking' | 'reveal' | 'result';

/** Payload the backend sends when the graph pauses to ask the user a question. */
export interface AwaitingInput {
  reason: string;
  question: string;
  options?: string[];
}

/** Body for POST /api/identify/resume — continues a paused session. */
export interface ResumeInput {
  session_id: string;
  user_message: string;
}

export type StreamEvent =
  | { type: 'session_id'; session_id: string }
  | { type: 'status'; message: string }
  | { type: 'thinking'; content: string }
  | { type: 'tool_call'; tool: string; input: Record<string, unknown> }
  | { type: 'tool_result'; tool: string; summary: string }
  | { type: 'detective_note'; message: string }
  | { type: 'candidates'; data: CandidateInfo[] }
  | { type: 'awaiting_input'; reason: string; question: string; options?: string[] }
  | { type: 'result'; data: RecommendationResponse }
  | { type: 'error'; message: string }
  | { type: 'done' };
