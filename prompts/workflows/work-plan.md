Prompt 4. Work Plan — @tasklist.md

Create an iterative, step-by-step development plan in: docs/tasklist.md

Context:

This is for the bird-identification MVP: a web app + MCP server connected to eBirdBase, where the user describes a bird in text and gets the most likely species and related info.

Requirements for the plan:

1. Iterative structure

- Each iteration should add a small but meaningful piece of functionality to the bird-ID assistant.
- After each iteration, the system should be testable end-to-end (even minimally).

2. Progress report at the top

- At the top of docs/tasklist.md, reserve a section for a progress report.
- Represent it as a clean Markdown table with:
  - Iteration number
  - Goal / feature
  - Status
  - Icon / emoji
  - Notes (optional)
- This table must be update-friendly, since it will change after every iteration.

3. Task list with checkboxes

- Below the progress report, create the actual task list.
- Each task should use a checkbox (`- [ ]`) for clear progress tracking.
- Tasks must be grouped by iterations (Iteration 1, Iteration 2, etc.).

4. Style and principles

- The plan must be concise and follow KISS.
- No unnecessary explanations — only what is essential to push the MVP forward.
- Each iteration should be testable.

After generating docs/tasklist.md:

- Save this prompt (Prompt 4) into the project's prompt session / prompt folder so it becomes part of the reusable workflow.

