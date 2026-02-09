from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class FailureReason(str, Enum):
    not_found = "not_found"
    hard_to_find = "hard_to_find"
    js_only = "js_only"
    non_text = "non_text"
    ambiguous = "ambiguous"
    blocked = "blocked"
    timeout = "timeout"
    requires_login = "requires_login"
    unknown = "unknown"


class StepStatus(str, Enum):
    ok = "ok"
    fail = "fail"


class StepLog(BaseModel):
    # Step log (agent_steps-*)
    run_id: str = Field(..., description="Run correlation id")
    ts: str = Field(..., description="ISO timestamp")
    site: str
    domain: str
    task: str
    step_num: int
    step_type: str  # e.g., fetch
    url: str
    page_title: str = ""
    http_status: int = 0
    latency_ms: int = 0
    status: StepStatus
    fail_reason: Optional[FailureReason] = None
    extracted_keys: List[str] = []
    missing_keys: List[str] = []
    evidence: str = ""
    meta: Dict[str, Any] = Field(default_factory=dict)


class RunSummary(BaseModel):
    # Run summary (agent_runs-*)
    run_id: str
    ts_start: str
    ts_end: str
    site: str
    domain: str
    task: str
    success: bool
    success_score: int = Field(ge=0, le=100)
    num_steps: int
    num_retries: int = 0
    final_url: str = ""
    final_status: StepStatus = StepStatus.fail
    final_fail_reason: Optional[FailureReason] = None
    notes: str = ""
