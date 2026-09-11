from fastapi.testclient import TestClient

from asistente_mikha.main import app


def test_api_routes_still_reachable_with_static_mount():
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
