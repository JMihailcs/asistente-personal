from asistente_mikha.memory import embeddings


def test_ollama_embed_sends_expected_request_and_parses_response(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [{"embedding": [0.1, 0.2, 0.3]}]}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr(embeddings.httpx, "post", fake_post)
    result = embeddings.ollama_embed("hola mundo")

    assert result == [0.1, 0.2, 0.3]
    assert captured["json"] == {"model": "nomic-embed-text", "input": "hola mundo"}
    assert captured["url"].endswith("/embeddings")
