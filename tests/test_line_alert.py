"""La alerta de captura del servicio de visión, vista desde el asistente: la tool de estado de línea, la API que
usa la interfaz y el simulador de capturas de la demostración."""

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from lineops.api import create_app
from lineops.llm import ScriptedProvider, say
from lineops.runtime import build
from lineops.settings import AgentSettings
from lineops.tools import ToolError
from lineops.tools.read import capture_alert
from lineops.vision_client import VisionClient


@pytest.fixture
def client(tmp_path, vision_app):
    def _client(demo_controls: bool, name: str = "a"):
        (tmp_path / name).mkdir()
        settings = replace(AgentSettings.from_env(), plant_db=tmp_path / name / "plant.db", uploads_dir=tmp_path / name / "up")
        rt = build(settings, ScriptedProvider([say("ok")]), VisionClient("http://testserver", client=vision_app))
        return TestClient(create_app(rt, demo_controls=demo_controls))
    return _client


def login(c, user_id):
    r = c.post("/api/login", json={"user_id": user_id})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_line_status_includes_the_live_capture_alert(plant):
    r = plant.ex.execute(plant.user("u-op-01"), "get_line_status", {"line_id": "L1"})
    assert r["ok"], r
    alert = r["data"]["capture_alert"]
    assert alert["available"] and alert["active"] is False and alert["raise_at"] == 0.10


def test_capture_alert_is_reported_as_unavailable_when_vision_fails():
    class Down:
        def line_alert(self, line_id):
            raise ToolError("vision_unavailable", "el servicio de visión no respondió", retryable=True)

    alert = capture_alert(Down(), "BAQ", "L1")
    assert alert == {"available": False, "detail": "el servicio de visión no respondió"}


def test_demo_controls_are_off_by_default_and_respect_the_line_scope(client):
    off = client(demo_controls=False)
    h = login(off, "u-sup-01")
    assert off.get("/api/lines").status_code == 401
    assert off.get("/api/lines", headers=h).json()["demo_controls"] is False
    assert off.post("/api/demo/captures", headers=h, json={"line_id": "L1", "scenario": "normal"}).status_code == 404
    on = client(demo_controls=True, name="b")
    operator = login(on, "u-op-01")  # el operario solo tiene la L1
    assert on.post("/api/demo/captures", headers=operator, json={"line_id": "L2", "scenario": "normal"}).status_code == 403
    assert on.post("/api/demo/captures", headers=operator, json={"line_id": "L1", "scenario": "otro"}).status_code == 422


def test_simulated_lamp_fault_raises_the_alert_and_normal_captures_clear_it(client):
    c = client(demo_controls=True)
    if c.get("/api/reference/74/0").status_code != 200:
        pytest.skip("vistas de referencia no disponibles (falta el dataset)")
    h = login(c, "u-sup-01")
    r = c.post("/api/demo/captures", headers=h, json={"line_id": "L2", "scenario": "lamp_fault"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["captures_sent"] == 70 and d["capture_alert"]["active"]
    assert "iluminación" in d["capture_alert"]["probable_cause"]
    # mientras la alerta está activa, los desconocidos se retienen para revisión en lugar de rechazarse
    assert d["robot_orders"].get("DIVERT_TO_REVIEW", 0) > d["robot_orders"].get("DIVERT_TO_REJECT", 0)
    lines = {x["line_id"]: x for x in c.get("/api/lines", headers=h).json()["lines"]}
    assert lines["L2"]["capture_alert"]["active"] and lines["L2"]["status"] == "RUNNING"
    assert lines["L1"]["capture_alert"]["active"] is False
    d = c.post("/api/demo/captures", headers=h, json={"line_id": "L2", "scenario": "normal"}).json()
    assert d["captures_sent"] == 100 and d["capture_alert"]["active"] is False
