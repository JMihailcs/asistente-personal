from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str
    pending_action_ids: list[str] = []


class ConfirmResponse(BaseModel):
    action_id: str
    status: str
    result: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    status: str
    ollama_reachable: bool
