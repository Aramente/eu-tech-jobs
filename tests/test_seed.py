"""Validate the committed company seed."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.models import Company
from pipeline.seed import SeedError, load_companies

REPO_ROOT = Path(__file__).parent.parent
SEED_DIR = REPO_ROOT / "companies"


def test_committed_seed_validates():
    """Every committed company YAML must validate."""
    companies = load_companies(SEED_DIR)
    assert len(companies) >= 50, f"Expected ≥50 seed companies, found {len(companies)}"
    assert all(isinstance(c, Company) for c in companies)


def test_no_duplicate_slugs():
    companies = load_companies(SEED_DIR)
    slugs = [c.slug for c in companies]
    assert len(slugs) == len(set(slugs))


def test_at_least_30_have_greenhouse(tmp_path):
    """v0 contract: at least 30 companies use Greenhouse."""
    companies = load_companies(SEED_DIR)
    gh = [c for c in companies if c.ats and c.ats.provider == "greenhouse"]
    assert len(gh) >= 30, f"v0 needs ≥30 Greenhouse-backed companies; have {len(gh)}"


def test_malformed_yaml_raises(tmp_path):
    bad = tmp_path / "broken.yaml"
    bad.write_text("name: [unclosed list\n")
    with pytest.raises(SeedError, match="Invalid YAML"):
        load_companies(tmp_path)


def test_yaml_with_explicit_slug_rejected(tmp_path):
    bad = tmp_path / "x.yaml"
    bad.write_text(
        "slug: explicit\nname: X\ncountry: FR\nats:\n  provider: greenhouse\n  handle: x\n"
    )
    with pytest.raises(SeedError, match="do not declare"):
        load_companies(tmp_path)


def test_drafts_folder_skipped(tmp_path):
    drafts = tmp_path / "_drafts" / "ai"
    drafts.mkdir(parents=True)
    (drafts / "skipme.yaml").write_text(
        "name: Skip\ncountry: FR\nats:\n  provider: greenhouse\n  handle: skip\n"
    )
    real = tmp_path / "ai"
    real.mkdir()
    (real / "real.yaml").write_text(
        "name: Real\ncountry: FR\nats:\n  provider: greenhouse\n  handle: real\n"
    )
    companies = load_companies(tmp_path)
    assert {c.slug for c in companies} == {"real"}
