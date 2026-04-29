"""Tests for the ntfy alert publisher."""

from __future__ import annotations

from datetime import date

from pipeline.models import Diff, Job, utcnow
from pipeline.publish.alerts import _ascii_safe, render_summary


def _job(slug: str = "x", title: str = "Eng", url_suffix: str = "1"):
    return Job(
        id=f"id-{url_suffix}",
        company_slug=slug,
        title=title,
        url=f"https://x.com/{url_suffix}",
        scraped_at=utcnow(),
        source="greenhouse",
    )


def test_summary_with_no_diff():
    diff = Diff(diff_date=date(2026, 4, 29))
    out = render_summary(diff)
    assert "+0 new" in out


def test_summary_top_companies():
    diff = Diff(
        diff_date=date(2026, 4, 29),
        new_jobs=[_job("a", url_suffix=str(i)) for i in range(5)]
        + [_job("b", url_suffix=f"b{i}") for i in range(2)],
    )
    out = render_summary(diff)
    assert "+7 new" in out
    assert "a(5)" in out
    assert "b(2)" in out


def test_ascii_safe_strips_em_dash():
    assert _ascii_safe("Bored CV — new signup") == "Bored CV ? new signup"
    # ascii_safe must not crash on emoji (one replacement char per code point)
    assert "launched" in _ascii_safe("🚀 launched")
    # Round trip is safe ASCII
    assert _ascii_safe("plain ascii").isascii()
