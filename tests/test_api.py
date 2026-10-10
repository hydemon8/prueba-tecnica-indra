"""API del asistente con un LLM guionizado: sesión, chat con imágenes y decisión humana de aprobaciones."""

from dataclasses import replace

import pytest
from conftest import blob, png
from fastapi.testclient import TestClient

from lineops.api import create_app
from lineops.llm import ScriptedProvider, call, say
from lineops.plant.db import one
from lineops.runtime import build
from lineops.settings import AgentSettings
from lineops.vision_client import VisionClient


@pytest.fixture
def app(tmp_path, vision_app):
    def _app(script, access_code=None):
        settings = replace(AgentSettings.from_env(), plant_db=tmp_path / "plant.db", uploads_dir=tmp_path / "up")
        rt = build(settings, ScriptedProvider(script), VisionClient("http://testserver", client=vision_app))
        client = TestClient(create_app(rt, access_code))
        client.rt = rt
        return client
    return _app


def login(client, user_id, **extra):
    r = client.post("/api/login", json={"user_id": user_id, **extra})
    assert r.status_code == 200, r.text
    d = r.json()
    return {"Authorization": f"Bearer {d['token']}"}, d["session_id"]


def test_requires_login_and_optional_access_code(app):
    c = app([say("hola")], access_code="clave-demo")
    assert c.get("/").status_code == 200 and c.get("/api/users").json()["access_code_required"]
    assert c.get("/api/approvals").status_code == 401
    assert c.post("/api/login", json={"user_id": "u-sup-01"}).status_code == 401
    assert c.post("/api/login", json={"user_id": "nadie", "access_code": "clave-demo"}).status_code == 404
    login(c, "u-sup-01", access_code="clave-demo")


def test_chat_with_image_returns_trace_and_evidence(app):
    c = app([call("inspect_images", image_ids=["x"]), say("No está en el catálogo.")])
    auth, sid = login(c, "u-qa-01")

    def swap(system, messages, tools, _orig=c.rt.agent.llm.generate):  # el guion usa el id real de la imagen cargada
        resp = _orig(system, messages, tools)
        for tc in resp.tool_calls:
            tc.args["image_ids"] = [one(c.rt.con, "SELECT image_id FROM images")["image_id"]]
        return resp
    c.rt.agent.llm.generate = swap
    r = c.post("/api/chat", headers=auth, data={"session_id": sid, "message": "revisa esto"},
               files=[("files", ("caja.png", png(blob()), "image/png"))]).json()
    assert r["stop_reason"] == "final_answer" and r["steps"][0]["outcome"] == "ok"
    assert r["evidence"][0]["decision"] == "UNKNOWN" and r["attachments"]["images"][0]["filename"] == "caja.png"
    image_id = r["evidence"][0]["image_id"]
    assert c.get(f"/api/images/{image_id}", params={"session_id": sid}, headers=auth).status_code == 200
    other_auth, other_sid = login(c, "u-sup-01")
    assert c.get(f"/api/images/{image_id}", params={"session_id": other_sid}, headers=other_auth).status_code == 404
    assert c.get(f"/api/images/{image_id}", params={"session_id": sid}, headers=other_auth).status_code == 404
    assert len(c.get(f"/api/sessions/{sid}/messages", headers=auth).json()["messages"]) == 2
    bad = c.post("/api/chat", headers=auth, data={"session_id": sid, "message": "y esto"},
                 files=[("files", ("nota.png", b"no es una imagen", "image/png"))])
    assert bad.status_code == 422


def test_approval_is_decided_by_a_human_through_the_api(app):
    c = app([call("set_line_state", line_id="L2", state="PAUSED", reason="agarres fallidos sobre el 5 %"), say("Solicitud creada.")])
    mnt, sid = login(c, "u-mnt-01")
    r = c.post("/api/chat", headers=mnt, data={"session_id": sid, "message": "pausa la L2"}).json()
    approval_id = r["approvals"][0]
    pending = c.get("/api/approvals", headers=mnt).json()["pending"]
    assert pending[0]["approval_id"] == approval_id and pending[0]["can_approve"] is False
    denied = c.post(f"/api/approvals/{approval_id}/decision", headers=mnt, json={"approve": True}).json()
    assert denied["error"]["code"] == "permission_denied"
    sup, _ = login(c, "u-sup-01")
    done = c.post(f"/api/approvals/{approval_id}/decision", headers=sup, json={"approve": True}).json()
    assert done["data"]["status"] == "EXECUTED"
    assert one(c.rt.con, "SELECT status FROM lines WHERE plant_id='BAQ' AND line_id='L2'")["status"] == "PAUSED"
    assert c.get("/api/approvals", headers=sup).json()["pending"] == []
    entries = c.get("/api/audit", headers=sup).json()["entries"]
    assert entries[0]["tool"] == "approval:set_line_state" and entries[0]["source"] == "human"
    op, _ = login(c, "u-op-01")
    assert c.get("/api/audit", headers=op).status_code == 403
    assert len(c.get("/api/tools").json()["tools"]) == 22
