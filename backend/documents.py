"""Loading and organizing the case file documents."""

from __future__ import annotations

from pathlib import Path

DOCUMENTS_DIR = Path(__file__).parent / "documents"

# The document under scrutiny. Everything else is the evidentiary record we check
# the motion's factual assertions against.
MSJ_KEY = "motion_for_summary_judgment"


def load_documents() -> dict[str, str]:
    """Load every .txt in the documents directory, keyed by filename stem."""
    return {p.stem: p.read_text() for p in sorted(DOCUMENTS_DIR.glob("*.txt"))}


def split_motion_and_record(documents: dict[str, str]) -> tuple[str, dict[str, str]]:
    """Separate the Motion for Summary Judgment from the supporting record.

    Returns ``(motion_text, record)`` where ``record`` maps each evidence
    document name to its text. Raises if the motion is missing.
    """
    if MSJ_KEY not in documents:
        raise FileNotFoundError(f"Expected '{MSJ_KEY}.txt' in {DOCUMENTS_DIR}")
    motion_text = documents[MSJ_KEY]
    record = {name: text for name, text in documents.items() if name != MSJ_KEY}
    return motion_text, record
