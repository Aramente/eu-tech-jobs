"""Probe a list of company slug candidates against all supported ATSes.

Inspired by outscal/OpenJobs' probe-ats.mjs (MIT). Given a list of candidate
slugs, it asks each ATS provider whether a board exists at that slug and emits
draft YAML files for the hits.

Run:
    uv run python scripts/probe_ats.py < candidates.txt
or  uv run python scripts/probe_ats.py mistral huggingface photoroom

Output: companies/_drafts/<slug>.yaml — review, then move to companies/<cat>/.
"""

from __future__ import annotations

import asyncio
import re
import sys
from collections.abc import Iterable
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
DRAFTS_DIR = ROOT / "companies" / "_drafts"
USER_AGENT = "ai-startups-bot/0.1 (+https://github.com/Aramente/eu-tech-jobs)"

# Provider → (probe URL template, success predicate on response.text/json)
# Each probe should be cheap; we don't need full data, only existence.


async def probe_greenhouse(client: httpx.AsyncClient, slug: str) -> int | None:
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=false"
    try:
        r = await client.get(url, timeout=10.0)
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    try:
        return len(r.json().get("jobs") or [])
    except ValueError:
        return None


async def probe_lever(client: httpx.AsyncClient, slug: str) -> int | None:
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    try:
        r = await client.get(url, timeout=10.0)
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    try:
        return len(r.json())
    except ValueError:
        return None


_ASHBY_QUERY = (
    "query Probe($n:String!){"
    "jobBoard:jobBoardWithTeams(organizationHostedJobsPageName:$n){"
    "jobPostings{id __typename}__typename"
    "}}"
)


async def probe_ashby(client: httpx.AsyncClient, slug: str) -> int | None:
    try:
        r = await client.post(
            "https://jobs.ashbyhq.com/api/non-user-graphql?op=Probe",
            json={"operationName": "Probe", "variables": {"n": slug}, "query": _ASHBY_QUERY},
            timeout=10.0,
        )
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    board = (data.get("data") or {}).get("jobBoard")
    if not board:
        return None
    return len(board.get("jobPostings") or [])


async def probe_smartrecruiters(client: httpx.AsyncClient, slug: str) -> int | None:
    url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=1"
    try:
        r = await client.get(url, timeout=10.0)
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    try:
        return r.json().get("totalFound")
    except ValueError:
        return None


async def probe_recruitee(client: httpx.AsyncClient, slug: str) -> int | None:
    url = f"https://{slug}.recruitee.com/api/offers/"
    try:
        r = await client.get(url, timeout=10.0)
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    try:
        return len(r.json().get("offers") or [])
    except ValueError:
        return None


async def probe_personio(client: httpx.AsyncClient, slug: str) -> int | None:
    url = f"https://{slug}.jobs.personio.com/xml"
    try:
        r = await client.get(
            url,
            timeout=10.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        )
    except httpx.HTTPError:
        return None
    if r.status_code != 200 or "<workzag-jobs>" not in r.text:
        return None
    return r.text.count("<position>")


PROBES = {
    "greenhouse": probe_greenhouse,
    "lever": probe_lever,
    "ashby": probe_ashby,
    "smartrecruiters": probe_smartrecruiters,
    "recruitee": probe_recruitee,
    "personio": probe_personio,
}


def normalize_slug(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


async def probe_one(client: httpx.AsyncClient, slug: str) -> dict[str, int]:
    """Probe all providers for a slug. Returns {provider: job_count}."""
    results = await asyncio.gather(
        *(probe(client, slug) for probe in PROBES.values()),
        return_exceptions=False,
    )
    return {
        name: count
        for name, count in zip(PROBES.keys(), results, strict=True)
        if count is not None and count > 0
    }


async def probe_all(slugs: Iterable[str]) -> dict[str, dict[str, int]]:
    sem = asyncio.Semaphore(20)
    out: dict[str, dict[str, int]] = {}
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:

        async def one(slug: str) -> None:
            async with sem:
                hits = await probe_one(client, slug)
                if hits:
                    out[slug] = hits

        await asyncio.gather(*(one(s) for s in slugs))
    return out


def emit_draft(slug: str, hits: dict[str, int]) -> Path:
    """Pick the provider with the most jobs; write a draft YAML."""
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    provider = max(hits.items(), key=lambda kv: kv[1])[0]
    path = DRAFTS_DIR / f"{slug}.yaml"
    data = {
        "name": slug.replace("-", " ").title(),
        "country": "XX",  # contributor must fill before promoting
        "categories": ["tech"],
        "ats": {"provider": provider, "handle": slug},
        "notes": f"draft: probe found {hits} ({sum(hits.values())} jobs across providers)",
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    return path


async def main() -> None:
    if len(sys.argv) > 1:
        candidates = sys.argv[1:]
    else:
        candidates = [
            normalize_slug(line) for line in sys.stdin.read().splitlines() if line.strip()
        ]
    candidates = [c for c in candidates if c]
    print(f"Probing {len(candidates)} candidates against {len(PROBES)} providers…")
    results = await probe_all(candidates)
    print(f"\n{len(results)} hits:")
    for slug, hits in sorted(results.items(), key=lambda kv: -sum(kv[1].values())):
        total = sum(hits.values())
        providers = ", ".join(f"{p}:{c}" for p, c in hits.items())
        path = emit_draft(slug, hits)
        rel = path.relative_to(ROOT)
        print(f"  {slug:30}  {total:>4} jobs  [{providers}]  → {rel}")


if __name__ == "__main__":
    asyncio.run(main())
