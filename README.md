# Zero Human Touch Pipeline

A fully automated, end-to-end software delivery pipeline. A product manager drops a Jira story with a `requirements.md` attachment — from that moment, no human touches anything. The pipeline builds the web app, tests it, deploys it to Vercel, QA-tests the live URL via Playwright, emails a bug report, and closes the Jira story automatically.

**Typical runtime: 6–7 minutes per story, zero human intervention.**

---

## Architecture

```
Jira Story (To Do)
       │
       ▼
Stage 1 ── Poll Jira every 5 min (label: ai-ready, status: To Do)
       │    Transitions story → In Progress
       ▼
Stage 2 ── Claude Code builds the web app
       │    Reads requirements.md → produces output/JIRA-KEY/index.html
       ▼
Stage 3 ── Jest unit test feedback loop
       │    Write tests → run → fix → re-run (max 5 attempts)
       │    Saves test-results.txt
       ▼
Stage 4 ── Push to GitHub
       │    Branch: feature/JIRA-KEY-description
       │    Opens PR with Jira key in title
       ▼
Stage 5 ── Vercel deployment
       │    Polls until READY, health-checks live URL
       ▼
Stage 6 ── Playwright QA
       │    Tests every acceptance criterion
       │    Takes screenshots, captures console errors
       │    Produces bug-report.md
       ▼
Stage 7 ── Email bug report
       │    Subject: QA Report — JIRA-KEY — PASS/FAIL
       │    Attaches screenshots
       ▼
Stage 8 ── Close Jira loop
           PASS → Done + deployment URL comment
           FAIL → Bug Reported + full bug report comment
```

---

## Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+, managed with `uv` |
| Jira API | REST API v3 (search/jql, transitions, attachments, comments) |
| Build agent | Claude Code CLI (`claude -p`) as subprocess |
| Unit tests | Jest + jsdom + @testing-library/dom |
| GitHub | `gh` CLI + GitHub REST API fallback |
| Deployment | Vercel REST API (auto-deploy from feature branch) |
| QA | Playwright Python (sync API, Chromium headless) |
| Email | Resend API with base64 screenshot attachments |
| Orchestration | `orchestrator.py` with `ThreadPoolExecutor` (parallel stories) |

---

## Repository Layout

