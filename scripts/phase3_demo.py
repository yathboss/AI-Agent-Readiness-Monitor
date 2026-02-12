from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[1]
REPORTS = REPO / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)

DEMO_SITE_URL = os.getenv("DEMO_SITE_URL", "http://localhost:3000")
ANALYST_URL = os.getenv("ANALYST_API_URL", "http://localhost:8010").rstrip("/")


def _run(cmd, cwd=None, env=None, check=True):
    print(f"[cmd] {' '.join(cmd)} (cwd={cwd})")
    return subprocess.run(cmd, cwd=cwd, env=env, check=check)


def start_demo_site() -> subprocess.Popen:
    """
    Starts Next.js demo site if present at apps/demo-site.
    If you run it separately, you can skip by setting DEMO_SITE_AUTOSTART=0.
    """
    if os.getenv("DEMO_SITE_AUTOSTART", "1").strip() in ("0", "false", "False"):
        return None

    demo_dir = REPO / "apps" / "demo-site"
    if not demo_dir.exists():
        print("[warn] demo site folder not found: apps/demo-site. Skipping autostart.")
        return None

    # Install deps if needed (best-effort, deterministic commands)
    if not (demo_dir / "node_modules").exists():
        _run(["npm", "install"], cwd=str(demo_dir))

    p = subprocess.Popen(["npm", "run", "dev"], cwd=str(demo_dir))
    time.sleep(4)
    return p


def start_analyst_api() -> subprocess.Popen:
    """
    Starts uvicorn for analyst API if not already running.
    You can skip by setting ANALYST_AUTOSTART=0.
    """
    if os.getenv("ANALYST_AUTOSTART", "1").strip() in ("0", "false", "False"):
        return None

    p = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "apps.analyst.main:app", "--port", "8010"],
        cwd=str(REPO),
    )
    time.sleep(2)
    return p


def wait_health(url: str, timeout_s: int = 40):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            r = requests.get(url, timeout=3)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError(f"Health check failed: {url}")


def generate_runs():
    """
    Generate 2–3 runs to create data in Elasticsearch.
    Assumes ES is already running via docker-compose.
    """
    print("[demo] Generating runs...")
    for i in range(3):
        _run([sys.executable, "-m", "apps.runner.main", "--site", DEMO_SITE_URL])
        time.sleep(1)


def ask_questions() -> str:
    questions = [
        "Why are agents failing to find pricing on this site?",
        "Show the top 5 failure hotspots for refund and explain why.",
        "Give me 3 example traces where contact failed, with evidence.",
        "Which fail reason is increasing over time?",
        "Show hotspots for pricing and suggest fixes mapped to fail reasons.",
    ]

    out = []
    out.append("# Phase 3 Demo Report\n")
    out.append(f"- Demo site: `{DEMO_SITE_URL}`\n")
    out.append(f"- Analyst API: `{ANALYST_URL}`\n")

    for q in questions:
        payload = {"question": q, "domain": "localhost:3000", "time_range": {"relative": "7d"}}
        r = requests.post(f"{ANALYST_URL}/ask", json=payload, timeout=90)
        r.raise_for_status()
        data = r.json()
        result = data.get("result", {})
        md = data.get("markdown", "")

        out.append("\n---\n")
        out.append(f"## Question\n{q}\n")
        out.append("\n### Plan\n")
        for i, step in enumerate(result.get("plan", []), 1):
            out.append(f"{i}. `{step['tool']}` — `{step.get('params', {})}`")

        out.append("\n\n### Markdown output\n")
        out.append(md)

        # Keep JSON short in the report: include top fixes + trace ids
        fixes = result.get("recommended_fixes", [])[:5]
        traces = result.get("evidence", {}).get("example_traces", [])[:2]
        out.append("\n### Top 5 fixes (JSON excerpt)\n")
        out.append("```json\n" + __import__("json").dumps(fixes, indent=2) + "\n```\n")
        out.append("\n### 2 evidence traces (run_id list)\n")
        out.append("```json\n" + __import__("json").dumps([t.get("run_id") for t in traces], indent=2) + "\n```\n")

    return "\n".join(out)


def main():
    demo_proc = None
    analyst_proc = None
    try:
        demo_proc = start_demo_site()
        analyst_proc = start_analyst_api()

        wait_health(f"{ANALYST_URL}/health")

        generate_runs()
        report_md = ask_questions()

        report_path = REPORTS / "phase3_demo.md"
        report_path.write_text(report_md, encoding="utf-8")
        print(f"[ok] wrote report: {report_path}")

    finally:
        if analyst_proc:
            analyst_proc.terminate()
        if demo_proc:
            demo_proc.terminate()


if __name__ == "__main__":
    main()
