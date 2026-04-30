"""Tests for the EU-only location filter."""

from __future__ import annotations

from pipeline.filters import is_us_only_location, keep_job, split_jobs
from pipeline.models import Job, utcnow


def _job(location: str = "", remote_policy: str | None = None) -> Job:
    return Job(
        id="x",
        company_slug="x",
        title="Engineer",
        url="https://x.com/job",
        location=location,
        remote_policy=remote_policy,
        scraped_at=utcnow(),
        source="greenhouse",
    )


# is_us_only_location ------------------------------------------------

def test_explicit_us_city_drops():
    assert is_us_only_location("San Francisco, CA") is True
    assert is_us_only_location("New York, NY") is True
    assert is_us_only_location("Boston, MA") is True
    assert is_us_only_location("Austin, TX") is True
    assert is_us_only_location("Seattle, Washington, United States") is True


def test_us_country_string_drops():
    assert is_us_only_location("United States") is True
    assert is_us_only_location("United States - Remote") is True
    assert is_us_only_location("USA") is True
    assert is_us_only_location("U.S.A.") is True


def test_canada_drops():
    assert is_us_only_location("Toronto, Ontario, Canada") is True
    assert is_us_only_location("Vancouver, BC") is True


def test_eu_locations_keep():
    assert is_us_only_location("Paris, France") is False
    assert is_us_only_location("London, UK") is False
    assert is_us_only_location("Berlin") is False
    assert is_us_only_location("Remote — Europe") is False


def test_us_with_eu_signal_keeps():
    # Companies that list both — keep, the EU office is reachable.
    assert is_us_only_location("San Francisco, CA / Berlin, DE") is False
    assert is_us_only_location("New York or London") is False
    assert is_us_only_location("Remote — Worldwide") is False


def test_empty_keeps():
    assert is_us_only_location("") is False
    assert is_us_only_location(None) is False
    assert is_us_only_location("   ") is False


def test_non_us_non_eu_keeps():
    # Ambiguous (e.g. Singapore, Tokyo) — keep, no clear US signal.
    assert is_us_only_location("Singapore") is False
    assert is_us_only_location("Tokyo") is False
    assert is_us_only_location("Remote") is False


def test_state_abbrev_alone_with_comma():
    # ", CA" pattern — must be preceded by comma to avoid false hits
    # like "we work in CO" or words containing those letters.
    assert is_us_only_location("Mountain View, CA") is True
    # Just letters in flowing text shouldn't match
    assert is_us_only_location("Remote — flexible hours") is False


# keep_job -----------------------------------------------------------

def test_remote_global_keeps_despite_us():
    j = _job(location="San Francisco, CA", remote_policy="remote-global")
    assert keep_job(j) is True


def test_remote_eu_keeps_despite_us():
    j = _job(location="New York, NY", remote_policy="remote-eu")
    assert keep_job(j) is True


def test_us_with_no_remote_tag_drops():
    j = _job(location="San Francisco, CA")
    assert keep_job(j) is False


def test_eu_keeps():
    j = _job(location="Paris")
    assert keep_job(j) is True


def test_split_jobs():
    jobs = [
        _job(location="Paris"),
        _job(location="San Francisco, CA"),
        _job(location="New York, NY", remote_policy="remote-global"),
        _job(location=""),
    ]
    kept, dropped = split_jobs(jobs)
    assert len(kept) == 3
    assert len(dropped) == 1
    assert dropped[0].location == "San Francisco, CA"
