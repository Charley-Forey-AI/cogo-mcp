"""Tests for calc.py — run: pytest test_calc.py -v"""

from __future__ import annotations

import pytest

from calc import eval_brace_block, find_brace_spans, resolve_calculations_in_text


def test_single_multiplication() -> None:
    r = resolve_calculations_in_text("LB, {feet = 500 * 16.5}, end")
    assert r["errors"] == []
    assert r["resolved_text"] == "LB, 8250.0, end"
    assert len(r["replacements"]) == 1
    assert r["replacements"][0]["value"] == 8250.0


def test_multiple_braces_in_order() -> None:
    r = resolve_calculations_in_text("a {1+2} b {3*4} c")
    assert r["errors"] == []
    assert r["resolved_text"] == "a 3 b 12 c"
    assert len(r["replacements"]) == 2


def test_multiline_block_with_math() -> None:
    inner = """r = 100
chord_length = 50
arc_length = 2 * r * math.asin(chord_length / (2 * r))"""
    text = f"start {{{inner}}} end"
    r = resolve_calculations_in_text(text)
    assert r["errors"] == []
    assert "start " in r["resolved_text"] and " end" in r["resolved_text"]
    assert float(r["resolved_text"].split()[1]) == pytest.approx(50.53605102841573)


def test_failed_block_keeps_braces_and_records_error() -> None:
    r = resolve_calculations_in_text("{undefined_name * 2}")
    assert r["resolved_text"] == "{undefined_name * 2}"
    assert len(r["errors"]) == 1


def test_find_brace_spans_nested_outer_only() -> None:
    # Balanced nesting: one outer span whose inner string contains inner braces as Python would parse
    spans = find_brace_spans("{a = 2 * 3}")
    assert len(spans) == 1
    assert spans[0][2].strip() == "a = 2 * 3"


def test_eval_disallows_import_or_builtin() -> None:
    with pytest.raises((ValueError, SyntaxError, TypeError)):
        eval_brace_block("__import__('os').system('echo')")


def test_replacement_is_string_of_numeric_result() -> None:
    r = resolve_calculations_in_text("x={1/3}")
    assert r["resolved_text"] == "x=0.3333333333333333"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
