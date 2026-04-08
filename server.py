#!/usr/bin/env python3
"""MCP server: fine-tuned OpenAI (Responses API) + `{...}` math resolution."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

import os
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from openai import OpenAI

from calc import resolve_calculations_in_text, strip_code_fence


def _env_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    if v is None or not v.strip():
        return default
    return int(v)


def _resolve_finetuned_model(model: str | None) -> str:
    """
    Model id from the tool argument, else OPENAI_FINETUNED_MODEL in the environment.
    Use the full id from OpenAI (often starts with ft:).
    """
    explicit = (model or "").strip()
    if explicit:
        return explicit
    from_env = (os.environ.get("OPENAI_FINETUNED_MODEL") or "").strip()
    if from_env:
        return from_env
    raise RuntimeError(
        "No model set: pass `model` on the tool, or set OPENAI_FINETUNED_MODEL in `.env`."
    )


DEFAULT_SYSTEM_PROMPT = """Convert legal description calls into COGO compact encoding.

Output ONLY the encoded line(s), exactly as specified. Preserve all numbers, bearings, punctuation, and ordering. No extra commentary.

Units: All COGO distances are in feet. Do not perform unit conversions. If a distance is provided in non-foot surveying units (rod/pole, chain, link, vara, furlong, etc.), output the distance as a feet-expression in curly braces using only Python math (simple multiplication), e.g. {feet = <value> * <feet_per_unit>} and use that feet value in the encoded line.

Allowed unit factors (for expressions only):

1 rod = 1 pole = 16.5 ft
1 chain = 66 ft
1 link = 0.66 ft
1 vara = 2.7777 ft
1 furlong = 660 ft

