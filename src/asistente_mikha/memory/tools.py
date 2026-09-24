from __future__ import annotations

from typing import Literal

from asistente_mikha.config import get_vault_path
from asistente_mikha.memory.embeddings import ollama_embed
from asistente_mikha.memory.index import VaultIndexer
from asistente_mikha.confirmation import get_default_store, register_implementation
from asistente_mikha.memory.tasks import (
    add_task,
    complete_task,
    delete_task,
    edit_task,
    find_task,
    list_task_lists,
    list_tasks,
)
from asistente_mikha.memory.vault import (
    delete_note,
    find_notes,
    update_note,
    write_note,
)
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
) -> dict:
    """Guarda ('save_note') o busca ('search_notes') notas en la memoria persistente."""
    if action == "save_note":
        missing = [
            name for name, value in (("title", title), ("content", content)) if not value
        ]
        if missing:
            return {"status": "missing_argument", "action": action, "required": missing}
        return {"status": "ok", "action": action, **save_note(title, content, tags)}

    if action == "search_notes":
        if not query:
            return {"status": "missing_argument", "action": action, "required": ["query"]}
        return {
            "status": "ok",
            "action": action,
            "results": search_notes(query=query, limit=limit),
        }

    return {
        "status": "invalid_action",
        "action": action,
        "allowed": ["save_note", "search_notes"],
    }


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
    # Que argumentos exige cada accion. Validar antes de tocar el vault evita
    # que una llamada a medio armar cree listas o complete tareas al azar.
    requires: dict[str, tuple[str, ...]] = {
        "add": ("list_name", "text"),
        "list": ("list_name",),
        "complete": ("list_name", "text"),
        "list_lists": (),
    }
    if action not in requires:
        return {"status": "invalid_action", "action": action, "allowed": list(requires)}

    given = {"list_name": list_name, "text": text}
    missing = [name for name in requires[action] if not given[name]]
    if missing:
        return {"status": "missing_argument", "action": action, "required": missing}

    vault_path = get_vault_path()

    if action == "list_lists":
        return {"status": "ok", "action": action, "lists": list_task_lists(vault_path)}

    assert list_name is not None  # garantizado por la validacion de arriba

    if action == "add":
        added = add_task(vault_path, list_name, text or "")
        if not added.tasks:
            return {"status": "missing_argument", "action": action, "required": ["text"]}
        return {
            "status": "ok",
            "action": action,
            "list": list_name,
            "added": added.tasks,
            "path": str(added.path),
        }

    if action == "list":
        result = list_tasks(vault_path, list_name)
        if result is None:
            return {"status": "list_not_found", "action": action, "list": list_name}
        return {
            "status": "ok",
            "action": action,
            "list": result.name,
            "tasks": [{"text": item.text, "done": item.done} for item in result.items],
        }

    return {"action": action, "list": list_name, **complete_task(vault_path, list_name, text or "")}


def _resync_index() -> None:
    try:
        get_indexer().sync()
    except Exception:
        # Igual que en save_note: el archivo ya cambio, el indice se
        # reconcilia en el proximo sync().
        pass


def _edit_note_impl(note: str, new_title: str | None = None, new_content: str | None = None) -> dict:
    found = find_notes(get_vault_path(), note)
    if len(found) != 1:
        return {"status": "not_found" if not found else "ambiguous"}
    updated = update_note(found[0], new_title, new_content)
    _resync_index()
    return {"status": "ok", "note": updated.title}


def _delete_note_impl(note: str) -> dict:
    found = find_notes(get_vault_path(), note)
    if len(found) != 1:
        return {"status": "not_found" if not found else "ambiguous"}
    delete_note(found[0])
    _resync_index()
    return {"status": "ok", "note": found[0].title}


def _edit_task_impl(list_name: str, text: str, new_text: str) -> dict:
    return edit_task(get_vault_path(), list_name, text, new_text)


def _delete_task_impl(list_name: str, text: str) -> dict:
    return delete_task(get_vault_path(), list_name, text)


_IMPLS = {
    "edit_note": _edit_note_impl,
    "delete_note": _delete_note_impl,
    "edit_task": _edit_task_impl,
    "delete_task": _delete_task_impl,
}
for _name, _impl in _IMPLS.items():
    register_implementation(_name, _impl)


def propose_change(
    action: str,
    note: str | None = None,
    new_title: str | None = None,
    new_content: str | None = None,
    list_name: str | None = None,
    text: str | None = None,
    new_text: str | None = None,
) -> dict:
    """Valida un cambio sobre notas/tareas y lo deja pendiente de confirmacion.

    Se valida al proponer (que exista y que sea una sola coincidencia):
    pedir confirmacion para algo que va a fallar no le sirve a nadie.
    """
    if action not in _IMPLS:
        return {"status": "invalid_action", "action": action, "allowed": list(_IMPLS)}
    # Idempotente: el store de tests se reinicia y borra las implementaciones.
    for name, impl in _IMPLS.items():
        register_implementation(name, impl)
    given = {
        "note": note,
        "list_name": list_name,
        "text": text,
        "new_text": new_text,
    }
    required = {
        "edit_note": ["note"],
        "delete_note": ["note"],
        "edit_task": ["list_name", "text", "new_text"],
        "delete_task": ["list_name", "text"],
    }[action]
    missing = [name for name in required if not given[name]]
    if action == "edit_note" and not (new_title or new_content is not None):
        missing.append("new_title o new_content")
    if missing:
        return {"status": "missing_argument", "action": action, "required": missing}

    vault_path = get_vault_path()
    if action in ("edit_note", "delete_note"):
        found = find_notes(vault_path, note or "")
        if not found:
            return {"status": "not_found", "action": action}
        if len(found) > 1:
            return {
                "status": "ambiguous",
                "action": action,
                "matches": [n.path.stem for n in found],
            }
        target = found[0].title
        kwargs: dict = {"note": found[0].path.stem}
        if action == "edit_note":
            kwargs.update(new_title=new_title, new_content=new_content)
    else:
        check = find_task(vault_path, list_name or "", text or "")
        if check["status"] != "ok":
            return {"action": action, "list": list_name, **check}
        target = check["task"]
        kwargs = {"list_name": list_name, "text": check["task"]}
        if action == "edit_task":
            kwargs["new_text"] = new_text
    pending = get_default_store().create(action, kwargs)
    return {
        "status": "pending_confirmation",
        "action": action,
        "target": target,
        "action_id": pending.action_id,
    }


@tool(
    risk=ToolRisk.CONFIRM,
    description=(
        "Edita o elimina notas y tareas existentes. Requiere confirmación."
    ),
)
def modify_data(
    action: Literal["edit_note", "delete_note", "edit_task", "delete_task"],
    note: str | None = None,
    new_title: str | None = None,
    new_content: str | None = None,
    list_name: str | None = None,
    text: str | None = None,
    new_text: str | None = None,
) -> dict:
    """Propone editar/eliminar una nota (por titulo) o tarea (lista + texto). No se ejecuta hasta confirmarse."""
    return propose_change(action, note, new_title, new_content, list_name, text, new_text)
