"""fashionjobs.com (FR) aggregator.

Cloudflare-protected — requires the same stealth Playwright fallback the
custom_page extractor uses. Listing pages SSR offer URLs in the form
`/emploi/<company-slug>/<title-slug>,<id>.html`, which is enough to
build Job + Company records without per-offer fetches.

Tags every company `industry_tags=['fashion']` so the segregation in
site/src/lib/data.ts routes them to /camille/ and keeps them off the
public surface.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from pipeline.extractors.custom_page import _render_with_playwright
from pipeline.models import Company, Job, utcnow

logger = logging.getLogger(__name__)

NAME = "fashionjobs"

# Camille-relevant categories. Each tuple is (path-segment, numeric id).
# Buying = primary lane. Direction surfaces head-of-buying. Marketing +
# Création-Design hide a lot of "chef de produit" / brand manager roles.
CATEGORIES: list[tuple[str, int]] = [
    ("Achat", 16),
    ("Merchandising", 14),
    ("Marketing", 6),
    ("Creation-Design", 1),
    ("Direction", 15),
    ("Production-Qualite", 3),
]

OFFER_RE = re.compile(
    r'href="(https?://[^/]*fashionjobs\.com/emploi/([^/]+)/([^",]+),(\d+)\.html)"'
)


def _pretty_company(slug: str) -> str:
    """Turn `louis-vuitton-malletier` → `Louis Vuitton Malletier`."""
    return " ".join(p.capitalize() for p in slug.split("-") if p)


def _pretty_title(slug: str) -> str:
    """Turn `Alternance-assistant-acheteur-pap-femme` →
    `Alternance assistant acheteur pap femme`. Light touch — no de-
    abbreviation, no gendered-suffix stripping."""
    return slug.replace("-", " ").strip().capitalize()


async def fetch_all(
    *, client: httpx.AsyncClient | None = None
) -> tuple[list[Company], list[Job]]:
    """Render each Camille category listing, parse offer URLs, and emit
    Company + Job records tagged for /camille/."""
    companies: dict[str, Company] = {}
    jobs: list[Job] = []
    seen_ids: set[str] = set()

    for cat_name, cat_id in CATEGORIES:
        url = f"https://fr.fashionjobs.com/categorie/{cat_name},{cat_id}.html"
        try:
            html = await _render_with_playwright(url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("fashionjobs %s render failed: %s", cat_name, exc)
            continue
        if not html:
            logger.warning("fashionjobs %s returned empty render", cat_name)
            continue

        offers = OFFER_RE.findall(html)
        added = 0
        for full_url, co_slug, title_slug, _ext_id in offers:
            slug = f"fjr-{co_slug.lower()}"[:64]
            if not re.match(r"^[a-z0-9][a-z0-9\-]*$", slug):
                continue
            if slug not in companies:
                companies[slug] = Company(
                    slug=slug,
                    name=_pretty_company(co_slug),
                    country="FR",
                    categories=[],
                    industry_tags=["fashion"],
                    career_url=f"https://fr.fashionjobs.com/recrutement/{co_slug}.html",
                    notes="Aggregated from fashionjobs.com (Camille lane).",
                )
            job = Job(
                id=Job.make_id(slug, full_url),
                company_slug=slug,
                title=_pretty_title(title_slug),
                url=full_url,
                location="France",
                remote_policy=None,
                posted_at=None,
                scraped_at=utcnow(),
                description_md="",
                source=NAME,
            )
            if job.id in seen_ids:
                continue
            seen_ids.add(job.id)
            jobs.append(job)
            added += 1
        logger.info("fashionjobs %s → +%d jobs", cat_name, added)

    logger.info(
        "fashionjobs total: %d jobs across %d companies",
        len(jobs),
        len(companies),
    )
    return list(companies.values()), jobs
