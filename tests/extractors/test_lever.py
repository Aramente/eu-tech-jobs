"""Contract tests for the Lever extractor."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from pipeline.extractors import lever
from pipeline.extractors.base import ExtractorNotFoundError, ExtractorTransientError
from pipeline.models import Job

FIXTURE = Path(__file__).parent / "fixtures" / "lever_mistral.json"


def _load() -> list:
    return json.loads(FIXTURE.read_text())


class TestParseJobs:
    def test_parses_fixture(self):
        jobs = lever.parse_jobs(_load(), "mistral")
        assert len(jobs) > 30
        for j in jobs:
            assert isinstance(j, Job)
            assert j.company_slug == "mistral"
            assert j.url.startswith("http")
            assert j.source == "lever"

    def test_empty_payload(self):
        assert lever.parse_jobs([], "x") == []

    def test_skips_postings_without_url(self):
        jobs = lever.parse_jobs([{"id": "x", "text": "no url"}], "x")
        assert jobs == []

    def test_lists_rendered_to_markdown(self):
        payload = [
            {
                "text": "Engineer",
                "hostedUrl": "https://jobs.lever.co/x/1",
                "lists": [
                    {"text": "What you'll do", "content": "<ul><li>Code</li></ul>"},
                    {"text": "About you", "content": "<ul><li>Python</li></ul>"},
                ],
            }
        ]
        jobs = lever.parse_jobs(payload, "x")
        assert len(jobs) == 1
        assert "What you'll do" in jobs[0].description_md
        assert "About you" in jobs[0].description_md
        assert "Code" in jobs[0].description_md

    def test_epoch_ms_dates(self):
        payload = [
            {
                "text": "Engineer",
                "hostedUrl": "https://jobs.lever.co/x/1",
                "createdAt": 1700000000000,
            }
        ]
        jobs = lever.parse_jobs(payload, "x")
        assert jobs[0].posted_at is not None
        assert jobs[0].posted_at.year >= 2023


class TestFetchJobs:
    @pytest.mark.asyncio
    @respx.mock
    async def test_happy_path(self):
        respx.get("https://api.lever.co/v0/postings/mistral?mode=json").mock(
            return_value=httpx.Response(200, json=_load())
        )
        async with httpx.AsyncClient() as client:
            jobs = await lever.fetch_jobs("mistral", company_slug="mistral", client=client)
        assert len(jobs) > 30

    @pytest.mark.asyncio
    @respx.mock
    async def test_404(self):
        respx.get("https://api.lever.co/v0/postings/missing?mode=json").mock(
            return_value=httpx.Response(404)
        )
        with pytest.raises(ExtractorNotFoundError):
            await lever.fetch_jobs("missing", company_slug="missing")

    @pytest.mark.asyncio
    @respx.mock
    async def test_5xx_retry_then_transient(self):
        respx.get("https://api.lever.co/v0/postings/flaky?mode=json").mock(
            return_value=httpx.Response(503)
        )
        with pytest.raises(ExtractorTransientError):
            await lever.fetch_jobs("flaky", company_slug="flaky")
