from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str
    pending_action_ids: list[str] = []
    duration_seconds: float
    queried_at: str


class ConfirmResponse(BaseModel):
    action_id: str
    status: str
    result: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    status: str
    ollama_reachable: bool


class SystemResponse(BaseModel):
    ram: dict[str, Any]
    disk: dict[str, Any]
    gpu: dict[str, Any]


class TaskItemResponse(BaseModel):
    text: str
    done: bool


class TaskListResponse(BaseModel):
    name: str
    tasks: list[TaskItemResponse]


class TasksResponse(BaseModel):
    lists: list[TaskListResponse]


class NoteResponse(BaseModel):
    title: str
    created: str
    excerpt: str


class NotesResponse(BaseModel):
    notes: list[NoteResponse]


class PendingActionResponse(BaseModel):
    action_id: str
    tool_name: str
    kwargs: dict[str, Any]


class PendingActionsResponse(BaseModel):
    actions: list[PendingActionResponse]
