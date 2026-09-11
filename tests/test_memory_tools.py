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
