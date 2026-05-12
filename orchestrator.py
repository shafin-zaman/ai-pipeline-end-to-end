#!/usr/bin/env python3
"""Zero Human Touch Pipeline — orchestrator.

Usage:
  uv run python orchestrator.py --once      # single poll cycle
  uv run python orchestrator.py --schedule  # run every 5 min forever
"""

import argparse
import logging
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

import schedule
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.text import Text
from rich import box

import config
from exceptions import PipelineError
from stages import jira_poller, build_agent, test_runner, github_pusher, vercel_deployer, qa_agent, email_reporter, jira_closer

# ── Logging ──────────────────────────────────────────────────────────────────

os.makedirs(config.LOGS_DIR, exist_ok=True)
os.makedirs(config.OUTPUT_DIR, exist_ok=True)

console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
    handlers=[
        RichHandler(
            console=console,
            show_time=True,
            show_path=False,
            markup=True,
            rich_tracebacks=True,
            log_time_format="%H:%M:%S",
        ),
        logging.FileHandler(os.path.join(config.LOGS_DIR, "pipeline.log")),
    ],
)

# Plain formatter for the file handler (no rich markup)
file_handler = logging.getLogger().handlers[1]
file_handler.setFormatter(logging.Formatter(
    fmt="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
))

log = logging.getLogger("pipeline")


STAGE_LABELS = {
    2: ("BUILD",   "cyan"),
    3: ("TESTS",   "yellow"),
    4: ("GITHUB",  "blue"),
    5: ("VERCEL",  "magenta"),
    6: ("QA",      "green"),
    7: ("EMAIL",   "bright_cyan"),
    8: ("JIRA",    "bright_green"),
}


def _stage_log(issue_key: str, stage_num: int, message: str) -> None:
    label, color = STAGE_LABELS[stage_num]
    log.info("[%s] [bold %s]Stage %d ▸ %s[/bold %s]  %s",
             issue_key, color, stage_num, label, color, message)


def _banner(issue_key: str, summary: str) -> None:
    text = Text()
    text.append(f" {issue_key} ", style="bold white on blue")
    text.append(f"  {summary}", style="bold white")
    console.print(Panel(text, box=box.DOUBLE_EDGE, border_style="blue", expand=False))


def _result_banner(issue_key: str, qa_status: str, elapsed: float) -> None:
    color = "green" if qa_status == "PASS" else ("yellow" if qa_status == "PARTIAL" else "red")
    text = Text()
    text.append(f" {issue_key} ", style=f"bold white on {color}")
    text.append(f"  {qa_status}  ", style=f"bold {color}")
    text.append(f"completed in {elapsed:.0f}s", style="dim")
    console.print(Panel(text, box=box.DOUBLE_EDGE, border_style=color, expand=False))


# ── Per-story pipeline ────────────────────────────────────────────────────────

