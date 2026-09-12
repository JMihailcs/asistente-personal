from __future__ import annotations

from typing import Literal

from asistente_mikha.config import get_vault_path
from asistente_mikha.memory.embeddings import ollama_embed
from asistente_mikha.memory.index import VaultIndexer
from asistente_mikha.memory.tasks import (
    add_task,
    complete_task,
    list_task_lists,
    list_tasks,
)
from asistente_mikha.memory.vault import write_note
from asistente_mikha.tools.registry import ToolRisk, tool

_indexer: VaultIndexer | None = None


def get_indexer() -> VaultIndexer:
    global _indexer
    if _indexer is None:
        _indexer = VaultIndexer(get_vault_path(), ollama_embed)
    return _indexer


def reset_indexer_for_tests() -> None:
    global _indexer
    _indexer = None


def save_note(title: str, content: str, tags: list[str] | None = None) -> dict:
    """Guarda una nota nueva en el vault y la indexa para busqueda semantica."""
    file_path = write_note(get_vault_path(), title, content, tags or [])
    try:
        get_indexer().sync()
        indexed = True
    except Exception:
        # No perder la nota si falla el paso de indexado (ej. Ollama caido):
        # el archivo ya quedo guardado y se reintentara en el proximo sync().
        indexed = False
    return {"path": str(file_path), "indexed": indexed}


def search_notes(query: str, limit: int = 5) -> list[dict]:
    """Busca semanticamente en las notas guardadas y devuelve las mas relevantes."""
    try:
        return get_indexer().search(query, limit)
    except Exception:
        # Fallar en silencio (lista vacia) es mejor que romper el turno de
        # conversacion completo por un problema transitorio de embeddings.
        return []


@tool(
    risk=ToolRisk.READ,
    description="Memoria persistente: guardar o buscar notas en el vault de Obsidian del usuario.",
)
def memory(
    action: Literal["save_note", "search_notes"],
    title: str | None = None,
    content: str | None = None,
    tags: list[str] | None = None,
    query: str | None = None,
    limit: int = 5,
) -> dict | list[dict]:
    """Guarda ('save_note') o busca ('search_notes') notas en la memoria persistente."""
    if action == "save_note":
        return save_note(title=title or "", content=content or "", tags=tags)
    return search_notes(query=query or "", limit=limit)


@tool(
    risk=ToolRisk.READ,
    description="Gestiona listas de tareas por tema/meta en el vault de Obsidian del usuario.",
)
def tasks(
    action: Literal["add", "list", "complete", "list_lists"],
    list_name: str | None = None,
    text: str | None = None,
) -> dict:
    """Agrega, lista o completa tareas de una lista por tema, o lista todas las listas existentes."""
    required: list[str] = []
    if action == "add":
        if not list_name:
            required.append("list_name")
        if not text:
            required.append("text")
    elif action == "list":
        if not list_name:
            required.append("list_name")
    elif action == "complete":
        if not list_name:
            required.append("list_name")
        if not text:
            required.append("text")
    if required:
        return {"status": "missing_argument", "required": required}

    vault_path = get_vault_path()
    if action == "add":
        added = add_task(vault_path, list_name or "", text or "")
        if not added.tasks:
            return {"status": "missing_argument", "required": ["text"]}
        return {"status": "added", "path": str(added.path), "tasks": added.tasks}
    if action == "list":
        result = list_tasks(vault_path, list_name or "")
        if result is None:
            return {"status": "list_not_found"}
        return {
            "list": result.name,
            "tasks": [{"text": item.text, "done": item.done} for item in result.items],
        }
    if action == "complete":
        return complete_task(vault_path, list_name or "", text or "")
    return {"lists": list_task_lists(vault_path)}
