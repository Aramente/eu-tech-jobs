"""Job aggregators (multi-company sources). Each module returns (companies, jobs)."""

from pipeline.aggregators import justjoinit, remoteok, weworkremotely

AGGREGATORS = [remoteok, weworkremotely, justjoinit]

__all__ = ["AGGREGATORS"]
