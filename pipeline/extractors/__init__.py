"""Per-ATS extractors. Each module exposes `fetch_jobs(handle)` returning `list[Job]`."""

from pipeline.extractors import greenhouse
from pipeline.extractors.base import (
    ExtractorError,
    ExtractorNotFoundError,
    ExtractorTransientError,
)

EXTRACTORS = {
    "greenhouse": greenhouse,
}

__all__ = [
    "EXTRACTORS",
    "ExtractorError",
    "ExtractorNotFoundError",
    "ExtractorTransientError",
]
