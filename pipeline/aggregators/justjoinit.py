"""JustJoin.it public job board API (Polish market + EU broad).

Endpoint: https://api.justjoin.it/v2/user-panel/offers
Public, uses `Version: 2` header. Default response is paginated; we fetch
~5 pages for v2 coverage.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from pipeline.extractors.base import ExtractorTransientError
from pipeline.models import Company, Job, utcnow

logger = logging.getLogger(__name__)

NAME = "justjoinit"
USER_AGENT = "Mozilla/5.0 ai-startups-bot/0.1"
_URL = "https://api.justjoin.it/v2/user-panel/offers"
_MAX_PAGES = 5


def _slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:48] or "unknown"


def parse(payload: dict[str, Any]) -> tuple[list[Company], list[Job]]:
    items = payload.get("data") or payload.get("offers") or []
    if isinstance(payload, list):
        items = payload
    companies: dict[str, Company] = {}
    jobs: list[Job] = []
    now = utcnow()
    for raw in items:
        company_name = (raw.get("companyName") or "").strip()
        if not company_name:
            continue
        slug = f"via-justjoinit-{_slugify(company_name)}"
        guid = raw.get("guid") or raw.get("slug") or ""
        slug_offer = raw.get("slug") or guid
        url = f"https://justjoin.it/offers/{slug_offer}" if slug_offer else ""
        if not url:
            continue
        title = (raw.get("title") or "").strip()
        city = (raw.get("city") or "").strip()
        country = (raw.get("country") or "PL").strip()[:2].upper() or "PL"
        location = ", ".join(p for p in [city, country] if p)
        wp = (raw.get("workplaceType") or "").lower()
        remote_policy = (
            "remote"
            if wp == "remote"
            else "hybrid"
            if wp == "hybrid"
            else "onsite"
        )
        posted_at = _parse_dt(raw.get("publishedAt") or raw.get("lastPublishedAt"))
        if slug not in companies:
            companies[slug] = Company(
                slug=slug,
                name=company_name,
                country=country,
                categories=["tech"],
                ats=None,
                career_url=url,
                notes=f"Aggregated from JustJoin.it ({city or 'Remote'})",
            )
        jobs.append(
            Job(
                id=Job.make_id(slug, url),
                company_slug=slug,
                title=title or "(untitled)",
                url=url,
                location=location,
                remote_policy=remote_policy,
                posted_at=posted_at,
                scraped_at=now,
                description_md="",
                source=NAME,
            )
        )
    return list(companies.values()), jobs


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


@retry(
    retry=retry_if_exception_type((httpx.TransportError, ExtractorTransientError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def _fetch_page(client: httpx.AsyncClient, page: int) -> dict[str, Any]:
    resp = await client.get(
        f"{_URL}?page={page}",
        headers={"User-Agent": USER_AGENT, "Version": "2"},
        timeout=30.0,
    )
    if resp.status_code >= 500:
        raise ExtractorTransientError(f"JJI {resp.status_code} for page {page}")
    if resp.status_code >= 400:
        raise ExtractorTransientError(f"JJI {resp.status_code}: {resp.text[:200]}")
    return resp.json()


async def fetch_all(
    *, client: httpx.AsyncClient | None = None
) -> tuple[list[Company], list[Job]]:
    owns = client is None
    client = client or httpx.AsyncClient()
    all_companies: dict[str, Company] = {}
    all_jobs: list[Job] = []
    try:
        for page in range(1, _MAX_PAGES + 1):
            try:
                payload = await _fetch_page(client, page)
            except ExtractorTransientError as exc:
                logger.warning("JJI page %d failed: %s", page, exc)
                break
            cs, js = parse(payload)
            if not js:
                break
            for c in cs:
                all_companies.setdefault(c.slug, c)
            all_jobs.extend(js)
            meta = payload.get("meta") or {}
            if meta.get("totalPages") and page >= meta["totalPages"]:
                break
    finally:
        if owns:
            await client.aclose()
    return list(all_companies.values()), all_jobs
