"""Greenhouse public job-board API extractor.

Endpoint: https://boards-api.greenhouse.io/v1/boards/{handle}/jobs?content=true

Public, no auth, polite rate ~10 r/s. Returns full HTML descriptions when
`content=true`. We sanitize HTML → markdown for storage.
"""

from __future__ import annotations

import logging
from datetime import datetime
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

NAME = "greenhouse"
RATE_LIMIT_PER_SEC = 10.0
USER_AGENT = "ai-startups-bot/0.1 (+https://github.com/Aramente/ai-startups)"
_BASE = "https://boards-api.greenhouse.io/v1/boards"


def parse_jobs(payload: dict[str, Any], company_slug: str) -> list[Job]:
    """Pure parser: payload → list[Job]. No I/O, easy to test against fixtures."""
    raw_jobs = payload.get("jobs") or []
    out: list[Job] = []
    now = utcnow()
    for raw in raw_jobs:
        url = raw.get("absolute_url") or ""
        if not url:
            continue
        title = (raw.get("title") or "").strip()
        location = ((raw.get("location") or {}).get("name") or "").strip()
        content_html = raw.get("content") or ""
        description_md = (
            markdownify(content_html, heading_style="ATX").strip() if content_html else ""
        )
        posted_at = _parse_dt(raw.get("first_published") or raw.get("updated_at"))
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


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # Greenhouse sends RFC3339 like "2026-04-15T10:30:00Z" or "+00:00"
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@retry(
    retry=retry_if_exception_type((httpx.TransportError, ExtractorTransientError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def _fetch_payload(client: httpx.AsyncClient, handle: str) -> dict[str, Any]:
    url = f"{_BASE}/{handle}/jobs?content=true"
    resp = await client.get(url, headers={"User-Agent": USER_AGENT}, timeout=30.0)
    if resp.status_code == 404:
        raise ExtractorNotFoundError(f"Greenhouse board not found: {handle}")
    if resp.status_code >= 500:
        raise ExtractorTransientError(f"Greenhouse {resp.status_code} for {handle}")
    if resp.status_code >= 400:
        raise ExtractorTransientError(
            f"Greenhouse {resp.status_code} for {handle}: {resp.text[:200]}"
        )
    return resp.json()


async def fetch_jobs(
    handle: str, *, company_slug: str, client: httpx.AsyncClient | None = None
) -> list[Job]:
    """Fetch + parse all jobs for a Greenhouse board handle.

    Args:
        handle: Greenhouse board slug (e.g. "wayve").
        company_slug: our internal company slug.
        client: optional shared httpx client (orchestrator passes one in for connection reuse).
    """
    owns_client = client is None
    client = client or httpx.AsyncClient()
    try:
        payload = await _fetch_payload(client, handle)
    finally:
        if owns_client:
            await client.aclose()
    return parse_jobs(payload, company_slug)
