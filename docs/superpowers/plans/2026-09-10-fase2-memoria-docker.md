# Fase 2 — Memoria (segundo cerebro) + Docker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar a Mikha memoria persistente sobre un vault de Obsidian (guardar y buscar notas semánticamente) y empaquetar el backend + Phoenix en `docker-compose`, manteniendo Ollama nativo por la aceleración GPU.

**Architecture:** Nuevo paquete `asistente_mikha.memory` (vault en texto plano con frontmatter YAML, embeddings vía Ollama, índice Chroma embebido) con dos herramientas nuevas (`save_note`, `search_notes`) registradas en el mismo `registry` de Fase 1. Toda configuración sensible al entorno (URL de Ollama, endpoint de Phoenix, ruta del vault) se centraliza en un módulo `config.py` nuevo, para que el mismo código corra nativo o dentro de Docker sin cambios. El backend y Phoenix se empaquetan en contenedores; Ollama y el CLI se quedan nativos.

**Tech Stack:** chromadb (vector store embebido), PyYAML (frontmatter), httpx (ya presente, para llamar al endpoint de embeddings de Ollama), Docker + Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-10-fase2-memoria-docker-design.md`

## Global Constraints

- El vault por defecto vive en `~/Obsidian/Mikha`, mismo valor tanto nativo como en Docker (dentro del contenedor se monta en `/vault` y se sobreescribe vía `MIKHA_VAULT_PATH`).
- `save_note` y `search_notes` son herramientas de riesgo `read` (ejecución inmediata, sin confirmación).
- Ninguna función de guardado de notas debe perder el contenido del usuario si falla el paso de indexado (embeddings) — el archivo `.md` siempre se escribe primero.
- El UID del usuario en esta máquina es `1000` (usado para el socket D-Bus en `docker-compose.yml`).
- Ollama sigue corriendo nativo en `http://localhost:11434`; nunca se dockeriza en este plan.

---

## Task 1: Módulo de configuración centralizada + dependencias nuevas

**Files:**
- Modify: `pyproject.toml`
- Create: `src/asistente_mikha/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `get_ollama_base_url() -> str`, `get_phoenix_endpoint() -> str`, `get_vault_path() -> Path`.

- [ ] **Step 1: Agregar dependencias nuevas**

En `pyproject.toml`, dentro de `dependencies`, agregar:
```toml
    "chromadb>=0.5",
    "pyyaml>=6.0",
```

Run:
```bash
source .venv/bin/activate
pip install -e ".[dev]"
```
Expected: instala `chromadb` y `pyyaml` sin errores.

- [ ] **Step 2: Escribir el test (falla primero)**

`tests/test_config.py`:
```python
from pathlib import Path

from asistente_mikha.config import (
    get_ollama_base_url,
    get_phoenix_endpoint,
    get_vault_path,
)


