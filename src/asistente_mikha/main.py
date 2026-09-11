from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from asistente_mikha.api.routes import router
from asistente_mikha.memory.tools import get_indexer
from asistente_mikha.observability import configure_tracing

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_tracing()
    get_indexer().sync()
    yield


app = FastAPI(title="Asistente Mikha", lifespan=lifespan)
app.include_router(router)

# Se monta al final a proposito: StaticFiles en "/" capturaria las rutas de
# API si se montara antes. En desarrollo el dist puede no existir todavia.
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
