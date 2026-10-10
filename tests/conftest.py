"""Fixtures compartidas del asistente: planta sembrada en una base temporal y servicio de visión real en
memoria (el artefacto versionado), sin red y sin LLM."""

import io
from dataclasses import replace

import numpy as np
import pytest
from PIL import Image


def png(arr: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr.astype(np.uint8)).save(buf, "PNG")
    return buf.getvalue()


def blob(color=(200, 40, 40), shift=0) -> np.ndarray:
    """Objeto sintético sobre fondo oscuro: captura válida de algo que no está en el catálogo."""
    img = np.full((128, 128, 3), 20, np.uint8)
    img[40:90, 30 + shift:100 + shift] = color
    return img


@pytest.fixture(scope="session")
def vision_app():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from linevision.service.app import create_app
    from linevision.service.settings import ServiceSettings

    settings = replace(ServiceSettings.from_env(), api_key=None, fault_injection=True)
    if not settings.artifact_path.is_file():
        pytest.skip("artefacto no disponible")
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def plant(tmp_path, vision_app):
    """Entorno completo del asistente sobre una planta recién sembrada."""
    from lineops.images import ImageStore
    from lineops.knowledge import KnowledgeBase
    from lineops.plant.db import connect
    from lineops.plant.seed import SIM_NOW, seed
    from lineops.policy import Executor, principal_for
    from lineops.settings import AgentSettings
    from lineops.vision_client import VisionClient

    settings = replace(AgentSettings.from_env(), plant_db=tmp_path / "plant.db", uploads_dir=tmp_path / "uploads")
    con = connect(settings.plant_db)
    seed(con)
    vision_app.post("/admin/fault", json={"mode": "none"})
    vision = VisionClient("http://testserver", retries=1, client=vision_app)
    images = ImageStore(con, settings.uploads_dir)
    ex = Executor(con, vision, KnowledgeBase(settings.sops_dir), images, settings, SIM_NOW)

    class Env:
        pass

    env = Env()
    env.con, env.ex, env.images, env.vision_http, env.settings, env.now = con, ex, images, vision_app, settings, SIM_NOW
    env.user = lambda user_id, session="s-test": principal_for(con, user_id, session)
    env.upload = lambda principal, *arrays: images.save_batch(
        principal, [(f"vista_{i:03d}.png", png(a)) for i, a in enumerate(arrays)], SIM_NOW)
    return env
