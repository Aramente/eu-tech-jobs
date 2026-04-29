# ai-startups

> Daily-updated open-data jobboard covering the EU AI / tech / OSS ecosystem.

[![Daily pipeline](https://github.com/Aramente/ai-startups/actions/workflows/daily.yml/badge.svg)](https://github.com/Aramente/ai-startups/actions/workflows/daily.yml)
[![Tests](https://github.com/Aramente/ai-startups/actions/workflows/tests.yml/badge.svg)](https://github.com/Aramente/ai-startups/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/Code-MIT-blue.svg)](LICENSE)
[![Data License: CC BY 4.0](https://img.shields.io/badge/Data-CC%20BY%204.0-lightgrey.svg)](DATA_LICENSE)

- **Live site:** https://aramente.github.io/ai-startups/
- **Dataset:** https://huggingface.co/datasets/Aramente/eu-tech-jobs *(published from v1)*

## What this is

A daily, open-data feed of jobs from EU-headquartered AI/ML/tech startups, plus
global tech companies that hire remote in Europe, plus open-source-first
companies hiring anywhere in the EU.

- ATS APIs (Greenhouse, Lever, Ashby, Workable, Recruitee, Personio, SmartRecruiters)
- EU job aggregators (Welcome to the Jungle, JustJoin.it, RemoteOK, WeWorkRemotely)
- Career-page scraping fallback for the long tail
- Daily diff → RSS feed → ntfy alert
- Per-job LLM tagging via Mistral (seniority, role, remote policy, stack, salary)

We **do not** scrape LinkedIn / Indeed / Glassdoor.

## Status

- [x] **v0** — hello world, ~50 hand-picked AI companies on Greenhouse, manual run
- [ ] **v1** — public alpha, 500 companies, daily cron, RSS
- [ ] **v2** — public beta, 2,000 companies, scraping + LLM tagging + alerts
- [ ] **v3** — full coverage, ~5,000 companies, EU aggregators, analytics

## Add a company in 30 seconds

Drop a YAML file in `companies/<category>/<slug>.yaml`:

```yaml
name: Hugging Face
country: FR
categories: [ai, oss]
ats:
  provider: greenhouse  # greenhouse | lever | ashby | workable | recruitee | personio | smartrecruiters
  handle: huggingface
career_url: https://huggingface.co/jobs
github_org: huggingface
funding_stage: series-d
size_bucket: 201-500
```

Open a PR — the daily pipeline picks it up tomorrow morning.

## Local development

```bash
uv sync --all-extras
uv run pipeline run --companies-glob "companies/ai/*.yaml" --output-dir data/
uv run pytest
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the pipeline shape and
[CONTRIBUTING.md](CONTRIBUTING.md) for how to add a new ATS extractor or fix a
broken one.

## Removal requests

If your company appears here and you would prefer it didn't, open an issue or
email kevin.duchier@gmail.com — we honor takedown requests within 7 days.

## License

- **Code:** MIT — see [LICENSE](LICENSE)
- **Data:** CC BY 4.0 — see [DATA_LICENSE](DATA_LICENSE)
