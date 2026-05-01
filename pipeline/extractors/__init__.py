"""Per-ATS extractors. Each module exposes `fetch_jobs(handle)` returning `list[Job]`."""

from pipeline.extractors import (
    ashby,
    custom_page,
    greenhouse,
    lever,
    personio,
    phenom,
    recruitee,
    smartrecruiters,
    workday,
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
    "custom_page": custom_page,
    "workday": workday,
    "phenom": phenom,
}

__all__ = [
    "EXTRACTORS",
    "ExtractorError",
    "ExtractorNotFoundError",
    "ExtractorTransientError",
]
