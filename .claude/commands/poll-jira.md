# Skill: Poll Jira for New Stories (Stage 1)

## What this skill does
Connects to the Jira REST API, finds stories labelled `ai-ready` in status `To Do`, downloads their `requirements.md` attachment, and immediately transitions each story to `In Progress` so the cron job won't pick it up again on the next tick.

## Inputs required
- `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY` from environment

## Outputs
- For each found story: the Jira issue key (e.g. `AI-42`) and the raw text content of `requirements.md`
- Story is transitioned to `In Progress` before returning

---

## Step-by-step instructions

### Step 1 — Authenticate
Use HTTP Basic auth: email + API token, Base64 encoded.
```
Authorization: Basic base64(email:api_token)
Content-Type: application/json
```

### Step 2 — Search for stories
```
GET {JIRA_BASE_URL}/rest/api/3/search
  ?jql=project={JIRA_PROJECT_KEY} AND labels=ai-ready AND status="To Do"
  &fields=summary,attachment,status,labels
```
Parse the `issues` array. If empty, return immediately — nothing to do.

### Step 3 — For each matching issue
1. Extract `issue.key` (e.g. `AI-42`) and `issue.fields.summary`
2. Look in `issue.fields.attachment` for a file named exactly `requirements.md`
3. If no attachment named `requirements.md` is found: add a Jira comment saying "No requirements.md found — skipping", transition story to `Bug Reported`, and continue to next story
4. Download the attachment:
   ```
   GET {JIRA_BASE_URL}/rest/api/3/attachment/content/{attachmentId}
   ```
   Decode response as UTF-8 text

### Step 4 — Transition story to In Progress
First, fetch available transitions:
```
GET {JIRA_BASE_URL}/rest/api/3/issue/{issueKey}/transitions
```
Find the transition whose name matches "In Progress" (case-insensitive).
Then POST:
```
POST {JIRA_BASE_URL}/rest/api/3/issue/{issueKey}/transitions
Body: {"transition": {"id": "<transitionId>"}}
```
Do this BEFORE passing requirements content to the next stage. This prevents duplicate processing if the cron fires again before Stage 2 completes.

### Step 5 — Add a comment to the story
```
POST {JIRA_BASE_URL}/rest/api/3/issue/{issueKey}/comment
Body: {
  "body": {
    "type": "doc", "version": 1,
    "content": [{"type": "paragraph", "content": [
      {"type": "text", "text": "🤖 Pipeline triggered. Building app from requirements.md..."}
    ]}]
  }
}
```

### Step 6 — Return results
Return a list of dicts:
```python
[{"issue_key": "AI-42", "summary": "...", "requirements": "<raw text of requirements.md>"}]
```

---

## Error handling
- If the Jira API returns non-2xx: log the status code and body, raise `PipelineError("Jira API error: {status} {body}")`
- If an attachment download fails: log, comment on the story, transition to `Bug Reported`, skip this story
- Never let one story's failure block other stories in the same poll

## Principle alignment
- **Principle 3 (Tools):** This skill is the "hands" that connect the pipeline to Jira
- **Principle 4 (Workflows):** Transitioning to In Progress immediately is the critical idempotency guard that makes the workflow reliable
