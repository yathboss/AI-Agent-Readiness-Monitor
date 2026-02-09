from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional, Set, Tuple

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from .es_client import ESClient
from .schemas import FailureReason, RunSummary, StepLog, StepStatus
from .tasks import extract_contact, extract_pricing, extract_refund, keyword_signal_for_task
from .utils import (
    detect_js_only,
    detect_non_text,
    detect_requires_login,
    extract_links,
    normalize_url,
    now_iso,
    score,
    visible_text_from_html,
)


@dataclass
class CrawlConfig:
    max_depth: int = 3
    max_steps: int = 25
    page_timeout_s: int = 25
    enqueue_cap: int = 40
    post_load_wait_ms: int = 1200


def daily_index(prefix: str) -> str:
    import datetime
    d = datetime.datetime.utcnow().strftime("%Y.%m.%d")
    return f"{prefix}-{d}"


def classify_fail_reason(task: str, http_status: int, html_len: int, text_len: int, text_lower: str, keyword_signal: int) -> FailureReason:
    # deterministic ordering of checks
    if http_status in (401, 403, 429):
        return FailureReason.blocked
    if http_status >= 500:
        return FailureReason.timeout
    if http_status == 404:
        return FailureReason.not_found
    if detect_requires_login(text_lower):
        return FailureReason.requires_login
    if detect_non_text("", text_len):  # placeholder; real check handled before this for better accuracy
        return FailureReason.non_text
    if detect_js_only(html_len, text_len):
        return FailureReason.js_only
    # choose between hard_to_find / not_found based on keyword signal
    if keyword_signal > 0:
        return FailureReason.hard_to_find
    return FailureReason.not_found


def extract_for_task(task: str, text: str, links: List[str]):
    if task == "pricing":
        return extract_pricing(text)
    if task == "refund":
        return extract_refund(text, links)
    if task == "contact":
        return extract_contact(text, links)
    raise ValueError(f"Unknown task: {task}")


