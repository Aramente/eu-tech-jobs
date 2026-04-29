# Contributing

Thanks for helping cover EU tech / AI hiring. Most contributions are simple:
adding a company, fixing a broken extractor, or adding a new ATS.

## Add a company (the most common PR)

Drop one YAML file in `companies/<category>/<slug>.yaml`:

```yaml
name: Example Co
country: FR             # ISO 3166-1 alpha-2
categories: [ai, oss]   # one or more of: ai, tech, oss, remote-eu
ats:
  provider: greenhouse  # greenhouse | lever | ashby | workable | recruitee | personio | smartrecruiters
  handle: example       # the slug from their public board URL
career_url: https://example.com/jobs   # optional fallback
github_org: example-org                # optional
funding_stage: series-b                # optional
size_bucket: 51-200                    # optional
notes: "Open generative video models"  # optional, ≤200 chars
```

The filename stem is the slug. **Do not** declare a `slug` field inside the
YAML — it is derived automatically.

To find the right ATS handle, open the company's careers page and look at the
URL of the first job listing:

| URL pattern | Provider | Handle |
|---|---|---|
| `boards.greenhouse.io/HANDLE` | `greenhouse` | `HANDLE` |
| `jobs.lever.co/HANDLE` | `lever` | `HANDLE` |
| `jobs.ashbyhq.com/HANDLE` | `ashby` | `HANDLE` |
| `apply.workable.com/HANDLE` | `workable` | `HANDLE` |
| `HANDLE.recruitee.com` | `recruitee` | `HANDLE` |
| `HANDLE.jobs.personio.com` | `personio` | `HANDLE` |
| `careers.smartrecruiters.com/HANDLE` | `smartrecruiters` | `HANDLE` |

You can sanity-check Greenhouse handles by visiting:

```
https://boards-api.greenhouse.io/v1/boards/<handle>/jobs?content=false
```

If it returns JSON with a `jobs` array, the handle works.

## Add a new ATS extractor

1. Create `pipeline/extractors/<name>.py` exposing
   `async def fetch_jobs(handle, *, company_slug, client)` returning `list[Job]`.
2. Register it in `pipeline/extractors/__init__.py` under the matching provider key.
3. Drop a real-response fixture in `tests/extractors/fixtures/<name>_<example>.json`.
4. Write contract tests in `tests/extractors/test_<name>.py` mirroring
   `test_greenhouse.py` (happy path, 404, 5xx, fixture round-trip).

## Fix a broken extractor

Check the extractor health metadata at `data/latest/metadata.json`. Failed
extractors carry an `error` field. Update the parser, refresh the fixture, and
the contract test should catch the regression next time.

## Code style

- `uv run ruff check .` must pass
- `uv run pytest` must pass
- Keep functions small; prefer explicit naming over comments.

## What we don't accept

- LinkedIn / Indeed / Glassdoor scrapers — legal exposure
- Personal-data extraction beyond what's already in public job postings
- Schema-breaking changes without a CHANGELOG bump
