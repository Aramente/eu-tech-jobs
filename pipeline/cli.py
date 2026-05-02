"""Click-based CLI entrypoint."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from pathlib import Path

import click

from pipeline.orchestrator import DEFAULT_CONCURRENCY, run_pipeline
from pipeline.publish.alerts import post_ntfy, post_slack, render_summary
from pipeline.publish.rss import write_rss
from pipeline.seed import load_companies
from pipeline.snapshot.differ import DifferRefusalError, diff_from_paths, write_diff


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@click.group()
def cli() -> None:
    """eu-tech-jobs pipeline."""


@cli.command("run")
@click.option("--seed-dir", default="companies", type=click.Path(path_type=Path))
@click.option("--output-dir", default="data", type=click.Path(path_type=Path))
@click.option("--companies-glob", default=None, help="e.g. 'ai/*.yaml'")
@click.option("--concurrency", default=DEFAULT_CONCURRENCY, type=int)
@click.option("--dry-run", is_flag=True)
@click.option("-v", "--verbose", is_flag=True)
def run_cmd(
    seed_dir: Path,
    output_dir: Path,
    companies_glob: str | None,
    concurrency: int,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Run the daily pipeline."""
    _setup_logging(verbose)
    snapshot = asyncio.run(
        run_pipeline(
            seed_dir=seed_dir,
            output_dir=output_dir,
            company_glob=companies_glob,
            concurrency=concurrency,
            dry_run=dry_run,
        )
    )
    success = sum(1 for r in snapshot.metadata.extractor_results if r.success)
    total = len(snapshot.metadata.extractor_results)
    click.echo(
        f"✓ {snapshot.metadata.job_count} jobs from {success}/{total} companies "
        f"({snapshot.metadata.success_rate * 100:.0f}% success)"
    )
    if total and snapshot.metadata.success_rate < 0.5:
        raise SystemExit(1)


@cli.command("seed")
@click.argument("subcommand", type=click.Choice(["validate", "list"]))
@click.option("--seed-dir", default="companies", type=click.Path(path_type=Path))
def seed_cmd(subcommand: str, seed_dir: Path) -> None:
    """Validate or list the curated company seed."""
    companies = load_companies(seed_dir)
    if subcommand == "validate":
        click.echo(f"✓ {len(companies)} companies validate")
    elif subcommand == "list":
        for c in sorted(companies, key=lambda x: x.slug):
            ats = f"{c.ats.provider}:{c.ats.handle}" if c.ats else "—"
            click.echo(f"{c.slug:30}  {c.country}  {ats}")


@cli.command("diff")
@click.option("--output-dir", default="data", type=click.Path(path_type=Path))
@click.option(
    "--diff-date",
    default=None,
    help="ISO date to use as 'today' (default: today UTC). Yesterday is auto-derived.",
)
@click.option("-v", "--verbose", is_flag=True)
def diff_cmd(output_dir: Path, diff_date: str | None, verbose: bool) -> None:
    """Compute today's diff vs yesterday's snapshot, write JSONL + RSS, post alerts."""
    _setup_logging(verbose)
    today = date.fromisoformat(diff_date) if diff_date else date.today()
    yesterday = today - timedelta(days=1)
    today_pq = output_dir / "snapshots" / today.isoformat() / "jobs.parquet"
    yesterday_pq = output_dir / "snapshots" / yesterday.isoformat() / "jobs.parquet"
    if not today_pq.exists():
        click.echo(f"No snapshot at {today_pq}; run 'pipeline run' first.", err=True)
        raise SystemExit(1)
    try:
        diff = diff_from_paths(today_pq, yesterday_pq if yesterday_pq.exists() else None, today)
    except DifferRefusalError as exc:
        click.echo(f"⚠ {exc}", err=True)
        raise SystemExit(2) from exc
    write_diff(diff, output_dir)
    write_rss(diff, output_dir)
    summary = render_summary(diff)
    click.echo(summary)
    if post_ntfy(diff):
        click.echo("✓ ntfy posted")
    if post_slack(diff):
        click.echo("✓ slack posted")


