"""Shared types for ATS extractors."""

from __future__ import annotations


class ExtractorError(Exception):
    """Base class for extractor errors."""


class ExtractorNotFoundError(ExtractorError):
    """The handle does not exist (404)."""


class ExtractorTransientError(ExtractorError):
    """A transient failure that may succeed on retry (5xx, network)."""
