"""Company-level enrichment via the GitHub API.

Populates `oss_signal`, `top_repo_stars`, `primary_language` for any company
with a `github_org` set in its YAML.

Runs as a separate (slower, weekly) command — not in the daily critical path.
Auth via GITHUB_TOKEN env var lifts the rate limit from 60 to 5,000 req/h.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from pipeline.models import Company

logger = logging.getLogger(__name__)

USER_AGENT = "ai-startups-bot/0.1 (+https://github.com/Aramente/eu-tech-jobs)"
_OSS_LANGUAGES = {
    "Python", "TypeScript", "JavaScript", "Go", "Rust", "C++", "C", "Java",
    "Kotlin", "Swift", "Ruby", "Elixir", "Erlang", "Haskell", "Clojure",
    "Scala", "OCaml", "Zig", "Nim", "Crystal",
}
_OSS_STAR_THRESHOLD = 100


@dataclass
class _Enrichment:
    oss_signal: bool | None = None
    top_repo_stars: int | None = None
    primary_language: str | None = None


@retry(
    retry=retry_if_exception_type(httpx.TransportError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def _fetch_top_repo(client: httpx.AsyncClient, org: str) -> dict | None:
    resp = await client.get(
        f"https://api.github.com/orgs/{org}/repos",
        params={"sort": "stars", "type": "public", "per_page": 1},
        timeout=20.0,
    )
    if resp.status_code == 404:
        return None
    if resp.status_code == 403:
        # Most likely rate-limit; back off the whole batch
        logger.warning("GitHub 403 (rate limit?) for %s", org)
        return None
    if resp.status_code != 200:
        return None
    items = resp.json()
    if not items:
        return None
    return items[0]


async def enrich_company(client: httpx.AsyncClient, company: Company) -> Company:
    """Fetch top-starred repo for the company's GitHub org."""
    if not company.github_org:
        return company
    repo = await _fetch_top_repo(client, company.github_org)
    if not repo:
        return company  # 404 / rate-limit / no repos: leave fields untouched
    stars = repo.get("stargazers_count", 0) or 0
    primary = repo.get("language") or None
    oss = stars >= _OSS_STAR_THRESHOLD and primary in _OSS_LANGUAGES
    return company.model_copy(
        update={
            "oss_signal": bool(oss),
            "top_repo_stars": int(stars),
            "primary_language": primary,
        }
    )


async def enrich_all(companies: list[Company], *, concurrency: int = 5) -> list[Company]:
    sem = asyncio.Semaphore(concurrency)
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(headers=headers, timeout=20.0) as client:

        async def one(c: Company) -> Company:
            async with sem:
                try:
                    return await enrich_company(client, c)
                except httpx.HTTPError as exc:
                    logger.warning("enrich %s: %s", c.slug, exc)
                    return c

        return await asyncio.gather(*(one(c) for c in companies))
