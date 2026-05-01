"""Phenom People (formerly Jibe) careers API extractor.

Phenom hosts careers for AMD, GE, Boeing, Wells Fargo, FedEx, and many
other Fortune 500. The endpoint is consistent:
    GET https://{careers_host}/api/jobs?size=N&start=0&country=...
    → {"jobs": [{"data": {slug, title, description, ...}}], "totalCount": N}

We accept the full API URL as the `handle` (same approach as Workday)
because the careers_host varies (careers.amd.com, careers.ge.com,
jobs.fedex.com, etc).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

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

NAME = "phenom"
USER_AGENT = "ai-startups-bot/0.1 (+https://github.com/Aramente/eu-tech-jobs)"
PAGE_SIZE = 50
MAX_PAGES = 40  # 2000 jobs per tenant cap


def _public_url(api_url: str, slug: str) -> str:
    """Phenom job pages live at the careers host root, format
    https://careers.amd.com/jobs/{slug}/{title-slug-or-anything}.

    We don't always have a clean title-slug at hand; the slug alone is a
    valid public URL.
    """
    parsed = urlparse(api_url)
    return f"{parsed.scheme}://{parsed.netloc}/jobs/{slug}"


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value) / 1000 if value > 1e12 else float(value))
    except (ValueError, OverflowError, OSError):
        return None
    return None


def _location_string(data: dict[str, Any]) -> str:
    parts = []
    for k in ("city", "state", "country"):
        v = data.get(k)
        if v:
            parts.append(str(v).strip())
    if not parts:
        # Some Phenom tenants return location in a "location" object
        loc = data.get("location") or {}
        if isinstance(loc, dict):
            for k in ("city", "state", "country", "name"):
                v = loc.get(k)
                if v:
                    parts.append(str(v).strip())
    return ", ".join(parts)


def parse_jobs(payload: dict[str, Any], company_slug: str, *, api_url: str) -> list[Job]:
    raw = payload.get("jobs") or []
    out: list[Job] = []
    now = utcnow()
    for r in raw:
        d = r.get("data") if isinstance(r, dict) else None
        if not isinstance(d, dict):
            continue
        slug = d.get("slug") or d.get("req_id")
        title = (d.get("title") or "").strip()
        if not slug or not title:
            continue
        url = _public_url(api_url, str(slug))
        location = _location_string(d)
        desc_html = d.get("description") or ""
        description_md = (
            markdownify(desc_html, heading_style="ATX").strip() if desc_html else ""
        )
        posted_at = _parse_dt(d.get("posted_date") or d.get("postedAt") or d.get("postedDate"))
        out.append(
            Job(
                id=Job.make_id(company_slug, url),
                company_slug=company_slug,
                title=title,
                url=url,
                location=location,
                posted_at=posted_at,
                scraped_at=now,
                description_md=description_md,
                source=NAME,
            )
        )
    return out


@retry(
    retry=retry_if_exception_type((httpx.TransportError, ExtractorTransientError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def _fetch_page(
    client: httpx.AsyncClient, api_url: str, start: int, size: int
) -> dict[str, Any]:
    sep = "&" if "?" in api_url else "?"
    url = f"{api_url}{sep}size={size}&start={start}"
    resp = await client.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=30.0,
    )
    if resp.status_code == 404:
        raise ExtractorNotFoundError(f"Phenom 404: {url}")
    if resp.status_code >= 500:
        raise ExtractorTransientError(f"Phenom {resp.status_code}: {url}")
    if resp.status_code >= 400:
        raise ExtractorTransientError(
            f"Phenom {resp.status_code}: {url}: {resp.text[:200]}"
        )
    try:
        return resp.json()
    except Exception as exc:
        raise ExtractorTransientError(f"Phenom non-JSON: {exc}") from exc


async def fetch_jobs(
    handle: str,
    *,
    company_slug: str,
    client: httpx.AsyncClient | None = None,
) -> list[Job]:
    if not handle.startswith(("http://", "https://")):
        raise ExtractorTransientError(
            f"Phenom handle must be a full /api/jobs URL, got: {handle}"
        )
    owns = client is None
    client = client or httpx.AsyncClient()
    out: list[Job] = []
    seen_urls: set[str] = set()
    try:
        for page in range(MAX_PAGES):
            try:
                payload = await _fetch_page(client, handle, page * PAGE_SIZE, PAGE_SIZE)
            except ExtractorNotFoundError:
                break
            except Exception as exc:
                logger.warning(
                    "Phenom %s page %d failed: %s", company_slug, page, exc
                )
                break
            jobs = parse_jobs(payload, company_slug, api_url=handle)
            if not jobs:
                break
            new_count = 0
            for j in jobs:
                if j.url in seen_urls:
                    continue
                seen_urls.add(j.url)
                out.append(j)
                new_count += 1
            if len(jobs) < PAGE_SIZE or new_count == 0:
                break
    finally:
        if owns:
            await client.aclose()
    logger.info("Phenom %s → %d jobs", company_slug, len(out))
    return out