def run_task(site: str, task: str, cfg: CrawlConfig, es: ESClient) -> RunSummary:
    start_ts = now_iso()
    run_id = f"{uuid.uuid4().hex[:10]}-{task}"
    domain = __domain(site)

    visited: Set[str] = set()
    q: Deque[Tuple[str, int]] = deque()
    q.append((normalize_url(site), 0))

    steps: List[StepLog] = []
    step_num = 0
    success = False
    final_url = normalize_url(site)
    final_fail: Optional[FailureReason] = None
    notes = ""
    num_retries = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="AWOA-Runner/1.0 (deterministic)",
            locale="en-US",
        )
        try:
            while q and step_num < cfg.max_steps:
                url, depth = q.popleft()
                if url in visited:
                    continue
                visited.add(url)
                step_num += 1
                final_url = url

                t0 = time.perf_counter()
                page = context.new_page()
                http_status = 0
                page_title = ""
                html = ""
                text = ""
                links: List[str] = []
                extracted_keys: List[str] = []
                missing_keys: List[str] = []
                evidence = ""
                status = StepStatus.fail
                fail_reason: Optional[FailureReason] = None

                try:
                    resp = page.goto(url, wait_until="domcontentloaded", timeout=cfg.page_timeout_s * 1000)
                    if resp is not None:
                        http_status = resp.status
                    # fixed wait for minimal JS rendering (deterministic)
                    if cfg.post_load_wait_ms > 0:
                        page.wait_for_timeout(cfg.post_load_wait_ms)

                    page_title = page.title() or ""
                    html = page.content() or ""

                    # Primary text extraction via browser (closer to visible)
                    try:
                        text = page.inner_text("body") or ""
                    except Exception:
                        text = visible_text_from_html(html)

                    # Link extraction from rendered HTML
                    links = extract_links(html, base_url=url, domain=domain)

                    # Extraction
                    er = extract_for_task(task, text, links)
                    extracted_keys = er.extracted_keys
                    missing_keys = er.missing_keys
                    evidence = er.evidence

                    # Determine step status for this task
                    if not missing_keys:
                        status = StepStatus.ok
                        success = True
                        notes = f"Found {task} on {url} ({', '.join(extracted_keys)})"
                    else:
                        status = StepStatus.fail

                        html_len = len(html.encode("utf-8", errors="ignore"))
                        # visible text length
                        t_vis = (text or "").strip()
                        text_len = len(t_vis)

                        # non-text heuristic (needs html + text)
                        if detect_non_text(html, text_len):
                            fail_reason = FailureReason.non_text
                        elif detect_js_only(html_len, text_len):
                            fail_reason = FailureReason.js_only
                        elif http_status in (401, 403, 429):
                            fail_reason = FailureReason.blocked
                        elif http_status >= 500:
                            fail_reason = FailureReason.timeout
                        elif http_status == 404:
                            fail_reason = FailureReason.not_found
                        elif detect_requires_login((t_vis or "").lower()):
                            fail_reason = FailureReason.requires_login
                        else:
                            signal = keyword_signal_for_task(task, t_vis, links)
                            fail_reason = FailureReason.hard_to_find if signal > 0 else FailureReason.not_found

                except PlaywrightTimeoutError:
                    status = StepStatus.fail
                    fail_reason = FailureReason.timeout
                except Exception:
                    status = StepStatus.fail
                    fail_reason = FailureReason.unknown
                finally:
                    latency_ms = int((time.perf_counter() - t0) * 1000)
                    try:
                        page.close()
                    except Exception:
                        pass

                    sl = StepLog(
                        run_id=run_id,
                        ts=now_iso(),
                        site=site,
                        domain=domain,
                        task=task,
                        step_num=step_num,
                        step_type="fetch",
                        url=url,
                        page_title=page_title,
                        http_status=http_status,
                        latency_ms=latency_ms,
                        status=status,
                        fail_reason=fail_reason,
                        extracted_keys=extracted_keys,
                        missing_keys=missing_keys,
                        evidence=(evidence or "")[:300],
                        meta={
                            "depth": depth,
                            "visited_count": len(visited),
                            "queue_len": len(q),
                        },
                    )
                    steps.append(sl)

                    # Print structured JSON line (trace)
                    print(sl.model_dump_json(), flush=True)

                    # Index into Elasticsearch
                    es.index(daily_index("agent_steps"), sl.model_dump())

                if success:
                    break

                # Enqueue next URLs (BFS, bounded)
                if depth < cfg.max_depth and links:
                    # cap links enqueued per page
                    for nxt in links[: cfg.enqueue_cap]:
                        if nxt not in visited:
                            q.append((nxt, depth + 1))

        finally:
            try:
                context.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass

    end_ts = now_iso()
    num_steps = len(steps)
    final_status = StepStatus.ok if success else StepStatus.fail
    if not success:
        # choose the last non-null fail reason if present, else not_found
        for s in reversed(steps):
            if s.fail_reason is not None:
                final_fail = s.fail_reason
                break
        final_fail = final_fail or FailureReason.not_found

    rs = RunSummary(
        run_id=run_id,
        ts_start=start_ts,
        ts_end=end_ts,
        site=site,
        domain=domain,
        task=task,
        success=success,
        success_score=score(success, num_steps, num_retries),
        num_steps=num_steps,
        num_retries=num_retries,
        final_url=final_url,
        final_status=final_status,
        final_fail_reason=final_fail,
        notes=notes,
    )

    # Print + index run summary
    print(rs.model_dump_json(), flush=True)
    es.index(daily_index("agent_runs"), rs.model_dump())
    return rs


def __domain(site: str) -> str:
    from urllib.parse import urlparse
    return urlparse(site).netloc


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Agentic Web Observability Analyzer (Phase 1)" )
    p.add_argument("--site", required=True, help="Start URL (e.g. https://example.com)")
    p.add_argument("--task", choices=["pricing", "refund", "contact"], default=None, help="Run a single task" )
    p.add_argument("--max-depth", type=int, default=int(os.getenv("MAX_DEPTH", "3")))
    p.add_argument("--max-steps", type=int, default=int(os.getenv("MAX_STEPS", "25")))
    p.add_argument("--page-timeout", type=int, default=int(os.getenv("PAGE_TIMEOUT_S", "25")))
    p.add_argument("--enqueue-cap", type=int, default=int(os.getenv("ENQUEUE_CAP", "40")))
    p.add_argument("--post-load-wait-ms", type=int, default=int(os.getenv("POST_LOAD_WAIT_MS", "1200")))
    return p.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()

    cfg = CrawlConfig(
        max_depth=args.max_depth,
        max_steps=args.max_steps,
        page_timeout_s=args.page_timeout,
        enqueue_cap=args.enqueue_cap,
        post_load_wait_ms=args.post_load_wait_ms,
    )

    es = ESClient.from_env()
    site = normalize_url(args.site)

    if args.task:
        run_task(site, args.task, cfg, es)
        return 0

    # Task suite (Phase 1)
    summaries = []
    for task in ("pricing", "refund", "contact"):
        summaries.append(run_task(site, task, cfg, es))

    # Nice deterministic console summary at the end
    print("\n=== Suite Summary ===")
    for s in summaries:
        print(f"{s.task}: success={s.success} score={s.success_score} steps={s.num_steps} final={s.final_status} reason={s.final_fail_reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
