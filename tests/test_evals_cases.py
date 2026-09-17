from pathlib import Path

import pytest

from asistente_mikha.evals.cases import CaseError, load_case, load_cases


def _minimo(**extra):
    data = {"id": "un-caso", "mensaje": "hola", "espera": {"herramienta": "ninguna"}}
    data.update(extra)
    return data


def test_carga_un_caso_minimo():
    caso = load_case(_minimo(), origen="test.yaml")

    assert caso.id == "un-caso"
    assert caso.mensaje == "hola"
    assert caso.espera.herramienta == "ninguna"
    assert caso.espera.argumentos == {}
    assert caso.espera.archivos == []
    assert caso.espera.fundamentada is False


def test_carga_un_caso_completo():
    caso = load_case(
        _minimo(
            prepara={"tareas": {"Casa": ["lavar los platos"]}},
            espera={
                "herramienta": "tasks",
                "argumentos": {"action": "add", "list_name": "Casa"},
                "archivos": [{"patron": "Tareas/*.md", "contiene": "sacar la basura"}],
                "respuesta_contiene": ["basura"],
                "respuesta_pregunta": True,
                "fundamentada": True,
            },
        ),
        origen="test.yaml",
    )

    assert caso.prepara == {"tareas": {"Casa": ["lavar los platos"]}}
    assert caso.espera.argumentos == {"action": "add", "list_name": "Casa"}
    assert caso.espera.archivos[0].patron == "Tareas/*.md"
    assert caso.espera.archivos[0].contiene == "sacar la basura"
    assert caso.espera.respuesta_contiene == ["basura"]
    assert caso.espera.respuesta_pregunta is True
    assert caso.espera.fundamentada is True


@pytest.mark.parametrize(
    "data, campo",
    [
        ({"mensaje": "hola", "espera": {"herramienta": "ninguna"}}, "id"),
        ({"id": "x", "espera": {"herramienta": "ninguna"}}, "mensaje"),
        ({"id": "x", "mensaje": "hola"}, "espera"),
        ({"id": "x", "mensaje": "hola", "espera": {}}, "herramienta"),
    ],
)
def test_un_caso_sin_un_campo_obligatorio_dice_cual_falta(data, campo):
    # Un caso mal escrito tiene que fallar antes de gastar horas de corrida,
    # y el mensaje tiene que decir que arreglar.
    with pytest.raises(CaseError) as error:
        load_case(data, origen="test.yaml")

    assert campo in str(error.value)
    assert "test.yaml" in str(error.value)


def test_rechaza_una_clave_desconocida_en_espera():
    # Un typo silencioso ('fundamentado' por 'fundamentada') apagaria un
    # chequeo sin que nadie se entere.
    with pytest.raises(CaseError) as error:
        load_case(_minimo(espera={"herramienta": "ninguna", "fundamentado": True}), origen="test.yaml")

    assert "fundamentado" in str(error.value)


def test_load_cases_lee_el_directorio_ordenado(tmp_path):
    (tmp_path / "a.yaml").write_text(
        "id: segundo\nmensaje: dos\nespera:\n  herramienta: ninguna\n", encoding="utf-8"
    )
    (tmp_path / "b.yaml").write_text(
        "id: primero\nmensaje: uno\nespera:\n  herramienta: ninguna\n", encoding="utf-8"
    )

    casos = load_cases(tmp_path)

    assert [c.id for c in casos] == ["primero", "segundo"]


def test_load_cases_rechaza_ids_repetidos(tmp_path):
    for nombre in ("a.yaml", "b.yaml"):
        (tmp_path / nombre).write_text(
            "id: mismo\nmensaje: x\nespera:\n  herramienta: ninguna\n", encoding="utf-8"
        )

    with pytest.raises(CaseError) as error:
        load_cases(tmp_path)

    assert "mismo" in str(error.value)


@pytest.mark.parametrize(
    "data, campo",
    [
        (_minimo(espera={"herramienta": "ninguna", "respuesta_contiene": "no-es-lista"}), "respuesta_contiene"),
        (_minimo(espera={"herramienta": "ninguna", "archivos": 123}), "archivos"),
        (_minimo(espera={"herramienta": "ninguna", "argumentos": "no-es-dict"}), "argumentos"),
        (_minimo(prepara="no-es-dict"), "prepara"),
    ],
)
def test_tipos_invalidos_en_campos_lanzan_case_error(data, campo):
    with pytest.raises(CaseError) as error:
        load_case(data, origen="test.yaml")

    assert campo in str(error.value)
    assert "test.yaml" in str(error.value)
