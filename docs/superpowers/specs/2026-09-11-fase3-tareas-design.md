# Asistente Mikha — Fase 3: Gestión de tareas

## Contexto

Continúa el roadmap de asistente personal (Fase 1: diagnóstico, Fase 2:
memoria/segundo cerebro + Docker). Esta fase agrega listas de tareas
organizadas por tema/meta, reutilizando el vault de Obsidian ya
existente de la Fase 2.

Lección aplicada de la Fase 2: el modelo local se vuelve poco confiable
invocando herramientas a partir de ~4-5 disponibles simultáneamente. Se
agrega **una sola herramienta router** (`tasks`) en vez de una por
acción, siguiendo el mismo patrón que `diagnostics`, `system_action` y
`memory`. Esto mantiene el conteo total de herramientas del agente en 4.

Por decisión explícita del usuario, esta fase no invierte esfuerzo en
mitigar más a fondo la fiabilidad del modelo actual — eso se abordará
más adelante probando modelos distintos.

## Decisiones

| Aspecto | Decisión |
|---|---|
| Formato de almacenamiento | Markdown plano con checkboxes nativos de Obsidian (`- [ ] texto`, `- [x] texto`), sin frontmatter |
| Organización | Una lista = un archivo, organizadas por tema/meta (no una sola lista general) |
| Ubicación | `<vault>/Tareas/<nombre-de-lista>.md` (subcarpeta separada de las notas) |
| Selección de lista | El agente debe preguntar a qué lista pertenece una tarea nueva si el usuario no lo especificó (mejor esfuerzo vía prompt, no garantizado) |
| Riesgo de las acciones | `read` — ejecución inmediata, sin confirmación (igual que `save_note`) |
| Creación de listas | Solo `add_task` crea una lista nueva si no existe; `list`/`complete` sobre una lista inexistente devuelven error claro |

## Arquitectura

```
memory/tasks.py                          (funciones puras, sin @tool)
├── TaskItem (dataclass: text: str, done: bool)
├── TaskList (dataclass: name: str, path: Path, items: list[TaskItem])
├── add_task(vault_path, list_name, text) -> Path
├── list_tasks(vault_path, list_name) -> TaskList | None
├── complete_task(vault_path, list_name, text) -> dict
└── list_task_lists(vault_path) -> list[str]

memory/tools.py (ampliado)
└── @tool tasks(action, list_name=None, text=None) -> dict | list
    despacha a las 4 funciones de memory/tasks.py
```

`tasks` se suma a `diagnostics`, `system_action` y `memory` como la
cuarta herramienta de nivel superior del agente.

## Componentes

**Formato de archivo** — cada lista es un `.md` sin frontmatter:
```markdown
- [ ] comprar granos de café
- [x] buscar local para la cafetería
```
El nombre de archivo es un slug del nombre de la lista (reutilizando
`slugify()` de `memory/vault.py`), ej. `Tareas/idea-de-negocio.md`.

**`add_task(vault_path, list_name, text) -> Path`** — crea la carpeta
`Tareas/` y el archivo de la lista si no existen (usando `slugify` para
el nombre de archivo pero conservando `list_name` como título legible
en la primera línea del archivo, ej. `# Idea de negocio`), agrega una
línea `- [ ] {text}` al final.

**`list_tasks(vault_path, list_name) -> TaskList | None`** — parsea el
archivo de la lista (líneas que empiezan con `- [ ]` o `- [x]`);
`None` si la lista no existe.

**`complete_task(vault_path, list_name, text) -> dict`** — busca
líneas `- [ ] ...` cuyo texto contenga `text` (insensible a
mayúsculas). Si hay exactamente una coincidencia, la cambia a `- [x]`
y devuelve `{"status": "completed", "task": <texto exacto>}`. Si hay
cero, `{"status": "not_found"}`. Si hay más de una,
`{"status": "ambiguous", "matches": [<textos>]}` — nunca marca al
azar.

**`list_task_lists(vault_path) -> list[str]`** — lista los nombres
(sin extensión) de los archivos `.md` en `Tareas/`.

**Router `tasks(action, list_name=None, text=None)`** (riesgo `read`):
- `action='add'` → `add_task`, requiere `list_name` y `text`.
- `action='list'` → `list_tasks`, requiere `list_name`.
- `action='complete'` → `complete_task`, requiere `list_name` y `text`.
- `action='list_lists'` → `list_task_lists`, sin argumentos extra.

## Prompt del agente

Se agrega al `SYSTEM_PROMPT` de `agent.py`: descripción de la cuarta
herramienta `tasks`, e instrucción de preguntar la lista/meta antes de
agregar una tarea si el usuario no la especificó explícitamente.

## Manejo de errores

- Lista inexistente en `list`/`complete`: mensaje claro, no se crea
  automáticamente.
- Coincidencia ambigua o nula en `complete_task`: se informa
  explícitamente, nunca se completa la tarea equivocada ni falla en
  silencio.
- Carpeta `Tareas/` inexistente: se crea automáticamente en el primer
  `add_task`.

## Testing

Mismo patrón que `memory/vault.py` y `memory/tools.py` de Fase 2:

- Funciones puras de `memory/tasks.py` testeadas con `tmp_path`
  (crear lista nueva, agregar múltiples tareas, listar, completar por
  coincidencia única/ambigua/nula, listar todas las listas).
- Tests del router `tasks()` verificando el despacho correcto a cada
  acción.
- Un test de integración real contra Ollama: agregar una tarea a una
  lista nueva, listarla, y confirmar que aparece.
