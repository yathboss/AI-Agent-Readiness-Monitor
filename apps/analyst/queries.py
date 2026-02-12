from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def _repo_root() -> Path:
    # apps/analyst/queries.py -> repo root is two parents up from apps/
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class RenderedQuery:
    name: str
    text: str
    params: Dict[str, Any]


class ESQLTemplateLoader:
    """
    Loads ES|QL templates from queries/esql/*.esql
    and performs deterministic {{param}} substitution.
    """
    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or (_repo_root() / "queries" / "esql")

    def load_template(self, query_name: str) -> str:
        path = self.base_dir / f"{query_name}.esql"
        if not path.exists():
            raise FileNotFoundError(f"ES|QL template not found: {path}")
        return path.read_text(encoding="utf-8")

    def render(self, query_name: str, params: Dict[str, Any]) -> RenderedQuery:
        template = self.load_template(query_name)

        def repl(match: re.Match) -> str:
            key = match.group(1)
            if key not in params:
                raise KeyError(f"Missing template param: {key}")
            v = params[key]
            return str(v)

        rendered = _PLACEHOLDER_RE.sub(repl, template)

        # fail fast if any placeholders remain
        leftovers = _PLACEHOLDER_RE.findall(rendered)
        if leftovers:
            raise ValueError(f"Unresolved placeholders in {query_name}: {sorted(set(leftovers))}")

        return RenderedQuery(name=query_name, text=rendered, params=params)


def esql_bool_filter(field: str, value: Optional[str]) -> str:
    """
    Returns a boolean expression string for ES|QL WHERE clause.
    If value is None/empty -> TRUE
    """
    if not value:
        return "TRUE"
    # Quote value safely for ES|QL string literal
    safe = str(value).replace('"', '\\"')
    return f'{field} == "{safe}"'


def esql_time_filter(
    ts_field: str,
    *,
    start_iso: Optional[str] = None,
    end_iso: Optional[str] = None,
    relative: Optional[str] = None,
) -> str:
    """
    Returns an ES|QL boolean expression string for time filtering.

    Supported:
      - relative: "7d", "24h", "30d" -> ts >= NOW() - 7 day / 24 hour
      - start/end iso: ts >= TO_DATETIME("...") AND ts < TO_DATETIME("...")

    If no time supplied -> TRUE
    """
    if relative:
        rel = relative.strip().lower()
        # deterministic mapping
        if rel.endswith("d"):
            n = int(rel[:-1])
            return f"{ts_field} >= NOW() - {n} day"
        if rel.endswith("h"):
            n = int(rel[:-1])
            return f"{ts_field} >= NOW() - {n} hour"
        if rel.endswith("m"):
            n = int(rel[:-1])
            return f"{ts_field} >= NOW() - {n} minute"
        # fallback: keep raw (user-provided) expression
        return f"{ts_field} >= NOW() - {rel}"

    if start_iso and end_iso:
        s = start_iso.replace('"', '\\"')
        e = end_iso.replace('"', '\\"')
        # Many installs map ts as a date; TO_DATETIME is accepted in modern ES|QL.
        return f'{ts_field} >= TO_DATETIME("{s}") AND {ts_field} < TO_DATETIME("{e}")'

    if start_iso and not end_iso:
        s = start_iso.replace('"', '\\"')
        return f'{ts_field} >= TO_DATETIME("{s}")'

    if end_iso and not start_iso:
        e = end_iso.replace('"', '\\"')
        return f'{ts_field} < TO_DATETIME("{e}")'

    return "TRUE"


def esql_limit(n: Optional[int], default: int = 20, max_n: int = 200) -> int:
    if n is None:
        return default
    n = int(n)
    return max(1, min(max_n, n))
