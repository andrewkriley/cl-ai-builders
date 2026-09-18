"""Galileo instrumentation for the workshop chat agent.

Galileo only ships a native import-swap wrapper for OpenAI (`galileo.openai`)
— it auto-logs every call, no decorator needed. Anthropic and Gemini have no
such wrapper, so those calls build their span by hand via
`GalileoLogger.add_llm_span(...)` — not the `@log(span_type="llm")`
decorator, which generically dumps every function argument (including
`system_prompt` as a stray key, and provider-specific response shapes like
Anthropic's `thinking` blocks) into the span rather than a clean message
list. Splunk MCP tool calls still use `@log(span_type="tool")`, which
doesn't have this problem — its input/output are already simple. The whole
turn is wrapped in one `galileo_context` so every LLM/tool span lands in a
single trace.
"""

import json
import os
import time

from galileo import galileo_context, log, start_session

from app import mcp_client

_mcp_session = None
_galileo_sessions: dict[str, str] = {}  # conversation_id -> Galileo session_id, so every
                                          # turn in one browser conversation lands in one session


def set_mcp_session(session):
    global _mcp_session
    _mcp_session = session


def _galileo_session_id(conversation_id: str) -> str:
    if conversation_id not in _galileo_sessions:
        _galileo_sessions[conversation_id] = start_session(name=f"workshop-chat-{conversation_id}")
    return _galileo_sessions[conversation_id]


OPENAI_MODEL = "gpt-4o"
ANTHROPIC_MODEL = "claude-sonnet-5"
GEMINI_MODEL = "gemini-3.6-flash"

# KNOWN ISSUE (unresolved): in a real multi-round tool-calling conversation,
# most (not all) `llm` spans for a worker silently never reach Galileo —
# verified repeatedly against the real backend: a 4-6 round conversation
# typically ends up with only 1 surviving `llm` span, while every `tool`
# span and the trace's own input/output are unaffected. Investigated over
# many controlled reproductions (bounding logged payload size, switching to
# each provider's async client, flushing after every span instead of once
# at the end, mode="distributed" instead of the default "batch") — none of
# them fixed it, and several fabricated-data repros using the exact same
# code path never reproduced it at all, so the precise trigger is still
# unknown. `_MAX_LOGGED_TURNS` below bounds what gets logged per span
# regardless, since a growing multi-round payload is bad practice on its
# own merits even though it turned out not to be the cause here — the full
# conversation is reconstructable from the sequence of spans in the trace.
# If you hit this, it's not something wrong with your setup.
_MAX_LOGGED_TURNS = 6


async def call_openai(messages: list[dict], tools: list[dict], system_prompt: str):
    from galileo.openai import openai  # auto-logs every call, no decorator needed

    # AsyncOpenAI, not the sync client: avoiding a long blocking call inside
    # an async function is good practice regardless (doesn't stall other
    # work on the event loop) — see the KNOWN ISSUE comment above though,
    # this alone did not turn out to fix the missing-llm-span problem.
    client = openai.AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    full_messages = [{"role": "system", "content": system_prompt}, *messages]
    # `name` is captured by Galileo's wrapper for the span label and stripped
    # before the real API call — it's not forwarded to OpenAI. The wrapper
    # already reads `model` from these same kwargs for the span's model field.
    return await client.chat.completions.create(
        model=OPENAI_MODEL, messages=full_messages, tools=tools or None, name="openai"
    )


def _anthropic_content_to_log(blocks) -> str:
    """Flatten Anthropic content blocks (text/tool_use/thinking) into readable text.

    @log(span_type="llm")'s generic argument/return-value capture doesn't
    understand Anthropic's block types — a response with a `thinking` block
    fell back to a raw stringified blob instead of a readable message
    (verified against real Galileo trace data). add_llm_span's `output` only
    renders cleanly as a plain string — passing a dict with a list `content`
    gets silently re-stringified inside a wrapper instead of displayed, so
    this returns text, not a structured value.
    """
    parts = []
    for block in blocks:
        if block.type == "text":
            parts.append(block.text)
        elif block.type == "tool_use":
            parts.append(f"[tool_use: {block.name}({json.dumps(block.input)})]")
        elif block.type == "thinking" and block.thinking:
            parts.append(f"[thinking: {block.thinking}]")
    return "\n".join(parts)


