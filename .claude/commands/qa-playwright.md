# Skill: QA Agent via Playwright (Stage 6)

## What this skill does
Opens the live deployed URL in a real browser via Playwright, tests every acceptance criterion from `requirements.md`, takes a screenshot of each key state, captures console errors, and produces a structured `bug-report.md`.

## Inputs required
- `issue_key` — e.g. `AI-42`
- `deployment_url` — the live https:// URL from Stage 5
- `output/{issue_key}/acceptance-criteria.txt` — one AC per line

## Outputs
- `output/{issue_key}/bug-report.md` — structured QA report
- `output/{issue_key}/screenshots/` — PNG screenshots of key states
- `qa_status` — `PASS`, `PARTIAL`, or `FAIL`

---

## Step-by-step instructions

### Step 1 — Setup Playwright
```bash
npm install --save-dev @playwright/test
npx playwright install chromium
```

### Step 2 — Launch browser and open the URL
```javascript
const { chromium } = require('@playwright/test');
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext();
const page = await context.newPage();

// Capture all console errors
const consoleErrors = [];
page.on('console', msg => {
  if (msg.type() === 'error') consoleErrors.push(msg.text());
});
page.on('pageerror', err => consoleErrors.push(err.message));

await page.goto(deployment_url, { waitUntil: 'networkidle' });
```

### Step 3 — Screenshot initial load state
```javascript
await page.screenshot({
  path: `output/{issue_key}/screenshots/screenshot-01-initial-load.png`,
  fullPage: true
});
```

### Step 4 — Test each acceptance criterion
Read `acceptance-criteria.txt` line by line. For each criterion:

1. Determine what user action to simulate based on the criterion text
2. Simulate the action using Playwright (`click`, `fill`, `press`, etc.)
3. Assert the expected outcome using `expect()`
4. Take a screenshot after each significant interaction
5. Record PASS or FAIL with notes

**Testing patterns to use:**
```javascript
// Finding elements
await page.getByRole('button', { name: /add/i }).click()
await page.getByRole('textbox').fill('Buy milk')
await page.getByText('Buy milk').waitFor()

// Assertions
await expect(page.getByText('Buy milk')).toBeVisible()
await expect(page.getByText('1 item remaining')).toBeVisible()

// localStorage check
const stored = await page.evaluate(() => localStorage.getItem('todos'))
expect(JSON.parse(stored)).toHaveLength(1)
```

**Screenshot after each AC test:**
```javascript
const screenshotNum = String(acIndex + 2).padStart(2, '0')
const screenshotName = `screenshot-${screenshotNum}-${slugify(criterion)}.png`
await page.screenshot({ path: `output/{issue_key}/screenshots/${screenshotName}`, fullPage: true })
```

### Step 5 — Test persistence (if in requirements)
For any AC involving persistence:
```javascript
// Simulate page refresh
await page.reload({ waitUntil: 'networkidle' })
await page.screenshot({ path: '...screenshot-XX-after-refresh.png', fullPage: true })
// Re-assert the persistent state
```

### Step 6 — Test mobile viewport (if in requirements)
```javascript
await page.setViewportSize({ width: 375, height: 667 })
await page.screenshot({ path: '...screenshot-XX-mobile.png', fullPage: true })
```

### Step 7 — Determine overall status
- `PASS` — all acceptance criteria passed
- `PARTIAL` — some passed, some failed
- `FAIL` — more than half failed, or any critical AC failed

### Step 8 — Generate bug-report.md
Write to `output/{issue_key}/bug-report.md`:

```markdown
# QA Report — {issue_key}
**Deployment URL:** {deployment_url}
**Tested at:** {ISO timestamp UTC}
**Overall status:** {PASS / PARTIAL / FAIL}

## Test Results
| Acceptance Criterion | Result | Notes |
|----------------------|--------|-------|
| {AC 1 text} | ✅ PASS / ❌ FAIL | {notes if fail} |
| {AC 2 text} | ✅ PASS / ❌ FAIL | {notes} |

## Console Errors
{None — OR list each error}

## Screenshots
{list each screenshot filename}

## Summary
{2-3 sentences in plain English: what works, what doesn't, severity assessment}
```

### Step 9 — Close browser
```javascript
await browser.close()
```

---

## Error handling
- If `page.goto` throws: retry once, then mark ALL criteria as FAIL and generate report with "Could not load page"
- If a specific AC test throws unexpectedly: mark that AC as FAIL with the error message, continue testing remaining ACs
- Always close the browser in a `finally` block
- Always produce `bug-report.md` regardless of errors — a QA report with all FAILs is better than no report

## Principle alignment
- **Principle 2 (Feedback Loop):** The QA agent is the final verification loop — it confirms the deployed site matches the requirements, not just that the code compiled
- **Principle 3 (Tools):** Playwright is literally the agent's hands in a real browser
- **Principle 6 (Parallelism opportunity):** Multiple ACs can be tested in parallel browser contexts if the test suite grows large
