import httpx

from asistente_mikha.cli import send_message, confirm_action, format_timestamp


def test_send_message_parses_reply_and_pending_actions():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/chat"
        assert request.method == "POST"
        return httpx.Response(
            200,
            json={
                "reply": "hola",
                "pending_action_ids": ["abc123"],
                "duration_seconds": 1.5,
                "queried_at": "2026-09-11T10:00:00",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://testserver")
    result = send_message(client, "session-1", "hola")
    assert result.reply == "hola"
    assert result.pending_action_ids == ["abc123"]
    assert result.duration_seconds == 1.5
    assert result.queried_at == "2026-09-11T10:00:00"


def test_send_message_defaults_missing_fields():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"reply": "sin acciones"})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://testserver")
    result = send_message(client, "session-1", "hola")
    assert result.pending_action_ids == []
    assert result.duration_seconds == 0.0
    assert result.queried_at == ""


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


def test_format_timestamp_extracts_hour_minute_second():
    assert format_timestamp("2026-09-11T10:05:03.123456") == "10:05:03"


def test_format_timestamp_returns_raw_value_when_unparseable():
    assert format_timestamp("no-es-una-fecha") == "no-es-una-fecha"
