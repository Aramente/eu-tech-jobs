"""For every company with `career_url:` and no `ats:` block, detect
whether the URL is actually a known ATS (Greenhouse/Lever/Ashby/Workable/
SmartRecruiters/Recruitee/Personio/Workday) and promote to a real `ats:`
block. This swaps an LLM call ($0.001/day) for a free structured ATS API,
permanently per company.

Usage:
    python scripts/promote-career-urls.py             # dry-run
    python scripts/promote-career-urls.py --commit    # write changes
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.parse
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def detect_ats(url: str) -> tuple[str, str] | None:
    """Map a careers URL to (provider, handle) when it's a known ATS."""
    p = urllib.parse.urlparse(url)
    host = p.hostname or ""
    path = p.path or ""

    # Greenhouse: boards.greenhouse.io/{handle} or job-boards.greenhouse.io/{handle}
    if "greenhouse.io" in host:
        parts = [x for x in path.split("/") if x]
        if parts:
            return "greenhouse", parts[0]
    # Greenhouse via boards.{handle}.greenhouse.io is rare
    # Lever: jobs.lever.co/{handle}
    if host == "jobs.lever.co":
        parts = [x for x in path.split("/") if x]
        if parts:
            return "lever", parts[0]
    # Ashby: jobs.ashbyhq.com/{handle} or {handle}.ashbyhq.com
    if "ashbyhq.com" in host:
        if host.endswith(".ashbyhq.com") and host != "jobs.ashbyhq.com":
            sub = host.replace(".ashbyhq.com", "")
            return "ashby", sub
        parts = [x for x in path.split("/") if x]
        if parts:
            return "ashby", parts[0]
    # Workable: apply.workable.com/{handle} or {handle}.workable.com
    if "workable.com" in host:
        if host.endswith(".workable.com") and host != "apply.workable.com":
            sub = host.replace(".workable.com", "")
            return "workable", sub
        parts = [x for x in path.split("/") if x]
        if parts:
            return "workable", parts[0]
    # SmartRecruiters: jobs.smartrecruiters.com/{handle} or careers.smartrecruiters.com
    if "smartrecruiters.com" in host:
        parts = [x for x in path.split("/") if x]
        if parts:
            return "smartrecruiters", parts[0]
    # Recruitee: {handle}.recruitee.com
    if host.endswith(".recruitee.com"):
        sub = host.replace(".recruitee.com", "")
        return "recruitee", sub
    # Personio: {handle}.jobs.personio.com or {handle}.jobs.personio.de
    if host.endswith(".jobs.personio.com") or host.endswith(".jobs.personio.de"):
        sub = re.sub(r"\.jobs\.personio\.(com|de)$", "", host)
        return "personio", sub
    # Workday CXS: {tenant}.{cluster}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
    if "myworkdayjobs.com" in host:
        # If the URL already includes /wday/cxs/.../jobs, keep it as-is.
        if "/wday/cxs/" in path and path.endswith("/jobs"):
            return "workday", url
        # Otherwise it's the human-facing path — hard to convert without
        # site-name knowledge. Leave alone.
        return None
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()

    promoted = 0
    skipped = 0
    for path in (ROOT / "companies").rglob("*.yaml"):
        if "_drafts" in path.parts:
            continue
        data = yaml.safe_load(path.read_text())
        if not isinstance(data, dict):
            continue
        if data.get("ats"):  # already has an ATS block
            continue
        career_url = data.get("career_url")
        if not career_url:
            continue
        detection = detect_ats(career_url)
        if not detection:
            skipped += 1
            continue
        provider, handle = detection
        data["ats"] = {"provider": provider, "handle": handle}
        # Drop career_url since ats fully replaces it for extraction.
        data.pop("career_url", None)
        if args.commit:
            path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
        promoted += 1
        rel = path.relative_to(ROOT)
        print(f"  → {provider}:{handle:30s}  {rel}")

    print()
    print(f"Promoted: {promoted}")
    print(f"Stayed custom_page: {skipped}")
    if not args.commit:
        print("(dry-run — pass --commit to apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
