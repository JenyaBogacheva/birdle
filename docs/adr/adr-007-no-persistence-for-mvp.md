# ADR-007: Avoid Persistent Storage in the MVP

- **Status**: Accepted
- **Context**: The initial release focuses on validating the LLM-driven identification flow. The system handles short-lived conversations and trait lookups, with no requirement to retain user data or analytical history at this stage.
- **Decision**: Store all request data, trait extractions, and species candidates in memory within the backend scope. Do not provision databases or external storage services for the MVP.
- **Consequences**: Implementation stays simple and deployment lighter—no schema design, migrations, or managed databases. We forgo historical analytics and personalization until needed; introducing persistence later will require new ADRs and migration planning.

