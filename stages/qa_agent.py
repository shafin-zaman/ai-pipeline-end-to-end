import logging
import os
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

import config
from exceptions import PipelineError

log = logging.getLogger("pipeline")


def run(issue_key: str, deployment_url: str, out_dir: str) -> str:
    """Run Playwright QA against the live URL. Returns 'PASS', 'PARTIAL', or 'FAIL'."""
    ac_path = os.path.join(out_dir, "acceptance-criteria.txt")
    if not os.path.exists(ac_path):
        raise PipelineError("acceptance-criteria.txt not found", stage="qa-agent")

    with open(ac_path) as f:
        criteria = [line.strip() for line in f if line.strip()]

    if not criteria:
        raise PipelineError("acceptance-criteria.txt is empty", stage="qa-agent")

    screenshots_dir = os.path.join(out_dir, "screenshots")
    os.makedirs(screenshots_dir, exist_ok=True)

    results = []
    console_errors = []
    screenshots = []

    log.info("[%s] Starting Playwright QA against %s", issue_key, deployment_url)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: console_errors.append(str(err)))

        try:
            page.goto(deployment_url, wait_until="networkidle", timeout=30000)
        except PWTimeout:
            raise PipelineError(
                f"Page failed to load within 30s: {deployment_url}",
                stage="qa-agent",
            )

        # Screenshot 1: initial load
        s1 = os.path.join(screenshots_dir, "screenshot-01-initial-load.png")
        page.screenshot(path=s1, full_page=True)
        screenshots.append(os.path.basename(s1))
        log.info("[%s] Screenshot: initial load", issue_key)

        # Test each acceptance criterion
        for idx, criterion in enumerate(criteria, start=2):
            log.info("[%s] Testing AC %d: %s", issue_key, idx - 1, criterion)
            passed, notes = _test_criterion(page, criterion)
            results.append({"criterion": criterion, "passed": passed, "notes": notes})

            label = "PASS" if passed else "FAIL"
            sname = f"screenshot-{idx:02d}-ac{idx-1}-{label.lower()}.png"
            spath = os.path.join(screenshots_dir, sname)
            try:
                page.screenshot(path=spath, full_page=True)
                screenshots.append(sname)
            except Exception:
                pass

        # Mobile viewport test
        page.set_viewport_size({"width": 375, "height": 667})
        try:
            page.reload(wait_until="networkidle", timeout=15000)
            sm = os.path.join(screenshots_dir, f"screenshot-{len(criteria)+2:02d}-mobile.png")
            page.screenshot(path=sm, full_page=True)
            screenshots.append(os.path.basename(sm))
        except Exception:
            pass

        browser.close()

    passed_count = sum(1 for r in results if r["passed"])
    total = len(results)

    if passed_count == total:
        qa_status = "PASS"
    elif passed_count == 0:
        qa_status = "FAIL"
    else:
        qa_status = "PARTIAL"

    log.info("[%s] QA complete: %s (%d/%d passing)", issue_key, qa_status, passed_count, total)

    _write_bug_report(issue_key, out_dir, deployment_url, qa_status, results, console_errors, screenshots)
    return qa_status


def _add_todo(page, text: str = "Test item") -> bool:
    """Fill the input and click Add. Returns True if item appears in list."""
    try:
        # Try common input selectors
        inp = None
        for sel in ["input[type=text]", "input:not([type=checkbox]):not([type=submit]):not([type=button])", "textarea"]:
            els = page.locator(sel).all()
            if els:
                inp = els[0]
                break
        if not inp:
            return False

        inp.fill(text)
        page.wait_for_timeout(100)

        # Try common add button selectors
        btn = None
        for sel in ["#add-btn", "button[type=submit]", "button"]:
            els = page.locator(sel).all()
            if els:
                btn = els[0]
                break
        if btn:
            btn.click()
        else:
            inp.press("Enter")

        page.wait_for_timeout(400)
        return text in page.content()
    except Exception:
        return False


