import json

from asistente_mikha.evals.cases import EvalCase, Expectation
from asistente_mikha.evals.runner import (
    barrer,
    claves_hechas,
    ejecutar_corrida,
    preparar_vault,
    veredictos_de,
)
from asistente_mikha.evals.variants import TurnOutcome


def _caso(**extra):
    campos = {
        "id": "un-caso",
        "mensaje": "hola",
        "espera": Expectation(herramienta="ninguna"),
    }
    campos.update(extra)
    return EvalCase(**campos)


def test_preparar_vault_escribe_las_listas_iniciales(tmp_path):
    preparar_vault(tmp_path, {"tareas": {"Casa": ["lavar los platos", "sacar la basura"]}})

    contenido = (tmp_path / "Tareas" / "casa.md").read_text(encoding="utf-8")
    assert contenido.startswith("# Casa")
    assert "- [ ] lavar los platos" in contenido
    assert "- [ ] sacar la basura" in contenido


def test_preparar_vault_sin_nada_que_preparar_no_rompe(tmp_path):
    preparar_vault(tmp_path, {})

    assert not (tmp_path / "Tareas").exists()


def test_veredictos_cubren_las_cinco_dimensiones(tmp_path):
    resultado = TurnOutcome(respuesta="Hola.", llamadas=[])

    veredictos = veredictos_de(_caso(), resultado, tmp_path)

    assert set(veredictos) == {
        "herramienta",
        "argumentos",
        "efecto",
        "respuesta",
        "fundamentada",
    }
    assert all("ok" in v and "motivo" in v for v in veredictos.values())


def test_la_dimension_no_pedida_cuenta_como_acierto(tmp_path):
    # Un caso que no declara 'fundamentada' no puede fallar por eso.
    veredictos = veredictos_de(_caso(), TurnOutcome(respuesta="Tengo 999 cosas."), tmp_path)

    assert veredictos["fundamentada"]["ok"] is True


def test_la_dimension_pedida_si_puede_fallar(tmp_path):
    caso = _caso(espera=Expectation(herramienta="ninguna", fundamentada=True))

    veredictos = veredictos_de(caso, TurnOutcome(respuesta="Tengo 999 GB."), tmp_path)

    assert veredictos["fundamentada"]["ok"] is False


async def test_ejecutar_corrida_produce_una_fila_completa(tmp_path, monkeypatch):
    async def turno_falso(modelo, variante, mensaje):
        return TurnOutcome(respuesta="listo", llamadas=[])

    monkeypatch.setattr("asistente_mikha.evals.runner.ejecutar_turno", turno_falso)

    fila = await ejecutar_corrida(_caso(), "un-modelo", "baseline", 0, tmp_path)

    assert fila["modelo"] == "un-modelo"
    assert fila["variante"] == "baseline"
    assert fila["caso"] == "un-caso"
    assert fila["repeticion"] == 0
    assert fila["respuesta"] == "listo"
    assert fila["error"] is None
    assert fila["latencia_s"] >= 0
    assert fila["veredictos"]["herramienta"]["ok"] is True


async def test_una_corrida_que_explota_queda_registrada_y_no_corta_el_barrido(tmp_path, monkeypatch):
    async def turno_que_explota(modelo, variante, mensaje):
        raise RuntimeError("ollama se cayo")

    monkeypatch.setattr("asistente_mikha.evals.runner.ejecutar_turno", turno_que_explota)

    fila = await ejecutar_corrida(_caso(), "un-modelo", "baseline", 0, tmp_path)

    assert "ollama se cayo" in fila["error"]
    assert all(v["ok"] is False for v in fila["veredictos"].values())


async def test_barrer_escribe_una_linea_por_corrida(tmp_path, monkeypatch):
    async def turno_falso(modelo, variante, mensaje):
        return TurnOutcome(respuesta="listo", llamadas=[])

    monkeypatch.setattr("asistente_mikha.evals.runner.ejecutar_turno", turno_falso)
    salida = tmp_path / "resultados.jsonl"

    await barrer([_caso()], ["m1", "m2"], ["baseline"], 2, salida)

    lineas = [json.loads(l) for l in salida.read_text(encoding="utf-8").splitlines()]
    assert len(lineas) == 4
    assert {l["modelo"] for l in lineas} == {"m1", "m2"}
    assert {l["repeticion"] for l in lineas} == {0, 1}


async def test_barrer_saltea_lo_ya_hecho(tmp_path, monkeypatch):
    corridas = []

    async def turno_contador(modelo, variante, mensaje):
        corridas.append(modelo)
        return TurnOutcome(respuesta="listo", llamadas=[])

    monkeypatch.setattr("asistente_mikha.evals.runner.ejecutar_turno", turno_contador)
    salida = tmp_path / "resultados.jsonl"

    await barrer([_caso()], ["m1"], ["baseline"], 2, salida)
    await barrer([_caso()], ["m1"], ["baseline"], 2, salida)

    # La segunda pasada no vuelve a ejecutar nada.
    assert len(corridas) == 2
    assert len(salida.read_text(encoding="utf-8").splitlines()) == 2


def test_claves_hechas_de_un_archivo_inexistente_es_vacio(tmp_path):
    assert claves_hechas(tmp_path / "no-existe.jsonl") == set()
