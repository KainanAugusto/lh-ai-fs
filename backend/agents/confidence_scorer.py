"""Agent 4 — Confidence Scorer.

Role: the single place that assigns a calibrated confidence to each finding. It
consolidates and ranks the citation and consistency findings — it does NOT invent
new findings or drop existing ones. Its core calibration principle matches the
product's stance: a finding anchored to a VERBATIM document quote is strong
documentary evidence and rates high; a citation verdict that leans on general
legal knowledge without the actual opinion is weaker and must rate lower.

``fallback_scoring`` is a deterministic backup used if the LLM step fails, so the
report always carries scored findings (graceful degradation).
"""

from __future__ import annotations

import json

from agents.base import run_agent
from schemas import (
    CitationFinding,
    CitationVerdict,
    Confidence,
    ConsistencyFinding,
    FindingType,
    ScoredFinding,
    ScoringResult,
    Severity,
)

SYSTEM = """You are the confidence-scoring layer of a legal verification pipeline. You receive \
findings already produced by two upstream agents — citation-integrity findings and \
cross-document consistency findings. Consolidate, rank, and assign a calibrated confidence to \
EACH finding provided.

Rules:
- Do NOT introduce new findings and do NOT drop findings. Score exactly the ones given.
- For each finding output: finding_type ('citation' or 'consistency'); a one-sentence \
reviewer-facing summary; severity; confidence and a numeric confidence_score (0.0–1.0); \
reasoning for the confidence; and source (case name / MSJ location, or the contradicting document).

Calibration — base confidence on the strength of the EVIDENCE, not on how serious the claim sounds:
- A consistency finding anchored to a VERBATIM quote from a source document is first-hand \
documentary evidence — it earns HIGH confidence.
- A citation finding that depends on general legal knowledge without the actual opinion text is \
weaker. If the upstream verdict was 'unverifiable', confidence MUST be low. If a cited case may \
not exist or cannot be confirmed, do not assign high confidence.
- Never inflate confidence. Tie every confidence judgment to the evidence actually provided.

Rank scored_findings from most to least important (roughly severity × confidence)."""


def score(
    citation_findings: list[CitationFinding],
    consistency_findings: list[ConsistencyFinding],
) -> list[ScoredFinding]:
    payload = {
        "citation_findings": [f.model_dump(mode="json") for f in citation_findings],
        "consistency_findings": [f.model_dump(mode="json") for f in consistency_findings],
    }
    user = "Findings to score and rank:\n" + json.dumps(payload, indent=2)
    result: ScoringResult = run_agent(SYSTEM, user, ScoringResult)
    return result.scored_findings


# --------------------------------------------------------------------------- #
# Deterministic fallback (used only if the scoring LLM call fails)             #
# --------------------------------------------------------------------------- #
_SEVERITY_TO_CONF = {
    Severity.HIGH: (Confidence.HIGH, 0.85),
    Severity.MEDIUM: (Confidence.MEDIUM, 0.6),
    Severity.LOW: (Confidence.LOW, 0.4),
}

_VERDICT_TO_SCORE = {
    CitationVerdict.CONTRADICTS: (Confidence.HIGH, 0.8, Severity.HIGH),
    CitationVerdict.OVERSTATED: (Confidence.MEDIUM, 0.55, Severity.MEDIUM),
    CitationVerdict.UNVERIFIABLE: (Confidence.LOW, 0.3, Severity.LOW),
    CitationVerdict.SUPPORTS: (Confidence.LOW, 0.3, Severity.LOW),
}


def fallback_scoring(
    citation_findings: list[CitationFinding],
    consistency_findings: list[ConsistencyFinding],
) -> list[ScoredFinding]:
    scored: list[ScoredFinding] = []

    for f in citation_findings:
        if not f.is_problem:
            continue
        conf, cscore, sev = _VERDICT_TO_SCORE.get(f.verdict, (Confidence.LOW, 0.3, Severity.LOW))
        scored.append(
            ScoredFinding(
                finding_type=FindingType.CITATION,
                summary=f"{f.case_name}: cited authority {f.verdict.value} for the stated proposition.",
                severity=sev,
                confidence=conf,
                confidence_score=cscore,
                reasoning=f.reasoning,
                source=f"{f.case_name} ({f.citation})",
            )
        )

    for f in consistency_findings:
        conf, cscore = _SEVERITY_TO_CONF.get(f.severity, (Confidence.MEDIUM, 0.6))
        scored.append(
            ScoredFinding(
                finding_type=FindingType.CONSISTENCY,
                summary=f"MSJ claim contradicted by {f.contradicting_document}: {f.msj_claim}",
                severity=f.severity,
                confidence=conf,
                confidence_score=cscore,
                reasoning=f.reasoning,
                source=f.contradicting_document,
            )
        )

    scored.sort(key=lambda s: s.confidence_score, reverse=True)
    return scored
