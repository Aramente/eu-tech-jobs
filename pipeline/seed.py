"""Load + validate the curated company seed from `companies/**/*.yaml`."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from pipeline.models import Company


class SeedError(Exception):
    """Raised when a seed YAML is malformed or duplicated."""


def load_companies(seed_dir: Path) -> list[Company]:
    """Walk `seed_dir` for `*.yaml`, validate each file as a Company.

    The slug is derived from the filename stem; YAMLs do not (and must not)
    declare slug themselves.
    """
    companies: dict[str, Company] = {}
    for path in sorted(seed_dir.rglob("*.yaml")):
        if "_drafts" in path.parts:
            continue
        slug = path.stem
        try:
            raw = yaml.safe_load(path.read_text())
        except yaml.YAMLError as exc:
            raise SeedError(f"Invalid YAML in {path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise SeedError(f"{path}: expected a YAML mapping at top level.")
        if "slug" in raw:
            raise SeedError(f"{path}: do not declare `slug` in YAML; it derives from filename.")
        try:
            company = Company.model_validate({**raw, "slug": slug})
        except ValidationError as exc:
            raise SeedError(f"{path}: validation error: {exc}") from exc
        if slug in companies:
            raise SeedError(f"Duplicate slug `{slug}` (from {path})")
        companies[slug] = company
    return list(companies.values())
