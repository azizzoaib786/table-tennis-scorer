"""Unit tests for pair-line parsing used by the bulk-pairings endpoint.

These are pure string tests — no FastAPI, no AWS.
"""
import pytest

from app.main import _parse_pair_line


def test_singles_simple_vs():
    r = _parse_pair_line("Alice vs Bob")
    assert r == {"match_type": "singles", "a_names": ["Alice"], "b_names": ["Bob"]}


def test_singles_dash_separator():
    r = _parse_pair_line("Alice - Bob")
    assert r["match_type"] == "singles"
    assert r["a_names"] == ["Alice"]
    assert r["b_names"] == ["Bob"]


def test_singles_pipe_separator():
    r = _parse_pair_line("Alice | Bob")
    assert r["match_type"] == "singles"


def test_singles_case_insensitive_vs():
    for sep in ("VS", "Vs", "vs.", "V", "v."):
        assert _parse_pair_line(f"Alice {sep} Bob")["match_type"] == "singles"


def test_doubles_plus_separator():
    r = _parse_pair_line("Alice + Amy vs Bob + Ben")
    assert r["match_type"] == "doubles"
    assert r["a_names"] == ["Alice", "Amy"]
    assert r["b_names"] == ["Bob", "Ben"]


def test_doubles_ampersand_separator():
    r = _parse_pair_line("Alice & Amy vs Bob & Ben")
    assert r["match_type"] == "doubles"


def test_doubles_slash_separator():
    r = _parse_pair_line("Alice / Amy vs Bob / Ben")
    assert r["match_type"] == "doubles"


def test_multi_word_names_preserved():
    r = _parse_pair_line("Mary Jane vs Peter Parker")
    assert r["a_names"] == ["Mary Jane"]
    assert r["b_names"] == ["Peter Parker"]


def test_extra_whitespace_ignored():
    r = _parse_pair_line("   Alice    vs   Bob   ")
    assert r["a_names"] == ["Alice"]
    assert r["b_names"] == ["Bob"]


def test_comment_line_skipped():
    assert _parse_pair_line("# this is a comment") is None


def test_empty_line_skipped():
    assert _parse_pair_line("") is None
    assert _parse_pair_line("   ") is None


def test_missing_side_returns_none():
    assert _parse_pair_line("Alice vs ") is None
    assert _parse_pair_line(" vs Bob") is None


def test_no_separator_returns_none():
    assert _parse_pair_line("Alice Bob") is None


def test_mixed_sides_singles_vs_doubles_rejected():
    # One side has 1 name, the other has 2 → invalid.
    assert _parse_pair_line("Alice vs Bob + Ben") is None
    assert _parse_pair_line("Alice + Amy vs Bob") is None


def test_three_players_per_side_rejected():
    assert _parse_pair_line("A + B + C vs D + E + F") is None
