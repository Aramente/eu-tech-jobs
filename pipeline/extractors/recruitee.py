"""Recruitee public job board API extractor.

Endpoint: https://{handle}.recruitee.com/api/offers/
Public, no auth. Returns all current offers in a single response.
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

NAME = "recruitee"
RATE_LIMIT_PER_SEC = 5.0
USER_AGENT = "ai-startups-bot/0.1 (+https://github.com/Aramente/eu-tech-jobs)"


def parse_jobs(payload: dict[str, Any], company_slug: str) -> list[Job]:
    offers = payload.get("offers") or []
    out: list[Job] = []
    now = utcnow()
    for raw in offers:
        url = raw.get("careers_url") or raw.get("careers_apply_url") or ""
        if not url:
            continue
        title = (raw.get("title") or "").strip()
        loc_parts = [
            raw.get("city") or "",
            raw.get("country") or "",
        ]
        location = ", ".join(p for p in loc_parts if p)
        description_md = ""
        desc_html = raw.get("description") or raw.get("requirements") or ""
        if desc_html:
            description_md = markdownify(desc_html, heading_style="ATX").strip()
        posted_at = _parse_dt(raw.get("created_at") or raw.get("published_at"))
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
    url = f"https://{handle}.recruitee.com/api/offers/"
    resp = await client.get(url, headers={"User-Agent": USER_AGENT}, timeout=30.0)
    if resp.status_code == 404:
        raise ExtractorNotFoundError(f"Recruitee subdomain not found: {handle}")
    if resp.status_code >= 500:
        raise ExtractorTransientError(f"Recruitee {resp.status_code} for {handle}")
    if resp.status_code >= 400:
        raise ExtractorTransientError(
            f"Recruitee {resp.status_code} for {handle}: {resp.text[:200]}"
        )
    return resp.json()


async def fetch_jobs(
    handle: str, *, company_slug: str, client: httpx.AsyncClient | None = None
) -> list[Job]:
    owns = client is None
    client = client or httpx.AsyncClient()
    try:
        payload = await _fetch_payload(client, handle)
    finally:
        if owns:
            await client.aclose()
    return parse_jobs(payload, company_slug)
