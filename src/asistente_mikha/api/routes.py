from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException

from asistente_mikha.agent import run_turn
from asistente_mikha.api.models import (
    ChatRequest,
    ChatResponse,
    ConfirmResponse,
    HealthResponse,
)
from asistente_mikha.confirmation import get_default_store

router = APIRouter()

OLLAMA_HEALTH_URL = "http://localhost:11434/api/tags"


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    result = await run_turn(request.session_id, request.message)
    return ChatResponse(reply=result.reply, pending_action_ids=result.pending_action_ids)


@router.post("/confirm/{action_id}", response_model=ConfirmResponse)
async def confirm(action_id: str, approve: bool = True) -> ConfirmResponse:
    store = get_default_store()
    try:
        action = store.execute(action_id) if approve else store.reject(action_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ConfirmResponse(action_id=action.action_id, status=action.status.value, result=action.result)


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    ollama_ok = False
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(OLLAMA_HEALTH_URL)
            ollama_ok = resp.status_code == 200
    except httpx.HTTPError:
        ollama_ok = False
    return HealthResponse(status="ok", ollama_reachable=ollama_ok)