async def call_anthropic(messages: list[dict], tools: list[dict], system_prompt: str):
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])  # see call_openai's comment on why async
    start = time.time()
    response = await client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1024,
        system=system_prompt,
        messages=messages,
        tools=tools or [],
    )

    # Logged by hand via add_llm_span (the same primitive @log calls
    # internally) instead of @log(span_type="llm"): that gave input as one
    # big stringified dict of every function argument (including
    # system_prompt as a stray key, not as part of the conversation) rather
    # than a clean message list, since it doesn't know Anthropic keeps
    # `system` separate from `messages`. The real API call above still gets
    # the full `messages` history; only the logged copy is bounded.
    galileo_context.get_logger_instance().add_llm_span(
        input=[{"role": "system", "content": system_prompt}, *messages[-_MAX_LOGGED_TURNS:]],
        output=_anthropic_content_to_log(response.content),
        model=ANTHROPIC_MODEL,
        name="anthropic",
        tools=tools or None,
        num_input_tokens=response.usage.input_tokens,
        num_output_tokens=response.usage.output_tokens,
        duration_ns=int((time.time() - start) * 1e9),
    )
    return response


def _gemini_part_to_text(part) -> str:
    if part.text is not None:
        return part.text
    if part.function_call is not None:
        return f"[function_call: {part.function_call.name}({json.dumps(dict(part.function_call.args or {}))})]"
    if part.function_response is not None:
        return f"[function_response: {part.function_response.name} -> {json.dumps(dict(part.function_response.response or {}))}]"
    return f"[{type(part).__name__}]"


def _gemini_content_text(content) -> str:
    # add_llm_span's message-list schema wants {"role": ..., "content": <str>}
    # per entry — verified against real Galileo data that {"role": ...,
    # "parts": [...]} isn't recognized: every entry's role silently collapsed
    # to "user" and the whole dict got re-stringified into a "content" field
    # instead of being displayed. Flattening parts to text up front avoids
    # that entirely, for both input entries and the final output.
    if content is None:
        return ""
    return "\n".join(_gemini_part_to_text(part) for part in content.parts)


async def call_gemini(contents: list, tools: list[dict], system_prompt: str):
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])  # client.aio used below — see call_openai's comment on why async
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=[types.Tool(function_declarations=tools)] if tools else None,
    )
    start = time.time()
    response = await client.aio.models.generate_content(model=GEMINI_MODEL, contents=contents, config=config)

    # Same reasoning as call_anthropic: log by hand so system_prompt shows up
    # as part of the conversation (Gemini keeps it out of `contents` too) and
    # so the response renders as text/function-call parts instead of an
    # opaque blob. Gemini's own role name for its turns is "model" — not a
    # role Galileo recognizes (verified: that entry alone got wrapped and
    # re-stringified, role silently defaulted to "user") — mapped to the
    # conventional "assistant" here.
    # The real API call above gets the full `contents` history; only the
    # logged copy is bounded (see _MAX_LOGGED_TURNS comment above).
    logged_input = [
        {"role": "system", "content": system_prompt},
        *[
            {"role": "assistant" if c.role == "model" else c.role, "content": _gemini_content_text(c)}
            for c in contents[-_MAX_LOGGED_TURNS:]
        ],
    ]
    logged_output = _gemini_content_text(response.candidates[0].content) if response.candidates else (response.text or "")
    usage = response.usage_metadata
    galileo_context.get_logger_instance().add_llm_span(
        input=logged_input,
        output=logged_output,
        model=GEMINI_MODEL,
        name="gemini",
        tools=tools or None,
        num_input_tokens=usage.prompt_token_count if usage else None,
        num_output_tokens=usage.candidates_token_count if usage else None,
        duration_ns=int((time.time() - start) * 1e9),
    )
    return response


@log(span_type="tool")
async def call_splunk_tool(tool_name: str, arguments: dict) -> str:
    return await mcp_client.call_tool(_mcp_session, tool_name, arguments)


async def run_traced_turn(user_message: str, conversation_id: str, provider: str | None = None) -> str:
    from app.agent import run_agent_turn

    with galileo_context(
        project=os.environ.get("GALILEO_PROJECT", "ai-builders-workshop"),
        log_stream=os.environ.get("GALILEO_LOG_STREAM", "default"),
        session_id=_galileo_session_id(conversation_id),
    ):
        # Without an explicit start_trace/conclude, Galileo lazily creates the
        # trace from whichever child span happens to log first — so the trace's
        # own input/output end up being an arbitrary tool call or LLM message
        # list instead of the actual user question and final answer.
        logger = galileo_context.get_logger_instance()
        logger.start_trace(input=user_message)

        async with mcp_client.splunk_mcp_session() as session:
            set_mcp_session(session)
            tools = await mcp_client.list_splunk_tools(session)
            result = await run_agent_turn(user_message, tools, provider=provider)

        logger.conclude(output=result)
        galileo_context.flush()
        return result