@cli.command("enrich")
@click.option("--seed-dir", default="companies", type=click.Path(path_type=Path))
@click.option("-v", "--verbose", is_flag=True)
def enrich_cmd(seed_dir: Path, verbose: bool) -> None:
    """Enrich curated companies with GitHub-org signals (oss, stars, language)."""
    import asyncio as _asyncio

    import yaml

    from pipeline.enrich.company import enrich_all

    _setup_logging(verbose)
    companies = load_companies(seed_dir)
    enriched = _asyncio.run(enrich_all(companies))
    # Write back to YAMLs (preserving filename = slug structure)
    updated = 0
    for c in enriched:
        if not c.github_org:
            continue
        # Find original path
        for path in seed_dir.rglob(f"{c.slug}.yaml"):
            data = yaml.safe_load(path.read_text())
            changed = False
            for field in ("oss_signal", "top_repo_stars", "primary_language"):
                v = getattr(c, field)
                if v is not None and data.get(field) != v:
                    data[field] = v
                    changed = True
            if changed:
                path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
                updated += 1
            break
    click.echo(f"✓ enriched {updated} company YAMLs")


@cli.command("tag")
@click.option("--seed-dir", default="companies", type=click.Path(path_type=Path))
@click.option("--output-dir", default="data", type=click.Path(path_type=Path))
@click.option("--limit", default=None, type=int, help="Cap the number of jobs to tag.")
@click.option(
    "--variant",
    default=None,
    help="Prompt variant (default: pipeline.enrich.prompts.DEFAULT_VARIANT).",
)
@click.option(
    "--retag-all",
    is_flag=True,
    help="Re-tag every job, not just untagged ones (use after a prompt change).",
)
@click.option(
    "--concurrency",
    default=20,
    type=int,
    help="Concurrent DeepSeek calls (20 is well under DeepSeek's per-key limit).",
)
@click.option(
    "--checkpoint-every",
    default=500,
    type=int,
    help="Write the parquet every N successful tag operations so a timeout can't lose work.",
)
@click.option("-v", "--verbose", is_flag=True)
def tag_cmd(
    seed_dir: Path,
    output_dir: Path,
    limit: int | None,
    variant: str | None,
    retag_all: bool,
    concurrency: int,
    checkpoint_every: int,
    verbose: bool,
) -> None:
    """Tag the latest snapshot's jobs with seniority/role/stack via DeepSeek (or Mistral).

    No-op when no LLM provider is configured (DEEPSEEK_API_KEY or
    MISTRAL_API_KEY). Reads the latest jobs.parquet, tags in parallel,
    writes back periodically (checkpoint-every) so a timeout never loses
    completed work.
    """
    import time as _time
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from datetime import date as _date

    import pyarrow.parquet as _pq

    from pipeline.enrich.prompts import DEFAULT_VARIANT
    from pipeline.enrich.tagger import (
        TaggerFatalError,
        is_configured,
        selected_provider,
        tag_job,
    )
    from pipeline.models import PipelineMetadata, Snapshot, utcnow
    from pipeline.snapshot.differ import _row_to_job
    from pipeline.snapshot.writer import write_snapshot

    _setup_logging(verbose)
    if not is_configured():
        click.echo(
            "⚠ tagger not configured (DEEPSEEK_API_KEY or MISTRAL_API_KEY unset). No-op.",
            err=True,
        )
        return
    chosen_variant = variant or DEFAULT_VARIANT
    click.echo(
        f"Tagger active: provider = {selected_provider()}, variant = {chosen_variant}, "
        f"concurrency = {concurrency}"
    )

    parquet = output_dir / "latest" / "jobs.parquet"
    if not parquet.exists():
        click.echo("No latest snapshot to tag; run 'pipeline run' first.", err=True)
        raise SystemExit(1)
    rows = _pq.read_table(parquet).to_pylist()
    jobs = [_row_to_job(r) for r in rows]
    if retag_all:
        targets_pool = jobs
    else:
        targets_pool = [
            j for j in jobs if j.role_family is None and j.seniority is None
        ]
    click.echo(
        f"{len(jobs)} jobs in snapshot; {len(targets_pool)} target(s) "
        f"({'retag-all' if retag_all else 'untagged-only'})."
    )
    targets = targets_pool if limit is None else targets_pool[:limit]
    click.echo(f"Tagging {len(targets)} jobs at concurrency {concurrency}…")

    # Load curated YAML companies AND read the aggregator-discovered
    # companies from the existing companies.parquet so the rewrite
    # doesn't drop them. (fjr-*, wttj-*, wttjc-*, via-* etc — aggregator
    # companies are created at run time and only persisted in the parquet.)
    from pipeline.models import Company

    yaml_companies = load_companies(seed_dir)
    yaml_slugs = {c.slug for c in yaml_companies}
    companies_pq = output_dir / "latest" / "companies.parquet"
    aggregator_companies: list[Company] = []
    if companies_pq.exists():
        for row in _pq.read_table(companies_pq).to_pylist():
            slug = row.get("slug")
            if not slug or slug in yaml_slugs:
                continue
            ats = None
            if row.get("ats_provider") and row.get("ats_handle"):
                from pipeline.models import ATSReference
                ats = ATSReference(
                    provider=row["ats_provider"], handle=row["ats_handle"]
                )
            try:
                aggregator_companies.append(Company(
                    slug=slug,
                    name=row.get("name") or slug,
                    country=row.get("country") or "XX",
                    categories=list(row.get("categories") or []),
                    industry_tags=list(row.get("industry_tags") or []),
                    ats=ats,
                    career_url=row.get("career_url"),
                    github_org=row.get("github_org"),
                    funding_stage=row.get("funding_stage"),
                    size_bucket=row.get("size_bucket"),
                    notes=row.get("notes"),
                    oss_signal=row.get("oss_signal"),
                    top_repo_stars=row.get("top_repo_stars"),
                    primary_language=row.get("primary_language"),
                ))
            except Exception:
                # Skip rows that don't satisfy Company validators (e.g.
                # neither ats nor career_url) rather than failing tag.
                continue
    companies = yaml_companies + aggregator_companies

    def _checkpoint(tagged_by_id: dict, processed: int) -> None:
        """Write the current parquet so a future kill -9 doesn't lose work."""
        final_jobs = [tagged_by_id.get(j.id, j) for j in jobs]
        snapshot = Snapshot(
            snapshot_date=_date.today(),
            companies=companies,
            jobs=final_jobs,
            metadata=PipelineMetadata(
                run_at=utcnow(),
                pipeline_version="0.1.0",
                company_count=len(companies),
                job_count=len(final_jobs),
            ),
        )
        write_snapshot(snapshot, output_dir)
        click.echo(f"  ✓ checkpoint at {processed}/{len(targets)}")

    tagged_by_id: dict[str, object] = {}
    started = _time.time()
    last_checkpoint = 0
    completed = 0

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        future_to_job = {
            pool.submit(tag_job, j, variant=chosen_variant): j for j in targets
        }
        try:
            for fut in as_completed(future_to_job):
                j = future_to_job[fut]
                try:
                    tagged_by_id[j.id] = fut.result()
                except TaggerFatalError as exc:
                    pool.shutdown(wait=False, cancel_futures=True)
                    click.echo(
                        f"\n✗ TAGGER FATAL: {exc}\n"
                        "  Likely cause: DEEPSEEK_API_KEY balance / quota / "
                        "credentials. Aborting before more wasted calls.",
                        err=True,
                    )
                    raise SystemExit(2) from exc
                except Exception as exc:  # noqa: BLE001
                    logging.warning("tag_job failed for %s: %s", j.id, exc)
                    tagged_by_id[j.id] = j
                completed += 1
                if completed % 100 == 0:
                    elapsed = _time.time() - started
                    rate = completed / max(elapsed, 1)
                    eta = (len(targets) - completed) / max(rate, 0.01)
                    click.echo(
                        f"  {completed}/{len(targets)} "
                        f"({elapsed:.0f}s · {rate:.1f}/s · eta {eta:.0f}s)"
                    )
                if completed - last_checkpoint >= checkpoint_every:
                    _checkpoint(tagged_by_id, completed)
                    last_checkpoint = completed
        finally:
            pass  # ThreadPoolExecutor `with` already handles shutdown

    final_jobs = [tagged_by_id.get(j.id, j) for j in jobs]

    # Use the same merged set (YAML + aggregator) we built earlier so the
    # final write preserves fjr-*, wttj-*, wttjc-*, via-* companies.
    snapshot = Snapshot(
        snapshot_date=_date.today(),
        companies=companies,
        jobs=final_jobs,
        metadata=PipelineMetadata(
            run_at=utcnow(),
            pipeline_version="0.1.0",
            company_count=len(companies),
            job_count=len(final_jobs),
        ),
    )
    write_snapshot(snapshot, output_dir)
    click.echo(f"✓ wrote {len(final_jobs)} jobs ({len(targets)} freshly tagged)")


@cli.command("publish")
@click.option("--output-dir", default="data", type=click.Path(path_type=Path))
@click.option(
    "--repo-id",
    default="Aramente/eu-tech-jobs",
    help="HF Dataset repo id.",
)
def publish_cmd(output_dir: Path, repo_id: str) -> None:
    """Push data/ to the Hugging Face Dataset repo."""
    from pipeline.publish.hf import PublishConfigError, push_to_hf

    try:
        url = push_to_hf(output_dir, repo_id=repo_id)
        click.echo(f"✓ pushed to HF: {url}")
    except PublishConfigError as exc:
        click.echo(f"⚠ {exc}", err=True)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    cli()
