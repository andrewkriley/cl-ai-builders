# Workshop workflow

Follow these steps in order. Where a step says "ask your AI harness," you can
paste the instruction into Claude Code (or whichever AI coding assistant
you're using) and let it run the commands for you.

## 1. Clone the repo

```
git clone https://github.com/andrewkriley/cl-ai-builders.git
cd cl-ai-builders
```

## 2. Sign up for Galileo

1. Go to https://app.galileo.ai/sign-up and create an account.
2. Verify your email address (check your inbox for a verification link).
3. Log in at https://app.galileo.ai and confirm you can reach your dashboard.

## 3. Create a Galileo API key

1. In the Galileo console, go to your account/API key settings.
2. Create a new API key and copy it somewhere safe — it's only shown once.
3. Note (or create) a project name you'll use for this workshop, e.g.
   `ai-builders-workshop`.

## 4. Set up your `.env` file

```
cp .env.example .env
```

Open `.env` and fill in the Galileo section:

```
GALILEO_API_KEY=<the key you just created>
GALILEO_PROJECT=ai-builders-workshop
GALILEO_LOG_STREAM=default
```

## 5. Get your Splunk details from the facilitator

The facilitator will hand out, per participant:

- A Splunk Cloud instance URL and login
- A Splunk MCP server URL and token

Log in to the Splunk Cloud instance in your browser first, to confirm your
credentials work.

Then fill in the Splunk section of `.env`:

```
SPLUNK_MCP_URL=<url the facilitator gave you>
SPLUNK_MCP_TOKEN=<token the facilitator gave you>
SPLUNK_MCP_TRANSPORT=http
```

> `SPLUNK_MCP_TRANSPORT` defaults to `http` — confirm with the facilitator
> whether your MCP server actually expects `http`, `sse`, or `stdio`.

## 6. Bring your own LLM API key

Get an API key from **one** of:

- Anthropic: https://console.anthropic.com
- OpenAI: https://platform.openai.com
- Gemini: https://aistudio.google.com/apikey

This must be a billed API key, not a Claude.ai/ChatGPT/Cursor subscription —
the app calls the API directly and pays per token.

Fill in the LLM section of `.env`, setting `LLM_PROVIDER` to match whichever
key you got:

```
LLM_PROVIDER=anthropic          # anthropic | openai | gemini
ANTHROPIC_API_KEY=<your key>    # if using Anthropic
OPENAI_API_KEY=<your key>       # if using OpenAI
GEMINI_API_KEY=<your key>       # if using Gemini
```

## 7. Create a virtual environment and install dependencies

```
python3 -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Keeping this in a venv means the workshop's dependencies (and Python version
requirement) won't clash with anything else on your machine, and you can
delete `.venv/` afterwards to clean up.

Remember to run `source .venv/bin/activate` again any time you open a new
terminal for the rest of the workshop.

## 8. Wire up your Splunk MCP connection

Run the setup script — it reads your `.env` and writes/updates a
project-scoped `.mcp.json` so your AI harness can see the Splunk MCP tools:

```
python scripts/setup_mcp.py
```

This also does a live connectivity check against your Splunk MCP server and
lists the tools it exposes. If it fails, see [Troubleshooting](#troubleshooting).

## 9. Check MCP access

Ask your AI harness (e.g. Claude Code) to list the available Splunk MCP tools
and run a simple query, for example:

> "List the Splunk MCP tools available to you, then run a sample search
> against the Splunk instance to confirm you can read data."

If it returns real results from your Splunk instance, you're ready to build.

## 10. Build or run the app

- **Just want it running:** see [`app/README.md`](./app/README.md) for the
  reference app.
- **Want to build your own:** `app/README.md` also describes the pieces
  (LLM adapter, MCP client, Galileo tracing, chat UI) so you can build the
  agent loop yourself.

## Troubleshooting

- **`scripts/setup_mcp.py` reports missing env vars** — double check `.env`
  has `SPLUNK_MCP_URL` and `SPLUNK_MCP_TOKEN` filled in (not left blank from
  `.env.example`).
- **MCP connection fails / times out** — confirm `SPLUNK_MCP_TRANSPORT`
  matches what the facilitator's server actually expects, and that you're on
  the workshop network/VPN if one is required.
- **LLM API calls fail with an auth error** — check you copied the full key
  with no extra whitespace, and that it's an API key (starts with `sk-ant-`
  for Anthropic, `sk-` for OpenAI, or `AIza` for Gemini), not a session token.
- **No traces show up in the Galileo dashboard** — confirm `GALILEO_API_KEY`
  and `GALILEO_PROJECT` are set, and that the app actually ran a turn (traces
  only appear after a completed request).
