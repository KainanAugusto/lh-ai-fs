"""Runtime grounding guardrail — enforces "nothing invented".

Every flag the pipeline surfaces must be backed by text that appears VERBATIM in
the source documents. The eval measures this after the fact (hallucination rate);
this module enforces it live, before the report is assembled:

- a cross-document finding whose contradicting quote is not actually in the cited
  record document is DROPPED — a fabricated contradiction is worse than a miss; and
- a citation finding whose evidence quote is not in the motion has that quote
  stripped — the legal verdict may stand on its reasoning, but we will not show a
  fabricated quote.

The normalize / quote-match logic is shared with the eval (``evals/metrics.py``
imports ``normalize`` from here) so "grounded" means the same thing in both places.
"""

from __future__ import annotations

import re
from typing import Optional

# Normalize the unicode dashes/quotes an LLM may emit back to ASCII so a verbatim
# quote still matches the source text.
_DASHES = ["‐", "‑", "‒", "–", "—", "―"]


def normalize(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    for dash in _DASHES:
        text = text.replace(dash, "-")
    text = text.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip()


def quote_in_source(quote: Optional[str], source: str) -> bool:
    """Is a verbatim quote actually present in the source document?

    Empty or very short quotes are treated as present (nothing meaningful to
    verify — we do not want to drop a finding over a 3-character fragment).
    """
    if not quote or not quote.strip():
        return True
    norm_quote = normalize(quote)
    if len(norm_quote) < 8:
        return True
    return norm_quote in normalize(source)


def enforce_grounding(citation_findings, consistency_findings, motion_text, record):
    """Remove or clean findings whose quotes are not grounded in the source.

    Returns ``(citation_findings, kept_consistency_findings, removed_count)``.
    Mutates citation findings in place to strip a fabricated ``evidence_quote``.
    """
    removed = 0

    kept_consistency = []
    for f in consistency_findings:
        source = record.get(f.contradicting_document, "")
        if quote_in_source(f.contradicting_quote, source):
            kept_consistency.append(f)
        else:
            removed += 1  # fabricated contradiction — drop it entirely

    for f in citation_findings:
        if f.evidence_quote and not quote_in_source(f.evidence_quote, motion_text):
            f.evidence_quote = None  # strip the fabricated quote, keep the verdict
            removed += 1

    return citation_findings, kept_consistency, removed
