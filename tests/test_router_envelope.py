"""El contrato que comparten los cuatro routers.

Todo lo que una herramienta le devuelve al modelo tiene la misma forma:
un dict plano con un `status` obligatorio. Sin esto el modelo tiene que
aprenderse una forma distinta por accion, y este es un modelo de 12B al
que le cuesta bastante menos revisar siempre el mismo campo.
"""

import pytest

from asistente_mikha.memory import tools as memory_tools
from asistente_mikha.tools.actions import system_action
from asistente_mikha.tools.diagnostics import diagnostics

# Estados que puede devolver cualquier router. Uno solo, plano, para que el
# modelo no tenga que desenvolver nada.
VALID_STATUSES = {
    "ok",
    "unavailable",
    "missing_argument",
    "invalid_action",
    "invalid_target",
    "pending_confirmation",
    "list_not_found",
    "not_found",
    "already_done",
    "ambiguous",
}


def _router_calls(tmp_path, monkeypatch):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))
    memory_tools.reset_indexer_for_tests()
    monkeypatch.setattr(memory_tools, "ollama_embed", lambda text: [float(len(text))])
    memory_tools.tasks(action="add", list_name="Casa", text="lavar los platos")

    return [
        ("diagnostics ram", lambda: diagnostics(check="ram")),
        ("diagnostics disk", lambda: diagnostics(check="disk")),
        ("diagnostics processes", lambda: diagnostics(check="processes", limit=3)),
        ("diagnostics gpu", lambda: diagnostics(check="gpu")),
        ("system_action ok", lambda: system_action(action="restart_service", target="wireplumber")),
        ("system_action malo", lambda: system_action(action="restart_service", target="nada")),
        ("memory save", lambda: memory_tools.memory(action="save_note", title="T", content="C")),
        ("memory search", lambda: memory_tools.memory(action="search_notes", query="t")),
        ("memory sin query", lambda: memory_tools.memory(action="search_notes")),
        ("tasks add", lambda: memory_tools.tasks(action="add", list_name="Casa", text="x")),
        ("tasks list", lambda: memory_tools.tasks(action="list", list_name="Casa")),
        ("tasks list vacia", lambda: memory_tools.tasks(action="list", list_name="Nada")),
        ("tasks complete", lambda: memory_tools.tasks(action="complete", list_name="Casa", text="lavar")),
        ("tasks complete de nuevo", lambda: memory_tools.tasks(action="complete", list_name="Casa", text="lavar")),
        ("tasks list_lists", lambda: memory_tools.tasks(action="list_lists")),
        ("tasks sin texto", lambda: memory_tools.tasks(action="add", list_name="Casa")),
    ]


def test_every_router_answer_is_a_dict_with_a_status(tmp_path, monkeypatch):
    for name, call in _router_calls(tmp_path, monkeypatch):
        result = call()
        assert isinstance(result, dict), f"{name} no devolvio un dict: {type(result)}"
        assert "status" in result, f"{name} no trae 'status': {result}"
        assert result["status"] in VALID_STATUSES, f"{name} trae un status raro: {result['status']}"


def test_no_router_answers_with_a_bare_list(tmp_path, monkeypatch):
    # Una lista pelada obliga al modelo a tratar esa accion distinto de todas
    # las demas. Las colecciones van bajo una clave con nombre.
    for name, call in _router_calls(tmp_path, monkeypatch):
        assert not isinstance(call(), list), f"{name} devolvio una lista pelada"


@pytest.mark.parametrize(
    "call_name, key",
    [
        ("processes", "processes"),
        ("results", "results"),
        ("tasks", "tasks"),
        ("lists", "lists"),
    ],
)
def test_collections_travel_under_a_named_key(tmp_path, monkeypatch, call_name, key):
    monkeypatch.setenv("MIKHA_VAULT_PATH", str(tmp_path))
    memory_tools.reset_indexer_for_tests()
    monkeypatch.setattr(memory_tools, "ollama_embed", lambda text: [float(len(text))])
    memory_tools.tasks(action="add", list_name="Casa", text="lavar los platos")

    results = {
        "processes": diagnostics(check="processes", limit=2),
        "results": memory_tools.memory(action="search_notes", query="algo"),
        "tasks": memory_tools.tasks(action="list", list_name="Casa"),
        "lists": memory_tools.tasks(action="list_lists"),
    }

    assert isinstance(results[call_name][key], list)
