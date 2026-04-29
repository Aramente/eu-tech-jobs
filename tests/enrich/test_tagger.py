"""Tests for the Mistral tagger's pure functions."""

from __future__ import annotations

from pipeline.enrich.tagger import (
    _VALID_SENIORITY,
    build_prompt,
    normalize_response,
    strip_boilerplate,
)
from pipeline.models import Job, utcnow


def _job(desc=""):
    return Job(
        id="x",
        company_slug="x",
        title="Senior Engineer",
        url="https://x.com",
        scraped_at=utcnow(),
        source="greenhouse",
        description_md=desc,
    )


def test_strip_boilerplate_removes_about_us():
    desc = """## What you'll do
Build cool stuff.

## About us
We are a great company that values diversity.
"""
    out = strip_boilerplate(desc)
    assert "great company" not in out
    assert "Build cool stuff" in out


def test_strip_boilerplate_handles_empty():
    assert strip_boilerplate("") == ""


def test_grounding_drops_unsupported_stack():
    raw = {"stack": ["Python", "Java"], "languages": []}
    source = "We use Python at scale."
    norm = normalize_response(raw, source)
    assert "Python" in norm["stack"]
    assert "Java" not in norm["stack"]


def test_grounding_keeps_only_in_source_languages():
    raw = {"languages": ["en", "fr"]}
    source = "English required, French nice-to-have."
    norm = normalize_response(raw, source)
    # case-insensitive substring match: "en" appears in "English" and "fr" in "French"
    assert "en" in norm["languages"]
    assert "fr" in norm["languages"]


def test_invalid_seniority_dropped():
    raw = {"seniority": "demigod"}
    norm = normalize_response(raw, "x")
    assert norm["seniority"] is None


def test_valid_seniority_kept():
    raw = {"seniority": "senior"}
    norm = normalize_response(raw, "x")
    assert norm["seniority"] == "senior"
    assert norm["seniority"] in _VALID_SENIORITY


def test_invalid_role_family_dropped():
    raw = {"role_family": "warlock"}
    norm = normalize_response(raw, "x")
    assert norm["role_family"] is None


def test_visa_only_bool_kept():
    assert normalize_response({"visa_sponsorship": "yes"}, "x")["visa_sponsorship"] is None
    assert normalize_response({"visa_sponsorship": True}, "x")["visa_sponsorship"] is True


def test_prompt_includes_title_and_description():
    j = _job("we want python")
    prompt = build_prompt(j, "we want python")
    assert "Senior Engineer" in prompt
    assert "we want python" in prompt
