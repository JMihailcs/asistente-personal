import pytest
from fastapi.testclient import TestClient

from asistente_mikha.confirmation import get_default_store, reset_default_store_for_tests
from asistente_mikha.main import app
from asistente_mikha.memory import tools as memory_tools
from asistente_mikha.memory.tasks import list_tasks
from asistente_mikha.memory.vault import list_vault_notes, write_note


@pytest.fixture(autouse=True)
def vault(monkeypatch, tmp_path):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))
    monkeypatch.setattr(memory_tools, "_resync_index", lambda: None)
    reset_default_store_for_tests()
    yield tmp_path
    reset_default_store_for_tests()


def _confirm(result):
    return get_default_store().execute(result["action_id"]).result


def test_delete_task_needs_confirmation(vault):
    memory_tools.tasks(action="add", list_name="Casa", text="lavar los platos")

    result = memory_tools.modify_data(action="delete_task", list_name="Casa", text="platos")

    assert result["status"] == "pending_confirmation"
    assert len(list_tasks(vault, "Casa").items) == 1
    assert _confirm(result)["status"] == "ok"
    assert list_tasks(vault, "Casa").items == []


def test_edit_task_keeps_done_state(vault):
    memory_tools.tasks(action="add", list_name="Casa", text="lavar")
    memory_tools.tasks(action="complete", list_name="Casa", text="lavar")

    result = memory_tools.modify_data(
        action="edit_task", list_name="Casa", text="lavar", new_text="lavar la ropa"
    )
    _confirm(result)

    item = list_tasks(vault, "Casa").items[0]
    assert (item.text, item.done) == ("lavar la ropa", True)


def test_task_not_found_and_ambiguous(vault):
    memory_tools.tasks(action="add", list_name="Casa", text="lavar platos\nlavar ropa")

    assert memory_tools.modify_data(
        action="delete_task", list_name="Casa", text="barrer"
    )["status"] == "not_found"
    ambiguous = memory_tools.modify_data(action="delete_task", list_name="Casa", text="lavar")
    assert ambiguous["status"] == "ambiguous"
    assert get_default_store().list_pending() == []


def test_edit_and_delete_note(vault):
    write_note(vault, "Idea", "contenido", ["a"])

    edit = memory_tools.modify_data(action="edit_note", note="idea", new_content="nuevo")
    assert edit["status"] == "pending_confirmation"
    assert list_vault_notes(vault)[0].content == "contenido"
    _confirm(edit)
    note = list_vault_notes(vault)[0]
    assert (note.content, note.tags) == ("nuevo", ["a"])

    delete = memory_tools.modify_data(action="delete_note", note="Idea")
    _confirm(delete)
    assert list_vault_notes(vault) == []


def test_missing_arguments_and_invalid_action(vault):
    assert memory_tools.modify_data(action="edit_note", note="x")["status"] == "missing_argument"
    assert memory_tools.modify_data(action="delete_task", list_name="Casa")["status"] == "missing_argument"
    assert memory_tools.propose_change("borrar_todo")["status"] == "invalid_action"


def test_ui_endpoint_only_proposes(vault):
    write_note(vault, "Idea", "contenido")
    with TestClient(app) as client:
        note_id = client.get("/notes/recent").json()["notes"][0]["id"]
        resp = client.post("/changes", json={"action": "delete_note", "note": note_id})
        assert resp.status_code == 200
        assert len(list_vault_notes(vault)) == 1
        client.post(f"/confirm/{resp.json()['action_id']}")
        assert list_vault_notes(vault) == []
        missing = client.post("/changes", json={"action": "delete_note", "note": "nope"})
        assert missing.status_code == 404
