"""Move company YAMLs that have produced 0 jobs for N consecutive
recent runs into companies/_archive/, keeping the active seed lean.

Reads the per-company job counts from the latest snapshot's
extractor_results plus historical metadata.json files where available.

Usage:
    python scripts/archive-stale.py             # dry-run
    python scripts/archive-stale.py --commit    # move files
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = ROOT / "data" / "snapshots"
ARCHIVE_DIR = ROOT / "companies" / "_archive"
THRESHOLD_RUNS = 7  # archive after 7 consecutive 0-job snapshots


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", action="store_true")
    parser.add_argument(
        "--threshold", type=int, default=THRESHOLD_RUNS,
        help="Consecutive 0-job runs needed to archive a company.",
    )
    args = parser.parse_args()

    snapshot_dirs = sorted(SNAPSHOTS.iterdir(), key=lambda p: p.name)[-args.threshold:]
    if not snapshot_dirs:
        print("No snapshots yet — nothing to do.")
        return 0
    print(f"Inspecting last {len(snapshot_dirs)} snapshots:")
    for d in snapshot_dirs:
        print(f"  - {d.name}")

    # Build slug → list of job counts across the recent snapshots.
    counts: dict[str, list[int]] = defaultdict(list)
    for d in snapshot_dirs:
        meta_path = d / "metadata.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text())
        for r in meta.get("extractor_results") or []:
            counts[r["company_slug"]].append(int(r.get("job_count") or 0))

    # Companies with EVERY recent run = 0 (and at least the threshold # of runs).
    stale = [
        slug for slug, hits in counts.items()
        if len(hits) >= args.threshold and all(h == 0 for h in hits)
    ]
    print(f"\nStale candidates: {len(stale)}")
    for s in sorted(stale)[:30]:
        print(f"  {s}")
    if len(stale) > 30:
        print(f"  … +{len(stale) - 30} more")

    if not args.commit:
        print("\n(dry-run — pass --commit to move files)")
        return 0

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    moved = 0
    for slug in stale:
        for src in (ROOT / "companies").rglob(f"{slug}.yaml"):
            if "_archive" in src.parts or "_drafts" in src.parts:
                continue
            dst = ARCHIVE_DIR / f"{slug}.yaml"
            src.rename(dst)
            moved += 1
            break
    print(f"\nMoved {moved} stale companies → companies/_archive/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
