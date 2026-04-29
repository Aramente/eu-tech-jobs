"""Tests for the RSS feed builder."""

from __future__ import annotations

from datetime import date
from xml.etree import ElementTree as ET

from pipeline.models import Diff, Job, utcnow
from pipeline.publish.rss import build_rss


def _job(i: int):
    return Job(
        id=f"id{i:02d}",
        company_slug="x",
        title=f"Engineer {i}",
        url=f"https://example.com/{i}",
        location="Paris",
        scraped_at=utcnow(),
        source="greenhouse",
    )


def test_rss_validates():
    diff = Diff(diff_date=date(2026, 4, 29), new_jobs=[_job(1), _job(2)])
    xml = build_rss(diff)
    tree = ET.fromstring(xml)
    assert tree.tag == "rss"
    items = tree.findall("./channel/item")
    assert len(items) == 2


def test_empty_diff_still_builds():
    diff = Diff(diff_date=date(2026, 4, 29))
    xml = build_rss(diff)
    tree = ET.fromstring(xml)
    items = tree.findall("./channel/item")
    assert len(items) == 0


def test_caps_at_max_items():
    jobs = [_job(i) for i in range(80)]
    diff = Diff(diff_date=date(2026, 4, 29), new_jobs=jobs)
    xml = build_rss(diff)
    tree = ET.fromstring(xml)
    assert len(tree.findall("./channel/item")) == 50
