from pathlib import Path

from asistente_mikha.memory import tools as memory_tools
from asistente_mikha.memory.turn_context import reset_user_message, set_user_message


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


def test_memory_router_dispatches_save_note(tmp_path, monkeypatch):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))
    memory_tools.reset_indexer_for_tests()
    monkeypatch.setattr(memory_tools, "ollama_embed", fake_embed)

    result = memory_tools.memory(action="save_note", title="Router", content="contenido")

    assert result["status"] == "ok"
    assert result["indexed"] is True
    assert Path(result["path"]).exists()


def test_memory_router_dispatches_search_notes(tmp_path, monkeypatch):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))
    memory_tools.reset_indexer_for_tests()
    monkeypatch.setattr(memory_tools, "ollama_embed", fake_embed)
    memory_tools.save_note(title="Idea", content="contenido de idea")

    found = memory_tools.memory(action="search_notes", query="idea")

    assert found["status"] == "ok"
    assert len(found["results"]) == 1
    assert found["results"][0]["title"] == "Idea"


def test_tasks_router_add_and_list(tmp_path, monkeypatch):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))

    added = memory_tools.tasks(action="add", list_name="Casa", text="lavar los platos")
    assert added["status"] == "ok"
    assert added["added"] == ["lavar los platos"]

    listed = memory_tools.tasks(action="list", list_name="Casa")
    assert listed["tasks"] == [{"text": "lavar los platos", "done": False}]


def test_tasks_router_list_returns_list_not_found(tmp_path, monkeypatch):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))

    result = memory_tools.tasks(action="list", list_name="No existe")

    assert result["status"] == "list_not_found"


def test_tasks_router_complete(tmp_path, monkeypatch):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))
    memory_tools.tasks(action="add", list_name="Casa", text="lavar los platos")

    result = memory_tools.tasks(action="complete", list_name="Casa", text="lavar")

    assert result["status"] == "ok"


def test_tasks_router_list_lists(tmp_path, monkeypatch):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))
    memory_tools.tasks(action="add", list_name="Casa", text="algo")

    result = memory_tools.tasks(action="list_lists")

    assert result["status"] == "ok"
    assert result["lists"] == ["Casa"]


def test_tasks_router_add_without_text_returns_missing_argument(tmp_path, monkeypatch):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))

    result = memory_tools.tasks(action="add", list_name="Casa")

    assert result["status"] == "missing_argument"
    assert result["required"] == ["text"]


def test_tasks_router_add_without_list_name_does_not_create_any_file(tmp_path, monkeypatch):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))

    result = memory_tools.tasks(action="add", text="comprar leche")

    assert result["status"] == "missing_argument"
    assert result["required"] == ["list_name"]
    assert not (tmp_path / "Tareas").exists()


def test_tasks_router_complete_without_text_returns_missing_argument(tmp_path, monkeypatch):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))

    result = memory_tools.tasks(action="complete", list_name="Casa")

    assert result["status"] == "missing_argument"
    assert result["required"] == ["text"]


def test_tasks_router_list_without_list_name_returns_missing_argument(tmp_path, monkeypatch):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))

    result = memory_tools.tasks(action="list")

    assert result["status"] == "missing_argument"
    assert result["required"] == ["list_name"]


def test_tasks_router_complete_without_text_does_not_complete_any_task(tmp_path, monkeypatch):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))
    memory_tools.tasks(action="add", list_name="Casa", text="lavar los platos")
    memory_tools.tasks(action="add", list_name="Casa", text="sacar la basura")

    result = memory_tools.tasks(action="complete", list_name="Casa")

    assert result["status"] == "missing_argument"
    assert result["required"] == ["text"]

    listed = memory_tools.tasks(action="list", list_name="Casa")
    assert listed["tasks"] == [
        {"text": "lavar los platos", "done": False},
        {"text": "sacar la basura", "done": False},
    ]


def test_tasks_add_to_unnamed_new_list_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))
    memory_tools.tasks(action="add", list_name="Casa", text="algo")
    token = set_user_message("Agrega la tarea comprar leche.")
    try:
        result = memory_tools.tasks(action="add", list_name="Compras", text="comprar leche")
    finally:
        reset_user_message(token)

    assert result["status"] == "list_not_specified"
    assert result["existing_lists"] == ["Casa"]
    assert not (tmp_path / "Tareas" / "compras.md").exists()


def test_tasks_add_creates_new_list_when_user_named_it(tmp_path, monkeypatch):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))
    token = set_user_message("Agrega 'llamar al plomero' a mi lista de Casa Nueva.")
    try:
        result = memory_tools.tasks(action="add", list_name="Casa Nueva", text="llamar al plomero")
    finally:
        reset_user_message(token)

    assert result["status"] == "ok"


def test_tasks_add_to_existing_list_needs_no_mention(tmp_path, monkeypatch):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))
    memory_tools.tasks(action="add", list_name="Casa", text="algo")
    token = set_user_message("Agrega la tarea comprar leche.")
    try:
        result = memory_tools.tasks(action="add", list_name="casa", text="comprar leche")
    finally:
        reset_user_message(token)

    assert result["status"] == "ok"


def test_tasks_add_list_name_must_match_whole_words(tmp_path, monkeypatch):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))
    token = set_user_message("Agrega comprar un regalo para el casamiento.")
    try:
        result = memory_tools.tasks(action="add", list_name="Casa", text="comprar un regalo")
    finally:
        reset_user_message(token)

    assert result["status"] == "list_not_specified"
    assert result["existing_lists"] == []
