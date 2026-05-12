# Skill: Build Web App from Requirements (Stage 2)

## What this skill does
Reads `requirements.md` in full, plans the implementation, and produces a complete, deployable web app in `output/{JIRA-KEY}/`. The agent must not ask for clarification — it makes reasonable decisions and builds.

## Inputs required
- `issue_key` — e.g. `AI-42`
- `requirements` — raw text content of `requirements.md`

## Outputs
- A working web app in `output/{issue_key}/` ready for Vercel static deployment
- At minimum: `index.html` (and any supporting files the requirements call for)

---

## Step-by-step instructions

### Step 1 — Read requirements completely before writing a single line of code
Parse the requirements.md for:
- **What to build** — the core concept
- **Features** — the exact list of capabilities required
- **Tech stack** — framework, constraints (plain HTML/CSS/JS, React, etc.)
- **Acceptance criteria** — the exact list that Stage 6 (QA) will test against
- **Output format** — single file vs. multi-file, framework project vs. static

Store these parsed sections. You will reference the acceptance criteria list explicitly in Stage 6.

### Step 2 — Plan the implementation
Before writing code, produce a written plan covering:
1. File structure (what files will be created)
2. Implementation approach for each feature
3. Edge cases to handle (e.g. empty state, invalid input, persistence)
4. How each acceptance criterion will be satisfied

### Step 3 — Create the output directory
```bash
mkdir -p output/{issue_key}
mkdir -p output/{issue_key}/screenshots
```

### Step 4 — Build the app
Follow the tech stack specified in requirements. Default behaviour when underspecified:
- Use plain HTML/CSS/JS — single `index.html` file
- No build step required — must run in Chrome as-is
- Use `localStorage` for any persistence
- CSS: modern, clean, mobile-responsive (375px minimum width)
- JS: vanilla, no external CDN dependencies unless explicitly allowed

Write the complete implementation. Do not produce placeholder code or TODOs.

### Step 5 — Self-review against acceptance criteria
After writing the code, go through each acceptance criterion one by one:
- Read the criterion
- Trace through your code and confirm the criterion is satisfied
- If any criterion is not satisfied, fix the code before moving on

This is the first feedback loop. Do not proceed to Stage 3 until all acceptance criteria are satisfied by code inspection.

### Step 6 — Verify the output is Vercel-deployable
Static site requirements:
- `index.html` must exist at the root of `output/{issue_key}/`
- No server-side code unless the requirements explicitly call for it
- All assets must be relative paths or inline

For framework projects (if required by the tech spec):
- Include a valid `package.json` with a `build` script
- Include `vercel.json` if non-standard configuration is needed

### Step 7 — Save the parsed acceptance criteria
Write the acceptance criteria list to `output/{issue_key}/acceptance-criteria.txt`:
```
One acceptance criterion per line, exactly as stated in requirements.md
```
Stage 6 (QA) will load this file to know what to test.

---

## Error handling
- If the tech stack is ambiguous: default to plain HTML/CSS/JS, document the decision in a comment at the top of index.html
- If a feature is technically impossible in the specified stack: note it in a `NOTES.md` alongside the output, implement the closest achievable alternative
- Never produce an empty or broken output directory

## Principle alignment
- **Principle 1 (Understand):** Agent reads requirements completely before acting
- **Principle 2 (Feedback Loop):** Step 5 is an explicit self-review loop before handing off
- **Principle 5 (Context Quality):** Requirements parsed and structured before code is written
