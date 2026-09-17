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


# Este test llevo un xfail desde la Fase 3: mistral-nemo omitia `list_name`
# con frases como "a mi lista de Idea de negocio". La Fase 5 lo midio
# (0 de 5, sistematico, no intermitente) y cambio el modelo a qwen3:8b, que
# acierta este caso 5 de 5. Las aserciones siguen verificando el archivo real
# en disco, no solo el texto de la respuesta. Si vuelve a fallar, mirar
# primero a que modelo apunta el alias 'default'.
@pytest.mark.integration
async def test_agent_adds_and_lists_task(tmp_path):
    add_result = await run_turn(
        "tasks-test",
        "Agrega la tarea 'comprar granos de cafe' a mi lista de Idea de negocio.",
    )
    assert add_result.reply

    tareas_dir = tmp_path / "Tareas"
    assert tareas_dir.exists()
    written_files = list(tareas_dir.glob("*.md"))
    assert written_files
    contents = "\n".join(f.read_text(encoding="utf-8").lower() for f in written_files)
    assert "comprar granos de cafe" in contents or "comprar granos de café" in contents

    list_result = await run_turn(
        "tasks-test",
        "Que tareas tengo en mi lista de Idea de negocio?",
    )
    assert "cafe" in list_result.reply.lower() or "café" in list_result.reply.lower()
