"""Job aggregators (multi-company sources). Each module returns (companies, jobs)."""

from pipeline.aggregators import eures, justjoinit, remoteok, weworkremotely, wttj

AGGREGATORS = [remoteok, weworkremotely, justjoinit, wttj, eures]

__all__ = ["AGGREGATORS"]
