import base64
import logging
from typing import Any

import requests

import config
from exceptions import PipelineError

log = logging.getLogger("pipeline")

_AUTH = base64.b64encode(
    f"{config.JIRA_EMAIL}:{config.JIRA_API_TOKEN}".encode()
).decode()

HEADERS = {
    "Authorization": f"Basic {_AUTH}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

JQL = (
    f'project = {config.JIRA_PROJECT_KEY} '
    f'AND labels = ai-ready '
    f'AND status = "To Do"'
)


def _jira(method: str, path: str, **kwargs) -> Any:
    url = f"{config.JIRA_BASE_URL}/rest/api/3{path}"
    resp = requests.request(method, url, headers=HEADERS, **kwargs)
    if not resp.ok:
        raise PipelineError(
            f"Jira API {method} {path} → {resp.status_code}: {resp.text[:400]}",
            stage="jira-poller",
        )
    return resp


def _get_transition_id(issue_key: str, target_name: str) -> str:
    data = _jira("GET", f"/issue/{issue_key}/transitions").json()
    for t in data["transitions"]:
        if t["name"].lower() == target_name.lower():
            return t["id"]
    # fuzzy fallback
    for t in data["transitions"]:
        if target_name.lower() in t["name"].lower():
            return t["id"]
    available = [t["name"] for t in data["transitions"]]
    raise PipelineError(
        f"Transition '{target_name}' not found. Available: {available}",
        stage="jira-poller",
    )


def _transition(issue_key: str, status_name: str) -> None:
    tid = _get_transition_id(issue_key, status_name)
    _jira("POST", f"/issue/{issue_key}/transitions", json={"transition": {"id": tid}})
    log.info("[%s] Transitioned to '%s'", issue_key, status_name)


def _comment(issue_key: str, text: str) -> None:
    body = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": text}],
                }
            ],
        }
    }
    _jira("POST", f"/issue/{issue_key}/comment", json=body)


def _download_attachment(attachment: dict) -> str:
    resp = requests.get(
        attachment["content"],
        headers={"Authorization": f"Basic {_AUTH}"},
    )
    if not resp.ok:
        raise PipelineError(
            f"Failed to download attachment {attachment['id']}: {resp.status_code}",
            stage="jira-poller",
        )
    return resp.text


def poll() -> list[dict]:
    """Return list of {issue_key, summary, requirements} dicts."""
    log.info("Polling Jira: %s", JQL)
    data = _jira(
        "GET",
        "/search/jql",
        params={"jql": JQL, "fields": "summary,attachment,status,labels", "maxResults": 10},
    ).json()

    issues = data.get("issues", [])
    log.info("Found %d story(ies) to process", len(issues))

    results = []
    for issue in issues:
        key = issue["key"]
        summary = issue["fields"]["summary"]
        attachments = issue["fields"].get("attachment") or []

        req_attachment = next(
            (a for a in attachments if a["filename"] == "requirements.md"), None
        )

        if not req_attachment:
            log.warning("[%s] No requirements.md attachment — skipping", key)
            try:
                _comment(key, "⚠️ Pipeline skipped: no requirements.md attachment found.")
                _transition(key, "Bug Reported")
            except PipelineError as e:
                log.error("[%s] Could not update story: %s", key, e)
            continue

        try:
            requirements = _download_attachment(req_attachment)
        except PipelineError as e:
            log.error("[%s] Attachment download failed: %s", key, e)
            _comment(key, f"⚠️ Pipeline failed: could not download requirements.md — {e}")
            _transition(key, "Bug Reported")
            continue

        # Transition immediately so next cron tick won't re-pick
        _transition(key, "In Progress")
        _comment(key, "🤖 Pipeline triggered. Building app from requirements.md…")

        results.append({"issue_key": key, "summary": summary, "requirements": requirements})

    return results
