"""Job aggregators (multi-company sources). Each module returns (companies, jobs)."""

from pipeline.aggregators import (
    bof_careers,
    eures,
    fashionjobs,
    justjoinit,
    remoteok,
    weworkremotely,
    wttj,
)

AGGREGATORS = [
    remoteok,
    weworkremotely,
    justjoinit,
    wttj,
    eures,
    fashionjobs,
    bof_careers,
]

__all__ = ["AGGREGATORS"]
