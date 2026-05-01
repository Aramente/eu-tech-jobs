"""Discover Workday tenants by following the redirect chain from each
company's public careers landing page.

Pattern: {brand}.com/careers → ... → {tenant}.{cluster}.myworkdayjobs.com/{site}

For each hit, parse out (tenant, cluster, site), build the CXS API URL,
verify it returns > 0 jobs, and emit a YAML.

Usage:
    python scripts/discover-workday.py             # dry-run
    python scripts/discover-workday.py --commit    # write YAMLs to companies/tech/
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parents[1]
TECH_DIR = ROOT / "companies" / "tech"
AI_DIR = ROOT / "companies" / "ai"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0 Safari/537.36"
)

# Public careers URLs for known/likely Workday users. We follow redirects
# from these and detect myworkdayjobs.com landing.
CANDIDATES = [
    # Big Tech / SaaS
    ("cisco",        "Cisco",        "US", ["tech"], "https://jobs.cisco.com/"),
    ("intuit",       "Intuit",       "US", ["tech"], "https://jobs.intuit.com/"),
    ("atlassian",    "Atlassian",    "AU", ["tech"], "https://www.atlassian.com/careers"),
    ("block",        "Block",        "US", ["tech"], "https://block.xyz/careers"),
    ("servicenow",   "ServiceNow",   "US", ["tech"], "https://careers.servicenow.com/"),
    ("netapp",       "NetApp",       "US", ["tech"], "https://careers.netapp.com/"),
    ("vmware",       "VMware",       "US", ["tech"], "https://careers.vmware.com/main"),
    ("zendesk",      "Zendesk",      "US", ["tech"], "https://www.zendesk.com/jobs/"),
    ("box",          "Box",          "US", ["tech"], "https://www.box.com/about-us/careers"),
    ("twilio",       "Twilio",       "US", ["tech"], "https://www.twilio.com/en-us/company/jobs"),
    ("uber-careers", "Uber",         "US", ["tech"], "https://www.uber.com/global/en/careers/"),
    ("lyft",         "Lyft",         "US", ["tech"], "https://www.lyft.com/careers"),
    ("airbnb",       "Airbnb",       "US", ["tech"], "https://careers.airbnb.com/"),
    ("doordash",     "DoorDash",     "US", ["tech"], "https://careersatdoordash.com/"),
    ("instacart",    "Instacart",    "US", ["tech"], "https://careers.instacart.com/"),
    ("samsara",      "Samsara",      "US", ["tech"], "https://www.samsara.com/company/careers/"),
    ("snowflake-2",  "Snowflake (Workday)", "US", ["tech"], "https://careers.snowflake.com/us/en"),
    ("autodesk",     "Autodesk",     "US", ["tech"], "https://www.autodesk.com/careers"),

    # Finance / payments
    ("visa",         "Visa",         "US", ["tech"], "https://corporate.visa.com/en/jobs.html"),
    ("mastercard",   "Mastercard",   "US", ["tech"], "https://careers.mastercard.com/"),
    ("americanexpress", "American Express", "US", ["tech"], "https://aexp.eightfold.ai/careers"),
    ("jpmorgan",     "JPMorgan",     "US", ["tech"], "https://careers.jpmorgan.com/"),
    ("blackrock",    "BlackRock",    "US", ["tech"], "https://careers.blackrock.com/"),

    # Industrial / EU corp
    ("siemens",      "Siemens",      "DE", ["tech"], "https://jobs.siemens.com/careers"),
    ("bosch",        "Bosch",        "DE", ["tech"], "https://www.bosch.com/careers/"),
    ("bmw",          "BMW",          "DE", ["tech"], "https://www.bmwgroup.jobs/de/de.html"),
    ("vw",           "Volkswagen",   "DE", ["tech"], "https://www.volkswagen-group.com/en/jobs"),
    ("philips",      "Philips",      "NL", ["tech"], "https://www.careers.philips.com/global/en"),
    ("schneider",    "Schneider Electric", "FR", ["tech"], "https://www.se.com/ww/en/about-us/careers/"),
    ("loreal",       "L'Oréal",      "FR", ["tech"], "https://careers.loreal.com/en_US/jobs"),
    ("airbus",       "Airbus",       "FR", ["tech"], "https://www.airbus.com/en/careers"),
    ("safran",       "Safran",       "FR", ["tech"], "https://www.safran-group.com/careers"),
    ("nestle",       "Nestlé",       "CH", ["tech"], "https://www.nestle.com/jobs"),

    # Pharma / biotech
    ("merck",        "Merck",        "US", ["tech"], "https://jobs.merck.com/us/en"),
    ("pfizer",       "Pfizer",       "US", ["tech"], "https://www.pfizer.com/about/careers"),
    ("gsk",          "GSK",          "GB", ["tech"], "https://www.gsk.com/en-gb/careers/"),
    ("sanofi",       "Sanofi",       "FR", ["tech"], "https://www.sanofi.com/en/careers"),
    ("bayer",        "Bayer",        "DE", ["tech"], "https://career.bayer.com/en"),
    ("gilead",       "Gilead",       "US", ["tech"], "https://www.gileadcareers.com/"),
    ("roche",        "Roche",        "CH", ["tech"], "https://careers.roche.com/global/en/"),

    # AI / ML scaleups
    ("scale-ai",     "Scale AI",     "US", ["ai"], "https://scale.com/careers"),
    ("mongodb",      "MongoDB",      "US", ["tech"], "https://www.mongodb.com/careers"),
    ("elastic",      "Elastic",      "US", ["tech"], "https://www.elastic.co/about/careers"),
    ("hashicorp-2",  "HashiCorp (Workday?)", "US", ["tech"], "https://www.hashicorp.com/jobs"),
]

# Workday URL pattern in the wild:
#   https://{tenant}.{cluster}.myworkdayjobs.com/{lang/}{site}
# After redirect, the human URL also varies — sometimes it's
# /en-US/{site}, sometimes /{site}, sometimes /wday/cxs/.../jobs (rare).
WORKDAY_PAT = re.compile(
    r"https?://([a-z0-9-]+)\.(wd[0-9]+)\.myworkdayjobs\.com",
    re.IGNORECASE,
)

# In the rendered HTML, the SPA bootstraps with the API path embedded
# in a script tag. Match `cxs/{tenant}/{site}/jobs` references.
HTML_API_PAT = re.compile(
    r'cxs/([a-z0-9_-]+)/([A-Za-z0-9_-]+)/jobs', re.IGNORECASE
)


def _follow_redirects(url: str, max_hops: int = 7) -> tuple[str, str]:
    """Static-fetch redirect follow. Returns (final_url, body). Used for
    server-side redirects only — JS-driven redirects need _render."""
    for _ in range(max_hops):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
            )
            with urllib.request.urlopen(req, timeout=12) as r:
                final = r.geturl()
                body = r.read(80000).decode("utf-8", errors="replace")
                return final, body
        except urllib.error.HTTPError as e:
            if 300 <= e.code < 400 and "location" in e.headers:
                url = e.headers["location"]
                continue
            return url, ""
        except Exception:
            return url, ""
    return url, ""


def _render_with_playwright_sync(url: str, timeout: int = 25) -> tuple[str, str]:
    """Headless render. Follows JS-driven redirects (most modern careers SPAs
    that route to Workday do it client-side after auth/handshake JS runs).
    Returns (final_url, body). Empty strings on failure or when Playwright
    isn't installed.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "", ""
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            try:
                ctx = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 "
                        "Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 900},
                    locale="en-US",
                )
                page = ctx.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
                # Some careers shells delay the WD redirect 1-3s after first paint.
                page.wait_for_timeout(3000)
                final = page.url
                # Page content captures iframes too via outer HTML. We also
                # check window.__INITIAL_STATE__ etc. but content() is enough
                # for the regex match.
                body = page.content()
                browser.close()
                return final, body
            except Exception:
                browser.close()
                return "", ""
    except Exception:
        return "", ""


