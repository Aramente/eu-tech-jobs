"""Ashby public job-board extractor (GraphQL endpoint used by hosted boards).

Endpoint: POST https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiBoardWithTeams
Public, no auth required for the listing. Returns titles, locations, employment
type. Per-posting full descriptions live behind a separate query — for v1 we
keep descriptions empty (the URL points to Ashby's hosted page).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from pipeline.extractors.base import (
    ExtractorNotFoundError,
    ExtractorTransientError,
)
from pipeline.models import Job, utcnow

logger = logging.getLogger(__name__)

NAME = "ashby"
RATE_LIMIT_PER_SEC = 5.0
USER_AGENT = "ai-startups-bot/0.1 (+https://github.com/Aramente/eu-tech-jobs)"
_ENDPOINT = "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiBoardWithTeams"
_QUERY = """
query ApiBoardWithTeams($organizationHostedJobsPageName: String!) {
  jobBoard: jobBoardWithTeams(organizationHostedJobsPageName: $organizationHostedJobsPageName) {
    teams { id name __typename }
    jobPostings {
      id
      title
      teamId
      locationName
      employmentType
      compensationTierSummary
      secondaryLocations { locationName __typename }
      __typename
    }
    __typename
  }
}
""".strip()


def parse_jobs(payload: dict[str, Any], company_slug: str, handle: str) -> list[Job]:
    """Pure parser. Ashby returns `data.jobBoard.jobPostings`."""
    job_board = (payload or {}).get("data", {}).get("jobBoard") or {}
    postings = job_board.get("jobPostings") or []
    out: list[Job] = []
    now = utcnow()
    for raw in postings:
        post_id = raw.get("id")
        if not post_id:
            continue
        url = f"https://jobs.ashbyhq.com/{handle}/{post_id}"
        title = (raw.get("title") or "").strip()
        loc = (raw.get("locationName") or "").strip()
        secondary = raw.get("secondaryLocations") or []
        if secondary:
            extras = ", ".join(
                s.get("locationName", "") for s in secondary if s.get("locationName")
            )
            if extras:
                loc = f"{loc} (+ {extras})" if loc else extras
        out.append(
            Job(
                id=Job.make_id(company_slug, url),
                company_slug=company_slug,
                title=title or "(untitled)",
                url=url,
                location=loc,
                scraped_at=now,
                description_md="",  # full description requires per-posting fetch (v2)
                source=NAME,
            )
        )
    return out


@retry(
    retry=retry_if_exception_type((httpx.TransportError, ExtractorTransientError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def _fetch_payload(client: httpx.AsyncClient, handle: str) -> dict[str, Any]:
    body = {
        "operationName": "ApiBoardWithTeams",
        "variables": {"organizationHostedJobsPageName": handle},
        "query": _QUERY,
    }
    resp = await client.post(
        _ENDPOINT,
        json=body,
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
        timeout=30.0,
    )
    if resp.status_code >= 500:
        raise ExtractorTransientError(f"Ashby {resp.status_code} for {handle}")
    if resp.status_code >= 400:
        raise ExtractorTransientError(
            f"Ashby {resp.status_code} for {handle}: {resp.text[:200]}"
        )
    data = resp.json()
    if data.get("data", {}).get("jobBoard") is None and (data.get("errors") or []):
        # Ashby returns 200 with errors[] when handle doesn't exist
        msg = str(data.get("errors") or "")
        if "not found" in msg.lower() or "could not find" in msg.lower():
            raise ExtractorNotFoundError(f"Ashby board not found: {handle}")
        raise ExtractorTransientError(f"Ashby errors for {handle}: {msg[:200]}")
    return data


async def fetch_jobs(
    handle: str, *, company_slug: str, client: httpx.AsyncClient | None = None
) -> list[Job]:
    """Fetch + parse postings from an Ashby hosted board."""
    owns = client is None
    client = client or httpx.AsyncClient()
    try:
        payload = await _fetch_payload(client, handle)
    finally:
        if owns:
            await client.aclose()
    return parse_jobs(payload, company_slug, handle)
