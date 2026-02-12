from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from apps.analyst.tools import AnalystTools
from apps.analyst.llm import synthesize_optional

INTENTS = (
    "diagnose_task_failure",
    "list_hotspots",
    "show_example_traces",
    "trend_fail_reasons",
    "compare_before_after",
)


def _infer_task(question: str) -> Optional[str]:
    q = (question or "").lower()
    if "pricing" in q or "price" in q or "plan" in q:
        return "pricing"
    if "refund" in q or "return" in q or "cancellation" in q:
        return "refund"
    if "contact" in q or "email" in q or "support" in q:
        return "contact"
    return None


def _route_intent(question: str) -> str:
    q = (question or "").lower()

    if any(k in q for k in ["trend", "over time", "increasing", "decreasing", "per day", "daily"]):
        return "trend_fail_reasons"
    if any(k in q for k in ["before and after", "compare", "before", "after"]):
        return "compare_before_after"
    if any(k in q for k in ["trace", "example trace", "show traces", "run_id", "examples"]):
        return "show_example_traces"
    if any(k in q for k in ["hotspot", "hotspots", "top failing", "worst pages", "failure hotspot"]):
        return "list_hotspots"

    return "diagnose_task_failure"


def _md_table(rows: List[Dict[str, Any]], columns: List[str], max_rows: int = 20) -> str:
    if not rows:
        return "_(no rows)_\n"
    cols = columns[:]
    out = []
    out.append("| " + " | ".join(cols) + " |")
    out.append("| " + " | ".join(["---"] * len(cols)) + " |")
    for r in rows[:max_rows]:
        out.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    if len(rows) > max_rows:
        out.append(f"\n_(showing {max_rows} of {len(rows)})_\n")
    return "\n".join(out) + "\n"


@dataclass
class AskInput:
    question: str
    site: Optional[str] = None
    domain: Optional[str] = None
    task: Optional[str] = None
    time_range: Optional[Dict[str, Any]] = None  # {start,end} or {relative:"7d"}


