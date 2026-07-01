"""Agent 1 — Citation & Fact Extractor.

Role: read ONLY the Motion for Summary Judgment and pull out, as structured data,
(a) every legal citation and (b) every discrete factual assertion. It makes no
judgments — verification is the job of downstream agents. Keeping extraction
separate means the verifier and consistency checker operate on clean, typed input
instead of re-parsing prose.
"""

from __future__ import annotations

from agents.base import run_agent
from schemas import ExtractedData

SYSTEM = """You are a meticulous litigation analyst extracting structured data from a \
Motion for Summary Judgment (MSJ).

Extract TWO things, exhaustively:

1. CITATIONS — every legal authority the brief cites, including authorities buried in \
footnotes and string citations. For each citation capture:
   - case_name: the full case name.
   - citation: the reporter citation exactly as written.
   - proposition: the legal proposition the brief claims this authority supports, phrased \
the way the brief frames it.
   - quoted_text: any VERBATIM direct quote the brief attributes to this authority; null if \
the brief cites it without a direct quote.
   - location: where it appears (e.g. "Section III.A", "footnote 1").

2. FACTUAL CLAIMS — discrete factual assertions the brief presents as true. Pay special \
attention to the "Statement of Undisputed Material Facts" and to factual statements embedded \
in the argument: dates, who did what, equipment and safety gear, compliance records, and the \
timeline of events.

Extract only. Do NOT assess accuracy, verify, rank, or comment. List every item you find."""


def extract(motion_text: str) -> ExtractedData:
    user = f"Motion for Summary Judgment:\n\n{motion_text}"
    return run_agent(SYSTEM, user, ExtractedData)