Curves / chord-based distances (NO numeric solving): If a curve's distance is given as a chord length/distance, do not compute arc length. Instead output python code in curly braces to be evaluated, using only the math library:
{arc_length = 2 * r * math.asin(chord_length / (2 * r))}"""


def _transport_security() -> TransportSecuritySettings | None:
    """
    FastMCP enables DNS-rebinding checks for localhost; nginx forwards Host as the public
    hostname/IP, which otherwise returns 421 Invalid Host. Set FASTMCP_TRUST_PROXY=1 behind nginx.
    Or set FASTMCP_ALLOWED_HOSTS=host1,host2 (comma-separated IPs or hostnames).
    """
    trust = os.environ.get("FASTMCP_TRUST_PROXY", "").lower() in (
        "1",
        "true",
        "yes",
    )
    if trust:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)

    extra_raw = os.environ.get("FASTMCP_ALLOWED_HOSTS", "").strip()
    if not extra_raw:
        return None

    extras = [h.strip() for h in extra_raw.split(",") if h.strip()]
    if not extras:
        return None

    allowed_hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    allowed_origins = [
        "http://127.0.0.1:*",
        "http://localhost:*",
        "http://[::1]:*",
    ]
    for h in extras:
        allowed_hosts.append(h)
        allowed_hosts.append(f"{h}:*")
        allowed_origins.append(f"http://{h}:*")
        allowed_origins.append(f"https://{h}:*")

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )


mcp = FastMCP(
    "cogo-finetuned",
    instructions=(
        "COGO fine-tuned model bridge: call the fine-tuned OpenAI model with context, "
        "then resolve `{...}` Python/math expressions in the result (and optionally in context)."
    ),
    host=os.environ.get("FASTMCP_HOST", "127.0.0.1"),
    port=_env_int("FASTMCP_PORT", 8880),
    streamable_http_path=os.environ.get(
        "FASTMCP_STREAMABLE_HTTP_PATH", "/mcp/cogo"
    ),
    transport_security=_transport_security(),
)


def _client() -> OpenAI:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Set it in the environment for the MCP server process."
        )
    return OpenAI(api_key=key)


def _responses_create(
    model: str,
    system_prompt: str,
    user_content: str,
    max_output_tokens: int = 2048,
) -> str:
    client = _client()
    response = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        max_output_tokens=max_output_tokens,
        temperature=0.0,
        top_p=1.0,
    )
    return (response.output_text or "").strip()


@mcp.tool()
def request_finetuned_model(
    user_message: str,
    model: str | None = None,
    system_prompt: str | None = None,
    extra_context: str | None = None,
    max_output_tokens: int = 2048,
) -> dict[str, Any]:
    """
    Send a request to your fine-tuned model via the OpenAI Responses API.

    Use `extra_context` for local/reference material you want included in the user turn
    (e.g. prior lines, units, project notes). It is combined with `user_message` in one user message.

    Parameters:
        model: Fine-tuned model id (e.g. ft:gpt-4.1-nano-...:org:project:id). If omitted, uses OPENAI_FINETUNED_MODEL from the environment.
        user_message: Main instruction or text to encode.
        system_prompt: Optional override; defaults to the built-in COGO compact-encoding prompt.
        extra_context: Optional context prepended to the user message (after a separator).
        max_output_tokens: Cap for the model output.
    """
    mid = _resolve_finetuned_model(model)
    sys_p = system_prompt if system_prompt is not None else DEFAULT_SYSTEM_PROMPT
    if extra_context and extra_context.strip():
        user_content = (
            f"{extra_context.strip()}\n\n---\n\n{user_message.strip()}"
        )
    else:
        user_content = user_message.strip()

    raw = _responses_create(
        mid, sys_p, user_content, max_output_tokens=max_output_tokens
    )
    return {
        "output_text": raw,
        "model_used": mid,
        "system_prompt_used": sys_p,
    }


@mcp.tool()
def resolve_calculations_in_text_tool(text: str) -> dict[str, Any]:
    """
    Find `{...}` blocks and evaluate them as restricted Python math (see calc.py).

    Supports +, -, *, /, **, %, //, unary +/-, and `math.*` calls (sin, cos, asin, etc.).
    Variables must be defined inside the same block before use, or will error.

    Returns resolved_text, replacements metadata, and any evaluation errors for blocks that failed.
    """
    return resolve_calculations_in_text(text)


@mcp.tool()
def complete_with_calculations(
    user_message: str,
    model: str | None = None,
    system_prompt: str | None = None,
    extra_context: str | None = None,
    preprocess_context: bool = True,
    postprocess_output: bool = True,
    strip_markdown_fence: bool = True,
    max_output_tokens: int = 2048,
) -> dict[str, Any]:
    """
    End-to-end: optionally resolve `{...}` in `extra_context`, call the fine-tuned model,
    then resolve `{...}` in the model output.

    Set `preprocess_context` to evaluate math in context before the API call (when context
    contains feet expressions you want expanded before encoding). Set `postprocess_output`
    to evaluate math in the model reply (typical for COGO output with brace expressions).

    If `model` is omitted, OPENAI_FINETUNED_MODEL from the environment is used.
    """
    mid = _resolve_finetuned_model(model)
    sys_p = system_prompt if system_prompt is not None else DEFAULT_SYSTEM_PROMPT
    ctx = extra_context
    ctx_notes: dict[str, Any] = {}
    if ctx and ctx.strip() and preprocess_context:
        pre = resolve_calculations_in_text(ctx)
        ctx = pre["resolved_text"]
        ctx_notes = {
            "preprocessed_context": ctx,
            "preprocess_replacements": pre["replacements"],
            "preprocess_errors": pre["errors"],
        }
    elif ctx and ctx.strip():
        ctx_notes = {"preprocessed_context": ctx.strip(), "preprocess_errors": []}

    if ctx and str(ctx).strip():
        user_content = f"{str(ctx).strip()}\n\n---\n\n{user_message.strip()}"
    else:
        user_content = user_message.strip()

    raw = _responses_create(
        mid, sys_p, user_content, max_output_tokens=max_output_tokens
    )
    display = strip_code_fence(raw) if strip_markdown_fence else raw

    out: dict[str, Any] = {
        "model_used": mid,
        "raw_output_text": raw,
        "model_response_before_calcs": display,
        "preprocess": ctx_notes,
    }

    if postprocess_output:
        post = resolve_calculations_in_text(display)
        out["final_text"] = post["resolved_text"]
        out["postprocess_replacements"] = post["replacements"]
        out["postprocess_errors"] = post["errors"]
    else:
        out["final_text"] = display
        out["postprocess_replacements"] = []
        out["postprocess_errors"] = []

    return out


if __name__ == "__main__":
    # Default: Streamable HTTP (MCP over HTTP). Use `python server.py stdio` for local stdio debugging.
    transport = os.environ.get("MCP_TRANSPORT", "streamable-http")
    if len(sys.argv) > 1:
        transport = sys.argv[1]
    if transport not in ("stdio", "sse", "streamable-http"):
        print(
            f"Unknown transport {transport!r}. Use: stdio | sse | streamable-http",
            file=sys.stderr,
        )
        sys.exit(1)
    mcp.run(transport=transport)  # type: ignore[arg-type]
