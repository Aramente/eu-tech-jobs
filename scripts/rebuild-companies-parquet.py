"""One-shot: rebuild data/latest/companies.parquet from YAMLs while
preserving GitHub-enriched fields (oss_signal, top_repo_stars,
primary_language) from the existing parquet.

Use after a schema change to companies.parquet (e.g. adding industry_tags)
when you don't want to wait for the next full pipeline run.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pyarrow.parquet as pq

from pipeline.seed import load_companies
from pipeline.snapshot.writer import _COMPANY_SCHEMA, _company_to_row
import pyarrow as pa


def main() -> None:
    repo = Path(__file__).resolve().parent.parent
    seed_dir = repo / "companies"
    latest = repo / "data" / "latest" / "companies.parquet"

    enriched: dict[str, dict] = {}
    if latest.exists():
        for row in pq.read_table(latest).to_pylist():
            enriched[row["slug"]] = {
                "oss_signal": row.get("oss_signal"),
                "top_repo_stars": row.get("top_repo_stars"),
                "primary_language": row.get("primary_language"),
            }

    companies = load_companies(seed_dir)
    rows = []
    for c in companies:
        row = _company_to_row(c)
        e = enriched.get(c.slug)
        if e:
            row["oss_signal"] = e["oss_signal"]
            row["top_repo_stars"] = e["top_repo_stars"]
            row["primary_language"] = e["primary_language"]
        rows.append(row)

    table = pa.Table.from_pylist(rows, schema=_COMPANY_SCHEMA)
    tmp = latest.with_suffix(".parquet.tmp")
    pq.write_table(table, tmp, compression="snappy")
    shutil.move(str(tmp), str(latest))
    print(f"[rebuild] wrote {len(rows)} companies → {latest}")


if __name__ == "__main__":
    main()
