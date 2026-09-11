from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class ToolRisk(str, Enum):
    READ = "read"
    CONFIRM = "confirm"


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    func: Callable[..., Any]
    risk: ToolRisk
    description: str


_REGISTRY: dict[str, RegisteredTool] = {}


def tool(risk: ToolRisk, description: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if func.__name__ in _REGISTRY:
            raise ValueError(f"Tool '{func.__name__}' ya está registrada")
        _REGISTRY[func.__name__] = RegisteredTool(
            name=func.__name__, func=func, risk=risk, description=description
        )
        return func

    return decorator


def get_tool(name: str) -> RegisteredTool | None:
    return _REGISTRY.get(name)


def all_tools() -> dict[str, RegisteredTool]:
    return dict(_REGISTRY)


def clear_registry_for_tests() -> None:
    _REGISTRY.clear()
