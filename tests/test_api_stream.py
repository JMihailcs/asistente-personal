import json

import pytest
from fastapi.testclient import TestClient

from asistente_mikha.main import app


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))
    from asistente_mikha.memory import tools as memory_tools

    memory_tools.reset_indexer_for_tests()

    async def fake_stream(session_id: str, message: str):
        from asistente_mikha.agent import AgentTurnResult

        yield "Hola "
        yield "mundo"
        yield AgentTurnResult(reply="Hola mundo", pending_action_ids=["abc123"])

    monkeypatch.setattr("asistente_mikha.api.routes.run_turn_stream", fake_stream)
    with TestClient(app) as test_client:
        yield test_client
    memory_tools.reset_indexer_for_tests()


def _parse_sse(raw: str) -> list[tuple[str, dict]]:
    events = []
    for block in raw.strip().split("\n\n"):
        name, payload = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[len("event: ") :]
            elif line.startswith("data: "):
                payload = json.loads(line[len("data: ") :])
        if name is not None:
            events.append((name, payload))
    return events


def test_chat_stream_emits_tokens_then_done(client):
    response = client.post("/chat/stream", json={"session_id": "s1", "message": "hola"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(response.text)
    names = [name for name, _ in events]
    assert names == ["token", "token", "done"]
    assert [p["text"] for name, p in events if name == "token"] == ["Hola ", "mundo"]

    done = events[-1][1]
    assert done["reply"] == "Hola mundo"
    assert done["pending_action_ids"] == ["abc123"]
    assert done["duration_seconds"] >= 0
    assert done["queried_at"]


def _client_que_falla(monkeypatch, tmp_path, error: Exception):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))
    from asistente_mikha.memory import tools as memory_tools

    memory_tools.reset_indexer_for_tests()

    async def stream_que_falla(session_id: str, message: str):
        raise error
        yield  # pragma: no cover - lo vuelve generador async

    monkeypatch.setattr("asistente_mikha.api.routes.run_turn_stream", stream_que_falla)
    return TestClient(app)


def test_una_falla_del_modelo_llega_como_evento_de_error(monkeypatch, tmp_path):
    # Sin esto el generador muere despues de mandar los headers 200 y el
    # cliente se queda esperando para siempre: 200 OK y cero bytes.
    from pydantic_ai.exceptions import ModelAPIError

    with _client_que_falla(
        monkeypatch, tmp_path, ModelAPIError(model_name="default", message="Connection error.")
    ) as client:
        response = client.post("/chat/stream", json={"session_id": "s1", "message": "hola"})

    assert response.status_code == 200
    eventos = _parse_sse(response.text)
    assert [n for n, _ in eventos] == ["error"]
    assert eventos[0][1]["message"]


def test_el_error_de_ollama_caido_dice_como_levantarlo(monkeypatch, tmp_path):
    from pydantic_ai.exceptions import ModelAPIError

    with _client_que_falla(
        monkeypatch, tmp_path, ModelAPIError(model_name="default", message="Connection error.")
    ) as client:
        response = client.post("/chat/stream", json={"session_id": "s1", "message": "hola"})

    mensaje = _parse_sse(response.text)[0][1]["message"]
    assert "ollama" in mensaje.lower()
    assert "serve" in mensaje


def test_el_error_de_modelo_faltante_nombra_el_modelo_y_el_alias(monkeypatch, tmp_path):
    from pydantic_ai.exceptions import ModelAPIError

    with _client_que_falla(
        monkeypatch,
        tmp_path,
        ModelAPIError(model_name="default", message='model "default" not found, try pulling it first'),
    ) as client:
        response = client.post("/chat/stream", json={"session_id": "s1", "message": "hola"})

    mensaje = _parse_sse(response.text)[0][1]["message"]
    assert "default" in mensaje
    assert "ollama cp" in mensaje


def test_una_falla_a_mitad_del_stream_no_pierde_los_tokens_ya_emitidos(monkeypatch, tmp_path):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))
    from asistente_mikha.memory import tools as memory_tools

    memory_tools.reset_indexer_for_tests()

    async def stream_que_corta(session_id: str, message: str):
        yield "Hola "
        raise RuntimeError("se corto a mitad")

    monkeypatch.setattr("asistente_mikha.api.routes.run_turn_stream", stream_que_corta)

    with TestClient(app) as client:
        response = client.post("/chat/stream", json={"session_id": "s1", "message": "hola"})

    assert [n for n, _ in _parse_sse(response.text)] == ["token", "error"]
