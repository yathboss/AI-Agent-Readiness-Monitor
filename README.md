
# AI-Agent-Readiness-Monitor

Measure how reliably AI agents can find pricing, refunds, and contact info on websites using deterministic runs, traces, and Elasticsearch dashboards.

---

# Agentic Web Observability Analyzer — Phase 1

Phase 1 is a **deterministic browser task-suite runner** that visits a website (bounded BFS crawl) and checks whether an AI agent can reliably find:

1) **Pricing**
2) **Refund/Return policy**
3) **Contact method** (email or a contact page)

Every step is logged as **structured JSON** and indexed into **Elasticsearch** daily indices:

- `agent_steps-YYYY.MM.DD`
- `agent_runs-YYYY.MM.DD`

> **Ethics / safety:** This tool is for observability and QA. **Do not bypass bot protections** or access controls. Only test websites you own or have explicit permission to test.

---

=======
# Agentic Web Observability Analyzer — Phase 1

Phase 1 is a **deterministic browser task-suite runner** that visits a website (bounded BFS crawl) and checks whether an AI agent can reliably find:

1) **Pricing**
2) **Refund/Return policy**
3) **Contact method** (email or a contact page)

Every step is logged as **structured JSON** and indexed into **Elasticsearch** daily indices:

- `agent_steps-YYYY.MM.DD`
- `agent_runs-YYYY.MM.DD`

> **Ethics / safety:** This tool is for observability and QA. **Do not bypass bot protections** or access controls. Only test websites you own or have explicit permission to test.

---

## 1) Start Elasticsearch + Kibana (dev mode)

Requirements: **Docker Desktop**

```bash
cd infra
docker compose up -d
```

- Elasticsearch: http://localhost:9200
- Kibana: http://localhost:5601

Security is disabled for local development.

---

## 2) Python environment setup (VS Code friendly)

Requirements: **Python 3.11+**

```bash
# from repo root
python -m venv .venv
# Windows:
#   .venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
python -m playwright install chromium
```

Create your env file:

```bash
cp .env.example .env
```

---

## 3) (Optional) Run the demo site (Next.js)

The demo site includes some intentionally “agent-hostile” patterns:
- `/pricing` renders pricing **after a JS delay** + large inline script (can trigger `js_only`)
- `/refund` provides policy only as a **PDF link**
- `/contact` includes an **email in plain text**

```bash
cd apps/demo-site
npm install
npm run dev
```

Demo site: http://localhost:3000

---

## 4) Run the deterministic task-suite runner (CLI)

From repo root:

### Run the full suite (pricing + refund + contact)

```bash
python -m apps.runner.main --site http://localhost:3000
```

### Run a single task

```bash
python -m apps.runner.main --site http://localhost:3000 --task pricing
python -m apps.runner.main --site http://localhost:3000 --task refund
python -m apps.runner.main --site http://localhost:3000 --task contact
```

### Tune determinism bounds

```bash
python -m apps.runner.main --site https://example.com --max-depth 3 --max-steps 25 --page-timeout 25
```

The runner prints each **StepLog** JSON line to stdout and indexes to Elasticsearch.

---

## 5) View logs in Kibana Discover

1. Open Kibana: http://localhost:5601
2. Go to **Stack Management → Data Views**
3. Create these Data Views:
   - `agent_steps-*` (time field: `ts`)
   - `agent_runs-*`  (time field: `ts_start`)
4. Go to **Discover** and select the Data View you want.

Tip: Filter by `run_id` to see a full trace.

---

## 6) (Optional) Run the API server (FastAPI)

```bash
cd apps/api
uvicorn main:app --reload --port 8000
```

Trigger a run:

```bash
curl -X POST http://localhost:8000/run -H "Content-Type: application/json" -d '{"site":"http://localhost:3000"}'
```

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

## Notes about determinism

- BFS crawl with bounded `max_depth` and `max_steps`
- Same-domain link-follow only
- Ignored schemes: `mailto:`, `tel:`, `javascript:`
- Links are **sorted lexicographically** before enqueue for stable ordering
- Cap links enqueued per page (default 40)
- Hard timeout per page (default 25s)
- Fixed post-load wait (default 1200ms) to allow minimal JS rendering

---

## VS Code

- Use the included `.vscode/launch.json` to debug the runner quickly.
>>>>>>> df748eb (Phase 2: baseline runner + ES|QL + dashboards + reporter)
