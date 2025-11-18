# ADR-003: Integrate OpenAI ChatGPT API with Structured Responses and Guardrails

- **Status**: Accepted
- **Context**: The assistant must converse in a friendly Gen-Z tone, extract bird traits, and guard against harmful prompts. We need reliable LLM behavior, predictable costs, and a way to supervise model output without building custom models during the MVP phase.
- **Decision**: Use the OpenAI ChatGPT API (GPT-4o/GPT-4.1) with a single system prompt defining tone and safety rules. Send trimmed conversation context plus structured trait data, require responses in a JSON envelope `{ message, clarification?, species_rankings? }`, and enforce moderation before and after each call. Operate at low temperature (~0.4), limit tokens, retry once on transient errors, and log usage cost per request.
- **Consequences**: We get high-quality language understanding with minimal setup and maintain control via schema validation and moderation. Costs remain transparent, and adding clarifying questions is straightforward. We depend on OpenAI’s availability/pricing and must maintain the validation layer to handle schema or moderation failures.

