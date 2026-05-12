import logging
import time

import requests

import config
from exceptions import PipelineError

log = logging.getLogger("pipeline")

API = "https://api.vercel.com"
HEADERS = {"Authorization": f"Bearer {config.VERCEL_TOKEN}"}

POLL_INTERVAL = 10   # seconds
MAX_WAIT      = 600  # 10 minutes


def _params() -> dict:
    p = {"projectId": config.VERCEL_PROJECT_ID}
    if config.VERCEL_TEAM_ID:
        p["teamId"] = config.VERCEL_TEAM_ID
    return p


def deploy(issue_key: str, branch: str) -> dict:
    """Wait for Vercel to auto-deploy the pushed branch. Returns {deployment_url, deployment_id}."""
    log.info("[%s] Waiting for Vercel to pick up branch '%s'…", issue_key, branch)

    # Give GitHub webhook a moment to reach Vercel
    time.sleep(20)

    deployment = _find_deployment(issue_key, branch)
    deployment_id = deployment["uid"]
    log.info("[%s] Found deployment %s (state: %s)", issue_key, deployment_id, deployment.get("readyState"))

    url = _poll_until_ready(issue_key, deployment_id)
    _health_check(issue_key, url)

    return {"deployment_url": url, "deployment_id": deployment_id}


def _find_deployment(issue_key: str, branch: str) -> dict:
    """Query Vercel for the most recent deployment from the given branch."""
    deadline = time.time() + MAX_WAIT
    while time.time() < deadline:
        params = _params()
        params["meta-githubCommitRef"] = branch
        params["limit"] = 5

        resp = requests.get(f"{API}/v6/deployments", headers=HEADERS, params=params)
        if resp.ok:
            deployments = resp.json().get("deployments", [])
            if deployments:
                return deployments[0]

        log.info("[%s] No deployment found yet — retrying in %ds…", issue_key, POLL_INTERVAL)
        time.sleep(POLL_INTERVAL)

    raise PipelineError(
        f"Vercel deployment not triggered within {MAX_WAIT}s for branch '{branch}'",
        stage="vercel-deployer",
    )


def _poll_until_ready(issue_key: str, deployment_id: str) -> str:
    deadline = time.time() + MAX_WAIT
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        resp = requests.get(
            f"{API}/v13/deployments/{deployment_id}",
            headers=HEADERS,
            params=_params(),
        )
        if not resp.ok:
            raise PipelineError(
                f"Vercel status check failed: {resp.status_code}",
                stage="vercel-deployer",
            )

        data = resp.json()
        state = data.get("readyState", data.get("status", "UNKNOWN"))
        url = f"https://{data.get('url', '')}"

        log.info("[%s] Deployment state: %s (attempt %d)", issue_key, state, attempt)

        if state == "READY":
            return url
        if state in ("ERROR", "CANCELED"):
            raise PipelineError(
                f"Vercel deployment {deployment_id} ended in state: {state}",
                stage="vercel-deployer",
            )

        time.sleep(POLL_INTERVAL)

    raise PipelineError(
        f"Vercel deployment timed out after {MAX_WAIT}s",
        stage="vercel-deployer",
    )


def _health_check(issue_key: str, url: str) -> None:
    log.info("[%s] Health-checking %s…", issue_key, url)
    # 200 = public, 401/403 = live but SSO/password protected — all mean Vercel is serving it
    LIVE_STATUSES = {200, 401, 403}
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=30, allow_redirects=True)
            if resp.status_code in LIVE_STATUSES:
                log.info("[%s] Health check OK (status %d)", issue_key, resp.status_code)
                return
            log.warning("[%s] Health check attempt %d: status %d", issue_key, attempt + 1, resp.status_code)
        except requests.RequestException as e:
            log.warning("[%s] Health check attempt %d error: %s", issue_key, attempt + 1, e)
        time.sleep(10)

    raise PipelineError(
        f"Health check failed for {url} after 3 attempts",
        stage="vercel-deployer",
    )
