from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from apps.runner.es_client import ESClient


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _audit_index_name(ts: Optional[datetime] = None) -> str:
    ts = ts or datetime.now(timezone.utc)
    return ts.strftime("agent_audit-%Y.%m.%d")


def _summarize_result(obj: Any, max_len: int = 320) -> str:
    """
    Keep it small: no full dumps.
    Deterministic summary for audit logs.
    """
    try:
        if obj is None:
            return "null"
        if isinstance(obj, (str, int, float, bool)):
            s = str(obj)
            return s[:max_len]
        if isinstance(obj, list):
            if not obj:
                return "list(len=0)"
            head = obj[0]
            return f"list(len={len(obj)}), head_keys={sorted(list(head.keys())) if isinstance(head, dict) else type(head).__name__}"
        if isinstance(obj, dict):
            keys = sorted(list(obj.keys()))
            # If it's an ES|QL-like response with columns/values
            if "columns" in obj and "values" in obj:
                cols = [c.get("name") for c in obj.get("columns", [])][:10]
                return f"esql(columns={cols}, rows={len(obj.get('values', []))})"
            return f"dict(keys={keys[:20]})"
        return f"type={type(obj).__name__}"
    except Exception:
        return "summary_error"


@dataclass
class AuditLogger:
    es: ESClient

    def log_tool_call(
        self,
        *,
        analyst_run_id: str,
        question: str,
        tool_name: str,
        tool_params: Dict[str, Any],
        tool_result: Any,
        duration_ms: int,
    ) -> None:
        idx = _audit_index_name()
        doc = {
            "analyst_run_id": analyst_run_id,
            "ts": _utc_now_iso(),
            "question": question,
            "tool_name": tool_name,
            "tool_params": tool_params,
            "tool_result_summary": _summarize_result(tool_result),
            "duration_ms": int(duration_ms),
        }
        self.es.index(idx, doc)
