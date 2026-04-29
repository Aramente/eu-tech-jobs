# Architecture

> The full plan lives at [Aramente vault → docs/superpowers/plans/2026-04-29-eu-tech-jobs-plan.md]; this file is the public-facing summary.

## Pipeline shape (v0)

```
companies/**/*.yaml  →  pipeline.seed.load_companies()  →  list[Company]
                                    │
                                    ▼
                  pipeline.orchestrator.run_pipeline()
                                    │
                       (asyncio gather, semaphore=10)
                                    │
                                    ▼
              ┌──────────────────────────────────┐
              │  pipeline/extractors/greenhouse  │   (v1 adds Lever, Ashby)
              │  → Job pydantic model            │
              └──────────────────────────────────┘
                                    │
                                    ▼
                pipeline.snapshot.writer.write_snapshot()
                  data/snapshots/YYYY-MM-DD/jobs.parquet
                  data/snapshots/YYYY-MM-DD/companies.parquet
                  data/snapshots/YYYY-MM-DD/metadata.json
                  data/latest/* (overwritten pointer)
                                    │
                                    ▼
            site/scripts/parquet-to-json.mjs (prebuild hook)
                  src/data/jobs.json
                                    │
                                    ▼
                       site/  (Astro static)  →  GitHub Pages
```

## File layout

| Path | Purpose |
|---|---|
| `pipeline/models.py` | Pydantic `Company`, `Job`, `Snapshot`, `Diff`, `SalaryBand`, `PipelineMetadata`. Single source of truth for the schema. |
| `pipeline/seed.py` | Load and validate `companies/**/*.yaml`. Slug derives from filename. |
| `pipeline/extractors/` | One module per ATS. Each exposes `fetch_jobs(handle, *, company_slug, client) -> list[Job]`. v0: Greenhouse only. |
| `pipeline/snapshot/writer.py` | Parquet writer (snappy). Writes `data/snapshots/YYYY-MM-DD/` and updates `data/latest/`. |
| `pipeline/orchestrator.py` | The `run_pipeline()` coroutine — fans out across companies, isolates errors, returns a `Snapshot`. |
| `pipeline/cli.py` | Click entrypoint: `pipeline run`, `pipeline seed validate`, `pipeline seed list`. |
| `companies/<category>/*.yaml` | Curated company seed. PR-friendly. |
| `data/` | Daily snapshot artifacts (committed in v0, pushed to HF Hub from v1). |
| `site/` | Astro 5 static site. `npm run build` runs the parquet→JSON prebuild then Astro. |
| `.github/workflows/daily.yml` | Daily cron (07:00 CET). Runs the pipeline + commits `data/` back. |
| `.github/workflows/site-deploy.yml` | Builds + deploys the Astro site to GitHub Pages on `data/` or `site/` changes. |
| `.github/workflows/tests.yml` | Pytest + ruff on every push / PR. |

## Schema stability

The `Job` and `Company` Pydantic models are the public contract for the HF Dataset
and the static site. New fields are always optional. Field renames or removals
require a major version bump documented in CHANGELOG.

## Roadmap

- **v0** (this) — 50 hand-picked companies on Greenhouse, manual run, single-page site
- **v1** — 500 companies, Lever + Ashby, daily cron, RSS, HF Dataset, per-job pages
- **v2** — 2,000 companies, more ATSes, career-page Playwright fallback, Mistral LLM tagging, ntfy alerts, Pagefind search
- **v3** — 5,000 companies, EU aggregators (WTTJ, JustJoin.it, RemoteOK, WeWorkRemotely), trend analytics

See the full plan in the project tracker.
