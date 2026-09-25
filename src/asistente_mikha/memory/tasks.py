from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from asistente_mikha.memory.vault import slugify

TASKS_DIRNAME = "Tareas"

_TASK_LINE_RE = re.compile(r"^- \[( |x|X)\] (.+)$")

# Una viñeta que el modelo pudo haber agregado por su cuenta al formatear
# una lista: "- ", "* ", "- [ ] ". Se exige espacio (o un checkbox) despues
# del guion para no mutilar texto como "-5 grados", que no es una viñeta.
# El checkbox va primero en la alternancia: si no, "[-*]\s+" se come el
# guion de "- [ ] tarea" y deja el "[ ]" pegado al texto.
_BULLET_PREFIX_RE = re.compile(r"^(?:[-*]\s*\[[ xX]\]\s*|[-*]\s+)")


@dataclass
class TasksAdded:
    path: Path
    tasks: list[str]


@dataclass
class TaskItem:
    text: str
    done: bool


@dataclass
class TaskList:
    name: str
    path: Path
    items: list[TaskItem] = field(default_factory=list)


def _tasks_dir(vault_path: Path) -> Path:
    return vault_path / TASKS_DIRNAME


def _list_path(vault_path: Path, list_name: str) -> Path:
    return _tasks_dir(vault_path) / f"{slugify(list_name)}.md"


def split_task_text(text: str) -> list[str]:
    """Parte un texto en una tarea por linea, sin viñetas ni lineas vacias.

    Escribir el texto crudo dejaba que un salto de linea inyectara
    checkboxes que el usuario nunca pidio, y perdia en silencio las lineas
    que no parecian tarea. Una linea, una tarea.
    """
    tasks = []
    for raw_line in text.splitlines():
        cleaned = _BULLET_PREFIX_RE.sub("", raw_line.strip()).strip()
        if cleaned:
            tasks.append(cleaned)
    return tasks


def add_task(vault_path: Path, list_name: str, text: str) -> TasksAdded:
    file_path = _list_path(vault_path, list_name)
    tasks = split_task_text(text)
    if not tasks:
        return TasksAdded(path=file_path, tasks=[])
    _tasks_dir(vault_path).mkdir(parents=True, exist_ok=True)
    if not file_path.exists():
        file_path.write_text(f"# {list_name}\n\n", encoding="utf-8")
    with file_path.open("a", encoding="utf-8") as f:
        for task_text in tasks:
            f.write(f"- [ ] {task_text}\n")
    return TasksAdded(path=file_path, tasks=tasks)


def _stored_list_name(file_path: Path, fallback: str) -> str:
    """Devuelve el nombre con el que la lista quedo guardada (su titulo H1).

    El archivo se ubica por slug, asi que "Casa", "casa" y "CASA" son la
    misma lista. El nombre que se reporta tiene que ser uno solo: el
    guardado, no el que uso quien pregunto.
    """
    raw = file_path.read_text(encoding="utf-8")
    first_line = raw.splitlines()[0] if raw else ""
    if first_line.startswith("# "):
        return first_line[2:].strip()
    return fallback


def _parse_task_list(file_path: Path, name: str) -> TaskList:
    items: list[TaskItem] = []
    for line in file_path.read_text(encoding="utf-8").splitlines():
        match = _TASK_LINE_RE.match(line.strip())
        if match:
            done = match.group(1).lower() == "x"
            items.append(TaskItem(text=match.group(2), done=done))
    return TaskList(name=name, path=file_path, items=items)


def list_tasks(vault_path: Path, list_name: str) -> TaskList | None:
    file_path = _list_path(vault_path, list_name)
    if not file_path.exists():
        return None
    return _parse_task_list(file_path, _stored_list_name(file_path, list_name))


def complete_task(vault_path: Path, list_name: str, text: str) -> dict:
    file_path = _list_path(vault_path, list_name)
    if not file_path.exists():
        return {"status": "list_not_found"}
    lines = file_path.read_text(encoding="utf-8").splitlines()
    matches: list[tuple[int, str]] = []
    done_matches: list[str] = []
    for i, line in enumerate(lines):
        match = _TASK_LINE_RE.match(line.strip())
        if not match or text.lower() not in match.group(2).lower():
            continue
        if match.group(1) == " ":
            matches.append((i, match.group(2)))
        else:
            done_matches.append(match.group(2))
    if len(matches) == 0:
        # Sin pendientes que coincidan, una que ya este hecha no es lo mismo
        # que una que no existe: decir 'not_found' sobre una tarea que esta
        # ahi, tachada, le miente al usuario.
        if done_matches:
            return {"status": "already_done", "task": done_matches[0]}
        return {"status": "not_found"}
    if len(matches) > 1:
        return {"status": "ambiguous", "matches": [m[1] for m in matches]}
    index, exact_text = matches[0]
    lines[index] = f"- [x] {exact_text}"
    file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"status": "ok", "task": exact_text}


def list_task_lists(vault_path: Path) -> list[str]:
    tasks_dir = _tasks_dir(vault_path)
    if not tasks_dir.exists():
        return []
    return [
        _stored_list_name(file_path, file_path.stem)
        for file_path in sorted(tasks_dir.glob("*.md"))
    ]


def _find_task(vault_path: Path, list_name: str, text: str):
    """Ubica una tarea (pendiente o hecha) por texto dentro de una lista.

    Devuelve (error, file_path, lines, index, exact_text): si error no es
    None, es el resultado a devolver tal cual.
    """
    file_path = _list_path(vault_path, list_name)
    if not file_path.exists():
        return {"status": "list_not_found"}, None, None, None, None
    lines = file_path.read_text(encoding="utf-8").splitlines()
    matches: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        match = _TASK_LINE_RE.match(line.strip())
        if match and text.lower() in match.group(2).lower():
            matches.append((i, match.group(2)))
    if not matches:
        return {"status": "not_found"}, None, None, None, None
    exact = [m for m in matches if m[1].lower() == text.lower()]
    if len(exact) == 1:
        matches = exact
    if len(matches) > 1:
        return (
            {"status": "ambiguous", "matches": [m[1] for m in matches]},
            None,
            None,
            None,
            None,
        )
    return None, file_path, lines, matches[0][0], matches[0][1]


def find_task(vault_path: Path, list_name: str, text: str) -> dict:
    """Valida que `text` apunte a una sola tarea, sin modificar nada."""
    error, _, _, _, exact_text = _find_task(vault_path, list_name, text)
    return error or {"status": "ok", "task": exact_text}


def edit_task(vault_path: Path, list_name: str, text: str, new_text: str) -> dict:
    new_clean = " ".join(new_text.split())
    if not new_clean:
        return {"status": "missing_argument", "required": ["new_text"]}
    error, file_path, lines, index, exact_text = _find_task(vault_path, list_name, text)
    if error:
        return error
    checkbox = _TASK_LINE_RE.match(lines[index].strip()).group(1)
    lines[index] = f"- [{checkbox}] {new_clean}"
    file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"status": "ok", "task": exact_text, "new_text": new_clean}


def delete_task(vault_path: Path, list_name: str, text: str) -> dict:
    error, file_path, lines, index, exact_text = _find_task(vault_path, list_name, text)
    if error:
        return error
    del lines[index]
    file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"status": "ok", "task": exact_text}
