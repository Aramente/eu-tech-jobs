"""Job aggregators (multi-company sources). Each module returns (companies, jobs)."""

from pipeline.aggregators import (
    eures,
    fashionjobs,
    justjoinit,
    remoteok,
    weworkremotely,
    wttj,
)

AGGREGATORS = [remoteok, weworkremotely, justjoinit, wttj, eures, fashionjobs]

__all__ = ["AGGREGATORS"]
