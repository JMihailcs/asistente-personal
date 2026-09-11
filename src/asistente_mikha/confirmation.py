from __future__ import annotations

import contextvars
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class ActionStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class PendingAction:
    action_id: str
    tool_name: str
    kwargs: dict[str, Any]
    created_at: float
    ttl_seconds: float
    status: ActionStatus = ActionStatus.PENDING
    result: Any = None


IMPLEMENTATIONS: dict[str, Callable[..., dict]] = {}


def register_implementation(tool_name: str, func: Callable[..., dict]) -> None:
    IMPLEMENTATIONS[tool_name] = func


_current_turn_actions: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar(
    "_current_turn_actions", default=None
)


def start_turn_tracking() -> None:
    _current_turn_actions.set([])


def record_pending_action(action_id: str) -> None:
    bucket = _current_turn_actions.get()
    if bucket is not None:
        bucket.append(action_id)


def collect_turn_actions() -> list[str]:
    return list(_current_turn_actions.get() or [])


class PendingActionStore:
    def __init__(
        self, ttl_seconds: float = 300.0, clock: Callable[[], float] = time.time
    ) -> None:
        self._actions: dict[str, PendingAction] = {}
        self._ttl_seconds = ttl_seconds
        self._clock = clock

    def create(self, tool_name: str, kwargs: dict[str, Any]) -> PendingAction:
        action = PendingAction(
            action_id=str(uuid.uuid4()),
            tool_name=tool_name,
            kwargs=kwargs,
            created_at=self._clock(),
            ttl_seconds=self._ttl_seconds,
        )
        self._actions[action.action_id] = action
        record_pending_action(action.action_id)
        return action

    def get(self, action_id: str) -> PendingAction | None:
        action = self._actions.get(action_id)
        if action is None:
            return None
        if (
            action.status == ActionStatus.PENDING
            and self._clock() - action.created_at > action.ttl_seconds
        ):
            action.status = ActionStatus.EXPIRED
        return action

    def reject(self, action_id: str) -> PendingAction:
        action = self._require_pending(action_id)
        action.status = ActionStatus.REJECTED
        return action

    def execute(self, action_id: str) -> PendingAction:
        action = self._require_pending(action_id)
        impl = IMPLEMENTATIONS.get(action.tool_name)
        if impl is None:
            raise KeyError(f"No hay implementación registrada para '{action.tool_name}'")
        action.result = impl(**action.kwargs)
        action.status = ActionStatus.CONFIRMED
        return action

    def _require_pending(self, action_id: str) -> PendingAction:
        action = self.get(action_id)
        if action is None:
            raise KeyError(f"Acción '{action_id}' no existe")
        if action.status != ActionStatus.PENDING:
            raise ValueError(f"Acción '{action_id}' no está pendiente (estado: {action.status})")
        return action


_default_store = PendingActionStore()


def get_default_store() -> PendingActionStore:
    return _default_store


def reset_default_store_for_tests() -> None:
    global _default_store
    _default_store = PendingActionStore()
    IMPLEMENTATIONS.clear()
