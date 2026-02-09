from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from elasticsearch import Elasticsearch

from apps.runner.es_client import ESClient
from apps.runner.utils import normalize_url, now_iso

from .templates import md_h, md_table, md_codeblock


@dataclass
class Filters:
    site: Optional[str] = None
    domain: Optional[str] = None
    task: str = "all"  # pricing/refund/contact/all
    since: Optional[str] = None  # ISO 8601
    until: Optional[str] = None  # ISO 8601


def _esql(client: Elasticsearch, query: str) -> Dict[str, Any]:
    """Run an ES|QL query via Python client (with REST fallback)."""
    try:
        if hasattr(client, "esql") and hasattr(client.esql, "query"):
            try:
                return client.esql.query(query=query, format="json")  # type: ignore[attr-defined]
            except TypeError:
                return client.esql.query(body={"query": query}, format="json")  # type: ignore[attr-defined]
    except Exception:
        pass

    return client.transport.perform_request(  # type: ignore[no-any-return]
        method="POST",
        path="/_query",
        params={"format": "json"},
        body={"query": query},
    )


def _rows(resp: Dict[str, Any]) -> List[Dict[str, Any]]:
    cols = [c.get("name") for c in (resp.get("columns") or [])]
    values = resp.get("values") or []
    out: List[Dict[str, Any]] = []
    for row in values:
        out.append({cols[i]: row[i] for i in range(min(len(cols), len(row)))})
    return out


def _and(*conds: Optional[str]) -> Optional[str]:
    parts = [c.strip() for c in conds if c and c.strip()]
    return " AND ".join(parts) if parts else None


def _where_clause(conds: Optional[str]) -> str:
    return f"| WHERE {conds}\n" if conds else ""


def _run_filters(f: Filters) -> Optional[str]:
    return _and(
        f'site == "{f.site}"' if f.site else None,
        f'domain == "{f.domain}"' if f.domain else None,
        f'task == "{f.task}"' if f.task and f.task != "all" else None,
        f'ts_start >= "{f.since}"' if f.since else None,
        f'ts_start <= "{f.until}"' if f.until else None,
    )


def _step_filters(f: Filters) -> Optional[str]:
    return _and(
        f'site == "{f.site}"' if f.site else None,
        f'domain == "{f.domain}"' if f.domain else None,
        f'task == "{f.task}"' if f.task and f.task != "all" else None,
        f'ts >= "{f.since}"' if f.since else None,
        f'ts <= "{f.until}"' if f.until else None,
    )


def q_task_success_rate(f: Filters) -> str:
    cond = _run_filters(f)
    return (
        "FROM agent_runs-*\n"
        + _where_clause(cond)
        + "| EVAL success_flag = CASE(success == true, 1, 0)\n"
        + "| STATS total_runs = COUNT(*), success_runs = SUM(success_flag), success_rate_pct = 100 * AVG(success_flag) BY task\n"
        + "| SORT success_rate_pct DESC\n"
    )


def q_failure_reason_distribution(f: Filters) -> str:
    cond = _and(_run_filters(f), "success == false")
    return (
        "FROM agent_runs-*\n"
        + _where_clause(cond)
        + "| STATS failures = COUNT(*) BY final_fail_reason\n"
        + "| SORT failures DESC\n"
    )


def q_top_failing_urls(f: Filters, limit: int = 20) -> str:
    cond = _and(_run_filters(f), "success == false")
    return (
        "FROM agent_runs-*\n"
        + _where_clause(cond)
        + "| STATS failures = COUNT(*), unique_runs = COUNT_DISTINCT(run_id) BY final_url\n"
        + "| SORT failures DESC\n"
        + f"| LIMIT {int(limit)}\n"
    )


def q_example_failed_runs_for_url(f: Filters, url: str, limit: int = 3) -> str:
    cond = _and(_run_filters(f), "success == false", f'final_url == "{url}"')
    return (
        "FROM agent_runs-*\n"
        + _where_clause(cond)
        + "| KEEP ts_start, run_id, task, final_url, final_fail_reason, num_steps\n"
        + "| SORT ts_start DESC\n"
        + f"| LIMIT {int(limit)}\n"
    )


