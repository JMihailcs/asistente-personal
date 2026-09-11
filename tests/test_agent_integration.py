import pytest

from asistente_mikha.agent import run_turn, reset_sessions_for_tests


@pytest.fixture(autouse=True)
def _clean_sessions():
    reset_sessions_for_tests()
    yield
    reset_sessions_for_tests()


@pytest.mark.integration
async def test_agent_answers_ram_question_using_real_tool():
    result = await run_turn("test-session", "¿Cuánta RAM tengo disponible ahora mismo?")
    assert result.reply
    assert "GB" in result.reply or "%" in result.reply


@pytest.mark.integration
async def test_agent_creates_pending_action_for_restart_service():
    result = await run_turn(
        "test-session-2",
        "Reinicia el servicio wireplumber por favor.",
    )
    assert result.pending_action_ids, "se esperaba al menos una acción pendiente"
