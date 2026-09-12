from asistente_mikha.memory.tasks import (
    add_task,
    list_tasks,
    complete_task,
    list_task_lists,
)


def test_add_task_creates_list_file_with_title(tmp_path):
    result = add_task(tmp_path, "Idea de negocio", "comprar granos de cafe")
    assert result.path.exists()
    assert result.tasks == ["comprar granos de cafe"]
    text = result.path.read_text()
    assert text.startswith("# Idea de negocio")
    assert "- [ ] comprar granos de cafe" in text


def test_add_task_appends_to_existing_list(tmp_path):
    add_task(tmp_path, "Casa", "lavar los platos")
    add_task(tmp_path, "Casa", "sacar la basura")

    result = list_tasks(tmp_path, "Casa")

    assert [t.text for t in result.items] == ["lavar los platos", "sacar la basura"]
    assert all(not t.done for t in result.items)


def test_add_task_splits_multiline_text_into_separate_tasks(tmp_path):
    result = add_task(tmp_path, "Casa", "lavar los platos\nsacar la basura")

    assert result.tasks == ["lavar los platos", "sacar la basura"]
    assert [t.text for t in list_tasks(tmp_path, "Casa").items] == [
        "lavar los platos",
        "sacar la basura",
    ]


def test_add_task_strips_markdown_bullets_the_model_may_add(tmp_path):
    result = add_task(tmp_path, "Casa", "- [ ] lavar los platos\n- sacar la basura\n* regar")

    assert result.tasks == ["lavar los platos", "sacar la basura", "regar"]


def test_add_task_ignores_blank_lines(tmp_path):
    result = add_task(tmp_path, "Casa", "\n  \nlavar los platos\n\n")

    assert result.tasks == ["lavar los platos"]


def test_add_task_with_no_real_text_creates_nothing(tmp_path):
    result = add_task(tmp_path, "Casa", "\n   \n")

    assert result.tasks == []
    assert not result.path.exists()


def test_add_task_keeps_leading_dash_that_is_not_a_bullet(tmp_path):
    # "-5 grados" es texto, no una viñeta: sin espacio detras del guion
    # no hay lista que desarmar.
    result = add_task(tmp_path, "Casa", "-5 grados en el freezer")

    assert result.tasks == ["-5 grados en el freezer"]


def test_list_tasks_returns_none_for_missing_list(tmp_path):
    assert list_tasks(tmp_path, "No existe") is None


def test_list_tasks_reports_the_stored_name_not_the_one_asked_for(tmp_path):
    add_task(tmp_path, "Idea de Negocio", "comprar granos")

    # La lista se pide con otra capitalizacion: es la misma lista, y debe
    # reportarse con el nombre que quedo guardado, no con el que se escribio.
    result = list_tasks(tmp_path, "IDEA DE NEGOCIO")

    assert result.name == "Idea de Negocio"


def test_list_tasks_name_matches_what_list_task_lists_reports(tmp_path):
    add_task(tmp_path, "Idea de Negocio", "comprar granos")
    add_task(tmp_path, "idea de negocio", "moler granos")

    assert list_task_lists(tmp_path) == ["Idea de Negocio"]
    assert list_tasks(tmp_path, "idea de negocio").name == "Idea de Negocio"


def test_complete_task_marks_single_match(tmp_path):
    add_task(tmp_path, "Compras", "comprar leche")
    add_task(tmp_path, "Compras", "comprar pan")

    result = complete_task(tmp_path, "Compras", "leche")

    assert result == {"status": "ok", "task": "comprar leche"}
    tasks_after = list_tasks(tmp_path, "Compras")
    done_map = {t.text: t.done for t in tasks_after.items}
    assert done_map["comprar leche"] is True
    assert done_map["comprar pan"] is False


def test_complete_task_returns_not_found(tmp_path):
    add_task(tmp_path, "Compras", "comprar leche")

    result = complete_task(tmp_path, "Compras", "algo que no existe")

    assert result == {"status": "not_found"}


def test_complete_task_reports_already_done_instead_of_not_found(tmp_path):
    add_task(tmp_path, "Compras", "comprar leche")
    complete_task(tmp_path, "Compras", "leche")

    result = complete_task(tmp_path, "Compras", "leche")

    assert result == {"status": "already_done", "task": "comprar leche"}


def test_complete_task_ignores_done_items_when_a_pending_one_matches(tmp_path):
    add_task(tmp_path, "Compras", "comprar leche entera")
    complete_task(tmp_path, "Compras", "entera")
    add_task(tmp_path, "Compras", "comprar leche deslactosada")

    # "leche" coincide con las dos, pero solo una sigue pendiente: no hay
    # ambigüedad real que preguntar.
    result = complete_task(tmp_path, "Compras", "leche")

    assert result == {"status": "ok", "task": "comprar leche deslactosada"}


def test_complete_task_returns_ambiguous_for_multiple_matches(tmp_path):
    add_task(tmp_path, "Compras", "comprar leche entera")
    add_task(tmp_path, "Compras", "comprar leche deslactosada")

    result = complete_task(tmp_path, "Compras", "leche")

    assert result["status"] == "ambiguous"
    assert set(result["matches"]) == {"comprar leche entera", "comprar leche deslactosada"}


def test_complete_task_returns_list_not_found(tmp_path):
    assert complete_task(tmp_path, "No existe", "algo") == {"status": "list_not_found"}


def test_list_task_lists_returns_pretty_names(tmp_path):
    add_task(tmp_path, "Idea de negocio", "tarea 1")
    add_task(tmp_path, "Casa", "tarea 2")

    assert set(list_task_lists(tmp_path)) == {"Idea de negocio", "Casa"}


def test_list_task_lists_returns_empty_when_no_tasks_dir(tmp_path):
    assert list_task_lists(tmp_path) == []
