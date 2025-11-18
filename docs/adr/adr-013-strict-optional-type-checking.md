# ADR-013: Strict Optional Type Checking with MyPy

**Status:** Accepted

**Date:** 2025-11-18

## Context

During CI, we discovered a mypy error: accessing `.common_name` on an Optional field without checking for None. Pre-commit didn't catch it because local config had `--no-strict-optional` while CI didn't.

## Alternatives

1. **Disable strict optional** - Allow accessing Optional fields without checks (`--no-strict-optional`)
2. **Enable strict optional** - Require explicit None checks before accessing Optional fields
3. **Use assertions** - Assert non-None before access
4. **Avoid Optional** - Make all fields required (not always possible)

## Decision

Enable strict Optional type checking in both pre-commit and CI (remove `--no-strict-optional` flag). Require explicit None checks before accessing Optional fields.

```python
# Before (unsafe)
logger.info(f"species={response.top_species.common_name}")

# After (safe)
if response.top_species:
    logger.info(f"species={response.top_species.common_name}")
```

## Reasoning

- **Type safety**: Prevents NoneType AttributeError at runtime
- **Explicit handling**: Forces developer to think about None case
- **Consistency**: Pre-commit and CI must have identical checks
- **Best practice**: Strict optional is Python typing best practice
- **Caught real bug**: CI found an actual issue we missed locally
- **Better code quality**: Defensive programming encouraged

## Consequences

### Positive
- Runtime safety (no accessing None values)
- Explicit error handling for missing data
- Pre-commit and CI configs now aligned
- Catches type errors locally before push
- Forces thinking about edge cases

### Negative
- More verbose code (requires if checks)
- Can feel tedious for "known" non-None cases
- Slightly longer development time

### Lesson learned
- **Always align local and CI configs** - Discrepancies hide bugs
- **Test builds locally** - What works in dev may fail in production build
- **Strict is better than permissive** - Catches bugs early

### Implementation
- Updated `.pre-commit-config.yaml` to remove `--no-strict-optional`
- Added None check in `identify.py` before accessing `top_species.common_name`
- Both pre-commit and CI now enforce same mypy rules
