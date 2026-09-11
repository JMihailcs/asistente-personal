from __future__ import annotations

from asistente_mikha.config import get_vault_path
from asistente_mikha.memory.embeddings import ollama_embed
from asistente_mikha.memory.index import VaultIndexer
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


@tool(risk=ToolRisk.READ, description="Guarda una nota en el vault de Obsidian del usuario.")
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


@tool(risk=ToolRisk.READ, description="Busca notas relevantes en el vault de Obsidian del usuario.")
def search_notes(query: str, limit: int = 5) -> list[dict]:
    """Busca semanticamente en las notas guardadas y devuelve las mas relevantes."""
    try:
        return get_indexer().search(query, limit)
    except Exception:
        # Fallar en silencio (lista vacia) es mejor que romper el turno de
        # conversacion completo por un problema transitorio de embeddings.
        return []
