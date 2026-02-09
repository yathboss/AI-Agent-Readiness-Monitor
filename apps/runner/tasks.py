from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)

PRICING_KEYWORDS = [
    "pricing", "price", "prices", "plan", "plans", "subscription", "billing",
    "₹", "$", "€", "usd", "inr", "eur"
]

REFUND_KEYWORDS = [
    "refund", "refunds", "return", "returns", "cancellation", "cancelation",
    "policy", "replacement", "chargeback"
]

CONTACT_KEYWORDS = [
    "contact", "support", "help", "customer service", "get in touch", "email us"
]

CONTACT_LINK_HINTS = ["contact", "support", "help", "customer-service"]


@dataclass(frozen=True)
class ExtractionResult:
    extracted_keys: List[str]
    missing_keys: List[str]
    evidence: str


def _keyword_hits(text_lower: str, keywords: List[str]) -> int:
    hits = 0
    for kw in keywords:
        if kw in ("₹", "$", "€"):
            hits += text_lower.count(kw)
        else:
            hits += text_lower.count(kw.lower())
    return hits


def extract_pricing(text: str) -> ExtractionResult:
    t = text or ""
    tl = t.lower()
    hits = _keyword_hits(tl, PRICING_KEYWORDS)
    if hits > 0:
        # evidence: first matching line fragment
        for kw in PRICING_KEYWORDS:
            k = kw.lower()
            idx = tl.find(k)
            if idx != -1:
                start = max(0, idx - 60)
                end = min(len(t), idx + 120)
                snippet = t[start:end].replace("\n", " ").strip()
                return ExtractionResult(["pricing"], [], snippet[:300])
        return ExtractionResult(["pricing"], [], t[:300])
    return ExtractionResult([], ["pricing"], "")


def extract_refund(text: str, links: List[str]) -> ExtractionResult:
    t = text or ""
    tl = t.lower()

    # keyword in visible text
    hits = _keyword_hits(tl, REFUND_KEYWORDS)

    # policy url presence (deterministic: first matching lexicographically)
    policy_links = []
    for href in links:
        hl = href.lower()
        if any(k in hl for k in ["refund", "return", "policy", "returns", "replacement", "cancellation"]):
            policy_links.append(href)
    policy_links = sorted(set(policy_links))

    extracted = []
    evidence = ""

    if hits > 0:
        extracted.append("refund_policy")
        # evidence snippet around first hit
        for kw in REFUND_KEYWORDS:
            idx = tl.find(kw)
            if idx != -1:
                start = max(0, idx - 60)
                end = min(len(t), idx + 160)
                evidence = t[start:end].replace("\n", " ").strip()[:300]
                break

    if policy_links:
        extracted.append("policy_url")
        if not evidence:
            evidence = f"policy_url: {policy_links[0]}"

    # success if either text keywords OR policy link exists
    if extracted:
        return ExtractionResult(extracted_keys=extracted, missing_keys=[], evidence=evidence[:300])
    return ExtractionResult(extracted_keys=[], missing_keys=["refund_policy"], evidence="")


def extract_contact(text: str, links: List[str]) -> ExtractionResult:
    t = text or ""
    tl = t.lower()

    emails = sorted(set(EMAIL_RE.findall(t)))
    if emails:
        return ExtractionResult(["email"], [], emails[0])

    # contact page link (deterministic: first matching lexicographically)
    contact_links = []
    for href in links:
        hl = href.lower()
        if any(hint in hl for hint in CONTACT_LINK_HINTS):
            contact_links.append(href)
    contact_links = sorted(set(contact_links))
    if contact_links:
        return ExtractionResult(["contact_page"], [], contact_links[0])

    # soft signal: contact keywords in text (not enough for success)
    hits = _keyword_hits(tl, CONTACT_KEYWORDS)
    if hits > 0:
        return ExtractionResult([], ["contact_method"], "contact-related words present but no email/contact link")

    return ExtractionResult([], ["contact_method"], "")


def keyword_signal_for_task(task: str, text: str, links: List[str]) -> int:
    tl = (text or "").lower()
    if task == "pricing":
        return _keyword_hits(tl, PRICING_KEYWORDS)
    if task == "refund":
        # count refund keywords plus matching link hints
        signal = _keyword_hits(tl, REFUND_KEYWORDS)
        for href in links:
            hl = href.lower()
            if any(k in hl for k in ["refund", "return", "policy", "returns", "replacement", "cancellation"]):
                signal += 1
        return signal
    if task == "contact":
        signal = _keyword_hits(tl, CONTACT_KEYWORDS)
        for href in links:
            hl = href.lower()
            if any(h in hl for h in CONTACT_LINK_HINTS):
                signal += 1
        return signal
    return 0
