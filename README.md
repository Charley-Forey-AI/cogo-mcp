# cogo-mcp

A [Model Context Protocol](https://modelcontextprotocol.io/) server that forwards requests to a **fine-tuned OpenAI** model (Responses API), then evaluates **`{...}` math blocks** in the model output (and optionally in supplied context)—for COGO-style legal-description encoding with feet expressions and `math.*` functions.

## Transport: Streamable HTTP (default)

This server runs **MCP over Streamable HTTP** by default (not stdio).

| Setting | Environment variable | Default |
|--------|----------------------|---------|
| Bind address | `FASTMCP_HOST` | `127.0.0.1` |
| Port | `FASTMCP_PORT` | `8000` |
| MCP endpoint path | `FASTMCP_STREAMABLE_HTTP_PATH` | `/mcp` |
| Transport selection | `MCP_TRANSPORT` | `streamable-http` |

**MCP URL** (what clients use to connect):

`http://<FASTMCP_HOST>:<FASTMCP_PORT><FASTMCP_STREAMABLE_HTTP_PATH>`

Example: `http://127.0.0.1:8000/mcp`

To listen on all interfaces (Docker, LAN, reverse proxy on the same host), set `FASTMCP_HOST=0.0.0.0`.

### Run

```bash
cd c:\Users\cforey\Desktop\cogo-mcp
pip install -r requirements.txt
set OPENAI_API_KEY=sk-...
python server.py
```

Optional: `python server.py stdio` or `python server.py sse` for other transports (local debugging or legacy clients).

### Cursor / client configuration

Point your MCP client at the **Streamable HTTP** URL above. Exact JSON shape depends on the client; for Cursor, use the MCP settings UI or a config that supports **remote HTTP MCP** with that URL.

**Secrets:** pass `OPENAI_API_KEY` via the process environment (or your orchestrator’s secret store), not committed files.

## Tools

| Tool | Purpose |
|------|---------|
| `request_finetuned_model` | Call the fine-tuned model with optional `extra_context` and optional custom `system_prompt`. |
| `resolve_calculations_in_text_tool` | Evaluate `{...}` expressions only (no OpenAI call). |
| `complete_with_calculations` | Preprocess context, call the model, postprocess output (typical end-to-end flow). |

Expression rules live in `calc.py`: assignments and simple math, **`math` module only** for calls (`sin`, `cos`, `asin`, …).

### Verifying `calc.py`

Run automated tests:

```bash
pip install -r requirements.txt
pytest test_calc.py -v
```

Your **Samples for Testing** files are mostly already-encoded COGO lines (`LB …, distance,, …`) with **no `{...}` blocks**, so `calc.py` will not change them unless you add brace expressions (e.g. unit conversions) for evaluation.

## Required environment

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key for Responses API calls. |

## What you might add next

These are **not** implemented here; add them if your deployment needs them:

1. **TLS termination** — Put **nginx**, **Caddy**, or **Traefik** in front with HTTPS; clients then use `https://host/mcp`.
2. **Authentication** — FastMCP supports OAuth / bearer patterns; expose MCP only on a private network or add auth at the reverse proxy or application layer.
3. **OpenAI response streaming** — The server currently uses the Responses API **non-streaming** (`output_text`). If you need token streaming from OpenAI, extend `_responses_create` to stream and decide how that maps to MCP tools.
4. **Health checks** — Add a small `/health` route (e.g. Starlette) or rely on proxy checks for process liveness.
5. **Logging / metrics** — Structured logs and request IDs for production.
6. **Resource limits** — `max_output_tokens` is per-call; add rate limiting or quotas if exposed broadly.

## Project layout

| File | Role |
|------|------|
| `server.py` | FastMCP app, tools, Streamable HTTP entrypoint |
| `calc.py` | Safe `{...}` evaluation |
| `requirements.txt` | Python dependencies |
