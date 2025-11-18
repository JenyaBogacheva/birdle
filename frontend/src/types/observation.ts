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
}

export interface RecommendationResponse {
  message: string;
  top_species?: SpeciesInfo;
  clarification?: string;
}

