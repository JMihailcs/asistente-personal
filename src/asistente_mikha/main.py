from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from asistente_mikha.api.routes import router
from asistente_mikha.memory.tools import get_indexer
from asistente_mikha.observability import configure_tracing


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_tracing()
    get_indexer().sync()
    yield


app = FastAPI(title="Asistente Mikha", lifespan=lifespan)
app.include_router(router)
