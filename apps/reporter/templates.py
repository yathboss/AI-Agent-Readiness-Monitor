from __future__ import annotations

from typing import Any, Dict, Sequence


def md_h(level: int, title: str) -> str:
    level = max(1, min(6, level))
    return f"{'#' * level} {title}\n"


def _cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.2f}"
    s = str(v)
    s = s.replace("\n", " ").replace("|", "\\|")
    return s


def md_table(rows: Sequence[Dict[str, Any]], columns: Sequence[str]) -> str:
    """Render a GitHub-flavored markdown table."""
    if not rows:
        return "_No data._\n"

    header = "| " + " | ".join(columns) + " |\n"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |\n"
    body = ""
    for r in rows:
        body += "| " + " | ".join(_cell(r.get(c)) for c in columns) + " |\n"
    return header + sep + body


def md_codeblock(text: str, lang: str = "") -> str:
    return f"```{lang}\n{text.rstrip()}\n```\n"
