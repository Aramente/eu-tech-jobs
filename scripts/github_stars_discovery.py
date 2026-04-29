"""Discover companies via GitHub orgs that maintain high-star AI/ML/dev repos.

Strategy: search GitHub for repos with AI-aligned topics + minimum stars,
extract owner orgs, dedupe, probe ATSes, emit drafts.

GitHub search API allows up to 1000 results per query. We rotate across
several topic queries to cover more of the space.

Run:
    GITHUB_TOKEN=$(gh auth token) uv run python scripts/github_stars_discovery.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.probe_ats import emit_draft, normalize_slug, probe_all  # noqa: E402

USER_AGENT = "ai-startups-bot/0.1 (+https://github.com/Aramente/eu-tech-jobs)"

# Queries that surface "real company maintaining a serious public repo".
# Each is "topic:X stars:>500" — adjust to taste.
QUERIES = [
    "topic:ai stars:>1000",
    "topic:llm stars:>500",
    "topic:machine-learning stars:>1000",
    "topic:devtools stars:>1000",
    "topic:database stars:>1000",
    "topic:agent stars:>500",
    "topic:nlp stars:>500",
    "topic:computer-vision stars:>500",
]

# Owners that aren't real organisations / are too generic to slug-probe.
_OWNER_BLOCKLIST = {
    "google", "facebook", "microsoft", "openai", "meta", "amazon", "nvidia",
    "intel", "ibm", "apple", "tensorflow", "pytorch", "huggingface",
    "kubernetes", "kubernetes-sigs", "cncf", "torvalds",
}


async def fetch_orgs() -> set[str]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    orgs: set[str] = set()
    async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
        for q in QUERIES:
            page = 1
            while page <= 10:  # 100 per page * 10 = 1000 max per query (GH cap)
                try:
                    r = await client.get(
                        "https://api.github.com/search/repositories",
                        params={
                            "q": q,
                            "sort": "stars",
                            "order": "desc",
                            "per_page": 100,
                            "page": page,
                        },
                    )
                except httpx.HTTPError:
                    break
                if r.status_code != 200:
                    break
                payload = r.json()
                items = payload.get("items") or []
                if not items:
                    break
                for item in items:
                    owner = (item.get("owner") or {}).get("login", "")
                    owner_type = (item.get("owner") or {}).get("type", "")
                    if owner_type != "Organization":
                        continue  # personal accounts → skip
                    if owner.lower() in _OWNER_BLOCKLIST:
                        continue
                    orgs.add(owner)
                if len(items) < 100:
                    break
                page += 1
    return orgs


async def main() -> None:
    print("Querying GitHub search across", len(QUERIES), "topic queries…")
    orgs = await fetch_orgs()
    print(f"Found {len(orgs)} distinct GitHub orgs.")

    candidates = {normalize_slug(o) for o in orgs}
    candidates = {c for c in candidates if c and 2 < len(c) < 50}

    # Drop already-curated slugs.
    seed_dir = Path(__file__).resolve().parents[1] / "companies"
    existing = {
        p.stem for p in seed_dir.rglob("*.yaml") if "_drafts" not in p.parts
    }
    fresh = sorted(candidates - existing)
    print(f"{len(fresh)} candidates after dropping {len(existing)} already-curated.")

    print(f"Probing {len(fresh)} slugs against 6 ATSes…")
    hits = await probe_all(fresh)
    print(f"\n{len(hits)} hits:")
    for slug, providers in sorted(hits.items(), key=lambda kv: -sum(kv[1].values())):
        path = emit_draft(slug, providers)
        total = sum(providers.values())
        rel = path.relative_to(Path(__file__).resolve().parents[1])
        print(f"  {slug:30}  {total:>4} jobs  {providers}  → {rel}")


if __name__ == "__main__":
    asyncio.run(main())
