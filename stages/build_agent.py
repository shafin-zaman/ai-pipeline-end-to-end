import logging
import os
import subprocess

import config
from exceptions import PipelineError

log = logging.getLogger("pipeline")


def build(issue_key: str, requirements: str) -> str:
    """Build the web app. Returns the output directory path."""
    out_dir = os.path.join(config.OUTPUT_DIR, issue_key)
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(os.path.join(out_dir, "screenshots"), exist_ok=True)

    # Write requirements so claude can read them from the working dir
    req_path = os.path.join(out_dir, "requirements.md")
    with open(req_path, "w") as f:
        f.write(requirements)

    log.info("[%s] Running build agent in %s", issue_key, out_dir)

    prompt = f"""You are an expert web developer. Build a complete web application based on the requirements in requirements.md.

IMPORTANT RULES:
1. Read requirements.md FULLY before writing any code.
2. Build a complete, working web application — no placeholders, no TODOs.
3. Follow the exact tech stack specified in requirements.md.
4. Default to a single index.html file (HTML + CSS + JS inline) unless the requirements specify otherwise.
5. The output must be deployable to Vercel as a static site — index.html must be at the root.
6. Make it mobile-responsive (minimum 375px wide).
7. After writing the code, create a file called acceptance-criteria.txt with each acceptance criterion on its own line (copy them verbatim from requirements.md).
8. Do NOT ask for clarification — make reasonable decisions and build.

Start by reading requirements.md, then build the app."""

    result = subprocess.run(
        [
            config.CLAUDE_BIN,
            "-p", prompt,
            "--allowedTools", "Read,Write,Edit,MultiEdit,Bash",
        ],
        cwd=out_dir,
        timeout=300,
        text=True,
    )

    if result.returncode != 0:
        raise PipelineError(
            f"Build agent exited with code {result.returncode}",
            stage="build-agent",
        )

    # Verify the minimum expected output exists
    index_path = os.path.join(out_dir, "index.html")
    if not os.path.exists(index_path):
        raise PipelineError(
            "Build agent completed but index.html was not created",
            stage="build-agent",
        )

    ac_path = os.path.join(out_dir, "acceptance-criteria.txt")
    if not os.path.exists(ac_path):
        log.warning("[%s] acceptance-criteria.txt missing — extracting from requirements", issue_key)
        _extract_ac_fallback(requirements, ac_path)

    log.info("[%s] Build complete: %s", issue_key, out_dir)
    return out_dir


def _extract_ac_fallback(requirements: str, ac_path: str) -> None:
    """Best-effort extraction of acceptance criteria lines from requirements.md."""
    lines = []
    in_ac_section = False
    for line in requirements.splitlines():
        low = line.lower().strip()
        if "acceptance" in low and ("criteria" in low or "criterion" in low):
            in_ac_section = True
            continue
        if in_ac_section:
            if line.startswith("#"):
                break
            stripped = line.lstrip("-* ").strip()
            if stripped:
                lines.append(stripped)
    with open(ac_path, "w") as f:
        f.write("\n".join(lines))
