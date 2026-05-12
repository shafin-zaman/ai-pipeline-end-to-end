# Skill: Write & Run Tests — Feedback Loop (Stage 3)

## What this skill does
Writes meaningful unit tests for the built web app, runs them programmatically, reads any failures, fixes the source code, and re-runs — iterating until all tests pass. This is a fully autonomous loop with no human involvement. Saves final results to `test-results.txt`.

## Inputs required
- `issue_key` — e.g. `AI-42`
- `output/{issue_key}/` — the built web app directory from Stage 2

## Outputs
- `output/{issue_key}/test-results.txt` — final test run output (all passing)
- Source code in `output/{issue_key}/` may be modified by fix iterations

---

## Step-by-step instructions

### Step 1 — Choose the test framework
Based on the app's tech stack:
- Plain HTML/CSS/JS → use **Jest** with `jsdom` environment + `@testing-library/dom`
- React → use **Vitest** + `@testing-library/react`
- Other frameworks → use the most natural fit

Initialize the test setup if not already present:
```bash
cd output/{issue_key}
npm init -y
npm install --save-dev jest jest-environment-jsdom @testing-library/dom @testing-library/jest-dom
```
Add to `package.json`:
```json
"scripts": {"test": "jest --testEnvironment jsdom"},
"jest": {"testEnvironment": "jsdom", "setupFilesAfterFramework": ["@testing-library/jest-dom"]}
```

### Step 2 — Write meaningful unit tests
Do NOT write trivial tests (e.g. `expect(1+1).toBe(2)`).

Write one test per acceptance criterion from `output/{issue_key}/acceptance-criteria.txt`.

For each acceptance criterion, write a test that:
1. Sets up the DOM (load the HTML)
2. Simulates the user action described
3. Asserts the expected outcome

**Example test structure for a todo app:**
```javascript
// AC: "Add a new todo item via a text input and a button"
test('adds a todo item when button is clicked', () => {
  document.body.innerHTML = fs.readFileSync('index.html', 'utf8');
  const input = screen.getByRole('textbox');
  const button = screen.getByRole('button', { name: /add/i });
  fireEvent.change(input, { target: { value: 'Buy milk' } });
  fireEvent.click(button);
  expect(screen.getByText('Buy milk')).toBeInTheDocument();
});
```

Write tests in `output/{issue_key}/tests/app.test.js`.

### Step 3 — Run the tests
```bash
cd output/{issue_key} && npm test -- --json --outputFile=test-run-raw.json 2>&1
```
Capture both stdout and the JSON output file.

### Step 4 — Evaluate results

**If all tests pass:**
- Write the output to `test-results.txt`
- Proceed to Stage 4
- Done

**If tests fail:**
- Parse `test-run-raw.json` to identify which tests failed and why
- For each failure:
  1. Read the failure message and stack trace
  2. Identify whether the bug is in the test or in the app code
  3. If the test itself is wrong (incorrect selector, wrong assumption): fix the test
  4. If the app code is wrong: fix `index.html` (or relevant source files)
- Re-run from Step 3
- **Maximum 5 iterations.** If still failing after 5 attempts: write the failure output to `test-results.txt`, add a `TEST_FAILURE` marker on line 1, and proceed — the pipeline continues with a FAIL status

### Step 5 — Save final results
```bash
echo "TEST RUN COMPLETE — $(date -u +"%Y-%m-%dT%H:%M:%SZ")" > output/{issue_key}/test-results.txt
echo "Status: ALL PASSING" >> output/{issue_key}/test-results.txt
npm test >> output/{issue_key}/test-results.txt 2>&1
```

---

## What makes a meaningful test
- Tests real user interactions, not implementation details
- Covers the happy path AND at least one edge case per feature
- Each test is independent — does not depend on state from a previous test
- Tests the rendered DOM output, not internal JavaScript variables

## Error handling
- If npm install fails: log the error, try once more, then raise `PipelineError`
- If the test file has a syntax error: agent fixes the syntax and re-runs
- Never skip to Stage 4 without producing `test-results.txt`

## Principle alignment
- **Principle 2 (Feedback Loop):** This is the canonical feedback loop — agent writes, runs, reads failures, fixes, repeats
- **Principle 4 (Workflows):** The loop terminates predictably (all pass or max 5 iterations)
