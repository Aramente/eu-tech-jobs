"""Contract tests for the Personio XML extractor."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from pipeline.extractors import personio
from pipeline.extractors.base import ExtractorNotFoundError, ExtractorTransientError
from pipeline.models import Job

FIXTURE = Path(__file__).parent / "fixtures" / "personio_orderbird.xml"


def _load() -> str:
    return FIXTURE.read_text()


def test_parses_fixture():
    jobs = personio.parse_jobs(_load(), "orderbird", "orderbird")
    assert len(jobs) >= 1
    for j in jobs:
        assert isinstance(j, Job)
        assert j.source == "personio"
        assert j.url.startswith("https://orderbird.jobs.personio.com/job/")


def test_handles_empty_xml():
    assert personio.parse_jobs("", "x", "x") == []
    assert personio.parse_jobs("<workzag-jobs></workzag-jobs>", "x", "x") == []


def test_handles_malformed_xml():
    assert personio.parse_jobs("not xml at all", "x", "x") == []


def test_handles_bot_wall():
    bot_wall = "<!DOCTYPE html>Vercel Security Checkpoint"
    assert personio.parse_jobs(bot_wall, "x", "x") == []


@pytest.mark.asyncio
@respx.mock
async def test_happy_path():
    respx.get("https://orderbird.jobs.personio.com/xml").mock(
        return_value=httpx.Response(200, text=_load())
    )
    async with httpx.AsyncClient() as client:
        jobs = await personio.fetch_jobs(
            "orderbird", company_slug="orderbird", client=client
        )
    assert len(jobs) >= 1


@pytest.mark.asyncio
@respx.mock
async def test_404_raises():
    respx.get("https://missing.jobs.personio.com/xml").mock(
        return_value=httpx.Response(404)
    )
    with pytest.raises(ExtractorNotFoundError):
        await personio.fetch_jobs("missing", company_slug="missing")


@pytest.mark.asyncio
@respx.mock
async def test_bot_wall_raises_transient():
    respx.get("https://blocked.jobs.personio.com/xml").mock(
        return_value=httpx.Response(200, text="<!DOCTYPE html>Vercel Security Checkpoint")
    )
    with pytest.raises(ExtractorTransientError):
        await personio.fetch_jobs("blocked", company_slug="blocked")
