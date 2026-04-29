"""Tests for JustJoin.it aggregator."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from pipeline.aggregators import justjoinit

FIXTURE = Path(__file__).parent.parent / "extractors" / "fixtures" / "justjoinit.json"


def _load() -> dict:
    return json.loads(FIXTURE.read_text())


def test_parses_fixture():
    cs, js = justjoinit.parse(_load())
    assert len(js) >= 1
    assert all(j.source == "justjoinit" for j in js)


def test_handles_empty():
    assert justjoinit.parse({}) == ([], [])
    assert justjoinit.parse({"data": []}) == ([], [])


@pytest.mark.asyncio
@respx.mock
async def test_fetch_all_stops_when_empty():
    # Page 1 has data, page 2 empty
    respx.get("https://api.justjoin.it/v2/user-panel/offers?page=1").mock(
        return_value=httpx.Response(200, json=_load())
    )
    respx.get("https://api.justjoin.it/v2/user-panel/offers?page=2").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    async with httpx.AsyncClient() as client:
        cs, js = await justjoinit.fetch_all(client=client)
    assert len(js) >= 1
