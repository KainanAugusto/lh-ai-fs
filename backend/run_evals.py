"""BS Detector eval harness — single-command quality measurement.

    python run_evals.py              # run the pipeline live, then score it
    python run_evals.py --report r.json   # score a previously saved report (no LLM calls)

Measures recall against a hand-annotated golden set, precision (golden lower
bound), and a deterministic hallucination rate. See evals/metrics.py for the
definitions and the rationale behind each.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from documents import load_documents
from evals.metrics import evaluate

GOLDEN_PATH = Path(__file__).parent / "evals" / "golden.json"
LAST_REPORT_PATH = Path(__file__).parent / "evals" / "last_report.json"


def _bar(value: float, width: int = 24) -> str:
    filled = round(value * width)
    return "█" * filled + "░" * (width - filled)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the BS Detector eval suite.")
    parser.add_argument(
        "--report",
        type=str,
        default=None,
        help="Path to a saved report JSON to score instead of running the pipeline live.",
    )
    args = parser.parse_args()

    golden = json.loads(GOLDEN_PATH.read_text())
    documents = load_documents()

    if args.report:
        report = json.loads(Path(args.report).read_text())
        if "report" in report:  # accept the API envelope {"report": {...}}
            report = report["report"]
        print(f"Scoring saved report: {args.report}\n")
    else:
        print("Running pipeline live (this makes LLM calls)...\n")
        from pipeline import run_pipeline  # imported lazily so --report needs no LLM config

        report = (asyncio.run(run_pipeline())).model_dump(mode="json")
        LAST_REPORT_PATH.write_text(json.dumps(report, indent=2))

    results = evaluate(report, golden, documents)

    print("=" * 70)
    print(" BS DETECTOR — EVAL RESULTS")
    print("=" * 70)

    # Recall breakdown
    print(f"\nRECALL — known defects caught: {results['caught_count']}/{results['golden_total']}")
    for item in results["item_results"]:
        mark = "✓ caught " if item["caught"] else "✗ MISSED "
        print(f"   {mark} [{item['category']:>11}] {item['id']}")

    print("\n" + "-" * 70)
    print("METRICS")
    print("-" * 70)
    r = results["recall"]
    p = results["precision_golden_lower_bound"]
    h = results["hallucination_rate"]
    print(f"  Recall                       {r:5.0%}  {_bar(r)}  ({results['caught_count']}/{results['golden_total']} defects)")
    print(f"  Precision (golden lower-bnd) {p:5.0%}  {_bar(p)}  ({results['matched_flags']}/{results['total_flags']} flags map to a known defect)")
    print(f"  Hallucination rate           {h:5.0%}  {_bar(h)}  ({results['quotes_hallucinated']}/{results['quotes_checked']} checked quotes not found in source)")

    if results["hallucinated_details"]:
        print("\n  Quotes NOT found verbatim in their source document:")
        for d in results["hallucinated_details"]:
            print(f"    - {d}")

    print("\nNotes:")
    print("  - Precision is a deliberate LOWER BOUND: the brief has more real issues than the")
    print("    6 curated golden defects, so valid extra flags count against this number.")
    print("  - Hallucination rate is deterministic (verbatim substring check), no LLM judge.")
    print("=" * 70)


if __name__ == "__main__":
    main()
