"""Core data models for the ai-startups pipeline.

Single source of truth for the public schema. JSON Schema files in `schemas/`
are generated from these — never edit those by hand.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ATSProvider = Literal[
    "greenhouse",
    "lever",
    "ashby",
    "workable",
    "recruitee",
    "personio",
    "smartrecruiters",
    "teamtailor",
]

RemotePolicy = Literal["onsite", "hybrid", "remote", "remote-eu", "remote-global"]
Seniority = Literal["intern", "junior", "mid", "senior", "staff", "principal", "exec"]
RoleFamily = Literal[
    "engineering",
    "ml-ai",
    "data",
    "product",
    "design",
    "sales",
    "marketing",
    "ops",
    "support",
    "finance",
    "legal",
    "hr",
    "research",
    "other",
]
SalaryPeriod = Literal["year", "month", "day", "hour"]
SizeBucket = Literal["1-10", "11-50", "51-200", "201-500", "501-1000", "1001-5000", "5001+"]
FundingStage = Literal[
    "bootstrapped",
    "pre-seed",
    "seed",
    "series-a",
    "series-b",
    "series-c",
    "series-d",
    "series-e+",
    "public",
    "acquired",
]


class ATSReference(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: ATSProvider
    handle: str = Field(min_length=1, max_length=128)


class Company(BaseModel):
    """A curated company entry. Source: `companies/<category>/<slug>.yaml`."""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    name: str
    country: str = Field(min_length=2, max_length=2, description="ISO 3166-1 alpha-2")
    categories: list[Literal["ai", "tech", "oss", "remote-eu"]] = Field(default_factory=list)
    ats: ATSReference | None = None
    career_url: str | None = None
    github_org: str | None = None
    funding_stage: FundingStage | None = None
    size_bucket: SizeBucket | None = None
    notes: str | None = None

    # Enrichment fields (populated by the enricher; null on first ingest)
    oss_signal: bool | None = None
    top_repo_stars: int | None = None
    primary_language: str | None = None

    @model_validator(mode="after")
    def _at_least_one_source(self) -> Company:
        if self.ats is None and self.career_url is None:
            raise ValueError("Company must have either `ats` or `career_url` set.")
        return self


class SalaryBand(BaseModel):
    model_config = ConfigDict(frozen=True)

    min: float | None = None
    max: float | None = None
    currency: str = Field(min_length=3, max_length=3, description="ISO 4217")
    period: SalaryPeriod = "year"

    @model_validator(mode="after")
    def _check_range(self) -> SalaryBand:
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("SalaryBand min must be <= max.")
        if self.min is None and self.max is None:
            raise ValueError("SalaryBand must have at least one of min/max.")
        return self


class Job(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    company_slug: str
    title: str
    url: str
    location: str = ""
    countries: list[str] = Field(default_factory=list)
    remote_policy: RemotePolicy | None = None
    seniority: Seniority | None = None
    role_family: RoleFamily | None = None
    salary: SalaryBand | None = None
    visa_sponsorship: bool | None = None
    languages: list[str] = Field(default_factory=list)
    stack: list[str] = Field(default_factory=list)
    posted_at: datetime | None = None
    scraped_at: datetime
    description_md: str = ""
    source: str = Field(description="extractor name, e.g. 'greenhouse'")

    @staticmethod
    def make_id(company_slug: str, canonical_url: str) -> str:
        """Stable hash so the same job has the same id across daily runs."""
        h = hashlib.sha256(f"{company_slug}:{canonical_url}".encode()).hexdigest()
        return h[:16]


class ExtractorResult(BaseModel):
    """Per-extractor health entry stored in PipelineMetadata."""

    model_config = ConfigDict(extra="forbid")

    extractor: str
    company_slug: str
    success: bool
    job_count: int = 0
    duration_ms: int = 0
    error: str | None = None


class PipelineMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_at: datetime
    pipeline_version: str
    company_count: int
    job_count: int
    extractor_results: list[ExtractorResult] = Field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if not self.extractor_results:
            return 1.0
        ok = sum(1 for r in self.extractor_results if r.success)
        return ok / len(self.extractor_results)


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_date: date
    companies: list[Company]
    jobs: list[Job]
    metadata: PipelineMetadata


class JobChange(BaseModel):
    """A field-level change between two snapshots of the same job id."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    field: str
    old: str | None
    new: str | None


class Diff(BaseModel):
    model_config = ConfigDict(extra="forbid")

    diff_date: date
    new_jobs: list[Job] = Field(default_factory=list)
    removed_job_ids: list[str] = Field(default_factory=list)
    changed: list[JobChange] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.new_jobs or self.removed_job_ids or self.changed)


def utcnow() -> datetime:
    """Timezone-aware UTC now, second-precision (parquet-friendly)."""
    return datetime.now(UTC).replace(microsecond=0)
