"""RemoteOK public JSON feed.

Endpoint: https://remoteok.com/api
First entry is metadata; the rest are postings. We filter to entries whose
location includes "Europe" (or is empty + has the EU tag) since the project
scope is EU + remote-EU jobs.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

import httpx
from markdownify import markdownify
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from pipeline.extractors.base import ExtractorTransientError
from pipeline.models import ATSReference, Company, Job, utcnow

logger = logging.getLogger(__name__)

NAME = "remoteok"
USER_AGENT = "ai-startups-bot/0.1 (+https://github.com/Aramente/eu-tech-jobs)"
_URL = "https://remoteok.com/api"


def _slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:48] or "unknown"


def _has_eu_signal(raw: dict[str, Any]) -> bool:
    """Keep the entry only if it's EU-eligible (Europe in location or worldwide-remote)."""
    loc = (raw.get("location") or "").lower()
    if not loc:
        return True  # no restriction declared = treat as remote-global
    return any(
        kw in loc
        for kw in (
            "europe",
            "eu",
            "emea",
            "uk",
            "germany",
            "france",
            "spain",
            "netherlands",
            "ireland",
            "anywhere",
            "worldwide",
            "remote",
        )
    )


def parse(payload: list[dict[str, Any]]) -> tuple[list[Company], list[Job]]:
    if not payload:
        return [], []
    # First item is the legal/meta entry; skip
    items = payload[1:] if isinstance(payload[0], dict) and "legal" in payload[0] else payload
    companies: dict[str, Company] = {}
    jobs: list[Job] = []
    now = utcnow()
    for raw in items:
        if not isinstance(raw, dict):
            continue
        if not _has_eu_signal(raw):
            continue
        company_name = (raw.get("company") or "").strip()
        if not company_name:
            continue
        slug = f"via-remoteok-{_slugify(company_name)}"
        url = raw.get("url") or raw.get("apply_url") or ""
        if not url:
            continue
        title = (raw.get("position") or "").strip()
        location = (raw.get("location") or "").strip() or "Remote"
        description_html = raw.get("description") or ""
        description_md = (
            markdownify(description_html, heading_style="ATX").strip() if description_html else ""
        )
        posted_at = _parse_dt(raw.get("date") or raw.get("epoch"))
        if slug not in companies:
            companies[slug] = Company(
                slug=slug,
                name=company_name,
                country="XX",
                categories=["tech", "remote-eu"],
                ats=None,
                career_url=url,
                notes=f"Aggregated from RemoteOK ({location})",
            )
        jobs.append(
            Job(
                id=Job.make_id(slug, url),
                company_slug=slug,
                title=title or "(untitled)",
                url=url,
                location=location,
                remote_policy="remote-global",
                posted_at=posted_at,
                scraped_at=now,
                description_md=description_md,
                source=NAME,
            )
        )
    return list(companies.values()), jobs


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=UTC)
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError, OSError):
        return None
    return None


@retry(
    retry=retry_if_exception_type((httpx.TransportError, ExtractorTransientError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def _fetch(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    resp = await client.get(_URL, headers={"User-Agent": USER_AGENT}, timeout=30.0)
    if resp.status_code >= 500:
        raise ExtractorTransientError(f"RemoteOK {resp.status_code}")
    if resp.status_code >= 400:
        raise ExtractorTransientError(f"RemoteOK {resp.status_code}: {resp.text[:200]}")
    return resp.json()


async def fetch_all(*, client: httpx.AsyncClient | None = None) -> tuple[list[Company], list[Job]]:
    """Fetch all RemoteOK jobs, filter to EU-relevant, return (companies, jobs)."""
    owns = client is None
    client = client or httpx.AsyncClient()
    try:
        payload = await _fetch(client)
    finally:
        if owns:
            await client.aclose()
    return parse(payload)


# unused but kept for parity with ATS extractors / future shaping
ATSReference  # noqa: B018
