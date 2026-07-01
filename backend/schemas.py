"""Structured contracts passed between agents.

Agents never hand each other raw text blobs — they exchange these typed objects.
Every model is also the JSON schema we show the LLM, so the field descriptions do
double duty as prompt instructions. Keep them precise.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Shared enums                                                                 #
# --------------------------------------------------------------------------- #
class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FindingType(str, Enum):
    CITATION = "citation"
    CONSISTENCY = "consistency"


class ReportStatus(str, Enum):
    COMPLETED = "completed"   # pipeline ran fully
    PARTIAL = "partial"       # extraction succeeded but a downstream agent failed
    FAILED = "failed"         # a required stage failed — no analysis was produced


# --------------------------------------------------------------------------- #
# Agent 1 — Citation & Fact Extractor                                          #
# --------------------------------------------------------------------------- #
class Citation(BaseModel):
    case_name: str = Field(description="Full case name, e.g. 'Privette v. Superior Court'.")
    citation: str = Field(description="Reporter citation as written, e.g. '5 Cal.4th 689, 695 (1993)'.")
    proposition: str = Field(
        description="The legal proposition the brief claims this authority supports, in the brief's own framing."
    )
    quoted_text: Optional[str] = Field(
        default=None,
        description="Verbatim direct quote attributed to this authority, if the brief quotes it. Null if no direct quote.",
    )
    location: str = Field(description="Where in the MSJ this appears, e.g. 'Section III.A' or 'footnote 1'.")


class FactClaim(BaseModel):
    claim_text: str = Field(description="A discrete factual assertion the MSJ presents as true.")
    source_location: str = Field(description="Where in the MSJ the claim appears, e.g. 'Statement of Facts ¶4'.")


class ExtractedData(BaseModel):
    """Output of the Extractor. Pure extraction — no judgment yet."""

    citations: list[Citation] = Field(default_factory=list)
    factual_claims: list[FactClaim] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Agent 2 — Citation Verifier                                                  #
# --------------------------------------------------------------------------- #
class CitationVerdict(str, Enum):
    SUPPORTS = "supports"           # authority genuinely supports the proposition as stated
    OVERSTATED = "overstated"       # real authority, but the rule is stretched beyond what it holds
    CONTRADICTS = "contradicts"     # authority actually cuts against the proposition
    UNVERIFIABLE = "unverifiable"   # cannot determine without the source opinion — do NOT guess


class QuoteAccuracy(str, Enum):
    ACCURATE = "accurate"
    ALTERED = "altered"             # words added/removed/changed in a way that shifts meaning
    NOT_A_QUOTE = "not_a_quote"     # no direct quote attached to this citation
    UNVERIFIABLE = "unverifiable"


class CitationFinding(BaseModel):
    case_name: str
    citation: str
    proposition: str
    verdict: CitationVerdict = Field(
        description="Whether the authority supports the stated proposition. Use 'unverifiable' rather than guessing."
    )
    quote_accuracy: QuoteAccuracy = Field(
        description="Accuracy of any direct quote. 'not_a_quote' if the brief did not quote this authority."
    )
    is_problem: bool = Field(description="True if this citation has an integrity issue worth flagging to a reviewer.")
    reasoning: str = Field(description="Concise legal reasoning for the verdict. State uncertainty plainly.")
    evidence_quote: Optional[str] = Field(
        default=None,
        description="Verbatim text copied from the MSJ that grounds this finding. Must appear in the brief.",
    )


class CitationVerificationResult(BaseModel):
    findings: list[CitationFinding] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Agent 3 — Cross-Document Consistency Checker                                 #
# --------------------------------------------------------------------------- #
class ConsistencyFinding(BaseModel):
    msj_claim: str = Field(description="The factual assertion from the MSJ that conflicts with the record.")
    contradicting_document: str = Field(
        description="Which source document contradicts it: police_report, medical_records_excerpt, or witness_statement."
    )
    contradicting_quote: str = Field(
        description="Verbatim text copied from that source document. Must appear in that document."
    )
    severity: Severity = Field(description="How material the contradiction is to the motion's argument.")
    reasoning: str = Field(description="Why these two statements conflict.")


class ConsistencyResult(BaseModel):
    findings: list[ConsistencyFinding] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Agent 4 — Confidence Scorer                                                  #
# --------------------------------------------------------------------------- #
class ScoredFinding(BaseModel):
    finding_type: FindingType
    summary: str = Field(description="One-sentence statement of the issue, reviewer-facing.")
    severity: Severity
    confidence: Confidence = Field(description="How certain the pipeline is that this is a real issue.")
    confidence_score: float = Field(ge=0.0, le=1.0, description="Numeric confidence, 0.0–1.0.")
    reasoning: str = Field(description="Why this confidence level — what supports or undercuts certainty.")
    source: str = Field(description="Origin for traceability, e.g. 'MSJ §III.A' or 'police_report'.")


class ScoringResult(BaseModel):
    scored_findings: list[ScoredFinding] = Field(
        default_factory=list, description="All findings, ranked most to least important."
    )


# --------------------------------------------------------------------------- #
# Agent 5 — Judicial Memo                                                      #
# --------------------------------------------------------------------------- #
class MemoResult(BaseModel):
    memo: str = Field(description="A single tight paragraph synthesizing the top findings, addressed to a judge.")


# --------------------------------------------------------------------------- #
# Final report                                                                 #
# --------------------------------------------------------------------------- #
class ReportStats(BaseModel):
    citations_extracted: int = 0
    factual_claims_extracted: int = 0
    citation_problems: int = 0
    consistency_issues: int = 0
    high_confidence_flags: int = 0
    # Findings the runtime grounding guardrail removed/cleaned because their quote
    # was not verbatim in the source (fabricated evidence). 0 on well-grounded runs.
    ungrounded_removed: int = 0


class VerificationReport(BaseModel):
    case_name: str
    status: ReportStatus = Field(
        default=ReportStatus.COMPLETED,
        description="Whether the pipeline ran fully, partially, or failed before producing analysis.",
    )
    citation_findings: list[CitationFinding] = Field(default_factory=list)
    consistency_findings: list[ConsistencyFinding] = Field(default_factory=list)
    scored_findings: list[ScoredFinding] = Field(default_factory=list)
    judicial_memo: str = ""
    stats: ReportStats = Field(default_factory=ReportStats)
    errors: list[str] = Field(
        default_factory=list,
        description="Non-fatal failures of individual agents, surfaced rather than hidden (graceful degradation).",
    )
