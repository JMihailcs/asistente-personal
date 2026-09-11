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
