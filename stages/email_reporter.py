import base64
import logging
import os

import markdown as md
import requests

import config
from exceptions import PipelineError

log = logging.getLogger("pipeline")

RESEND_URL = "https://api.resend.com/emails"
FROM_EMAIL = "onboarding@resend.dev"   # update to verified domain when available


def send(issue_key: str, qa_status: str, out_dir: str) -> None:
    report_path = os.path.join(out_dir, "bug-report.md")
    if not os.path.exists(report_path):
        raise PipelineError("bug-report.md not found", stage="email-reporter")

    with open(report_path) as f:
        raw_md = f.read()

    html_body = _md_to_html(raw_md)
    subject = f"QA Report — {issue_key} — {qa_status}"
    attachments = _collect_screenshots(out_dir)

    payload = {
        "from": FROM_EMAIL,
        "to": [config.QA_REPORT_EMAIL],
        "subject": subject,
        "html": html_body,
        "attachments": attachments,
    }

    log.info("[%s] Sending QA email to %s…", issue_key, config.QA_REPORT_EMAIL)
    resp = requests.post(
        RESEND_URL,
        headers={
            "Authorization": f"Bearer {config.RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )

    if not resp.ok:
        # Non-fatal: log and continue so Stage 8 still runs
        log.error(
            "[%s] Email send failed: %d %s",
            issue_key,
            resp.status_code,
            resp.text[:200],
        )
        return

    msg_id = resp.json().get("id", "unknown")
    log.info("[%s] Email sent — message ID: %s", issue_key, msg_id)


def _md_to_html(raw: str) -> str:
    body = md.markdown(raw, extensions=["tables", "fenced_code"])
    return f"""<!DOCTYPE html>
<html>
<head><style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 820px;
          margin: 2rem auto; color: #1a1a1a; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
  th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; }}
  th {{ background: #f5f5f5; font-weight: 600; }}
  code {{ background: #f0f0f0; padding: 2px 5px; border-radius: 3px; }}
  pre {{ background: #f0f0f0; padding: 1rem; overflow-x: auto; }}
</style></head>
<body>{body}</body>
</html>"""


def _collect_screenshots(out_dir: str) -> list[dict]:
    shots_dir = os.path.join(out_dir, "screenshots")
    attachments = []
    if not os.path.isdir(shots_dir):
        return attachments

    for fname in sorted(os.listdir(shots_dir)):
        if not fname.endswith(".png"):
            continue
        fpath = os.path.join(shots_dir, fname)
        try:
            with open(fpath, "rb") as f:
                content = base64.b64encode(f.read()).decode()
            attachments.append({"filename": fname, "content": content})
        except OSError as e:
            log.warning("Could not read screenshot %s: %s", fname, e)

    return attachments
