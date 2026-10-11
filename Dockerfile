# Imagen única para los dos servicios (visión y asistente). Empaquetado reproducible: dependencias fijadas por uv.lock.
# Cada servicio se arranca con su propio comando (ver compose.yaml).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy LINEVISION_ROOT=/app PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
WORKDIR /app

# capa de dependencias (solo cambia si cambia el lock)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra service --extra agent --no-install-project

COPY src ./src
COPY configs ./configs
COPY knowledge ./knowledge
COPY artifacts ./artifacts
RUN uv sync --frozen --no-dev --extra service --extra agent

# usuario sin privilegios: solo puede escribir en /app/var (planta simulada e imágenes subidas)
RUN useradd --create-home --uid 10001 app && mkdir -p /app/var && chown app /app/var
USER app
EXPOSE 8001 8002
CMD ["linevision-serve"]
