"""Welcome to the Jungle (WTTJ) aggregator.

Largest French job platform. Public Algolia keys are leaked in the
window.env script tag of every page. Index `wk_cms_jobs_production`
holds ~108k current EU jobs (Apr 2026). We paginate per EU country to
maximise coverage within Algolia's per-query 1000-hit cap.

License posture: WTTJ ToS forbids scraping. We're consuming the public
read-only Algolia keys their site uses for visitors, with rate limits
matching what their own UI hits. Set ATTRIBUTION on yielded jobs and
keep the extractor easy to disable if a complaint lands.
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

NAME = "wttj"
USER_AGENT = "ai-startups-bot/0.1 (+https://github.com/Aramente/eu-tech-jobs)"

# Public Algolia keys — leaked in WTTJ's own window.env script tag.
ALGOLIA_APP = "CSEKHVMS53"
ALGOLIA_KEY = "4bd8f6215d0cc52b26430765769e65a0"
INDEX = "wk_cms_jobs_production"
URL = f"https://{ALGOLIA_APP}-dsn.algolia.net/1/indexes/{INDEX}/query"

# EU member-state ISO-2 codes plus a few near-EU we care about.
EU_COUNTRIES = [
    "FR", "DE", "GB", "ES", "IT", "NL", "BE", "SE", "DK", "FI", "NO",
    "IE", "PT", "PL", "CZ", "AT", "CH", "EE", "LT", "LV", "GR", "RO",
    "BG", "HU", "SK", "SI", "HR", "LU", "IS", "CY", "MT", "UA",
]

# Algolia caps per-query results at paginationLimitedTo (1000 by default).
HITS_PER_PAGE = 100
MAX_PAGES = 10  # → up to 1000 most recent per country


def _slugify(name: str) -> str:
    s = (name or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:48] or "unknown"


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value))
    except (ValueError, OverflowError, OSError):
        return None
    return None


def _job_url(org_slug: str, job_slug: str, lang: str) -> str:
    lang = lang or "en"
    if lang not in {"en", "fr", "es", "cs", "sk"}:
        lang = "en"
    return f"https://www.welcometothejungle.com/{lang}/companies/{org_slug}/jobs/{job_slug}"


def _remote_policy(remote: str | None, offices: list[dict] | None) -> str | None:
    if remote == "fulltime":
        return "remote"
    if remote == "partial":
        return "hybrid"
    if not offices:
        return None
    return None


def _location(offices: list[dict] | None) -> str:
    if not offices:
        return ""
    parts = []
    for o in offices[:3]:
        city = o.get("city")
        country = o.get("country")
        if city and country:
            parts.append(f"{city}, {country}")
        elif city:
            parts.append(city)
        elif country:
            parts.append(country)
    return "; ".join(parts)


def _company_country(offices: list[dict] | None) -> str:
    if not offices:
        return "XX"
    cc = offices[0].get("country_code")
    return cc or "XX"


# Tech-relevance gate. WTTJ has every kind of job — chefs, hotel staff,
# baristas, etc. We only want tech / data / AI / business / sales /
# product / design roles. Title or sectors must match.
_TECH_TITLE = re.compile(
    r"\b(engineer|engineering|developer|software|backend|frontend|fullstack|"
    r"full[ -]?stack|devops|sre|cloud|platform|infrastructure|architect|"
    r"data|machine\s*learning|ml\s|\bai\b|llm|nlp|product|design|ux|ui|"
    r"sales|account|marketing|growth|content|seo|sem|finance|controller|"
    r"hr|recruit|talent|people|operations|\bops\b|legal|counsel|"
    r"consultant|business|customer|support|qa|security|research|"
    r"scientist|analyst|technicien|technique|tech|saas|mobile|cybersec)"
    r"\b",
    re.I,
)
_TECH_SECTOR_KEYWORDS = (
    "tech", "saas", "data", "ai", "fintech", "edtech", "healthtech",
    "biotech", "mobility", "marketplace", "consulting", "cyber",
    "communication", "media", "industrie", "industry", "logistique",
    "logistics", "advertising", "transport",
)


def _is_tech_relevant(hit: dict) -> bool:
    """True when WTTJ hit is plausibly an EU tech-ecosystem role.
    Conservative — drops obvious noise (chefs, baristas, housekeepers,
    medical/wellness staff) without losing tech-adjacent business roles."""
    title = (hit.get("name") or "")
    if _TECH_TITLE.search(title):
        return True
    # Sector check — WTTJ tags every job with parent + child sectors.
    sectors = hit.get("sectors_name", {}).get("en", []) or []
    for s in sectors:
        for k, v in (s.items() if isinstance(s, dict) else []):
            text = f"{k} {v}".lower()
            if any(kw in text for kw in _TECH_SECTOR_KEYWORDS):
                return True
    return False


@retry(
    retry=retry_if_exception_type((httpx.TransportError, ExtractorTransientError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def _fetch_page(
    client: httpx.AsyncClient, country: str, page: int, query: str = ""
) -> dict[str, Any]:
    parts = [f"hitsPerPage={HITS_PER_PAGE}", f"page={page}"]
    parts.append(f"filters=offices.country_code:{country}")
    if query:
        # Algolia query terms are appended via the standard "query" param.
        from urllib.parse import quote_plus
        parts.append(f"query={quote_plus(query)}")
    body = {"params": "&".join(parts)}
    resp = await client.post(
        URL,
        json=body,
        headers={
            "X-Algolia-Application-Id": ALGOLIA_APP,
            "X-Algolia-API-Key": ALGOLIA_KEY,
            "Referer": "https://www.welcometothejungle.com/",
            "Origin": "https://www.welcometothejungle.com",
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
        },
        timeout=30.0,
    )
    if resp.status_code >= 500:
        raise ExtractorTransientError(f"WTTJ {resp.status_code}")
    if resp.status_code >= 400:
        raise ExtractorTransientError(f"WTTJ {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def _hit_to_job(hit: dict, company_slug: str, source_country: str) -> Job | None:
    org_slug = hit.get("organization", {}).get("slug")
    job_slug = hit.get("slug")
    title = hit.get("name") or ""
    if not org_slug or not job_slug or not title:
        return None
    url = _job_url(org_slug, job_slug, hit.get("language") or "en")
    job_id = Job.make_id(company_slug, url)
    return Job(
        id=job_id,
        company_slug=company_slug,
        title=title.strip(),
        url=url,
        location=_location(hit.get("offices")),
        remote_policy=_remote_policy(hit.get("remote"), hit.get("offices")),
        posted_at=_parse_dt(hit.get("published_at")),
        scraped_at=utcnow(),
        description_md="",
        source=NAME,
    )


def _hit_to_company(hit: dict) -> tuple[str, Company] | None:
    org = hit.get("organization") or {}
    org_slug = org.get("slug")
    org_name = org.get("name")
    if not org_slug or not org_name:
        return None
    slug = f"wttj-{_slugify(org_slug)}"
    return slug, Company(
        slug=slug,
        name=org_name,
        country=_company_country(hit.get("offices")),
        categories=["tech"],
        ats=None,
        career_url=f"https://www.welcometothejungle.com/en/companies/{org_slug}",
        notes=f"Aggregated from Welcome to the Jungle ({org.get('nb_employees', '?')} employees)",
    )


# Targeted queries to surface roles that Algolia's default custom ranking
# buries. Each query runs paginated alongside the country crawl. These cost
# little and noticeably lift hard-to-find buckets like Talent Acquisition.
TARGETED_QUERIES = [
    "talent acquisition",
    "recruiter",
    "people partner",
    "engineering manager",
]


async def fetch_all(
    *, client: httpx.AsyncClient | None = None
) -> tuple[list[Company], list[Job]]:
    """Fetch top-N most-recent jobs across EU countries from WTTJ.

    Two passes:
      1. Default-ranking crawl per EU country (most "relevant" by WTTJ's
         own ranking — captures featured / promoted jobs first).
      2. Targeted query crawl for hard-to-find buckets (TA, recruiter,
         people partner, eng manager) per top-coverage country, to surface
         long-tail roles the default ranking buries.
    """
    owns = client is None
    client = client or httpx.AsyncClient()
    companies: dict[str, Company] = {}
    jobs: list[Job] = []
    seen_ids: set[str] = set()

    def _absorb(hits: list[dict], country: str) -> int:
        added = 0
        for hit in hits:
            # Drop obvious non-tech (chefs, hotel staff, wellness, etc).
            if not _is_tech_relevant(hit):
                continue
            pair = _hit_to_company(hit)
            if not pair:
                continue
            slug, company = pair
            if slug not in companies:
                companies[slug] = company
            job = _hit_to_job(hit, slug, country)
            if job and job.id not in seen_ids:
                jobs.append(job)
                seen_ids.add(job.id)
                added += 1
        return added

    try:
        # Pass 1: default ranking per country.
        for country in EU_COUNTRIES:
            country_jobs = 0
            for page in range(MAX_PAGES):
                try:
                    payload = await _fetch_page(client, country, page)
                except Exception as exc:
                    logger.warning("WTTJ %s page %d failed: %s", country, page, exc)
                    break
                hits = payload.get("hits") or []
                if not hits:
                    break
                country_jobs += _absorb(hits, country)
                if len(hits) < HITS_PER_PAGE:
                    break
            logger.info("WTTJ %s → +%d jobs (pass 1)", country, country_jobs)

        # Pass 2: targeted queries — top-5 EU countries × 4 queries × 5 pages = 100 calls max.
        targeted_countries = ["FR", "DE", "GB", "ES", "NL"]
        for country in targeted_countries:
            for q in TARGETED_QUERIES:
                added = 0
                for page in range(5):  # 500 max per (country, query)
                    try:
                        payload = await _fetch_page(client, country, page, query=q)
                    except Exception as exc:
                        logger.warning(
                            "WTTJ %s %r page %d failed: %s", country, q, page, exc
                        )
                        break
                    hits = payload.get("hits") or []
                    if not hits:
                        break
                    added += _absorb(hits, country)
                    if len(hits) < HITS_PER_PAGE:
                        break
                if added:
                    logger.info("WTTJ %s %r → +%d (pass 2)", country, q, added)
    finally:
        if owns:
            await client.aclose()
    logger.info(
        "WTTJ total: %d jobs across %d organizations",
        len(jobs),
        len(companies),
    )
    return list(companies.values()), jobs
