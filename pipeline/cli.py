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
