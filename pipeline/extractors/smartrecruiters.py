"""SmartRecruiters public job board API extractor.

Endpoint: https://api.smartrecruiters.com/v1/companies/{handle}/postings
Public, no auth. Cursor pagination via `offset` and `limit`. We page until
exhausted (default 100 per page).
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

NAME = "smartrecruiters"
RATE_LIMIT_PER_SEC = 5.0
USER_AGENT = "ai-startups-bot/0.1 (+https://github.com/Aramente/eu-tech-jobs)"
_BASE = "https://api.smartrecruiters.com/v1/companies"
_PAGE_SIZE = 100
_MAX_PAGES = 50  # safety guard against runaway pagination


def _format_job_ad(job_ad: dict[str, Any]) -> str:
    """Render SmartRecruiters' jobAd.sections into markdown."""
    sections = job_ad.get("sections") or {}
    parts: list[str] = []
    for key in ("companyDescription", "jobDescription", "qualifications", "additionalInformation"):
        section = sections.get(key) or {}
        title = section.get("title") or ""
        text = section.get("text") or ""
        if title:
            parts.append(f"## {title}")
        if text:
            parts.append(markdownify(text, heading_style="ATX").strip())
    return "\n\n".join(s for s in parts if s)


def parse_jobs(payload: dict[str, Any], company_slug: str) -> list[Job]:
    """Pure parser. SmartRecruiters returns `{content: [postings...]}`."""
    postings = payload.get("content") or []
    out: list[Job] = []
    now = utcnow()
    for raw in postings:
        post_id = raw.get("id") or raw.get("uuid")
        if not post_id:
            continue
        raw.get("name") or post_id
        # Public posting URL pattern
        company_id = raw.get("company", {}).get("identifier") or company_slug
        url = (
            (raw.get("ref") or "")
            or f"https://jobs.smartrecruiters.com/{company_id}/{post_id}"
        )
        title = (raw.get("name") or "").strip()
        loc_obj = raw.get("location") or {}
        loc = ", ".join(
            v for v in [loc_obj.get("city"), loc_obj.get("region"), loc_obj.get("country")] if v
        )
        description_md = _format_job_ad(raw.get("jobAd") or {})
        posted_at = _parse_dt(raw.get("releasedDate") or raw.get("createdOn"))
        out.append(
            Job(
                id=Job.make_id(company_slug, url),
                company_slug=company_slug,
                title=title or "(untitled)",
                url=url,
                location=loc,
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
async def _fetch_page(
    client: httpx.AsyncClient, handle: str, offset: int
) -> dict[str, Any]:
    url = f"{_BASE}/{handle}/postings?limit={_PAGE_SIZE}&offset={offset}"
    resp = await client.get(url, headers={"User-Agent": USER_AGENT}, timeout=30.0)
    if resp.status_code == 404:
        raise ExtractorNotFoundError(f"SmartRecruiters company not found: {handle}")
    if resp.status_code >= 500:
        raise ExtractorTransientError(f"SR {resp.status_code} for {handle}")
    if resp.status_code >= 400:
        raise ExtractorTransientError(f"SR {resp.status_code} for {handle}: {resp.text[:200]}")
    return resp.json()


async def fetch_jobs(
    handle: str, *, company_slug: str, client: httpx.AsyncClient | None = None
) -> list[Job]:
    owns = client is None
    client = client or httpx.AsyncClient()
    all_jobs: list[Job] = []
    try:
        offset = 0
        for _ in range(_MAX_PAGES):
            payload = await _fetch_page(client, handle, offset)
            jobs = parse_jobs(payload, company_slug)
            all_jobs.extend(jobs)
            total = payload.get("totalFound") or len(jobs)
            offset += _PAGE_SIZE
            if offset >= total or not jobs:
                break
    finally:
        if owns:
            await client.aclose()
    return all_jobs
