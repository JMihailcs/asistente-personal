from pathlib import Path

from asistente_mikha.evals.cases import SIN_HERRAMIENTA, load_cases

CASOS = Path("evals/casos")
HERRAMIENTAS = {"diagnostics", "system_action", "memory", "tasks", SIN_HERRAMIENTA}


def test_los_casos_reales_cargan():
    # Un caso mal escrito tiene que explotar aca, en milisegundos, y no a
    # la hora y media de barrido.
    assert len(load_cases(CASOS)) >= 20


def test_todos_apuntan_a_una_herramienta_que_existe():
    for caso in load_cases(CASOS):
        assert caso.espera.herramienta in HERRAMIENTAS, caso.id


def test_hay_casos_de_cada_dimension():
    casos = load_cases(CASOS)

    assert any(c.espera.herramienta == SIN_HERRAMIENTA for c in casos)
    assert any(c.espera.archivos for c in casos)
    assert any(c.espera.fundamentada for c in casos)
    assert any(c.espera.respuesta_pregunta for c in casos)


def test_cada_caso_que_espera_herramienta_declara_argumentos():
    # Sin argumentos esperados, la dimension 'argumentos' es un aprobado
    # automatico y el numero no significa nada.
    for caso in load_cases(CASOS):
        if caso.espera.herramienta != SIN_HERRAMIENTA:
            assert caso.espera.argumentos, caso.id
