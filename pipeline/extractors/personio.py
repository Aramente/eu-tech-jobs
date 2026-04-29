"""Personio public job board (XML) extractor.

Endpoint: https://{handle}.jobs.personio.com/xml
Public, no auth. Returns one big XML document with `<position>` entries —
common shape for DACH companies.
"""

from __future__ import annotations

import logging
from datetime import datetime
from xml.etree import ElementTree as ET

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

NAME = "personio"
RATE_LIMIT_PER_SEC = 3.0
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0 Safari/537.36"
)
# Personio's hosted job pages sometimes hide behind a Vercel security checkpoint
# unless the User-Agent looks browser-like. We use a real-Chrome UA here.


def parse_jobs(xml_text: str, company_slug: str, handle: str) -> list[Job]:
    """Pure parser for Personio's XML feed."""
    if not xml_text or "<position>" not in xml_text:
        return []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    out: list[Job] = []
    now = utcnow()
    for pos in root.findall("position"):
        post_id = (pos.findtext("id") or "").strip()
        title = (pos.findtext("name") or "").strip()
        if not post_id or not title:
            continue
        # Personio doesn't give canonical URLs in XML; build from handle + id
        url = f"https://{handle}.jobs.personio.com/job/{post_id}"
        office = (pos.findtext("office") or "").strip()
        # Concatenate all jobDescription nodes into markdown-friendly text
        desc_parts: list[str] = []
        for jd in pos.findall("jobDescriptions/jobDescription"):
            jd_name = (jd.findtext("name") or "").strip()
            jd_value = (jd.findtext("value") or "").strip()
            if jd_name:
                desc_parts.append(f"## {jd_name}")
            if jd_value:
                desc_parts.append(jd_value)
        description_md = "\n\n".join(desc_parts)
        posted_at = _parse_dt(pos.findtext("createdAt") or pos.findtext("created_at"))
        out.append(
            Job(
                id=Job.make_id(company_slug, url),
                company_slug=company_slug,
                title=title,
                url=url,
                location=office,
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
async def _fetch_xml(client: httpx.AsyncClient, handle: str) -> str:
    url = f"https://{handle}.jobs.personio.com/xml"
    resp = await client.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/xml,text/xml,*/*"},
        timeout=30.0,
        follow_redirects=True,
    )
    if resp.status_code == 404:
        raise ExtractorNotFoundError(f"Personio subdomain not found: {handle}")
    if resp.status_code >= 500:
        raise ExtractorTransientError(f"Personio {resp.status_code} for {handle}")
    if resp.status_code >= 400:
        raise ExtractorTransientError(
            f"Personio {resp.status_code} for {handle}"
        )
    text = resp.text
    if "Vercel Security Checkpoint" in text or "<workzag-jobs>" not in text:
        # Bot-blocked; treat as transient (retry won't help, but don't crash run)
        raise ExtractorTransientError(
            f"Personio {handle} returned non-XML (bot wall)"
        )
    return text


async def fetch_jobs(
    handle: str, *, company_slug: str, client: httpx.AsyncClient | None = None
) -> list[Job]:
    owns = client is None
    client = client or httpx.AsyncClient()
    try:
        xml = await _fetch_xml(client, handle)
    finally:
        if owns:
            await client.aclose()
    return parse_jobs(xml, company_slug, handle)
