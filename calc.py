"""Resolve `{...}` Python/math expressions in text (COGO-style feet expressions, etc.)."""

from __future__ import annotations

import ast
import math
import re
from typing import Any


def _eval_expr(node: ast.expr, ns: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, bool)) or node.value is None:
            return node.value
        raise ValueError("Only numeric/bool constants allowed")
    if isinstance(node, ast.Name):
        if node.id not in ns:
            raise NameError(f"Undefined name: {node.id!r}")
        return ns[node.id]
    if isinstance(node, ast.BinOp):
        left = _eval_expr(node.left, ns)
        right = _eval_expr(node.right, ns)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.Mod):
            return left % right
        if isinstance(node.op, ast.Pow):
            return left**right
        if isinstance(node.op, ast.FloorDiv):
            return left // right
        raise ValueError(f"Unsupported binary op: {type(node.op)}")
    if isinstance(node, ast.UnaryOp):
        operand = _eval_expr(node.operand, ns)
        if isinstance(node.op, ast.UAdd):
            return +operand
        if isinstance(node.op, ast.USub):
            return -operand
        raise ValueError(f"Unsupported unary op: {type(node.op)}")
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "math":
                fn = getattr(math, node.func.attr)
                args = [_eval_expr(a, ns) for a in node.args]
                return fn(*args)
        raise ValueError("Only math.* function calls are allowed")
    raise ValueError(f"Unsupported expression: {type(node).__name__}")


def eval_brace_block(code: str) -> Any:
    """
    Evaluate a brace block: assignments and/or a trailing expression, using `math` only.
    Returns the last computed value (last assignment target's value, or last expression).
    """
    stripped = code.strip()
    if not stripped:
        raise ValueError("Empty brace block")

    ns: dict[str, Any] = {"math": math}
    tree = ast.parse(stripped, mode="exec")
    result: Any = None

    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
                raise ValueError("Only simple single-target assignment is allowed")
            target = stmt.targets[0].id
            if target == "math":
                raise ValueError("Cannot assign to 'math'")
            value = _eval_expr(stmt.value, ns)
            ns[target] = value
            result = value
        elif isinstance(stmt, ast.Expr):
            result = _eval_expr(stmt.value, ns)
        else:
            raise ValueError(f"Unsupported statement: {type(stmt).__name__}")

    if result is None:
        raise ValueError("No expression or assignment found")
    return result


def find_brace_spans(text: str) -> list[tuple[int, int, str]]:
    """Return (start, end_exclusive, inner) for each top-level `{...}` span."""
    spans: list[tuple[int, int, str]] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "{":
            depth = 1
            start = i
            j = i + 1
            while j < n and depth:
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                j += 1
            if depth == 0:
                inner = text[start + 1 : j - 1]
                spans.append((start, j, inner))
                i = j
                continue
        i += 1
    return spans


def resolve_calculations_in_text(text: str) -> dict[str, Any]:
    """
    Replace each `{...}` with its evaluated result.
    Returns dict with resolved_text, replacements, errors.
    """
    spans = find_brace_spans(text)
    out = text
    replacements: list[dict[str, Any]] = []
    errors: list[str] = []

    for start, end, inner in reversed(spans):
        try:
            val = eval_brace_block(inner)
            rep = str(val)
            replacements.insert(
                0,
                {"start": start, "end": end, "inner": inner, "value": val, "string": rep},
            )
            out = out[:start] + rep + out[end:]
        except Exception as e:
            errors.append(f"Braces at {start}-{end}: {e}")

    return {
        "resolved_text": out,
        "replacements": replacements,
        "errors": errors,
    }


def strip_code_fence(text: str) -> str:
    """If the model wrapped output in a markdown fence, unwrap it."""
    t = text.strip()
    m = re.match(r"^```(?:\w+)?\s*\n([\s\S]*?)\n```\s*$", t)
    if m:
        return m.group(1).strip()
    return t
