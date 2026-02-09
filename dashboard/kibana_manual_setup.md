# Kibana manual setup (Phase 2)

This project writes Phase-1 traces into Elasticsearch indices:
- `agent_runs-*` (one doc per run)
- `agent_steps-*` (one doc per step)

Phase 2 adds ES|QL queries + a CLI reporter to turn those logs into **metrics + dashboards**.

---

## 0) Generate data (Phase-1 runner)

1) Start Elasticsearch + Kibana:

```bash
docker compose -f infra/docker-compose.yml up -d
