from unittest.mock import patch, MagicMock

import pytest

from asistente_mikha.confirmation import get_default_store, reset_default_store_for_tests
from asistente_mikha.tools import actions


@pytest.fixture(autouse=True)
def _clean_store():
    reset_default_store_for_tests()
    # las funciones _impl se registran al importar el módulo `actions`;
    # como el import ya ocurrió antes del test, hay que re-registrarlas.
    actions.register_implementation("restart_service", actions._restart_service_impl)
    actions.register_implementation("clear_directory_cache", actions._clear_directory_cache_impl)
    yield
    reset_default_store_for_tests()


def test_restart_service_creates_pending_action_without_executing():
    with patch("asistente_mikha.tools.actions.subprocess.run") as mock_run:
        result = actions.restart_service(service_name="wireplumber")
        assert result["status"] == "pending_confirmation"
        mock_run.assert_not_called()


def test_confirming_restart_service_calls_systemctl():
    mock_result = MagicMock(returncode=0, stderr="")
    with patch("asistente_mikha.tools.actions.subprocess.run", return_value=mock_result) as mock_run:
        pending = actions.restart_service(service_name="wireplumber")
        executed = get_default_store().execute(pending["action_id"])
        mock_run.assert_called_once_with(
            ["systemctl", "--user", "restart", "wireplumber"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert executed.result["returncode"] == 0


def test_restart_service_rejects_service_outside_allowlist():
    with pytest.raises(ValueError):
        actions._restart_service_impl("sshd")


def test_clear_directory_cache_creates_pending_action():
    result = actions.clear_directory_cache(target="asistente_scratch")
    assert result["status"] == "pending_confirmation"


def test_clear_directory_cache_impl_removes_files(tmp_path, monkeypatch):
    fake_target_dir = tmp_path / "scratch"
    monkeypatch.setitem(actions.CACHE_TARGETS, "asistente_scratch", fake_target_dir)
    fake_target_dir.mkdir()
    (fake_target_dir / "a.txt").write_text("x")
    (fake_target_dir / "b.txt").write_text("y")

    result = actions._clear_directory_cache_impl("asistente_scratch")
    assert result["files_removed"] == 2
    assert list(fake_target_dir.iterdir()) == []
