# AI-Agent-Readiness-Monitor (Agentic Web Observability Analyzer)

Measure how reliably AI agents can find **Pricing**, **Refund/Return policy**, and **Contact** info on websites using deterministic runs, traces, and Elasticsearch dashboards.

---

## Overview

This project is an **observability + QA harness** for “agent-readiness”:
- Deterministic **task-suite runner** (Phase 1/2)
- Elasticsearch-backed **logs + metrics + dashboards** (Phase 2)
- Deterministic **Analyst Agent** for natural-language investigation with evidence + recommendations (Phase 3)

**Ethics / safety:** This tool is for observability and QA. **Do not bypass bot protections** or access controls. Only test websites you own or have explicit permission to test.

---

## Indices

Daily indices:
- `agent_steps-YYYY.MM.DD`
- `agent_runs-YYYY.MM.DD`

Phase 3 adds:
- `agent_audit-YYYY.MM.DD` (Analyst tool-call audit)

---

## Failure taxonomy (enum)

The runner uses a fixed failure taxonomy (non free-text):

- `not_found`
- `hard_to_find`
- `js_only`
- `non_text`
- `ambiguous`
- `blocked`
- `timeout`
- `requires_login`
- `unknown`

---

## 1) Start Elasticsearch + Kibana (dev mode)

Requirements: **Docker Desktop**

```bash
cd infra
docker compose up -d
Elasticsearch: http://localhost:9200

Kibana: http://localhost:5601

Security is disabled for local development.

2) Python environment setup (VS Code friendly)
Requirements: Python 3.11+

# from repo root
python -m venv .venv

# Windows:
#   .venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
python -m playwright install chromium
Create your env file:

cp .env.example .env
3) (Optional) Run the demo site (Next.js)
The demo site includes some intentionally “agent-hostile” patterns:

/pricing renders pricing after a JS delay + large inline script (can trigger js_only)

/refund provides policy only as a PDF link

/contact includes an email in plain text

cd apps/demo-site
npm install
npm run dev
Demo site: http://localhost:3000

4) Run the deterministic task-suite runner (CLI)
From repo root:

Run the full suite (pricing + refund + contact)
python -m apps.runner.main --site http://localhost:3000
Run a single task
python -m apps.runner.main --site http://localhost:3000 --task pricing
python -m apps.runner.main --site http://localhost:3000 --task refund
python -m apps.runner.main --site http://localhost:3000 --task contact
Tune determinism bounds
python -m apps.runner.main --site https://example.com --max-depth 3 --max-steps 25 --page-timeout 25
The runner prints each StepLog JSON line to stdout and indexes to Elasticsearch.

5) View logs in Kibana Discover
Open Kibana: http://localhost:5601

Go to Stack Management → Data Views

Create these Data Views:

agent_steps-* (time field: ts)

agent_runs-* (time field: ts_start)

Go to Discover and select the Data View you want.

Tip: Filter by run_id to see a full trace.

6) (Optional) Run the API server (FastAPI)
If your Phase-2 repo includes an API (example: apps/api):

cd apps/api
uvicorn main:app --reload --port 8000
Trigger a run:

curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{"site":"http://localhost:3000"}'
Phase 2 (recap): ES|QL queries + dashboards
Phase 2 keeps ES|QL templates under:

queries/esql/

Use them in Kibana (ES|QL) or via your reporting scripts.

Phase 3 — Analyst Agent (FastAPI)
Phase 3 adds a deterministic Analyst Agent that:

routes a question into one of fixed intents,

executes a fixed plan via explicit tool calls,

returns structured JSON + readable markdown,

includes evidence traces (run_id + ordered steps + snippets),

emits audit logs of tool calls into agent_audit-YYYY.MM.DD.

Start the Analyst API
uvicorn apps.analyst.main:app --reload --port 8010
Health:

curl http://localhost:8010/health
Ask:

curl -X POST http://localhost:8010/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Show the top 5 failure hotspots for refund and explain why.",
    "domain": "localhost:3000",
    "time_range": {"relative":"7d"}
  }'
Trace:

curl http://localhost:8010/trace/<RUN_ID>
Streamlit UI (recommended)
streamlit run apps/ui_streamlit/app.py
Phase 3 demo script
This will:

(optionally) start demo-site,

start analyst API,

generate a few runs against the demo site to create Elasticsearch data,

call /ask with 5 questions,

write reports/phase3_demo.md

python scripts/phase3_demo.py
Output:

reports/phase3_demo.md

Evidence format (Phase 3)
Evidence is returned as:

run_id

ordered step list (sorted by step_num)

url, status, fail_reason, latency_ms, and evidence snippet

Notes about determinism
BFS crawl with bounded max_depth and max_steps

Same-domain link-follow only

Ignored schemes: mailto:, tel:, javascript:

Links are sorted lexicographically before enqueue for stable ordering

Cap links enqueued per page (default 40)

Hard timeout per page (default 25s)

Fixed post-load wait (default 1200ms) to allow minimal JS rendering

VS Code
Use the included .vscode/launch.json to debug the runner quickly.


---

### What this fixes
- ✅ Removes all merge conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`)
- ✅ Removes duplicate repeated Phase-1 section
- ✅ Keeps your existing setup steps
- ✅ Adds Phase 3 Analyst Agent + Streamlit + demo report + audit index

If you want, paste your **current repo tree** (just the folder list) and I’ll tailor the README paths exactly to yo