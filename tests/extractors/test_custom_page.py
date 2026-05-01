"""Unit tests for the custom_page extractor's pure functions.

The LLM call itself is integration territory and gets exercised by the
daily pipeline in CI where DEEPSEEK_API_KEY is set.
"""

from __future__ import annotations

from pipeline.extractors.custom_page import (
    _absolute_url,
    _html_to_text,
    _looks_like_job_url,
    parse_jobs,
)


def test_absolute_url_passthrough():
    assert _absolute_url("https://x.com/jobs/1", "https://acme.com/careers") == "https://x.com/jobs/1"


def test_absolute_url_relative_path():
    assert (
        _absolute_url("/jobs/1", "https://acme.com/careers/")
        == "https://acme.com/jobs/1"
    )


def test_absolute_url_protocol_relative():
    assert _absolute_url("//cdn.x.com/a", "https://acme.com/") == "https://cdn.x.com/a"


def test_looks_like_job_url_same_domain():
    assert _looks_like_job_url("https://acme.com/jobs/1", "acme.com")


def test_looks_like_job_url_known_ats():
    assert _looks_like_job_url("https://boards.greenhouse.io/acme/job/123", "acme.com")
    assert _looks_like_job_url("https://acme.ashbyhq.com/job/123", "acme.com")


def test_looks_like_job_url_rejects_offsite():
    assert not _looks_like_job_url("https://random-other.com/job/1", "acme.com")


def test_parse_jobs_filters_offsite_urls():
    payload = {
        "jobs": [
            {"title": "Eng", "url": "https://acme.com/jobs/1", "location": "Paris"},
            {"title": "Spam", "url": "https://random.com/foo", "location": "Paris"},
        ]
    }
    jobs = parse_jobs(payload, "acme", "https://acme.com/careers")
    assert len(jobs) == 1
    assert jobs[0].url == "https://acme.com/jobs/1"


def test_parse_jobs_dedupes_by_url():
    payload = {
        "jobs": [
            {"title": "Eng", "url": "https://acme.com/jobs/1", "location": "Paris"},
            {"title": "Eng", "url": "https://acme.com/jobs/1", "location": "Paris"},
        ]
    }
    jobs = parse_jobs(payload, "acme", "https://acme.com/careers")
    assert len(jobs) == 1


def test_parse_jobs_normalises_relative_urls():
    payload = {
        "jobs": [{"title": "Eng", "url": "/jobs/1", "location": "Paris"}],
    }
    jobs = parse_jobs(payload, "acme", "https://acme.com/careers/")
    assert jobs[0].url == "https://acme.com/jobs/1"


def test_parse_jobs_drops_missing_title_or_url():
    payload = {
        "jobs": [
            {"title": "", "url": "https://acme.com/1"},
            {"title": "Eng", "url": ""},
            {"title": "Eng", "url": "https://acme.com/2"},
        ],
    }
    jobs = parse_jobs(payload, "acme", "https://acme.com/")
    assert len(jobs) == 1
    assert jobs[0].title == "Eng"


def test_parse_jobs_validates_remote_policy():
    payload = {
        "jobs": [
            {"title": "Eng A", "url": "https://acme.com/a", "remote_policy": "remote-eu"},
            {"title": "Eng B", "url": "https://acme.com/b", "remote_policy": "junk"},
        ]
    }
    jobs = parse_jobs(payload, "acme", "https://acme.com/")
    assert jobs[0].remote_policy == "remote-eu"
    assert jobs[1].remote_policy is None


def test_parse_jobs_handles_non_dict_payload():
    assert parse_jobs([], "acme", "https://acme.com/") == []
    assert parse_jobs(None, "acme", "https://acme.com/") == []
    assert parse_jobs({"jobs": "not a list"}, "acme", "https://acme.com/") == []


def test_html_to_text_strips_scripts_and_styles():
    html = """
        <html><head><style>body{color:red}</style></head>
        <body>
          <h1>Open roles</h1>
          <script>console.log(1)</script>
          <p>Senior Engineer · Paris</p>
        </body></html>
    """
    text = _html_to_text(html)
    assert "console.log" not in text
    assert "color:red" not in text
    assert "Senior Engineer" in text


def test_html_to_text_truncates():
    big = "<p>" + ("x " * 50000) + "</p>"
    text = _html_to_text(big)
    assert len(text) <= 32000
