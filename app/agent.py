"""Provider-specific tool-calling loops: LLM <-> Splunk MCP tools, one loop per chat turn.

Each loop repeats: call the LLM with the Splunk MCP tools available -> if it
asks for a tool call, run it via observability.call_splunk_tool (a Galileo
`tool` span) and feed the result back -> otherwise return its final text.

The LLM calls run synchronously in-line (not via asyncio.to_thread) on
purpose: Galileo's logger lookup resolves to a different object with no
active trace inside a to_thread-spawned worker thread, which silently drops
every LLM span from the trace. Blocking the event loop briefly is an
acceptable tradeoff for this single-user workshop demo.
"""

import json
import os

from app import observability

MAX_TURNS = 5

SYSTEM_PROMPT = """\
You are an AI assistant helping a workshop participant explore their Splunk \
environment through Splunk MCP tools.

Known indexes on this instance:
- oidemo: IT/datacenter operations telemetry (PDU power, CRAC cooling, \
Windows/Exchange Perfmon counters).
- oidemo_notable: Splunk Enterprise Security notable events (security \
alerts) correlated to oidemo. Use this index for anything about security, \
notables, brute force, authentication failures, or audit events.
- main: general default-index sample data.

Prefer splunk_run_query with explicit SPL (e.g. `search index=oidemo_notable \
...`) over the saia_* tools — they call out to a separate AI Assistant \
backend on the Splunk instance that may be unavailable or return server \
errors, independent of this app.

Be concise and cite concrete numbers or index names from the tool results \
in your answer."""


async def run_agent_turn(user_message: str, mcp_tools: list[dict]) -> str:
    provider = os.environ.get("LLM_PROVIDER", "anthropic")
    if provider == "openai":
        return await _openai_loop(user_message, mcp_tools)
    if provider == "gemini":
        return await _gemini_loop(user_message, mcp_tools)
    return await _anthropic_loop(user_message, mcp_tools)


async def _openai_loop(user_message: str, mcp_tools: list[dict]) -> str:
    tools = [
        {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
        for t in mcp_tools
    ]
    messages = [{"role": "user", "content": user_message}]

    for _ in range(MAX_TURNS):
        response = observability.call_openai(messages, tools, SYSTEM_PROMPT)
        message = response.choices[0].message
        if not message.tool_calls:
            return message.content or ""

        messages.append(message.model_dump(exclude_unset=True))
        for tool_call in message.tool_calls:
            arguments = json.loads(tool_call.function.arguments or "{}")
            result = await observability.call_splunk_tool(tool_call.function.name, arguments)
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})

    return "Reached the tool-call limit for this turn without a final answer."


async def _anthropic_loop(user_message: str, mcp_tools: list[dict]) -> str:
    tools = [{"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]} for t in mcp_tools]
    messages = [{"role": "user", "content": user_message}]

    for _ in range(MAX_TURNS):
        response = observability.call_anthropic(messages, tools, SYSTEM_PROMPT)
        tool_uses = [block for block in response.content if block.type == "tool_use"]
        if not tool_uses:
            return "".join(block.text for block in response.content if block.type == "text")

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in tool_uses:
            result = await observability.call_splunk_tool(block.name, block.input)
            tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
        messages.append({"role": "user", "content": tool_results})

    return "Reached the tool-call limit for this turn without a final answer."


async def _gemini_loop(user_message: str, mcp_tools: list[dict]) -> str:
    from google.genai import types

    tools = [
        {"name": t["name"], "description": t["description"], "parameters_json_schema": t["input_schema"]} for t in mcp_tools
    ]
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=user_message)])]

    for _ in range(MAX_TURNS):
        response = observability.call_gemini(contents, tools, SYSTEM_PROMPT)
        calls = response.function_calls or []
        if not calls:
            return response.text or ""

        contents.append(response.candidates[0].content)
        result_parts = [
            types.Part.from_function_response(
                name=call.name,
                response={"result": await observability.call_splunk_tool(call.name, dict(call.args or {}))},
            )
            for call in calls
        ]
        contents.append(types.Content(role="user", parts=result_parts))

    return "Reached the tool-call limit for this turn without a final answer."
