import json

from asistente_mikha.evals.cli import construir_parser, main


def test_correr_parsea_listas_separadas_por_coma():
    args = construir_parser().parse_args(
        ["correr", "--modelos", "a,b", "--variantes", "baseline,cot_arg"]
    )

    assert args.modelos == ["a", "b"]
    assert args.variantes == ["baseline", "cot_arg"]


def test_correr_usa_cinco_repeticiones_por_defecto():
    args = construir_parser().parse_args(["correr", "--modelos", "a"])

    assert args.repeticiones == 5


def test_reporte_agrupa_por_modelo_por_defecto():
    args = construir_parser().parse_args(["reporte", "x.jsonl"])

    assert args.por == "modelo"


def test_el_reporte_imprime_la_tabla(tmp_path, capsys):
    fila = {
        "modelo": "m1", "variante": "baseline", "caso": "c1", "repeticion": 0,
        "veredictos": {
            d: {"ok": True, "motivo": ""}
            for d in ("herramienta", "argumentos", "efecto", "respuesta", "fundamentada")
        },
        "latencia_s": 9.0, "llamadas": [], "respuesta": "", "error": None,
    }
    archivo = tmp_path / "r.jsonl"
    archivo.write_text(json.dumps(fila) + "\n", encoding="utf-8")

    assert main(["reporte", str(archivo)]) == 0
    assert "| m1 |" in capsys.readouterr().out


def test_correr_falla_temprano_si_falta_un_modelo(tmp_path, monkeypatch, capsys):
    # Fallar a las dos horas por un modelo no descargado es inaceptable.
    monkeypatch.setattr(
        "asistente_mikha.evals.cli.modelos_faltantes", lambda modelos: ["no-existe"]
    )
    monkeypatch.setattr("asistente_mikha.evals.cli.load_cases", lambda directorio: ["un-caso"])

    codigo = main(["correr", "--modelos", "no-existe", "--salida", str(tmp_path / "r.jsonl")])

    assert codigo == 1
    assert "no-existe" in capsys.readouterr().err


def test_correr_rechaza_una_variante_desconocida(tmp_path, capsys):
    codigo = main(
        ["correr", "--modelos", "m", "--variantes", "inventada", "--salida", str(tmp_path / "r.jsonl")]
    )

    assert codigo == 1
    assert "inventada" in capsys.readouterr().err
