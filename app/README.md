# The chat app

A working reference chat app — run it with:

```
uvicorn app.main:app --reload
```

Then open http://127.0.0.1:8000 and ask it something about `oidemo` or
`oidemo_notable` (see the [main README](../README.md#data-available-via-splunk-mcp)
for what's in them). It needs everything from `.env` filled in (`python
scripts/check_env.py` first if unsure) — no separate MCP config file needed,
it connects directly.

## How it's built

- **`main.py`** — FastAPI app. `GET /` serves `static/index.html`; `GET
  /config` returns `{"providers": [...], "default_provider": "..."}` — only
  providers with an API key set in `.env` are listed; `POST /chat` takes
  `{"message": "...", "conversation_id": "...", "provider": "..."}` (provider
  optional, falls back to `LLM_PROVIDER`) and returns `{"reply": "..."}`. An
  unconfigured `provider` is rejected with `400`, not a crash.
- **`static/index.html`** — a minimal HTML/JS chat page, no build step. A
  provider dropdown in the header is populated from `/config` (so it never
  offers a provider with no key) and sent with every message, letting you
  switch anthropic/openai/gemini per turn without restarting the app.
  Generates a random `conversation_id` once per page load and sends it with
  every message, so a reload starts a fresh Galileo session.
- **`mcp_client.py`** — connects to the Splunk MCP server at
  `<SPLUNK_INSTANCE_URL>:8089/services/mcp` (see `scripts/setup_mcp.py` for
  how that URL is derived) using the `mcp` Python SDK, authenticating with
  `SPLUNK_MCP_TOKEN`. Splunk's management port uses a self-signed cert by
  default, so TLS verification is disabled for this one connection.
- **`agent.py`** — one tool-calling loop per `LLM_PROVIDER`
  (anthropic/openai/gemini): call the LLM with the Splunk MCP tools on offer,
  execute whatever tool call it asks for, feed the result back, repeat until
  it returns a final answer (capped at 8 rounds — `oidemo_notable` is
  `sourcetype=stash`, where `severity` is embedded as literal uppercase text
  like `severity=HIGH` rather than a normalized field, so the model
  sometimes needs a few rounds to rediscover the right query shape; the
  system prompt now warns it up front, but the cap has headroom regardless).
  The LLM calls run in-line rather than via `asyncio.to_thread` — Galileo's
  logger lookup silently loses the active trace inside a thread-pool worker,
  so this briefly blocks the event loop as a deliberate tradeoff for a
  single-user demo.
- **`observability.py`** — OpenAI calls go through Galileo's native
  `galileo.openai` wrapper (auto-logs, no decorator needed), passing
  `name="openai"` so its spans are labeled by provider instead of the
  wrapper's generic default (`"llm"`) — that kwarg is captured by Galileo
  for the span label and stripped before the real API call, never sent to
  OpenAI. Anthropic and Gemini calls, and every Splunk MCP tool call, use
  Galileo's `@log(span_type=..., name=...)` decorator instead, since no
  native wrapper exists for those — `name="anthropic"`/`name="gemini"` for
  the same reason (otherwise `@log` defaults the span name to the Python
  function name, e.g. `call_anthropic`). `run_traced_turn` maps each
  `conversation_id` to a Galileo session (created once via `start_session`,
  cached), explicitly calls `start_trace(input=user_message)` /
  `conclude(output=result)` so the trace shows the real question and answer
  rather than an arbitrary child span's input/output, and wraps it all in
  one `galileo_context(session_id=...)` so every LLM/tool span from that
  turn lands in one trace, and every turn in the conversation lands in one
  session.

If you're building your own version instead of using this one, this is the
same build order: MCP client → LLM adapter/agent loop → Galileo tracing →
chat UI.
