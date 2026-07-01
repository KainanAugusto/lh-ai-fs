"""Metric computation for the eval harness.

Three metrics, by design:

- recall — of the hand-annotated known defects (golden.json), how many did the
  pipeline catch? Matched by keyword "signals" so it survives the LLM's wording
  variation between runs.
- precision (golden lower-bound) — of the flags the pipeline raised, how many map
  to a known defect. This is a deliberate LOWER BOUND: the brief contains more
  real issues than the curated golden set, so a genuine extra flag counts against
  this number. Reported honestly rather than inflated.
- hallucination rate — of the flags that cite a verbatim quote, how many of those
  quotes do NOT actually appear in the source document. Fully deterministic, no
  LLM judge: a fabricated quote is the clearest signal of a fabricated finding.
"""

from __future__ import annotations

# Single source of truth for text normalization + "is this quote in the source":
# the same helpers the runtime grounding guardrail uses, so the eval and the live
# pipeline agree on what "grounded" means.
from grounding import normalize


def matches_signals(text: str, signals: list[list[str]]) -> bool:
    """True if every keyword of ANY one signal set appears in ``text``."""
    norm = normalize(text)
    return any(all(normalize(kw) in norm for kw in sig_set) for sig_set in signals)


# Phrases a model uses to DECLINE to quote (instead of returning null). These are
# not fabricated quotes — they mean "no quote" — so they must not count as
# hallucinations. Weaker models tend to fill the field with prose like this.
_NO_QUOTE_SENTINELS = {
    "not specified",
    "not specified in the brief",
    "not specified in the motion",
    "n/a",
    "na",
    "none",
    "no quote",
    "no direct quote",
    "not applicable",
    "not available",
    "unknown",
}


def check_quote(quote: str | None, document: str):
    """Is a finding's quote actually in its source?

    Returns True (grounded), False (not found = fabricated), or None (no
    meaningful quote to check — excluded from the hallucination denominator).
    """
    if not quote or not quote.strip():
        return None
    norm_quote = normalize(quote).strip(" .\"'")
    if norm_quote in _NO_QUOTE_SENTINELS:  # model declined to quote, not a fabrication
        return None
    if len(norm_quote) < 8:  # too short to verify meaningfully
        return None
    return norm_quote in normalize(document)


def _consistency_text(f: dict) -> str:
    return " ".join(
        [
            f.get("msj_claim", ""),
            f.get("contradicting_document", ""),
            f.get("contradicting_quote", ""),
            f.get("reasoning", ""),
        ]
    )


def _citation_text(f: dict) -> str:
    return " ".join(
        [
            f.get("case_name", ""),
            f.get("citation", ""),
            f.get("proposition", ""),
            f.get("verdict", ""),
            f.get("reasoning", ""),
            f.get("evidence_quote") or "",
        ]
    )


def evaluate(report: dict, golden: dict, documents: dict[str, str]) -> dict:
    citation_findings = report.get("citation_findings", [])
    consistency_findings = report.get("consistency_findings", [])
    flagged_citations = [f for f in citation_findings if f.get("is_problem")]

    # ---- Recall: which known defects were caught? -------------------------
    item_results = []
    for item in golden["items"]:
        cat = item["category"]
        candidates: list[str] = []
        if cat in ("consistency", "any"):
            candidates += [_consistency_text(f) for f in consistency_findings]
        if cat in ("citation", "any"):
            candidates += [_citation_text(f) for f in flagged_citations]
        caught = any(matches_signals(t, item["signals"]) for t in candidates)
        item_results.append({"id": item["id"], "category": cat, "caught": caught})

    caught_count = sum(1 for r in item_results if r["caught"])
    recall = caught_count / len(golden["items"]) if golden["items"] else 0.0

    # ---- Precision (golden lower-bound) -----------------------------------
    sig_consistency = [s for it in golden["items"] if it["category"] in ("consistency", "any") for s in it["signals"]]
    sig_citation = [s for it in golden["items"] if it["category"] in ("citation", "any") for s in it["signals"]]

    total_flags = len(flagged_citations) + len(consistency_findings)
    matched_flags = 0
    for f in consistency_findings:
        if matches_signals(_consistency_text(f), sig_consistency):
            matched_flags += 1
    for f in flagged_citations:
        if matches_signals(_citation_text(f), sig_citation):
            matched_flags += 1
    precision = (matched_flags / total_flags) if total_flags else 0.0

    # ---- Hallucination rate (quote grounding) -----------------------------
    msj = documents.get("motion_for_summary_judgment", "")
    checkable = 0
    hallucinated = 0
    hallucinated_details = []

    for f in consistency_findings:
        res = check_quote(f.get("contradicting_quote", ""), documents.get(f.get("contradicting_document", ""), ""))
        if res is None:
            continue
        checkable += 1
        if not res:
            hallucinated += 1
            hallucinated_details.append(f"consistency / {f.get('contradicting_document')}: {(f.get('contradicting_quote') or '')[:70]!r}")

    for f in flagged_citations:
        res = check_quote(f.get("evidence_quote", ""), msj)
        if res is None:
            continue
        checkable += 1
        if not res:
            hallucinated += 1
            hallucinated_details.append(f"citation / {f.get('case_name')}: {(f.get('evidence_quote') or '')[:70]!r}")

    hallucination_rate = (hallucinated / checkable) if checkable else 0.0

    return {
        "recall": recall,
        "caught_count": caught_count,
        "golden_total": len(golden["items"]),
        "item_results": item_results,
        "precision_golden_lower_bound": precision,
        "matched_flags": matched_flags,
        "total_flags": total_flags,
        "hallucination_rate": hallucination_rate,
        "quotes_checked": checkable,
        "quotes_hallucinated": hallucinated,
        "hallucinated_details": hallucinated_details,
    }
