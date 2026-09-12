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
