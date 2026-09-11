from asistente_mikha.memory.tasks import (
    add_task,
    list_tasks,
    complete_task,
    list_task_lists,
)


def test_add_task_creates_list_file_with_title(tmp_path):
    path = add_task(tmp_path, "Idea de negocio", "comprar granos de cafe")
    assert path.exists()
    text = path.read_text()
    assert text.startswith("# Idea de negocio")
    assert "- [ ] comprar granos de cafe" in text


def test_add_task_appends_to_existing_list(tmp_path):
    add_task(tmp_path, "Casa", "lavar los platos")
    add_task(tmp_path, "Casa", "sacar la basura")

    result = list_tasks(tmp_path, "Casa")

    assert [t.text for t in result.items] == ["lavar los platos", "sacar la basura"]
    assert all(not t.done for t in result.items)


def test_list_tasks_returns_none_for_missing_list(tmp_path):
    assert list_tasks(tmp_path, "No existe") is None


def test_complete_task_marks_single_match(tmp_path):
    add_task(tmp_path, "Compras", "comprar leche")
    add_task(tmp_path, "Compras", "comprar pan")

    result = complete_task(tmp_path, "Compras", "leche")

    assert result == {"status": "completed", "task": "comprar leche"}
    tasks_after = list_tasks(tmp_path, "Compras")
    done_map = {t.text: t.done for t in tasks_after.items}
    assert done_map["comprar leche"] is True
    assert done_map["comprar pan"] is False


def test_complete_task_returns_not_found(tmp_path):
    add_task(tmp_path, "Compras", "comprar leche")

    result = complete_task(tmp_path, "Compras", "algo que no existe")

    assert result == {"status": "not_found"}


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
