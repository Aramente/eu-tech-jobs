"""Diff two snapshots: new jobs, removed jobs, materially-changed jobs."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date
from pathlib import Path

import pyarrow.parquet as pq

from pipeline.models import Diff, Job, JobChange, SalaryBand


class DifferRefusalError(Exception):
    """Refuse to emit a diff (e.g. today empty after a broken pipeline run)."""


# Fields that trigger a "changed" diff entry. description_md changes alone
# are intentionally ignored — too noisy.
_TRACKED_FIELDS = ("title", "url", "location", "salary", "remote_policy", "seniority")


def _read_jobs(parquet_path: Path) -> list[dict]:
    if not parquet_path.exists():
        return []
    return pq.read_table(parquet_path).to_pylist()


def _row_to_job(row: dict) -> Job:
    """Reconstruct a Job from a parquet row (inverse of _job_to_row)."""
    salary = None
    if row.get("salary_currency"):
        try:
            salary = SalaryBand(
                min=row.get("salary_min"),
                max=row.get("salary_max"),
                currency=row["salary_currency"],
                period=row.get("salary_period") or "year",
            )
        except (ValueError, TypeError):
            salary = None
    return Job(
        id=row["id"],
        company_slug=row["company_slug"],
        title=row.get("title") or "",
        url=row["url"],
        location=row.get("location") or "",
        countries=list(row.get("countries") or []),
        remote_policy=row.get("remote_policy"),
        seniority=row.get("seniority"),
        role_family=row.get("role_family"),
        salary=salary,
        visa_sponsorship=row.get("visa_sponsorship"),
        languages=list(row.get("languages") or []),
        stack=list(row.get("stack") or []),
        posted_at=row.get("posted_at"),
        scraped_at=row["scraped_at"],
        description_md=row.get("description_md") or "",
        source=row["source"],
    )


def _index(jobs: Iterable[Job]) -> dict[str, Job]:
    return {j.id: j for j in jobs}


def diff_snapshots(
    today_jobs: list[Job], yesterday_jobs: list[Job], snapshot_date: date
) -> Diff:
    """Pure-function diff. Tomorrow's pipeline reads two snapshots and calls this."""
    today_idx = _index(today_jobs)
    yesterday_idx = _index(yesterday_jobs)

    new_ids = set(today_idx) - set(yesterday_idx)
    removed_ids = set(yesterday_idx) - set(today_idx)
    common_ids = set(today_idx) & set(yesterday_idx)

    changes: list[JobChange] = []
    for job_id in common_ids:
        a, b = yesterday_idx[job_id], today_idx[job_id]
        for field in _TRACKED_FIELDS:
            old = getattr(a, field)
            new = getattr(b, field)
            if old == new:
                continue
            old_s = str(old) if old is not None else None
            new_s = str(new) if new is not None else None
            changes.append(JobChange(job_id=job_id, field=field, old=old_s, new=new_s))

    return Diff(
        diff_date=snapshot_date,
        new_jobs=[today_idx[i] for i in sorted(new_ids)],
        removed_job_ids=sorted(removed_ids),
        changed=changes,
    )


def diff_from_paths(today_parquet: Path, yesterday_parquet: Path | None, diff_date: date) -> Diff:
    """Convenience: load two parquets, run diff."""
    today_rows = _read_jobs(today_parquet)
    yesterday_rows = _read_jobs(yesterday_parquet) if yesterday_parquet else []
    if today_rows == [] and yesterday_rows:
        raise DifferRefusalError(
            "Today's snapshot is empty while yesterday had jobs — refusing to emit a diff "
            "(prevents alerting on a broken run)."
        )
    today_jobs = [_row_to_job(r) for r in today_rows]
    yesterday_jobs = [_row_to_job(r) for r in yesterday_rows]
    return diff_snapshots(today_jobs, yesterday_jobs, diff_date)


def write_diff(diff: Diff, output_dir: Path) -> dict[str, Path]:
    """Persist diff as JSONL (RSS-friendly)."""
    diffs_dir = output_dir / "diffs"
    diffs_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = diffs_dir / f"{diff.diff_date.isoformat()}-diff.jsonl"
    lines: list[str] = []
    for j in diff.new_jobs:
        lines.append(json.dumps({"event": "new", **j.model_dump(mode="json")}, default=str))
    for jid in diff.removed_job_ids:
        lines.append(json.dumps({"event": "removed", "id": jid}))
    for ch in diff.changed:
        lines.append(json.dumps({"event": "changed", **ch.model_dump()}))
    jsonl_path.write_text("\n".join(lines) + ("\n" if lines else ""))
    return {"diff_jsonl": jsonl_path}
