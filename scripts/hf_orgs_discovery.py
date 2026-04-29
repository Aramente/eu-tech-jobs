"""Discover AI companies from HuggingFace Organizations.

Strategy:
1. Walk the HF API listing of organizations that own at least one model.
2. Slugify their names + likely website-derived slugs.
3. Probe ATSes via the existing probe_ats.

Quality filter: HF Orgs that publish models are real AI orgs. Hits with an
EU-known ATS handle are the ones worth promoting.

Run:
    uv run python scripts/hf_orgs_discovery.py [--max 5000]
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.probe_ats import emit_draft, normalize_slug, probe_all  # noqa: E402

# HF lists models, not orgs directly — we walk the model index, dedupe org names.
MODELS_URL = "https://huggingface.co/api/models"
USER_AGENT = "ai-startups-bot/0.1 (+https://github.com/Aramente/eu-tech-jobs)"

# Known noise: HF user accounts that look like orgs but aren't companies.
_NAME_BLOCKLIST = {
    "huggingfaceh4", "google", "facebook", "microsoft", "openai", "meta",
    "amazon", "nvidia", "intel", "ibm", "apple", "stable-diffusion-v1-5",
    "kaggle", "pytorch", "tensorflow", "anonymous", "bert-base-uncased",
    "stabilityai-internal",
}


def _candidate_slugs(org_name: str) -> set[str]:
    """For an org name like `mistralai`, generate candidate ATS slugs to probe."""
    slug = normalize_slug(org_name)
    if not slug or slug in _NAME_BLOCKLIST or len(slug) < 3:
        return set()
    out = {slug}
    # Common transformations: `mistralai` ↔ `mistral`, `openaiteam` ↔ `openai`
    if slug.endswith("ai"):
        stripped = slug[:-2].rstrip("-")
        if 2 < len(stripped) < 50:
            out.add(stripped)
    if slug.endswith("hq"):
        out.add(slug[:-2].rstrip("-"))
    if slug.endswith("team"):
        out.add(slug[:-4].rstrip("-"))
    if slug.endswith("inc") or slug.endswith("co"):
        out.add(slug.rstrip("-inc").rstrip("-co"))
    return {s for s in out if s and 2 < len(s) < 50}


async def fetch_org_names(max_orgs: int) -> set[str]:
    """Walk HF model listings, return distinct author/org slugs."""
    seen: set[str] = set()
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=30.0) as client:
        # The HF API supports `limit` + cursor paging. Sort by downloads desc to
        # bias toward popular (= more likely real-org) authors.
        cursor = None
        page = 0
        while len(seen) < max_orgs and page < 200:
            params: dict[str, str | int] = {
                "limit": 1000,
                "sort": "downloads",
                "direction": -1,
            }
            if cursor:
                params["cursor"] = cursor
            try:
                r = await client.get(MODELS_URL, params=params)
            except httpx.HTTPError:
                break
            if r.status_code != 200:
                break
            payload = r.json()
            if not payload:
                break
            for model in payload:
                model_id = model.get("modelId") or model.get("id") or ""
                if "/" not in model_id:
                    continue
                org = model_id.split("/", 1)[0]
                if not org:
                    continue
                seen.add(org)
            link = r.headers.get("Link", "")
            m = re.search(r'<[^>]*[?&]cursor=([^&>]+)[^>]*>;\s*rel="next"', link)
            if not m:
                break
            cursor = m.group(1)
            page += 1
    return seen


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--max", type=int, default=8000, help="Stop walking HF after this many orgs"
    )
    args = parser.parse_args()

    print(f"Walking HF model listings (max {args.max} orgs)…")
    orgs = await fetch_org_names(args.max)
    print(f"Found {len(orgs)} distinct HF orgs/authors.")

    # Generate candidate slugs (with name-transformation variants).
    candidates: set[str] = set()
    for org in orgs:
        candidates.update(_candidate_slugs(org))
    print(f"{len(candidates)} candidate slugs after dedup + filtering.")

    # Skip slugs that already exist in the curated seed.
    seed_dir = Path(__file__).resolve().parents[1] / "companies"
    existing = {
        p.stem
        for p in seed_dir.rglob("*.yaml")
        if "_drafts" not in p.parts
    }
    fresh = sorted(candidates - existing)
    print(f"{len(fresh)} after dropping {len(existing)} already-curated slugs.")

    print(f"Probing {len(fresh)} slugs against 6 ATSes (this is the slow step)…")
    hits = await probe_all(fresh)
    print(f"\n{len(hits)} hits:")
    for slug, providers in sorted(hits.items(), key=lambda kv: -sum(kv[1].values())):
        path = emit_draft(slug, providers)
        total = sum(providers.values())
        rel = path.relative_to(Path(__file__).resolve().parents[1])
        print(f"  {slug:30}  {total:>4} jobs  {providers}  → {rel}")


if __name__ == "__main__":
    asyncio.run(main())
