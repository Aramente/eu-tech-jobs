"""Custom-page extractor — fetches a careers URL, asks DeepSeek to
extract job postings as structured JSON.

This is the "moat" extractor for companies whose careers page doesn't
sit on one of the supported ATS providers (Greenhouse / Lever / Ashby /
Workable / SmartRecruiters / Recruitee / Personio). Lets us cover Apple,
Meta, NVIDIA, Adept, Magic Dev, Midjourney, etc — companies that run on
Workday, custom one-pagers, or proprietary systems.

Activation: a Company YAML with `career_url:` set and no `ats:` block
(or `ats.provider: custom_page`). The orchestrator routes those to here.

Cost: one DeepSeek `deepseek-chat` call per company per day. ~$0.001
per page after html → markdown stripping. ~$0.05/day for 50 companies.

Limitations (call out, don't hide):
- Static HTML only. Workday and other JS-rendered SPAs return shell
  HTML with no job content; the LLM dutifully returns []. Playwright-
  backed rendering would unlock those — separate sprint.
- The LLM occasionally hallucinates URLs. We post-validate every URL
  is HTTP(S) and from the same registrable domain as the source page.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from urllib.parse import urlparse

import httpx
from markdownify import markdownify
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from pipeline.extractors.base import (
    ExtractorNotFoundError,
    ExtractorTransientError,
)
from pipeline.models import Job, utcnow

logger = logging.getLogger(__name__)

NAME = "custom_page"
USER_AGENT = (
    "Mozilla/5.0 (compatible; ai-startups-bot/0.1; "
    "+https://github.com/Aramente/eu-tech-jobs)"
)
# Truncate the page text before sending to the LLM. Most careers pages
# fit in 30K chars after markdown conversion. Long ones (>50K) are
# usually JS-rendered shells where extra context wouldn't help anyway.
MAX_PAGE_CHARS = 32000
LLM_MODEL = "deepseek-chat"
DEEPSEEK_BASE = "https://api.deepseek.com/v1"

EXTRACTION_PROMPT = """You are extracting current job openings from a company's careers page.

Given the markdown content of the page below, return a JSON object with this exact shape:
{
  "jobs": [
    {
      "title": "Senior Backend Engineer",
      "location": "Paris, France",
      "url": "https://example.com/jobs/12345",
      "remote_policy": "remote-eu" | "remote-global" | "hybrid" | "onsite" | null
    }
  ]
}

Rules:
- Only include actual job postings, not "Join our talent community" generic CTAs.
- If a job's link is a relative path, prefix it with the page's base URL: {base_url}
- If you can't find any jobs (page is JS-rendered shell or generic landing), return {"jobs": []}.
- DO NOT invent jobs. DO NOT include jobs explicitly listed as "Closed" / "Filled" / past tense.
- Output JSON ONLY — no prose, no markdown fences."""


def _absolute_url(url: str, base_url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("//"):
        return "https:" + url
    parsed = urlparse(base_url)
    if url.startswith("/"):
        return f"{parsed.scheme}://{parsed.netloc}{url}"
    return f"{parsed.scheme}://{parsed.netloc}/{url}"


def _registrable_domain(url: str) -> str:
    host = urlparse(url).hostname or ""
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _looks_like_job_url(url: str, source_domain: str) -> bool:
    if not url or not url.startswith(("http://", "https://")):
        return False
    job_domain = _registrable_domain(url)
    # Allow same registrable domain OR known ATS-on-subdomain patterns.
    ats_subdomains = (
        "greenhouse.io",
        "lever.co",
        "ashbyhq.com",
        "workday.com",
        "myworkdayjobs.com",
        "workable.com",
        "smartrecruiters.com",
        "recruitee.com",
        "personio.com",
        "personio.de",
    )
    if job_domain == source_domain:
        return True
    if any(url.endswith(d) or f".{d}/" in url or f".{d}?" in url for d in ats_subdomains):
        return True
    if any(d in url for d in ats_subdomains):
        return True
    return False


def parse_jobs(payload: dict, company_slug: str, source_url: str) -> list[Job]:
    """Validate and normalise the LLM's structured output → Job[]."""
    raw_jobs = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(raw_jobs, list):
        return []
    source_domain = _registrable_domain(source_url)
    out: list[Job] = []
    now = utcnow()
    seen_urls: set[str] = set()
    for raw in raw_jobs:
        if not isinstance(raw, dict):
            continue
        title = (raw.get("title") or "").strip()
        url = (raw.get("url") or "").strip()
        location = (raw.get("location") or "").strip()
        remote = raw.get("remote_policy")
        if not title or not url:
            continue
        url = _absolute_url(url, source_url)
        # Reject hallucinated cross-domain links.
        if not _looks_like_job_url(url, source_domain):
            logger.debug(
                "Custom-page %s dropped suspicious url %r", company_slug, url
            )
            continue
        # Dedupe by url within a single page extraction.
        if url in seen_urls:
            continue
        seen_urls.add(url)
        if remote not in {"remote-eu", "remote-global", "remote", "hybrid", "onsite"}:
            remote = None
        out.append(
            Job(
                id=Job.make_id(company_slug, url),
                company_slug=company_slug,
                title=title,
                url=url,
                location=location,
                remote_policy=remote,
                posted_at=None,
                scraped_at=now,
                description_md="",
                source=NAME,
            )
        )
    return out


