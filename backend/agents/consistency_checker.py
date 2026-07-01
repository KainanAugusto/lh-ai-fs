"""Agent 3 — Cross-Document Consistency Checker.

Role: take the factual claims the Extractor pulled from the MSJ (structured input,
not raw prose) and check them against the supporting record — police report,
medical records, witness statement. It flags assertions the record contradicts or
materially undercuts, always anchoring each flag to a verbatim quote from the
source document so the finding is auditable.
"""

from __future__ import annotations

import json

from agents.base import run_agent
from schemas import ConsistencyFinding, ConsistencyResult, FactClaim

SYSTEM = """You are a cross-document consistency auditor in litigation.

You are given (1) factual assertions made in a Motion for Summary Judgment (MSJ) and (2) the \
full text of the supporting record: a police report, medical records, and a witness statement. \
Find places where the MSJ's factual assertions are CONTRADICTED by, or materially inconsistent \
with, the record.

For each contradiction report:
- msj_claim: the MSJ assertion at issue.
- contradicting_document: the record file that conflicts — exactly one of: police_report, \
medical_records_excerpt, witness_statement.
- contradicting_quote: the exact text from that document, copied VERBATIM.
- severity: how damaging the discrepancy is to the motion's argument (low / medium / high).
- reasoning: why the two statements conflict.

Flag genuine factual contradictions and material factual discrepancies (wrong dates, wrong \
facts about who did what, contradicted claims about equipment or conduct). Do NOT flag mere \
differences in wording or style. If a claim cannot be checked against the record, do NOT \
invent a contradiction."""


def check(factual_claims: list[FactClaim], record: dict[str, str]) -> list[ConsistencyFinding]:
    claims_json = json.dumps([c.model_dump() for c in factual_claims], indent=2)
    record_text = "\n\n".join(f"=== {name} ===\n{text}" for name, text in record.items())
    user = (
        f"MSJ factual assertions to check:\n{claims_json}\n\n"
        f"Supporting record documents:\n\n{record_text}"
    )
    result: ConsistencyResult = run_agent(SYSTEM, user, ConsistencyResult)
    return result.findings
