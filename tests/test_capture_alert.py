"""Alerta de captura: una subida brusca de UNKNOWN en una línea retiene esos objetos para revisión."""

from dataclasses import replace

import numpy as np
import pytest
from conftest import blob, png
from fastapi.testclient import TestClient
from PIL import Image

from linevision.service.app import create_app
from linevision.service.monitor import CaptureMonitor, MonitorConfig
from linevision.service.robot import robot_command
from linevision.service.settings import ServiceSettings

SETTINGS = replace(ServiceSettings.from_env(), api_key=None, alert_window=40, alert_min_samples=10)
COIL = SETTINGS.reference_dir


# ---------- la regla, sin servicio ----------
def feed(m, line, decisions, brightness=0.22):
    out = None
    for d in decisions:
        out = m.observe(line, d, brightness)
    return out


def test_alert_needs_enough_samples_and_a_sustained_rate():
    m = CaptureMonitor(MonitorConfig(window=40, min_samples=10, raise_at=0.10, clear_at=0.03))
    state, change = feed(m, "L1", ["UNKNOWN"] * 5)  # 100 % de desconocidos, pero solo 5 capturas
    assert not state["active"] and change is None
    m = CaptureMonitor(MonitorConfig(window=40, min_samples=10, raise_at=0.10, clear_at=0.03))
    state, _ = feed(m, "L1", ["ACT"] * 39 + ["UNKNOWN"])  # 2,5 %: lo normal con un umbral al 99 %
    assert not state["active"]
    state, _ = feed(m, "L1", ["UNKNOWN"] * 2)
    assert not state["active"] and state["unknown_rate"] == pytest.approx(3 / 40)
    state, change = feed(m, "L1", ["UNKNOWN"])
    assert state["active"] and change == "raised" and state["times_raised"] == 1


def test_alert_has_hysteresis_and_lines_are_independent():
    m = CaptureMonitor(MonitorConfig(window=40, min_samples=10, raise_at=0.10, clear_at=0.03))
    feed(m, "L1", ["ACT"] * 30 + ["UNKNOWN"] * 10)
    assert m.snapshot("L1")["active"] and not m.snapshot("L2")["active"]
    state, _ = feed(m, "L1", ["ACT"] * 36)  # quedan 4 de 40 = 10 %: baja del umbral de activación pero no se apaga
    assert state["active"] and state["unknown_rate"] == pytest.approx(0.10)
    state, change = feed(m, "L1", ["ACT"] * 3)  # 1 de 40 = 2,5 % <= 3 %
    assert not state["active"] and change == "cleared"


def test_probable_cause_follows_the_brightness_of_the_captures():
    m = CaptureMonitor(MonitorConfig(window=40, min_samples=10, raise_at=0.10, clear_at=0.03))
    feed(m, "L1", ["ACT"] * 30, brightness=0.22)
    state, _ = feed(m, "L1", ["UNKNOWN"] * 12, brightness=0.154)  # -30 %
    assert state["active"] and state["brightness_change"] == pytest.approx(-0.25, abs=0.06)
    assert "iluminación" in state["probable_cause"]
    m = CaptureMonitor(MonitorConfig(window=40, min_samples=10, raise_at=0.10, clear_at=0.03))
    feed(m, "L2", ["ACT"] * 30, brightness=0.22)
    state, _ = feed(m, "L2", ["UNKNOWN"] * 12, brightness=0.22)  # mismos brillos: no es la luz
    assert state["active"] and "lote" in state["probable_cause"]


def test_robot_holds_unknowns_only_while_the_alert_is_active():
    assert robot_command("UNKNOWN", None, None)["action"] == "DIVERT_TO_REJECT"
    assert robot_command("UNKNOWN", None, None, hold_unknown=True)["action"] == "DIVERT_TO_REVIEW"
    assert robot_command("ACT", 5, 40.0, hold_unknown=True) == {"action": "PICK", "object_id": 5, "angle_deg": 40.0}


# ---------- en el servicio ----------
@pytest.fixture
def client():
    if not SETTINGS.artifact_path.is_file():
        pytest.skip("artefacto no disponible")
    with TestClient(create_app(SETTINGS)) as c:
        yield c


def send(client, images, line=None):
    out, alert = [], None
    for i in range(0, len(images), 16):
        files = [("images", (f"{i + k}.png", data, "image/png")) for k, data in enumerate(images[i:i + 16])]
        r = client.post("/v1/predict", files=files, params={"top_k": 1}, headers={"X-Line-ID": line} if line else {})
        assert r.status_code == 200, r.text
        out += r.json()["results"]
        alert = r.json()["line_alert"]
    return out, alert


def test_unknown_burst_on_a_line_is_held_for_review(client):
    unknowns = [png(blob(shift=i % 20)) for i in range(12)]
    manual, alert = send(client, unknowns)  # sin X-Line-ID (inspección manual): nunca cuenta ni se retiene
    assert alert is None and {r["robot_command"]["action"] for r in manual} == {"DIVERT_TO_REJECT"}
    results, alert = send(client, unknowns, line="L1")
    actions = [r["robot_command"]["action"] for r in results]
    assert actions[:9] == ["DIVERT_TO_REJECT"] * 9 and actions[9:] == ["DIVERT_TO_REVIEW"] * 3  # se activa con 10 capturas
    assert alert["active"] and alert["unknown_rate"] == 1.0 and "retiene" in results[-1]["reasons"][-1]
    assert client.get("/v1/lines/L1/monitor").json()["active"]
    assert not client.get("/v1/lines/L2/monitor").json()["active"]
    assert client.post("/v1/predict", files=[("images", ("a.png", unknowns[0], "image/png"))],
                       headers={"X-Line-ID": "linea 1"}).status_code == 422


@pytest.mark.skipif(not (COIL / "obj5__0.png").is_file(), reason="dataset no disponible")
def test_dimmed_lamp_raises_the_alert_and_points_to_lighting(client):
    rng = np.random.default_rng(3)
    views = [np.asarray(Image.open(COIL / f"obj{o}__{a}.png").convert("RGB"))
             for o, a in zip(rng.integers(1, 101, 60), rng.integers(0, 72, 60) * 5)]
    clean, alert = send(client, [png(v) for v in views[:40]], line="L1")
    assert not alert["active"] and sum(r["decision"] == "UNKNOWN" for r in clean) == 0
    dimmed, alert = send(client, [png(v * 0.7) for v in views[40:]], line="L1")  # la lámpara pierde un 30 %
    assert sum(r["decision"] == "UNKNOWN" for r in dimmed) >= 15  # producto conocido que el modelo ya no reconoce
    assert alert["active"] and alert["brightness_change"] < -0.15 and "iluminación" in alert["probable_cause"]
    held = [r for r in dimmed if r["robot_command"]["action"] == "DIVERT_TO_REVIEW" and r["decision"] == "UNKNOWN"]
    rejected = [r for r in dimmed if r["robot_command"]["action"] == "DIVERT_TO_REJECT"]
    assert len(held) >= 10 and len(rejected) <= 5  # solo se rechazan los primeros, antes de que salte la alerta
