"""Arranque del servicio de visión con un solo comando: `uv run --extra service linevision-serve`."""

from __future__ import annotations

import logging
import os

from ..config import ROOT


def load_env_file(path=ROOT / ".env") -> None:
    """Carga .env si existe, sin pisar variables ya definidas en el entorno."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def main() -> None:
    import uvicorn

    from .app import create_app
    from .settings import ServiceSettings

    load_env_file()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = ServiceSettings.from_env()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
