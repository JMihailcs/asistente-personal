from __future__ import annotations

import uuid

import httpx

API_BASE_URL = "http://localhost:8000"


def send_message(client: httpx.Client, session_id: str, message: str) -> tuple[str, list[str]]:
    response = client.post("/chat", json={"session_id": session_id, "message": message})
    response.raise_for_status()
    body = response.json()
    return body["reply"], body.get("pending_action_ids", [])


def confirm_action(client: httpx.Client, action_id: str, approve: bool) -> dict:
    response = client.post(f"/confirm/{action_id}", params={"approve": approve})
    response.raise_for_status()
    return response.json()


def main() -> None:
    session_id = str(uuid.uuid4())
    print(f"Asistente Mikha — sesión {session_id}. Escribe 'salir' para terminar.")
    with httpx.Client(base_url=API_BASE_URL) as client:
        while True:
            try:
                message = input("> ").strip()
            except EOFError:
                break
            if message.lower() in {"salir", "exit", "quit"}:
                break
            if not message:
                continue
            reply, pending_ids = send_message(client, session_id, message)
            print(reply)
            for action_id in pending_ids:
                answer = input(f"  ¿Confirmar acción {action_id}? [s/N] ").strip().lower()
                result = confirm_action(client, action_id, approve=(answer == "s"))
                print(f"  -> {result}")


if __name__ == "__main__":
    main()
