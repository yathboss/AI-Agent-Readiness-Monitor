from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from apps.runner.es_client import ESClient
from apps.analyst.audit import AuditLogger
from apps.analyst.queries import (
    ESQLTemplateLoader,
    esql_bool_filter,
    esql_limit,
    esql_time_filter,
)
from apps.analyst.fix_rules import fixes_for_reason


def _esql_query(es: ESClient, query_text: str) -> Dict[str, Any]:
    """
    Execute ES|QL query using the python client.
    Tries multiple call styles for compatibility.
    """
    if not es.client:
        return {"columns": [], "values": []}

    client = es.client
    # 1) Native helper if present
    if hasattr(client, "esql") and hasattr(client.esql, "query"):
        return client.esql.query(query=query_text)

    # 2) Transport fallback
    return client.transport.perform_request(
        method="POST",
        path="/_query",
        body={"query": query_text},
    )


def _esql_rows(resp: Dict[str, Any]) -> List[Dict[str, Any]]:
    cols = [c.get("name") for c in resp.get("columns", [])]
    rows = []
    for vals in resp.get("values", []) or []:
        row = {}
        for i, name in enumerate(cols):
            row[name] = vals[i] if i < len(vals) else None
        rows.append(row)
    return rows


@dataclass
class ToolResult:
    name: str
    params: Dict[str, Any]
    data: Any


