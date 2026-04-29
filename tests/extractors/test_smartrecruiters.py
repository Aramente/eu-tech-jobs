"""Contract tests for the SmartRecruiters extractor."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from pipeline.extractors import smartrecruiters
from pipeline.extractors.base import ExtractorNotFoundError
from pipeline.models import Job

FIXTURE = Path(__file__).parent / "fixtures" / "smartrecruiters_boschgroup.json"


def _load() -> dict:
    return json.loads(FIXTURE.read_text())


def test_parses_fixture():
    jobs = smartrecruiters.parse_jobs(_load(), "boschgroup")
    assert len(jobs) >= 5
    for j in jobs:
        assert isinstance(j, Job)
        assert j.source == "smartrecruiters"


def test_empty():
    assert smartrecruiters.parse_jobs({}, "x") == []
    assert smartrecruiters.parse_jobs({"content": []}, "x") == []


@pytest.mark.asyncio
@respx.mock
async def test_pagination_terminates():
    page = _load()
    page["totalFound"] = len(page.get("content", []))
    respx.get(
        "https://api.smartrecruiters.com/v1/companies/boschgroup/postings?limit=100&offset=0"
    ).mock(return_value=httpx.Response(200, json=page))
    async with httpx.AsyncClient() as client:
        jobs = await smartrecruiters.fetch_jobs(
            "boschgroup", company_slug="boschgroup", client=client
        )
    assert len(jobs) >= 1


@pytest.mark.asyncio
@respx.mock
async def test_404_raises():
    respx.get(
        "https://api.smartrecruiters.com/v1/companies/missing/postings?limit=100&offset=0"
    ).mock(return_value=httpx.Response(404))
    with pytest.raises(ExtractorNotFoundError):
        await smartrecruiters.fetch_jobs("missing", company_slug="missing")
