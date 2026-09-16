from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

import httpx

API_BASE_URL = "http://localhost:8000"
# El LLM local puede tardar más que el timeout por defecto de httpx (5s),
# sobre todo en la primera respuesta de una sesión nueva.
REQUEST_TIMEOUT_SECONDS = 120.0


@dataclass
class ChatReply:
    reply: str
    pending_action_ids: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    queried_at: str = ""


def send_message(client: httpx.Client, session_id: str, message: str) -> ChatReply:
    response = client.post("/chat", json={"session_id": session_id, "message": message})
    response.raise_for_status()
    body = response.json()
    return ChatReply(
        reply=body["reply"],
        pending_action_ids=body.get("pending_action_ids", []),
        duration_seconds=body.get("duration_seconds", 0.0),
        queried_at=body.get("queried_at", ""),
    )


def confirm_action(client: httpx.Client, action_id: str, approve: bool) -> dict:
    response = client.post(f"/confirm/{action_id}", params={"approve": approve})
    response.raise_for_status()
    return response.json()


def format_timestamp(queried_at: str) -> str:
    """Extrae hora:minuto:segundo de un timestamp ISO; si no se puede, lo devuelve tal cual."""
    try:
        return datetime.fromisoformat(queried_at).strftime("%H:%M:%S")
    except ValueError:
        return queried_at


def describir_error_http(error: Exception) -> str:
    """Convierte una falla de red o un error del backend en algo accionable.

    El backend ya manda un detalle que dice que comando correr; lo unico que
    hace falta es mostrarlo en vez de dejar salir un traceback crudo.
    """
    if isinstance(error, httpx.HTTPStatusError):
        try:
            detalle = error.response.json().get("detail")
        except ValueError:
            detalle = None
        if detalle:
            return str(detalle)
        return f"el backend respondio {error.response.status_code}"
    return (
        f"No hay conexion con el backend en {API_BASE_URL}. "
        f"Levantalo con 'uvicorn asistente_mikha.main:app' y volve a intentar."
    )


def main() -> None:
    session_id = str(uuid.uuid4())
    print(f"Asistente Mikha — sesión {session_id}. Escribe 'salir' para terminar.")
    with httpx.Client(base_url=API_BASE_URL, timeout=REQUEST_TIMEOUT_SECONDS) as client:
        while True:
            try:
                message = input("> ").strip()
            except EOFError:
                break
            if message.lower() in {"salir", "exit", "quit"}:
                break
            if not message:
                continue
            try:
                result = send_message(client, session_id, message)
            except (httpx.HTTPStatusError, httpx.HTTPError) as error:
                print(f"  [!] {describir_error_http(error)}")
                continue
            print(result.reply)
            print(f"  [{format_timestamp(result.queried_at)} · {result.duration_seconds:.1f}s]")
            for action_id in result.pending_action_ids:
                answer = input(f"  ¿Confirmar acción {action_id}? [s/N] ").strip().lower()
                confirm_result = confirm_action(client, action_id, approve=(answer == "s"))
                print(f"  -> {confirm_result}")


if __name__ == "__main__":
    main()