@dataclass
class AnalystTools:
    es: ESClient
    loader: ESQLTemplateLoader
    audit: AuditLogger

    # 1) tool_esql(query_name, params)
    def tool_esql(self, query_name: str, params: Dict[str, Any]) -> ToolResult:
        rendered = self.loader.render(query_name, params)
        resp = _esql_query(self.es, rendered.text)
        rows = _esql_rows(resp)
        return ToolResult(name=f"tool_esql:{query_name}", params=params, data={"rows": rows, "raw": resp})

    # 2) tool_search_steps(filters)
    def tool_search_steps(self, filters: Dict[str, Any]) -> ToolResult:
        """
        Query step documents deterministically.
        Filters:
          - run_id (str) OR run_ids (list)
          - task (str)
          - domain (str)
          - site (str)
          - url_contains (str)
          - status ("ok"|"fail")
          - fail_reason (str)
          - limit (int)
        """
        if not self.es.client:
            return ToolResult(name="tool_search_steps", params=filters, data=[])

        limit = int(filters.get("limit") or 50)
        limit = max(1, min(500, limit))

        must = []
        if filters.get("run_id"):
            must.append({"term": {"run_id": filters["run_id"]}})
        if filters.get("run_ids"):
            must.append({"terms": {"run_id": filters["run_ids"]}})
        if filters.get("task"):
            must.append({"term": {"task": filters["task"]}})
        if filters.get("domain"):
            must.append({"term": {"domain": filters["domain"]}})
        if filters.get("site"):
            must.append({"term": {"site": filters["site"]}})
        if filters.get("status"):
            must.append({"term": {"status": filters["status"]}})
        if filters.get("fail_reason"):
            must.append({"term": {"fail_reason": filters["fail_reason"]}})
        if filters.get("url_contains"):
            must.append({"wildcard": {"url": f"*{filters['url_contains']}*"}})

        query = {"bool": {"must": must}} if must else {"match_all": {}}

        resp = self.es.client.search(
            index="agent_steps-*",
            size=limit,
            query=query,
            sort=[{"run_id": "asc"}, {"step_num": "asc"}],
            _source=True,
        )
        hits = [h["_source"] for h in resp.get("hits", {}).get("hits", [])]
        return ToolResult(name="tool_search_steps", params=filters, data=hits)

    # 3) tool_get_trace(run_id)
    def tool_get_trace(self, run_id: str) -> ToolResult:
        steps = self.tool_search_steps({"run_id": run_id, "limit": 500}).data
        # Ensure deterministic ordering
        steps = sorted(steps, key=lambda d: int(d.get("step_num", 0)))
        trace = []
        for s in steps:
            trace.append(
                {
                    "step_num": s.get("step_num"),
                    "ts": s.get("ts"),
                    "task": s.get("task"),
                    "url": s.get("url"),
                    "status": s.get("status"),
                    "fail_reason": s.get("fail_reason"),
                    "latency_ms": s.get("latency_ms"),
                    "http_status": s.get("http_status"),
                    "page_title": s.get("page_title", ""),
                    "evidence": (s.get("evidence") or "")[:300],
                }
            )
        return ToolResult(name="tool_get_trace", params={"run_id": run_id}, data=trace)

    # 4) tool_hotspots(params)
    def tool_hotspots(self, params: Dict[str, Any]) -> ToolResult:
        """
        Returns top failing URLs with failure counts (and optional latency).
        Prefers ES|QL query; deterministic fallback to aggregations if ES|QL fails.
        """
        domain = params.get("domain")
        task = params.get("task")
        start = params.get("start")
        end = params.get("end")
        relative = params.get("relative") or params.get("time_range")
        limit = esql_limit(params.get("limit"), default=20, max_n=200)

        esql_params = {
            "steps_index": "agent_steps-*",
            "domain_filter": esql_bool_filter("domain", domain),
            "task_filter": esql_bool_filter("task", task),
            "time_filter": esql_time_filter("ts", start_iso=start, end_iso=end, relative=relative),
            "limit": limit,
        }

        try:
            tr = self.tool_esql("fail_hotspots_by_task", esql_params).data["rows"]
            return ToolResult(name="tool_hotspots", params=params, data=tr)
        except Exception:
            # Fallback: ES aggregations
            if not self.es.client:
                return ToolResult(name="tool_hotspots", params=params, data=[])

            must = [{"term": {"status": "fail"}}]
            if domain:
                must.append({"term": {"domain": domain}})
            if task:
                must.append({"term": {"task": task}})

            resp = self.es.client.search(
                index="agent_steps-*",
                size=0,
                query={"bool": {"must": must}},
                aggs={
                    "by_url": {
                        "terms": {"field": "url.keyword", "size": limit, "order": {"_count": "desc"}},
                        "aggs": {
                            "by_reason": {"terms": {"field": "fail_reason.keyword", "size": 5}},
                            "avg_latency": {"avg": {"field": "latency_ms"}},
                        },
                    }
                },
            )
            buckets = resp.get("aggregations", {}).get("by_url", {}).get("buckets", [])
            rows = []
            for b in buckets:
                rows.append(
                    {
                        "url": b.get("key"),
                        "fails": b.get("doc_count"),
                        "avg_latency": int((b.get("avg_latency", {}).get("value") or 0)),
                        "top_reasons": [
                            {"fail_reason": r.get("key"), "fails": r.get("doc_count")}
                            for r in b.get("by_reason", {}).get("buckets", [])
                        ],
                    }
                )
            return ToolResult(name="tool_hotspots", params=params, data=rows)

    # 5) tool_recommend_fixes(failure_profile)
    def tool_recommend_fixes(self, failure_profile: Dict[str, Any]) -> ToolResult:
        """
        Rule-based deterministic recommendations.
        Expects:
          - top_fail_reasons: [{fail_reason, fails}]
          - example_traces: [{run_id, ...}]
          - hotspots: [{url, fails, ...}]
        """
        top = failure_profile.get("top_fail_reasons") or []
        hotspots = failure_profile.get("hotspots") or []
        traces = failure_profile.get("example_traces") or []

        recs = []
        # deterministic order: by failures desc
        for item in sorted(top, key=lambda x: int(x.get("fails", 0)), reverse=True):
            reason = item.get("fail_reason")
            fails = int(item.get("fails", 0))
            for fx in fixes_for_reason(reason):
                recs.append(
                    {
                        "fix_id": fx.id,
                        "title": fx.title,
                        "why": fx.why,
                        "confidence": fx.confidence,
                        "mapped_fail_reason": reason,
                        "support": {
                            "fails": fails,
                            "hotspot_urls": [h.get("url") for h in hotspots[:3] if isinstance(h, dict)],
                            "trace_run_ids": [t.get("run_id") for t in traces[:3] if isinstance(t, dict)],
                        },
                    }
                )

        # remove duplicates by fix_id (keep first = highest priority)
        seen = set()
        uniq = []
        for r in recs:
            if r["fix_id"] in seen:
                continue
            seen.add(r["fix_id"])
            uniq.append(r)

        return ToolResult(name="tool_recommend_fixes", params={"profile_keys": sorted(list(failure_profile.keys()))}, data=uniq)
