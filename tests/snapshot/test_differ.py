"""Tests for the diff engine."""

from __future__ import annotations

from datetime import date

from pipeline.models import Job, utcnow
from pipeline.snapshot.differ import diff_snapshots


def _job(jid: str, title: str = "Eng", url: str | None = None, location: str = "Paris"):
    url = url or f"https://example.com/{jid}"
    return Job(
        id=jid,
        company_slug="x",
        title=title,
        url=url,
        location=location,
        scraped_at=utcnow(),
        source="greenhouse",
    )


D = date(2026, 4, 29)


def test_empty_inputs_empty_diff():
    d = diff_snapshots([], [], D)
    assert d.is_empty


def test_all_new_when_yesterday_empty():
    today = [_job("a"), _job("b")]
    d = diff_snapshots(today, [], D)
    assert len(d.new_jobs) == 2
    assert d.removed_job_ids == []
    assert d.changed == []


def test_removed_when_missing_today():
    yesterday = [_job("a"), _job("b")]
    today = [_job("a")]
    d = diff_snapshots(today, yesterday, D)
    assert d.new_jobs == []
    assert d.removed_job_ids == ["b"]


def test_changed_title():
    yesterday = [_job("a", title="Old")]
    today = [_job("a", title="New")]
    d = diff_snapshots(today, yesterday, D)
    assert len(d.changed) == 1
    assert d.changed[0].field == "title"
    assert d.changed[0].old == "Old"
    assert d.changed[0].new == "New"


def test_description_change_ignored():
    a_yesterday = _job("a")
    a_today = _job("a")
    a_today.description_md = "totally rewritten"
    d = diff_snapshots([a_today], [a_yesterday], D)
    assert d.is_empty


def test_location_change_detected():
    yesterday = [_job("a", location="Paris")]
    today = [_job("a", location="London")]
    d = diff_snapshots(today, yesterday, D)
    assert any(c.field == "location" for c in d.changed)
