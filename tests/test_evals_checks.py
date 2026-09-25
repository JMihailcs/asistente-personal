from asistente_mikha.evals.cases import ExpectedFile
from asistente_mikha.evals.checks import (
    ToolCall,
    argumentos_correctos,
    efecto_correcto,
    eligio_herramienta,
    normalizar,
    respuesta_ok,
)


def test_normalizar_pliega_acentos_mayusculas_y_espacios():
    assert normalizar("  Idea  de NEGOCIO ") == "idea de negocio"
    assert normalizar("café") == "cafe"


def test_eligio_la_herramienta_esperada():
    llamadas = [ToolCall(name="tasks", args={}, result={})]

    assert eligio_herramienta(llamadas, "tasks").ok is True


def test_no_eligio_ninguna_cuando_se_esperaba_una():
    veredicto = eligio_herramienta([], "tasks")

    assert veredicto.ok is False
    assert "ninguna" in veredicto.motivo


def test_eligio_la_herramienta_equivocada():
    llamadas = [ToolCall(name="memory", args={}, result={})]

    veredicto = eligio_herramienta(llamadas, "tasks")

    assert veredicto.ok is False
    assert "memory" in veredicto.motivo


def test_no_llamar_ninguna_cuando_no_corresponde_es_acierto():
    assert eligio_herramienta([], "ninguna").ok is True


def test_llamar_una_herramienta_cuando_no_correspondia_es_fallo():
    llamadas = [ToolCall(name="tasks", args={}, result={})]

    veredicto = eligio_herramienta(llamadas, "ninguna")

    assert veredicto.ok is False
    assert "tasks" in veredicto.motivo


def test_argumentos_compara_por_subconjunto():
    # Los argumentos de mas no penalizan: solo importa que este lo pedido.
    llamadas = [ToolCall(name="tasks", args={"action": "add", "list_name": "Casa", "extra": 1}, result={})]

    assert argumentos_correctos(llamadas, "tasks", {"action": "add"}).ok is True


def test_argumentos_normaliza_el_texto():
    # "Idea de negocio" e "idea de NEGOCIO" son la misma lista.
    llamadas = [ToolCall(name="tasks", args={"list_name": "idea de NEGOCIO"}, result={})]

    assert argumentos_correctos(llamadas, "tasks", {"list_name": "Idea de negocio"}).ok is True


def test_argumentos_detecta_el_que_falta():
    llamadas = [ToolCall(name="tasks", args={"action": "add"}, result={})]

    veredicto = argumentos_correctos(llamadas, "tasks", {"action": "add", "list_name": "Casa"})

    assert veredicto.ok is False
    assert "list_name" in veredicto.motivo


def test_argumentos_detecta_el_valor_distinto():
    llamadas = [ToolCall(name="tasks", args={"action": "list"}, result={})]

    veredicto = argumentos_correctos(llamadas, "tasks", {"action": "add"})

    assert veredicto.ok is False
    assert "add" in veredicto.motivo and "list" in veredicto.motivo


def test_efecto_encuentra_el_archivo_escrito(tmp_path):
    (tmp_path / "Tareas").mkdir()
    (tmp_path / "Tareas" / "casa.md").write_text("# Casa\n\n- [ ] sacar la basura\n", encoding="utf-8")

    esperados = [ExpectedFile(patron="Tareas/*.md", contiene="sacar la basura")]

    assert efecto_correcto(tmp_path, esperados).ok is True


def test_efecto_falla_si_no_hay_archivo(tmp_path):
    veredicto = efecto_correcto(tmp_path, [ExpectedFile(patron="Tareas/*.md", contiene="lo que sea")])

    assert veredicto.ok is False
    assert "Tareas/*.md" in veredicto.motivo


