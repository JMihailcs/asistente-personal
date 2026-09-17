import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from asistente_mikha.evals.variants import VARIANTES, con_motivo


def _esquema_de(func):
    agent = Agent(TestModel())
    agent.tool_plain(func)
    herramienta = list(agent._function_toolset.tools.values())[0]
    return herramienta.function_schema.json_schema


def ejemplo(action: str, list_name: str = "") -> dict:
    """Una herramienta de ejemplo."""
    return {"status": "ok", "action": action, "list_name": list_name}


def test_las_variantes_estan_declaradas():
    assert VARIANTES == ("baseline", "cot_prompt", "cot_arg", "two_step", "no_think")


def test_con_motivo_agrega_el_parametro_como_obligatorio():
    esquema = _esquema_de(con_motivo(ejemplo))

    assert "motivo" in esquema["properties"]
    assert "motivo" in esquema["required"]


def test_con_motivo_conserva_los_argumentos_originales():
    esquema = _esquema_de(con_motivo(ejemplo))

    assert "action" in esquema["properties"]
    assert "list_name" in esquema["properties"]
    assert "action" in esquema["required"]


def test_la_herramienta_sin_envolver_no_tiene_motivo():
    # El baseline tiene que quedar intacto: si no, no es baseline.
    esquema = _esquema_de(ejemplo)

    assert "motivo" not in esquema["properties"]


def test_con_motivo_ejecuta_la_funcion_original_ignorando_el_motivo():
    envuelta = con_motivo(ejemplo)

    assert envuelta(motivo="porque si", action="add", list_name="Casa") == {
        "status": "ok",
        "action": "add",
        "list_name": "Casa",
    }


def test_construir_agente_rechaza_una_variante_desconocida():
    from asistente_mikha.evals.variants import construir_agente

    with pytest.raises(ValueError) as error:
        construir_agente("un-modelo", "no-existe")

    assert "no-existe" in str(error.value)


def test_no_think_apaga_el_razonamiento_del_modelo():
    from asistente_mikha.evals.variants import construir_agente

    agente = construir_agente("qwen3:8b", "no_think")

    assert agente.model_settings["openai_reasoning_effort"] == "none"
    assert agente.model_settings["temperature"] == 0.0


def test_las_demas_variantes_no_tocan_el_razonamiento():
    # Si baseline apagara el thinking, la comparacion no mediria nada.
    from asistente_mikha.evals.variants import construir_agente

    agente = construir_agente("qwen3:8b", "baseline")

    assert "openai_reasoning_effort" not in agente.model_settings
