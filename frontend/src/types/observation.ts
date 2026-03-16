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

export type StreamEvent =
  | { type: 'status'; message: string }
  | { type: 'thinking'; content: string }
  | { type: 'tool_call'; tool: string; input: Record<string, unknown> }
  | { type: 'tool_result'; tool: string; summary: string }
  | { type: 'result'; data: RecommendationResponse }
  | { type: 'error'; message: string }
  | { type: 'done' };
