# Skill: Deploy to Vercel & Verify Live URL (Stage 5)

## What this skill does
Triggers a Vercel deployment from the pushed GitHub branch, polls until the deployment status is `READY`, extracts the live URL, and performs a health check to confirm the URL returns HTTP 200. Does not proceed until the URL is confirmed live.

## Inputs required
- `issue_key` — e.g. `AI-42`
- `branch` — the pushed branch name, e.g. `feature/AI-42-todo-app`
- `VERCEL_TOKEN`, `VERCEL_PROJECT_ID`, `VERCEL_TEAM_ID` (optional) from environment

## Outputs
- `deployment_url` — the live https:// URL of the deployed site
- `deployment_id` — the Vercel deployment ID (for logs if needed)

---

## Step-by-step instructions

### Step 1 — Trigger deployment
```
POST https://api.vercel.com/v13/deployments
Authorization: Bearer {VERCEL_TOKEN}
Content-Type: application/json

{
  "name": "{VERCEL_PROJECT_ID}",
  "gitSource": {
    "type": "github",
    "repoId": "{GITHUB_REPO_ID}",
    "ref": "feature/{issue_key}-{slug}"
  },
  "projectId": "{VERCEL_PROJECT_ID}",
  "teamId": "{VERCEL_TEAM_ID}"   // omit if no team
}
```

Extract from response: `deployment.id` and `deployment.url` (may still be building).

### Step 2 — Poll deployment status
```
GET https://api.vercel.com/v13/deployments/{deploymentId}
Authorization: Bearer {VERCEL_TOKEN}
```

Poll every 10 seconds. Track `deployment.readyState`:
- `INITIALIZING` / `BUILDING` / `DEPLOYING` → keep polling
- `READY` → proceed to Step 3
- `ERROR` / `CANCELED` → raise `PipelineError("Vercel deployment failed: {readyState}")`

**Timeout:** Stop polling after 10 minutes. If not READY, raise `PipelineError("Vercel deployment timed out after 10 min")`.

**Poll logic:**
```python
for attempt in range(60):  # 60 attempts × 10s = 10 min
    status = get_deployment_status(deployment_id)
    if status == "READY":
        break
    if status in ("ERROR", "CANCELED"):
        raise PipelineError(f"Deploy failed: {status}")
    time.sleep(10)
else:
    raise PipelineError("Deploy timed out")
```

### Step 3 — Extract the live URL
From the READY deployment response:
```python
deployment_url = f"https://{deployment['url']}"
```
Ensure it starts with `https://`.

### Step 4 — Health check
Confirm the URL is actually serving content:
```python
import requests
response = requests.get(deployment_url, timeout=30)
if response.status_code != 200:
    raise PipelineError(f"Health check failed: {response.status_code} at {deployment_url}")
```

Also verify `Content-Type: text/html` is present in response headers.

### Step 5 — Return results
```python
{"deployment_url": "https://...", "deployment_id": "dpl_xxx"}
```

---

## Vercel API reference
```
POST https://api.vercel.com/v13/deployments          # Trigger
GET  https://api.vercel.com/v13/deployments/{id}     # Poll status
```

Alternatively, if the GitHub repo is already connected to the Vercel project, pushing the branch in Stage 4 may automatically trigger a deployment. In that case:
1. Wait 15 seconds after the push
2. Query `GET /v6/deployments?projectId={id}&meta-githubCommitRef={branch}` to find the auto-triggered deployment
3. Then follow the same poll loop

### Step 6 — Log deployment info
```
[AI-42] Vercel deployment triggered: dpl_xxx
[AI-42] Polling deployment status...
[AI-42] Status: BUILDING (attempt 3/60)
[AI-42] Status: READY after 47s
[AI-42] Live URL: https://ai-42-todo-abc123.vercel.app
[AI-42] Health check: 200 OK
```

---

## Error handling
- Deploy ERROR state: read the error message from response, log it, raise `PipelineError`
- Health check non-200: log status code + response body, raise `PipelineError`
- Network timeout on health check: retry once after 30 seconds, then raise

## Principle alignment
- **Principle 2 (Feedback Loop):** Poll loop with explicit success/failure states — pipeline does not proceed on assumption
- **Principle 3 (Tools):** Vercel API is the agent's deployment hand