def test_get_ollama_base_url_default(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    assert get_ollama_base_url() == "http://localhost:11434/v1"


def test_get_ollama_base_url_env_override(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://otro-host:11434/v1")
    assert get_ollama_base_url() == "http://otro-host:11434/v1"


def test_get_phoenix_endpoint_default(monkeypatch):
    monkeypatch.delenv("PHOENIX_ENDPOINT", raising=False)
    assert get_phoenix_endpoint() == "http://localhost:6006/v1/traces"


def test_get_phoenix_endpoint_env_override(monkeypatch):
    monkeypatch.setenv("PHOENIX_ENDPOINT", "http://phoenix:6006/v1/traces")
    assert get_phoenix_endpoint() == "http://phoenix:6006/v1/traces"


def test_get_vault_path_default(monkeypatch):
    monkeypatch.delenv("MIKHA_VAULT_PATH", raising=False)
    assert get_vault_path() == Path.home() / "Obsidian" / "Mikha"


def test_get_vault_path_env_override(monkeypatch):
    monkeypatch.setenv("MIKHA_VAULT_PATH", "/vault")
    assert get_vault_path() == Path("/vault")
```

Run: `pytest tests/test_config.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'asistente_mikha.config'`.

- [ ] **Step 3: Implementar**

`src/asistente_mikha/config.py`:
```python
from __future__ import annotations

import os
from pathlib import Path


def get_ollama_base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")


def get_phoenix_endpoint() -> str:
    return os.environ.get("PHOENIX_ENDPOINT", "http://localhost:6006/v1/traces")


def get_vault_path() -> Path:
    default = str(Path.home() / "Obsidian" / "Mikha")
    return Path(os.environ.get("MIKHA_VAULT_PATH", default))
```

- [ ] **Step 4: Verificar que pasa**

Run: `pytest tests/test_config.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/asistente_mikha/config.py tests/test_config.py
git commit -m "feat: modulo de configuracion centralizada por variables de entorno"
```

---

## Task 2: Vault de notas (lectura/escritura de archivos markdown)

**Files:**
- Create: `src/asistente_mikha/memory/__init__.py`
- Create: `src/asistente_mikha/memory/vault.py`
- Test: `tests/test_vault.py`

**Interfaces:**
- Consumes: nada de tareas anteriores (módulo puro, recibe `vault_path: Path` explícito en cada función).
- Produces: `Note` (dataclass: `path: Path`, `title: str`, `tags: list[str]`, `created: str`, `content: str`, propiedad `content_hash: str`), `slugify(title: str) -> str`, `write_note(vault_path: Path, title: str, content: str, tags: list[str] | None = None) -> Path`, `parse_note(file_path: Path) -> Note | None`, `list_vault_notes(vault_path: Path) -> list[Note]`.

- [ ] **Step 1: Escribir tests (fallan primero)**

`src/asistente_mikha/memory/__init__.py`: vacío.

`tests/test_vault.py`:
```python
from asistente_mikha.memory.vault import (
    slugify,
    write_note,
    parse_note,
    list_vault_notes,
)


def test_slugify_basic():
    assert slugify("Idea de Negocio X") == "idea-de-negocio-x"


def test_slugify_strips_punctuation():
    assert slugify("Que hacer? Ya!") == "que-hacer-ya"


def test_slugify_empty_falls_back():
    assert slugify("   ") == "nota"


def test_write_note_creates_file_with_frontmatter(tmp_path):
    file_path = write_note(tmp_path, "Mi primera nota", "Contenido de prueba", ["ideas"])
    assert file_path.exists()
    text = file_path.read_text()
    assert text.startswith("---\n")
    assert "title: Mi primera nota" in text
    assert "Contenido de prueba" in text


def test_write_note_avoids_overwriting_duplicate_titles(tmp_path):
    first = write_note(tmp_path, "Repetida", "primera")
    second = write_note(tmp_path, "Repetida", "segunda")
    assert first != second
    assert first.exists()
    assert second.exists()


def test_parse_note_roundtrip(tmp_path):
    path = write_note(tmp_path, "Nota de prueba", "Cuerpo de la nota", ["a", "b"])
    note = parse_note(path)
    assert note is not None
    assert note.title == "Nota de prueba"
    assert note.tags == ["a", "b"]
    assert note.content == "Cuerpo de la nota"


def test_parse_note_returns_none_for_malformed_file(tmp_path):
    bad_file = tmp_path / "roto.md"
    bad_file.write_text("esto no tiene frontmatter")
    assert parse_note(bad_file) is None


def test_list_vault_notes_skips_malformed_and_finds_valid(tmp_path):
    write_note(tmp_path, "B nota", "contenido b")
    write_note(tmp_path, "A nota", "contenido a")
    (tmp_path / "roto.md").write_text("sin frontmatter")
    notes = list_vault_notes(tmp_path)
    assert {n.title for n in notes} == {"B nota", "A nota"}


def test_list_vault_notes_returns_empty_for_missing_vault(tmp_path):
    assert list_vault_notes(tmp_path / "no-existe") == []
```

Run: `pytest tests/test_vault.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'asistente_mikha.memory.vault'`.

- [ ] **Step 2: Implementar**

`src/asistente_mikha/memory/vault.py`:
```python
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml


@dataclass
class Note:
    path: Path
    title: str
    tags: list[str]
    created: str
    content: str

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


def slugify(title: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", title.lower()).strip()
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug or "nota"


def write_note(
    vault_path: Path, title: str, content: str, tags: list[str] | None = None
) -> Path:
    vault_path.mkdir(parents=True, exist_ok=True)
    tags = tags or []
    base_slug = slugify(title)
    slug = base_slug
    counter = 2
    while (vault_path / f"{slug}.md").exists():
        slug = f"{base_slug}-{counter}"
        counter += 1
    file_path = vault_path / f"{slug}.md"
    frontmatter = {
        "title": title,
        "tags": tags,
        "created": datetime.now().isoformat(timespec="seconds"),
    }
    text = (
        "---\n"
        + yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False)
        + "---\n\n"
        + content
        + "\n"
    )
    file_path.write_text(text, encoding="utf-8")
    return file_path


def parse_note(file_path: Path) -> Note | None:
    try:
        raw = file_path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not raw.startswith("---\n"):
        return None
    parts = raw.split("---\n", 2)
    if len(parts) < 3:
        return None
    _, frontmatter_text, body = parts
    try:
        frontmatter = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(frontmatter, dict) or "title" not in frontmatter:
        return None
    return Note(
        path=file_path,
        title=str(frontmatter.get("title", "")),
        tags=list(frontmatter.get("tags", []) or []),
        created=str(frontmatter.get("created", "")),
        content=body.strip(),
    )


def list_vault_notes(vault_path: Path) -> list[Note]:
    if not vault_path.exists():
        return []
    notes = []
    for md_file in sorted(vault_path.glob("*.md")):
        note = parse_note(md_file)
        if note is not None:
            notes.append(note)
    return notes
```

- [ ] **Step 3: Verificar que pasa**

Run: `pytest tests/test_vault.py -v`
Expected: 8 passed.

- [ ] **Step 4: Commit**

```bash
git add src/asistente_mikha/memory/__init__.py src/asistente_mikha/memory/vault.py tests/test_vault.py
git commit -m "feat: lectura/escritura de notas markdown con frontmatter"
```

---

## Task 3: Embeddings vía Ollama

**Files:**
- Create: `src/asistente_mikha/memory/embeddings.py`
- Test: `tests/test_embeddings.py`

**Interfaces:**
- Consumes: `get_ollama_base_url()` de `asistente_mikha.config` (Task 1).
- Produces: `EMBEDDING_MODEL: str`, `ollama_embed(text: str) -> list[float]`.

- [ ] **Step 1: Escribir test (falla primero)**

`tests/test_embeddings.py`:
```python
from asistente_mikha.memory import embeddings


def test_ollama_embed_sends_expected_request_and_parses_response(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [{"embedding": [0.1, 0.2, 0.3]}]}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr(embeddings.httpx, "post", fake_post)
    result = embeddings.ollama_embed("hola mundo")

    assert result == [0.1, 0.2, 0.3]
    assert captured["json"] == {"model": "nomic-embed-text", "input": "hola mundo"}
    assert captured["url"].endswith("/embeddings")
```

Run: `pytest tests/test_embeddings.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'asistente_mikha.memory.embeddings'`.

- [ ] **Step 2: Implementar**

`src/asistente_mikha/memory/embeddings.py`:
```python
from __future__ import annotations

import httpx

from asistente_mikha.config import get_ollama_base_url

EMBEDDING_MODEL = "nomic-embed-text"


def ollama_embed(text: str) -> list[float]:
    """Genera un embedding para `text` usando el endpoint OpenAI-compatible de Ollama."""
    response = httpx.post(
        f"{get_ollama_base_url()}/embeddings",
        json={"model": EMBEDDING_MODEL, "input": text},
        timeout=30.0,
    )
    response.raise_for_status()
    body = response.json()
    return body["data"][0]["embedding"]
```

- [ ] **Step 3: Verificar que pasa**

Run: `pytest tests/test_embeddings.py -v`
Expected: 1 passed.

- [ ] **Step 4: Verificar contra Ollama real (manual, no automatizado)**

Run:
```bash
python3 -c "
from asistente_mikha.memory.embeddings import ollama_embed
v = ollama_embed('hola mundo')
print(len(v), v[:3])
"
```
Expected: imprime `768 [...]` (o el tamaño real del modelo `nomic-embed-text`), sin errores. Requiere `ollama pull nomic-embed-text` ya hecho y `ollama serve` corriendo.

- [ ] **Step 5: Commit**

```bash
git add src/asistente_mikha/memory/embeddings.py tests/test_embeddings.py
git commit -m "feat: generacion de embeddings via endpoint OpenAI-compatible de Ollama"
```

---

## Task 4: Índice semántico del vault (Chroma)

**Files:**
- Create: `src/asistente_mikha/memory/index.py`
- Test: `tests/test_vault_indexer.py`

**Interfaces:**
- Consumes: `Note`, `list_vault_notes` de `asistente_mikha.memory.vault` (Task 2); acepta cualquier `Callable[[str], list[float]]` como función de embedding (no depende directamente de `ollama_embed`).
- Produces: `VaultIndexer` (constructor `(vault_path: Path, embed: Callable[[str], list[float]], client=None)`; métodos `sync() -> dict` con claves `added`, `updated`, `removed`, `total`; `search(query: str, limit: int = 5) -> list[dict]` con claves `title`, `path`, `excerpt`, `distance` por resultado).

- [ ] **Step 1: Escribir tests (fallan primero)**

`tests/test_vault_indexer.py`:
```python
from pathlib import Path

from asistente_mikha.memory.index import VaultIndexer
from asistente_mikha.memory.vault import write_note


def fake_embed(text: str) -> list[float]:
    return [float(len(text) % 7), float(text.count("a")), float(text.count("e"))]


def test_sync_indexes_new_notes(tmp_path):
    write_note(tmp_path, "Nota uno", "contenido con la palabra clave manzana")
    write_note(tmp_path, "Nota dos", "otro contenido distinto")
    indexer = VaultIndexer(tmp_path, embed=fake_embed)

    stats = indexer.sync()

    assert stats == {"added": 2, "updated": 0, "removed": 0, "total": 2}


def test_sync_skips_unchanged_notes_on_second_run(tmp_path):
    write_note(tmp_path, "Nota uno", "contenido sin cambios")
    indexer = VaultIndexer(tmp_path, embed=fake_embed)
    indexer.sync()

    stats = indexer.sync()

    assert stats["added"] == 0
    assert stats["updated"] == 0


def test_sync_removes_deleted_notes(tmp_path):
    path = write_note(tmp_path, "Nota a borrar", "contenido")
    indexer = VaultIndexer(tmp_path, embed=fake_embed)
    indexer.sync()
    path.unlink()

    stats = indexer.sync()

    assert stats["removed"] == 1
    assert stats["total"] == 0


def test_search_returns_empty_list_when_no_notes(tmp_path):
    indexer = VaultIndexer(tmp_path, embed=fake_embed)
    assert indexer.search("cualquier cosa") == []


def test_search_returns_note_with_expected_shape(tmp_path):
    write_note(tmp_path, "Nota manzana", "contenido de prueba")
    indexer = VaultIndexer(tmp_path, embed=fake_embed)
    indexer.sync()

    results = indexer.search("consulta cualquiera", limit=5)

    assert len(results) == 1
    assert set(results[0].keys()) == {"title", "path", "excerpt", "distance"}
    assert results[0]["title"] == "Nota manzana"
```

Run: `pytest tests/test_vault_indexer.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'asistente_mikha.memory.index'`.

- [ ] **Step 2: Implementar**

`src/asistente_mikha/memory/index.py`:
```python
from __future__ import annotations

from pathlib import Path
from typing import Callable

import chromadb

from asistente_mikha.memory.vault import list_vault_notes

EmbeddingFunction = Callable[[str], list[float]]

INDEX_DIRNAME = ".mikha-index"
COLLECTION_NAME = "notes"


def get_chroma_client(vault_path: Path) -> chromadb.ClientAPI:
    index_path = vault_path / INDEX_DIRNAME
    index_path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(index_path))


class VaultIndexer:
    def __init__(
        self,
        vault_path: Path,
        embed: EmbeddingFunction,
        client: chromadb.ClientAPI | None = None,
    ) -> None:
        self.vault_path = vault_path
        self.embed = embed
        self.client = client or get_chroma_client(vault_path)
        self.collection = self.client.get_or_create_collection(COLLECTION_NAME)

    def sync(self) -> dict:
        notes = list_vault_notes(self.vault_path)
        current_ids = {note.path.name for note in notes}
        existing = self.collection.get()
        existing_hashes = {
            id_: meta.get("content_hash")
            for id_, meta in zip(existing["ids"], existing["metadatas"])
        }

        added = 0
        updated = 0
        for note in notes:
            note_id = note.path.name
            if existing_hashes.get(note_id) == note.content_hash:
                continue
            embedding = self.embed(note.content)
            self.collection.upsert(
                ids=[note_id],
                embeddings=[embedding],
                documents=[note.content],
                metadatas=[
                    {
                        "title": note.title,
                        "tags": ",".join(note.tags),
                        "path": str(note.path),
                        "content_hash": note.content_hash,
                    }
                ],
            )
            if note_id in existing_hashes:
                updated += 1
            else:
                added += 1

        stale_ids = [id_ for id_ in existing_hashes if id_ not in current_ids]
        if stale_ids:
            self.collection.delete(ids=stale_ids)

        return {
            "added": added,
            "updated": updated,
            "removed": len(stale_ids),
            "total": len(notes),
        }

    def search(self, query: str, limit: int = 5) -> list[dict]:
        count = self.collection.count()
        if count == 0:
            return []
        query_embedding = self.embed(query)
        results = self.collection.query(
            query_embeddings=[query_embedding], n_results=min(limit, count)
        )
        found = []
        for doc, meta, distance in zip(
            results["documents"][0], results["metadatas"][0], results["distances"][0]
        ):
            found.append(
                {
                    "title": meta.get("title"),
                    "path": meta.get("path"),
                    "excerpt": doc[:280],
                    "distance": distance,
                }
            )
        return found
```

- [ ] **Step 3: Verificar que pasa**

Run: `pytest tests/test_vault_indexer.py -v`
Expected: 5 passed.

- [ ] **Step 4: Commit**

```bash
git add src/asistente_mikha/memory/index.py tests/test_vault_indexer.py
git commit -m "feat: indice semantico del vault con Chroma embebido"
```

---

## Task 5: Herramientas `save_note` y `search_notes`

**Files:**
- Create: `src/asistente_mikha/memory/tools.py`
- Test: `tests/test_memory_tools.py`

**Interfaces:**
- Consumes: `ToolRisk`, `tool` de `asistente_mikha.tools.registry` (Fase 1); `write_note` de `asistente_mikha.memory.vault` (Task 2); `ollama_embed` de `asistente_mikha.memory.embeddings` (Task 3); `VaultIndexer` de `asistente_mikha.memory.index` (Task 4); `get_vault_path` de `asistente_mikha.config` (Task 1).
- Produces: `save_note(title: str, content: str, tags: list[str] | None = None) -> dict`, `search_notes(query: str, limit: int = 5) -> list[dict]`, `get_indexer() -> VaultIndexer`, `reset_indexer_for_tests() -> None`.

- [ ] **Step 1: Escribir tests (fallan primero)**

`tests/test_memory_tools.py`:
```python
from pathlib import Path

from asistente_mikha.memory import tools as memory_tools


def fake_embed(text: str) -> list[float]:
    return [float(len(text))]


def failing_embed(text: str) -> list[float]:
    raise RuntimeError("ollama no disponible")


def test_save_note_writes_file_and_indexes(tmp_path, monkeypatch):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))
    memory_tools.reset_indexer_for_tests()
    monkeypatch.setattr(memory_tools, "ollama_embed", fake_embed)

    result = memory_tools.save_note(title="Idea nueva", content="contenido de la idea", tags=["ideas"])

    assert result["indexed"] is True
    assert Path(result["path"]).exists()

    found = memory_tools.search_notes(query="idea", limit=5)
    assert len(found) == 1
    assert found[0]["title"] == "Idea nueva"


