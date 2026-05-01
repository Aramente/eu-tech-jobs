"""EURES — official EU public-employment-services job portal.

EURES exposes a structured search API for partners. Partner credentials
are required via the EURES Partnership programme; once obtained they go
into env vars EURES_CLIENT_ID + EURES_CLIENT_SECRET. Without them, this
extractor is a graceful no-op.

To register for credentials:
1. Go to https://ec.europa.eu/eures/public/eures-partner-form (NB: the
   public-API access path has shifted in 2024-25; if the form 404s,
   contact EURES Support — eu-eures-helpdesk@europa.eu).
2. Register your organisation as a recognised "Member" or "Partner".
3. Once approved, request OAuth2 client_credentials access to the
   Job-Vacancy Search Engine (JVSE) API.

When credentials land, set the GHA secrets:
   EURES_CLIENT_ID, EURES_CLIENT_SECRET

Expected scale: 3M+ EU jobs in the public dataset, ~400k FR. ISCO codes
1212/2423 are HR/Recruitment specialists — should yield 500+ FR TA
jobs alone.
"""

from __future__ import annotations

import logging
import os

import httpx

from pipeline.models import Company, Job

logger = logging.getLogger(__name__)

NAME = "eures"


def is_configured() -> bool:
    return bool(os.environ.get("EURES_CLIENT_ID") and os.environ.get("EURES_CLIENT_SECRET"))


async def fetch_all(
    *, client: httpx.AsyncClient | None = None
) -> tuple[list[Company], list[Job]]:
    """No-op until EURES partner credentials are configured."""
    if not is_configured():
        logger.info(
            "EURES extractor disabled — EURES_CLIENT_ID/SECRET not set. "
            "See pipeline/aggregators/eures.py for partner registration steps."
        )
        return [], []
    # TODO: implement OAuth2 client_credentials flow + JVSE search call.
    # Keep this stub small until credentials are in hand and the live API
    # surface can be confirmed.
    logger.warning(
        "EURES credentials present but extractor not yet implemented. "
        "Implement the JVSE search loop here once the API surface is confirmed."
    )
    return [], []
