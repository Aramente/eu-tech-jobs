"""Tests for pipeline.models."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from pipeline.models import (
    ATSReference,
    Company,
    Diff,
    ExtractorResult,
    Job,
    PipelineMetadata,
    SalaryBand,
    Snapshot,
    utcnow,
)


def _company(**overrides):
    base = dict(
        slug="huggingface",
        name="Hugging Face",
        country="FR",
        categories=["ai", "oss"],
        ats=ATSReference(provider="greenhouse", handle="huggingface"),
    )
    base.update(overrides)
    return Company(**base)


def _job(**overrides):
    base = dict(
        id=Job.make_id("huggingface", "https://example.com/job/123"),
        company_slug="huggingface",
        title="Senior ML Engineer",
        url="https://example.com/job/123",
        scraped_at=utcnow(),
        source="greenhouse",
    )
    base.update(overrides)
    return Job(**base)


class TestCompany:
    def test_minimum_valid_round_trip(self):
        c = _company()
        assert Company.model_validate(c.model_dump()) == c

    def test_at_least_one_source_required(self):
        with pytest.raises(ValidationError, match="ats.*career_url"):
            Company(slug="x", name="X", country="FR")

    def test_career_url_only_is_valid(self):
        c = Company(
            slug="x",
            name="X",
            country="FR",
            career_url="https://example.com/jobs",
        )
        assert c.ats is None

    def test_invalid_slug_rejected(self):
        with pytest.raises(ValidationError, match="slug"):
            _company(slug="Invalid Slug!")

    def test_invalid_country_rejected(self):
        with pytest.raises(ValidationError):
            _company(country="FRA")

    def test_extra_field_forbidden(self):
        with pytest.raises(ValidationError, match="extra"):
            Company.model_validate(
                {**_company().model_dump(), "unknown_field": "x"}
            )


class TestJob:
    def test_id_is_stable(self):
        a = Job.make_id("foo", "https://x.com/job/1")
        b = Job.make_id("foo", "https://x.com/job/1")
        assert a == b
        assert len(a) == 16

    def test_id_differs_with_company(self):
        a = Job.make_id("foo", "https://x.com/job/1")
        b = Job.make_id("bar", "https://x.com/job/1")
        assert a != b

    def test_minimum_valid(self):
        j = _job()
        assert j.id == Job.make_id("huggingface", "https://example.com/job/123")
        assert j.remote_policy is None
        assert j.stack == []

    def test_invalid_remote_policy(self):
        with pytest.raises(ValidationError):
            _job(remote_policy="weird")  # type: ignore[arg-type]

    def test_unicode_round_trip(self):
        j = _job(title="Ingénieur·e ML — Paris", description_md="€100k+ + équité")
        assert Job.model_validate(j.model_dump()) == j


class TestSalaryBand:
    def test_valid_range(self):
        s = SalaryBand(min=80000, max=120000, currency="EUR")
        assert s.period == "year"

    def test_min_only(self):
        s = SalaryBand(min=60000, currency="EUR")
        assert s.max is None

    def test_max_only(self):
        s = SalaryBand(max=150000, currency="USD")
        assert s.min is None

    def test_neither_rejected(self):
        with pytest.raises(ValidationError, match="at least one"):
            SalaryBand(currency="EUR")

    def test_min_gt_max_rejected(self):
        with pytest.raises(ValidationError, match="min must be"):
            SalaryBand(min=200000, max=100000, currency="EUR")


class TestSnapshotAndDiff:
    def test_empty_snapshot(self):
        meta = PipelineMetadata(
            run_at=utcnow(),
            pipeline_version="0.1.0",
            company_count=0,
            job_count=0,
        )
        s = Snapshot(snapshot_date=date(2026, 4, 29), companies=[], jobs=[], metadata=meta)
        assert s.metadata.success_rate == 1.0

    def test_metadata_success_rate(self):
        meta = PipelineMetadata(
            run_at=utcnow(),
            pipeline_version="0.1.0",
            company_count=2,
            job_count=10,
            extractor_results=[
                ExtractorResult(
                    extractor="greenhouse", company_slug="a", success=True, job_count=5
                ),
                ExtractorResult(
                    extractor="greenhouse", company_slug="b", success=False, error="404"
                ),
            ],
        )
        assert meta.success_rate == 0.5

    def test_diff_is_empty(self):
        d = Diff(diff_date=date(2026, 4, 29))
        assert d.is_empty
        d2 = Diff(diff_date=date(2026, 4, 29), new_jobs=[_job()])
        assert not d2.is_empty
