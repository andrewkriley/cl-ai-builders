"""Galileo instrumentation reference for the workshop chat agent.

Galileo only ships a native import-swap wrapper for OpenAI (`galileo.openai`)
— it auto-logs every call, no decorator needed. Anthropic and Gemini have no
such wrapper, so those calls use Galileo's `@log` decorator instead, which
creates the same kind of span manually. Tool calls (e.g. a Splunk MCP call)
use `@log(span_type="tool")` the same way, so all three providers plus tool
calls share one consistent instrumentation pattern.
"""

import os

from galileo import galileo_context, log


def call_openai(prompt: str) -> str:
    from galileo.openai import openai  # auto-logs every call, no decorator needed

    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


@log(span_type="llm")
def call_anthropic(prompt: str) -> str:
    from anthropic import Anthropic

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


@log(span_type="llm")
def call_gemini(prompt: str) -> str:
    from google import genai

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
    return response.text


@log(span_type="tool")
def call_splunk_tool(tool_name: str, arguments: dict):
    ...  # TODO: call the Splunk MCP tool here once the MCP client is built


_PROVIDER_CALLS = {
    "openai": call_openai,
    "anthropic": call_anthropic,
    "gemini": call_gemini,
}


def run_traced_turn(user_message: str) -> str:
    provider = os.environ.get("LLM_PROVIDER", "anthropic")

    with galileo_context(
        project=os.environ.get("GALILEO_PROJECT", "ai-builders-workshop"),
        log_stream=os.environ.get("GALILEO_LOG_STREAM", "default"),
    ):
        result = _PROVIDER_CALLS[provider](user_message)
        galileo_context.flush()
        return result
