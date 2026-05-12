import logging
import os
import re
import shutil
import subprocess

import requests

import config
from exceptions import PipelineError

log = logging.getLogger("pipeline")

_GH_API = "https://api.github.com"
_GH_HEADERS = {
    "Authorization": f"token {config.GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}

# Single shared repo — all feature branches live here so PRs have common history
_SHARED_REPO = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".shared-repo")


def _slug(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:40]


def _git(args: list[str], cwd: str, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise PipelineError(
            f"git {' '.join(args)} failed: {result.stderr.strip()}",
            stage="github-pusher",
        )
    return result


def _remote_url() -> str:
    return f"https://{config.GITHUB_TOKEN}@github.com/{config.GITHUB_REPO}.git"


def _default_branch() -> str:
    owner, repo = config.GITHUB_REPO.split("/", 1)
    resp = requests.get(f"{_GH_API}/repos/{owner}/{repo}", headers=_GH_HEADERS, timeout=15)
    return resp.json().get("default_branch", "main") if resp.ok else "main"


def _ensure_shared_repo(base_branch: str) -> None:
    """Clone or init the shared repo, ensure base_branch exists on remote."""
    if os.path.isdir(os.path.join(_SHARED_REPO, ".git")):
        # Fetch latest
        _git(["fetch", "origin"], cwd=_SHARED_REPO)
        # Ensure we're on base_branch
        _git(["checkout", base_branch], cwd=_SHARED_REPO, check=False)
        _git(["reset", "--hard", f"origin/{base_branch}"], cwd=_SHARED_REPO, check=False)
        return

    os.makedirs(_SHARED_REPO, exist_ok=True)

    # Check if remote has any commits
    owner, repo_name = config.GITHUB_REPO.split("/", 1)
    resp = requests.get(
        f"{_GH_API}/repos/{owner}/{repo_name}/branches/{base_branch}",
        headers=_GH_HEADERS, timeout=15,
    )

    if resp.ok:
        # Remote has the branch — clone it
        log.info("Cloning shared repo from GitHub…")
        subprocess.run(
            ["git", "clone", _remote_url(), _SHARED_REPO],
            capture_output=True, text=True,
        )
    else:
        # Remote has no base branch — init and push one
        log.info("Initialising shared repo with initial commit on %s…", base_branch)
        _git(["init", "-b", base_branch], cwd=_SHARED_REPO)
        _git(["remote", "add", "origin", _remote_url()], cwd=_SHARED_REPO)
        _git(["config", "user.email", config.JIRA_EMAIL], cwd=_SHARED_REPO)
        _git(["config", "user.name", "AI Pipeline"], cwd=_SHARED_REPO)

        readme = os.path.join(_SHARED_REPO, "README.md")
        with open(readme, "w") as f:
            f.write("# AI Pipeline Output\n\nAuto-generated deployments.\n")
        _git(["add", "README.md"], cwd=_SHARED_REPO)
        _git(["commit", "-m", "chore: initial commit"], cwd=_SHARED_REPO)
        _git(["push", "-u", "origin", base_branch], cwd=_SHARED_REPO)
        log.info("Base branch '%s' created on remote", base_branch)


def push(issue_key: str, summary: str, out_dir: str) -> dict:
    """Copy built files into shared repo, commit on feature branch, push, open PR."""
    branch = f"feature/{issue_key}-{_slug(summary)}"
    base_branch = _default_branch()

    _ensure_shared_repo(base_branch)

    # Switch to a clean feature branch from base
    _git(["checkout", base_branch], cwd=_SHARED_REPO)
    _git(["checkout", "-b", branch], cwd=_SHARED_REPO, check=False)
    _git(["checkout", branch], cwd=_SHARED_REPO)

    # Copy story files to root of the feature branch (Vercel deploys from root)
    SKIP = {"node_modules", ".git", ".venv", "test-run-raw.json", "README.md"}
    # Remove old app files from root first (keep .git)
    for item in os.listdir(_SHARED_REPO):
        if item in {".git", "README.md"}:
            continue
        target = os.path.join(_SHARED_REPO, item)
        if os.path.isdir(target):
            shutil.rmtree(target)
        else:
            os.remove(target)

    for item in os.listdir(out_dir):
        if item in SKIP:
            continue
        src = os.path.join(out_dir, item)
        dst = os.path.join(_SHARED_REPO, item)
        if os.path.isdir(src):
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("node_modules", ".git"))
        else:
            shutil.copy2(src, dst)

    # Stage and commit
    _git(["add", "-A"], cwd=_SHARED_REPO)
    status = _git(["status", "--porcelain"], cwd=_SHARED_REPO)
    if status.stdout.strip():
        _git(["commit", "-m",
              f"feat({issue_key}): build web app\n\nAuto-generated. Jira: {issue_key}"],
             cwd=_SHARED_REPO)

    # Push feature branch
    log.info("[%s] Pushing branch %s…", issue_key, branch)
    push_r = _git(["push", "-u", "origin", branch, "--force"], cwd=_SHARED_REPO, check=False)
    if push_r.returncode != 0:
        raise PipelineError(f"git push failed: {push_r.stderr.strip()}", stage="github-pusher")

    pr_url = _open_pr(issue_key, summary, branch, base_branch, out_dir)
    log.info("[%s] PR: %s", issue_key, pr_url)
    return {"branch": branch, "pr_url": pr_url}


def _open_pr(issue_key: str, summary: str, branch: str, base_branch: str, out_dir: str) -> str:
    ac_path = os.path.join(out_dir, "acceptance-criteria.txt")
    ac_text = ""
    if os.path.exists(ac_path):
        with open(ac_path) as f:
            ac_text = "\n".join(f"- {l}" for l in f.read().splitlines() if l.strip())

    pr_title = f"[{issue_key}] {summary}"
    pr_body = (
        f"## Summary\nAuto-generated for Jira story **{issue_key}**.\n\n"
        f"## Acceptance Criteria\n{ac_text or '_See requirements.md_'}\n\n"
        f"## Test Results\nSee `{issue_key}/test-results.txt`.\n\n"
        f"🤖 Generated by the Zero Human Touch Pipeline"
    )

    # gh CLI
    try:
        env = os.environ.copy()
        env["GH_TOKEN"] = config.GITHUB_TOKEN
        r = subprocess.run(
            ["gh", "pr", "create",
             "--title", pr_title, "--body", pr_body,
             "--head", branch, "--base", base_branch,
             "--repo", config.GITHUB_REPO],
            capture_output=True, text=True, env=env, cwd=_SHARED_REPO,
        )
        if r.returncode == 0:
            return r.stdout.strip()
        log.warning("[%s] gh pr create: %s", issue_key, r.stderr.strip()[:200])
    except FileNotFoundError:
        pass

    # REST API fallback
    owner, repo = config.GITHUB_REPO.split("/", 1)
    resp = requests.post(
        f"{_GH_API}/repos/{owner}/{repo}/pulls",
        headers=_GH_HEADERS,
        json={"title": pr_title, "body": pr_body, "head": branch, "base": base_branch},
        timeout=30,
    )
    if resp.ok:
        return resp.json().get("html_url", "")

    log.warning("[%s] REST PR: %d %s", issue_key, resp.status_code, resp.text[:150])
    return f"https://github.com/{config.GITHUB_REPO}/tree/{branch}"
