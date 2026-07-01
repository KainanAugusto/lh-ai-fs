"""Agent 5 — Judicial Memo.

Role: synthesize the top-ranked findings into a single tight paragraph addressed
to a judge. It is strictly a synthesis step: it may only restate issues already
established in the scored findings — no new facts, cases, or conclusions. This
keeps the memo as grounded as the evidence beneath it.
"""

from __future__ import annotations

import json

from agents.base import run_agent
from schemas import MemoResult, ScoredFinding

SYSTEM = """You are a neutral judicial-clerk assistant. Using ONLY the findings provided, write a \
SINGLE tight paragraph for a judge that summarizes the most serious, highest-confidence problems \
identified in the moving party's Motion for Summary Judgment.

Requirements:
- Use only what is in the findings. Do NOT introduce any fact, case, date, or conclusion that is \
not present in them.
- Be concrete: name the specific issues (e.g. the contradicted incident date, the overstated \
holding, the contradicted factual assertion).
- Neutral, measured tone. Identify issues for the court's attention; do not advocate for either party.
- One paragraph. No headings, no bullet list."""


def summarize(scored_findings: list[ScoredFinding]) -> str:
    if not scored_findings:
        return "No findings were produced by the pipeline; no memo generated."
    top = [s.model_dump(mode="json") for s in scored_findings[:6]]
    user = "Top findings (ranked, most important first):\n" + json.dumps(top, indent=2)
    result: MemoResult = run_agent(SYSTEM, user, MemoResult)
    return result.memo
