"""Pull the latest 'Who is hiring' HN thread, extract company names, probe-ats.

Uses HN's Algolia API for search and the Firebase API for the thread tree.

Run:
    uv run python scripts/hn_discovery.py
Output: companies/_drafts/<slug>.yaml for each ATS hit.
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.probe_ats import emit_draft, normalize_slug, probe_all  # noqa: E402

ALGOLIA = "https://hn.algolia.com/api/v1/search"
HN_FIREBASE = "https://hacker-news.firebaseio.com/v0"


async def latest_who_is_hiring_id() -> int | None:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            ALGOLIA,
            params={
                "query": "Ask HN Who is hiring",
                "tags": "story,author_whoishiring",
                "hitsPerPage": 5,
            },
            timeout=30.0,
        )
        r.raise_for_status()
        for hit in r.json()["hits"]:
            t = (hit.get("title") or "").lower()
            if "who is hiring" in t and "freelancer" not in t and "wants to be hired" not in t:
                return int(hit["objectID"])
    return None


async def fetch_top_level_comments(story_id: int) -> list[str]:
    """Return raw HTML text of every top-level comment on the story."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(f"{HN_FIREBASE}/item/{story_id}.json")
        r.raise_for_status()
        kids = r.json().get("kids") or []
        comments: list[str] = []
        sem = asyncio.Semaphore(20)

        async def fetch_one(cid: int) -> None:
            async with sem:
                cr = await client.get(f"{HN_FIREBASE}/item/{cid}.json")
                if cr.status_code != 200:
                    return
                payload = cr.json() or {}
                if payload.get("dead") or payload.get("deleted"):
                    return
                text = payload.get("text") or ""
                if text:
                    comments.append(text)

        await asyncio.gather(*(fetch_one(cid) for cid in kids))
    return comments


# Heuristic: HN "Who is hiring" comments typically open with
#   "CompanyName | role | location | tech…"
# or "**CompanyName** — role — location"
_FIRST_LINE_RE = re.compile(r"^([A-Z][A-Za-z0-9 &.\-/]{1,30}?)\s*(?:[|—\-:]|<|$)")


def extract_company_names(html: str) -> list[str]:
    """Extract candidate company names from a comment's HTML."""
    # Strip the HTML enough to find the leading company name in the first line.
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    m = _FIRST_LINE_RE.match(text)
    if not m:
        return []
    name = m.group(1).strip().rstrip(".,;:")
    if len(name) < 2 or name.lower() in {"hi", "hey", "hello", "we", "the", "i'm", "we're"}:
        return []
    return [name]


async def main() -> None:
    story_id = await latest_who_is_hiring_id()
    if not story_id:
        print("No 'Who is hiring' thread found")
        return
    print(f"Found story {story_id}")
    comments = await fetch_top_level_comments(story_id)
    print(f"Pulled {len(comments)} top-level comments")
    names: set[str] = set()
    for c in comments:
        names.update(extract_company_names(c))
    print(f"Extracted {len(names)} candidate company names")

    slugs = sorted({normalize_slug(n) for n in names if normalize_slug(n)})
    print(f"Probing {len(slugs)} slugs against ATSes…")
    hits = await probe_all(slugs)
    print(f"\n{len(hits)} hits:")
    for slug, providers in sorted(hits.items(), key=lambda kv: -sum(kv[1].values())):
        path = emit_draft(slug, providers)
        total = sum(providers.values())
        rel = path.relative_to(Path(__file__).resolve().parents[1])
        print(f"  {slug:30}  {total:>4} jobs  {providers}  → {rel}")


if __name__ == "__main__":
    asyncio.run(main())
