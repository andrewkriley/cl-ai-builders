"""Galileo instrumentation for the workshop chat agent.

Galileo only ships a native import-swap wrapper for OpenAI (`galileo.openai`)
— it auto-logs every call, no decorator needed. Anthropic and Gemini have no
such wrapper, so those calls use Galileo's `@log` decorator instead, which
creates the same kind of span manually. Splunk MCP tool calls use
`@log(span_type="tool")` the same way. The whole turn is wrapped in one
`galileo_context` so every LLM/tool span lands in a single trace.
"""

import os

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


def call_openai(messages: list[dict], tools: list[dict], system_prompt: str):
    from galileo.openai import openai  # auto-logs every call, no decorator needed

    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    full_messages = [{"role": "system", "content": system_prompt}, *messages]
    return client.chat.completions.create(model="gpt-4o", messages=full_messages, tools=tools or None)


@log(span_type="llm")
def call_anthropic(messages: list[dict], tools: list[dict], system_prompt: str):
    from anthropic import Anthropic

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return client.messages.create(
        model="claude-sonnet-5",
        max_tokens=1024,
        system=system_prompt,
        messages=messages,
        tools=tools or [],
    )


@log(span_type="llm")
def call_gemini(contents: list, tools: list[dict], system_prompt: str):
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=[types.Tool(function_declarations=tools)] if tools else None,
    )
    return client.models.generate_content(model="gemini-3.6-flash", contents=contents, config=config)


@log(span_type="tool")
async def call_splunk_tool(tool_name: str, arguments: dict) -> str:
    return await mcp_client.call_tool(_mcp_session, tool_name, arguments)


async def run_traced_turn(user_message: str, conversation_id: str) -> str:
    from app.agent import run_agent_turn

    with galileo_context(
        project=os.environ.get("GALILEO_PROJECT", "ai-builders-workshop"),
        log_stream=os.environ.get("GALILEO_LOG_STREAM", "default"),
        session_id=_galileo_session_id(conversation_id),
    ):
        async with mcp_client.splunk_mcp_session() as session:
            set_mcp_session(session)
            tools = await mcp_client.list_splunk_tools(session)
            result = await run_agent_turn(user_message, tools)

        galileo_context.flush()
        return result