def test_search_notes_returns_empty_on_embedding_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))
    memory_tools.reset_indexer_for_tests()
    monkeypatch.setattr(memory_tools, "ollama_embed", failing_embed)

    assert memory_tools.search_notes(query="algo") == []


def test_save_note_succeeds_even_if_indexing_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))
    memory_tools.reset_indexer_for_tests()
    monkeypatch.setattr(memory_tools, "ollama_embed", failing_embed)

    result = memory_tools.save_note(title="Nota resiliente", content="contenido")

    assert result["indexed"] is False
    assert Path(result["path"]).exists()
```

Run: `pytest tests/test_memory_tools.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'asistente_mikha.memory.tools'`.

- [ ] **Step 2: Implementar**

`src/asistente_mikha/memory/tools.py`:
```python
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
```

- [ ] **Step 3: Verificar que pasa**

Run: `pytest tests/test_memory_tools.py -v`
Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add src/asistente_mikha/memory/tools.py tests/test_memory_tools.py
git commit -m "feat: herramientas save_note y search_notes"
```

---

## Task 6: Integrar memoria en el agente

**Files:**
- Modify: `src/asistente_mikha/agent.py`
- Test: `tests/test_memory_integration.py`

**Interfaces:**
- Consumes: `save_note`, `search_notes` (Task 5, vía el registro compartido); `get_ollama_base_url` de `asistente_mikha.config` (Task 1).
- Produces: ninguna interfaz nueva — el agente ya construido en Fase 1 ahora tiene 2 herramientas más disponibles.

