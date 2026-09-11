import pytest

from asistente_mikha.tools.registry import (
    ToolRisk,
    tool,
    get_tool,
    all_tools,
    clear_registry_for_tests,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    clear_registry_for_tests()
    yield
    clear_registry_for_tests()


def test_tool_decorator_registers_function_with_metadata():
    @tool(risk=ToolRisk.READ, description="ejemplo de solo lectura")
    def sample_read_tool() -> str:
        return "ok"

    registered = get_tool("sample_read_tool")
    assert registered is not None
    assert registered.risk == ToolRisk.READ
    assert registered.description == "ejemplo de solo lectura"
    assert registered.func() == "ok"


def test_get_tool_returns_none_for_unknown_name():
    assert get_tool("no_existe") is None


def test_all_tools_returns_every_registered_tool():
    @tool(risk=ToolRisk.READ, description="a")
    def tool_a() -> None:
        ...

    @tool(risk=ToolRisk.CONFIRM, description="b")
    def tool_b() -> None:
        ...

    names = set(all_tools().keys())
    assert names == {"tool_a", "tool_b"}


def test_duplicate_registration_raises():
    @tool(risk=ToolRisk.READ, description="a")
    def dup_tool() -> None:
        ...

    with pytest.raises(ValueError):
        @tool(risk=ToolRisk.READ, description="a otra vez")
        def dup_tool() -> None:  # noqa: F811
            ...
