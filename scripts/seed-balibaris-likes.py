"""Seed Balibaris-adjacent brands: French/EU premium menswear, contemporary
casual, niche perfume, premium leather goods, premium home/decor.

Stricter probe than seed-fashion-beauty.py — only base slug + no-hyphen
variant, AND a sample-job fetch must contain the brand name. Filters out
the noise we caught in the earlier round (paco/charlotte/nemo etc).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TARGET_DIR = ROOT / "companies" / "tech"
USER_AGENT = "ai-startups-bot/0.1 (+https://github.com/Aramente/eu-tech-jobs)"

# Balibaris-adjacent + the broader fashion/beauty/home set Kevin asked for.
# Each: (display name, ISO2, [industry_tags]).
BRANDS: list[tuple[str, str, list[str]]] = [
    # === Premium FR menswear (closest peers to Balibaris) ===
    ("De Fursac", "FR", ["fashion"]),
    ("Officine Generale", "FR", ["fashion"]),
    ("IZAC", "FR", ["fashion"]),
    ("Eden Park", "FR", ["fashion"]),
    ("Smalto", "FR", ["fashion", "retail-luxury"]),
    ("Father Sons", "FR", ["fashion"]),
    ("Husbands Paris", "FR", ["fashion"]),
    ("Jacques Marie Mage", "FR", ["fashion", "retail-luxury"]),
    ("Husbands", "FR", ["fashion"]),
    ("Maison Standards", "FR", ["fashion"]),
    ("Drake's", "GB", ["fashion", "retail-luxury"]),
    ("Begg Co", "GB", ["fashion", "textile"]),
    ("Pierre Cardin", "FR", ["fashion"]),
    ("Cerruti 1881", "IT", ["fashion"]),
    ("Lardini", "IT", ["fashion"]),
    ("Boglioli", "IT", ["fashion"]),
    ("Eleventy", "IT", ["fashion"]),
    ("Caruso", "IT", ["fashion"]),
    ("Tagliatore", "IT", ["fashion"]),
    ("Drumohr", "IT", ["fashion", "textile"]),
    ("Mackintosh", "GB", ["fashion"]),

    # === Premium FR / EU contemporary unisex (Kitsuné, Kenzo lookalikes) ===
    ("Maison Kitsune", "FR", ["fashion"]),
    ("AMI Paris", "FR", ["fashion"]),  # already attempted; safe
    ("APC", "FR", ["fashion"]),  # Atelier de Production et Création
    ("Officine Universelle Buly", "FR", ["beauty", "home"]),
    ("Lemaire", "FR", ["fashion"]),
    ("Dries Van Noten", "BE", ["fashion"]),
    ("Acne Studios", "SE", ["fashion"]),
    ("Studio Nicholson", "GB", ["fashion"]),
    ("Folk", "GB", ["fashion"]),
    ("Norse Projects", "DK", ["fashion"]),
    ("Wood Wood", "DK", ["fashion"]),
    ("YMC", "GB", ["fashion"]),
    ("Albam", "GB", ["fashion"]),
    ("Mr Porter", "GB", ["fashion", "retail-luxury"]),
    ("End Clothing", "GB", ["fashion", "retail-luxury"]),

    # === FR contemporary women's (sister brands, Camille might browse) ===
    ("Sezane", "FR", ["fashion"]),
    ("Soeur", "FR", ["fashion"]),
    ("Sandro", "FR", ["fashion"]),
    ("Maje", "FR", ["fashion"]),
    ("Claudie Pierlot", "FR", ["fashion"]),
    ("The Kooples", "FR", ["fashion"]),
    ("Ba sh", "FR", ["fashion"]),
    ("Rouje", "FR", ["fashion"]),
    ("American Vintage", "FR", ["fashion"]),
    ("Comptoir des Cotonniers", "FR", ["fashion"]),
    ("IKKS", "FR", ["fashion"]),
    ("Aigle", "FR", ["fashion"]),

    # === Premium leather goods / accessories (FR/IT) ===
    ("Le Tanneur", "FR", ["fashion"]),
    ("Polene", "FR", ["fashion"]),
    ("Manu Atelier", "TR", ["fashion"]),
    ("Demellier", "GB", ["fashion"]),
    ("Wandler", "NL", ["fashion"]),
    ("By Far", "BG", ["fashion"]),
    ("Polite Worldwide", "US", ["fashion"]),

    # === Niche FR perfumeries (Camille likely cares) ===
    ("Diptyque", "FR", ["perfume", "home"]),
    ("Frederic Malle", "FR", ["perfume"]),
    ("Caron", "FR", ["perfume"]),
    ("Goutal Paris", "FR", ["perfume"]),
    ("Houbigant", "FR", ["perfume"]),
    ("BDK Parfums", "FR", ["perfume"]),
    ("By Kilian", "FR", ["perfume"]),
    ("Fragonard", "FR", ["perfume", "beauty"]),
    ("Molinard", "FR", ["perfume"]),
    ("Detaille 1905", "FR", ["perfume", "beauty"]),
    ("MFK", "FR", ["perfume"]),  # Maison Francis Kurkdjian abbrev
    ("Cire Trudon", "FR", ["perfume", "home"]),

    # === Indie FR beauty (Camille likely browses) ===
    ("Aroma Zone", "FR", ["beauty"]),
    ("Typology", "FR", ["beauty"]),
    ("Manucurist", "FR", ["beauty"]),
    ("Respire", "FR", ["beauty"]),
    ("Indemne", "FR", ["beauty"]),
    ("La Bouche Rouge", "FR", ["beauty"]),
    ("Polaar", "FR", ["beauty"]),
    ("Patyka", "FR", ["beauty"]),
    ("Christophe Robin", "FR", ["beauty"]),
    ("Embryolisse", "FR", ["beauty"]),
    ("Filorga", "FR", ["beauty"]),

    # === Premium FR home / interior / table ===
    ("Sarah Lavoine", "FR", ["interior-design", "home", "decoration"]),
    ("Astier de Villatte", "FR", ["home", "interior-design"]),
    ("Caravane", "FR", ["home", "interior-design"]),
    ("AM PM", "FR", ["home", "interior-design"]),  # La Redoute branch
    ("Bonnetier", "FR", ["home"]),
    ("MERCI", "FR", ["fashion", "home", "decoration"]),
    ("Bonton", "FR", ["fashion", "home"]),
    ("Maison Sarah Lavoine", "FR", ["interior-design", "decoration"]),

    # === Major mass + premium retail (Camille for pricing baseline) ===
    ("Mango", "ES", ["fashion"]),
    ("COS", "SE", ["fashion"]),
    ("Other Stories", "SE", ["fashion"]),
    ("Arket", "SE", ["fashion"]),
    ("Massimo Dutti", "ES", ["fashion"]),
    ("HM", "SE", ["fashion"]),  # short slug

    # === Athleisure / sustainable (premium-FR) ===
    ("Veja", "FR", ["fashion"]),  # already in earlier list
    ("LOOM", "FR", ["fashion"]),
    ("Asphalte", "FR", ["fashion"]),
    ("Hopaal", "FR", ["fashion"]),
    ("1083", "FR", ["fashion", "textile"]),
    ("Maison Bonneterie", "FR", ["fashion", "textile"]),
    ("Paire", "FR", ["fashion"]),

    # === EU minimal / premium designers ===
    ("Jil Sander", "DE", ["fashion", "retail-luxury"]),
    ("Margaret Howell", "GB", ["fashion"]),
    ("Toteme", "SE", ["fashion"]),
    ("Khaite", "US", ["fashion", "retail-luxury"]),
    ("The Row", "US", ["fashion", "retail-luxury"]),

    # === Italian premium tailoring + casual ===
    ("Etro", "IT", ["fashion", "retail-luxury"]),
    ("Massimo Alba", "IT", ["fashion"]),
    ("Aspesi", "IT", ["fashion"]),
    ("Brioni", "IT", ["fashion", "retail-luxury"]),  # may be in earlier list
    ("Canali", "IT", ["fashion"]),
    ("Corneliani", "IT", ["fashion"]),

    # === French department / multi-brand ===
    ("Galeries Lafayette Group", "FR", ["fashion", "beauty", "retail-luxury"]),
    ("Le Bon Marche Paris", "FR", ["retail-luxury"]),
    ("BHV Marais", "FR", ["fashion", "home"]),

    # === FR niche kids ===
    ("Bonpoint", "FR", ["fashion"]),
    ("Tartine et Chocolat", "FR", ["fashion"]),
    ("Cyrillus Enfants", "FR", ["fashion"]),
]


def _slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:48] or "unknown"


def _existing_slugs() -> set[str]:
    return {p.stem for p in (ROOT / "companies").rglob("*.yaml") if "_drafts" not in p.parts}


def _verify_brand_match(name: str, provider: str, handle: str) -> bool:
    sample_url_map = {
        "greenhouse": f"https://boards-api.greenhouse.io/v1/boards/{handle}/jobs?content=true",
        "lever": f"https://api.lever.co/v0/postings/{handle}?mode=json",
        "ashby": f"https://api.ashbyhq.com/posting-api/job-board/{handle}",
        "workable": f"https://apply.workable.com/api/v1/widget/accounts/{handle}",
        "smartrecruiters": f"https://api.smartrecruiters.com/v1/companies/{handle}/postings?limit=5",
        "recruitee": f"https://{handle}.recruitee.com/api/offers/",
        "personio": f"https://{handle}.jobs.personio.com/xml",
    }
    url = sample_url_map.get(provider)
    if not url:
        return False
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=8) as r:
            body = r.read().decode("utf-8", errors="replace")
    except Exception:
        return False
    name_norm = re.sub(r"[^a-z]", "", name.lower())
    body_norm = re.sub(r"[^a-z]", "", body.lower())[:200000]
    return name_norm in body_norm


def _probe_ats(handle: str) -> tuple[str, str] | None:
    candidates = [
        ("greenhouse", f"https://boards-api.greenhouse.io/v1/boards/{handle}/jobs",
         lambda d: bool(d.get("jobs"))),
        ("lever", f"https://api.lever.co/v0/postings/{handle}?mode=json",
         lambda d: isinstance(d, list) and len(d) > 0),
        ("ashby", f"https://api.ashbyhq.com/posting-api/job-board/{handle}",
         lambda d: bool(d.get("jobs") if isinstance(d, dict) else None)),
        ("workable", f"https://apply.workable.com/api/v1/widget/accounts/{handle}",
         lambda d: bool(d.get("jobs") or d.get("totalCount"))),
        ("smartrecruiters",
         f"https://api.smartrecruiters.com/v1/companies/{handle}/postings?limit=5",
         lambda d: int(d.get("totalFound", 0)) > 0),
        ("recruitee", f"https://{handle}.recruitee.com/api/offers/",
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
                    return provider, handle
        except Exception:
            continue
    try:
        url = f"https://{handle}.jobs.personio.com/xml"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=6) as r:
            if r.status == 200:
                body = r.read(2048).decode("utf-8", errors="replace")
                if "<position" in body or "<job" in body:
                    return "personio", handle
    except Exception:
        pass
    return None


def _find_career_url(name: str, base_slug: str) -> str | None:
    """For brands without a discoverable ATS, find a careers page on
    their main site by trying common paths. Returns the first that
    responds 200 with non-trivial HTML body. The custom_page LLM
    extractor takes it from there.
    """
    # Build candidate domains from the brand name.
    domain_variants = [
        base_slug,
        base_slug.replace("-", ""),
        base_slug + "paris" if "paris" not in base_slug else base_slug,
    ]
    # Common careers paths in EN + FR.
    paths = [
        "/careers", "/careers/", "/jobs", "/jobs/",
        "/recrutement", "/recrutement/",
        "/nous-rejoindre", "/nous-rejoindre/",
        "/about/careers", "/about-us/careers",
        "/company/careers",
        "/",  # homepage as last-resort — LLM may still find a careers link
    ]
    for d in domain_variants:
        for tld in ("com", "fr"):
            url_root = f"https://www.{d}.{tld}"
            # Quick HEAD probe to confirm the domain resolves at all.
            try:
                req = urllib.request.Request(
                    url_root, headers={"User-Agent": USER_AGENT}, method="HEAD"
                )
                with urllib.request.urlopen(req, timeout=6):
                    pass
            except Exception:
                continue
            for path in paths:
                full = url_root + path
                try:
                    req = urllib.request.Request(full, headers={"User-Agent": USER_AGENT})
                    with urllib.request.urlopen(req, timeout=8) as r:
                        if r.status != 200:
                            continue
                        body = r.read(40000).decode("utf-8", errors="replace")
                        # Heuristic: page should have multiple "job" / "career" /
                        # "recrutement" mentions OR a list element with
                        # title-like content. Cheap and false-positive prone
                        # but the LLM will validate downstream.
                        body_l = body.lower()
                        if any(kw in body_l for kw in ("careers", "recrutement", "nous-rejoindre", "jobs", "openings")):
                            return full
                except Exception:
                    continue
            # Domain resolves but no careers URL found — return root for LLM.
            return url_root
    return None


def _probe_one(brand: tuple[str, str, list[str]]):
    name, country, tags = brand
    base = _slugify(name)
    variants = [base, base.replace("-", "")]
    variants = list(dict.fromkeys(v for v in variants if v))
    # Pass 1: structured ATS probe.
    for handle in variants:
        found = _probe_ats(handle)
        if not found:
            continue
        provider, h = found
        if _verify_brand_match(name, provider, h):
            return ("ats", base, name, country, tags, provider, h)
    # Pass 2: career_url fallback (custom_page LLM extractor).
    career_url = _find_career_url(name, base)
    if career_url:
        return ("career_url", base, name, country, tags, career_url)
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()

    existing = _existing_slugs()
    print(f"Existing seed: {len(existing)} companies")
    new_brands = [b for b in BRANDS if _slugify(b[0]) not in existing]
    print(f"Probing {len(new_brands)} new candidates ({len(BRANDS)} total)…")

    hits: list = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as ex:
        for r in ex.map(_probe_one, new_brands):
            if r:
                hits.append(r)

    ats_hits = [r for r in hits if r[0] == "ats"]
    cp_hits = [r for r in hits if r[0] == "career_url"]
    print(f"\n{len(ats_hits)} ATS hits:")
    for kind, slug, name, country, tags, prov, h in ats_hits:
        print(f"  + {slug:30s} {prov}:{h:25s} ({country}, {','.join(tags)})")
    print(f"\n{len(cp_hits)} custom-page candidates (career_url, LLM-extracted):")
    for entry in cp_hits:
        kind, slug, name, country, tags, career_url = entry
        print(f"  + {slug:30s} {career_url}")

    if not args.commit:
        print("\n(dry-run — pass --commit to write YAMLs)")
        return 0

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for entry in hits:
        kind = entry[0]
        if kind == "ats":
            _, slug, name, country, tags, prov, h = entry
            data = {
                "name": name,
                "country": country,
                "categories": ["tech"],
                "industry_tags": tags,
                "ats": {"provider": prov, "handle": h},
                "notes": "Curated for /camille/ — Balibaris-adjacent fashion/beauty/home.",
            }
        else:
            _, slug, name, country, tags, career_url = entry
            data = {
                "name": name,
                "country": country,
                "categories": ["tech"],
                "industry_tags": tags,
                "career_url": career_url,
                "notes": "Custom-page LLM extractor — no ATS detected. Curated for /camille/.",
            }
        path = TARGET_DIR / f"{slug}.yaml"
        if path.exists():
            continue
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
        written += 1
    print(f"\n+{written} YAMLs written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