def q_trace_for_run_id(f: Filters, run_id: str, limit: int = 100) -> str:
    cond = _and(_step_filters(f), f'run_id == "{run_id}"')
    return (
        "FROM agent_steps-*\n"
        + _where_clause(cond)
        + "| SORT step_num ASC\n"
        + "| KEEP step_num, url, status, fail_reason, latency_ms\n"
        + f"| LIMIT {int(limit)}\n"
    )


def generate_report(client: Elasticsearch, f: Filters) -> str:
    out = ""
    out += md_h(1, "Agentic Web Observability — Phase 2 Report")
    out += f"Generated: `{now_iso()}`\n\n"

    out += md_h(2, "Filters")
    out += md_codeblock(
        "\n".join(
            [
                f"site:   {f.site or '(any)'}",
                f"domain: {f.domain or '(any)'}",
                f"task:   {f.task}",
                f"since:  {f.since or '(any)'}",
                f"until:  {f.until or '(any)'}",
            ]
        ),
        lang="txt",
    )

    out += md_h(2, "Task success rate")
    rows = _rows(_esql(client, q_task_success_rate(f)))
    out += md_table(rows, ["task", "total_runs", "success_runs", "success_rate_pct"]) + "\n"

    out += md_h(2, "Failure reason distribution")
    rows = _rows(_esql(client, q_failure_reason_distribution(f)))
    out += md_table(rows, ["final_fail_reason", "failures"]) + "\n"

    out += md_h(2, "Top failing URLs")
    top_urls = _rows(_esql(client, q_top_failing_urls(f, limit=15)))
    out += md_table(top_urls, ["final_url", "failures", "unique_runs"]) + "\n"

    out += md_h(2, "Example failure traces")
    if not top_urls:
        out += "_No failures found for the selected filters (or no data ingested yet)._\\n"
        return out

    hotspot_url = str(top_urls[0].get("final_url") or "")
    if not hotspot_url:
        out += "_Could not determine a hotspot URL from data._\\n"
        return out

    out += f"Hotspot URL: `{hotspot_url}`\\n\\n"

    failed_runs = _rows(_esql(client, q_example_failed_runs_for_url(f, hotspot_url, limit=3)))
    if not failed_runs:
        out += "_No failed runs found for the hotspot URL (unexpected)._\\n"
        return out

    for r in failed_runs:
        rid = str(r.get("run_id") or "")
        task = str(r.get("task") or "")
        reason = str(r.get("final_fail_reason") or "")
        out += md_h(3, f"Run `{rid}` — task `{task}` — reason `{reason}`")

        trace_rows = _rows(_esql(client, q_trace_for_run_id(f, rid, limit=100)))
        if not trace_rows:
            out += "_No step logs found for this run_id._\\n\\n"
            continue

        seq = " -> ".join(str(s.get("url") or "") for s in trace_rows)
        out += "Sequence:\\n"
        out += md_codeblock(seq, lang="txt")

        out += "Steps (first 25):\\n"
        out += md_table(trace_rows[:25], ["step_num", "url", "status", "fail_reason", "latency_ms"]) + "\\n"

    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AWOA Phase 2 Reporter (ES-backed)")
    p.add_argument("--site", default=None, help="Filter: site start URL")
    p.add_argument("--domain", default=None, help="Filter: domain (netloc)")
    p.add_argument("--task", default="all", choices=["all", "pricing", "refund", "contact"])
    p.add_argument("--since", default=None, help="Lower bound ISO timestamp")
    p.add_argument("--until", default=None, help="Upper bound ISO timestamp")
    p.add_argument("--out", default="reports/latest_report.md", help="Output markdown path")
    return p.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()

    f = Filters(
        site=normalize_url(args.site) if args.site else None,
        domain=args.domain,
        task=args.task,
        since=args.since,
        until=args.until,
    )

    esw = ESClient.from_env()
    if not esw.client:
        print("Elasticsearch is disabled (ES_ENABLED=0) or not configured.")
        return 2

    client: Elasticsearch = esw.client

    report_md = generate_report(client, f)

    out_path = args.out
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fp:
        fp.write(report_md)

    print(f"Wrote report: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
