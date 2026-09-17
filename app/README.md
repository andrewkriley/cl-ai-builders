# The chat app

The reference chat app lands here in a follow-up step. This file is the
checklist for what it (or your own version) needs to do:

- **Chat UI**: a minimal HTML/JS page that posts user messages to the backend
  and renders the responses. No frontend build step required.
- **Backend**: a FastAPI app exposing a chat endpoint.
- **MCP client**: uses the `mcp` Python SDK to connect to the Splunk MCP
  server (`SPLUNK_MCP_URL` / `SPLUNK_MCP_TOKEN` / `SPLUNK_MCP_TRANSPORT` from
  `.env`) and list/call its tools.
- **LLM adapter**: switches between Anthropic, OpenAI, and Gemini based on
  `LLM_PROVIDER`, running the agent loop — send the user message and the
  available Splunk MCP tools to the LLM, execute any tool calls it requests
  via the MCP client, feed results back, repeat until it returns a final
  answer.
- **Observability**: see `observability.py` — OpenAI calls go through
  Galileo's native `galileo.openai` wrapper (auto-logs, no decorator needed);
  Anthropic and Gemini calls, and Splunk MCP tool calls, use Galileo's
  `@log(span_type=...)` decorator instead, since no native wrapper exists for
  those. The whole turn is wrapped in `galileo_context(...)` so everything
  lands in one trace.

If you're building your own version instead of using the reference app, this
list is your build order: MCP client → LLM adapter → agent loop → Galileo
tracing → chat UI.
