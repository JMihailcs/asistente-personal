import json

from asistente_mikha.evals.report import agregar, cargar_filas, fallos, tabla_markdown


def _fila(modelo="m1", caso="c1", repeticion=0, herramienta=True, latencia=10.0, error=None):
    return {
        "modelo": modelo,
        "variante": "baseline",
        "caso": caso,
        "repeticion": repeticion,
        "veredictos": {
            "herramienta": {"ok": herramienta, "motivo": "" if herramienta else "llamo a otra"},
            "argumentos": {"ok": True, "motivo": ""},
            "efecto": {"ok": True, "motivo": ""},
            "respuesta": {"ok": True, "motivo": ""},
            "fundamentada": {"ok": True, "motivo": ""},
        },
        "latencia_s": latencia,
        "llamadas": [],
        "respuesta": "",
        "error": error,
    }


def test_agregar_calcula_la_tasa_por_dimension():
    filas = [_fila(herramienta=True), _fila(repeticion=1, herramienta=False)]

    agregado = agregar(filas, por="modelo")

    assert agregado["m1"]["herramienta"] == 0.5
    assert agregado["m1"]["argumentos"] == 1.0


def test_agregar_calcula_la_latencia_mediana():
    filas = [_fila(latencia=10.0), _fila(repeticion=1, latencia=20.0), _fila(repeticion=2, latencia=12.0)]

    agregado = agregar(filas, por="modelo")

    assert agregado["m1"]["latencia_mediana"] == 12.0


def test_agregar_separa_por_modelo():
    filas = [_fila(modelo="m1", herramienta=True), _fila(modelo="m2", herramienta=False)]

    agregado = agregar(filas, por="modelo")

    assert agregado["m1"]["herramienta"] == 1.0
    assert agregado["m2"]["herramienta"] == 0.0


def test_agregar_cuenta_las_corridas():
    agregado = agregar([_fila(), _fila(repeticion=1)], por="modelo")

    assert agregado["m1"]["corridas"] == 2


def test_la_tabla_trae_una_fila_por_modelo_y_las_dimensiones():
    tabla = tabla_markdown(agregar([_fila()], por="modelo"), por="modelo")

    assert "| modelo |" in tabla
    assert "herramienta" in tabla
    assert "latencia" in tabla
    assert "| m1 |" in tabla


def test_los_fallos_dicen_caso_dimension_y_motivo():
    lista = fallos([_fila(herramienta=False)])

    assert any("c1" in f and "herramienta" in f and "llamo a otra" in f for f in lista)


def test_una_corrida_con_error_aparece_en_los_fallos():
    lista = fallos([_fila(error="timeout tras 90.0s")])

    assert any("timeout" in f for f in lista)


def test_cargar_filas_ignora_lineas_vacias(tmp_path):
    archivo = tmp_path / "r.jsonl"
    archivo.write_text(json.dumps(_fila()) + "\n\n", encoding="utf-8")

    assert len(cargar_filas(archivo)) == 1
