# ADR-009: Pre-commit Hooks for Code Quality

**Status:** Accepted

**Date:** 2025-11-18

## Context

We need to ensure code quality and consistency across the team. CI catches issues, but only after pushing code. We want to catch formatting, linting, and type errors before commits reach the repository.

## Alternatives

1. **Manual code review only** - Rely on developers and PR reviews to catch issues
2. **CI-only checks** - Run all checks only in GitHub Actions
3. **Pre-commit hooks** - Automatic local checks before git commit
4. **Git hooks + CI** - Both local pre-commit and CI checks

## Decision

Use pre-commit hooks with the following checks:
- **Python**: ruff (linting + formatting), mypy (type checking)
- **TypeScript**: ESLint
- **General**: trailing whitespace, EOF fixes, YAML validation, merge conflict detection

Configure identical checks in both pre-commit and GitHub Actions CI.

## Reasoning

- **Fast feedback**: Catch issues in seconds, not minutes (CI wait time)
- **Prevents bad commits**: Issues never reach the repository
- **Consistent style**: Auto-formatting ensures uniform code style
- **Developer experience**: Fixes apply automatically where possible
- **CI alignment**: Local and CI checks must match to avoid surprises
- **Convention enforcement**: Makes "never skip pre-commit" rule enforceable

## Consequences

### Positive
- Issues caught immediately during development
- Reduced CI failures (faster iteration)
- Auto-formatting eliminates style debates
- Type errors caught before push
- Forces addressing issues upfront

### Negative
- Slower commit process (adds 2-5 seconds per commit)
- Initial setup required for new developers
- Must maintain two configs (pre-commit + CI) in sync
- Can't commit broken code for WIP (though can use `--no-verify` in emergencies)

### Neutral
- Requires `poetry install` and `pre-commit install` during setup
- Team must learn to trust auto-formatting
