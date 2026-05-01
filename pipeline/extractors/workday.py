"""Workday CXS (Career Experience Site) extractor.

Workday powers careers for ~70% of Fortune 500 + many AI/scale-ups
(NVIDIA, Adobe, Salesforce, Workday itself, Recursion, ServiceNow…).
The visible site is a JS SPA, but every Workday tenant exposes an
internal POST endpoint that returns a paginated, structured JSON
listing with no auth.

Endpoint shape:
    POST https://{tenant}.{cluster}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
    Content-Type: application/json
    Body: {"appliedFacets": {...}, "limit": 20, "offset": 0, "searchText": ""}

We accept that full URL as the `handle` field in YAML to avoid having
to model tenant/site/cluster as separate keys. The cluster (wd1…wd105)
is per-tenant and not directly inferable from the brand name, so the
URL itself is the cleanest identifier.

Optional EU filter: pass `&locationCountry={country-uuid}` via
`appliedFacets.locationCountry`. Workday country UUIDs aren't human-
readable; we leave filtering to the snapshot-level geo filter
(pipeline/filters.py) downstream.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import httpx
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

NAME = "workday"
USER_AGENT = "ai-startups-bot/0.1 (+https://github.com/Aramente/eu-tech-jobs)"
PAGE_SIZE = 20  # Workday default and most stable


def _job_url(tenant_base: str, external_path: str) -> str:
    """external_path is like '/job/UK-London/Senior-Engineer_JR123' →
    full https://tenant.cluster.myworkdayjobs.com/<site>/job/...

    The tenant_base passed in here is the part of the URL before /wday/.
    Example tenant_base for NVIDIA:
        https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite
    """
    if not external_path:
        return ""
    if external_path.startswith("http"):
        return external_path
    base = tenant_base.rstrip("/")
    if external_path.startswith("/"):
        return base + external_path
    return f"{base}/{external_path}"


def _derive_tenant_base(api_url: str) -> str:
    """From '...myworkdayjobs.com/wday/cxs/<tenant>/<site>/jobs' return
    '...myworkdayjobs.com/<site>' for building public URLs."""
    parsed = urlparse(api_url)
    parts = [p for p in parsed.path.split("/") if p]
    # Expect: ['wday', 'cxs', tenant, site, 'jobs']
    if len(parts) >= 5 and parts[0] == "wday" and parts[1] == "cxs":
        site = parts[3]
        return f"{parsed.scheme}://{parsed.netloc}/{site}"
    return f"{parsed.scheme}://{parsed.netloc}"


def _parse_dt_relative(posted_on: str | None) -> datetime | None:
    """Workday returns relative strings ('Posted Today', 'Posted 5 Days Ago').
    We can't recover an exact timestamp, so we return None and let the
    consumer fall back to scraped_at for "first seen".
    """
    return None


def parse_jobs(
    payload: dict[str, Any],
    company_slug: str,
    *,
    api_url: str,
) -> list[Job]:
    raw = payload.get("jobPostings") or []
    if not isinstance(raw, list):
        return []
    tenant_base = _derive_tenant_base(api_url)
    out: list[Job] = []
    now = utcnow()
    for r in raw:
        title = (r.get("title") or "").strip()
        path = r.get("externalPath") or ""
        url = _job_url(tenant_base, path)
        if not title or not url:
            continue
        location = (r.get("locationsText") or "").strip()
        out.append(
            Job(
                id=Job.make_id(company_slug, url),
                company_slug=company_slug,
                title=title,
                url=url,
                location=location,
                posted_at=None,
                scraped_at=now,
                description_md="",
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
    client: httpx.AsyncClient, api_url: str, offset: int, limit: int
) -> dict[str, Any]:
    body = {
        "appliedFacets": {},
        "limit": limit,
        "offset": offset,
        "searchText": "",
    }
    resp = await client.post(
        api_url,
        json=body,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        timeout=30.0,
    )
    if resp.status_code == 404:
        raise ExtractorNotFoundError(f"Workday 404: {api_url}")
    if resp.status_code >= 500:
        raise ExtractorTransientError(f"Workday {resp.status_code}: {api_url}")
    if resp.status_code >= 400:
        raise ExtractorTransientError(
            f"Workday {resp.status_code}: {api_url}: {resp.text[:200]}"
        )
    try:
        return resp.json()
    except Exception as exc:
        raise ExtractorTransientError(f"Workday non-JSON response: {exc}") from exc


# Cap one tenant at 1000 jobs/run so a single mega-employer doesn't dominate
# the snapshot. The geo filter downstream typically drops 70-90% anyway.
MAX_PAGES = 50  # 50 * 20 = 1000 jobs


async def fetch_jobs(
    handle: str,
    *,
    company_slug: str,
    client: httpx.AsyncClient | None = None,
) -> list[Job]:
    """Paginated fetch of Workday postings for one tenant."""
    if not handle.startswith(("http://", "https://")):
        raise ExtractorTransientError(
            f"Workday handle must be the full /wday/cxs/.../jobs URL, got: {handle}"
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
                logger.warning("Workday %s page %d failed: %s", company_slug, page, exc)
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
            # If the response paginated below page size OR all jobs were dups,
            # we've reached the end.
            if len(jobs) < PAGE_SIZE or new_count == 0:
                break
    finally:
        if owns:
            await client.aclose()
    logger.info("Workday %s → %d jobs", company_slug, len(out))
    return out
