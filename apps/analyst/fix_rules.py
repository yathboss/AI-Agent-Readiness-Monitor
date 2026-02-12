from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class Fix:
    id: str
    title: str
    why: str
    confidence: str  # low | med | high


# Rule-based mapping from failure taxonomy -> recommended fixes.
# Deterministic by design.
FIX_RULES: Dict[str, List[Fix]] = {
    "not_found": [
        Fix(
            id="nf_nav_links",
            title="Add clear top-nav + footer links to the target page",
            why="Agent cannot find the target information; adding obvious 'Pricing/Refund/Contact' links reduces search entropy.",
            confidence="high",
        ),
        Fix(
            id="nf_sitemap",
            title="Expose a sitemap and consistent URL structure",
            why="Improves discoverability and reduces BFS crawl misses.",
            confidence="med",
        ),
        Fix(
            id="nf_onpage_keywords",
            title="Ensure the page includes explicit keywords (e.g., 'Pricing', 'Refund Policy') in visible text",
            why="Heuristic extractors and human users rely on visible keywords.",
            confidence="high",
        ),
    ],
    "hard_to_find": [
        Fix(
            id="htf_above_fold",
            title="Move key info above the fold and reduce multi-click depth",
            why="Signals exist but are too weak/deep; restructuring improves findability and reduces max_steps failures.",
            confidence="high",
        ),
        Fix(
            id="htf_anchor_text",
            title="Use unambiguous anchor text for links",
            why="Avoid generic labels like 'Learn more' for critical pages; label as 'Pricing', 'Refund Policy', 'Contact'.",
            confidence="high",
        ),
    ],
    "js_only": [
        Fix(
            id="js_ssr",
            title="Server-render critical content (SSR/SSG) instead of delayed JS-only rendering",
            why="If visible text appears only after heavy JS/delays, the agent may classify it as JS-only and fail extraction.",
            confidence="high",
        ),
        Fix(
            id="js_noscript",
            title="Provide <noscript> fallback or minimal HTML fallback",
            why="Ensures essential info exists even if scripts are blocked or timeouts occur.",
            confidence="med",
        ),
        Fix(
            id="js_reduce_payload",
            title="Reduce initial HTML/script bloat and speed up first contentful paint",
            why="Large payload + little visible text often triggers JS-only heuristics and timeouts.",
            confidence="med",
        ),
    ],
    "non_text": [
        Fix(
            id="nt_html_version",
            title="Provide an HTML page version of the policy (not only PDF/image)",
            why="Non-text pages are hard for deterministic extraction; HTML improves accessibility and search.",
            confidence="high",
        ),
        Fix(
            id="nt_link_label",
            title="Label downloads clearly (e.g., 'Refund Policy (PDF)')",
            why="If link text avoids key terms, the agent may miss it even if the PDF exists.",
            confidence="med",
        ),
    ],
    "ambiguous": [
        Fix(
            id="amb_disambiguate",
            title="Disambiguate multiple similar links and headings",
            why="Ambiguity causes wrong-path exploration; clearer IA reduces errors.",
            confidence="med",
        ),
        Fix(
            id="amb_single_source",
            title="Consolidate canonical pages for Pricing/Refund/Contact",
            why="Multiple scattered references lead to inconsistent extraction and confusion.",
            confidence="med",
        ),
    ],
    "blocked": [
        Fix(
            id="blk_allowlist",
            title="Allowlist test environment / disable bot protections for permitted QA runs",
            why="Observability tools should not bypass protections; instead test on controlled environments.",
            confidence="high",
        ),
        Fix(
            id="blk_robots_test",
            title="Expose a QA-friendly endpoint or staging domain for agent testing",
            why="Keeps production protections intact while enabling deterministic testing.",
            confidence="high",
        ),
    ],
    "timeout": [
        Fix(
            id="to_perf",
            title="Improve page performance (reduce JS, images, third-party scripts)",
            why="Timeout failures often correlate with slow render/network and heavy client work.",
            confidence="high",
        ),
        Fix(
            id="to_critical_content_fast",
            title="Render key info quickly (reduce delay; avoid late hydration for essential text)",
            why="Even if content eventually appears, delayed rendering causes timeouts and missing evidence.",
            confidence="high",
        ),
    ],
    "requires_login": [
        Fix(
            id="rl_public_info",
            title="Expose public Pricing/Refund/Contact info without requiring login",
            why="Agent cannot access gated content by design; provide public pages for these basics.",
            confidence="high",
        ),
    ],
    "unknown": [
        Fix(
            id="unk_instrument",
            title="Improve observability: log clearer failure notes + add page hints",
            why="Unknown buckets usually mean insufficient evidence; better instrumentation improves diagnosis.",
            confidence="low",
        ),
    ],
}


def fixes_for_reason(reason: Optional[str]) -> List[Fix]:
    if not reason:
        return []
    return FIX_RULES.get(reason, FIX_RULES.get("unknown", []))
