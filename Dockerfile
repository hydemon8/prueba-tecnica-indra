# Servicio de visión (Reto 4). Empaquetado reproducible: dependencias fijadas por uv.lock.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy LINEVISION_ROOT=/app PATH="/app/.venv/bin:$PATH"
WORKDIR /app

# capa de dependencias (solo cambia si cambia el lock)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra service --no-install-project

COPY src ./src
COPY configs ./configs
COPY artifacts ./artifacts
RUN uv sync --frozen --no-dev --extra service

RUN useradd --create-home --uid 10001 app && chown -R app /app
USER app
ENV VISION_HOST=0.0.0.0 VISION_PORT=8001
EXPOSE 8001
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/readyz')"
CMD ["linevision-serve"]
