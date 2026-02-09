from __future__ import annotations

import os
from typing import Optional, List

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel, Field

# Import runner components
from apps.runner.main import CrawlConfig, run_task
from apps.runner.es_client import ESClient
from apps.runner.utils import normalize_url


load_dotenv()
app = FastAPI(title="Agentic Web Observability Analyzer API (Phase 1)")


class RunRequest(BaseModel):
    site: str = Field(..., description="Start URL")
    task: Optional[str] = Field(default=None, description="pricing | refund | contact (if omitted, runs suite)")
    max_depth: int = 3
    max_steps: int = 25
    page_timeout: int = 25
    enqueue_cap: int = 40
    post_load_wait_ms: int = 1200


class RunResponse(BaseModel):
    summaries: List[dict]


@app.post("/run", response_model=RunResponse)
def run(req: RunRequest) -> RunResponse:
    es = ESClient.from_env()
    cfg = CrawlConfig(
        max_depth=req.max_depth,
        max_steps=req.max_steps,
        page_timeout_s=req.page_timeout,
        enqueue_cap=req.enqueue_cap,
        post_load_wait_ms=req.post_load_wait_ms,
    )
    site = normalize_url(req.site)

    if req.task:
        s = run_task(site, req.task, cfg, es)
        return RunResponse(summaries=[s.model_dump()])

    summaries = []
    for t in ("pricing", "refund", "contact"):
        s = run_task(site, t, cfg, es)
        summaries.append(s.model_dump())
    return RunResponse(summaries=summaries)
