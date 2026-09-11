from __future__ import annotations

from pathlib import Path
from typing import Callable

import chromadb

from asistente_mikha.memory.vault import list_vault_notes

EmbeddingFunction = Callable[[str], list[float]]

INDEX_DIRNAME = ".mikha-index"
COLLECTION_NAME = "notes"


def get_chroma_client(vault_path: Path) -> chromadb.ClientAPI:
    index_path = vault_path / INDEX_DIRNAME
    index_path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(index_path))


class VaultIndexer:
    def __init__(
        self,
        vault_path: Path,
        embed: EmbeddingFunction,
        client: chromadb.ClientAPI | None = None,
    ) -> None:
        self.vault_path = vault_path
        self.embed = embed
        self.client = client or get_chroma_client(vault_path)
        self.collection = self.client.get_or_create_collection(COLLECTION_NAME)

    def sync(self) -> dict:
        notes = list_vault_notes(self.vault_path)
        current_ids = {note.path.name for note in notes}
        existing = self.collection.get()
        existing_hashes = {
            id_: meta.get("content_hash")
            for id_, meta in zip(existing["ids"], existing["metadatas"])
        }

        added = 0
        updated = 0
        for note in notes:
            note_id = note.path.name
            if existing_hashes.get(note_id) == note.content_hash:
                continue
            embedding = self.embed(note.content)
            self.collection.upsert(
                ids=[note_id],
                embeddings=[embedding],
                documents=[note.content],
                metadatas=[
                    {
                        "title": note.title,
                        "tags": ",".join(note.tags),
                        "path": str(note.path),
                        "content_hash": note.content_hash,
                    }
                ],
            )
            if note_id in existing_hashes:
                updated += 1
            else:
                added += 1

        stale_ids = [id_ for id_ in existing_hashes if id_ not in current_ids]
        if stale_ids:
            self.collection.delete(ids=stale_ids)

        return {
            "added": added,
            "updated": updated,
            "removed": len(stale_ids),
            "total": len(notes),
        }

    def search(self, query: str, limit: int = 5) -> list[dict]:
        count = self.collection.count()
        if count == 0:
            return []
        query_embedding = self.embed(query)
        results = self.collection.query(
            query_embeddings=[query_embedding], n_results=min(limit, count)
        )
        found = []
        for doc, meta, distance in zip(
            results["documents"][0], results["metadatas"][0], results["distances"][0]
        ):
            found.append(
                {
                    "title": meta.get("title"),
                    "path": meta.get("path"),
                    "excerpt": doc[:280],
                    "distance": distance,
                }
            )
        return found
