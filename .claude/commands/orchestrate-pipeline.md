# Skill: Orchestrate the Full Pipeline

## What this skill does
Runs all 8 stages in sequence for a given Jira story. Handles errors at every stage, ensures the Jira story always ends in a terminal state, and logs every action with timestamps.

## When to invoke
This is the top-level orchestrator. It is called by the cron job for each story returned by Stage 1.

---

## Full execution sequence

```
Stage 1: /poll-jira          → finds stories, transitions to In Progress
Stage 2: /build-webapp        → builds the web app
Stage 3: /test-feedback-loop  → writes + runs tests until passing
Stage 4: /push-to-github      → creates branch + PR
Stage 5: /deploy-to-vercel    → deploys + health check
Stage 6: /qa-playwright       → tests live site, generates bug-report.md
Stage 7: /send-report-email   → emails the report with screenshots
Stage 8: /close-jira-loop     → transitions story to Done or Bug Reported
```

## Pseudocode

```python
def run_pipeline(issue_key: str, summary: str, requirements: str) -> None:
    log(f"[{issue_key}] Pipeline started")
    start_time = time.time()

    try:
        # Stage 2
        build_webapp(issue_key, requirements)
        log(f"[{issue_key}] Stage 2 complete: app built")

        # Stage 3
        test_status = run_test_feedback_loop(issue_key)
        log(f"[{issue_key}] Stage 3 complete: tests {test_status}")

        # Stage 4
        branch, pr_url = push_to_github(issue_key, summary)
        log(f"[{issue_key}] Stage 4 complete: PR {pr_url}")

        # Stage 5
        deployment_url, deployment_id = deploy_to_vercel(issue_key, branch)
        log(f"[{issue_key}] Stage 5 complete: live at {deployment_url}")

        # Stage 6
        qa_status = run_qa_playwright(issue_key, deployment_url)
        log(f"[{issue_key}] Stage 6 complete: QA {qa_status}")

        # Stage 7
        send_report_email(issue_key, qa_status)
        log(f"[{issue_key}] Stage 7 complete: email sent")

        # Stage 8
        close_jira_loop(issue_key, qa_status, deployment_url, pr_url)
        log(f"[{issue_key}] Stage 8 complete: story closed")

    except PipelineError as e:
        log(f"[{issue_key}] PIPELINE ERROR at stage: {e}")
        # Always close the loop even on error
        emergency_close_jira(issue_key, str(e))

    finally:
        duration = time.time() - start_time
        log(f"[{issue_key}] Pipeline finished in {duration:.0f}s")


def emergency_close_jira(issue_key: str, error_message: str) -> None:
    """Called when any stage raises PipelineError. Transitions story to Bug Reported."""
    try:
        comment = f"🚨 Pipeline failed\n\nError: {error_message}\n\nManual investigation required."
        transition_to_bug_reported(issue_key, comment)
    except Exception as e:
        log(f"[{issue_key}] CRITICAL: Could not close Jira story — {e}")
        send_emergency_email(issue_key, error_message)
```

## Cron setup

Add to crontab (`crontab -e`):
```cron
*/5 * * * * cd /path/to/pipeline && python orchestrator.py --once >> logs/cron.log 2>&1
```

Or use the built-in scheduler:
```python
import schedule, time

def job():
    stories = poll_jira()
    for story in stories:
        run_pipeline(story["issue_key"], story["summary"], story["requirements"])

schedule.every(5).minutes.do(job)
while True:
    schedule.run_pending()
    time.sleep(30)
```

## Parallelism opportunities (Principle 6)
If multiple stories are found in one poll, run their pipelines in parallel:
```python
from concurrent.futures import ThreadPoolExecutor

stories = poll_jira()
with ThreadPoolExecutor(max_workers=3) as executor:
    futures = [
        executor.submit(run_pipeline, s["issue_key"], s["summary"], s["requirements"])
        for s in stories
    ]
    for f in futures:
        f.result()  # surface exceptions
```

Within a single story, Stage 2 (build) and test scaffolding setup can overlap.
After Stage 4 (push), Stage 5 deployment starts while Stage 6 QA script is being prepared.

## Logging format
All log lines must follow:
```
[ISO-TIMESTAMP] [{ISSUE_KEY}] [{STAGE}] {MESSAGE}
2025-05-07T14:32:01Z [AI-42] [STAGE-2] Building web app from requirements.md
2025-05-07T14:32:45Z [AI-42] [STAGE-3] Tests: 5/5 passing after 2 iterations
2025-05-07T14:33:12Z [AI-42] [STAGE-5] Live at https://ai-42-todo-abc123.vercel.app
```

## Principle alignment
- **Principle 2 (Feedback Loop):** Each stage's output is verified before the next runs
- **Principle 4 (Workflows):** This orchestrator IS the workflow — defined once, runs forever
- **Principle 6 (Parallelism):** Multiple stories run concurrently; stages within a story overlap where safe
