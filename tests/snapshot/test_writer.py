"""Tests for the parquet snapshot writer."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pyarrow.parquet as pq

from pipeline.models import (
    ATSReference,
    Company,
    Job,
    PipelineMetadata,
    SalaryBand,
    Snapshot,
    utcnow,
)
from pipeline.snapshot.writer import read_jobs, write_snapshot


def _company():
    return Company(
        slug="wayve",
        name="Wayve",
        country="GB",
        categories=["ai"],
        ats=ATSReference(provider="greenhouse", handle="wayve"),
    )


def _job(title="Senior Engineer", url="https://example.com/job/1"):
    return Job(
        id=Job.make_id("wayve", url),
        company_slug="wayve",
        title=title,
        url=url,
        location="London",
        scraped_at=utcnow(),
        source="greenhouse",
    )


def _snapshot(jobs=None, companies=None):
    if jobs is None:
        jobs = [_job()]
    if companies is None:
        companies = [_company()]
    return Snapshot(
        snapshot_date=date(2026, 4, 29),
        companies=companies,
        jobs=jobs,
        metadata=PipelineMetadata(
            run_at=utcnow(),
            pipeline_version="0.1.0",
            company_count=len(companies),
            job_count=len(jobs),
        ),
    )


def test_writes_dated_folder(tmp_path: Path):
    paths = write_snapshot(_snapshot(), tmp_path)
    assert paths["jobs"].exists()
    assert paths["jobs"].parent.name == "2026-04-29"
    assert paths["latest_jobs"].exists()
    assert paths["latest_jobs"].parent.name == "latest"


def test_round_trip_preserves_fields(tmp_path: Path):
    j = _job(title="Ingénieur·e ML — €100k")
    paths = write_snapshot(_snapshot(jobs=[j]), tmp_path)
    rows = read_jobs(paths["jobs"])
    assert len(rows) == 1
    assert rows[0]["title"] == "Ingénieur·e ML — €100k"
    assert rows[0]["company_slug"] == "wayve"


def test_empty_jobs_writes_valid_parquet(tmp_path: Path):
    paths = write_snapshot(_snapshot(jobs=[]), tmp_path)
    table = pq.read_table(paths["jobs"])
    assert table.num_rows == 0
    # Schema must still be present
    assert "title" in table.schema.names


def test_salary_band_round_trip(tmp_path: Path):
    j = _job()
    j2 = j.model_copy(update={"salary": SalaryBand(min=80000, max=120000, currency="EUR")})
    paths = write_snapshot(_snapshot(jobs=[j2]), tmp_path)
    rows = read_jobs(paths["jobs"])
    assert rows[0]["salary_min"] == 80000
    assert rows[0]["salary_max"] == 120000
    assert rows[0]["salary_currency"] == "EUR"


def test_writing_two_dates_does_not_overwrite(tmp_path: Path):
    s1 = _snapshot()
    s2 = Snapshot(
        snapshot_date=date(2026, 4, 30),
        companies=s1.companies,
        jobs=s1.jobs,
        metadata=s1.metadata,
    )
    p1 = write_snapshot(s1, tmp_path)
    p2 = write_snapshot(s2, tmp_path)
    assert p1["jobs"].exists()
    assert p2["jobs"].exists()
    assert p1["jobs"] != p2["jobs"]
    # Latest reflects the most recent write
    assert p2["latest_jobs"].read_bytes() == p2["jobs"].read_bytes()


def test_metadata_json_committed(tmp_path: Path):
    paths = write_snapshot(_snapshot(), tmp_path)
    text = paths["metadata"].read_text()
    assert '"pipeline_version"' in text
    assert '"job_count"' in text
