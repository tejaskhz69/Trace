"""Tests for the AI Trainer's pure validation logic.

Only `validate_question` is pure and testable without a network call --
`ask()` calls Gemini directly, same as `vision.recognize()`, and this repo
has no HTTP/DB test harness to mock that through (see other test files: they
all exercise pure functions directly).
"""

from __future__ import annotations

import pytest

from app.services.chat import MAX_QUESTION_LEN, validate_question


def test_trims_whitespace():
    assert validate_question("  how does trace work?  ") == "how does trace work?"


def test_rejects_empty_question():
    with pytest.raises(ValueError):
        validate_question("")


def test_rejects_whitespace_only_question():
    with pytest.raises(ValueError):
        validate_question("   ")


def test_rejects_question_over_max_length():
    with pytest.raises(ValueError):
        validate_question("a" * (MAX_QUESTION_LEN + 1))


def test_accepts_question_at_max_length():
    q = "a" * MAX_QUESTION_LEN
    assert validate_question(q) == q
