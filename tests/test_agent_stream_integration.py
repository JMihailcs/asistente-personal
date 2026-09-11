import pytest

from asistente_mikha.agent import (
    AgentTurnResult,
    reset_sessions_for_tests,
    run_turn_stream,
)


@pytest.fixture(autouse=True)
def _clean_sessions():
    reset_sessions_for_tests()
    yield
    reset_sessions_for_tests()


@pytest.mark.integration
async def test_run_turn_stream_emits_deltas_then_result():
    deltas: list[str] = []
    final: AgentTurnResult | None = None

    async for item in run_turn_stream("stream-test", "Decime hola en una frase corta."):
        if isinstance(item, AgentTurnResult):
            final = item
        else:
            deltas.append(item)

    assert deltas, "se esperaba al menos un delta de texto"
    assert final is not None, "se esperaba un AgentTurnResult como ultimo elemento"
    assert final.reply == "".join(deltas)
    assert isinstance(final.pending_action_ids, list)
