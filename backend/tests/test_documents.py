"""Deterministic tests for document loading/splitting — no LLM, safe for CI."""

import pytest

from documents import MSJ_KEY, load_documents, split_motion_and_record


def test_loads_all_four_case_documents():
    docs = load_documents()
    assert set(docs) == {
        "motion_for_summary_judgment",
        "police_report",
        "medical_records_excerpt",
        "witness_statement",
    }
    assert all(text.strip() for text in docs.values())


def test_split_separates_motion_from_record():
    motion, record = split_motion_and_record(load_documents())
    assert "MOTION FOR SUMMARY JUDGMENT" in motion.upper()
    assert MSJ_KEY not in record
    assert set(record) == {"police_report", "medical_records_excerpt", "witness_statement"}


def test_split_raises_when_motion_missing():
    with pytest.raises(FileNotFoundError):
        split_motion_and_record({"police_report": "x"})
