"""Wire up and verify the Splunk MCP connection for this workshop.

Reads SPLUNK_MCP_URL / SPLUNK_MCP_TOKEN / SPLUNK_MCP_TRANSPORT from .env,
writes (or merges into) a project-root .mcp.json so an MCP-aware AI harness
(e.g. Claude Code) can see the Splunk MCP tools, then does a live
connectivity check by listing the server's tools.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
MCP_CONFIG_PATH = REPO_ROOT / ".mcp.json"


def load_config():
    load_dotenv(REPO_ROOT / ".env")

    url = os.environ.get("SPLUNK_MCP_URL", "").strip()
    token = os.environ.get("SPLUNK_MCP_TOKEN", "").strip()
    transport = os.environ.get("SPLUNK_MCP_TRANSPORT", "http").strip().lower()

    missing = [name for name, value in (("SPLUNK_MCP_URL", url), ("SPLUNK_MCP_TOKEN", token)) if not value]
    if missing:
        print(f"Missing required .env value(s): {', '.join(missing)}")
        print("Copy .env.example to .env and fill in the Splunk section, then re-run this script.")
        sys.exit(1)

    if transport not in ("http", "sse"):
        print(f"SPLUNK_MCP_TRANSPORT='{transport}' isn't handled by this script (only http/sse).")
        print("Ask the facilitator for the exact MCP client config for this transport.")
        sys.exit(1)

    return url, token, transport


def write_mcp_config(url: str, token: str, transport: str):
    config = {}
    if MCP_CONFIG_PATH.exists():
        try:
            config = json.loads(MCP_CONFIG_PATH.read_text())
        except json.JSONDecodeError:
            print(f"Warning: {MCP_CONFIG_PATH} exists but isn't valid JSON — leaving it untouched.")
            return

    config.setdefault("mcpServers", {})
    config["mcpServers"]["splunk"] = {
        "type": transport,
        "url": url,
        "headers": {"Authorization": f"Bearer {token}"},
    }

    MCP_CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n")
    print(f"Wrote Splunk MCP server config to {MCP_CONFIG_PATH}")


async def check_connection(url: str, token: str, transport: str):
    from mcp import ClientSession

    headers = {"Authorization": f"Bearer {token}"}

    if transport == "http":
        from mcp.client.streamable_http import streamablehttp_client

        client_cm = streamablehttp_client(url, headers=headers)
    else:
        from mcp.client.sse import sse_client

        client_cm = sse_client(url, headers=headers)

    async with client_cm as streams:
        read, write = streams[0], streams[1]
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return [tool.name for tool in result.tools]


def main():
    url, token, transport = load_config()
    write_mcp_config(url, token, transport)

    print(f"Checking connection to Splunk MCP server ({transport}) at {url} ...")
    try:
        tool_names = asyncio.run(check_connection(url, token, transport))
    except Exception as exc:  # noqa: BLE001 — this is a diagnostic tool, show the user what broke
        print(f"Could not connect: {exc}")
        print("Double check SPLUNK_MCP_URL, SPLUNK_MCP_TOKEN, and SPLUNK_MCP_TRANSPORT with the facilitator.")
        sys.exit(1)

    print(f"Connected. Available Splunk MCP tools: {', '.join(tool_names) if tool_names else '(none returned)'}")


if __name__ == "__main__":
    main()
