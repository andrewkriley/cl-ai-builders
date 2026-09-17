"""Minimal FastAPI chat app: browser <-> LLM agent <-> Splunk MCP, traced to Galileo.

Run from the repo root with: uvicorn app.main:app --reload
"""

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.observability import run_traced_turn  # noqa: E402 — import after load_dotenv sets env vars

app = FastAPI(title="AI Builders Workshop Chat")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


class ChatRequest(BaseModel):
    message: str
    conversation_id: str


class ChatResponse(BaseModel):
    reply: str


@app.get("/")
async def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    reply = await run_traced_turn(request.message, request.conversation_id)
    return ChatResponse(reply=reply)
