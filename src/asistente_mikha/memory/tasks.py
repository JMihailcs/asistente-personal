from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from asistente_mikha.memory.vault import slugify

TASKS_DIRNAME = "Tareas"

_TASK_LINE_RE = re.compile(r"^- \[( |x|X)\] (.+)$")


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


def add_task(vault_path: Path, list_name: str, text: str) -> Path:
    tasks_dir = _tasks_dir(vault_path)
    tasks_dir.mkdir(parents=True, exist_ok=True)
    file_path = _list_path(vault_path, list_name)
    if not file_path.exists():
        file_path.write_text(f"# {list_name}\n\n", encoding="utf-8")
    with file_path.open("a", encoding="utf-8") as f:
        f.write(f"- [ ] {text}\n")
    return file_path


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
    return _parse_task_list(file_path, list_name)


def complete_task(vault_path: Path, list_name: str, text: str) -> dict:
    file_path = _list_path(vault_path, list_name)
    if not file_path.exists():
        return {"status": "list_not_found"}
    lines = file_path.read_text(encoding="utf-8").splitlines()
    matches: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        match = _TASK_LINE_RE.match(line.strip())
        if match and match.group(1) == " " and text.lower() in match.group(2).lower():
            matches.append((i, match.group(2)))
    if len(matches) == 0:
        return {"status": "not_found"}
    if len(matches) > 1:
        return {"status": "ambiguous", "matches": [m[1] for m in matches]}
    index, exact_text = matches[0]
    lines[index] = f"- [x] {exact_text}"
    file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"status": "completed", "task": exact_text}


def list_task_lists(vault_path: Path) -> list[str]:
    tasks_dir = _tasks_dir(vault_path)
    if not tasks_dir.exists():
        return []
    names = []
    for file_path in sorted(tasks_dir.glob("*.md")):
        raw = file_path.read_text(encoding="utf-8")
        first_line = raw.splitlines()[0] if raw else ""
        if first_line.startswith("# "):
            names.append(first_line[2:].strip())
        else:
            names.append(file_path.stem)
    return names