- [ ] **Step 1: Escribir test de integración (falla primero)**

`tests/test_memory_integration.py`:
```python
import pytest

from asistente_mikha.agent import run_turn, reset_sessions_for_tests
from asistente_mikha.memory import tools as memory_tools


@pytest.fixture(autouse=True)
def _clean_state(tmp_path, monkeypatch):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))
    memory_tools.reset_indexer_for_tests()
    reset_sessions_for_tests()
    yield
    memory_tools.reset_indexer_for_tests()
    reset_sessions_for_tests()


@pytest.mark.integration
async def test_agent_saves_and_finds_note():
    save_result = await run_turn(
        "memoria-test",
        "Guarda una nota titulada 'Idea de negocio' con el contenido: "
        "vender cafe de especialidad en el barrio.",
    )
    assert save_result.reply

    search_result = await run_turn(
        "memoria-test",
        "Busca en mis notas que tengo guardado sobre negocios de cafe.",
    )
    assert "café" in search_result.reply.lower() or "cafe" in search_result.reply.lower()
```

Run: `pytest tests/test_memory_integration.py -v -m integration`
Expected: FAIL — el agente aún no tiene las herramientas de memoria registradas (no encuentra la nota, o el assert de contenido falla).

- [ ] **Step 2: Modificar `agent.py`**