@retry(
    retry=retry_if_exception_type((httpx.TransportError, ExtractorTransientError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
async def _fetch_html(client: httpx.AsyncClient, url: str) -> str:
    resp = await client.get(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.7,fr;q=0.6",
        },
        timeout=30.0,
        follow_redirects=True,
    )
    if resp.status_code == 404:
        raise ExtractorNotFoundError(f"Custom page 404: {url}")
    if resp.status_code >= 500:
        raise ExtractorTransientError(f"Custom page {resp.status_code}: {url}")
    if resp.status_code >= 400:
        raise ExtractorTransientError(
            f"Custom page {resp.status_code}: {url}: {resp.text[:200]}"
        )
    return resp.text


def _html_to_text(html: str) -> str:
    """Strip script/style and convert to markdown for LLM consumption."""
    text = re.sub(r"<script\b[^<]*(?:(?!</script>)<[^<]*)*</script>", "", html, flags=re.I)
    text = re.sub(r"<style\b[^<]*(?:(?!</style>)<[^<]*)*</style>", "", text, flags=re.I)
    md = markdownify(text, heading_style="ATX")
    md = re.sub(r"\n{3,}", "\n\n", md).strip()
    return md[:MAX_PAGE_CHARS]


def _call_deepseek(page_md: str, source_url: str) -> dict:
    """Send the page to DeepSeek with structured-output JSON mode."""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise ExtractorTransientError("DEEPSEEK_API_KEY not set")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ExtractorTransientError("openai SDK not installed") from exc
    client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE)
    parsed_base = urlparse(source_url)
    base_url = f"{parsed_base.scheme}://{parsed_base.netloc}"
    prompt = EXTRACTION_PROMPT.replace("{base_url}", base_url)
    try:
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": page_md},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=4096,
        )
    except Exception as exc:
        raise ExtractorTransientError(f"DeepSeek call failed: {exc}") from exc
    content = resp.choices[0].message.content or "{}"
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        logger.warning("Custom-page extractor got non-JSON from LLM, dropping")
        return {"jobs": []}