```
├── orchestrator.py          # Master script — calls all 8 stages
├── config.py                # Loads env vars, raises on missing
├── exceptions.py            # PipelineError with stage attribute
├── pyproject.toml           # uv project config + dependencies
├── CLAUDE.md                # Claude Code context file
├── .env                     # Secrets (git-ignored)
├── stages/
│   ├── jira_poller.py       # Stage 1: Jira REST API polling
│   ├── build_agent.py       # Stage 2: spawns Claude Code subprocess
│   ├── test_runner.py       # Stage 3: Jest feedback loop
│   ├── github_pusher.py     # Stage 4: shared repo + PR
│   ├── vercel_deployer.py   # Stage 5: Vercel REST API
│   ├── qa_agent.py          # Stage 6: Playwright test runner
│   ├── email_reporter.py    # Stage 7: Resend email sender
│   └── jira_closer.py       # Stage 8: Jira transitions + comments
├── .claude/commands/        # Slash-command skill files for each stage
├── output/                  # Per-story working dirs (git-ignored)
└── logs/                    # Pipeline logs (git-ignored)
```

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.11+ | `brew install python` |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js | 18+ | `brew install node` |
| Claude Code CLI | latest | [claude.ai/code](https://claude.ai/code) — requires org account |
| GitHub CLI | latest | `brew install gh` |

---

## Setup

### 1. Clone this repository

```bash
git clone https://github.com/muzammal1/ai-pipeline-end-to-end.git --branch pipeline-source pipeline
cd pipeline
```

### 2. Create the `.env` file

```bash
cat > .env << 'EOF'
# Jira
JIRA_BASE_URL=https://yourorg.atlassian.net
JIRA_EMAIL=you@example.com
JIRA_API_TOKEN=your-jira-api-token
JIRA_PROJECT_KEY=SCRUM

# GitHub
GITHUB_TOKEN=github_pat_...
GITHUB_REPO=yourorg/your-repo

# Vercel
VERCEL_TOKEN=vcp_...
VERCEL_PROJECT_ID=prj_...
VERCEL_TEAM_ID=your-team-id

# Email (Resend)
RESEND_API_KEY=re_...
QA_REPORT_EMAIL=you@example.com
EOF
```

> **Where to get each credential:**
> - Jira API token: `https://id.atlassian.com/manage-profile/security/api-tokens`
> - GitHub PAT: `https://github.com/settings/tokens` — needs `repo` scope
> - Vercel token: `https://vercel.com/account/settings/tokens`
> - Vercel project/team IDs: project settings page in the Vercel dashboard
> - Resend API key: `https://resend.com/api-keys`

### 3. Install Python dependencies

```bash
uv sync
```

### 4. Install Playwright browser

```bash
uv run playwright install chromium
```

### 5. Authenticate the GitHub CLI

```bash
echo "your_github_pat" | gh auth login --with-token
```

### 6. Authenticate Claude Code (org account)

```bash
claude auth login
```

---

## Creating a Jira Story

Every story the pipeline will process must follow this format:

1. **Title:** anything descriptive (e.g., `Build a simple todo app`)
2. **Label:** `ai-ready` — this is what the cron filter matches
3. **Status:** `To Do`
4. **Attachment:** a file named exactly `requirements.md`

### Example `requirements.md`

```markdown
# Requirements — Simple Todo App

## What to build
A single-page web application that lets a user manage a todo list.

## Features
- Add a new todo item via a text input and a button
- Mark a todo as complete (strikethrough + visual indicator)
- Delete a todo item
- Show a count of remaining incomplete items
- Persist todos in localStorage so they survive a page refresh

## Tech
- Plain HTML, CSS, JavaScript — no framework required
- Single file output preferred (index.html)
- Must work in Chrome without any build step

## Acceptance criteria
- All 5 features work correctly
- No console errors on load or interaction
- Page is usable on a mobile screen (375px wide)
```

---

## Running the Pipeline

### One-shot (process all ready stories once, then exit)

```bash
uv run python orchestrator.py --once
```

Use this for manual runs and demos.

### Watch mode (polls every 5 minutes indefinitely)

```bash
uv run python orchestrator.py --schedule
```

Use this when running unattended.

### Unattended cron job

Add to your crontab (`crontab -e`) to run every hour:

```
0 * * * * cd /path/to/pipeline && /Users/yourname/.local/bin/uv run python orchestrator.py --once >> logs/cron.log 2>&1
```

Or every 5 minutes (matches the assignment spec):

```
*/5 * * * * cd /path/to/pipeline && /Users/yourname/.local/bin/uv run python orchestrator.py --once >> logs/cron.log 2>&1
```

---

## What Happens (Stage by Stage)

| Stage | What it does | Time |
|-------|-------------|------|
| 1 — Poll Jira | Finds stories labelled `ai-ready` in `To Do`, transitions to `In Progress` | ~5s |
| 2 — Build | Claude Code reads `requirements.md` and writes the web app to `output/JIRA-KEY/` | ~60s |
| 3 — Unit tests | Jest tests are written, run, and fixed in a loop until all pass | ~60–120s |
| 4 — GitHub | Feature branch created, files committed, PR opened | ~15s |
| 5 — Vercel | Branch auto-deploys; pipeline polls until `READY` and health-checks the URL | ~3min |
| 6 — Playwright QA | Every acceptance criterion tested against the live site; screenshots taken | ~30s |
| 7 — Email | Bug report + screenshots sent to `QA_REPORT_EMAIL` | ~5s |
| 8 — Close Jira | Story transitions to `Done` (pass) or `Bug Reported` (fail); comment added | ~5s |

---

## Output Artifacts

Each processed story creates a directory:

```
output/SCRUM-X/
├── index.html                  ← built web app (deployed to Vercel)
├── requirements.md             ← copy of the Jira attachment
├── acceptance-criteria.txt     ← extracted from requirements
├── package.json                ← Jest config
├── app.test.js                 ← generated unit tests
├── test-results.txt            ← Jest output (pass/fail summary)
├── bug-report.md               ← Playwright QA report
└── screenshots/
    ├── screenshot-01-initial-load.png
    ├── screenshot-02-ac1-pass.png
    ├── screenshot-03-ac2-pass.png
    └── ...
```

---

## Error Handling

The pipeline is designed so a story **never gets stuck in progress**:

- Every stage either returns a result or raises a `PipelineError`
- `orchestrator.py` catches all errors and calls `_emergency_close()` which:
  1. Transitions the story to `Bug Reported`
  2. Posts the full Python traceback as a Jira comment
  3. Logs the error to `logs/pipeline.log`

This means even a complete stage failure is visible in Jira with a diagnosis.

---

## Performance Notes

Two shared caches prevent repeated slow operations:

| Cache | Location | Benefit |
|-------|----------|---------|
| npm modules | `.npm-cache/node_modules` | First story installs (~2 min), all subsequent stories symlink instantly |
| Git repo | `.shared-repo/` | Single clone of GitHub repo — all feature branches share history so PRs work |

Both directories are git-ignored and created automatically on first run.

---

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `JIRA_BASE_URL` | Yes | Your Atlassian instance URL |
| `JIRA_EMAIL` | Yes | Atlassian account email |
| `JIRA_API_TOKEN` | Yes | Atlassian API token |
| `JIRA_PROJECT_KEY` | Yes | Project key (e.g. `SCRUM`) |
| `GITHUB_TOKEN` | Yes | PAT with `repo` scope |
| `GITHUB_REPO` | Yes | `owner/repo` (e.g. `muzammal1/ai-pipeline-end-to-end`) |
| `VERCEL_TOKEN` | Yes | Vercel API token |
| `VERCEL_PROJECT_ID` | Yes | Vercel project ID (`prj_...`) |
| `VERCEL_TEAM_ID` | No | Vercel team ID (required for team projects) |
| `RESEND_API_KEY` | Yes | Resend API key (`re_...`) |
| `QA_REPORT_EMAIL` | Yes | Email address to receive QA reports |
| `CLAUDE_BIN` | No | Path to `claude` CLI (default: `claude`) |

---

## Skill Commands

Claude Code slash commands for each stage are in `.claude/commands/`:

| Command | Stage |
|---------|-------|
| `/poll-jira` | Stage 1 instructions |
| `/build-webapp` | Stage 2 instructions |
| `/test-feedback-loop` | Stage 3 instructions |
| `/push-to-github` | Stage 4 instructions |
| `/deploy-to-vercel` | Stage 5 instructions |
| `/qa-playwright` | Stage 6 instructions |
| `/send-report-email` | Stage 7 instructions |
| `/close-jira-loop` | Stage 8 instructions |
| `/orchestrate-pipeline` | Full pipeline overview |

---

## Loom Demo Checklist

The submission requires a screen recording showing:

- [ ] Creating a Jira story with `requirements.md` attached
- [ ] Stepping away — cron picks it up (show logs)
- [ ] Claude building the app (show it running)
- [ ] GitHub PR being opened (show in GitHub)
- [ ] Vercel deployment going live (show the URL)
- [ ] Playwright running against the live site
- [ ] Bug report email arriving in inbox
- [ ] Jira story in final state (Done or Bug Reported)

---

## Constraints Met

- No human intervention at any stage after creating the Jira story
- Cron job runs unattended
- Every stage handles failure gracefully — errors logged and Jira updated
- Jira story always ends in a terminal state (Done or Bug Reported, never stuck In Progress)
- Parallel story processing via `ThreadPoolExecutor`
