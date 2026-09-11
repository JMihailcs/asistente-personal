# Node 26 a proposito: coincide con el npm local (12.x), cuyo formato de
# lockfile no lo entienden los npm mas viejos que traen las imagenes de
# Node 22 y anteriores.
FROM node:26-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -e .
COPY --from=frontend /build/dist ./frontend/dist

EXPOSE 8000
CMD ["uvicorn", "asistente_mikha.main:app", "--host", "0.0.0.0", "--port", "8000"]