Reemplazar la línea de import de herramientas y el uso de `OLLAMA_BASE_URL`:

```python
# antes:
# OLLAMA_BASE_URL = "http://localhost:11434/v1"
# ...
# from asistente_mikha.tools import actions, diagnostics  # noqa: F401

# despues:
from asistente_mikha.config import get_ollama_base_url
# ...
from asistente_mikha.tools import actions, diagnostics  # noqa: F401
from asistente_mikha.memory import tools as memory_tools  # noqa: F401
```

Y en `_build_model`:
```python
def _build_model(model_name: str = DEFAULT_MODEL_NAME) -> OpenAIChatModel:
    provider = OpenAIProvider(base_url=get_ollama_base_url(), api_key="ollama")
    return OpenAIChatModel(model_name, provider=provider)
```

Eliminar la constante `OLLAMA_BASE_URL = "http://localhost:11434/v1"` (ya no se usa; el valor por defecto vive en `config.py`).

- [ ] **Step 3: Verificar que pasa (con Ollama y `nomic-embed-text` disponibles)**

Run: `pytest tests/test_memory_integration.py -v -m integration`
Expected: 1 passed.

- [ ] **Step 4: Correr toda la suite para confirmar que nada se rompio**

Run: `pytest -v`
Expected: todos los tests pasan (Fase 1 + Fase 2 hasta este punto).