def _detect_workday(final_url: str, body: str) -> tuple[str, str, str] | None:
    """Return (tenant, cluster, site) if a Workday URL is detectable."""
    # 1. Final-URL match
    m = WORKDAY_PAT.search(final_url)
    tenant = cluster = None
    if m:
        tenant = m.group(1).lower()
        cluster = m.group(2).lower()
    else:
        # 2. Body match — sometimes the page is a generic landing that
        # lazy-loads the Workday iframe.
        m = WORKDAY_PAT.search(body)
        if m:
            tenant = m.group(1).lower()
            cluster = m.group(2).lower()
    if not tenant:
        return None

    # Find the site name. First try CXS reference in body.
    m = HTML_API_PAT.search(body)
    if m and m.group(1).lower() == tenant:
        return tenant, cluster, m.group(2)

    # Otherwise extract from the path of the final URL.
    parsed = urlparse(final_url)
    parts = [x for x in (parsed.path or "").split("/") if x]
    # Strip language prefixes like "en-US"
    if parts and re.match(r"^[a-z]{2}(-[A-Z]{2})?$", parts[0]):
        parts = parts[1:]
    site = parts[0] if parts else None
    if site:
        return tenant, cluster, site
    return None


def _verify_cxs(tenant: str, cluster: str, site: str) -> tuple[str, int] | None:
    url = f"https://{tenant}.{cluster}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
    body = json.dumps({"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""}).encode()
    try:
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
            total = int(data.get("total", 0))
            if total > 0:
                return url, total
    except Exception:
        pass
    return None


def _existing_slugs() -> set[str]:
    return {p.stem for p in (ROOT / "companies").rglob("*.yaml") if "_drafts" not in p.parts}


def _discover(candidate: tuple) -> tuple | None:
    slug, name, country, cats, careers_url = candidate
    # Pass 1: static fetch + redirect chain. Cheap.
    final, body = _follow_redirects(careers_url)
    detect = _detect_workday(final, body)
    # Pass 2: if static didn't yield Workday markers, render with Playwright.
    # Modern careers shells often JS-redirect to *.myworkdayjobs.com after
    # initial paint, which is invisible to httpx. ~5s/candidate.
    if not detect:
        rendered_final, rendered_body = _render_with_playwright_sync(careers_url)
        if rendered_final or rendered_body:
            detect = _detect_workday(rendered_final, rendered_body)
    if not detect:
        return None
    tenant, cluster, site = detect
    verify = _verify_cxs(tenant, cluster, site)
    if not verify:
        return None
    api_url, total = verify
    return slug, name, country, cats, api_url, total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()

    existing = _existing_slugs()
    print(f"Existing seeded slugs: {len(existing)}")
    print(f"Probing {len(CANDIDATES)} candidates via redirect chain…")

    # Sequential — Playwright sync_api can't share an event loop across
    # threads, so the threadpool would crash on the rendered fallback.
    # Static-only discovery is fast (~1s/candidate); Playwright fallback
    # adds ~5s only when needed.
    hits = []
    for i, c in enumerate(CANDIDATES, 1):
        print(f"  [{i:>2}/{len(CANDIDATES)}] {c[0]:18s} {c[4]}")
        r = _discover(c)
        if r:
            hits.append(r)
            slug, name, country, _, api_url, total = r
            print(f"    ✓ {total:>5} jobs  {api_url}")

    print(f"\nFound {len(hits)} new Workday tenants")
    if not args.commit:
        print("(dry-run — pass --commit to write YAMLs)")
        return 0

    written = 0
    for slug, name, country, cats, api_url, total in hits:
        if slug in existing:
            print(f"  ⊘ {slug} already seeded")
            continue
        target_dir = AI_DIR if "ai" in cats else TECH_DIR
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"{slug}.yaml"
        if path.exists():
            continue
        cats_full = list(cats) + (["remote-eu"] if "remote-eu" not in cats else [])
        path.write_text(yaml.safe_dump({
            "name": name,
            "country": country,
            "categories": cats_full,
            "ats": {"provider": "workday", "handle": api_url},
            "notes": f"Workday-hosted ({total} jobs at discovery)",
        }, sort_keys=False, allow_unicode=True))
        print(f"  + {path.relative_to(ROOT)}")
        written += 1
    print(f"\n+{written} YAMLs written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