# Inline stealth init script. Patches the headless-Chrome fingerprint
# so Cloudflare / DataDome / PerimeterX silent challenges don't fire.
# Source: distilled from puppeteer-extra-plugin-stealth + chromium tests.
_STEALTH_INIT = r"""
// Hide that we're WebDriver-controlled.
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
// Realistic plugin/mimeType arrays — empty = headless tell.
Object.defineProperty(navigator, 'plugins', {
  get: () => [
    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
    { name: 'Native Client', filename: 'internal-nacl-plugin' },
  ],
});
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en', 'fr'] });
// chrome.runtime presence is an anti-bot signal — fake the presence.
window.chrome = window.chrome || { runtime: {} };
// Permissions API — match Chrome's 'prompt' default for notifications.
const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
if (originalQuery) {
  window.navigator.permissions.query = (parameters) =>
    parameters.name === 'notifications'
      ? Promise.resolve({ state: Notification.permission })
      : originalQuery(parameters);
}
// WebGL vendor + renderer — headless reports SwiftShader, real Chrome reports the GPU.
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function (parameter) {
  if (parameter === 37445) return 'Intel Inc.';      // UNMASKED_VENDOR_WEBGL
  if (parameter === 37446) return 'Intel Iris OpenGL Engine'; // UNMASKED_RENDERER_WEBGL
  return getParameter.call(this, parameter);
};
"""


async def _render_with_playwright(url: str) -> str:
    """Headless render fallback for JS-only and Cloudflare-protected
    careers pages. Optional — requires the `browser` extra (playwright).
    Inlines stealth fingerprint patches via add_init_script — no
    additional Python dep needed.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.info("Playwright not installed — skipping JS render for %s", url)
        return ""

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
            try:
                ctx = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 "
                        "Safari/537.36"
                    ),
                    viewport={"width": 1440, "height": 900},
                    locale="en-US",
                    timezone_id="Europe/Paris",
                    extra_http_headers={
                        "Accept-Language": "en-US,en;q=0.9,fr;q=0.7",
                        "sec-ch-ua": '"Chromium";v="127", "Not?A_Brand";v="99"',
                        "sec-ch-ua-mobile": "?0",
                        "sec-ch-ua-platform": '"macOS"',
                    },
                )
                # Apply the stealth patches BEFORE any page script runs.
                await ctx.add_init_script(_STEALTH_INIT)
                page = await ctx.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                # Some Cloudflare challenges resolve in 1-3s of JS execution.
                # Give them time to settle before reading content.
                await page.wait_for_timeout(4500)
                content = await page.content()
            finally:
                await browser.close()
        return content
    except Exception as exc:
        logger.warning("Playwright render failed for %s: %s", url, exc)
        return ""


async def fetch_jobs(
    handle: str,
    *,
    company_slug: str,
    client: httpx.AsyncClient | None = None,
) -> list[Job]:
    """Fetch and LLM-extract jobs from an arbitrary careers URL.

    Two-pass: try static httpx first (fast, free). If the page text is
    too short (JS-only), or the static fetch hit a Cloudflare-style
    bot wall, fall back to Playwright headless render and LLM-extract
    from that. Playwright is opt-in via the `browser` extra and falls
    through gracefully when not installed.
    """
    owns = client is None
    client = client or httpx.AsyncClient()
    html = ""
    static_blocked = False
    try:
        try:
            html = await _fetch_html(client, handle)
        except ExtractorNotFoundError:
            return []
        except ExtractorTransientError as exc:
            # 403 from Cloudflare / bot mitigation, 401, etc — try Playwright.
            msg = str(exc)
            if " 403" in msg or " 401" in msg or "Just a moment" in msg or "challenge" in msg.lower():
                static_blocked = True
                logger.info(
                    "Custom-page %s static fetch blocked (%s) — trying Playwright",
                    company_slug,
                    msg[:80],
                )
            else:
                raise
    finally:
        if owns:
            await client.aclose()
    page_md = _html_to_text(html) if html else ""

    # JS-rendered detection OR static-blocked → headless render fallback.
    if static_blocked or not page_md or len(page_md) < 500:
        if not static_blocked:
            logger.info(
                "Custom-page %s returned %d chars of static text — trying Playwright",
                company_slug,
                len(page_md or ""),
            )
        rendered = await _render_with_playwright(handle)
        if rendered:
            page_md = _html_to_text(rendered)
        if not page_md or len(page_md) < 200:
            logger.info(
                "Custom-page %s still %d chars after render — giving up",
                company_slug,
                len(page_md or ""),
            )
            return []

    payload = _call_deepseek(page_md, handle)
    return parse_jobs(payload, company_slug, handle)
