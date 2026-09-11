from asistente_mikha.memory.vault import (
    slugify,
    write_note,
    parse_note,
    list_vault_notes,
)


def test_slugify_basic():
    assert slugify("Idea de Negocio X") == "idea-de-negocio-x"


def test_slugify_strips_punctuation():
    assert slugify("Que hacer? Ya!") == "que-hacer-ya"


def test_slugify_empty_falls_back():
    assert slugify("   ") == "nota"


def test_write_note_creates_file_with_frontmatter(tmp_path):
    file_path = write_note(tmp_path, "Mi primera nota", "Contenido de prueba", ["ideas"])
    assert file_path.exists()
    text = file_path.read_text()
    assert text.startswith("---\n")
    assert "title: Mi primera nota" in text
    assert "Contenido de prueba" in text


def test_write_note_avoids_overwriting_duplicate_titles(tmp_path):
    first = write_note(tmp_path, "Repetida", "primera")
    second = write_note(tmp_path, "Repetida", "segunda")
    assert first != second
    assert first.exists()
    assert second.exists()


def test_parse_note_roundtrip(tmp_path):
    path = write_note(tmp_path, "Nota de prueba", "Cuerpo de la nota", ["a", "b"])
    note = parse_note(path)
    assert note is not None
    assert note.title == "Nota de prueba"
    assert note.tags == ["a", "b"]
    assert note.content == "Cuerpo de la nota"


def test_parse_note_returns_none_for_malformed_file(tmp_path):
    bad_file = tmp_path / "roto.md"
    bad_file.write_text("esto no tiene frontmatter")
    assert parse_note(bad_file) is None


def test_list_vault_notes_skips_malformed_and_finds_valid(tmp_path):
    write_note(tmp_path, "B nota", "contenido b")
    write_note(tmp_path, "A nota", "contenido a")
    (tmp_path / "roto.md").write_text("sin frontmatter")
    notes = list_vault_notes(tmp_path)
    assert {n.title for n in notes} == {"B nota", "A nota"}


def test_list_vault_notes_returns_empty_for_missing_vault(tmp_path):
    assert list_vault_notes(tmp_path / "no-existe") == []
