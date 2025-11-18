## LLM-Powered Bird Identification Assistant

- **Goal**: Deliver a web-based assistant that identifies bird species from plain-text user descriptions.
- **Interface**: Responsive web app that guides users through describing a bird and surfaces results clearly alongside images and range maps.
- **Core Intelligence**: An LLM orchestrates user interaction, captures relevant traits, and matches them against species candidates.
- **Data Backbone**: An MCP server bridges the assistant with the eBird database, enabling real-time species lookup, trait filtering, and retrieval of supplementary details (status, range, photos, calls).
- **Primary Task Flow**:
  1. User enters a free-form description of a sighted bird.
  2. The LLM extracts salient attributes (size, coloration, location, behavior, time of year).
  3. The assistant queries the MCP-eBird integration to score likely species and fetch supporting data.
  4. The assistant returns the top species match with confidence notes, key differentiators, and quick facts.
- **Enhancements to Explore**:
  - Allow optional photo/audio uploads to enrich the LLM’s prompts.
  - Offer clarifying questions when descriptions are ambiguous.
  - Surface regional rarity alerts and conservation statuses.
  - Log anonymized sightings to personalize future suggestions.
- **Next Steps**: Define MCP schema, build the eBird connector, stand up the web frontend, and design prompt strategies for robust species ranking.
