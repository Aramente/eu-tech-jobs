"""Generate an RSS 2.0 feed of newly-posted jobs from the latest diff."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from pipeline.models import Diff

SITE_URL = "https://aramente.github.io/eu-tech-jobs/"
FEED_TITLE = "eu-tech-jobs — new EU AI/tech jobs (daily)"
FEED_DESC = (
    "New jobs added to the eu-tech-jobs daily snapshot. Open-data; CC BY 4.0."
)
MAX_ITEMS = 50


def build_rss(diff: Diff, generated_at: datetime | None = None) -> str:
    """Render an RSS 2.0 feed string from a Diff."""
    generated_at = generated_at or datetime.now(UTC)
    rss = ET.Element("rss", attrib={"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = FEED_TITLE
    ET.SubElement(channel, "link").text = SITE_URL
    ET.SubElement(channel, "description").text = FEED_DESC
    ET.SubElement(channel, "lastBuildDate").text = _rfc822(generated_at)
    ET.SubElement(channel, "language").text = "en"

    # Newest jobs first; cap at MAX_ITEMS to keep feed lightweight.
    items = sorted(
        diff.new_jobs,
        key=lambda j: j.posted_at or j.scraped_at,
        reverse=True,
    )[:MAX_ITEMS]
    for j in items:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = f"{j.title} — {j.company_slug}"
        ET.SubElement(item, "link").text = j.url
        ET.SubElement(item, "guid", attrib={"isPermaLink": "false"}).text = j.id
        when = j.posted_at or j.scraped_at
        ET.SubElement(item, "pubDate").text = _rfc822(when)
        location = j.location or "—"
        ET.SubElement(item, "description").text = (
            f"<b>{j.company_slug}</b> · {location}\n\n{j.description_md[:500]}"
        )

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        rss, encoding="unicode"
    )


def write_rss(diff: Diff, output_dir: Path) -> Path:
    """Write `data/feed.xml` (and overwrite each day)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "feed.xml"
    path.write_text(build_rss(diff))
    return path


def _rfc822(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.strftime("%a, %d %b %Y %H:%M:%S %z")
