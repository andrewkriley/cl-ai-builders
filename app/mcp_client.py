"""Splunk MCP client — same derived endpoint and self-signed-cert handling as scripts/setup_mcp.py."""

import os
from contextlib import asynccontextmanager

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def _mcp_url() -> str:
    instance_url = os.environ["SPLUNK_INSTANCE_URL"].rstrip("/")
    return f"{instance_url}:8089/services/mcp"


@asynccontextmanager
async def splunk_mcp_session():
    token = os.environ["SPLUNK_MCP_TOKEN"]
    async with httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        verify=False,  # Splunk's management port uses a self-signed cert by default
    ) as http_client:
        async with streamable_http_client(_mcp_url(), http_client=http_client) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


async def list_splunk_tools(session: ClientSession) -> list[dict]:
    result = await session.list_tools()
    return [{"name": t.name, "description": t.description or "", "input_schema": t.input_schema} for t in result.tools]


async def call_tool(session: ClientSession, name: str, arguments: dict) -> str:
    result = await session.call_tool(name, arguments)
    return "\n".join(block.text for block in result.content if hasattr(block, "text"))