- [ ] **Step 5: Commit**

```bash
git add src/asistente_mikha/agent.py tests/test_memory_integration.py
git commit -m "feat: integrar herramientas de memoria en el agente"
```

---

## Task 7: Sincronizar el vault al arrancar + endpoint de Phoenix configurable

**Files:**
- Modify: `src/asistente_mikha/main.py`
- Modify: `src/asistente_mikha/observability.py`
- Test: `tests/test_observability.py` (ampliar)

**Interfaces:**
- Consumes: `get_indexer` de `asistente_mikha.memory.tools` (Task 5); `get_phoenix_endpoint` de `asistente_mikha.config` (Task 1).
- Produces: ninguna interfaz nueva de cara afuera; cambia el comportamiento interno de `configure_tracing` y del `lifespan` de FastAPI.

- [ ] **Step 1: Escribir tests nuevos (fallan primero)**

Agregar a `tests/test_observability.py`:
```python
from unittest.mock import patch

from asistente_mikha import observability


def test_configure_tracing_uses_phoenix_endpoint_from_config(monkeypatch):
    monkeypatch.setenv("PHOENIX_ENDPOINT", "http://phoenix:6006/v1/traces")
    observability._tracing_configured = False
    captured = {}

    def fake_register(**kwargs):
        captured.update(kwargs)

    with patch("phoenix.otel.register", side_effect=fake_register):
        observability.configure_tracing()

    assert captured["endpoint"] == "http://phoenix:6006/v1/traces"
    observability._tracing_configured = False
```

