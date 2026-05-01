"""Unit tests for the Workday extractor parser."""

from __future__ import annotations

from pipeline.extractors.workday import (
    _derive_tenant_base,
    _job_url,
    parse_jobs,
)

NVIDIA_API = "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs"
NVIDIA_BASE = "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"


def test_derive_tenant_base_strips_wday_path():
    assert _derive_tenant_base(NVIDIA_API) == NVIDIA_BASE


def test_derive_tenant_base_handles_unknown_shape():
    assert _derive_tenant_base("https://x.com/abc") == "https://x.com"


def test_job_url_prefixes_relative_path():
    url = _job_url(NVIDIA_BASE, "/job/UK-London/Senior-Engineer_JR1")
    assert url == f"{NVIDIA_BASE}/job/UK-London/Senior-Engineer_JR1"


def test_job_url_passthrough_absolute():
    abs_ = "https://other.example/job/123"
    assert _job_url(NVIDIA_BASE, abs_) == abs_


def test_parse_jobs_basic():
    payload = {
        "total": 2,
        "jobPostings": [
            {
                "title": "Senior Engineer",
                "externalPath": "/job/UK-London/Senior-Engineer_JR1",
                "locationsText": "UK, London",
                "postedOn": "Posted Today",
                "bulletFields": ["JR1"],
            },
            {
                "title": "Talent Acquisition Partner",
                "externalPath": "/job/France-Paris/TA_JR2",
                "locationsText": "France, Paris",
                "postedOn": "Posted 2 Days Ago",
                "bulletFields": ["JR2"],
            },
        ],
    }
    jobs = parse_jobs(payload, "nvidia-workday", api_url=NVIDIA_API)
    assert len(jobs) == 2
    assert jobs[0].title == "Senior Engineer"
    assert jobs[0].url.startswith(NVIDIA_BASE + "/job/UK-London")
    assert jobs[0].location == "UK, London"
    assert jobs[1].title == "Talent Acquisition Partner"


def test_parse_jobs_skips_missing_title_or_path():
    payload = {
        "jobPostings": [
            {"title": "", "externalPath": "/job/x"},
            {"title": "Eng", "externalPath": ""},
            {"title": "Eng", "externalPath": "/job/ok"},
        ]
    }
    jobs = parse_jobs(payload, "x", api_url=NVIDIA_API)
    assert len(jobs) == 1
    assert jobs[0].title == "Eng"


def test_parse_jobs_handles_empty_payload():
    assert parse_jobs({}, "x", api_url=NVIDIA_API) == []
    assert parse_jobs({"jobPostings": None}, "x", api_url=NVIDIA_API) == []
