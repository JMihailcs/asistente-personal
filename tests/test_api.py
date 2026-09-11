import pytest
from fastapi.testclient import TestClient

from asistente_mikha.api.routes import _ollama_health_url
from asistente_mikha.confirmation import (
    get_default_store,
    register_implementation,
    reset_default_store_for_tests,
)
from asistente_mikha.main import app


@pytest.fixture(autouse=True)
def _clean_store():
    reset_default_store_for_tests()
    yield
    reset_default_store_for_tests()


@pytest.fixture
def client(monkeypatch, tmp_path):
    # El lifespan de la app sincroniza el vault al arrancar; sin esto,
    # los tests tocarian el vault real de Obsidian del usuario.
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))
    from asistente_mikha.memory import tools as memory_tools

    memory_tools.reset_indexer_for_tests()

    async def fake_run_turn(session_id: str, message: str):
        from asistente_mikha.agent import AgentTurnResult

        return AgentTurnResult(reply=f"eco: {message}", pending_action_ids=[])

    monkeypatch.setattr("asistente_mikha.api.routes.run_turn", fake_run_turn)
    with TestClient(app) as test_client:
        yield test_client
    memory_tools.reset_indexer_for_tests()


def test_chat_endpoint_returns_agent_reply(client):
    response = client.post("/chat", json={"session_id": "s1", "message": "hola"})
    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "eco: hola"
    assert body["pending_action_ids"] == []


def test_chat_endpoint_returns_timing_metadata(client):
    from datetime import datetime

    response = client.post("/chat", json={"session_id": "s1", "message": "hola"})
    body = response.json()
    assert isinstance(body["duration_seconds"], (int, float))
    assert body["duration_seconds"] >= 0
    datetime.fromisoformat(body["queried_at"])  # no debe lanzar


def test_confirm_endpoint_approves_pending_action(client):
    register_implementation("dummy_tool", lambda: {"ok": True})
    action = get_default_store().create("dummy_tool", {})
    response = client.post(f"/confirm/{action.action_id}", params={"approve": True})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "confirmed"
    assert body["result"] == {"ok": True}


def test_confirm_endpoint_rejects_when_approve_false(client):
    action = get_default_store().create("dummy_tool", {})
    response = client.post(f"/confirm/{action.action_id}", params={"approve": False})
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


def test_confirm_endpoint_unknown_action_returns_404(client):
    response = client.post("/confirm/no-existe", params={"approve": True})
    assert response.status_code == 404


def test_health_endpoint_returns_structure(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "ollama_reachable" in body


def test_ollama_health_url_derives_from_configured_base_url(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1")
    assert _ollama_health_url() == "http://host.docker.internal:11434/api/tags"


def test_ollama_health_url_default(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    assert _ollama_health_url() == "http://localhost:11434/api/tags"
