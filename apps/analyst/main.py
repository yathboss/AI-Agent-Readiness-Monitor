from __future__ import annotations

import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel, Field

from apps.runner.es_client import ESClient
from apps.analyst.audit import AuditLogger
from apps.analyst.queries import ESQLTemplateLoader
from apps.analyst.tools import AnalystTools
from apps.analyst.agent import AnalystAgent, AskInput


load_dotenv()
app = FastAPI(title="AWOA Analyst Agent API (Phase 3)")


class TimeRange(BaseModel):
    # Either specify start/end ISO or relative like "7d"
    start: Optional[str] = None
    end: Optional[str] = None
    relative: Optional[str] = None
    # Compare mode:
    before: Optional[Dict[str, Any]] = None
    after: Optional[Dict[str, Any]] = None


class AskRequest(BaseModel):
    question: str = Field(..., description="Natural language question")
    site: Optional[str] = None
    domain: Optional[str] = None
    task: Optional[str] = Field(default=None, description="pricing | refund | contact")
    time_range: Optional[Dict[str, Any]] = None


class AskResponse(BaseModel):
    result: Dict[str, Any]
    markdown: str


def _agent() -> AnalystAgent:
    es = ESClient.from_env()
    loader = ESQLTemplateLoader()
    audit = AuditLogger(es)
    tools = AnalystTools(es=es, loader=loader, audit=audit)
    return AnalystAgent(tools)


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "service": "awoa-analyst", "phase": 3}


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    agent = _agent()
    result = agent.ask(
        AskInput(
            question=req.question,
            site=req.site,
            domain=req.domain,
            task=req.task,
            time_range=req.time_range,
        )
    )
    return AskResponse(result=result, markdown=result.get("markdown", ""))


@app.get("/trace/{run_id}")
def trace(run_id: str) -> Dict[str, Any]:
    agent = _agent()
    tr = agent.tools.tool_get_trace(run_id).data
    return {"run_id": run_id, "steps": tr}
