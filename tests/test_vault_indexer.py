from asistente_mikha.memory.index import VaultIndexer
from asistente_mikha.memory.vault import write_note


def fake_embed(text: str) -> list[float]:
    return [float(len(text) % 7), float(text.count("a")), float(text.count("e"))]


def test_sync_indexes_new_notes(tmp_path):
    write_note(tmp_path, "Nota uno", "contenido con la palabra clave manzana")
    write_note(tmp_path, "Nota dos", "otro contenido distinto")
    indexer = VaultIndexer(tmp_path, embed=fake_embed)

    stats = indexer.sync()

    assert stats == {"added": 2, "updated": 0, "removed": 0, "total": 2}


def test_sync_skips_unchanged_notes_on_second_run(tmp_path):
    write_note(tmp_path, "Nota uno", "contenido sin cambios")
    indexer = VaultIndexer(tmp_path, embed=fake_embed)
    indexer.sync()

    stats = indexer.sync()

    assert stats["added"] == 0
    assert stats["updated"] == 0


def test_sync_removes_deleted_notes(tmp_path):
    path = write_note(tmp_path, "Nota a borrar", "contenido")
    indexer = VaultIndexer(tmp_path, embed=fake_embed)
    indexer.sync()
    path.unlink()

    stats = indexer.sync()

    assert stats["removed"] == 1
    assert stats["total"] == 0


def test_search_returns_empty_list_when_no_notes(tmp_path):
    indexer = VaultIndexer(tmp_path, embed=fake_embed)
    assert indexer.search("cualquier cosa") == []


def test_search_returns_note_with_expected_shape(tmp_path):
    write_note(tmp_path, "Nota manzana", "contenido de prueba")
    indexer = VaultIndexer(tmp_path, embed=fake_embed)
    indexer.sync()

    results = indexer.search("consulta cualquiera", limit=5)

    assert len(results) == 1
    assert set(results[0].keys()) == {"title", "path", "excerpt", "distance"}
    assert results[0]["title"] == "Nota manzana"
