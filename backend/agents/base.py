"""Shared scaffolding for every agent.

Each agent supplies its own role-specific system prompt; this module appends a
common set of "house rules" that apply to all of them (verbatim quotes, no
fabrication, prefer uncertainty over guessing) and routes the call through the
JSON-validated LLM helper. Centralizing the rules keeps the prompts consistent
and makes the anti-hallucination posture explicit in one place.
"""

from __future__ import annotations

from pydantic import BaseModel

from llm import call_llm_json

HOUSE_RULES = (
    "Operating rules (apply to every response):\n"
    "- Copy any quoted text VERBATIM from the source. Never paraphrase inside quotation marks.\n"
    "- Never invent facts, legal holdings, citations, or document text.\n"
    "- When you cannot determine something with confidence, say so explicitly "
    "(use 'unverifiable' / 'could not verify') rather than guessing.\n"
    "- Be precise and conservative: a false flag is as harmful as a missed one.\n"
    "- Return only the single JSON object required by the schema — no prose, no markdown."
)


def run_agent(system: str, user: str, schema: type[BaseModel]) -> BaseModel:
    """Run one agent step: role prompt + house rules -> schema-validated object."""
    full_system = f"{system}\n\n{HOUSE_RULES}"
    return call_llm_json(full_system, user, schema)
