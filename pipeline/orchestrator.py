"""Pipeline orchestrator: seed → fetch jobs (per ATS) → snapshot.

v0 supports Greenhouse only. Adding more ATSes = register a new module in
`pipeline.extractors.EXTRACTORS` and the orchestrator dispatches automatically.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date
from pathlib import Path

import httpx

from pipeline import __version__
from pipeline.extractors import EXTRACTORS, ExtractorError
from pipeline.models import (
    Company,
    ExtractorResult,
    Job,
    PipelineMetadata,
    Snapshot,
    utcnow,
)
from pipeline.seed import load_companies
from pipeline.snapshot.writer import write_snapshot

logger = logging.getLogger(__name__)

DEFAULT_CONCURRENCY = 10


async def _run_one(
    company: Company,
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
) -> tuple[list[Job], ExtractorResult]:
    if company.ats is None:
        return [], ExtractorResult(
            extractor="none",
            company_slug=company.slug,
            success=False,
            error="No ATS reference (career-page scraping not in v0)",
        )
    provider = company.ats.provider
    module = EXTRACTORS.get(provider)
    if module is None:
        return [], ExtractorResult(
            extractor=provider,
            company_slug=company.slug,
            success=False,
            error=f"Unsupported ATS provider: {provider} (v0 supports greenhouse only)",
        )
    started = time.perf_counter()
    async with sem:
        try:
            jobs = await module.fetch_jobs(
                company.ats.handle, company_slug=company.slug, client=client
            )
        except ExtractorError as exc:
            duration = int((time.perf_counter() - started) * 1000)
            logger.warning("extractor=%s slug=%s error=%s", provider, company.slug, exc)
            return [], ExtractorResult(
                extractor=provider,
                company_slug=company.slug,
                success=False,
                duration_ms=duration,
                error=str(exc),
            )
        except Exception as exc:  # noqa: BLE001 — defensive last-resort
            duration = int((time.perf_counter() - started) * 1000)
            logger.exception("unexpected error for %s", company.slug)
            return [], ExtractorResult(
                extractor=provider,
                company_slug=company.slug,
                success=False,
                duration_ms=duration,
                error=f"Unexpected: {type(exc).__name__}: {exc}",
            )
    duration = int((time.perf_counter() - started) * 1000)
    return jobs, ExtractorResult(
        extractor=provider,
        company_slug=company.slug,
        success=True,
        job_count=len(jobs),
        duration_ms=duration,
    )


async def run_pipeline(
    seed_dir: Path,
    output_dir: Path,
    *,
    snapshot_date: date | None = None,
    company_glob: str | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    dry_run: bool = False,
) -> Snapshot:
    """Execute the full pipeline.

    Args:
        seed_dir: directory holding curated `companies/**/*.yaml`.
        output_dir: where snapshots / latest are written.
        snapshot_date: override (defaults to today UTC).
        company_glob: optional glob (relative to seed_dir) to subset companies.
        concurrency: max concurrent HTTP requests.
        dry_run: skip writing snapshot to disk.
    """
    companies_all = load_companies(seed_dir)
    if company_glob:
        matching_paths = {p.stem for p in seed_dir.rglob(company_glob)}
        companies = [c for c in companies_all if c.slug in matching_paths]
    else:
        companies = companies_all
    logger.info("Pipeline run: %d companies", len(companies))

    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(timeout=30.0) as client:
        results = await asyncio.gather(
            *(_run_one(c, client, sem) for c in companies)
        )

    all_jobs: list[Job] = []
    extractor_results: list[ExtractorResult] = []
    for jobs, result in results:
        all_jobs.extend(jobs)
        extractor_results.append(result)

    metadata = PipelineMetadata(
        run_at=utcnow(),
        pipeline_version=__version__,
        company_count=len(companies),
        job_count=len(all_jobs),
        extractor_results=extractor_results,
    )
    snapshot = Snapshot(
        snapshot_date=snapshot_date or date.today(),
        companies=companies,
        jobs=all_jobs,
        metadata=metadata,
    )

    logger.info(
        "Done: %d jobs from %d/%d companies (%.0f%% success)",
        len(all_jobs),
        sum(1 for r in extractor_results if r.success),
        len(extractor_results),
        metadata.success_rate * 100,
    )

    if not dry_run:
        write_snapshot(snapshot, output_dir)

    return snapshot
