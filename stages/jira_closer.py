import logging
import os

import requests

from stages.jira_poller import _jira, _get_transition_id, _comment
from exceptions import PipelineError

log = logging.getLogger("pipeline")

_DONE_NAMES    = ["done", "closed", "complete", "resolved"]
_REVIEW_NAMES  = ["in review", "review", "needs review"]
_BUG_NAMES     = ["bug reported", "reopened", "blocked"]


def close(issue_key: str, qa_status: str, deployment_url: str, pr_url: str, out_dir: str) -> None:
    if qa_status == "PASS":
        _close_as_done(issue_key, deployment_url, pr_url)
    else:
        _close_as_bug(issue_key, qa_status, deployment_url, pr_url, out_dir)

    _verify_not_in_progress(issue_key)


def _close_as_done(issue_key: str, deployment_url: str, pr_url: str) -> None:
    # Try direct Done transition first
    tid = _find_transition(issue_key, _DONE_NAMES, fallback=None)
    if tid:
        _jira("POST", f"/issue/{issue_key}/transitions", json={"transition": {"id": tid}})
        log.info("[%s] Transitioned directly to Done", issue_key)
    else:
        # Workflow requires In Review → Done (standard Scrum board)
        review_tid = _find_transition(issue_key, _REVIEW_NAMES, fallback=None)
        if review_tid:
            _jira("POST", f"/issue/{issue_key}/transitions", json={"transition": {"id": review_tid}})
            log.info("[%s] Transitioned to In Review (step 1/2)", issue_key)
            done_tid = _find_transition(issue_key, _DONE_NAMES, fallback=None)
            if done_tid:
                _jira("POST", f"/issue/{issue_key}/transitions", json={"transition": {"id": done_tid}})
                log.info("[%s] Transitioned to Done (step 2/2)", issue_key)
            else:
                log.info("[%s] Resting at In Review (Done not reachable from here)", issue_key)
        else:
            # Last resort — use whatever transition is available
            fallback_tid = _find_transition(issue_key, _DONE_NAMES, fallback=_REVIEW_NAMES)
            _jira("POST", f"/issue/{issue_key}/transitions", json={"transition": {"id": fallback_tid}})
            log.info("[%s] Transitioned using fallback", issue_key)

    _comment(
        issue_key,
        f"✅ Pipeline complete — all QA tests passed.\n\n"
        f"Deployment URL: {deployment_url}\n"
        f"GitHub PR: {pr_url}\n\n"
        f"_Automated by the Zero Human Touch Pipeline_",
    )


def _close_as_bug(
    issue_key: str, qa_status: str, deployment_url: str, pr_url: str, out_dir: str
) -> None:
    tid = _find_transition(issue_key, _BUG_NAMES, fallback=_REVIEW_NAMES + _DONE_NAMES)
    _jira("POST", f"/issue/{issue_key}/transitions", json={"transition": {"id": tid}})
    log.info("[%s] Transitioned to Bug Reported/In Review", issue_key)

    report_path = os.path.join(out_dir, "bug-report.md")
    report_text = ""
    if os.path.exists(report_path):
        with open(report_path) as f:
            report_text = f.read()

    _comment(
        issue_key,
        f"❌ Pipeline complete — QA status: {qa_status}\n\n"
        f"Deployment URL: {deployment_url}\n"
        f"GitHub PR: {pr_url}\n\n"
        f"--- Bug Report ---\n\n{report_text[:3000]}\n\n"
        f"_Automated by the Zero Human Touch Pipeline_",
    )


def _find_transition(issue_key: str, preferred: list[str], fallback: list[str] | None = None) -> str | None:
    data = _jira("GET", f"/issue/{issue_key}/transitions").json()
    transitions = data["transitions"]

    for name in preferred:
        for t in transitions:
            if name in t["name"].lower():
                return t["id"]

    if fallback is None:
        available = [t["name"] for t in transitions]
        log.debug("[%s] No match in %s. Available: %s", issue_key, preferred, available)
        return None

    for name in fallback:
        for t in transitions:
            if name in t["name"].lower():
                return t["id"]

    available = [t["name"] for t in transitions]
    log.warning("[%s] No matching transition found. Available: %s — using first", issue_key, available)
    return transitions[0]["id"] if transitions else None


def _verify_not_in_progress(issue_key: str) -> None:
    data = _jira("GET", f"/issue/{issue_key}?fields=status").json()
    status_name = data["fields"]["status"]["name"]
    if "progress" in status_name.lower():
        log.error("[%s] Story still In Progress after close attempt!", issue_key)
        raise PipelineError(
            f"Story {issue_key} is still in '{status_name}' after close attempt",
            stage="jira-closer",
        )
    log.info("[%s] Final Jira status: %s", issue_key, status_name)
