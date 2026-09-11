# Asistente Mikha — Fase 2: Memoria (segundo cerebro) + infraestructura Docker

## Contexto y cambio de dirección

Mikha deja de ser únicamente un diagnosticador de máquina y pasa a ser un
**asistente personal de propósito general** que vive en esta máquina; el
diagnóstico de sistema (Fase 1) es una capacidad entre varias. El roadmap
completo del proyecto queda así:

1. ~~Fase 1: Núcleo del agente~~ — completada (diagnóstico + acciones
   controladas + observabilidad).
2. **Fase 2 (este documento): Memoria / segundo cerebro** — reemplaza el
   plan original de "RAG sobre docs de la máquina"; el corpus se amplía a
   notas y contexto personal del usuario. Incluye también dockerizar la
   infraestructura, decisión tomada durante esta fase al notar que la
   cantidad de servicios (backend, Ollama, Phoenix, y lo que sigue) ya
   justifica un `docker-compose`.
3. Fase 3: Gestión de tareas.
4. Fase 4: Calendario / reuniones.
5. Fase 5: Interfaz web.
6. Fase 6: Evals y guardrails.

Cada fase mantiene su propio ciclo spec → plan → implementación. Este
documento cubre únicamente la Fase 2.

## Parte A — Memoria (segundo cerebro sobre Obsidian)

### Decisiones

| Aspecto | Decisión |
|---|---|
| Backend de notas | Vault de Obsidian nuevo, creado por Mikha, en `~/Obsidian/Mikha` |
| Cuándo se guardan notas | Solo cuando el usuario lo pide explícitamente (sin extracción automática por ahora) |
| Riesgo de `save_note` | `read` — ejecución inmediata, sin confirmación (es aditivo y reversible a mano en Obsidian) |
| Indexado semántico | Embeddings vía `nomic-embed-text` (Ollama) + Chroma embebido, sin framework de RAG externo (LlamaIndex sería sobre-ingeniería a esta escala) |
| Granularidad de embeddings | Una nota completa = un vector (no se parte en chunks; las notas personales son cortas) |
| Reindexado | Al arrancar el backend, por hash de contenido — no hay file-watcher en vivo todavía |

### Arquitectura

```
Agente (PydanticAI)
    │
    ├── save_note(title, content, tags) ──► escribe .md con frontmatter
    │                                          en el vault
    │                                          + embebe y agrega a Chroma
    │
    └── search_notes(query, limit) ────────► embebe query
                                                → busca en Chroma
                                                → devuelve notas relevantes

Al arrancar el backend:
    VaultIndexer.sync() escanea el vault, embebe archivos
    nuevos/modificados (por hash), actualiza Chroma.
```

### Componentes

**Formato de nota** — archivo `.md` con frontmatter YAML:
```markdown
---
title: Idea de negocio X
tags: [ideas, negocio]
created: 2026-09-10T21:30:00
---

Contenido de la nota en texto libre...
```
El nombre de archivo es un slug del título; si ya existe, se agrega un
sufijo numérico (`idea-de-negocio-x-2.md`) — nunca sobreescribe una nota
existente.

**`save_note(title: str, content: str, tags: list[str] = []) -> dict`**
(riesgo `read`). El LLM decide título y tags según lo que el usuario pida
guardar. Escribe el archivo, calcula su embedding y lo agrega a la
colección `notes` de Chroma. Si el embedding falla (Ollama no responde),
el archivo se guarda igual y queda pendiente de indexar en el próximo
`VaultIndexer.sync()`.

**`search_notes(query: str, limit: int = 5) -> list[dict]`** (riesgo
`read`). Embebe la consulta, busca los `limit` vecinos más cercanos en
Chroma, devuelve título + fragmento + ruta de archivo de cada nota. Si no
hay notas indexadas o falla el embedding, devuelve una lista vacía con un
mensaje claro — nunca rompe el turno de conversación.

**`VaultIndexer`** — escanea el vault, compara un hash de contenido de
cada archivo contra lo último indexado (guardado como metadata en el
propio Chroma), y solo re-embebe lo nuevo o modificado. Notas con
frontmatter inválido se saltan (se loguea, no se rompe la sincronización
completa). Corre una vez al arrancar el backend, en el mismo `lifespan`
de FastAPI donde ya se llama `configure_tracing()`.

**Colección Chroma** — cliente persistente apuntando a
`<vault>/.mikha-index/` (fuera del contenido que el usuario ve en
Obsidian, ya que es un índice derivado). Una colección `notes`.

### Manejo de errores

