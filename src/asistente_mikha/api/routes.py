from __future__ import annotations

import time
from datetime import datetime

import httpx
from fastapi import APIRouter, HTTPException

from asistente_mikha.agent import run_turn
from asistente_mikha.api.models import (
    ChatRequest,
    ChatResponse,
    ConfirmResponse,
    HealthResponse,
)
from asistente_mikha.config import get_ollama_base_url
from asistente_mikha.confirmation import get_default_store

router = APIRouter()


def _ollama_health_url() -> str:
    base = get_ollama_base_url()
    root = base[: -len("/v1")] if base.endswith("/v1") else base
    return f"{root}/api/tags"


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    queried_at = datetime.now()
    started = time.perf_counter()
    result = await run_turn(request.session_id, request.message)
    duration_seconds = time.perf_counter() - started
    return ChatResponse(
        reply=result.reply,
        pending_action_ids=result.pending_action_ids,
        duration_seconds=duration_seconds,
        queried_at=queried_at.isoformat(),
    )


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
            resp = await client.get(_ollama_health_url())
            ollama_ok = resp.status_code == 200
    except httpx.HTTPError:
        ollama_ok = False
    return HealthResponse(status="ok", ollama_reachable=ollama_ok)