Run: `pytest tests/test_observability.py -v`
Expected: FAIL — `configure_tracing` todavía usa un valor fijo, no lee `PHOENIX_ENDPOINT`.

- [ ] **Step 2: Modificar `observability.py`**

```python
from __future__ import annotations

from opentelemetry import trace
from opentelemetry.trace import Tracer

from asistente_mikha.config import get_phoenix_endpoint

TRACER_NAME = "asistente_mikha"

_tracing_configured = False


def configure_tracing(project_name: str = "asistente-mikha", endpoint: str | None = None) -> None:
    """Registra el TracerProvider global apuntando a un Phoenix local. Idempotente."""
    global _tracing_configured
    if _tracing_configured:
        return
    from phoenix.otel import register

    register(
        project_name=project_name,
        endpoint=endpoint or get_phoenix_endpoint(),
        auto_instrument=False,
    )
    _tracing_configured = True


def get_tracer() -> Tracer:
    return trace.get_tracer(TRACER_NAME)
```

- [ ] **Step 3: Verificar que pasa**

Run: `pytest tests/test_observability.py -v`
Expected: 2 passed (el test original de Fase 1 + el nuevo).

- [ ] **Step 4: Modificar `main.py` para sincronizar el vault al arrancar**

```python
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from asistente_mikha.api.routes import router
from asistente_mikha.memory.tools import get_indexer
from asistente_mikha.observability import configure_tracing


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_tracing()
    get_indexer().sync()
    yield


app = FastAPI(title="Asistente Mikha", lifespan=lifespan)
app.include_router(router)
```

- [ ] **Step 5: Verificar que la suite completa sigue pasando**

Run: `pytest -v`
Expected: todos los tests pasan, incluyendo `tests/test_api.py` (que levanta la app vía `TestClient` y ahora tambien dispara `get_indexer().sync()` al arrancar).

- [ ] **Step 6: Commit**

```bash
git add src/asistente_mikha/main.py src/asistente_mikha/observability.py tests/test_observability.py
git commit -m "feat: sincronizar vault al arrancar y endpoint de Phoenix configurable"
```

---

## Task 8: Dockerizar backend + Phoenix

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.dockerignore`
- Modify: `README.md`

**Interfaces:**
- Consumes: todo lo construido en Tasks 1-7 (variables de entorno `OLLAMA_BASE_URL`, `PHOENIX_ENDPOINT`, `MIKHA_VAULT_PATH` ya soportadas por el código).
- Produces: ninguna interfaz de código — es infraestructura de despliegue.

- [ ] **Step 1: Crear `.dockerignore`**

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
.git/
```

- [ ] **Step 2: Crear `Dockerfile`**

