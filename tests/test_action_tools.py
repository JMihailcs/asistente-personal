from unittest.mock import patch, MagicMock

import pytest
from jeepney import MessageType

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


def _fake_dbus_connection(message_type: MessageType, body: tuple) -> MagicMock:
    reply = MagicMock()
    reply.header.message_type = message_type
    reply.body = body
    connection = MagicMock()
    connection.send_and_get_reply.return_value = reply
    connection.__enter__.return_value = connection
    connection.__exit__.return_value = False
    return connection


def test_restart_service_creates_pending_action_without_executing():
    with patch("asistente_mikha.tools.actions.open_dbus_connection") as mock_open:
        result = actions.restart_service(service_name="wireplumber")
        assert result["status"] == "pending_confirmation"
        mock_open.assert_not_called()


def test_confirming_restart_service_calls_systemd_manager_via_dbus():
    fake_connection = _fake_dbus_connection(
        MessageType.method_return, ("/org/freedesktop/systemd1/job/1",)
    )
    with patch("asistente_mikha.tools.actions.open_dbus_connection", return_value=fake_connection):
        pending = actions.restart_service(service_name="wireplumber")
        executed = get_default_store().execute(pending["action_id"])
        assert executed.result["returncode"] == 0
        assert executed.result["stderr"] == ""


def test_confirming_restart_service_surfaces_dbus_error():
    fake_connection = _fake_dbus_connection(MessageType.error, ("Unit not found.",))
    with patch("asistente_mikha.tools.actions.open_dbus_connection", return_value=fake_connection):
        pending = actions.restart_service(service_name="wireplumber")
        executed = get_default_store().execute(pending["action_id"])
        assert executed.result["returncode"] == 1
        assert "Unit not found" in executed.result["stderr"]


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


def test_system_action_router_dispatches_restart_service():
    result = actions.system_action(action="restart_service", target="wireplumber")
    assert result["status"] == "pending_confirmation"


def test_system_action_router_dispatches_clear_directory_cache():
    result = actions.system_action(action="clear_directory_cache", target="asistente_scratch")
    assert result["status"] == "pending_confirmation"