- Ollama no responde al pedir un embedding: no se pierde la nota, se
  reintenta indexar en el próximo arranque/sync.
- Vault no existe: se crea automáticamente (`mkdir -p`).
- Nota con frontmatter inválido: se salta, el resto del vault se indexa
  normalmente.
- Título duplicado: sufijo numérico en el nombre de archivo.

### Testing

- `VaultIndexer.sync()`: directorio temporal como vault + función de
  embedding falsa e inyectable (mismo patrón que el reloj inyectable de
  `PendingActionStore` en Fase 1) — no depende de Ollama para correr
  rápido.
- `save_note`: verifica frontmatter correcto y que se agrega a Chroma
  (con embedding falso).
- `search_notes`: con embeddings falsos deterministas, verifica el orden
  de los vecinos más cercanos.
- Test de integración real: "guarda una nota sobre X" → "¿qué notas
  tengo sobre X?" en la misma sesión, contra Ollama real.

## Parte B — Infraestructura Docker

### Decisión y alcance

Ollama se queda **nativo** (ya corre con aceleración GPU AMD/ROCm
funcionando; dockerizarlo arriesga perder esa aceleración por la
complejidad de pasar `/dev/kfd`/`/dev/dri` a un contenedor). El resto
(backend FastAPI + Phoenix) pasa a `docker-compose`. El CLI se queda
nativo — solo habla HTTP con el backend, sin importar dónde corra este.

### Conflicto resuelto: `restart_service` y D-Bus

`restart_service` (Fase 1) ejecuta `systemctl --user restart wireplumber`,
lo que requiere acceso al bus de sesión D-Bus del usuario del host —
normalmente no disponible dentro de un contenedor aislado. Se resuelve
montando el socket del host (`/run/user/<uid>/bus`) dentro del
contenedor del backend y pasando `DBUS_SESSION_BUS_ADDRESS` como
variable de entorno — patrón estándar de Docker para esto. Con eso,
`restart_service` sigue funcionando exactamente igual que corriendo
nativo.

### Componentes

**`Dockerfile`** (backend) — `python:3.14-slim`, copia `pyproject.toml` y
`src/`, `pip install -e .`, expone el puerto 8000, arranca con
`uvicorn asistente_mikha.main:app --host 0.0.0.0 --port 8000`.

**`docker-compose.yml`**:
- `backend`: build local, puerto `8000:8000`, monta el vault
  (`~/Obsidian/Mikha:/vault`) y el socket D-Bus del host, variables de
  entorno `OLLAMA_BASE_URL=http://host.docker.internal:11434/v1`,
  `PHOENIX_ENDPOINT=http://phoenix:6006/v1/traces`,
  `MIKHA_VAULT_PATH=/vault`, `DBUS_SESSION_BUS_ADDRESS`, `extra_hosts:
  host.docker.internal:host-gateway` (patrón estándar de Docker en Linux
  para alcanzar servicios del host), `depends_on: phoenix`.
- `phoenix`: imagen oficial `arizephoenix/phoenix:latest`, puertos 6006
  (UI) y 4317 (OTLP), volumen persistente para no perder trazas al
  reiniciar el contenedor.

**Cambios de código necesarios** (todos son leer de variable de entorno
con el valor actual como default, sin romper el modo nativo):
- `agent.py`: `OLLAMA_BASE_URL` pasa a `os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")`.
- `observability.py`: `DEFAULT_PHOENIX_ENDPOINT` pasa a leer
  `os.environ.get("PHOENIX_ENDPOINT", "http://localhost:6006/v1/traces")`.
- Vault: la ruta pasa a `os.environ.get("MIKHA_VAULT_PATH", str(Path.home() / "Obsidian" / "Mikha"))`.

### Manejo de errores

- Si el backend no puede alcanzar `host.docker.internal:11434` (Ollama
  no corriendo en el host), `/health` reporta `ollama_reachable: false`
  igual que hoy — no cambia el comportamiento ya construido en Fase 1.
- Si el socket D-Bus no está montado o no es accesible, `restart_service`
  falla con un error claro capturado (mismo manejo de errores de
  herramientas ya definido en Fase 1) en vez de colgar el proceso.

### Testing

- Los tests unitarios/de integración de Python siguen corriendo nativos
  contra el entorno virtual (no dentro de Docker) — Docker es para
  *correr* el sistema, no para testearlo.
- Un smoke test manual (documentado en el README, no automatizado):
  `docker compose up`, `curl http://localhost:8000/health`, confirmar
  `ollama_reachable: true` y que `restart_service` sigue funcionando
  pidiéndolo por el CLI.
