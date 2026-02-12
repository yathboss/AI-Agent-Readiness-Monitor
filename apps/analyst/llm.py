from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


@dataclass(frozen=True)
class LLMConfig:
    mode: str  # none | ollama | openai (stub)
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"


def load_llm_config() -> LLMConfig:
    mode = os.getenv("LLM_MODE", "none").strip().lower()
    return LLMConfig(
        mode=mode,
        ollama_url=os.getenv("OLLAMA_URL", "http://localhost:11434").strip(),
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3.1").strip(),
    )


def synthesize_markdown_deterministic(context: Dict[str, Any]) -> str:
    # Simple deterministic synthesis: no LLM.
    # context contains diagnosis, metrics, evidence, fixes.
    return context.get("markdown", "")


def synthesize_with_ollama(prompt: str, cfg: LLMConfig) -> str:
    """
    Optional: call local Ollama (no paid API).
    Works only if user runs Ollama locally.
    """
    url = cfg.ollama_url.rstrip("/") + "/api/generate"
    payload = {
        "model": cfg.ollama_model,
        "prompt": prompt,
        "stream": False,
    }
    r = requests.post(url, json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    return (data.get("response") or "").strip()


def synthesize_optional(context: Dict[str, Any]) -> str:
    """
    Entry point used by the agent.
    Defaults to deterministic mode.
    """
    cfg = load_llm_config()
    if cfg.mode == "none":
        return synthesize_markdown_deterministic(context)

    if cfg.mode == "ollama":
        # keep prompt compact/deterministic
        prompt = context.get("llm_prompt") or context.get("markdown") or "Summarize findings."
        try:
            return synthesize_with_ollama(prompt, cfg)
        except Exception:
            # fallback to deterministic
            return synthesize_markdown_deterministic(context)

    if cfg.mode == "openai":
        # stub only as requested
        return synthesize_markdown_deterministic(context)

    return synthesize_markdown_deterministic(context)
