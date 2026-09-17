from asistente_mikha.agent import build_agent


def test_el_agente_apaga_el_razonamiento_del_modelo():
    # Fase 5: qwen3:8b sin thinking acierta 21 de 22 casos a 3.9s, contra
    # 100% a 17.1s con thinking. Se eligio la velocidad. Si esto se pierde,
    # cada respuesta vuelve a tardar 4 veces mas sin que nadie lo note.
    agente = build_agent()

    assert agente.model_settings["openai_reasoning_effort"] == "none"


def test_el_agente_sigue_siendo_determinista():
    assert build_agent().model_settings["temperature"] == 0.0
