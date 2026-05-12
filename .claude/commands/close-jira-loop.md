# Skill: Close the Jira Loop (Stage 8)

## What this skill does
Transitions the Jira story to its terminal state — `Done` if all QA tests passed, `Bug Reported` (or equivalent) if any failed — and posts a detailed comment. The story must NEVER be left in `In Progress`.

## Inputs required
- `issue_key` — e.g. `AI-42`
- `qa_status` — `PASS`, `PARTIAL`, or `FAIL`
- `deployment_url` — the live Vercel URL
- `pr_url` — the GitHub PR URL
- `output/{issue_key}/bug-report.md` — the QA report content
- `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` from environment

## Outputs
- Jira story in terminal state (`Done` or `Bug Reported`)
- Jira comment with deployment URL, PR link, and QA summary

---

## Step-by-step instructions

### Step 1 — Determine target transition
```python
if qa_status == "PASS":
    target_status = "Done"
    emoji = "✅"
else:  # PARTIAL or FAIL
    target_status = "Bug Reported"  # or "In Review" — depends on Jira config
    emoji = "❌"
```

### Step 2 — Fetch available transitions
```
GET {JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/transitions
Authorization: Basic {base64(email:token)}
```
Parse the `transitions` array. Find the transition whose `name` matches the target status (case-insensitive). If exact match not found, look for the closest semantic match:
- `Done` → also try: `Closed`, `Complete`, `Resolved`
- `Bug Reported` → also try: `In Review`, `Needs Review`, `Reopened`

If no matching transition found: log a warning, try to transition to `Done` as fallback (never leave In Progress).

### Step 3 — Execute the transition
```
POST {JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/transitions
Content-Type: application/json

{
  "transition": {"id": "{transitionId}"}
}
```

### Step 4 — Post a comment
Read `output/{issue_key}/bug-report.md` and compose the comment.

**For PASS:**
```python
comment_text = f"""🤖 Pipeline Complete — {emoji} All tests passed

**Deployment URL:** {deployment_url}
**GitHub PR:** {pr_url}
**QA Status:** PASS — all acceptance criteria verified by Playwright

The story has been transitioned to Done. A full QA report has been emailed to the team.

---
_Automated by the Zero Human Touch Pipeline_"""
```

**For PARTIAL/FAIL:**
```python
with open(f"output/{issue_key}/bug-report.md") as f:
    bug_report = f.read()

comment_text = f"""🤖 Pipeline Complete — {emoji} QA issues found

**Deployment URL:** {deployment_url}
**GitHub PR:** {pr_url}
**QA Status:** {qa_status} — see bug report below

---

{bug_report}

---
_Automated by the Zero Human Touch Pipeline_"""
```

### Step 5 — Submit the comment
```
POST {JIRA_BASE_URL}/rest/api/3/issue/{issue_key}/comment
Content-Type: application/json

{
  "body": {
    "type": "doc",
    "version": 1,
    "content": [
      {
        "type": "paragraph",
        "content": [{"type": "text", "text": "{comment_text}"}]
      }
    ]
  }
}
```

For rich formatting (tables from bug report), use Jira's Atlassian Document Format (ADF) or post the markdown as a code block.

### Step 6 — Verify final state
```
GET {JIRA_BASE_URL}/rest/api/3/issue/{issue_key}?fields=status
```
Confirm `issue.fields.status.name` is no longer `In Progress`. Log the final state.

```
[AI-42] Final Jira status: Done ✅
[AI-42] Pipeline complete for story AI-42
[AI-42] Total pipeline duration: 4m 32s
```

---

## Error handling
- If transition POST fails: retry once, then log the error and attempt a fallback transition to `Done`
- If comment POST fails: log the error — the story MUST still be transitioned even if the comment fails
- If the final status check shows still `In Progress`: retry the transition once more with a different matching transition ID
- **Invariant:** This stage MUST exit with the story in a non-In-Progress state. This is non-negotiable.

## The fallback rule
If ALL transition attempts fail:
1. Log a critical error
2. Send an emergency email to `QA_REPORT_EMAIL` with subject `PIPELINE STUCK — {issue_key} — manual intervention required`
3. Include the issue key, last error message, and deployment URL
4. Never silently abandon a stuck story

## Principle alignment
- **Principle 2 (Feedback Loop):** Step 6 verifies the transition actually happened — agent confirms its own action
- **Principle 4 (Workflows):** The invariant (never leave In Progress) is the defining constraint of this workflow's reliability
