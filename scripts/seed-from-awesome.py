"""Mine GitHub-hosted "awesome" lists for EU AI/tech company candidates,
auto-probe each candidate's career page across 7 ATS providers, and emit
draft YAML files under companies/_drafts/ for human review.

Bypasses Cloudflare-protected directory sites by relying only on
raw.githubusercontent.com (plain HTTP, no anti-scrape) and direct ATS
API endpoints (which are public and unprotected).

Usage:
    python scripts/seed-from-awesome.py
    python scripts/seed-from-awesome.py --commit  # write to companies/, not _drafts/

Output: per-company YAML files. Companies whose ATS we can't auto-detect
are skipped (no point keeping a stub that produces zero jobs).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parents[1]
DRAFTS_DIR = ROOT / "companies" / "_drafts"
TECH_DIR = ROOT / "companies" / "tech"
AI_DIR = ROOT / "companies" / "ai"

# Public Markdown company lists. raw.githubusercontent.com endpoints —
# no Cloudflare, no terms friction. Each list is biased toward EU/FR so
# the extracted candidates skew toward our scope.
AWESOME_LISTS = [
    "https://raw.githubusercontent.com/jmbarrancoml/awesome-european-ai/main/README.md",
    "https://raw.githubusercontent.com/diselostudio/awesome-european-tech/main/README.md",
    "https://raw.githubusercontent.com/gmberton/awesome-machine-learning-startups/master/README.md",
    "https://raw.githubusercontent.com/timqian/open-source-jobs/master/README.md",
]

# Markdown link pattern: [Name](https://url)
LINK_RE = re.compile(r"\[([^\]]{2,80})\]\((https?://[^\s\)]+)\)")

USER_AGENT = "ai-startups-bot/0.1 (+https://github.com/Aramente/eu-tech-jobs)"


def _slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:48] or "unknown"


def _existing_slugs() -> set[str]:
    slugs = set()
    for p in (ROOT / "companies").rglob("*.yaml"):
        if "_drafts" in p.parts:
            continue
        slugs.add(p.stem)
    return slugs


def _fetch(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def _extract_candidates(md: str) -> list[tuple[str, str]]:
    """Yield (name, url) tuples from Markdown links in the body."""
    out = []
    seen_urls = set()
    for m in LINK_RE.finditer(md):
        name = m.group(1).strip()
        url = m.group(2).strip()
        if not name or not url:
            continue
        # Skip self-links (anchors), images, github profiles
        if any(skip in url for skip in ("github.com", "githubusercontent", "twitter.com",
                                          "linkedin.com", "youtube.com", "wikipedia.org",
                                          "shields.io", "/issues", "/pulls", "#")):
            continue
        host = urlparse(url).hostname or ""
        if not host:
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        out.append((name, url))
    return out


def _probe_ats(slug: str) -> tuple[str, str] | None:
    """Try slug as a handle on each ATS provider; return first hit that
    actually has > 0 jobs (some providers return 200 with empty results
    for any handle, polluting auto-discovery if we trust status alone)."""
    import json

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
                    body = r.read()
                    data = json.loads(body)
                except Exception:
                    continue
                if has_jobs(data):
                    return provider, slug
        except Exception:
            continue
    # Personio returns XML, not JSON — handle separately.
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


def _probe_one(name: str, url: str) -> tuple[str, str, str, str] | None:
    """Return (slug, name, provider, handle) if ATS detection succeeds."""
    slug = _slugify(name)
    if not slug:
        return None
    found = _probe_ats(slug)
    if not found:
        # Try with a hyphen/no-hyphen alternate
        alt = slug.replace("-", "")
        if alt != slug:
            found = _probe_ats(alt)
            if found:
                return slug, name, found[0], found[1]
        return None
    return slug, name, found[0], found[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true", help="Write to companies/{ai,tech}/, not companies/_drafts/")
    parser.add_argument("--max", type=int, default=300, help="Cap candidates probed (avoid runaway probes).")
    args = parser.parse_args()

    existing = _existing_slugs()
    print(f"Existing seeded slugs: {len(existing)}")

    candidates: list[tuple[str, str]] = []
    for url in AWESOME_LISTS:
        md = _fetch(url)
        if not md:
            print(f"  ⚠ could not fetch {url}")
            continue
        found = _extract_candidates(md)
        print(f"  ✓ {len(found)} candidates from {url}")
        candidates.extend(found)

    # De-dup by name, prefer earliest occurrence
    seen_names = set()
    unique: list[tuple[str, str]] = []
    for name, url in candidates:
        key = name.lower().strip()
        if key in seen_names:
            continue
        seen_names.add(key)
        unique.append((name, url))
    print(f"Unique candidates: {len(unique)}")

    # Filter out already-seeded
    new = [(n, u) for n, u in unique if _slugify(n) not in existing]
    print(f"Not yet seeded: {len(new)}")

    new = new[:args.max]
    print(f"Probing {len(new)} candidates across 7 ATS providers in parallel…")

    out_dir = (TECH_DIR if args.commit else DRAFTS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    hits = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        for result in ex.map(lambda x: _probe_one(*x), new):
            if not result:
                continue
            slug, name, provider, handle = result
            data = {
                "name": name,
                "country": "XX",  # let the daily run / company-enrich step refine country
                "categories": ["tech"],
                "ats": {"provider": provider, "handle": handle},
                "notes": "Discovered via awesome-european-tech / awesome-european-ai mining",
            }
            path = out_dir / f"{slug}.yaml"
            if path.exists():
                continue
            path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
            hits += 1
            print(f"  + {slug:35s} {provider}:{handle}")

    print(f"\n✓ {hits} new company YAMLs written to {out_dir.relative_to(ROOT)}")
    if not args.commit:
        print("  (drafts — review, then `git mv` to companies/{ai,tech}/ to activate)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
