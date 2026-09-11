from __future__ import annotations

import json
import time
from datetime import datetime
from typing import AsyncIterator

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from asistente_mikha.agent import AgentTurnResult, run_turn, run_turn_stream
from asistente_mikha.api.models import (
    ChatRequest,
    ChatResponse,
    ConfirmResponse,
    HealthResponse,
    NoteResponse,
    NotesResponse,
    PendingActionResponse,
    PendingActionsResponse,
    SystemResponse,
    TaskItemResponse,
    TaskListResponse,
    TasksResponse,
)
from asistente_mikha.config import get_ollama_base_url, get_vault_path
from asistente_mikha.confirmation import get_default_store
from asistente_mikha.memory.tasks import list_task_lists, list_tasks
from asistente_mikha.memory.vault import list_vault_notes
from asistente_mikha.tools.diagnostics import (
    get_disk_usage,
    get_gpu_status,
    get_ram_usage,
)

router = APIRouter()

RECENT_NOTES_LIMIT = 5


def _ollama_health_url() -> str:
    base = get_ollama_base_url()
    root = base[: -len("/v1")] if base.endswith("/v1") else base
    return f"{root}/api/tags"


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    queried_at = datetime.now().astimezone()
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


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    async def event_source() -> AsyncIterator[str]:
        queried_at = datetime.now().astimezone()
        started = time.perf_counter()
        async for item in run_turn_stream(request.session_id, request.message):
            if isinstance(item, AgentTurnResult):
                yield _sse(
                    "done",
                    {
                        "reply": item.reply,
                        "pending_action_ids": item.pending_action_ids,
                        "duration_seconds": time.perf_counter() - started,
                        "queried_at": queried_at.isoformat(),
                    },
                )
            else:
                yield _sse("token", {"text": item})

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/system", response_model=SystemResponse)
async def system() -> SystemResponse:
    return SystemResponse(
        ram=get_ram_usage(), disk=get_disk_usage("/"), gpu=get_gpu_status()
    )


@router.get("/tasks", response_model=TasksResponse)
async def all_tasks() -> TasksResponse:
    vault_path = get_vault_path()
    lists = []
    for name in list_task_lists(vault_path):
        task_list = list_tasks(vault_path, name)
        if task_list is None:
            continue
        lists.append(
            TaskListResponse(
                name=task_list.name,
                tasks=[
                    TaskItemResponse(text=item.text, done=item.done)
                    for item in task_list.items
                ],
            )
        )
    return TasksResponse(lists=lists)


@router.get("/notes/recent", response_model=NotesResponse)
async def recent_notes() -> NotesResponse:
    notes = list_vault_notes(get_vault_path())
    notes.sort(key=lambda n: n.created, reverse=True)
    return NotesResponse(
        notes=[
            NoteResponse(title=n.title, created=n.created, excerpt=n.content[:160])
            for n in notes[:RECENT_NOTES_LIMIT]
        ]
    )


@router.get("/actions/pending", response_model=PendingActionsResponse)
async def pending_actions() -> PendingActionsResponse:
    return PendingActionsResponse(
        actions=[
            PendingActionResponse(
                action_id=a.action_id, tool_name=a.tool_name, kwargs=a.kwargs
            )
            for a in get_default_store().list_pending()
        ]
    )


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