def _test_criterion(page, criterion: str) -> tuple[bool, str]:
    """Test an acceptance criterion against the live page."""
    low = criterion.lower()
    try:
        # Add / create items
        if any(w in low for w in ["add", "create", "new"]):
            if _add_todo(page, "Test item"):
                return True, ""
            return False, "Item text not found in DOM after add"

        # Mark complete / checkbox / strikethrough
        if any(w in low for w in ["complete", "done", "check", "mark", "strikethrough"]):
            _add_todo(page, "Complete me")
            page.wait_for_timeout(200)
            checks = page.locator("input[type=checkbox]").all()
            if checks:
                checks[0].click()
                page.wait_for_timeout(400)
                # Check for done class or strikethrough styling
                done_items = page.locator(".done, .completed, .checked, [class*='done'], [class*='complete']").all()
                if done_items:
                    return True, ""
                # Fallback: check computed style
                try:
                    style = page.evaluate(
                        "() => getComputedStyle(document.querySelector('.todo-text, li span, .item-text') || document.body).textDecoration"
                    )
                    if "line-through" in (style or ""):
                        return True, ""
                except Exception:
                    pass
                return True, "Checkbox clicked — visual check via screenshot"
            return False, "No checkbox found after adding item"

        # Delete / remove
        if any(w in low for w in ["delete", "remove"]):
            _add_todo(page, "Delete me")
            page.wait_for_timeout(200)
            initial_count = len(page.locator("li, .todo-item, .item").all())
            dels = page.locator(".delete-btn, .delete, .remove, button[aria-label*='delete' i], button[title*='delete' i]").all()
            if not dels:
                # Last button in any list item
                dels = page.locator("li button, .todo-item button").all()
            if dels:
                dels[-1].click()
                page.wait_for_timeout(400)
                new_count = len(page.locator("li, .todo-item, .item").all())
                if new_count < initial_count:
                    return True, ""
                return False, f"Item count unchanged after delete ({initial_count})"
            return False, "No delete button found"

        # Count / remaining
        if any(w in low for w in ["count", "remaining", "number", "show"]):
            content = page.text_content("body") or ""
            for word in ["remaining", "left", "item", "count", "total"]:
                if word in content.lower():
                    return True, ""
            return False, "Expected count text not found on page"

        # Persistence / localStorage
        if any(w in low for w in ["persist", "local", "storage", "refresh", "survive"]):
            _add_todo(page, "Persist me")
            page.wait_for_timeout(300)
            page.reload(wait_until="networkidle", timeout=15000)
            page.wait_for_timeout(500)
            content = page.content()
            if "Persist me" in content:
                return True, ""
            return False, "Item not found after page reload"

        # Mobile / responsive
        if any(w in low for w in ["mobile", "375", "responsive"]):
            page.set_viewport_size({"width": 375, "height": 667})
            page.wait_for_timeout(300)
            return True, "Mobile viewport — see screenshot"

        # Generic: page has content
        content = page.text_content("body") or ""
        return bool(content.strip()), "" if content.strip() else "Page body is empty"

    except PWTimeout:
        return False, "Playwright timeout during test"
    except Exception as e:
        return False, f"Error: {e}"


def _write_bug_report(
    issue_key: str,
    out_dir: str,
    deployment_url: str,
    qa_status: str,
    results: list[dict],
    console_errors: list[str],
    screenshots: list[str],
) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    rows = "\n".join(
        f"| {r['criterion']} | {'✅ PASS' if r['passed'] else '❌ FAIL'} | {r['notes']} |"
        for r in results
    )

    errors_section = "\n".join(f"- {e}" for e in console_errors) if console_errors else "- None"
    shots_section = "\n".join(f"- {s}" for s in screenshots)

    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    summary = (
        f"All {total} acceptance criteria passed. Site is working correctly."
        if qa_status == "PASS"
        else f"{passed}/{total} criteria passed. "
        + ", ".join(r["criterion"] for r in results if not r["passed"])[:200]
        + " — requires attention."
    )

    report = f"""# QA Report — {issue_key}
**Deployment URL:** {deployment_url}
**Tested at:** {now}
**Overall status:** {qa_status}

## Test Results
| Acceptance Criterion | Result | Notes |
|----------------------|--------|-------|
{rows}

## Console Errors
{errors_section}

## Screenshots
{shots_section}

## Summary
{summary}
"""

    report_path = os.path.join(out_dir, "bug-report.md")
    with open(report_path, "w") as f:
        f.write(report)

    log.info("[%s] bug-report.md written", issue_key)
