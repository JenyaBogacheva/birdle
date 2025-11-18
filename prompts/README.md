# Project Setup Prompts

This directory contains the meta-prompts used to bootstrap this project's structure and documentation.

## Purpose

These prompts represent a **systematic approach to project initialization** - instead of ad-hoc documentation, I used structured prompts to generate consistent, well-organized project artifacts.

## Workflow Prompts

Located in `workflows/`:

1. **`idea-capture.md`** - Structured brainstorming template
2. **`vision-generation.md`** - Technical blueprint creation (→ `docs/vision.md`)
3. **`development-conventions.md`** - Code standards definition (→ `docs/conventions.md`)
4. **`work-plan.md`** - Iteration planning template (→ `docs/tasklist.md`)
5. **`workflow.md`** - Development process rules (→ `docs/workflow.md`)

## Why Keep This?

This demonstrates:
- ✅ **Process thinking** - Systematic approach to project setup
- ✅ **Repeatability** - Can apply same structure to other projects
- ✅ **Documentation-first** - Plan before code
- ✅ **AI-augmented development** - Leverage LLMs for scaffolding, not just coding

## From Prompts to Product

```
prompts/workflows/     →  docs/           →  working code
├─ idea-capture        →  idea.md
├─ vision-generation   →  vision.md       →  architecture implemented
├─ conventions         →  conventions.md  →  code standards enforced
├─ work-plan           →  tasklist.md     →  4 iterations completed
└─ workflow            →  workflow.md     →  dev process followed
```

## Note

These are **meta-artifacts** - the actual project lives in `frontend/`, `services/`, and `docs/`. These prompts just show *how* the structure was created.
