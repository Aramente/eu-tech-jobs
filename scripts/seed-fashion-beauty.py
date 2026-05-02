"""Bulk-seed ~300 FR fashion / beauty / perfume / home / interior /
decoration / textile / retail-luxury brands, auto-probing ATS handles
and writing YAMLs with the industry_tags field.

Companion to the curated /camille/ landing page that surfaces buyer /
purchasing / product-offering roles in those verticals.

Usage:
    python scripts/seed-fashion-beauty.py             # dry-run
    python scripts/seed-fashion-beauty.py --commit    # write YAMLs
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

# (name, ISO2, [industry_tags]) — companies are FR-located OR have a
# meaningful FR presence. industry_tags drive the /camille/ filter.
BRANDS: list[tuple[str, str, list[str]]] = [
    # === LVMH brands (a chunk of them, group careers usually live on
    # smartrecruiters under each maison's name) ===
    ("Sephora", "FR", ["beauty", "perfume", "retail-luxury"]),
    ("Dior", "FR", ["fashion", "perfume", "retail-luxury"]),
    ("Christian Dior Couture", "FR", ["fashion", "retail-luxury"]),
    ("Louis Vuitton", "FR", ["fashion", "retail-luxury"]),
    ("Kenzo", "FR", ["fashion"]),
    ("Givenchy", "FR", ["fashion", "perfume"]),
    ("Celine", "FR", ["fashion", "retail-luxury"]),
    ("Loewe", "FR", ["fashion", "retail-luxury"]),
    ("Loro Piana", "IT", ["fashion", "textile", "retail-luxury"]),
    ("Berluti", "FR", ["fashion", "retail-luxury"]),
    ("Fendi", "IT", ["fashion", "retail-luxury"]),
    ("Marc Jacobs", "FR", ["fashion"]),
    ("Patou", "FR", ["fashion", "perfume"]),
    ("Rimowa", "DE", ["fashion", "retail-luxury"]),
    ("Le Bon Marché", "FR", ["retail-luxury"]),
    ("La Samaritaine", "FR", ["retail-luxury"]),
    ("Acqua di Parma", "IT", ["beauty", "perfume"]),
    ("Make Up For Ever", "FR", ["beauty"]),
    ("Benefit Cosmetics", "US", ["beauty"]),
    ("Fresh", "US", ["beauty"]),
    ("Guerlain", "FR", ["beauty", "perfume", "retail-luxury"]),
    ("Parfums Christian Dior", "FR", ["beauty", "perfume"]),
    ("Maison Francis Kurkdjian", "FR", ["perfume", "retail-luxury"]),
    ("TAG Heuer", "CH", ["retail-luxury"]),
    ("Bulgari", "IT", ["retail-luxury", "beauty", "perfume"]),
    ("Tiffany", "US", ["retail-luxury"]),
    ("Hublot", "CH", ["retail-luxury"]),
    ("Zenith", "CH", ["retail-luxury"]),
    ("24S", "FR", ["fashion", "beauty", "retail-luxury"]),

    # === Kering brands ===
    ("Saint Laurent", "FR", ["fashion", "perfume", "retail-luxury"]),
    ("Balenciaga", "FR", ["fashion", "retail-luxury"]),
    ("Gucci", "IT", ["fashion", "perfume", "retail-luxury"]),
    ("Bottega Veneta", "IT", ["fashion", "retail-luxury"]),
    ("Alexander McQueen", "GB", ["fashion", "retail-luxury"]),
    ("Brioni", "IT", ["fashion", "retail-luxury"]),
    ("Boucheron", "FR", ["retail-luxury"]),
    ("Pomellato", "IT", ["retail-luxury"]),
    ("Qeelin", "FR", ["retail-luxury"]),
    ("Kering Eyewear", "IT", ["retail-luxury"]),
    ("Creed", "GB", ["perfume", "retail-luxury"]),

    # === Richemont brands ===
    ("Cartier", "FR", ["retail-luxury"]),
    ("Van Cleef Arpels", "FR", ["retail-luxury"]),
    ("Piaget", "CH", ["retail-luxury"]),
    ("Vacheron Constantin", "CH", ["retail-luxury"]),
    ("IWC", "CH", ["retail-luxury"]),
    ("Jaeger LeCoultre", "CH", ["retail-luxury"]),
    ("Panerai", "CH", ["retail-luxury"]),
    ("Montblanc", "DE", ["retail-luxury"]),
    ("Roger Dubuis", "CH", ["retail-luxury"]),
    ("Baume Mercier", "CH", ["retail-luxury"]),
    ("Chloe", "FR", ["fashion", "perfume", "retail-luxury"]),
    ("Alaia", "FR", ["fashion", "retail-luxury"]),
    ("Dunhill", "GB", ["fashion", "retail-luxury"]),
    ("Net A Porter", "GB", ["fashion", "retail-luxury"]),
    ("Yoox", "IT", ["fashion", "retail-luxury"]),
    ("Watchfinder", "GB", ["retail-luxury"]),
    ("Buccellati", "IT", ["retail-luxury"]),
    ("Delvaux", "BE", ["fashion", "retail-luxury"]),

    # === Hermès, Chanel — independent ===
    ("Hermes", "FR", ["fashion", "perfume", "retail-luxury"]),
    ("Chanel", "FR", ["fashion", "beauty", "perfume", "retail-luxury"]),
    ("John Lobb", "GB", ["fashion", "retail-luxury"]),

    # === L'Oréal Groupe brands ===
    ("L Oreal", "FR", ["beauty", "retail-luxury"]),
    ("Lancome", "FR", ["beauty", "perfume"]),
    ("Garnier", "FR", ["beauty"]),
    ("Maybelline", "US", ["beauty"]),
    ("Kerastase", "FR", ["beauty"]),
    ("Vichy", "FR", ["beauty"]),
    ("La Roche Posay", "FR", ["beauty"]),
    ("CeraVe", "US", ["beauty"]),
    ("Urban Decay", "US", ["beauty"]),
    ("NYX", "US", ["beauty"]),
    ("YSL Beauty", "FR", ["beauty", "perfume"]),
    ("Giorgio Armani Beauty", "IT", ["beauty", "perfume"]),
    ("Mugler", "FR", ["fashion", "perfume"]),
    ("Atelier Cologne", "FR", ["perfume"]),
    ("Aesop", "AU", ["beauty", "perfume"]),
    ("Helena Rubinstein", "FR", ["beauty"]),
    ("Biotherm", "FR", ["beauty"]),
    ("Cacharel", "FR", ["fashion", "perfume"]),

    # === Coty brands ===
    ("Coty", "US", ["beauty", "perfume"]),
    ("Bourjois", "FR", ["beauty"]),
    ("Lancaster", "DE", ["beauty"]),

    # === Beiersdorf ===
    ("Beiersdorf", "DE", ["beauty"]),
    ("Nivea", "DE", ["beauty"]),
    ("Eucerin", "DE", ["beauty"]),
    ("La Prairie", "CH", ["beauty"]),

    # === Puig brands ===
    ("Puig", "ES", ["beauty", "perfume"]),
    ("Carolina Herrera", "US", ["fashion", "perfume"]),
    ("Christian Louboutin", "FR", ["fashion", "beauty"]),
    ("Jean Paul Gaultier", "FR", ["fashion", "perfume"]),
    ("Nina Ricci", "FR", ["fashion", "perfume"]),
    ("Paco Rabanne", "ES", ["fashion", "perfume"]),
    ("Penhaligons", "GB", ["perfume"]),
    ("L Artisan Parfumeur", "FR", ["perfume"]),
    ("Charlotte Tilbury", "GB", ["beauty"]),
    ("Byredo", "SE", ["perfume"]),

    # === Niche / indie French perfumers ===
    ("Diptyque", "FR", ["perfume", "home"]),
    ("Frederic Malle", "FR", ["perfume"]),
    ("Maison Margiela Replica", "FR", ["fashion", "perfume"]),
    ("Le Couvent", "FR", ["beauty", "perfume"]),
    ("Histoires de Parfums", "FR", ["perfume"]),
    ("Le Labo", "US", ["perfume"]),
    ("By Kilian", "FR", ["perfume"]),
    ("Goutal Paris", "FR", ["perfume"]),
    ("Caron", "FR", ["perfume"]),
    ("Houbigant", "FR", ["perfume"]),
    ("BDK Parfums", "FR", ["perfume"]),
    ("Sisley Paris", "FR", ["beauty", "perfume"]),
    ("Caudalie", "FR", ["beauty"]),
    ("Nuxe", "FR", ["beauty"]),
    ("Clarins", "FR", ["beauty"]),
    ("L Occitane", "FR", ["beauty", "perfume"]),
    ("Yves Rocher", "FR", ["beauty"]),
    ("Mademoiselle Saint Germain", "FR", ["beauty"]),
    ("Aroma Zone", "FR", ["beauty"]),
    ("Manucurist", "FR", ["beauty"]),
    ("Typology", "FR", ["beauty"]),
    ("Indemne", "FR", ["beauty"]),
    ("Respire", "FR", ["beauty"]),
    ("La Bouche Rouge", "FR", ["beauty"]),
    ("Polaar", "FR", ["beauty"]),
    ("Christophe Robin", "FR", ["beauty"]),
    ("Filorga", "FR", ["beauty"]),
    ("Talika", "FR", ["beauty"]),
    ("Klorane", "FR", ["beauty"]),
    ("Galenic", "FR", ["beauty"]),
    ("Embryolisse", "FR", ["beauty"]),
    ("Avene", "FR", ["beauty"]),
    ("Ducray", "FR", ["beauty"]),
    ("Bioderma", "FR", ["beauty"]),
    ("Mixa", "FR", ["beauty"]),
    ("Le Petit Marseillais", "FR", ["beauty"]),
    ("Roger Gallet", "FR", ["beauty", "perfume"]),
    ("Boon Soin", "FR", ["beauty"]),
    ("Kure Bazaar", "FR", ["beauty"]),
    ("Inoui Editions", "FR", ["fashion"]),
    ("Make My Lemonade", "FR", ["fashion"]),

    # === French apparel scaleups + luxury ===
    ("Sezane", "FR", ["fashion"]),
    ("Veja", "FR", ["fashion"]),
    ("Sandro", "FR", ["fashion"]),
    ("Maje", "FR", ["fashion"]),
    ("Claudie Pierlot", "FR", ["fashion"]),
    ("The Kooples", "FR", ["fashion"]),
    ("Ba Sh", "FR", ["fashion"]),
    ("Rouje", "FR", ["fashion"]),
    ("Soeur", "FR", ["fashion"]),
    ("AMI Paris", "FR", ["fashion"]),
    ("Jacquemus", "FR", ["fashion"]),
    ("Isabel Marant", "FR", ["fashion"]),
    ("Faguo", "FR", ["fashion"]),
    ("Le Slip Francais", "FR", ["fashion", "textile"]),
    ("Le Tanneur", "FR", ["fashion"]),
    ("Petit Bateau", "FR", ["fashion", "textile"]),
    ("Aigle", "FR", ["fashion"]),
    ("Lacoste", "FR", ["fashion"]),
    ("APC", "FR", ["fashion"]),
    ("American Vintage", "FR", ["fashion"]),
    ("IKKS", "FR", ["fashion"]),
    ("Comptoir des Cotonniers", "FR", ["fashion"]),
    ("Princesse Tam Tam", "FR", ["fashion"]),
    ("Etam", "FR", ["fashion"]),
    ("Smallable", "FR", ["fashion"]),
    ("Bensimon", "FR", ["fashion"]),
    ("Bonpoint", "FR", ["fashion"]),
    ("Cyrillus", "FR", ["fashion"]),
    ("DPAM", "FR", ["fashion"]),
    ("Tape A L Oeil", "FR", ["fashion"]),
    ("Promod", "FR", ["fashion"]),
    ("Pimkie", "FR", ["fashion"]),
    ("Camaieu", "FR", ["fashion"]),
    ("Galeries Lafayette", "FR", ["fashion", "beauty", "retail-luxury"]),
    ("Printemps", "FR", ["fashion", "beauty", "retail-luxury"]),
    ("BHV", "FR", ["fashion", "home"]),
    ("Monoprix", "FR", ["fashion", "home"]),
    ("Show Room Prive", "FR", ["fashion"]),
    ("La Redoute", "FR", ["fashion", "home"]),
    ("La Redoute Interieurs", "FR", ["home", "interior-design"]),
    ("Mytheresa", "DE", ["fashion", "retail-luxury"]),
    ("Vestiaire Collective", "FR", ["fashion"]),
    ("Decathlon", "FR", ["fashion", "textile"]),
    ("Patrick", "FR", ["fashion"]),

    # === French home / interior / decoration ===
    ("Maisons du Monde", "FR", ["home", "interior-design", "decoration"]),
    ("Westwing", "DE", ["home", "interior-design"]),
    ("Tikamoon", "FR", ["home", "interior-design"]),
    ("Made", "GB", ["home", "interior-design"]),
    ("BoConcept", "DK", ["home", "interior-design"]),
    ("Kave Home", "ES", ["home", "interior-design"]),
    ("Cyrillus Maison", "FR", ["home"]),
    ("MERCI", "FR", ["home", "fashion", "decoration"]),
    ("Caravane", "FR", ["home", "decoration"]),
    ("Madura", "FR", ["home", "textile"]),
    ("AM PM", "FR", ["home", "interior-design"]),
    ("Roche Bobois", "FR", ["interior-design"]),
    ("Ligne Roset", "FR", ["interior-design"]),
    ("Cinna", "FR", ["interior-design"]),
    ("Gautier", "FR", ["interior-design"]),
    ("Habitat", "FR", ["home", "interior-design"]),
    ("Conforama", "FR", ["home"]),
    ("But", "FR", ["home"]),
    ("Alinea", "FR", ["home"]),
    ("Maison Sarah Lavoine", "FR", ["interior-design", "decoration"]),
    ("La Cerise sur le Gateau", "FR", ["home", "textile"]),
    ("Le Bonheur du Jour", "FR", ["home"]),

    # === DIY / home-improvement (FR) ===
    ("Leroy Merlin", "FR", ["home"]),
    ("Castorama", "FR", ["home"]),
    ("Mr Bricolage", "FR", ["home"]),
    ("Bricomarche", "FR", ["home"]),
    ("Brico Depot", "FR", ["home"]),
    ("IKEA", "SE", ["home", "interior-design"]),
    ("Habitat France", "FR", ["home"]),
    ("Schmidt", "FR", ["home", "interior-design"]),

    # === French luxury-goods / eyewear / leather / writing instruments ===
    ("Lalique", "FR", ["retail-luxury", "decoration"]),
    ("Baccarat", "FR", ["retail-luxury", "decoration"]),
    ("Christofle", "FR", ["retail-luxury", "home"]),
    ("Saint Louis", "FR", ["retail-luxury"]),
    ("Devialet", "FR", ["home", "retail-luxury"]),
    ("Krys Group", "FR", ["retail-luxury"]),
    ("Atol Les Opticiens", "FR", ["retail-luxury"]),
    ("Octobre Editions", "FR", ["fashion"]),
    ("Faguo", "FR", ["fashion"]),

    # === Eyewear / specs ===
    ("Lunettes Pour Tous", "FR", ["retail-luxury"]),

    # === French textile manufacturers ===
    ("Saint James", "FR", ["fashion", "textile"]),
    ("Petit Bateau Textile", "FR", ["textile"]),
    ("Etoile Bisson", "FR", ["textile"]),
    ("Eminence", "FR", ["fashion", "textile"]),
    ("Armor Lux", "FR", ["fashion", "textile"]),
    ("DIM", "FR", ["fashion", "textile"]),

    # === EU adjacent (have FR offices / EU-located, in scope) ===
    ("Zalando", "DE", ["fashion"]),  # already in seed; let probe handle dup
    ("About You", "DE", ["fashion"]),  # dup safe
    ("Asos", "GB", ["fashion"]),
    ("Mango", "ES", ["fashion"]),
    ("Inditex", "ES", ["fashion"]),
    ("Zara", "ES", ["fashion"]),
    ("Massimo Dutti", "ES", ["fashion"]),
    ("Bershka", "ES", ["fashion"]),
    ("Pull Bear", "ES", ["fashion"]),
    ("Stradivarius", "ES", ["fashion"]),
    ("Camper", "ES", ["fashion"]),
    ("Tod s", "IT", ["fashion", "retail-luxury"]),
    ("Roger Vivier", "IT", ["fashion", "retail-luxury"]),
    ("Salvatore Ferragamo", "IT", ["fashion", "retail-luxury"]),
    ("Prada", "IT", ["fashion", "retail-luxury"]),
    ("Miu Miu", "IT", ["fashion", "retail-luxury"]),
    ("Versace", "IT", ["fashion", "retail-luxury"]),
    ("Dolce Gabbana", "IT", ["fashion", "perfume", "retail-luxury"]),
    ("Moncler", "IT", ["fashion"]),
    ("Stone Island", "IT", ["fashion"]),
    ("OTB Group", "IT", ["fashion"]),
    ("Diesel", "IT", ["fashion"]),
    ("Marni", "IT", ["fashion"]),
    ("Margiela", "FR", ["fashion"]),
    ("Sergio Rossi", "IT", ["fashion", "retail-luxury"]),
    ("Furla", "IT", ["fashion"]),
    ("Coccinelle", "IT", ["fashion"]),
    ("Liu Jo", "IT", ["fashion"]),
    ("Twin Set", "IT", ["fashion"]),
    ("Pinko", "IT", ["fashion"]),
    ("Patrizia Pepe", "IT", ["fashion"]),
    ("Ermenegildo Zegna", "IT", ["fashion", "retail-luxury"]),
    ("Brunello Cucinelli", "IT", ["fashion", "retail-luxury"]),
    ("Max Mara", "IT", ["fashion"]),
    ("Aspesi", "IT", ["fashion"]),
    ("Marella", "IT", ["fashion"]),
    ("Boggi Milano", "IT", ["fashion"]),
    ("Camicissima", "IT", ["fashion"]),
    ("Geox", "IT", ["fashion"]),
    ("Calzedonia", "IT", ["fashion", "textile"]),
    ("Intimissimi", "IT", ["fashion", "textile"]),
    ("Tezenis", "IT", ["fashion", "textile"]),
    ("Falconeri", "IT", ["fashion"]),
    ("Atelier Emé", "IT", ["fashion"]),
    ("Iceberg", "IT", ["fashion"]),
    ("MSGM", "IT", ["fashion"]),
    ("Off White", "IT", ["fashion"]),
    ("Acne Studios", "SE", ["fashion"]),
    ("Ganni", "DK", ["fashion"]),
    ("Cos", "SE", ["fashion"]),
    ("H M", "SE", ["fashion"]),
    ("Arket", "SE", ["fashion"]),
    ("Other Stories", "SE", ["fashion"]),
    ("Filippa K", "SE", ["fashion"]),
    ("By Malene Birger", "DK", ["fashion"]),
    ("Samsoe", "DK", ["fashion"]),

    # === Swiss + DE perfume / beauty ===
    ("Wella", "DE", ["beauty"]),
    ("Schwarzkopf", "DE", ["beauty"]),
    ("Symrise", "DE", ["perfume", "beauty"]),
    ("Givaudan", "CH", ["perfume", "beauty"]),
    ("Firmenich", "CH", ["perfume", "beauty"]),
    ("IFF", "US", ["perfume", "beauty"]),

    # === French-specific scaleups in beauty ===
    ("Chronos Care", "FR", ["beauty"]),
    ("Gisou Paris", "FR", ["beauty"]),
    ("Kosas", "US", ["beauty"]),
    ("Ouai", "US", ["beauty"]),
    ("Glossier", "US", ["beauty"]),
    ("Drunk Elephant", "US", ["beauty"]),
    ("Rare Beauty", "US", ["beauty"]),
    ("Aime Skincare", "FR", ["beauty"]),
    ("Le Mini Macaron", "FR", ["beauty"]),
    ("Birchbox France", "FR", ["beauty"]),
    ("Blissim", "FR", ["beauty"]),
    ("Nocibe", "FR", ["beauty", "retail-luxury"]),
    ("Marionnaud", "FR", ["beauty", "retail-luxury"]),

    # === Department / lifestyle ===
    ("Uniqlo", "JP", ["fashion"]),
    ("Muji", "JP", ["fashion", "home"]),
    ("Decathlon Decat", "FR", ["fashion"]),
    ("Au Vieux Campeur", "FR", ["fashion"]),

    # === Scandinavian / European interior design ===
    ("Hay", "DK", ["home", "interior-design"]),
    ("Muuto", "DK", ["interior-design"]),
    ("Fritz Hansen", "DK", ["interior-design"]),
    ("Vitra", "CH", ["interior-design"]),
    ("Cassina", "IT", ["interior-design"]),
    ("Magis", "IT", ["interior-design"]),
    ("B B Italia", "IT", ["interior-design"]),
    ("Poltrona Frau", "IT", ["interior-design"]),
    ("Kartell", "IT", ["interior-design"]),
    ("Flos", "IT", ["interior-design"]),
    ("Artemide", "IT", ["interior-design"]),
    ("Foscarini", "IT", ["interior-design"]),
    ("Nemo Lighting", "IT", ["interior-design"]),
    ("Louis Poulsen", "DK", ["interior-design"]),
]


def _slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:48] or "unknown"


def _existing_slugs() -> set[str]:
    return {p.stem for p in (ROOT / "companies").rglob("*.yaml") if "_drafts" not in p.parts}


def _verify_brand_match(name: str, provider: str, handle: str) -> bool:
    """Fetch a sample job and confirm the company name in the response
    actually maps to the brand we wanted. Without this, generic handles
    like 'paco' or 'charlotte' silently grab unrelated companies."""
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
    # The brand name (no spaces/punct) must appear somewhere in the response.
    # Catches 'lvuitton' inside 'Louis Vuitton', 'galerieslafayette', etc.
    return name_norm in body_norm


def _probe_ats(handle: str) -> tuple[str, str] | None:
    """Probe a single handle across providers. Require non-empty results."""
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
    # Personio (XML)
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


def _probe_one(brand: tuple[str, str, list[str]]):
    name, country, tags = brand
    base = _slugify(name)
    # Only the canonical slug + the no-hyphen variant. Splitting on '-'
    # gave too many false positives (paco→Paco Rabanne probe matched
    # an unrelated personio:paco tenant).
    variants = [base, base.replace("-", "")]
    variants = list(dict.fromkeys(v for v in variants if v))
    for handle in variants:
        found = _probe_ats(handle)
        if not found:
            continue
        provider, h = found
        if _verify_brand_match(name, provider, h):
            return base, name, country, tags, provider, h
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()

    existing = _existing_slugs()
    print(f"Existing seed: {len(existing)} companies")
    new_brands = [b for b in BRANDS if _slugify(b[0]) not in existing]
    print(f"Probing {len(new_brands)} new candidates ({len(BRANDS)} total in list)…")

    hits: list = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as ex:
        for r in ex.map(_probe_one, new_brands):
            if r:
                hits.append(r)

    print(f"\n{len(hits)} ATS hits:")
    for slug, name, country, tags, prov, h in hits:
        print(f"  + {slug:30s} {prov}:{h:25s} ({country}, {','.join(tags)})")

    if not args.commit:
        print("\n(dry-run — pass --commit to write YAMLs)")
        return 0

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for slug, name, country, tags, prov, h in hits:
        path = TARGET_DIR / f"{slug}.yaml"
        if path.exists():
            continue
        path.write_text(yaml.safe_dump({
            "name": name,
            "country": country,
            "categories": ["tech"],  # placeholder for the EU-tech axis
            "industry_tags": tags,
            "ats": {"provider": prov, "handle": h},
            "notes": "Curated for the /camille/ buyer/product-offering page",
        }, sort_keys=False, allow_unicode=True))
        written += 1
    print(f"\n+{written} YAMLs written to {TARGET_DIR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
