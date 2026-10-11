"""Despliegue local de un comando: `uv run --extra service --extra agent lineops-up`.

Levanta dos procesos independientes: el servicio de visión (API propia, puerto 8001) y el asistente con su
interfaz web (puerto 8002). Si el servicio de visión ya está arriba, se reutiliza.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time

import httpx

from linevision.service.cli import load_env_file

log = logging.getLogger("lineops.cli")


def _ready(url: str) -> bool:
    try:
        return httpx.get(f"{url}/readyz", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


def main() -> None:
    import uvicorn

    from .api import create_app
    from .runtime import build
    from .settings import AgentSettings

    load_env_file()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = AgentSettings.from_env()
    child = None
    if not _ready(settings.vision_url) and os.environ.get("LINEOPS_START_VISION", "true").lower() != "false":
        child = subprocess.Popen([sys.executable, "-m", "linevision.service.cli"])
        for _ in range(90):
            if _ready(settings.vision_url) or child.poll() is not None:
                break
            time.sleep(1)
    if not _ready(settings.vision_url):
        log.warning("el servicio de visión no responde en %s: el asistente arrancará degradado", settings.vision_url)
    try:
        app = create_app(build(settings), os.environ.get("DEMO_ACCESS_CODE") or None,
                         demo_controls=os.environ.get("LINEOPS_DEMO_CONTROLS", "false").lower() == "true")
        log.info("asistente en http://%s:%s", settings.host, settings.port)
        uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")
    finally:
        if child and child.poll() is None:
            child.terminate()


if __name__ == "__main__":
    main()