```dockerfile
FROM python:3.14-slim

# systemd se instala solo para obtener el binario `systemctl` (cliente),
# necesario para que restart_service hable con el D-Bus del host montado
# como volumen — el contenedor no ejecuta systemd como init.
RUN apt-get update \
    && apt-get install -y --no-install-recommends systemd \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -e .

EXPOSE 8000
CMD ["uvicorn", "asistente_mikha.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 3: Crear `docker-compose.yml`**

```yaml
services:
  phoenix:
    image: arizephoenix/phoenix:latest
    ports:
      - "6006:6006"
      - "4317:4317"
    volumes:
      - phoenix_data:/mnt/data
    restart: unless-stopped

  backend:
    build: .
    ports:
      - "8000:8000"
    environment:
      - OLLAMA_BASE_URL=http://host.docker.internal:11434/v1
      - PHOENIX_ENDPOINT=http://phoenix:6006/v1/traces
      - MIKHA_VAULT_PATH=/vault
      # UID 1000 es el usuario de esta maquina (ver Global Constraints).
      - DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
    volumes:
      - ${HOME}/Obsidian/Mikha:/vault
      - /run/user/1000/bus:/run/user/1000/bus
    extra_hosts:
      - "host.docker.internal:host-gateway"
    depends_on:
      - phoenix
    restart: unless-stopped

volumes:
  phoenix_data:
```

- [ ] **Step 4: Levantar y verificar manualmente**

Run:
```bash
docker compose up --build -d
sleep 5
curl -s http://localhost:8000/health
```
Expected: `{"status":"ok","ollama_reachable":true}` — confirma que el contenedor del backend alcanza a Ollama nativo del host vía `host.docker.internal`.

- [ ] **Step 5: Verificar que `restart_service` funciona a traves del contenedor**

Run:
```bash
curl -s -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"session_id":"docker-test","message":"Reinicia el servicio wireplumber."}'
```
Expected: respuesta JSON con `pending_action_ids` no vacio. Si falla con un error de D-Bus o `systemctl: command not found`, revisar el montaje del socket y la instalacion de `systemd` en el Dockerfile antes de continuar — no marcar esta tarea como terminada hasta que funcione.

Luego confirmar la accion pendiente:
```bash
curl -s -X POST "http://localhost:8000/confirm/<action_id>?approve=false"
```
(se usa `approve=false` para no reiniciar wireplumber de verdad en esta verificacion, igual que en el smoke test de Fase 1).

- [ ] **Step 6: Apagar los contenedores de prueba**

Run: `docker compose down`

- [ ] **Step 7: Actualizar `README.md`**

Agregar una sección después de "Correr el backend":
```markdown
## Correr con Docker (backend + Phoenix)

Ollama se queda corriendo nativo en el host (por la aceleración GPU). El
backend y Phoenix corren en contenedores:

\`\`\`bash
docker compose up --build
\`\`\`

Esto expone el backend en `http://localhost:8000` (igual que corriendo
`uvicorn` nativo) y Phoenix en `http://localhost:6006`. El vault de
Obsidian se monta desde `~/Obsidian/Mikha` — las notas que Mikha guarde
desde el contenedor son visibles inmediatamente en la app de Obsidian
del host.

El CLI (`mikha`) sigue corriendo nativo sin cambios, sin importar si el
backend está en Docker o no.
```

- [ ] **Step 8: Commit**

```bash
git add Dockerfile docker-compose.yml .dockerignore README.md
git commit -m "feat: dockerizar backend y Phoenix, Ollama se mantiene nativo"
```

---

## Self-Review (completado durante la escritura de este plan)

- **Cobertura del spec:** Vault (Task 2), embeddings (Task 3), índice Chroma (Task 4), herramientas `save_note`/`search_notes` (Task 5), integración en el agente (Task 6), sync al arrancar + Phoenix configurable (Task 7), Docker + conflicto D-Bus resuelto (Task 8), configuración centralizada (Task 1) que sostiene tanto el modo nativo como Docker. Sin huecos detectados.
- **Placeholders:** ninguno — cada step trae código completo y ejecutable, incluyendo el Dockerfile y docker-compose.yml reales.
- **Consistencia de tipos:** `VaultIndexer.sync()` devuelve siempre las claves `added`/`updated`/`removed`/`total` (usado igual en Task 4 y su test); `search()` devuelve siempre `title`/`path`/`excerpt`/`distance` (usado igual en Task 4 y Task 5); `save_note`/`search_notes` mantienen las firmas declaradas en la interfaz de Task 5 en todos los consumidores posteriores (Task 6, Task 7).
- **Riesgo técnico marcado explícitamente:** Task 8 Step 5 no se da por completada solo por escribir el código — requiere confirmar en vivo que `restart_service` funciona a través del contenedor, dado que la combinación systemd-en-slim-image + D-Bus montado no se había probado antes en este proyecto.
