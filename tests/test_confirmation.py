import pytest

from asistente_mikha.confirmation import (
    ActionStatus,
    PendingActionStore,
    register_implementation,
    get_default_store,
    reset_default_store_for_tests,
    start_turn_tracking,
    collect_turn_actions,
)


@pytest.fixture(autouse=True)
def _clean_store():
    reset_default_store_for_tests()
    yield
    reset_default_store_for_tests()


def test_create_and_get_returns_pending_before_ttl():
    store = PendingActionStore(ttl_seconds=300.0)
    action = store.create("dummy_tool", {"x": 1})
    fetched = store.get(action.action_id)
    assert fetched is not None
    assert fetched.status == ActionStatus.PENDING
    assert fetched.kwargs == {"x": 1}


def test_action_expires_after_ttl():
    current = {"t": 1000.0}
    store = PendingActionStore(ttl_seconds=5.0, clock=lambda: current["t"])
    action = store.create("dummy_tool", {})
    current["t"] += 10.0
    assert store.get(action.action_id).status == ActionStatus.EXPIRED


def test_reject_sets_rejected_status():
    store = PendingActionStore()
    action = store.create("dummy_tool", {})
    rejected = store.reject(action.action_id)
    assert rejected.status == ActionStatus.REJECTED


def test_execute_calls_registered_implementation_with_kwargs():
    store = PendingActionStore()
    calls = []

    def fake_impl(x: int) -> dict:
        calls.append(x)
        return {"doubled": x * 2}

    register_implementation("dummy_tool", fake_impl)
    action = store.create("dummy_tool", {"x": 3})
    executed = store.execute(action.action_id)
    assert calls == [3]
    assert executed.status == ActionStatus.CONFIRMED
    assert executed.result == {"doubled": 6}


def test_execute_without_implementation_raises_keyerror():
    store = PendingActionStore()
    action = store.create("sin_implementacion", {})
    with pytest.raises(KeyError):
        store.execute(action.action_id)


def test_execute_twice_raises_valueerror():
    store = PendingActionStore()
    register_implementation("dummy_tool", lambda: {"ok": True})
    action = store.create("dummy_tool", {})
    store.execute(action.action_id)
    with pytest.raises(ValueError):
        store.execute(action.action_id)


def test_unknown_action_id_raises_keyerror_on_reject():
    store = PendingActionStore()
    with pytest.raises(KeyError):
        store.reject("no-existe")


def test_create_on_default_store_records_turn_action():
    reset_default_store_for_tests()
    start_turn_tracking()
    action = get_default_store().create("dummy_tool", {})
    assert collect_turn_actions() == [action.action_id]
