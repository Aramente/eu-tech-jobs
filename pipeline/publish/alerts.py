"""Send a diff summary alert via ntfy.sh (and optionally Slack)."""

from __future__ import annotations

import logging
import os
from collections import Counter

import httpx

from pipeline.models import Diff, Job

logger = logging.getLogger(__name__)


def _ascii_safe(s: str) -> str:
    """HTTP headers must be ASCII (Bored CV em-dash bug, 2026-04)."""
    return s.encode("ascii", errors="replace").decode("ascii")


def render_summary(diff: Diff) -> str:
    """Pure-function summary text (no I/O)."""
    new_count = len(diff.new_jobs)
    removed_count = len(diff.removed_job_ids)
    changed_count = len(diff.changed)
    top_companies = _top_companies(diff.new_jobs)
    parts = [
        f"+{new_count} new · -{removed_count} removed · ~{changed_count} changed",
    ]
    if top_companies:
        parts.append("Top: " + ", ".join(f"{c}({n})" for c, n in top_companies))
    return "\n".join(parts)


def _top_companies(jobs: list[Job], limit: int = 5) -> list[tuple[str, int]]:
    return Counter(j.company_slug for j in jobs).most_common(limit)


def post_ntfy(diff: Diff, *, topic: str | None = None) -> bool:
    topic = topic or os.environ.get("NTFY_TOPIC")
    if not topic:
        return False
    if diff.is_empty:
        return False
    body = render_summary(diff)
    title = f"eu-tech-jobs {diff.diff_date.isoformat()}"
    try:
        resp = httpx.post(
            f"https://ntfy.sh/{topic}",
            content=body.encode("utf-8"),
            headers={
                "Title": _ascii_safe(title),
                "Tags": "briefcase",
                "Click": "https://aramente.github.io/eu-tech-jobs/",
            },
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        logger.warning("ntfy unreachable: %s", exc)
        return False
    return resp.status_code < 400


def post_slack(diff: Diff, *, webhook_url: str | None = None) -> bool:
    webhook_url = webhook_url or os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url or diff.is_empty:
        return False
    text = render_summary(diff)
    try:
        resp = httpx.post(webhook_url, json={"text": text}, timeout=10.0)
    except httpx.HTTPError as exc:
        logger.warning("Slack webhook unreachable: %s", exc)
        return False
    return resp.status_code < 400
