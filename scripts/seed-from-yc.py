"""Pull EU companies from YC's public Algolia directory, auto-probe ATS,
write YAML drafts. Every YC company uses a modern ATS by default —
this is the highest-density "cool startup" source we have.

Usage:
    python scripts/seed-from-yc.py             # writes to companies/_drafts/
    python scripts/seed-from-yc.py --commit    # writes to companies/{ai,tech}/

Source: https://www.ycombinator.com/companies?regions=Europe
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DRAFTS_DIR = ROOT / "companies" / "_drafts"
TECH_DIR = ROOT / "companies" / "tech"
AI_DIR = ROOT / "companies" / "ai"

USER_AGENT = "ai-startups-bot/0.1 (+https://github.com/Aramente/eu-tech-jobs)"

# Public YC Algolia keys — leaked in the live www.ycombinator.com HTML.
ALGOLIA_APP = "45BWZJ1SGC"
ALGOLIA_KEY = (
    "NzllNTY5MzJiZGM2OTY2ZTQwMDEzOTNhYWZiZGRjODlhYzVkNjBmOGRjNzJiMWM4ZTU0ZDlhYT"
    "ZjOTJiMjlhMWFuYWx5dGljc1RhZ3M9eWNkYyZyZXN0cmljdEluZGljZXM9WUNDb21wYW55X3By"
    "b2R1Y3Rpb24lMkNZQ0NvbXBhbnlfQnlfTGF1bmNoX0RhdGVfcHJvZHVjdGlvbiZ0YWdGaWx0Z"
    "XJzPSU1QiUyMnljZGNfcHVibGljJTIyJTVE"
)
INDEX = "YCCompany_production"
URL = f"https://{ALGOLIA_APP}-dsn.algolia.net/1/indexes/{INDEX}/query"


def _slugify(name: str) -> str:
    s = (name or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:48] or "unknown"


def _existing_slugs() -> set[str]:
    slugs = set()
    for p in (ROOT / "companies").rglob("*.yaml"):
        if "_drafts" in p.parts:
            continue
        slugs.add(p.stem)
    return slugs


def _fetch_yc_eu() -> list[dict]:
    """Algolia paginated pull of EU YC companies."""
    out = []
    for page in range(0, 5):  # 500 cap is plenty (~390 known EU companies)
        body = json.dumps({
            "params": f"hitsPerPage=100&page={page}&filters=regions:Europe",
        }).encode()
        req = urllib.request.Request(
            URL,
            data=body,
            headers={
                "X-Algolia-Application-Id": ALGOLIA_APP,
                "X-Algolia-API-Key": ALGOLIA_KEY,
                "Referer": "https://www.ycombinator.com/",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read())
        except Exception as exc:
            print(f"  ⚠ YC page {page} failed: {exc}")
            break
        hits = data.get("hits") or []
        if not hits:
            break
        out.extend(hits)
        if len(hits) < 100:
            break
    return out


def _categories_for(yc_co: dict) -> list[str]:
    industries = [i.lower() for i in (yc_co.get("industries") or [])]
    if any("ai" in i or "ml" in i or "machine" in i for i in industries):
        return ["ai"]
    return ["tech"]


def _country_iso2(loc: str) -> str:
    """Best-effort country code from YC location string. Returns 'XX' if unknown."""
    if not loc:
        return "XX"
    table = {
        "France": "FR", "Paris": "FR",
        "Germany": "DE", "Berlin": "DE", "Munich": "DE",
        "United Kingdom": "GB", "UK": "GB", "London": "GB",
        "Spain": "ES", "Madrid": "ES", "Barcelona": "ES",
        "Netherlands": "NL", "Amsterdam": "NL",
        "Sweden": "SE", "Stockholm": "SE",
        "Ireland": "IE", "Dublin": "IE",
        "Italy": "IT", "Milan": "IT",
        "Portugal": "PT", "Lisbon": "PT",
        "Poland": "PL", "Warsaw": "PL",
        "Czech": "CZ", "Prague": "CZ",
        "Austria": "AT", "Vienna": "AT",
        "Switzerland": "CH", "Zurich": "CH", "Zürich": "CH",
        "Estonia": "EE", "Tallinn": "EE",
        "Lithuania": "LT", "Vilnius": "LT",
        "Latvia": "LV", "Riga": "LV",
        "Belgium": "BE", "Brussels": "BE",
        "Denmark": "DK", "Copenhagen": "DK",
        "Finland": "FI", "Helsinki": "FI",
        "Norway": "NO", "Oslo": "NO",
        "Romania": "RO",
        "Greece": "GR",
        "Bulgaria": "BG",
    }
    for needle, code in table.items():
        if needle in loc:
            return code
    return "XX"


def _probe_ats(slug: str) -> tuple[str, str] | None:
    """Probe slug across providers, require non-empty job results."""
    candidates = [
        ("greenhouse", f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
         lambda d: bool(d.get("jobs"))),
        ("lever", f"https://api.lever.co/v0/postings/{slug}?mode=json",
         lambda d: isinstance(d, list) and len(d) > 0),
        ("ashby", f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
         lambda d: bool((d.get("jobs") if isinstance(d, dict) else None))),
        ("workable", f"https://apply.workable.com/api/v1/widget/accounts/{slug}",
         lambda d: bool(d.get("jobs") or d.get("totalCount"))),
        ("smartrecruiters",
         f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=5",
         lambda d: int(d.get("totalFound", 0)) > 0),
        ("recruitee", f"https://{slug}.recruitee.com/api/offers/",
         lambda d: bool(d.get("offers"))),
    ]
    for provider, url, has_jobs in candidates:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=6) as r:
                if r.status != 200:
                    continue
                try:
                    data = json.loads(r.read())
                except Exception:
                    continue
                if has_jobs(data):
                    return provider, slug
        except Exception:
            continue
    # Personio (XML)
    try:
        url = f"https://{slug}.jobs.personio.com/xml"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=6) as r:
            if r.status == 200:
                body = r.read(2048).decode("utf-8", errors="replace")
                if "<position" in body or "<job" in body:
                    return "personio", slug
    except Exception:
        pass
    return None


def _probe_one(yc_co: dict) -> tuple[dict, tuple[str, str] | None]:
    name = yc_co.get("name", "")
    slug = _slugify(name)
    if not slug:
        return yc_co, None
    found = _probe_ats(slug)
    if not found:
        # Try slug without hyphens
        alt = slug.replace("-", "")
        if alt != slug:
            found = _probe_ats(alt)
    return yc_co, found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--max", type=int, default=500)
    args = parser.parse_args()

    existing = _existing_slugs()
    print(f"Already seeded: {len(existing)} companies")

    print("Pulling EU YC companies via Algolia…")
    yc = _fetch_yc_eu()
    print(f"  ✓ {len(yc)} EU YC companies fetched")

    new = [c for c in yc if _slugify(c.get("name", "")) not in existing]
    new = new[:args.max]
    print(f"  Not yet seeded: {len(new)}; probing ATS for each…")

    out_dir = TECH_DIR if args.commit else DRAFTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    hits = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        for yc_co, found in ex.map(_probe_one, new):
            if not found:
                continue
            provider, handle = found
            name = yc_co.get("name", "")
            slug = _slugify(name)
            cats = _categories_for(yc_co)
            country = _country_iso2(
                yc_co.get("all_locations") or yc_co.get("location") or ""
            )
            target_dir = AI_DIR if "ai" in cats and args.commit else out_dir
            if args.commit:
                target_dir.mkdir(parents=True, exist_ok=True)
            data = {
                "name": name,
                "country": country,
                "categories": cats,
                "ats": {"provider": provider, "handle": handle},
                "notes": f"YC {yc_co.get('batch', '?')} — discovered via YC EU directory",
            }
            path = target_dir / f"{slug}.yaml"
            if path.exists():
                continue
            path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
            hits += 1
            print(f"  + {slug:35s} {provider}:{handle:30s} ({country}, YC {yc_co.get('batch', '?')})")

    print(f"\n✓ {hits} new YC EU company YAMLs in {target_dir.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
