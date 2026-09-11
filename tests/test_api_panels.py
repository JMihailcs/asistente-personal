import pytest
from fastapi.testclient import TestClient

from asistente_mikha.confirmation import (
    get_default_store,
    register_implementation,
    reset_default_store_for_tests,
)
from asistente_mikha.main import app


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))
    from asistente_mikha.memory import tools as memory_tools

    memory_tools.reset_indexer_for_tests()
    reset_default_store_for_tests()
    with TestClient(app) as test_client:
        yield test_client
    memory_tools.reset_indexer_for_tests()
    reset_default_store_for_tests()


def test_system_endpoint_returns_all_three_readings(client):
    body = client.get("/system").json()

    assert body["ram"]["total_gb"] > 0
    assert body["disk"]["path"] == "/"
    assert "available" in body["gpu"]


def test_tasks_endpoint_returns_lists_with_items(client):
    from asistente_mikha.memory import tools as memory_tools

    memory_tools.tasks(action="add", list_name="Casa", text="lavar los platos")

    body = client.get("/tasks").json()

    assert body["lists"] == [
        {"name": "Casa", "tasks": [{"text": "lavar los platos", "done": False}]}
    ]


def test_tasks_endpoint_empty_when_no_lists(client):
    assert client.get("/tasks").json() == {"lists": []}


def test_notes_recent_returns_newest_first(client, tmp_path):
    from asistente_mikha.memory.vault import write_note

    write_note(tmp_path, "Vieja", "contenido viejo")
    write_note(tmp_path, "Nueva", "contenido nuevo")

    body = client.get("/notes/recent").json()

    titles = [n["title"] for n in body["notes"]]
    assert set(titles) == {"Vieja", "Nueva"}
    assert len(body["notes"]) <= 5


def test_pending_actions_endpoint(client):
    register_implementation("dummy_tool", lambda: {"ok": True})
    action = get_default_store().create("dummy_tool", {"service_name": "wireplumber"})

    body = client.get("/actions/pending").json()

    assert body["actions"] == [
        {
            "action_id": action.action_id,
            "tool_name": "dummy_tool",
            "kwargs": {"service_name": "wireplumber"},
        }
    ]
