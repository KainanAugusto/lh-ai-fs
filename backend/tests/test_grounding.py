"""Deterministic tests for the grounding guardrail — no LLM, safe for CI.

These lock in the "nothing invented" contract: a finding is only kept if its
quote appears verbatim in the source document.
"""

from grounding import enforce_grounding, normalize, quote_in_source
from schemas import (
    CitationFinding,
    CitationVerdict,
    ConsistencyFinding,
    QuoteAccuracy,
    Severity,
)

SOURCE = 'The report states: "Date of Incident:  March 12, 2021" — filed by Officer Murata.'


def test_normalize_collapses_whitespace_and_dashes():
    assert normalize("A\n\n  B —  C") == "a b - c"


def test_quote_present_verbatim_is_grounded():
    assert quote_in_source("Date of Incident: March 12, 2021", SOURCE) is True


def test_fabricated_quote_is_not_grounded():
    assert quote_in_source("Officer Murata admitted the report was falsified.", SOURCE) is False


def test_empty_or_tiny_quote_is_not_penalized():
    assert quote_in_source("", SOURCE) is True
    assert quote_in_source(None, SOURCE) is True
    assert quote_in_source("March", SOURCE) is True  # too short to verify


def _consistency(quote):
    return ConsistencyFinding(
        msj_claim="claim", contradicting_document="police_report",
        contradicting_quote=quote, severity=Severity.HIGH, reasoning="r",
    )


def _citation(evidence):
    return CitationFinding(
        case_name="Foo v. Bar", citation="1 X 2", proposition="p",
        verdict=CitationVerdict.OVERSTATED, quote_accuracy=QuoteAccuracy.ALTERED,
        is_problem=True, reasoning="r", evidence_quote=evidence,
    )


def test_enforce_grounding_drops_fabricated_contradiction():
    record = {"police_report": SOURCE}
    real = _consistency("Date of Incident: March 12, 2021")
    fake = _consistency("Officer Murata admitted the report was falsified.")
    cits, kept, removed = enforce_grounding([], [real, fake], "", record)
    assert [f.contradicting_quote for f in kept] == ["Date of Incident: March 12, 2021"]
    assert removed == 1


def test_enforce_grounding_strips_fabricated_citation_quote_but_keeps_verdict():
    motion = "The motion argues the hirer is never liable under the doctrine."
    good = _citation("the hirer is never liable")
    bad = _citation("This sentence does not appear in the motion at all.")
    cits, kept, removed = enforce_grounding([good, bad], [], motion, {})
    assert good.evidence_quote == "the hirer is never liable"  # grounded → kept
    assert bad.evidence_quote is None  # fabricated → stripped, verdict retained
    assert bad.verdict == CitationVerdict.OVERSTATED
    assert removed == 1
