"""Business of Fashion Careers aggregator.

BoF Careers (Madgex platform) lists ~3000 fashion/luxury/beauty jobs at
businessoffashion.com/careers/jobs/<page>/. The HTML cards expose
title + company logo alt + location, which is enough for the camille
lane. Every aggregator company is tagged industry_tags=['fashion'] so
they route off the public surface.

License posture: BoF is a public job board with no robots.txt block on
/careers/jobs/. We mimic a normal-rate browser; if a complaint lands,
disable by removing from AGGREGATORS.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import Any

import httpx

from pipeline.models import Company, Job, utcnow

logger = logging.getLogger(__name__)

NAME = "bof"
USER_AGENT = "ai-startups-bot/0.1 (+https://github.com/Aramente/eu-tech-jobs)"

BASE = "https://www.businessoffashion.com"
LISTING = BASE + "/careers/jobs/{page}/"

# BoF is global; filter to EU + Remote-EU at parse time. EU countries by
# their typical free-text suffix on Madgex listings.
_EU_COUNTRIES = re.compile(
    r"\b("
    r"France|United Kingdom|Germany|Italy|Spain|Netherlands|Belgium|"
    r"Sweden|Denmark|Finland|Norway|Ireland|Portugal|Poland|Czechia|"
    r"Czech Republic|Austria|Switzerland|Estonia|Lithuania|Latvia|"
    r"Greece|Romania|Bulgaria|Hungary|Slovakia|Slovenia|Croatia|"
    r"Luxembourg|Iceland|Cyprus|Malta|Ukraine"
    r")\b",
    re.I,
)
_REMOTE_EU = re.compile(
    r"\b(remote.*(europe|emea|eu)|europe.*remote|emea.*remote)\b", re.I
)
_REMOTE_GLOBAL = re.compile(r"\b(worldwide|global|anywhere|fully\s*remote)\b", re.I)

_EU_LOC_TO_CC = {
    "France": "FR", "United Kingdom": "GB", "Germany": "DE", "Italy": "IT",
    "Spain": "ES", "Netherlands": "NL", "Belgium": "BE", "Sweden": "SE",
    "Denmark": "DK", "Finland": "FI", "Norway": "NO", "Ireland": "IE",
    "Portugal": "PT", "Poland": "PL", "Czechia": "CZ", "Czech Republic": "CZ",
    "Austria": "AT", "Switzerland": "CH", "Estonia": "EE", "Lithuania": "LT",
    "Latvia": "LV", "Greece": "GR", "Romania": "RO", "Bulgaria": "BG",
    "Hungary": "HU", "Slovakia": "SK", "Slovenia": "SI", "Croatia": "HR",
    "Luxembourg": "LU", "Iceland": "IS", "Cyprus": "CY", "Malta": "MT",
    "Ukraine": "UA",
}


def _slugify(name: str) -> str:
    s = (name or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:48] or "unknown"


def _is_eu_or_remote(location: str) -> tuple[bool, str | None, str | None]:
    """Return (keep, country_code, remote_policy)."""
    if not location:
        return (False, None, None)
    if _REMOTE_GLOBAL.search(location):
        return (True, "XX", "remote-global")
    if _REMOTE_EU.search(location):
        return (True, "XX", "remote-eu")
    m = _EU_COUNTRIES.search(location)
    if not m:
        return (False, None, None)
    return (True, _EU_LOC_TO_CC.get(m.group(1).title(), "XX"), None)


# Each item block in the listing page.
_ITEM_RE = re.compile(
    r'class="lister__item[^"]*"\s+id="item-(\d+)"(.+?)(?=class="lister__item|</section>|$)',
    re.S,
)
_TITLE_RE = re.compile(
    r'<a[^>]*href="\s*(/careers/job/\d+/[^"]+)\s*"[^>]*>\s*<span>([^<]+)</span>'
)
_LOC_RE = re.compile(r'lister__meta-item--location">([^<]+)</li>')
_BRAND_RE = re.compile(r'alt="([^"]+) logo"')


async def _fetch_page(client: httpx.AsyncClient, page: int) -> str:
    resp = await client.get(
        LISTING.format(page=page),
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
        timeout=30.0,
        follow_redirects=True,
    )
    if resp.status_code != 200:
        return ""
    return resp.text


def _parse_listing(html: str) -> list[dict[str, Any]]:
    out = []
    for match in _ITEM_RE.finditer(html):
        body = match.group(2)[:3000]
        title_m = _TITLE_RE.search(body)
        loc_m = _LOC_RE.search(body)
        brand_m = _BRAND_RE.search(body)
        if not title_m:
            continue
        path = title_m.group(1).strip()
        title_full = title_m.group(2).strip()
        brand = brand_m.group(1).strip() if brand_m else None
        # The visible title is "<Brand> <Job Title>" — strip the brand prefix
        # if it matches, so the role-pattern regex on /camille/ works cleanly.
        if brand and title_full.lower().startswith(brand.lower()):
            title = title_full[len(brand):].strip(" :,-")
        else:
            title = title_full
        out.append({
            "id": match.group(1),
            "url": BASE + path,
            "title": title or title_full,
            "brand": brand or "Unknown",
            "location": (loc_m.group(1).strip() if loc_m else ""),
        })
    return out


async def fetch_all(
    *, client: httpx.AsyncClient | None = None, max_pages: int = 160
) -> tuple[list[Company], list[Job]]:
    """Walk the BoF listing pages and emit Camille-tagged Company+Job records."""
    owns = client is None
    client = client or httpx.AsyncClient()
    companies: dict[str, Company] = {}
    jobs: list[Job] = []
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    try:
        for page in range(1, max_pages + 1):
            try:
                html = await _fetch_page(client, page)
            except Exception as exc:  # noqa: BLE001
                logger.warning("BoF page %d fetch error: %s", page, exc)
                continue
            if not html:
                break
            items = _parse_listing(html)
            if not items:
                # Last page reached or template changed.
                break
            added = 0
            for it in items:
                keep, cc, remote = _is_eu_or_remote(it["location"])
                if not keep:
                    continue
                if it["url"] in seen_urls:
                    continue
                seen_urls.add(it["url"])
                slug = f"bof-{_slugify(it['brand'])}"[:64]
                if not re.match(r"^[a-z0-9][a-z0-9\-]*$", slug):
                    continue
                if slug not in companies:
                    companies[slug] = Company(
                        slug=slug,
                        name=it["brand"],
                        country=cc or "XX",
                        categories=[],
                        industry_tags=["fashion"],
                        career_url=BASE + "/careers/",
                        notes="Aggregated from Business of Fashion Careers (Camille lane).",
                    )
                jid = Job.make_id(slug, it["url"])
                if jid in seen_ids:
                    continue
                seen_ids.add(jid)
                jobs.append(Job(
                    id=jid,
                    company_slug=slug,
                    title=it["title"],
                    url=it["url"],
                    location=it["location"],
                    remote_policy=remote,
                    posted_at=None,
                    scraped_at=utcnow(),
                    description_md="",
                    source=NAME,
                ))
                added += 1
            if added == 0 and page > 5:
                # Give it a few empty pages before bailing — early pages
                # are heavier UK/US, EU jobs cluster later.
                if all(not _is_eu_or_remote(it["location"])[0] for it in items):
                    pass  # keep going; UK jobs are useful too via _EU_COUNTRIES match
            if page % 20 == 0:
                logger.info("BoF page %d → +%d jobs total", page, len(jobs))
    finally:
        if owns:
            await client.aclose()
    logger.info(
        "BoF total: %d jobs across %d brands (EU + Remote)",
        len(jobs),
        len(companies),
    )
    return list(companies.values()), jobs
