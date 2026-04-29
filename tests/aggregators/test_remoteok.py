"""Contract tests for RemoteOK aggregator."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from pipeline.aggregators import remoteok

FIXTURE = Path(__file__).parent.parent / "extractors" / "fixtures" / "remoteok.json"


def _load() -> list:
    return json.loads(FIXTURE.read_text())


def test_parses_fixture():
    companies, jobs = remoteok.parse(_load())
    assert len(jobs) >= 1
    assert all(j.source == "remoteok" for j in jobs)
    # Every job's company_slug exists as a Company
    company_slugs = {c.slug for c in companies}
    assert all(j.company_slug in company_slugs for j in jobs)


def test_skips_legal_metadata_entry():
    payload = [{"legal": "..."}]
    cs, js = remoteok.parse(payload)
    assert cs == [] and js == []


def test_filter_eu_signal():
    payload = [
        {
            "company": "Foo",
            "url": "https://x.com/1",
            "position": "Eng",
            "location": "United States only",
        },
        {
            "company": "Bar",
            "url": "https://x.com/2",
            "position": "Eng",
            "location": "Europe",
        },
    ]
    cs, js = remoteok.parse(payload)
    assert {j.company_slug for j in js} == {"via-remoteok-bar"}


@pytest.mark.asyncio
@respx.mock
async def test_fetch_all_happy_path():
    respx.get("https://remoteok.com/api").mock(
        return_value=httpx.Response(200, json=_load())
    )
    async with httpx.AsyncClient() as client:
        cs, js = await remoteok.fetch_all(client=client)
    assert len(js) >= 1
