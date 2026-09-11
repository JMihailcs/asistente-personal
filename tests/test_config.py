from pathlib import Path

from asistente_mikha.config import (
    get_ollama_base_url,
    get_phoenix_endpoint,
    get_vault_path,
)


def test_get_ollama_base_url_default(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    assert get_ollama_base_url() == "http://localhost:11434/v1"


def test_get_ollama_base_url_env_override(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://otro-host:11434/v1")
    assert get_ollama_base_url() == "http://otro-host:11434/v1"


def test_get_phoenix_endpoint_default(monkeypatch):
    monkeypatch.delenv("PHOENIX_ENDPOINT", raising=False)
    assert get_phoenix_endpoint() == "http://localhost:6006/v1/traces"


def test_get_phoenix_endpoint_env_override(monkeypatch):
    monkeypatch.setenv("PHOENIX_ENDPOINT", "http://phoenix:6006/v1/traces")
    assert get_phoenix_endpoint() == "http://phoenix:6006/v1/traces"


def test_get_vault_path_default(monkeypatch):
    monkeypatch.delenv("MIKHA_VAULT_PATH", raising=False)
    assert get_vault_path() == Path.home() / "Obsidian" / "Mikha"


def test_get_vault_path_env_override(monkeypatch):
    monkeypatch.setenv("MIKHA_VAULT_PATH", "/vault")
    assert get_vault_path() == Path("/vault")
