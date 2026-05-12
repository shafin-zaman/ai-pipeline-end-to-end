# Skill: Send Bug Report Email (Stage 7)

## What this skill does
Sends an email to the configured QA report address with the `bug-report.md` as the body and all Playwright screenshots as attachments. Uses the Resend API.

## Inputs required
- `issue_key` — e.g. `AI-42`
- `qa_status` — `PASS`, `PARTIAL`, or `FAIL`
- `output/{issue_key}/bug-report.md` — the QA report
- `output/{issue_key}/screenshots/` — directory of PNG screenshots
- `RESEND_API_KEY`, `QA_REPORT_EMAIL` from environment

## Outputs
- Email sent successfully (or `PipelineError` if send fails)
- Log entry: `[AI-42] Email sent to {QA_REPORT_EMAIL} — Message ID: {id}`

---

## Step-by-step instructions

### Step 1 — Read the bug report
```python
with open(f"output/{issue_key}/bug-report.md") as f:
    bug_report_content = f.read()
```

### Step 2 — Collect screenshots
```python
import os, glob
screenshots = glob.glob(f"output/{issue_key}/screenshots/*.png")
screenshots.sort()  # deterministic order
```

### Step 3 — Build the email subject
```python
subject = f"QA Report — {issue_key} — {qa_status}"
# Examples:
# "QA Report — AI-42 — PASS"
# "QA Report — AI-42 — FAIL"
```

### Step 4 — Convert bug report markdown to HTML for email body
Use a simple markdown-to-HTML conversion:
```python
import markdown
html_body = markdown.markdown(bug_report_content, extensions=['tables'])
```
Wrap in minimal HTML:
```html
<!DOCTYPE html>
<html>
<head><style>
  body { font-family: -apple-system, sans-serif; max-width: 800px; margin: 2rem auto; }
  table { border-collapse: collapse; width: 100%; }
  th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
  th { background: #f5f5f5; }
</style></head>
<body>{html_body}</body>
</html>
```

### Step 5 — Send via Resend API
```python
import requests, base64

attachments = []
for screenshot_path in screenshots:
    with open(screenshot_path, 'rb') as f:
        content = base64.b64encode(f.read()).decode('utf-8')
    attachments.append({
        "filename": os.path.basename(screenshot_path),
        "content": content
    })

response = requests.post(
    "https://api.resend.com/emails",
    headers={
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json"
    },
    json={
        "from": "pipeline@yourdomain.com",
        "to": [QA_REPORT_EMAIL],
        "subject": subject,
        "html": html_body,
        "attachments": attachments
    }
)

if response.status_code not in (200, 201):
    raise PipelineError(f"Email send failed: {response.status_code} {response.text}")

message_id = response.json().get("id")
```

### Alternative: SendGrid
If using SendGrid instead of Resend:
```python
import sendgrid
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition

sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
message = Mail(
    from_email='pipeline@yourdomain.com',
    to_emails=QA_REPORT_EMAIL,
    subject=subject,
    html_content=html_body
)
for screenshot_path in screenshots:
    with open(screenshot_path, 'rb') as f:
        data = base64.b64encode(f.read()).decode()
    attachment = Attachment(
        FileContent(data),
        FileName(os.path.basename(screenshot_path)),
        FileType('image/png'),
        Disposition('attachment')
    )
    message.add_attachment(attachment)

response = sg.send(message)
```

### Step 6 — Log and return
```python
log(f"[{issue_key}] QA email sent to {QA_REPORT_EMAIL} — Message ID: {message_id}")
return {"email_sent": True, "message_id": message_id}
```

---

## Error handling
- If screenshots directory is empty: send the email without attachments, note it in the log
- If a single screenshot file is corrupt: skip it, continue with the rest
- If the email API returns 4xx: check API key validity, raise `PipelineError`
- If the email API returns 5xx: retry once after 30 seconds, then raise `PipelineError`
- Never block the pipeline on email failure — log the error, continue to Stage 8

## Principle alignment
- **Principle 3 (Tools):** Email is the notification tool that closes the human feedback channel
- **Principle 4 (Workflows):** Structured subject line format makes emails immediately scannable
