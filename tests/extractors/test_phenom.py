"""Unit tests for the Phenom People (Jibe) extractor parser."""

from __future__ import annotations

from pipeline.extractors.phenom import _public_url, parse_jobs

API = "https://careers.amd.com/api/jobs"


def test_public_url_root():
    assert _public_url(API, "12345") == "https://careers.amd.com/jobs/12345"


def test_parse_jobs_basic():
    payload = {
        "totalCount": 2,
        "jobs": [
            {
                "data": {
                    "slug": "84572",
                    "title": "Senior GPU Software Performance Engineer",
                    "city": "Munich",
                    "country": "Germany",
                    "description": "<p>Build kernels.</p>",
                }
            },
            {
                "data": {
                    "slug": "84599",
                    "title": "Talent Acquisition Partner — EU",
                    "country": "France",
                    "description": "",
                }
            },
        ],
    }
    jobs = parse_jobs(payload, "amd", api_url=API)
    assert len(jobs) == 2
    assert jobs[0].url.endswith("/jobs/84572")
    assert jobs[0].location == "Munich, Germany"
    assert "Build kernels" in jobs[0].description_md
    assert jobs[1].location == "France"


def test_parse_jobs_skips_missing_fields():
    payload = {
        "jobs": [
            {"data": {"slug": "1", "title": ""}},
            {"data": {"slug": "", "title": "x"}},
            {"data": {"slug": "3", "title": "ok"}},
        ]
    }
    jobs = parse_jobs(payload, "x", api_url=API)
    assert len(jobs) == 1


def test_parse_jobs_handles_location_object():
    payload = {
        "jobs": [
            {
                "data": {
                    "slug": "1",
                    "title": "Eng",
                    "location": {"city": "Paris", "country": "France"},
                }
            },
        ]
    }
    jobs = parse_jobs(payload, "x", api_url=API)
    assert jobs[0].location == "Paris, France"


def test_parse_jobs_handles_empty():
    assert parse_jobs({}, "x", api_url=API) == []
    assert parse_jobs({"jobs": None}, "x", api_url=API) == []
