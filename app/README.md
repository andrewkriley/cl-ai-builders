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
- **`agent.py`** — a supervisor/classifier/worker structure, not just a flat
  loop:
  - A **supervisor** agent span (`agent_type="supervisor"`) wraps the whole
    turn.
  - A **classifier** agent span (`agent_type="classifier"`) inside it picks
    a category — `security`, `infra`, or `general` — via a fast keyword
    heuristic (not an LLM call, to keep this deterministic and free of
    extra API cost/latency). That category selects a scoped system prompt
    (e.g. the security prompt knows `oidemo_notable` is `sourcetype=stash`
    with `severity` embedded as literal uppercase text like `severity=HIGH`,
    not a normalized field) and a scoped tool subset — the `saia_*` tools
    are excluded from every category, since they reliably return server
    errors on this instance (confirmed).
  - A **worker** agent span (`agent_type="react"`) then runs the actual
    tool-calling loop for `LLM_PROVIDER` (anthropic/openai/gemini) with that
    scoped prompt/tools: call the LLM, execute whatever tool call it asks
    for, feed the result back, repeat until it returns a final answer.

  In Galileo this renders as `trace -> agent(supervisor) ->
  [agent(classifier), agent(react) -> [llm, tool, llm, ...]]` (verified
  against the real backend).

  Two independent safety nets inside each worker loop, since a real LLM can
  get stuck: `MAX_TURNS` caps the round count (8), and a repeated-call guard
  stops immediately if the model calls the exact same tool with the exact
  same arguments twice in a row — a common real loop failure mode, faster to
  catch than waiting for the cap (verified with mocked responses: trips
  after exactly 2 calls, not 8). Either one tripping sets `status_code=1` on
  the worker's (and supervisor's) agent span when it concludes, so a stuck
  turn is visible/filterable in Galileo instead of just a silent fallback
  message in the chat.

  The LLM calls run in-line rather than via `asyncio.to_thread` — Galileo's
  logger lookup silently loses the active trace inside a thread-pool worker,
  so this briefly blocks the event loop as a deliberate tradeoff for a
  single-user demo.
- **`observability.py`** — OpenAI calls go through Galileo's native
  `galileo.openai` wrapper (auto-logs, no decorator needed), passing
  `name="openai"` so its spans are labeled by provider instead of the
  wrapper's generic default (`"llm"`) — that kwarg is captured by Galileo
  for the span label and stripped before the real API call, never sent to
  OpenAI. Anthropic and Gemini calls build their span by hand via
  `GalileoLogger.add_llm_span(...)` instead of the generic
  `@log(span_type="llm")` decorator — `@log` auto-captures *every* function
  argument as the input (including `system_prompt` as a stray key, since it
  doesn't know Anthropic/Gemini keep the system prompt separate from the
  conversation) and re-stringifies structured outputs it doesn't recognize
  (verified: a response with an Anthropic `thinking` block fell back to a
  raw JSON blob instead of readable text). Calling `add_llm_span` directly
  gives full control: `input` is a clean `[{"role": "system", ...}, ...]`
  list matching OpenAI's shape, `output` is flattened to readable text, and
  `tools`/token counts/duration are passed explicitly (the `tools` list
  matters — without it, Galileo's `tool_selection_quality` metric can't run
  and reports "not applicable"). Every Splunk MCP tool call still uses
  `@log(span_type="tool")`, which doesn't have this problem since its
  input/output are already simple strings. `run_traced_turn` maps each
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