def run_story(story: dict) -> None:
    issue_key    = story["issue_key"]
    summary      = story["summary"]
    requirements = story["requirements"]
    start        = time.time()

    _banner(issue_key, summary)

    out_dir    = None
    pr_url     = f"https://github.com/{config.GITHUB_REPO}"
    deploy_url = ""
    qa_status  = "FAIL"

    try:
        # Stage 2 — Build
        _stage_log(issue_key, 2, "Building web app…")
        out_dir = build_agent.build(issue_key, requirements)
        log.info("[%s] [green]✓[/green] App built → %s", issue_key, out_dir)

        # Stage 3 — Tests
        _stage_log(issue_key, 3, "Running test feedback loop…")
        test_runner.run(issue_key, out_dir)
        log.info("[%s] [green]✓[/green] Tests passed", issue_key)

        # Stage 4 — GitHub
        _stage_log(issue_key, 4, "Pushing to GitHub…")
        gh_result = github_pusher.push(issue_key, summary, out_dir)
        branch    = gh_result["branch"]
        pr_url    = gh_result["pr_url"]
        log.info("[%s] [green]✓[/green] PR → %s", issue_key, pr_url)

        # Stage 5 — Vercel
        _stage_log(issue_key, 5, "Deploying to Vercel (polling until READY)…")
        v_result   = vercel_deployer.deploy(issue_key, branch)
        deploy_url = v_result["deployment_url"]
        log.info("[%s] [green]✓[/green] Live → %s", issue_key, deploy_url)

        # Stage 6 — QA
        _stage_log(issue_key, 6, f"Running Playwright QA against {deploy_url}…")
        qa_status = qa_agent.run(issue_key, deploy_url, out_dir)
        qa_color  = "green" if qa_status == "PASS" else ("yellow" if qa_status == "PARTIAL" else "red")
        log.info("[%s] [%s]✓ QA %s[/%s]", issue_key, qa_color, qa_status, qa_color)

        # Stage 7 — Email
        _stage_log(issue_key, 7, "Sending QA report email…")
        email_reporter.send(issue_key, qa_status, out_dir)
        log.info("[%s] [green]✓[/green] Email sent", issue_key)

    except PipelineError as e:
        log.error("[%s] [red]Pipeline error:[/red] %s", issue_key, e)
        _emergency_close(issue_key, str(e), out_dir)
        return

    except Exception as e:
        tb = traceback.format_exc()
        log.error("[%s] [red]Unexpected error:[/red] %s\n%s", issue_key, e, tb)
        _emergency_close(issue_key, f"Unexpected error: {e}\n\n{tb}", out_dir)
        return

    # Stage 8 — Close Jira
    _stage_log(issue_key, 8, "Closing Jira loop…")
    try:
        jira_closer.close(issue_key, qa_status, deploy_url, pr_url, out_dir)
        log.info("[%s] [green]✓[/green] Jira story closed", issue_key)
    except Exception as e:
        log.error("[%s] Jira close failed: %s", issue_key, e)

    _result_banner(issue_key, qa_status, time.time() - start)


def _emergency_close(issue_key: str, error_msg: str, out_dir: str | None) -> None:
    """Always transition the story out of In Progress, even on hard failure."""
    log.warning("[%s] Emergency close — transitioning to Bug Reported", issue_key)
    try:
        from stages.jira_poller import _jira, _comment
        data = _jira("GET", f"/issue/{issue_key}/transitions").json()
        transitions = data["transitions"]
        bug_id = next(
            (t["id"] for t in transitions if "bug" in t["name"].lower() or "review" in t["name"].lower()),
            transitions[0]["id"] if transitions else None,
        )
        if bug_id:
            _jira("POST", f"/issue/{issue_key}/transitions", json={"transition": {"id": bug_id}})
        _comment(issue_key, f"🚨 Pipeline failed at an early stage.\n\nError:\n{error_msg[:2000]}")
    except Exception as e:
        log.error("[%s] Emergency close also failed: %s", issue_key, e)


# ── Poll cycle ────────────────────────────────────────────────────────────────

def poll_and_run() -> None:
    log.info("[dim]Polling Jira for [bold]ai-ready[/bold] stories…[/dim]")
    try:
        stories = jira_poller.poll()
    except PipelineError as e:
        log.error("Jira poll failed: %s", e)
        return

    if not stories:
        log.info("[dim]No new stories found — sleeping until next poll.[/dim]")
        return

    log.info("[bold]Found %d story(ies) — starting pipeline…[/bold]", len(stories))

    if len(stories) == 1:
        run_story(stories[0])
    else:
        # Principle 6 — run multiple stories in parallel
        with ThreadPoolExecutor(max_workers=min(len(stories), 3)) as executor:
            futures = {executor.submit(run_story, s): s["issue_key"] for s in stories}
            for future in as_completed(futures):
                key = futures[future]
                try:
                    future.result()
                except Exception as e:
                    log.error("[%s] Unhandled future error: %s", key, e)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Zero Human Touch Pipeline")
    group  = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--once",     action="store_true", help="Run a single poll cycle and exit")
    group.add_argument("--schedule", action="store_true", help="Run on a 5-minute schedule forever")
    args = parser.parse_args()

    console.print(Panel(
        "[bold white]Zero Human Touch Pipeline[/bold white]\n"
        "[dim]Jira → Build → Tests → GitHub → Vercel → QA → Email → Close[/dim]",
        border_style="blue", box=box.DOUBLE_EDGE, expand=False,
    ))

    if args.once:
        poll_and_run()
    else:
        log.info("[bold]Scheduler started[/bold] — polling every [cyan]5 minutes[/cyan]")
        schedule.every(5).minutes.do(poll_and_run)
        poll_and_run()  # run immediately on startup
        while True:
            schedule.run_pending()
            time.sleep(30)


if __name__ == "__main__":
    main()
