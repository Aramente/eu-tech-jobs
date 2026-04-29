"""Contract tests for the Recruitee extractor."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from pipeline.extractors import recruitee
from pipeline.extractors.base import ExtractorNotFoundError
from pipeline.models import Job

FIXTURE = Path(__file__).parent / "fixtures" / "recruitee_jobtome.json"


def _load() -> dict:
    return json.loads(FIXTURE.read_text())


def test_parses_fixture():
    jobs = recruitee.parse_jobs(_load(), "jobtome")
    assert len(jobs) >= 1
    for j in jobs:
        assert isinstance(j, Job)
        assert j.source == "recruitee"


def test_empty():
    assert recruitee.parse_jobs({}, "x") == []
    assert recruitee.parse_jobs({"offers": []}, "x") == []


@pytest.mark.asyncio
@respx.mock
async def test_happy_path():
    respx.get("https://jobtome.recruitee.com/api/offers/").mock(
        return_value=httpx.Response(200, json=_load())
    )
    async with httpx.AsyncClient() as client:
        jobs = await recruitee.fetch_jobs("jobtome", company_slug="jobtome", client=client)
    assert len(jobs) >= 1


@pytest.mark.asyncio
@respx.mock
async def test_404_raises():
    respx.get("https://missing.recruitee.com/api/offers/").mock(
        return_value=httpx.Response(404)
    )
    with pytest.raises(ExtractorNotFoundError):
        await recruitee.fetch_jobs("missing", company_slug="missing")
