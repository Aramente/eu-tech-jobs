# Unreachable companies (and what would unlock each)

Audit from 2026-05-01 daily run. These companies are in the seed but
produced 0 jobs because none of our 4 extraction lanes (ATS APIs,
Workday CXS, custom_page LLM, aggregators) could pull from them.

## Solved

- **Cerebras** → moved from `custom_page` to `greenhouse:cerebrassystems`
  (93 jobs). The careers page was a marketing wrapper hiding a standard
  Greenhouse board; brute-handle probe found it.

## Still unreachable (and the cheap free path for each)

### AMD — `careers.amd.com`
Eightfold AI ATS. Public site is at `careers.amd.com/careers-home/jobs`,
returns 411KB HTML but the `/api/apply/v2/jobs` endpoint returns 404
without their tenant-specific `domain` and `pid` parameters.
- **Free fix**: scrape one page of the SPA with Playwright, extract the
  Eightfold params from `window.__INITIAL_STATE__` or similar, then
  hit the API directly. ~1hr of reverse engineering.
- **Faster alt**: just keep `career_url` set; the LLM extractor will
  process the rendered page once Playwright stealth bypasses Eightfold's
  bot detection.

### Microsoft Research — `jobs.careers.microsoft.com`
Microsoft has its own custom careers system. The API is
`gcsservices.careers.microsoft.com/search/api/v1/search` but that
hostname has SSL cert routing issues from some agents and likely
needs auth or a specific origin header.
- **Free fix**: Playwright on the search results page with EU filter
  pre-applied. Microsoft's JSON loads after first paint and is visible
  in the DOM after `networkidle`.
- **Caveat**: their per-job links are stable and the page text contains
  the title + location, so even the dumb LLM extraction should work
  once the page renders.

### Hippocratic AI — `hippocraticai.com/careers`
Cloudflare-protected. Static fetch returns the JS challenge HTML,
Playwright still gets blocked because the page detects headless
fingerprints.
- **Free fix**: Playwright with `playwright-stealth` plugin (~1
  additional Python dep). Bypasses Cloudflare's headless detection.
- Lower priority — small company, likely <10 jobs.

### Civitai — `jobs.civitai.com`
Returns 0 bytes (broken). Their main site `civitai.com/jobs` is also
404. They moved hosting at some point.
- **Free fix**: search GitHub for `civitai careers` to find their
  current host; OR remove from seed entirely until they republish.

### Jina AI — Personio account
`jina-ai.jobs.personio.com` redirects to `personio.de` then 429s.
Their Personio account was deactivated or never set up correctly.
- **Free fix**: check Jina's website footer for the actual current
  careers URL; might be on Greenhouse / Lever now.

### Adept — `adept.ai/careers`
Cloudflare bot wall. Same problem as Hippocratic.
- **Free fix**: same as Hippocratic — Playwright stealth.
- Note: Adept was acquired by Amazon in 2024; may not be hiring
  independently anymore.

### Midjourney — `midjourney.com/jobs`
Cloudflare bot wall.
- **Free fix**: same as above.

## Pattern

The remaining 7 fall into two buckets:

1. **Bot mitigation** (Hippocratic, Adept, Midjourney) — Playwright
   stealth handles all three with one library install.
2. **Custom ATS APIs** (AMD, MS Research) — each needs ~1hr of
   reverse-engineering against the live site to find the right
   request shape.

Combined: ~2hr of free engineering work to unlock all 7 (excluding
Civitai/Jina which need re-discovery of where their jobs live).
