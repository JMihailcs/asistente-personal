from asistente_mikha.agent import build_agent


def test_el_agente_apaga_el_razonamiento_del_modelo():
    # Fase 5: qwen3:8b sin thinking acierta 21 de 22 casos a 3.9s, contra
    # 100% a 17.1s con thinking. Se eligio la velocidad. Si esto se pierde,
    # cada respuesta vuelve a tardar 4 veces mas sin que nadie lo note.
    agente = build_agent()

    assert agente.model_settings["openai_reasoning_effort"] == "none"


def test_el_agente_sigue_siendo_determinista():
    assert build_agent().model_settings["temperature"] == 0.0


def test_la_fecha_se_inyecta_con_reloj_inyectable_y_dia_de_la_semana():
    from datetime import datetime, timezone

    from asistente_mikha.agent import instrucciones_de_fecha

    texto = instrucciones_de_fecha(datetime(2026, 9, 24, 10, 30, tzinfo=timezone.utc))

    assert "jueves 24 de septiembre de 2026" in texto
    assert "el siguiente mes" in texto


def test_el_agente_usa_el_reloj_en_cada_turno():
    import asyncio
    from datetime import datetime, timezone

    from pydantic_ai.messages import ModelResponse, TextPart
    from pydantic_ai.models.function import FunctionModel

    vistas = []

    def modelo(mensajes, info):
        vistas.append(info.instructions)
        return ModelResponse(parts=[TextPart("ok")])

    fechas = iter([datetime(2026, 1, 5, tzinfo=timezone.utc), datetime(2026, 2, 6, tzinfo=timezone.utc)])
    agente = build_agent(reloj=lambda: next(fechas))

    with agente.override(model=FunctionModel(modelo)):
        asyncio.run(agente.run("hola"))
        asyncio.run(agente.run("hola"))

    assert "5 de enero de 2026" in vistas[0]
    assert "6 de febrero de 2026" in vistas[1]
