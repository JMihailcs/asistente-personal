import pytest
from fastapi.testclient import TestClient

from asistente_mikha.agent import reset_sessions_for_tests
from asistente_mikha.confirmation import reset_default_store_for_tests
from asistente_mikha.main import app
from asistente_mikha.memory import tools as memory_tools


@pytest.fixture(autouse=True)
def _clean_state(tmp_path, monkeypatch):
    # El lifespan de la app sincroniza el vault al arrancar; sin esto,
    # este test tocaria el vault real de Obsidian del usuario.
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))
    memory_tools.reset_indexer_for_tests()
    reset_default_store_for_tests()
    reset_sessions_for_tests()
    yield
    memory_tools.reset_indexer_for_tests()
    reset_default_store_for_tests()
    reset_sessions_for_tests()


@pytest.mark.integration
def test_full_flow_diagnose_then_confirm_action():
    with TestClient(app) as client:
        chat_response = client.post(
            "/chat",
            json={"session_id": "e2e-1", "message": "¿Cuánta RAM tengo disponible?"},
        )
        assert chat_response.status_code == 200
        assert chat_response.json()["reply"]

        action_response = client.post(
            "/chat",
            json={
                "session_id": "e2e-1",
                "message": "Reinicia el servicio wireplumber.",
            },
        )
        assert action_response.status_code == 200
        pending_ids = action_response.json()["pending_action_ids"]
        assert pending_ids, "se esperaba una acción pendiente para restart_service"

        confirm_response = client.post(f"/confirm/{pending_ids[0]}", params={"approve": False})
        assert confirm_response.status_code == 200
        assert confirm_response.json()["status"] == "rejected"
