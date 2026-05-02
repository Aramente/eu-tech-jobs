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

    # ========================================================================
    # EXPANSION 2026-05-02: max coverage of small/boutique brands Camille
    # plausibly likes. Permissive — script verifies against sample jobs and
    # falls back to career_url for the LLM extractor. Any non-resolving
    # candidate is silently dropped.
    # ========================================================================

    # === FR DTC menswear / new-gen (Asphalte territory) ===
    ("Bonnegueule", "FR", ["fashion"]),
    ("Le Slip Francais", "FR", ["fashion"]),
    ("Faguo", "FR", ["fashion"]),
    ("La Gentle Factory", "FR", ["fashion", "textile"]),
    ("Patine", "FR", ["fashion"]),
    ("Encre", "FR", ["fashion"]),
    ("Splice", "FR", ["fashion"]),
    ("17H10", "FR", ["fashion"]),
    ("Maison Standards", "FR", ["fashion"]),
    ("Maison Le Pape", "FR", ["fashion"]),
    ("Maison Cleo", "FR", ["fashion"]),
    ("Maison Father", "FR", ["fashion"]),
    ("Maison Pere", "FR", ["fashion"]),
    ("Maison Margiela", "FR", ["fashion", "retail-luxury"]),
    ("Maison Labiche", "FR", ["fashion"]),
    ("Maison Lejaby", "FR", ["fashion"]),
    ("Maison Ullens", "BE", ["fashion", "retail-luxury"]),
    ("Septieme Largeur", "FR", ["fashion"]),
    ("M Moustache", "FR", ["fashion"]),
    ("Bobbies", "FR", ["fashion"]),
    ("J M Weston", "FR", ["fashion", "retail-luxury"]),
    ("Paraboot", "FR", ["fashion"]),
    ("Heschung", "FR", ["fashion"]),
    ("Carmina", "ES", ["fashion"]),
    ("Carmina Shoemaker", "ES", ["fashion"]),
    ("Repetto", "FR", ["fashion"]),
    ("Bensimon", "FR", ["fashion"]),
    ("K Way", "FR", ["fashion"]),
    ("Saint James", "FR", ["fashion", "textile"]),
    ("Le Bourget", "FR", ["fashion", "textile"]),
    ("Le Coq Sportif", "FR", ["fashion"]),
    ("Lacoste", "FR", ["fashion", "retail-luxury"]),
    ("Eden Park Paris", "FR", ["fashion"]),
    ("Le Tanneur", "FR", ["fashion"]),
    ("Jonak", "FR", ["fashion"]),
    ("Bocage", "FR", ["fashion"]),
    ("Minelli", "FR", ["fashion"]),
    ("San Marina", "FR", ["fashion"]),
    ("Robert Clergerie", "FR", ["fashion"]),

    # === FR contemporary women's (small/mid) ===
    ("Sezane", "FR", ["fashion"]),
    ("Sezane Paris", "FR", ["fashion"]),
    ("Soeur", "FR", ["fashion"]),
    ("Rouje", "FR", ["fashion"]),
    ("Musier", "FR", ["fashion"]),
    ("Musier Paris", "FR", ["fashion"]),
    ("Anne Fontaine", "FR", ["fashion"]),
    ("Tara Jarmon", "FR", ["fashion"]),
    ("Ines de la Fressange", "FR", ["fashion"]),
    ("Cyrillus", "FR", ["fashion"]),
    ("Manoush", "FR", ["fashion"]),
    ("Mes Demoiselles", "FR", ["fashion"]),
    ("Roseanna", "FR", ["fashion"]),
    ("Vanessa Bruno", "FR", ["fashion"]),
    ("Iro", "FR", ["fashion"]),
    ("Iro Paris", "FR", ["fashion"]),
    ("Zadig et Voltaire", "FR", ["fashion"]),
    ("Zadig and Voltaire", "FR", ["fashion"]),
    ("Naf Naf", "FR", ["fashion"]),
    ("La Fee Maraboutee", "FR", ["fashion"]),
    ("Promod", "FR", ["fashion"]),
    ("Caroll", "FR", ["fashion"]),
    ("Pablo", "FR", ["fashion"]),
    ("Diane Von Furstenberg", "US", ["fashion"]),
    ("Sandro Paris", "FR", ["fashion"]),
    ("Realisation Par", "AU", ["fashion"]),

    # === FR contemporary designers (small ateliers) ===
    ("Jacquemus", "FR", ["fashion", "retail-luxury"]),
    ("Coperni", "FR", ["fashion", "retail-luxury"]),
    ("Marine Serre", "FR", ["fashion", "retail-luxury"]),
    ("Schiaparelli", "FR", ["fashion", "retail-luxury"]),
    ("Patou", "FR", ["fashion", "retail-luxury"]),
    ("Carven", "FR", ["fashion"]),
    ("Lanvin", "FR", ["fashion", "retail-luxury"]),
    ("Chloe", "FR", ["fashion", "retail-luxury"]),
    ("Mugler", "FR", ["fashion", "retail-luxury"]),
    ("Rabanne", "FR", ["fashion", "retail-luxury"]),
    ("Y Project", "FR", ["fashion"]),
    ("Casablanca", "FR", ["fashion"]),
    ("Avoc", "FR", ["fashion"]),
    ("Cordova", "AR", ["fashion"]),
    ("Cecilie Bahnsen", "DK", ["fashion"]),
    ("Stine Goya", "DK", ["fashion"]),
    ("Ganni", "DK", ["fashion"]),
    ("Holzweiler", "NO", ["fashion"]),
    ("Filippa K", "SE", ["fashion"]),
    ("Hope", "SE", ["fashion"]),
    ("Rains", "DK", ["fashion"]),

    # === EU contemporary unisex (Maison Kitsuné lookalikes) ===
    ("Studio Nicholson", "GB", ["fashion"]),
    ("Carhartt WIP", "DE", ["fashion"]),
    ("Stussy", "US", ["fashion"]),
    ("Marni", "IT", ["fashion", "retail-luxury"]),
    ("Comme des Garcons", "JP", ["fashion", "retail-luxury"]),
    ("Issey Miyake", "JP", ["fashion"]),
    ("Sacai", "JP", ["fashion"]),
    ("Yohji Yamamoto", "JP", ["fashion", "retail-luxury"]),

    # === FR niche perfume / indie beauty (deep cuts) ===
    ("Annick Goutal", "FR", ["perfume"]),
    ("L Artisan Parfumeur", "FR", ["perfume"]),
    ("Atelier Cologne", "FR", ["perfume"]),
    ("Editions de Parfums", "FR", ["perfume"]),
    ("Memo Paris", "FR", ["perfume"]),
    ("Lubin", "FR", ["perfume"]),
    ("Roger et Gallet", "FR", ["beauty", "perfume"]),
    ("Maison Crivelli", "FR", ["perfume"]),
    ("Akro", "FR", ["perfume"]),
    ("Ex Nihilo", "FR", ["perfume"]),
    ("Olfactive Studio", "FR", ["perfume"]),
    ("Histoires de Parfums", "FR", ["perfume"]),
    ("Nicolai Parfumeur Createur", "FR", ["perfume"]),
    ("Parfums de Marly", "FR", ["perfume"]),
    ("Etat Libre d Orange", "FR", ["perfume"]),
    ("Frapin", "FR", ["perfume"]),
    ("Astier de Villatte Paris", "FR", ["perfume", "home"]),
    ("Bois 1920", "IT", ["perfume"]),
    ("Tom Ford Beauty", "US", ["beauty", "perfume"]),
    ("Le Labo", "US", ["perfume"]),
    ("Byredo", "SE", ["perfume", "beauty"]),
    ("D S and Durga", "US", ["perfume"]),
    ("Maison Crivelli Paris", "FR", ["perfume"]),

    # === FR mass beauty (DTC + premium) ===
    ("Caudalie", "FR", ["beauty"]),
    ("Sisley Paris", "FR", ["beauty"]),
    ("Clarins", "FR", ["beauty"]),
    ("Yves Rocher", "FR", ["beauty"]),
    ("Bourjois", "FR", ["beauty"]),
    ("Make Up For Ever", "FR", ["beauty"]),
    ("Avene", "FR", ["beauty"]),
    ("La Roche Posay", "FR", ["beauty"]),
    ("Vichy", "FR", ["beauty"]),
    ("Nuxe", "FR", ["beauty"]),
    ("Klorane", "FR", ["beauty"]),
    ("Sanoflore", "FR", ["beauty"]),
    ("Garancia", "FR", ["beauty"]),
    ("Oolution", "FR", ["beauty"]),
    ("Bioderma", "FR", ["beauty"]),
    ("Pierre Fabre", "FR", ["beauty"]),
    ("Galenic", "FR", ["beauty"]),
    ("Sothys", "FR", ["beauty"]),
    ("Decleor", "FR", ["beauty"]),
    ("Phyto", "FR", ["beauty"]),
    ("Phytomer", "FR", ["beauty"]),
    ("Lancome", "FR", ["beauty"]),  # L'Oreal — group will likely shadow
    ("Loreal Paris", "FR", ["beauty"]),
    ("Aesop", "AU", ["beauty"]),

    # === EU home / decoration (small) ===
    ("Maisons du Monde", "FR", ["home", "interior-design"]),
    ("Habitat", "FR", ["home", "interior-design"]),
    ("Tikamoon", "FR", ["home", "interior-design"]),
    ("La Redoute", "FR", ["fashion", "home"]),
    ("Pierre Frey", "FR", ["interior-design", "decoration"]),
    ("Nobilis", "FR", ["interior-design", "decoration"]),
    ("Atrium Concept", "FR", ["home"]),
    ("Sema Design", "FR", ["home", "decoration"]),
    ("Bonsoir Paris", "FR", ["home", "decoration"]),
    ("Petite Friture", "FR", ["interior-design", "decoration"]),
    ("Forestier", "FR", ["interior-design"]),
    ("Made", "GB", ["home", "interior-design"]),
    ("Hay", "DK", ["interior-design"]),
    ("Muuto", "DK", ["interior-design"]),
    ("Vitra", "CH", ["interior-design"]),
    ("Ferm Living", "DK", ["interior-design", "decoration"]),
    ("Fritz Hansen", "DK", ["interior-design"]),
    ("String Furniture", "SE", ["interior-design"]),
    ("Tine K Home", "DK", ["home", "decoration"]),
    ("Bloomingville", "DK", ["home", "decoration"]),

    # === FR luxury accessories / leather goods ===
    ("Goyard", "FR", ["fashion", "retail-luxury"]),
    ("Moynat", "FR", ["fashion", "retail-luxury"]),
    ("Delvaux", "BE", ["fashion", "retail-luxury"]),
    ("Pinel et Pinel", "FR", ["fashion", "retail-luxury"]),
    ("Berluti", "FR", ["fashion", "retail-luxury"]),
    ("Le Chameau", "FR", ["fashion"]),
    ("Aigle Paris", "FR", ["fashion"]),
    ("Petit Bateau Paris", "FR", ["fashion"]),

    # === Mass-market FR (Camille comparison set) ===
    ("Kiabi", "FR", ["fashion"]),
    ("Gemo", "FR", ["fashion"]),
    ("Pimkie", "FR", ["fashion"]),
    ("Camaieu", "FR", ["fashion"]),
    ("Devred", "FR", ["fashion"]),
    ("Cache Cache", "FR", ["fashion"]),
    ("Bonobo", "FR", ["fashion"]),
    ("Jules", "FR", ["fashion"]),
    ("Brice", "FR", ["fashion"]),
    ("Celio", "FR", ["fashion"]),
    ("Andre", "FR", ["fashion"]),
    ("Eram", "FR", ["fashion"]),
    ("La Halle", "FR", ["fashion"]),

    # === EU multi-brand retail / e-com ===
    ("Zalando", "DE", ["fashion", "retail-luxury"]),
    ("About You", "DE", ["fashion"]),
    ("Net a Porter", "GB", ["fashion", "retail-luxury"]),
    ("Mr Porter", "GB", ["fashion", "retail-luxury"]),
    ("Matches Fashion", "GB", ["fashion", "retail-luxury"]),
    ("Mytheresa", "DE", ["fashion", "retail-luxury"]),
    ("Spartoo", "FR", ["fashion"]),
    ("Sarenza", "FR", ["fashion"]),
    ("La Redoute Interieurs", "FR", ["home", "interior-design"]),

    # === Outdoor / lifestyle (Camille adjacent) ===
    ("Salomon", "FR", ["fashion"]),
    ("Rossignol", "FR", ["fashion"]),
    ("Millet Mountain", "FR", ["fashion"]),
    ("Lafuma", "FR", ["fashion"]),
    ("Eider", "FR", ["fashion"]),
    ("Patagonia Europe", "US", ["fashion"]),

    # === Niche jewelry (Camille might browse) ===
    ("Mejuri", "CA", ["fashion"]),
    ("Anissa Kermiche", "FR", ["fashion"]),
    ("Charlotte Chesnais", "FR", ["fashion"]),
    ("Aurelie Bidermann", "FR", ["fashion"]),
    ("Messika", "FR", ["fashion", "retail-luxury"]),
    ("Boucheron", "FR", ["fashion", "retail-luxury"]),
    ("Mauboussin", "FR", ["fashion", "retail-luxury"]),
    ("Atelier Paulin", "FR", ["fashion"]),
    ("Gigi Clozeau", "FR", ["fashion"]),
    ("Adelline", "FR", ["fashion"]),
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
