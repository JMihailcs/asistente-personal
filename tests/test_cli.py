import httpx

from asistente_mikha.cli import send_message, confirm_action


def test_send_message_parses_reply_and_pending_actions():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/chat"
        assert request.method == "POST"
        return httpx.Response(200, json={"reply": "hola", "pending_action_ids": ["abc123"]})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://testserver")
    reply, pending = send_message(client, "session-1", "hola")
    assert reply == "hola"
    assert pending == ["abc123"]


def test_send_message_defaults_pending_actions_to_empty_list():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"reply": "sin acciones"})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://testserver")
    _, pending = send_message(client, "session-1", "hola")
    assert pending == []


def test_confirm_action_sends_approve_param():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["approve"] = request.url.params.get("approve")
        return httpx.Response(200, json={"action_id": "abc123", "status": "confirmed", "result": None})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://testserver")
    result = confirm_action(client, "abc123", approve=True)
    assert captured["path"] == "/confirm/abc123"
    assert captured["approve"] == "true"
    assert result["status"] == "confirmed"
