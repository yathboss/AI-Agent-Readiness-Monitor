from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urldefrag, urlparse

from bs4 import BeautifulSoup


IGNORED_SCHEMES_PREFIXES = ("mailto:", "tel:", "javascript:")


def normalize_url(url: str) -> str:
    """Normalize a URL for deterministic visited-set comparisons."""
    if not url:
        return url
    url, _frag = urldefrag(url)
    # strip trailing slash except root
    parsed = urlparse(url)
    if parsed.path != "/" and url.endswith("/"):
        url = url[:-1]
    return url


def is_http_url(url: str) -> bool:
    p = urlparse(url)
    return p.scheme in ("http", "https")


def is_same_domain(url: str, domain: str) -> bool:
    try:
        return urlparse(url).netloc == domain
    except Exception:
        return False


def extract_links(html: str, base_url: str, domain: str) -> List[str]:
    soup = BeautifulSoup(html or "", "lxml")
    hrefs = []
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        if href.startswith(IGNORED_SCHEMES_PREFIXES):
            continue
        abs_url = urljoin(base_url, href)
        abs_url = normalize_url(abs_url)
        if not is_http_url(abs_url):
            continue
        if not is_same_domain(abs_url, domain):
            continue
        hrefs.append(abs_url)
    # deterministic order
    return sorted(set(hrefs))


def visible_text_from_html(html: str) -> str:
    soup = BeautifulSoup(html or "", "lxml")

    # Remove non-visible elements that bloat text
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text(" ", strip=True)
    # collapse whitespace deterministically
    text = re.sub(r"\s+", " ", text).strip()
    return text


def detect_non_text(html: str, visible_text_len: int) -> bool:
    """Heuristic: many images but almost no text."""
    if visible_text_len >= 80:
        return False
    soup = BeautifulSoup(html or "", "lxml")
    img_count = len(soup.find_all("img"))
    return img_count >= 6 and visible_text_len < 80


def detect_js_only(html_len: int, visible_text_len: int) -> bool:
    """Heuristic: very large HTML but very little visible text."""
    return (html_len >= 150_000 and visible_text_len <= 1_500) or (html_len >= 60_000 and visible_text_len <= 200)


def detect_requires_login(text_lower: str) -> bool:
    return ("password" in text_lower and ("login" in text_lower or "sign in" in text_lower))


def now_iso() -> str:
    # UTC iso string with Z
    import datetime
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def score(success: bool, steps: int, retries: int) -> int:
    if success:
        s = 100 - (max(0, steps - 1) * 4) - (retries * 10)
        return max(0, min(100, s))
    else:
        s = 30 - (steps * 2)
        return max(0, min(100, s))
