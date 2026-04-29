"""Lever public job-board API extractor.

Endpoint: https://api.lever.co/v0/postings/{handle}?mode=json
Public, no auth, polite rate ~5 r/s. Returns flat JSON with structured `lists`
arrays for "What you'll do" / "About you" sections.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx
from markdownify import markdownify
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from pipeline.extractors.base import (
    ExtractorNotFoundError,
    ExtractorTransientError,
)
from pipeline.models import Job, utcnow

logger = logging.getLogger(__name__)

NAME = "lever"
RATE_LIMIT_PER_SEC = 5.0
USER_AGENT = "ai-startups-bot/0.1 (+https://github.com/Aramente/eu-tech-jobs)"
_BASE = "https://api.lever.co/v0/postings"


def _format_lists(lists: list[dict[str, Any]]) -> str:
    """Render Lever's structured `lists` array (with HTML content) into markdown."""
    parts: list[str] = []
    for entry in lists:
        text = (entry.get("text") or "").strip()
        content = entry.get("content") or ""
        if text:
            parts.append(f"## {text}")
        if content:
            parts.append(markdownify(content, heading_style="ATX").strip())
    return "\n\n".join(parts)


def parse_jobs(payload: list[dict[str, Any]], company_slug: str) -> list[Job]:
    """Pure parser. Lever returns a flat list at the top level."""
    out: list[Job] = []
    now = utcnow()
    for raw in payload or []:
        url = raw.get("hostedUrl") or raw.get("applyUrl") or ""
        if not url:
            continue
        title = (raw.get("text") or "").strip()
        cats = raw.get("categories") or {}
        location = (cats.get("location") or "").strip()
        # Description = top-level descriptionPlain + structured lists + additional
        sections: list[str] = []
        desc = raw.get("description") or ""
        if desc:
            sections.append(markdownify(desc, heading_style="ATX").strip())
        lists = raw.get("lists") or []
        if lists:
            sections.append(_format_lists(lists))
        additional = raw.get("additional") or ""
        if additional:
            sections.append(markdownify(additional, heading_style="ATX").strip())
        description_md = "\n\n".join(s for s in sections if s)
        posted_at = _parse_dt(raw.get("createdAt"))
        out.append(
            Job(
                id=Job.make_id(company_slug, url),
                company_slug=company_slug,
                title=title or "(untitled)",
                url=url,
                location=location,
                posted_at=posted_at,
                scraped_at=now,
                description_md=description_md,
                source=NAME,
            )
        )
    return out


def _parse_dt(value: int | str | None) -> datetime | None:
    if value is None:
        return None
    # Lever returns epoch milliseconds
    if isinstance(value, int):
        try:
            return datetime.fromtimestamp(value / 1000, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


@retry(
    retry=retry_if_exception_type((httpx.TransportError, ExtractorTransientError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def _fetch_payload(client: httpx.AsyncClient, handle: str) -> list[dict[str, Any]]:
    url = f"{_BASE}/{handle}?mode=json"
    resp = await client.get(url, headers={"User-Agent": USER_AGENT}, timeout=30.0)
    if resp.status_code == 404:
        raise ExtractorNotFoundError(f"Lever board not found: {handle}")
    if resp.status_code >= 500:
        raise ExtractorTransientError(f"Lever {resp.status_code} for {handle}")
    if resp.status_code >= 400:
        raise ExtractorTransientError(
            f"Lever {resp.status_code} for {handle}: {resp.text[:200]}"
        )
    return resp.json()


async def fetch_jobs(
    handle: str, *, company_slug: str, client: httpx.AsyncClient | None = None
) -> list[Job]:
    """Fetch + parse all postings for a Lever handle."""
    owns = client is None
    client = client or httpx.AsyncClient()
    try:
        payload = await _fetch_payload(client, handle)
    finally:
        if owns:
            await client.aclose()
    return parse_jobs(payload, company_slug)
