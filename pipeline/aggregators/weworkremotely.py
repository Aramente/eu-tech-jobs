"""WeWorkRemotely RSS feeds.

Endpoint pattern: https://weworkremotely.com/categories/{category}.rss
We pull a few relevant categories (programming, devops, design, product).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from pipeline.extractors.base import ExtractorTransientError
from pipeline.models import Company, Job, utcnow

logger = logging.getLogger(__name__)

NAME = "weworkremotely"
USER_AGENT = "ai-startups-bot/0.1 (+https://github.com/Aramente/eu-tech-jobs)"

CATEGORIES = (
    "remote-programming-jobs",
    "remote-devops-sysadmin-jobs",
    "remote-design-jobs",
    "remote-product-jobs",
    "remote-management-and-finance-jobs",
)


def _slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:48] or "unknown"


def parse(rss_xml: str) -> tuple[list[Company], list[Job]]:
    if not rss_xml or "<item>" not in rss_xml:
        return [], []
    try:
        root = ET.fromstring(rss_xml)
    except ET.ParseError:
        return [], []
    companies: dict[str, Company] = {}
    jobs: list[Job] = []
    now = utcnow()
    for item in root.findall(".//item"):
        title_full = (item.findtext("title") or "").strip()
        if ":" not in title_full:
            continue
        company_part, role_part = title_full.split(":", 1)
        company_name = company_part.strip()
        title = role_part.strip()
        url = (item.findtext("link") or "").strip()
        if not company_name or not title or not url:
            continue
        slug = f"via-wwr-{_slugify(company_name)}"
        description_md = (item.findtext("description") or "").strip()
        # Locations are typically in WWR's regions tag — fall back to "Remote"
        region = (item.findtext("region") or "").strip() or "Remote"
        posted_at = _parse_dt(item.findtext("pubDate"))
        if slug not in companies:
            companies[slug] = Company(
                slug=slug,
                name=company_name,
                country="XX",
                categories=["tech", "remote-eu"],
                ats=None,
                career_url=url,
                notes=f"Aggregated from WeWorkRemotely ({region})",
            )
        jobs.append(
            Job(
                id=Job.make_id(slug, url),
                company_slug=slug,
                title=title,
                url=url,
                location=region,
                remote_policy="remote-global",
                posted_at=posted_at,
                scraped_at=now,
                description_md=description_md,
                source=NAME,
            )
        )
    return list(companies.values()), jobs


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


@retry(
    retry=retry_if_exception_type((httpx.TransportError, ExtractorTransientError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def _fetch(client: httpx.AsyncClient, category: str) -> str:
    url = f"https://weworkremotely.com/categories/{category}.rss"
    resp = await client.get(url, headers={"User-Agent": USER_AGENT}, timeout=30.0)
    if resp.status_code >= 500:
        raise ExtractorTransientError(f"WWR {resp.status_code} for {category}")
    if resp.status_code >= 400:
        raise ExtractorTransientError(f"WWR {resp.status_code} for {category}")
    return resp.text


async def fetch_all(
    *, client: httpx.AsyncClient | None = None
) -> tuple[list[Company], list[Job]]:
    owns = client is None
    client = client or httpx.AsyncClient()
    all_companies: dict[str, Company] = {}
    all_jobs: list[Job] = []
    try:
        for category in CATEGORIES:
            try:
                xml = await _fetch(client, category)
            except ExtractorTransientError as exc:
                logger.warning("WWR category %s failed: %s", category, exc)
                continue
            cs, js = parse(xml)
            for c in cs:
                all_companies.setdefault(c.slug, c)
            all_jobs.extend(js)
    finally:
        if owns:
            await client.aclose()
    return list(all_companies.values()), all_jobs
