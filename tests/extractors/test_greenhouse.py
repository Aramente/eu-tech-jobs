"""Contract tests for the Greenhouse extractor against a frozen fixture."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from pipeline.extractors import greenhouse
from pipeline.extractors.base import ExtractorNotFoundError, ExtractorTransientError
from pipeline.models import Job

FIXTURE = Path(__file__).parent / "fixtures" / "greenhouse_wayve.json"


def _load() -> dict:
    return json.loads(FIXTURE.read_text())


class TestParseJobs:
    def test_parses_fixture(self):
        jobs = greenhouse.parse_jobs(_load(), "wayve")
        assert len(jobs) > 30
        for j in jobs:
            assert isinstance(j, Job)
            assert j.company_slug == "wayve"
            assert j.url.startswith("http")
            assert j.source == "greenhouse"
            assert j.title

    def test_id_is_stable_across_calls(self):
        a = greenhouse.parse_jobs(_load(), "wayve")
        b = greenhouse.parse_jobs(_load(), "wayve")
        assert {j.id for j in a} == {j.id for j in b}

    def test_id_changes_with_company(self):
        a = greenhouse.parse_jobs(_load(), "wayve")
        b = greenhouse.parse_jobs(_load(), "other")
        # Same urls, different slug → different ids
        assert {j.id for j in a}.isdisjoint({j.id for j in b})

    def test_handles_empty_jobs(self):
        assert greenhouse.parse_jobs({"jobs": []}, "x") == []

    def test_handles_missing_jobs_key(self):
        assert greenhouse.parse_jobs({}, "x") == []

    def test_skips_jobs_without_url(self):
        payload = {"jobs": [{"id": 1, "title": "no url"}, {"id": 2, "title": "ok", "absolute_url": "https://x.com/1"}]}
        jobs = greenhouse.parse_jobs(payload, "x")
        assert len(jobs) == 1
        assert jobs[0].url == "https://x.com/1"

    def test_html_to_markdown(self):
        payload = {
            "jobs": [
                {
                    "id": 1,
                    "title": "Eng",
                    "absolute_url": "https://x.com/1",
                    "content": "<p>Hello <strong>world</strong></p>",
                    "location": {"name": "Paris"},
                }
            ]
        }
        jobs = greenhouse.parse_jobs(payload, "x")
        assert "Hello" in jobs[0].description_md
        assert "**world**" in jobs[0].description_md


class TestFetchJobs:
    @pytest.mark.asyncio
    @respx.mock
    async def test_happy_path(self):
        respx.get("https://boards-api.greenhouse.io/v1/boards/wayve/jobs?content=true").mock(
            return_value=httpx.Response(200, json=_load())
        )
        async with httpx.AsyncClient() as client:
            jobs = await greenhouse.fetch_jobs("wayve", company_slug="wayve", client=client)
        assert len(jobs) > 30

    @pytest.mark.asyncio
    @respx.mock
    async def test_404_raises_not_found(self):
        respx.get("https://boards-api.greenhouse.io/v1/boards/missing/jobs?content=true").mock(
            return_value=httpx.Response(404)
        )
        with pytest.raises(ExtractorNotFoundError, match="missing"):
            await greenhouse.fetch_jobs("missing", company_slug="missing")

    @pytest.mark.asyncio
    @respx.mock
    async def test_5xx_retries_then_raises_transient(self):
        respx.get("https://boards-api.greenhouse.io/v1/boards/flaky/jobs?content=true").mock(
            return_value=httpx.Response(503, text="overloaded")
        )
        with pytest.raises(ExtractorTransientError):
            await greenhouse.fetch_jobs("flaky", company_slug="flaky")

    @pytest.mark.live
    @pytest.mark.asyncio
    async def test_live_real_endpoint(self):
        async with httpx.AsyncClient() as client:
            jobs = await greenhouse.fetch_jobs("wayve", company_slug="wayve", client=client)
        assert len(jobs) >= 1
