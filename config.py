import os
from dotenv import load_dotenv

load_dotenv()

def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise RuntimeError(f"Missing required env var: {key}")
    return val

JIRA_BASE_URL   = _require("JIRA_BASE_URL").rstrip("/")
JIRA_EMAIL      = _require("JIRA_EMAIL")
JIRA_API_TOKEN  = _require("JIRA_API_TOKEN")
JIRA_PROJECT_KEY = _require("JIRA_PROJECT_KEY")

GITHUB_TOKEN = _require("GITHUB_TOKEN")
GITHUB_REPO  = _require("GITHUB_REPO")

VERCEL_TOKEN      = _require("VERCEL_TOKEN")
VERCEL_PROJECT_ID = _require("VERCEL_PROJECT_ID")
VERCEL_TEAM_ID    = os.getenv("VERCEL_TEAM_ID", "")

RESEND_API_KEY  = _require("RESEND_API_KEY")
QA_REPORT_EMAIL = _require("QA_REPORT_EMAIL")

CLAUDE_BIN = os.getenv("CLAUDE_BIN", "claude")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
LOGS_DIR   = os.path.join(os.path.dirname(__file__), "logs")
