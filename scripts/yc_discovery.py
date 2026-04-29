"""Pull YC company list, filter EU HQ, probe ATSes, emit drafts.

Run:
    uv run python scripts/yc_discovery.py [--all-batches]
Default: filters to last 6 batches (most actively hiring).
Output: companies/_drafts/<slug>.yaml for each ATS hit.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.probe_ats import emit_draft, normalize_slug, probe_all  # noqa: E402

API = "https://api.ycombinator.com/v0.1/companies"

# ISO 3166-1 alpha-2 codes for EU + EFTA + UK (post-Brexit, still EU-relevant)
EU_COUNTRIES = {
    "FR", "DE", "GB", "ES", "IT", "NL", "BE", "SE", "DK", "FI", "NO",
    "IE", "PT", "PL", "CZ", "AT", "CH", "EE", "LT", "LV", "GR", "RO",
    "BG", "HU", "SK", "SI", "HR", "LU", "MT", "CY", "IS",
}


_EU_KEYWORDS = (
    "france", "paris", "lyon", "marseille",
    "germany", "berlin", "munich", "münchen", "hamburg", "frankfurt",
    "uk", "united kingdom", "london", "manchester", "edinburgh",
    "spain", "madrid", "barcelona",
    "italy", "milan", "rome",
    "netherlands", "amsterdam", "rotterdam",
    "belgium", "brussels", "antwerp",
    "sweden", "stockholm",
    "denmark", "copenhagen",
    "finland", "helsinki",
    "norway", "oslo",
    "ireland", "dublin",
    "portugal", "lisbon",
    "poland", "warsaw", "krakow", "kraków",
    "czech", "prague",
    "austria", "vienna", "wien",
    "switzerland", "zurich", "zürich", "geneva",
    "estonia", "tallinn",
    "latvia", "riga",
    "lithuania", "vilnius",
    "greece", "athens",
    "romania", "bucharest",
    "bulgaria", "sofia",
    "hungary", "budapest",
    "slovakia", "bratislava",
    "slovenia", "ljubljana",
    "croatia", "zagreb",
    "luxembourg",
    "iceland", "reykjavik",
)


def is_eu_company(c: dict) -> bool:
    """Heuristic: EU-flagged by any text field referencing an EU country/city."""
    blobs: list[str] = []
    for key in ("country", "location"):
        v = c.get(key)
        if isinstance(v, str):
            blobs.append(v)
    for key in ("regions", "locations", "all_locations"):
        v = c.get(key)
        if isinstance(v, list):
            blobs.extend(str(x) for x in v if x)
    haystack = " ".join(blobs).lower()
    if not haystack:
        return False
    return any(kw in haystack for kw in _EU_KEYWORDS)


async def fetch_yc_companies() -> list[dict]:
    out: list[dict] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        page = 1
        while page < 200:
            r = await client.get(f"{API}?page={page}")
            if r.status_code != 200:
                break
            payload = r.json()
            companies = payload.get("companies") or []
            if not companies:
                break
            out.extend(companies)
            next_page = payload.get("nextPage")
            total_pages = payload.get("totalPages")
            if not next_page or (total_pages and page >= total_pages):
                break
            page += 1
    return out


async def main() -> None:
    print("Fetching YC company list…")
    all_companies = await fetch_yc_companies()
    print(f"Got {len(all_companies)} companies; filtering to EU HQ…")
    eu = [c for c in all_companies if is_eu_company(c)]
    print(f"{len(eu)} EU companies after filter")

    # Slugify each name (using YC's `slug` when available)
    slugs: set[str] = set()
    for c in eu:
        slug = c.get("slug") or normalize_slug(c.get("name") or "")
        if slug:
            slugs.add(slug)

    print(f"Probing {len(slugs)} candidate slugs against ATSes…")
    hits = await probe_all(sorted(slugs))

    print(f"\n{len(hits)} hits:")
    for slug, providers in sorted(hits.items(), key=lambda kv: -sum(kv[1].values())):
        path = emit_draft(slug, providers)
        total = sum(providers.values())
        rel = path.relative_to(Path(__file__).resolve().parents[1])
        print(f"  {slug:30}  {total:>4} jobs  {providers}  → {rel}")


if __name__ == "__main__":
    asyncio.run(main())
