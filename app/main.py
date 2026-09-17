"""Minimal FastAPI chat app: browser <-> LLM agent <-> Splunk MCP, traced to Galileo.

Run from the repo root with: uvicorn app.main:app --reload
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.observability import run_traced_turn  # noqa: E402 — import after load_dotenv sets env vars

app = FastAPI(title="AI Builders Workshop Chat")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

PROVIDER_KEY_ENV_VARS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


class ChatRequest(BaseModel):
    message: str
    conversation_id: str
    provider: str | None = None


class ChatResponse(BaseModel):
    reply: str


class ConfigResponse(BaseModel):
    providers: list[str]
    default_provider: str


def _configured_providers() -> list[str]:
    return [p for p, env_var in PROVIDER_KEY_ENV_VARS.items() if os.environ.get(env_var, "").strip()]


@app.get("/")
async def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/config", response_model=ConfigResponse)
async def config():
    providers = _configured_providers()
    if not providers:
        raise HTTPException(500, "No LLM provider API key is configured in .env")

    env_default = os.environ.get("LLM_PROVIDER", "").strip()
    default_provider = env_default if env_default in providers else providers[0]
    return ConfigResponse(providers=providers, default_provider=default_provider)


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    if request.provider and request.provider not in _configured_providers():
        raise HTTPException(400, f"'{request.provider}' has no API key configured in .env")

    reply = await run_traced_turn(request.message, request.conversation_id, provider=request.provider)
    return ChatResponse(reply=reply)