def test_efecto_falla_si_el_archivo_no_tiene_el_texto(tmp_path):
    (tmp_path / "Tareas").mkdir()
    (tmp_path / "Tareas" / "casa.md").write_text("# Casa\n\n- [ ] otra cosa\n", encoding="utf-8")

    veredicto = efecto_correcto(tmp_path, [ExpectedFile(patron="Tareas/*.md", contiene="sacar la basura")])

    assert veredicto.ok is False
    assert "sacar la basura" in veredicto.motivo


def test_efecto_sin_expectativas_es_acierto(tmp_path):
    assert efecto_correcto(tmp_path, []).ok is True


def test_respuesta_ok_exige_las_subcadenas():
    assert respuesta_ok("Tenes 3 tareas", ["3 tareas"], False).ok is True
    assert respuesta_ok("Tenes 3 tareas", ["4 tareas"], False).ok is False


def test_respuesta_ok_exige_pregunta_cuando_se_pide():
    assert respuesta_ok("¿A que lista la agrego?", [], True).ok is True
    assert respuesta_ok("La agregue a Casa.", [], True).ok is False


import pytest

from asistente_mikha.evals.checks import fundamentada


def _ram():
    return [ToolCall(
        name="diagnostics",
        args={"check": "ram"},
        result={"status": "ok", "total_gb": 31.23, "used_gb": 16.57, "available_gb": 14.66},
    )]


def test_una_respuesta_sin_numeros_esta_fundamentada():
    assert fundamentada("Todo en orden.", _ram()).ok is True


def test_los_valores_exactos_estan_fundamentados():
    assert fundamentada("Tenes 31.23 GB en total y 16.57 usados.", _ram()).ok is True


@pytest.mark.parametrize("texto", ["unos 31 GB", "31.2 GB", "31,2 GB", "casi 31.5 GB"])
def test_el_redondeo_razonable_esta_fundamentado(texto):
    # 'unos 31 GB' sobre un valor de 31.23 es correcto, no una invencion.
    assert fundamentada(f"Tenes {texto} de RAM.", _ram()).ok is True


def test_un_numero_inventado_se_detecta():
    veredicto = fundamentada("Tenes 45 GB de RAM.", _ram())

    assert veredicto.ok is False
    assert "45" in veredicto.motivo


def test_el_tamano_de_una_coleccion_esta_fundamentado():
    llamadas = [ToolCall(
        name="tasks",
        args={"action": "list_lists"},
        result={"status": "ok", "lists": ["Casa", "Compras", "Idea de negocio"]},
    )]

    assert fundamentada("Tenes 3 listas.", llamadas).ok is True


def test_los_enteros_chicos_son_lenguaje_y_no_datos():
    # "un par de cosas", "los 2 primeros": no son cifras reportadas.
    assert fundamentada("Te menciono 2 cosas.", _ram()).ok is True


def test_sin_ninguna_llamada_un_numero_grande_es_invencion():
    veredicto = fundamentada("Tenes 512 GB libres.", [])

    assert veredicto.ok is False
    assert "512" in veredicto.motivo


def test_busca_en_valores_anidados_del_resultado():
    llamadas = [ToolCall(
        name="diagnostics",
        args={"check": "processes"},
        result={"status": "ok", "processes": [{"pid": 2721251, "rss_mb": 1843.5}]},
    )]

    assert fundamentada("El proceso 2721251 usa 1843.5 MB.", llamadas).ok is True


def test_sin_efecto_falla_si_aparece_un_archivo_prohibido(tmp_path):
    from asistente_mikha.evals.checks import sin_efecto

    assert sin_efecto(tmp_path, ["Tareas/*.md"]).ok
    (tmp_path / "Tareas").mkdir()
    (tmp_path / "Tareas" / "compras.md").write_text("# Compras\n")
    assert not sin_efecto(tmp_path, ["Tareas/*.md"]).ok


def test_cualquier_herramienta_no_exige_ni_prohibe():
    from asistente_mikha.evals.checks import eligio_herramienta

    assert eligio_herramienta([], "cualquiera").ok
