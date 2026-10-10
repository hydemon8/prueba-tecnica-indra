import io
from dataclasses import replace

import numpy as np
import pytest
from PIL import Image

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from linevision.service import quality
from linevision.service.app import create_app
from linevision.service.robot import ROBOT_ACTION, robot_command
from linevision.service.settings import ServiceSettings

SETTINGS = replace(ServiceSettings.from_env(), api_key=None, fault_injection=True, max_batch=3)
needs_artifact = pytest.mark.skipif(not SETTINGS.artifact_path.is_file(), reason="artefacto no disponible")
COIL_VIEW = SETTINGS.reference_dir / "obj5__40.png"


def png(arr: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr.astype(np.uint8)).save(buf, "PNG")
    return buf.getvalue()


def blob(color=(200, 40, 40)) -> np.ndarray:
    """Objeto sintético sobre fondo oscuro: pasa la validación de captura pero no está en el catálogo."""
    img = np.full((128, 128, 3), 20, np.uint8)
    img[40:90, 30:100] = color
    return img


# ---------- reglas deterministas ----------
@pytest.mark.parametrize("decision", sorted(ROBOT_ACTION))
def test_robot_only_gets_an_angle_on_pick(decision):
    cmd = robot_command(decision, 7, 123.5)
    if decision == "ACT":
        assert cmd == {"action": "PICK", "object_id": 7, "angle_deg": 123.5}
    else:
        assert cmd["action"] != "PICK" and cmd["object_id"] is None and cmd["angle_deg"] is None


def test_quality_rejects_empty_and_backgroundless_captures():
    _, dark = quality.check(Image.fromarray(np.zeros((128, 128, 3), np.uint8)), 60)
    _, white = quality.check(Image.fromarray(np.full((128, 128, 3), 255, np.uint8)), 60)
    _, tiny = quality.check(Image.fromarray(blob()[:16, :16]), 60)
    arr, good = quality.check(Image.fromarray(blob()).resize((256, 256)), 60)
    assert not dark["ok"] and not white["ok"] and not tiny["ok"]
    assert good["ok"] and good["resized"] and arr.shape == (128, 128, 3)


def test_quality_decode_error():
    with pytest.raises(quality.ImageDecodeError):
        quality.decode(b"esto no es una imagen")


# ---------- API con el artefacto versionado ----------
@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(SETTINGS)) as c:
        yield c


def post(client, *payloads, **kw):
    files = [("images", (f"img{i}.png", p, "image/png")) for i, p in enumerate(payloads)]
    return client.post("/v1/predict", files=files, **kw)


@needs_artifact
def test_health_model_and_catalog(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").status_code == 200
    info = client.get("/v1/model").json()
    assert info["version"] == "4e39f878-rf" and info["n_objects"] == 100 and info["tolerance_deg"] == 10
    catalog = client.get("/v1/catalog").json()
    assert len(catalog) == 100 and all(c["angle_certified"] for c in catalog)


@needs_artifact
def test_unknown_object_is_rejected_and_robot_does_not_pick(client):
    r = post(client, png(blob()), headers={"X-Request-ID": "caso-1"})
    assert r.status_code == 200 and r.headers["X-Request-ID"] == "caso-1"
    res = r.json()["results"][0]
    assert res["decision"] == "UNKNOWN" and res["object_id"] is None and res["angle_deg"] is None
    assert res["robot_command"] == {"action": "DIVERT_TO_REJECT", "object_id": None, "angle_deg": None}
    assert len(res["topk_appearance"]) == 5


@needs_artifact
def test_bad_captures_do_not_reach_the_model(client):
    r = post(client, b"no es una imagen", png(np.zeros((128, 128, 3))))
    results = r.json()["results"]
    assert [x["decision"] for x in results] == ["BAD_CAPTURE", "BAD_CAPTURE"]
    assert all(x["robot_command"]["action"] == "RECAPTURE" and x["reasons"] for x in results)


@needs_artifact
@pytest.mark.skipif(not COIL_VIEW.is_file(), reason="dataset no disponible")
def test_catalog_view_is_picked_with_its_angle(client):
    r = post(client, COIL_VIEW.read_bytes(), params={"top_k": 3})
    res = r.json()["results"][0]
    assert res["decision"] == "ACT" and res["object_id"] == 5 and res["angle_deg"] == pytest.approx(40, abs=10)
    assert res["robot_command"]["action"] == "PICK" and res["robot_command"]["angle_deg"] == res["angle_deg"]
    assert len(res["topk_pose"]) == 3 and len(res["topk_appearance"]) == 3
    assert client.get("/v1/reference/5/40").headers["content-type"] == "image/png"
    assert client.get("/v1/reference/5/41").json()["code"] == "reference_not_found"


@needs_artifact
def test_limits_and_validation_errors(client):
    r = post(client, *[png(blob())] * 4)
    assert r.status_code == 413 and r.json()["code"] == "batch_too_large"
    assert post(client, png(blob()), params={"top_k": 0}).status_code == 422
    assert client.post("/v1/predict").status_code == 422


@needs_artifact
def test_injected_fault_returns_503_once(client):
    assert client.post("/admin/fault", json={"mode": "error", "count": 1}).json()["remaining"] == 1
    r = post(client, png(blob()))
    assert r.status_code == 503 and r.json()["code"] == "service_unavailable" and r.json()["request_id"]
    assert post(client, png(blob())).status_code == 200


@needs_artifact
def test_api_key_is_enforced_when_configured():
    with TestClient(create_app(replace(SETTINGS, api_key="secreto-de-prueba", fault_injection=False))) as c:
        assert c.get("/healthz").status_code == 200
        assert c.get("/v1/model").status_code == 401
        assert c.get("/v1/model", headers={"X-API-Key": "secreto-de-prueba"}).status_code == 200
        assert c.post("/admin/fault", json={"mode": "error"}).status_code == 404
