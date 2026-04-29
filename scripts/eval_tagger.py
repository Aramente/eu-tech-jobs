"""Evaluate tagger prompt variants on a stratified sample of real jobs.

Strategy:
1. Load `data/latest/jobs.parquet` and sample N jobs stratified by source.
2. Run each prompt variant in pipeline.enrich.prompts.VARIANTS against each
   sampled job.
3. Score per variant:
   - role_family / seniority / remote_policy coverage (% non-null)
   - per-source breakdown (does the variant work on Ashby's empty
     descriptions? on aggregator title-only listings?)
   - average stack size (extraction quality stays consistent)
   - tokens / job (cost)
4. Emit a markdown report at `data/eval/<timestamp>.md` you can eyeball.

Run:
    DEEPSEEK_API_KEY=sk-... uv run python scripts/eval_tagger.py
    uv run python scripts/eval_tagger.py --sample-size 30 --variants v1_differentiated,v2_few_shot

Env: requires DEEPSEEK_API_KEY (or MISTRAL_API_KEY).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.enrich.prompts import VARIANTS  # noqa: E402
from pipeline.enrich.tagger import (  # noqa: E402
    call_llm,
    is_configured,
    normalize_response,
    selected_provider,
    strip_boilerplate,
)

SOURCES_PER_BUCKET = 8  # sample size per source for stratification


def stratified_sample(rows: list[dict], n: int) -> list[dict]:
    """Sample `n` jobs trying to keep representation across sources."""
    by_source: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_source[r.get("source", "unknown")].append(r)
    # Sort each bucket by description length desc (so non-empty descriptions
    # are picked first within each source) so we get rich + lean both.
    for s in by_source:
        by_source[s].sort(
            key=lambda r: -(len(r.get("description_md") or "")),
        )
    out: list[dict] = []
    target = max(1, n // max(len(by_source), 1))
    for _src, bucket in by_source.items():
        # Take half from the top (rich descriptions) and half from the
        # tail (no descriptions) when possible, to test both regimes.
        half = max(1, target // 2)
        out.extend(bucket[:half])
        if len(bucket) > half:
            out.extend(bucket[-half:])
    # If we under-shot, pad from any source.
    if len(out) < n:
        flat = [r for s in by_source.values() for r in s]
        seen_ids = {r["id"] for r in out}
        for r in flat:
            if r["id"] not in seen_ids:
                out.append(r)
                if len(out) >= n:
                    break
    return out[:n]


def run_variant(
    variant: str,
    jobs: list[dict],
) -> tuple[list[dict], dict[str, int]]:
    """Run one variant against the sample. Returns (results, totals)."""
    results: list[dict] = []
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for j in jobs:
        title = j.get("title") or ""
        desc = strip_boilerplate(j.get("description_md") or "")
        try:
            raw, usage = call_llm(title, desc, variant=variant)
            normalized = normalize_response(raw, desc)
            err = None
        except Exception as exc:  # noqa: BLE001
            raw, usage, normalized, err = {}, {}, {}, str(exc)
        for k, v in usage.items():
            totals[k] += v
        results.append(
            {
                "id": j["id"],
                "source": j.get("source", "unknown"),
                "title": title,
                "has_description": bool(desc),
                "raw": raw,
                "normalized": normalized,
                "error": err,
            }
        )
    return results, totals


def coverage(results: list[dict], field: str) -> float:
    if not results:
        return 0.0
    n = sum(1 for r in results if r["normalized"].get(field) not in (None, ""))
    return n / len(results)


def avg_stack(results: list[dict]) -> float:
    if not results:
        return 0.0
    return sum(len(r["normalized"].get("stack") or []) for r in results) / len(results)


def render_markdown(
    sample: list[dict],
    by_variant: dict[str, list[dict]],
    cost_by_variant: dict[str, dict[str, int]],
) -> str:
    variants = list(by_variant.keys())
    sources = sorted({s["source"] for s in sample})
    lines: list[str] = []
    lines.append("# Tagger prompt variant evaluation\n")
    lines.append(
        f"Generated {datetime.now(UTC).isoformat()} on "
        f"{len(sample)} jobs across {len(sources)} sources "
        f"(provider: {selected_provider()}).\n"
    )

    # --- Summary ---
    lines.append("## Summary\n")
    lines.append(
        "| Variant | role_family | seniority | remote_policy | "
        "visa_sponsorship | avg stack | total tokens |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for v in variants:
        rs = by_variant[v]
        toks = cost_by_variant[v]["total_tokens"]
        lines.append(
            f"| `{v}` | {coverage(rs, 'role_family')*100:.0f}% | "
            f"{coverage(rs, 'seniority')*100:.0f}% | "
            f"{coverage(rs, 'remote_policy')*100:.0f}% | "
            f"{coverage(rs, 'visa_sponsorship')*100:.0f}% | "
            f"{avg_stack(rs):.1f} | "
            f"{toks:,} |"
        )
    lines.append("")

    # --- Per-source ---
    lines.append("## Per-source breakdown (role_family coverage)\n")
    header = "| Source | sample size | " + " | ".join(f"`{v}`" for v in variants) + " |"
    sep = "|---" * (2 + len(variants)) + "|"
    lines.append(header)
    lines.append(sep)
    for src in sources:
        sample_n = sum(1 for s in sample if s["source"] == src)
        cells = [
            f"{src}",
            f"{sample_n}",
        ]
        for v in variants:
            rs = [r for r in by_variant[v] if r["source"] == src]
            cells.append(f"{coverage(rs, 'role_family')*100:.0f}%")
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")

    # --- Sample table ---
    lines.append("## Side-by-side sample (first 12)\n")
    lines.append("Format per cell: `role · seniority · remote · |stack|`\n")
    lines.append("| # | Source | Title | " + " | ".join(f"`{v}`" for v in variants) + " |")
    lines.append("|---" * (3 + len(variants)) + "|")
    for i, s in enumerate(sample[:12]):
        cells = [
            str(i + 1),
            s["source"],
            (s["title"][:60] + "…") if len(s["title"]) > 60 else s["title"],
        ]
        for v in variants:
            row = next((r for r in by_variant[v] if r["id"] == s["id"]), None)
            if not row:
                cells.append("—")
                continue
            n = row["normalized"]
            cells.append(
                f"{n.get('role_family') or '—'} · "
                f"{n.get('seniority') or '—'} · "
                f"{n.get('remote_policy') or '—'} · "
                f"|{len(n.get('stack') or [])}|"
            )
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")

    # --- Recommendation ---
    lines.append("## Pick the winner\n")
    lines.append(
        "1. Look at the summary table — which variant has highest combined "
        "role_family + seniority coverage?\n"
        "2. Check the per-source breakdown — does it work on Ashby (no "
        "descriptions) and aggregator-only listings?\n"
        "3. Eyeball 5-6 rows in the side-by-side — are the picks sensible?\n"
        "4. Check tokens — V2 is more expensive than V1 by ~2x; only pick V2 "
        "if it meaningfully wins on quality.\n\n"
        "Then update `pipeline/enrich/prompts.py::DEFAULT_VARIANT` and re-run "
        "the daily workflow with `--retag-all` for one cycle.\n"
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sample-size", type=int, default=40,
        help="Total number of jobs to sample (stratified by source).",
    )
    parser.add_argument(
        "--variants", default=",".join(VARIANTS.keys()),
        help="Comma-separated variant names to evaluate.",
    )
    parser.add_argument(
        "--parquet", default="data/latest/jobs.parquet",
        help="Path to the jobs parquet to sample from.",
    )
    parser.add_argument(
        "--out-dir", default="data/eval",
        help="Where to write the markdown + JSON results.",
    )
    args = parser.parse_args()

    if not is_configured():
        print(
            "ERROR: no LLM provider configured. Set DEEPSEEK_API_KEY (or "
            "MISTRAL_API_KEY) and re-run.",
            file=sys.stderr,
        )
        sys.exit(1)

    variants = [v.strip() for v in args.variants.split(",") if v.strip()]
    for v in variants:
        if v not in VARIANTS:
            print(f"Unknown variant '{v}'. Available: {sorted(VARIANTS)}")
            sys.exit(2)

    parquet = Path(args.parquet)
    if not parquet.exists():
        print(f"Missing {parquet}. Run `uv run pipeline run` first.")
        sys.exit(2)

    print(f"Loading {parquet}…")
    rows = pq.read_table(parquet).to_pylist()
    print(f"  {len(rows):,} jobs total. Sampling {args.sample_size}…")
    sample = stratified_sample(rows, args.sample_size)
    print(f"  Sample: {Counter(r['source'] for r in sample).most_common()}")

    by_variant: dict[str, list[dict]] = {}
    cost_by_variant: dict[str, dict[str, int]] = {}
    for v in variants:
        print(f"\n→ Running variant `{v}` ({len(sample)} calls)…")
        started = time.time()
        results, totals = run_variant(v, sample)
        elapsed = time.time() - started
        print(
            f"  done in {elapsed:.0f}s · {totals['total_tokens']:,} tokens · "
            f"role_family {coverage(results, 'role_family')*100:.0f}% · "
            f"seniority {coverage(results, 'seniority')*100:.0f}% · "
            f"remote_policy {coverage(results, 'remote_policy')*100:.0f}%"
        )
        by_variant[v] = results
        cost_by_variant[v] = totals

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    md_path = out_dir / f"{stamp}.md"
    md_path.write_text(render_markdown(sample, by_variant, cost_by_variant))
    json_path = out_dir / f"{stamp}.json"
    json_path.write_text(
        json.dumps(
            {
                "sample": sample,
                "by_variant": by_variant,
                "cost_by_variant": cost_by_variant,
            },
            default=str,
            indent=2,
        )
    )
    latest_md = out_dir / "latest.md"
    latest_md.write_text(md_path.read_text())
    print(f"\n✓ Report: {md_path}")
    print(f"✓ Latest: {latest_md}")


if __name__ == "__main__":
    main()