class AnalystAgent:
    def __init__(self, tools: AnalystTools):
        self.tools = tools

    def _build_time_params(self, time_range: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not time_range:
            return {"relative": "7d"}  # deterministic default
        if isinstance(time_range, dict):
            if "relative" in time_range:
                return {"relative": str(time_range["relative"])}
            return {
                "start": time_range.get("start"),
                "end": time_range.get("end"),
                "relative": time_range.get("relative"),
            }
        return {"relative": "7d"}

    def _plan(self, intent: str, inp: AskInput) -> List[Dict[str, Any]]:
        t = inp.task or _infer_task(inp.question)
        time_p = self._build_time_params(inp.time_range)

        if intent == "list_hotspots":
            return [
                {"tool": "tool_hotspots", "params": {"domain": inp.domain, "task": t, **time_p, "limit": 20}},
            ]

        if intent == "show_example_traces":
            return [
                {"tool": "tool_search_steps", "params": {"domain": inp.domain, "task": t, "status": "fail", "limit": 200}},
                {"tool": "tool_get_trace", "params": {"_pick_from_search": 3}},
            ]

        if intent == "trend_fail_reasons":
            return [
                {
                    "tool": "tool_esql",
                    "params": {
                        "query_name": "fail_reason_trends_daily",
                        "domain": inp.domain,
                        "task": t,
                        **time_p,
                        "limit": 500,
                    },
                }
            ]

        if intent == "compare_before_after":
            tr = inp.time_range or {}
            before = tr.get("before") or {"relative": "14d"}
            after = tr.get("after") or {"relative": "7d"}
            return [
                {
                    "tool": "tool_esql",
                    "params": {
                        "query_name": "fail_reason_trends_daily",
                        "domain": inp.domain,
                        "task": t,
                        **before,
                        "limit": 500,
                        "_label": "before",
                    },
                },
                {
                    "tool": "tool_esql",
                    "params": {
                        "query_name": "fail_reason_trends_daily",
                        "domain": inp.domain,
                        "task": t,
                        **after,
                        "limit": 500,
                        "_label": "after",
                    },
                },
            ]

        return [
            {"tool": "tool_hotspots", "params": {"domain": inp.domain, "task": t, **time_p, "limit": 20}},
            {"tool": "tool_search_steps", "params": {"domain": inp.domain, "task": t, "status": "fail", "limit": 300}},
            {"tool": "tool_get_trace", "params": {"_pick_from_search": 3}},
        ]

    def _execute_plan(self, analyst_run_id: str, question: str, plan: List[Dict[str, Any]]) -> Dict[str, Any]:
        ctx: Dict[str, Any] = {"plan": plan, "results": {}}
        search_hits: List[Dict[str, Any]] = []

        def _q(s: str) -> str:
            # Quote for ES|QL string literal deterministically
            return str(s).replace('"', '\\"')

        for step in plan:
            tool = step["tool"]
            params = dict(step.get("params") or {})

            t0 = time.time()
            if tool == "tool_esql":
                qn = params.pop("query_name")
                domain = params.pop("domain", None)
                task = params.pop("task", None)
                start = params.pop("start", None)
                end = params.pop("end", None)
                relative = params.pop("relative", None)

                from apps.analyst.queries import esql_time_filter

                esql_params = {
                    "steps_index": "agent_steps-*",
                    "domain_filter": "TRUE" if not domain else f'domain == "{_q(domain)}"',
                    "task_filter": "TRUE" if not task else f'task == "{_q(task)}"',
                    "time_filter": esql_time_filter("ts", start_iso=start, end_iso=end, relative=relative),
                    "limit": int(params.pop("limit", 500)),
                }

                res = self.tools.tool_esql(qn, esql_params).data
                label = step.get("params", {}).get("_label") or qn
                ctx["results"][label] = res

            elif tool == "tool_hotspots":
                res = self.tools.tool_hotspots(params).data
                ctx["results"]["hotspots"] = res

            elif tool == "tool_search_steps":
                res = self.tools.tool_search_steps(params).data
                search_hits = res
                ctx["results"]["search_steps"] = res

            elif tool == "tool_get_trace":
                n = int(params.get("_pick_from_search", 3))
                run_ids: List[str] = []
                for h in search_hits:
                    rid = h.get("run_id")
                    if rid and rid not in run_ids:
                        run_ids.append(rid)
                    if len(run_ids) >= n:
                        break

                traces = []
                for rid in run_ids:
                    tr = self.tools.tool_get_trace(rid).data
                    traces.append({"run_id": rid, "trace": tr})

                ctx["results"]["example_traces"] = traces
                res = traces

            else:
                raise ValueError(f"Unknown tool: {tool}")

            dur = int((time.time() - t0) * 1000)
            self.tools.audit.log_tool_call(
                analyst_run_id=analyst_run_id,
                question=question,
                tool_name=tool,
                tool_params=step.get("params") or {},
                tool_result=res,
                duration_ms=dur,
            )

        return ctx

    def _failure_profile(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        hotspots = ctx["results"].get("hotspots") or []
        traces = ctx["results"].get("example_traces") or []

        reason_counts: Dict[str, int] = {}
        for row in hotspots:
            fr = row.get("fail_reason") or "unknown"
            fails = int(row.get("fails", 0) or 0)
            reason_counts[fr] = reason_counts.get(fr, 0) + fails

        top_fail_reasons = [{"fail_reason": k, "fails": v} for k, v in reason_counts.items()]
        top_fail_reasons = sorted(top_fail_reasons, key=lambda x: int(x["fails"]), reverse=True)[:5]

        return {
            "top_fail_reasons": top_fail_reasons,
            "hotspots": hotspots,
            "example_traces": traces,
        }

    def _build_markdown(
        self,
        analyst_run_id: str,
        intent: str,
        inp: AskInput,
        ctx: Dict[str, Any],
        fixes: List[Dict[str, Any]],
    ) -> str:
        md = []
        md.append("# AWOA Analyst Agent — Phase 3\n")
        md.append(f"**analyst_run_id:** `{analyst_run_id}`  \n")
        md.append(f"**intent:** `{intent}`  \n")
        if inp.domain:
            md.append(f"**domain:** `{inp.domain}`  \n")
        if inp.task:
            md.append(f"**task:** `{inp.task}`  \n")
        md.append(f"\n## Question\n{inp.question}\n")

        md.append("\n## Plan\n")
        for i, p in enumerate(ctx["plan"], 1):
            md.append(f"{i}. `{p['tool']}` — `{p.get('params', {})}`")
        md.append("")

        md.append("\n## Metrics\n")
        if "hotspots" in ctx["results"]:
            rows = ctx["results"]["hotspots"]
            md.append("### Top failure hotspots\n")
            md.append(_md_table(rows, ["task", "url", "fail_reason", "fails", "avg_latency"], max_rows=10))

        if "fail_reason_trends_daily" in ctx["results"]:
            rows = ctx["results"]["fail_reason_trends_daily"]["rows"]
            md.append("### Fail reason trends (daily)\n")
            md.append(_md_table(rows, ["day", "task", "fail_reason", "fails"], max_rows=20))

        md.append("\n## Evidence (example traces)\n")
        traces = ctx["results"].get("example_traces") or []
        if not traces:
            md.append("_(no traces found)_\n")
        else:
            for t in traces[:3]:
                rid = t.get("run_id")
                md.append(f"### run_id: `{rid}`\n")
                tr = t.get("trace") or []
                for s in tr[:12]:
                    md.append(
                        f"- step {s.get('step_num')}: {s.get('status')} "
                        f"({s.get('fail_reason')}) — {s.get('url')} "
                        f"[{s.get('latency_ms')}ms] — evidence: `{s.get('evidence','')}`"
                    )
                if len(tr) > 12:
                    md.append(f"_(showing 12 of {len(tr)})_\n")

        md.append("\n## Recommended fixes (ranked)\n")
        if not fixes:
            md.append("_(no fixes generated)_\n")
        else:
            for i, fx in enumerate(fixes[:5], 1):
                md.append(f"### {i}) {fx['title']}  ")
                md.append(f"- **confidence:** `{fx['confidence']}`  ")
                md.append(f"- **mapped_fail_reason:** `{fx.get('mapped_fail_reason')}`  ")
                md.append(f"- **why:** {fx['why']}  ")
                sup = fx.get("support", {})
                md.append(
                    f"- **evidence:** fails={sup.get('fails')}, "
                    f"traces={sup.get('trace_run_ids')}, "
                    f"hotspots={sup.get('hotspot_urls')}\n"
                )

        return "\n".join(md).strip() + "\n"

    def ask(self, inp: AskInput) -> Dict[str, Any]:
        analyst_run_id = uuid.uuid4().hex
        intent = _route_intent(inp.question)
        if intent not in INTENTS:
            intent = "diagnose_task_failure"

        inp.task = inp.task or _infer_task(inp.question)

        plan = self._plan(intent, inp)
        ctx = self._execute_plan(analyst_run_id, inp.question, plan)

        profile = self._failure_profile(ctx)
        fixes = self.tools.tool_recommend_fixes(profile).data

        diagnosis = {
            "summary": "Deterministic diagnosis based on hotspots + traces. See evidence and metrics below.",
            "top_fail_reasons": profile.get("top_fail_reasons", []),
        }

        markdown = self._build_markdown(analyst_run_id, intent, inp, ctx, fixes)
        markdown_final = synthesize_optional({"markdown": markdown, "llm_prompt": markdown})

        return {
            "analyst_run_id": analyst_run_id,
            "intent": intent,
            "plan": plan,
            "diagnosis": diagnosis,
            "metrics": ctx["results"],
            "evidence": {"example_traces": ctx["results"].get("example_traces") or []},
            "recommended_fixes": fixes,
            "markdown": markdown_final,
        }
