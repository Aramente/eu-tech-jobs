"""Contract tests for the Ashby extractor."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from pipeline.extractors import ashby
from pipeline.extractors.base import ExtractorNotFoundError
from pipeline.models import Job

FIXTURE = Path(__file__).parent / "fixtures" / "ashby_photoroom.json"


def _load() -> dict:
    return json.loads(FIXTURE.read_text())


class TestParseJobs:
    def test_parses_fixture(self):
        jobs = ashby.parse_jobs(_load(), "photoroom", "photoroom")
        assert len(jobs) >= 5
        for j in jobs:
            assert isinstance(j, Job)
            assert j.company_slug == "photoroom"
            assert j.url.startswith("https://jobs.ashbyhq.com/")
            assert j.source == "ashby"

    def test_handles_empty(self):
        assert ashby.parse_jobs({"data": {"jobBoard": {"jobPostings": []}}}, "x", "x") == []

    def test_handles_missing_data(self):
        assert ashby.parse_jobs({}, "x", "x") == []

    def test_secondary_locations_appended(self):
        payload = {
            "data": {
                "jobBoard": {
                    "jobPostings": [
                        {
                            "id": "abc",
                            "title": "Eng",
                            "locationName": "Paris",
                            "secondaryLocations": [
                                {"locationName": "Remote EU"},
                            ],
                        }
                    ]
                }
            }
        }
        jobs = ashby.parse_jobs(payload, "x", "x")
        assert "Paris" in jobs[0].location
        assert "Remote EU" in jobs[0].location


class TestFetchJobs:
    @pytest.mark.asyncio
    @respx.mock
    async def test_happy_path(self):
        respx.post("https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiBoardWithTeams").mock(
            return_value=httpx.Response(200, json=_load())
        )
        async with httpx.AsyncClient() as client:
            jobs = await ashby.fetch_jobs("photoroom", company_slug="photoroom", client=client)
        assert len(jobs) >= 1

    @pytest.mark.asyncio
    @respx.mock
    async def test_not_found_raises(self):
        respx.post("https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiBoardWithTeams").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"jobBoard": None}, "errors": [{"message": "Could not find org"}]},
            )
        )
        with pytest.raises(ExtractorNotFoundError):
            await ashby.fetch_jobs("missing", company_slug="missing")
