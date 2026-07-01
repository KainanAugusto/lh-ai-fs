"""Orchestration of the multi-agent pipeline.

Flow:
    Extractor (required)
        -> Citation Verifier ‖ Consistency Checker   (independent, run concurrently)
            -> Confidence Scorer                      (consolidates + ranks)
                -> Judicial Memo                      (synthesis)

Graceful degradation: every agent is isolated. A failure in any non-essential
stage is captured in ``report.errors`` and the pipeline keeps going with what it
has, rather than failing the whole request. The scorer additionally falls back to
deterministic scoring so the report always carries ranked findings.
"""

from __future__ import annotations

import asyncio

from agents import (
    citation_verifier,
    confidence_scorer,
    consistency_checker,
    extractor,
    judicial_memo,
)
from documents import load_documents, split_motion_and_record
from grounding import enforce_grounding
from schemas import (
    CitationFinding,
    Confidence,
    ConsistencyFinding,
    ReportStats,
    ReportStatus,
    ScoredFinding,
    VerificationReport,
)

CASE_NAME = "Rivera v. Harmon Construction Group"


async def run_pipeline() -> VerificationReport:
    documents = load_documents()
    motion_text, record = split_motion_and_record(documents)
    errors: list[str] = []

    # --- Agent 1: extraction (required) -------------------------------------
    # Everything downstream depends on this. If it fails, return a degraded but
    # well-formed report instead of raising.
    try:
        extracted = await asyncio.to_thread(extractor.extract, motion_text)
    except Exception as exc:  # noqa: BLE001 - surface, don't crash
        # Required stage failed: there is NO analysis to report. This is a
        # failure, not a clean "no issues found" result — the status makes that
        # unambiguous to the UI so it can't render a false negative.
        return VerificationReport(
            case_name=CASE_NAME,
            status=ReportStatus.FAILED,
            errors=[f"extractor failed (pipeline cannot proceed): {exc}"],
        )

    # --- Agents 2 & 3: independent, run concurrently, each isolated ----------
    (citation_findings, err_cite), (consistency_findings, err_cons) = await asyncio.gather(
        _safe(citation_verifier.verify, motion_text, extracted.citations, label="citation_verifier"),
        _safe(consistency_checker.check, extracted.factual_claims, record, label="consistency_checker"),
    )
    errors.extend(e for e in (err_cite, err_cons) if e)

    # --- Grounding guardrail: nothing invented ------------------------------
    # Before anything is scored or shown, drop/strip findings whose quotes are not
    # verbatim in the source. Enforced at runtime, not just measured in the eval.
    citation_findings, consistency_findings, ungrounded_removed = enforce_grounding(
        citation_findings, consistency_findings, motion_text, record
    )

    # --- Agent 4: confidence scoring (deterministic fallback) ---------------
    # Only actual flags get scored/ranked. Citations verified as fine stay in the
    # raw citation_findings list for transparency, but they are not "issues".
    flagged_citations = [f for f in citation_findings if f.is_problem]
    try:
        scored: list[ScoredFinding] = await asyncio.to_thread(
            confidence_scorer.score, flagged_citations, consistency_findings
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"confidence_scorer failed; used deterministic fallback: {exc}")
        scored = confidence_scorer.fallback_scoring(flagged_citations, consistency_findings)

    # --- Agent 5: judicial memo ---------------------------------------------
    judicial_memo_text = ""
    try:
        judicial_memo_text = await asyncio.to_thread(judicial_memo.summarize, scored)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"judicial_memo failed: {exc}")

    stats = ReportStats(
        citations_extracted=len(extracted.citations),
        factual_claims_extracted=len(extracted.factual_claims),
        citation_problems=sum(1 for f in citation_findings if f.is_problem),
        consistency_issues=len(consistency_findings),
        high_confidence_flags=sum(1 for s in scored if s.confidence == Confidence.HIGH),
        ungrounded_removed=ungrounded_removed,
    )

    # Extraction succeeded, so we have analysis. If any downstream agent failed,
    # the result is "partial" (real findings, but something is missing), never
    # "completed".
    status = ReportStatus.PARTIAL if errors else ReportStatus.COMPLETED

    return VerificationReport(
        case_name=CASE_NAME,
        status=status,
        citation_findings=citation_findings,
        consistency_findings=consistency_findings,
        scored_findings=scored,
        judicial_memo=judicial_memo_text,
        stats=stats,
        errors=errors,
    )


async def _safe(fn, *args, label: str):
    """Run a blocking agent in a thread; return (result, error_message_or_None)."""
    try:
        return await asyncio.to_thread(fn, *args), None
    except Exception as exc:  # noqa: BLE001
        return [], f"{label} failed: {exc}"
