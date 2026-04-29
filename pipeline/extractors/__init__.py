"""Per-ATS extractors. Each module exposes `fetch_jobs(handle)` returning `list[Job]`."""

from pipeline.extractors import (
    ashby,
    greenhouse,
    lever,
    personio,
    recruitee,
    smartrecruiters,
)
from pipeline.extractors.base import (
    ExtractorError,
    ExtractorNotFoundError,
    ExtractorTransientError,
)

EXTRACTORS = {
    "greenhouse": greenhouse,
    "lever": lever,
    "ashby": ashby,
    "smartrecruiters": smartrecruiters,
    "recruitee": recruitee,
    "personio": personio,
}

__all__ = [
    "EXTRACTORS",
    "ExtractorError",
    "ExtractorNotFoundError",
    "ExtractorTransientError",
]
