from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import yaml


@dataclass
class Note:
    path: Path
    title: str
    tags: list[str]
    created: str
    content: str

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


def slugify(title: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", title.lower()).strip()
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug or "nota"


def write_note(
    vault_path: Path, title: str, content: str, tags: list[str] | None = None
) -> Path:
    vault_path.mkdir(parents=True, exist_ok=True)
    tags = tags or []
    base_slug = slugify(title)
    slug = base_slug
    counter = 2
    while (vault_path / f"{slug}.md").exists():
        slug = f"{base_slug}-{counter}"
        counter += 1
    file_path = vault_path / f"{slug}.md"
    frontmatter = {
        "title": title,
        "tags": tags,
        "created": datetime.now().isoformat(timespec="seconds"),
    }
    text = (
        "---\n"
        + yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False)
        + "---\n\n"
        + content
        + "\n"
    )
    file_path.write_text(text, encoding="utf-8")
    return file_path


def parse_note(file_path: Path) -> Note | None:
    try:
        raw = file_path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not raw.startswith("---\n"):
        return None
    parts = raw.split("---\n", 2)
    if len(parts) < 3:
        return None
    _, frontmatter_text, body = parts
    try:
        frontmatter = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(frontmatter, dict) or "title" not in frontmatter:
        return None
    return Note(
        path=file_path,
        title=str(frontmatter.get("title", "")),
        tags=list(frontmatter.get("tags", []) or []),
        created=str(frontmatter.get("created", "")),
        content=body.strip(),
    )


def list_vault_notes(vault_path: Path) -> list[Note]:
    if not vault_path.exists():
        return []
    notes = []
    for md_file in sorted(vault_path.glob("*.md")):
        note = parse_note(md_file)
        if note is not None:
            notes.append(note)
    return notes


def find_notes(vault_path: Path, ref: str) -> list[Note]:
    """Ubica notas por nombre de archivo o por titulo exacto (sin mayusculas).

    Puede devolver varias si hay titulos repetidos; quien llama decide que
    hacer con la ambiguedad.
    """
    wanted = ref.strip().lower()
    notes = list_vault_notes(vault_path)
    by_stem = [n for n in notes if n.path.stem.lower() == wanted]
    if by_stem:
        return by_stem
    return [n for n in notes if n.title.strip().lower() == wanted]


def update_note(
    note: Note, new_title: str | None = None, new_content: str | None = None
) -> Note:
    """Reescribe una nota conservando su archivo, tags y fecha de creacion."""
    title = new_title if new_title else note.title
    content = new_content if new_content is not None else note.content
    frontmatter = {"title": title, "tags": note.tags, "created": note.created}
    text = (
        "---\n"
        + yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False)
        + "---\n\n"
        + content
        + "\n"
    )
    note.path.write_text(text, encoding="utf-8")
    return Note(
        path=note.path, title=title, tags=note.tags, created=note.created, content=content
    )


def delete_note(note: Note) -> None:
    note.path.unlink()
