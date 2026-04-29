"""Tests for WeWorkRemotely RSS aggregator."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from pipeline.aggregators import weworkremotely

FIXTURE = Path(__file__).parent.parent / "extractors" / "fixtures" / "weworkremotely.xml"


def test_parses_rss_fixture():
    cs, js = weworkremotely.parse(FIXTURE.read_text())
    assert len(js) >= 1
    assert all(j.source == "weworkremotely" for j in js)


def test_handles_empty_xml():
    assert weworkremotely.parse("") == ([], [])
    assert weworkremotely.parse("<rss><channel></channel></rss>") == ([], [])


def test_handles_malformed_xml():
    assert weworkremotely.parse("garbage") == ([], [])


@pytest.mark.asyncio
@respx.mock
async def test_fetch_all_one_category():
    sample = FIXTURE.read_text()
    for cat in weworkremotely.CATEGORIES:
        respx.get(f"https://weworkremotely.com/categories/{cat}.rss").mock(
            return_value=httpx.Response(200, text=sample)
        )
    async with httpx.AsyncClient() as client:
        cs, js = await weworkremotely.fetch_all(client=client)
    assert len(js) >= 1
