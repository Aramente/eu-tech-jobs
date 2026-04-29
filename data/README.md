---
license: cc-by-4.0
language:
  - en
size_categories:
  - 10K<n<100K
task_categories:
  - tabular-classification
  - text-classification
tags:
  - jobs
  - europe
  - tech
  - ai
  - open-data
  - hiring
pretty_name: EU Tech Jobs
---

# eu-tech-jobs

Daily-updated open-data feed of jobs from EU AI/tech and remote-EU companies.

- **Source repo:** https://github.com/Aramente/eu-tech-jobs
- **Live site:** https://aramente.github.io/eu-tech-jobs/
- **License:** CC BY 4.0 (data) + MIT (pipeline code)

## What's in here

| Path | Contents |
|---|---|
| `latest/jobs.parquet` | Most recent snapshot, all active jobs |
| `latest/companies.parquet` | Curated company list with categories + ATS handles |
| `latest/metadata.json` | Pipeline run metadata (per-extractor health, durations) |
| `snapshots/YYYY-MM-DD/` | Historical snapshot per date |
| `diffs/YYYY-MM-DD-diff.jsonl` | Per-day diff: new / removed / changed jobs |
| `feed.xml` | RSS 2.0 feed of new jobs |

## Schema (jobs.parquet)

| Column | Type | Notes |
|---|---|---|
| id | string | sha256(slug + url)[:16] — stable across days |
| company_slug | string | matches a row in companies.parquet |
| title | string | |
| url | string | canonical apply URL |
| location | string | as reported by the ATS |
| countries | list[string] | ISO 3166-1 alpha-2, normalized |
| remote_policy | string | onsite / hybrid / remote / remote-eu / remote-global |
| seniority | string | intern / junior / mid / senior / staff / principal / exec |
| role_family | string | engineering / ml-ai / data / product / design / sales / ops / ... |
| salary_min, salary_max | float | when disclosed |
| salary_currency, salary_period | string | ISO 4217; year/month/day/hour |
| visa_sponsorship | bool | when disclosed |
| stack | list[string] | extracted tech keywords |
| posted_at | timestamp | as reported |
| scraped_at | timestamp | UTC, second-precision |
| description_md | string | sanitized markdown |
| source | string | extractor name (greenhouse, lever, ashby, ...) |

## Quick query

```python
import pandas as pd

df = pd.read_parquet(
    "https://huggingface.co/datasets/Aramente/eu-tech-jobs/resolve/main/latest/jobs.parquet"
)
df[df["location"].str.contains("Paris", case=False, na=False)].head()
```

```sql
-- DuckDB
SELECT company_slug, count(*) AS jobs
FROM read_parquet('https://huggingface.co/datasets/Aramente/eu-tech-jobs/resolve/main/latest/jobs.parquet')
GROUP BY 1 ORDER BY 2 DESC LIMIT 10;
```

## Pipeline

The data is regenerated daily by a GitHub Actions cron (07:00 CET) that fetches
public ATS APIs (Greenhouse, Lever, Ashby, Workable, Recruitee, Personio,
SmartRecruiters) and EU job aggregators. Companies are curated as YAML files in
the source repo; PRs welcome.

## What we explicitly do NOT do

- Scrape LinkedIn, Indeed, or Glassdoor
- Extract personal contact information from postings
- Re-publish under a more restrictive license

## Removal

If your company appears here and you would prefer it didn't, open an issue on
the source repo or email kevin.duchier@gmail.com — takedown within 7 days.
