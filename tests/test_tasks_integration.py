import pytest

from asistente_mikha.agent import run_turn, reset_sessions_for_tests


@pytest.fixture(autouse=True)
def _clean_state(tmp_path, monkeypatch):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))
    reset_sessions_for_tests()
    yield
    reset_sessions_for_tests()


@pytest.mark.integration
async def test_agent_adds_and_lists_task():
    add_result = await run_turn(
        "tasks-test",
        "Agrega la tarea 'comprar granos de cafe' a mi lista de Idea de negocio.",
    )
    assert add_result.reply

    list_result = await run_turn(
        "tasks-test",
        "Que tareas tengo en mi lista de Idea de negocio?",
    )
    assert "cafe" in list_result.reply.lower() or "café" in list_result.reply.lower()
