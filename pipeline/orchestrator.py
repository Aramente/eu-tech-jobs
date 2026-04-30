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
from pipeline.aggregators import AGGREGATORS
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
    extractor_results: list[ExtractorResult] = []
    all_jobs: list[Job] = []
    aggregator_companies: list[Company] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1) ATS extractors (per curated company)
        results = await asyncio.gather(
            *(_run_one(c, client, sem) for c in companies)
        )
        for jobs, result in results:
            all_jobs.extend(jobs)
            extractor_results.append(result)

        # 2) Aggregators (multi-company sources). Skipped when company_glob restricts run.
        if not company_glob:
            seen_urls = {j.url for j in all_jobs}
            for agg in AGGREGATORS:
                started = time.perf_counter()
                try:
                    agg_companies, agg_jobs = await agg.fetch_all(client=client)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("aggregator=%s error=%s", agg.NAME, exc)
                    extractor_results.append(
                        ExtractorResult(
                            extractor=agg.NAME,
                            company_slug="(aggregator)",
                            success=False,
                            duration_ms=int((time.perf_counter() - started) * 1000),
                            error=f"{type(exc).__name__}: {exc}",
                        )
                    )
                    continue
                # Dedupe: drop aggregator jobs whose URL we already have from ATS
                deduped = [j for j in agg_jobs if j.url not in seen_urls]
                seen_urls.update(j.url for j in deduped)
                all_jobs.extend(deduped)
                aggregator_companies.extend(agg_companies)
                extractor_results.append(
                    ExtractorResult(
                        extractor=agg.NAME,
                        company_slug="(aggregator)",
                        success=True,
                        job_count=len(deduped),
                        duration_ms=int((time.perf_counter() - started) * 1000),
                    )
                )

    # Merge curated + aggregator companies (curated wins on slug clash)
    merged_companies = {c.slug: c for c in aggregator_companies}
    merged_companies.update({c.slug: c for c in companies})
    final_companies = list(merged_companies.values())

    # EU-only filter: drop jobs whose location explicitly names a US/NA
    # place AND has no EU/global counter-signal. Conservative — keeps
    # empty-location jobs and any LLM-tagged remote-global / remote-eu.
    from pipeline.filters import split_jobs

    kept_jobs, dropped_jobs = split_jobs(all_jobs)
    if dropped_jobs:
        logger.info(
            "Filter: dropped %d US/NA-located jobs (kept %d EU-relevant)",
            len(dropped_jobs),
            len(kept_jobs),
        )

    metadata = PipelineMetadata(
        run_at=utcnow(),
        pipeline_version=__version__,
        company_count=len(final_companies),
        job_count=len(kept_jobs),
        extractor_results=extractor_results,
    )
    snapshot = Snapshot(
        snapshot_date=snapshot_date or date.today(),
        companies=final_companies,
        jobs=kept_jobs,
        metadata=metadata,
    )

    logger.info(
        "Done: %d EU-relevant jobs (%d dropped) from %d/%d companies (%.0f%% success)",
        len(kept_jobs),
        len(dropped_jobs),
        sum(1 for r in extractor_results if r.success),
        len(extractor_results),
        metadata.success_rate * 100,
    )

    if not dry_run:
        write_snapshot(snapshot, output_dir)

    return snapshot
