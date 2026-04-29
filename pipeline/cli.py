"""Click-based CLI entrypoint."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import click

from pipeline.orchestrator import DEFAULT_CONCURRENCY, run_pipeline
from pipeline.seed import load_companies


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@click.group()
def cli() -> None:
    """ai-startups pipeline."""


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


if __name__ == "__main__":
    cli()
