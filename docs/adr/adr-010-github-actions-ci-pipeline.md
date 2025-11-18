# ADR-010: GitHub Actions CI Pipeline

**Status:** Accepted

**Date:** 2025-11-18

## Context

We need automated testing and quality checks on all pull requests to prevent broken code from reaching main. The CI must validate both backend (Python) and frontend (TypeScript) code.

## Alternatives

1. **No CI** - Rely on local testing and manual review
2. **GitHub Actions** - Native GitHub CI/CD
3. **CircleCI / Jenkins** - External CI services
4. **GitLab CI** - Requires migrating to GitLab

## Decision

Use GitHub Actions with two parallel jobs:
- **Backend job**: Python setup, Poetry, ruff, black, mypy, pytest
- **Frontend job**: Node.js setup, npm install, TypeScript build, ESLint

Run on all pushes to `main` and all pull requests to `main`.

## Reasoning

- **Native integration**: Built into GitHub, no external service needed
- **Free for public repos**: No additional cost
- **Parallel jobs**: Backend and frontend run simultaneously (faster)
- **Caching**: Poetry and npm dependencies cached between runs
- **Standard tooling**: Familiar to most developers
- **Configuration as code**: `.github/workflows/ci.yml` versioned in repo
- **Matches pre-commit**: Same checks locally and in CI

## Consequences

### Positive
- Automated quality gate on all PRs
- Catches issues missed locally (if pre-commit skipped)
- Public visibility of build status
- Prevents merging broken code
- Acts as documentation of quality standards

### Negative
- CI runs take 1-2 minutes per push
- Must maintain CI config in addition to pre-commit
- Can slow down development if overly strict
- GitHub Actions minutes count toward quota (not an issue for public repos)

### Neutral
- Requires matching CI checks with pre-commit hooks
- Team must wait for CI before merging
- Failed CI blocks merging (this is desired)
