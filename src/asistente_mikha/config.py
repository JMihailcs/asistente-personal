from __future__ import annotations

import os
from pathlib import Path


def get_ollama_base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")


def get_phoenix_endpoint() -> str:
    return os.environ.get("PHOENIX_ENDPOINT", "http://localhost:6006/v1/traces")


def get_vault_path() -> Path:
    default = str(Path.home() / "Obsidian" / "Mikha")
    return Path(os.environ.get("MIKHA_VAULT_PATH", default))
