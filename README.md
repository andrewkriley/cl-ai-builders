# AI Builders Workshop: Splunk + MCP + Galileo

A hands-on workshop for building an AI agent application that queries live data
from a Splunk instance via [MCP](https://modelcontextprotocol.io) and reports
agent observability signals to [Galileo](https://app.galileo.ai).

## What you'll build

A small web app with a chat interface, backed by an AI agent that:

1. Takes a user's question in the chat UI.
2. Calls an LLM API (Anthropic, OpenAI, or Gemini — your own key) to reason
   about the question.
3. Lets the LLM call tools exposed by a **Splunk MCP server** to query your
   Splunk instance for the data it needs.
4. Traces the whole turn (prompts, tool calls, responses) to **Galileo** for
   agent observability.

```
 Browser (chat UI)
       │
       ▼
   FastAPI app ──► LLM API (Anthropic / OpenAI / Gemini, your key)
       │                     │
       │                     ▼ (tool calls)
       └───────────► Splunk MCP server ──► your Splunk instance
       │
       ▼
    Galileo (trace of the agent's turn)
```

Galileo only ships a native wrapper for OpenAI (`galileo.openai`, drop-in,
auto-logs every call). Anthropic and Gemini calls — and Splunk MCP tool
calls — use Galileo's `@log` decorator instead, which produces the same kind
of trace without a provider-specific wrapper.

A working reference app will be provided so everyone has something running by
the end of the session. If you're comfortable, you're encouraged to build your
own version from scratch using the same three building blocks (LLM API, MCP
client, Galileo).

## Prerequisites

- Python 3.11+
- git
- A [Galileo](https://app.galileo.ai/sign-up) account (free to sign up)
- Your own Anthropic, OpenAI, or Gemini API key (**not** a subscription tool
  like Claude Code/Claude.ai or Cursor/ChatGPT Plus — the app needs a billed
  API key it can call directly)
- A Splunk Cloud login, Splunk MCP token, and MCP server URL — **provided by
  the workshop facilitator** at the start of the session

## Getting started

Follow [`build.md`](./build.md) — it's the step-by-step workflow for this
workshop, from cloning the repo through to a running app.

## Repo layout

| Path | Purpose |
|---|---|
| `build.md` | Step-by-step workshop workflow |
| `.env.example` | Template for your local `.env` (API keys, tokens) |
| `requirements.txt` | Python dependencies |
| `scripts/setup_mcp.py` | Wires up and verifies your Splunk MCP connection |
| `app/` | Where the chat app lives (reference app + your own build) |
| `.github/workflows/gitleaks.yml` | CI check that scans commits for leaked secrets |
