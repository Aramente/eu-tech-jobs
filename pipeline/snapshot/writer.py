"""Write `Snapshot` to parquet (`data/snapshots/YYYY-MM-DD/jobs.parquet`)
and update the `data/latest/` pointer.

Schema is derived from the Pydantic models — single source of truth.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from pipeline.models import Company, Job, Snapshot

# pyarrow schemas (kept minimal: storage shape, not the public API contract).
_JOB_SCHEMA = pa.schema([
    pa.field("id", pa.string()),
    pa.field("company_slug", pa.string()),
    pa.field("title", pa.string()),
    pa.field("url", pa.string()),
    pa.field("location", pa.string()),
    pa.field("countries", pa.list_(pa.string())),
    pa.field("remote_policy", pa.string()),
    pa.field("seniority", pa.string()),
    pa.field("role_family", pa.string()),
    pa.field("salary_min", pa.float64()),
    pa.field("salary_max", pa.float64()),
    pa.field("salary_currency", pa.string()),
    pa.field("salary_period", pa.string()),
    pa.field("visa_sponsorship", pa.bool_()),
    pa.field("languages", pa.list_(pa.string())),
    pa.field("stack", pa.list_(pa.string())),
    pa.field("posted_at", pa.timestamp("s", tz="UTC")),
    pa.field("scraped_at", pa.timestamp("s", tz="UTC")),
    pa.field("description_md", pa.string()),
    pa.field("source", pa.string()),
])

_COMPANY_SCHEMA = pa.schema([
    pa.field("slug", pa.string()),
    pa.field("name", pa.string()),
    pa.field("country", pa.string()),
    pa.field("categories", pa.list_(pa.string())),
    pa.field("ats_provider", pa.string()),
    pa.field("ats_handle", pa.string()),
    pa.field("career_url", pa.string()),
    pa.field("github_org", pa.string()),
    pa.field("funding_stage", pa.string()),
    pa.field("size_bucket", pa.string()),
    pa.field("notes", pa.string()),
    pa.field("oss_signal", pa.bool_()),
    pa.field("top_repo_stars", pa.int64()),
    pa.field("primary_language", pa.string()),
])


def _job_to_row(j: Job) -> dict:
    s = j.salary
    return {
        "id": j.id,
        "company_slug": j.company_slug,
        "title": j.title,
        "url": j.url,
        "location": j.location,
        "countries": list(j.countries),
        "remote_policy": j.remote_policy,
        "seniority": j.seniority,
        "role_family": j.role_family,
        "salary_min": s.min if s else None,
        "salary_max": s.max if s else None,
        "salary_currency": s.currency if s else None,
        "salary_period": s.period if s else None,
        "visa_sponsorship": j.visa_sponsorship,
        "languages": list(j.languages),
        "stack": list(j.stack),
        "posted_at": j.posted_at,
        "scraped_at": j.scraped_at,
        "description_md": j.description_md,
        "source": j.source,
    }


def _company_to_row(c: Company) -> dict:
    return {
        "slug": c.slug,
        "name": c.name,
        "country": c.country,
        "categories": list(c.categories),
        "ats_provider": c.ats.provider if c.ats else None,
        "ats_handle": c.ats.handle if c.ats else None,
        "career_url": c.career_url,
        "github_org": c.github_org,
        "funding_stage": c.funding_stage,
        "size_bucket": c.size_bucket,
        "notes": c.notes,
        "oss_signal": c.oss_signal,
        "top_repo_stars": c.top_repo_stars,
        "primary_language": c.primary_language,
    }


def write_snapshot(snapshot: Snapshot, output_dir: Path) -> dict[str, Path]:
    """Persist a snapshot to disk.

    Creates:
      - data/snapshots/YYYY-MM-DD/jobs.parquet
      - data/snapshots/YYYY-MM-DD/companies.parquet
      - data/snapshots/YYYY-MM-DD/metadata.json
      - data/latest/jobs.parquet (overwritten)
      - data/latest/companies.parquet (overwritten)
      - data/latest/metadata.json (overwritten)

    Returns a dict of artifact name → path.
    """
    snap_dir = output_dir / "snapshots" / snapshot.snapshot_date.isoformat()
    snap_dir.mkdir(parents=True, exist_ok=True)
    latest_dir = output_dir / "latest"
    latest_dir.mkdir(parents=True, exist_ok=True)

    # Jobs
    jobs_path = snap_dir / "jobs.parquet"
    if snapshot.jobs:
        rows = [_job_to_row(j) for j in snapshot.jobs]
        table = pa.Table.from_pylist(rows, schema=_JOB_SCHEMA)
    else:
        table = _JOB_SCHEMA.empty_table()
    pq.write_table(table, jobs_path, compression="snappy")

    # Companies
    companies_path = snap_dir / "companies.parquet"
    if snapshot.companies:
        rows = [_company_to_row(c) for c in snapshot.companies]
        ctable = pa.Table.from_pylist(rows, schema=_COMPANY_SCHEMA)
    else:
        ctable = _COMPANY_SCHEMA.empty_table()
    pq.write_table(ctable, companies_path, compression="snappy")

    # Metadata
    meta_path = snap_dir / "metadata.json"
    meta_path.write_text(snapshot.metadata.model_dump_json(indent=2))

    # Latest pointer (copy)
    shutil.copyfile(jobs_path, latest_dir / "jobs.parquet")
    shutil.copyfile(companies_path, latest_dir / "companies.parquet")
    shutil.copyfile(meta_path, latest_dir / "metadata.json")

    return {
        "jobs": jobs_path,
        "companies": companies_path,
        "metadata": meta_path,
        "latest_jobs": latest_dir / "jobs.parquet",
    }


def read_jobs(parquet_path: Path) -> list[dict]:
    """Read a jobs parquet back as dicts (used for the site builder + tests)."""
    return pq.read_table(parquet_path).to_pylist()
