"""Tests for the company GitHub enricher."""

from __future__ import annotations

import httpx
import pytest
import respx

from pipeline.enrich import company as enricher
from pipeline.models import ATSReference, Company


def _company(github_org: str | None = "huggingface") -> Company:
    return Company(
        slug="hf",
        name="HF",
        country="FR",
        categories=["ai"],
        ats=ATSReference(provider="greenhouse", handle="huggingface"),
        github_org=github_org,
    )


@pytest.mark.asyncio
@respx.mock
async def test_enrich_oss_company():
    respx.get("https://api.github.com/orgs/huggingface/repos").mock(
        return_value=httpx.Response(
            200,
            json=[{"stargazers_count": 100000, "language": "Python", "name": "transformers"}],
        )
    )
    async with httpx.AsyncClient() as client:
        out = await enricher.enrich_company(client, _company())
    assert out.oss_signal is True
    assert out.top_repo_stars == 100000
    assert out.primary_language == "Python"


@pytest.mark.asyncio
@respx.mock
async def test_low_stars_not_oss():
    respx.get("https://api.github.com/orgs/huggingface/repos").mock(
        return_value=httpx.Response(
            200,
            json=[{"stargazers_count": 50, "language": "Python", "name": "small"}],
        )
    )
    async with httpx.AsyncClient() as client:
        out = await enricher.enrich_company(client, _company())
    assert out.oss_signal is False
    assert out.top_repo_stars == 50


@pytest.mark.asyncio
@respx.mock
async def test_no_github_org_noop():
    async with httpx.AsyncClient() as client:
        out = await enricher.enrich_company(client, _company(github_org=None))
    assert out.oss_signal is None


@pytest.mark.asyncio
@respx.mock
async def test_404_org_returns_unchanged():
    respx.get("https://api.github.com/orgs/missing/repos").mock(
        return_value=httpx.Response(404)
    )
    async with httpx.AsyncClient() as client:
        out = await enricher.enrich_company(client, _company(github_org="missing"))
    assert out.oss_signal is None  # unchanged
