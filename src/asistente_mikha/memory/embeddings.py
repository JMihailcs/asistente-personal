from __future__ import annotations

import httpx

from asistente_mikha.config import get_ollama_base_url

EMBEDDING_MODEL = "nomic-embed-text"


def ollama_embed(text: str) -> list[float]:
    """Genera un embedding para `text` usando el endpoint OpenAI-compatible de Ollama."""
    response = httpx.post(
        f"{get_ollama_base_url()}/embeddings",
        json={"model": EMBEDDING_MODEL, "input": text},
        timeout=30.0,
    )
    response.raise_for_status()
    body = response.json()
    return body["data"][0]["embedding"]
