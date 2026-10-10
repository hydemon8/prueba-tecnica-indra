"""Capa de política y tools, sin LLM: lo que aquí se comprueba no depende de lo que decida el modelo."""

from pathlib import Path

import numpy as np
import pytest
from conftest import blob
from PIL import Image

from lineops.plant.db import one, rows
from lineops.tools import REGISTRY
from lineops.tools.base import ALL_ROLES

COIL = Path(__file__).resolve().parents[1] / "coil-100"


def audit(env, n=1):
    return rows(env.con, "SELECT tool, outcome, detail, source, user_id FROM audit_log ORDER BY id DESC LIMIT ?", (n,))


# ---------- catálogo ----------
def test_catalog_shape():
    kinds = [s.kind for s in REGISTRY.values()]
    assert len(REGISTRY) >= 10 and kinds.count("read") >= 5 and kinds.count("write") >= 5
    for spec in REGISTRY.values():
        assert spec.roles <= ALL_ROLES and spec.description and spec.use_cases
        if spec.risk == "high":
            assert spec.kind == "write" and spec.approvers and "aprob" in spec.description
        assert "plant_id" not in spec.json_schema().get("properties", {}), "la planta nunca es un argumento"


# ---------- validación, permisos y alcance ----------
def test_unknown_tool_and_invalid_arguments_are_rejected_and_audited(plant):
    sup = plant.user("u-sup-01")
    r = plant.ex.execute(sup, "borrar_base_de_datos", {})
    assert r["error"]["code"] == "unknown_tool" and "get_line_status" in r["error"]["available_tools"]
    r = plant.ex.execute(sup, "get_shift_metrics", {"line_id": "L1", "shift": 7, "extra": 1})
    assert r["error"]["code"] == "invalid_arguments"
    assert {p["field"] for p in r["error"]["problems"]} == {"shift", "extra"}
    r = plant.ex.execute(sup, "get_line_timeline", {"line_id": "L1", "start": "ayer", "end": "hoy"})
    assert r["error"]["code"] == "invalid_arguments"
    assert [a["outcome"] for a in audit(plant, 3)] == ["error", "invalid", "invalid"]


def test_role_and_line_scope_are_enforced(plant):
    op = plant.user("u-op-01")
    assert plant.ex.execute(op, "resolve_review_case", {"case_id": "RC-0001", "confirmed_object_id": 5,
                                                         "confirmed_angle_deg": 40})["error"]["code"] == "permission_denied"
    assert plant.ex.execute(op, "get_line_status", {"line_id": "L2"})["error"]["code"] == "out_of_scope"
    assert plant.ex.execute(op, "get_line_status", {"line_id": "L1"})["ok"]
    assert "set_line_state" not in plant.ex.allowed_tools(op)


def test_plants_are_isolated(plant):
    bog = plant.user("u-sup-02")
    baq_case = one(plant.con, "SELECT case_id FROM review_cases WHERE plant_id='BAQ' LIMIT 1")["case_id"]
    assert plant.ex.execute(bog, "get_review_case", {"case_id": baq_case})["error"]["code"] == "not_found"
    tickets = plant.ex.execute(bog, "list_tickets", {"line_id": "L1"})["data"]["tickets"]
    assert [t["ticket_id"] for t in tickets] == ["TCK-1044"]  # ve solo los de Bogotá, aunque la línea se llame igual
    totals = plant.ex.execute(bog, "get_shift_metrics", {"line_id": "L1", "shift": 3})["data"]["totals"]
    assert totals["unknown_pct"] < 5  # la falla de la lámpara es de Barranquilla


# ---------- lecturas: las historias plantadas se pueden encontrar ----------
def test_timeline_correlates_rejections_with_camera_not_with_model(plant):
    sup = plant.user("u-sup-01")
    data = plant.ex.execute(sup, "get_line_timeline", {"line_id": "L1", "start": "2026-10-09T21:00",
                                                       "end": "2026-10-10T06:00", "bucket_minutes": 60})["data"]
    by = {b["bucket"][11:13]: b for b in data["buckets"]}
    assert by["03"]["unknown_pct"] > 40 and by["03"]["camera_status"] == "DEGRADED"
    assert by["23"]["unknown_pct"] < 5 and by["23"]["camera_status"] == "OK"  # tras promover el modelo no cambia nada
    assert {e["type"] for e in data["line_events"]} == {"MODEL_PROMOTED", "MAINTENANCE"}
    cam = plant.ex.execute(sup, "get_camera_health", {"line_id": "L1", "start": "2026-10-10T02:00",
                                                      "end": "2026-10-10T05:00"})["data"]
    assert cam["status"] == "DEGRADED" and cam["min_brightness_vs_nominal_pct"] < -25


def test_grasp_failures_point_to_three_skus(plant):
    mnt = plant.user("u-mnt-01")
    data = plant.ex.execute(mnt, "get_grasp_failures", {"line_id": "L2", "start": "2026-10-10T15:30",
                                                        "end": "2026-10-10T17:30"})["data"]
    assert {r["object_id"] for r in data["by_sku"][:3]} == {23, 47, 81}
    assert data["failure_pct"] > 5 and data["share_of_failures_in_top3_skus_pct"] > 80


def test_shift_metrics_and_handover(plant):
    sup = plant.user("u-sup-01")
    m = plant.ex.execute(sup, "get_shift_metrics", {"line_id": "L1", "shift": 2})["data"]
    assert m["in_progress"] and m["totals"]["objects"] == 420 and len(m["by_hour"]) == 4
    h = plant.ex.execute(sup, "create_shift_handover", {"line_id": "L1", "shift": 3})["data"]
    kinds = {i["type"] for i in h["incidents"]}
    assert {"MODEL_PROMOTED", "CAMERA_DEGRADED", "HIGH_REJECTIONS", "MAINTENANCE"} <= kinds
    assert len(h["pending_review_cases"]) == 8 and h["open_tickets"][0]["ticket_id"] == "TCK-1043"
    again = plant.ex.execute(sup, "create_shift_handover", {"line_id": "L1", "shift": 3})["data"]
    assert again["handover_id"] == h["handover_id"] and again["replaced_previous"]
    assert one(plant.con, "SELECT COUNT(*) AS n FROM handovers")["n"] == 1


# ---------- inspección de imagen contra el servicio de visión real ----------
def test_inspect_unknown_image_and_session_isolation(plant):
    sup = plant.user("u-sup-01")
    up = plant.upload(sup, blob())
    r = plant.ex.execute(sup, "inspect_images", {"image_ids": [up["images"][0]["image_id"]]})["data"]["results"][0]
    assert r["decision"] == "UNKNOWN" and r["robot_command"]["action"] == "DIVERT_TO_REJECT"
    assert "rechazo" in r["recommended_action"] and r["similar_views_by_appearance"][0]["reference_url"]
    other = plant.user("u-qa-01", session="otra-sesion")
    denied = plant.ex.execute(other, "inspect_images", {"image_ids": [up["images"][0]["image_id"]]})
    assert denied["error"]["code"] == "image_not_found"


def test_vision_outage_is_a_structured_retryable_error(plant):
    sup = plant.user("u-sup-01")
    image_id = plant.upload(sup, blob())["images"][0]["image_id"]
    plant.vision_http.post("/admin/fault", json={"mode": "error", "count": 5})
    r = plant.ex.execute(sup, "inspect_images", {"image_ids": [image_id]})
    assert r["error"]["code"] == "vision_unavailable" and r["error"]["retryable"]
    assert plant.vision_http.get("/admin/fault").json()["remaining"] == 3  # 1 intento + 1 reintento, no más
    assert audit(plant)[0]["detail"] == "vision_unavailable"


# ---------- escrituras de riesgo bajo: efectos repetidos ----------
def test_review_case_resolution_is_idempotent(plant):
    sup = plant.user("u-sup-01")
    args = {"case_id": "RC-0001", "confirmed_object_id": 12, "confirmed_angle_deg": 45.0}
    assert plant.ex.execute(sup, "add_to_retraining_dataset", {"case_id": "RC-0001"})["error"]["code"] == "precondition_failed"
    assert plant.ex.execute(sup, "resolve_review_case", args)["data"]["status"] == "RESOLVED"
    assert plant.ex.execute(sup, "resolve_review_case", args)["data"]["already_resolved"]
    assert plant.ex.execute(sup, "resolve_review_case", {**args, "confirmed_object_id": 13})["error"]["code"] == "conflict"
    assert plant.ex.execute(sup, "add_to_retraining_dataset", {"case_id": "RC-0001"})["data"]["added"]
    assert plant.ex.execute(sup, "add_to_retraining_dataset", {"case_id": "RC-0001"})["data"]["already_in_dataset"]
    assert one(plant.con, "SELECT COUNT(*) AS n FROM retraining_items")["n"] == 1


def test_tickets_are_deduplicated_and_escalation_is_idempotent(plant):
    mnt = plant.user("u-mnt-01")
    args = {"line_id": "L2", "title": "Agarres fallidos en SKU 23, 47 y 81",
            "description": "Desde las 15:30, 14,7 % de fallos concentrados en tres SKU.", "severity": "high"}
    first = plant.ex.execute(mnt, "create_ticket", args)["data"]
    second = plant.ex.execute(mnt, "create_ticket", args)["data"]
    assert not first["deduplicated"] and second["deduplicated"] and second["ticket_id"] == first["ticket_id"]
    esc = {"ticket_id": first["ticket_id"], "reason": "Supera el 5 % durante más de 15 minutos."}
    assert plant.ex.execute(mnt, "escalate_ticket", esc)["data"]["assignee"] == "u-mgr-01"
    assert plant.ex.execute(mnt, "escalate_ticket", esc)["data"]["already_escalated"]


# ---------- operaciones de riesgo: nunca sin aprobación humana ----------
PAUSE = {"line_id": "L2", "state": "PAUSED", "reason": "Agarres fallidos por encima del 5 %"}


def test_risky_operation_is_not_executed_until_a_human_approves(plant):
    mnt, sup, mgr = plant.user("u-mnt-01"), plant.user("u-sup-01"), plant.user("u-mgr-01")
    req = plant.ex.execute(mnt, "set_line_state", PAUSE)["data"]
    assert req["status"] == "pending_approval" and not req["executed"]
    assert one(plant.con, "SELECT status FROM lines WHERE plant_id='BAQ' AND line_id='L2'")["status"] == "RUNNING"
    assert plant.ex.execute(mnt, "set_line_state", PAUSE)["data"]["approval_id"] == req["approval_id"]  # no duplica
    assert plant.ex.decide(mnt, req["approval_id"], True)["error"]["code"] == "permission_denied"
    assert plant.ex.decide(plant.user("u-sup-02"), req["approval_id"], True)["error"]["code"] == "not_found"  # otra planta
    done = plant.ex.decide(sup, req["approval_id"], True)["data"]
    assert done["status"] == "EXECUTED" and done["result"]["status"] == "PAUSED"
    assert plant.ex.decide(mgr, req["approval_id"], True)["data"]["already_decided"]  # no se ejecuta dos veces
    events = rows(plant.con, "SELECT actor FROM line_events WHERE type='LINE_PAUSED'")
    assert events == [{"actor": "u-mnt-01 (aprobó u-sup-01)"}]
    assert audit(plant)[0] == {"tool": "approval:set_line_state", "outcome": "ok", "detail": "executed",
                               "source": "human", "user_id": "u-sup-01"}


def test_separation_of_duties_and_rejection(plant):
    ml, qa, sup = plant.user("u-ml-01"), plant.user("u-qa-01"), plant.user("u-sup-01")
    bad = plant.ex.execute(ml, "set_confidence_threshold", {"line_id": "L1", "value": 0.0, "reason": "probar sin umbral"})
    assert bad["error"]["code"] == "invalid_arguments"  # fuera de 0,20–0,95: ni siquiera se crea la solicitud
    req = plant.ex.execute(qa, "set_confidence_threshold", {"line_id": "L1", "value": 0.5, "reason": "reducir errores de clase"})["data"]
    assert plant.ex.decide(qa, req["approval_id"], True)["error"]["code"] == "separation_of_duties"
    assert plant.ex.decide(plant.user("u-mgr-01"), req["approval_id"], False, "sin evidencia")["data"]["status"] == "REJECTED"
    assert one(plant.con, "SELECT class_conf_min FROM lines WHERE plant_id='BAQ' AND line_id='L1'")["class_conf_min"] == 0.334
    own = plant.ex.execute(sup, "set_line_state", {**PAUSE, "line_id": "L1"})["data"]
    assert plant.ex.decide(sup, own["approval_id"], True)["data"]["status"] == "EXECUTED"  # excepción: pausa por seguridad
    resume = plant.ex.execute(sup, "set_line_state", {"line_id": "L1", "state": "RUNNING", "reason": "problema resuelto"})["data"]
    assert plant.ex.decide(sup, resume["approval_id"], True)["error"]["code"] == "separation_of_duties"


def test_preconditions_are_checked_on_request_and_again_on_approval(plant):
    sup, mgr, ml, qa = (plant.user(u) for u in ("u-sup-01", "u-mgr-01", "u-ml-01", "u-qa-01"))
    angle = {"line_id": "L1", "object_id": 5, "angle_deg": 40.0, "reason": "objeto atascado en la posición de agarre"}
    assert plant.ex.execute(sup, "send_manual_angle", angle)["error"]["code"] == "precondition_failed"  # línea en marcha
    pause = plant.ex.execute(sup, "set_line_state", {**PAUSE, "line_id": "L1"})["data"]
    plant.ex.decide(sup, pause["approval_id"], True)
    req = plant.ex.execute(sup, "send_manual_angle", angle)["data"]
    resume = plant.ex.execute(sup, "set_line_state", {"line_id": "L1", "state": "RUNNING", "reason": "se reanuda la línea"})["data"]
    plant.ex.decide(mgr, resume["approval_id"], True)
    failed = plant.ex.decide(mgr, req["approval_id"], True)  # la línea ya no está en pausa cuando se aprueba
    assert not failed["ok"] and failed["data"]["status"] == "FAILED"
    assert rows(plant.con, "SELECT 1 FROM line_events WHERE type='MANUAL_ANGLE'") == []
    assert plant.ex.execute(ml, "promote_model_version", {"line_id": "L1", "version": "4e39f878-rf",
                                                          "reason": "ya está en producción"})["error"]["code"] == "precondition_failed"
    promo = plant.ex.execute(ml, "promote_model_version", {"line_id": "L1", "version": "9f2d6c11-rf",
                                                           "reason": "mejor robustez a la iluminación"})["data"]
    assert plant.ex.decide(qa, promo["approval_id"], True)["data"]["result"]["model_version"] == "9f2d6c11-rf"


# ---------- alta de producto ----------
def test_sku_onboarding_rejects_insufficient_material(plant):
    ml = plant.user("u-ml-01")
    few = plant.upload(ml, *[blob(shift=i) for i in range(12)])
    r = plant.ex.execute(ml, "register_sku_candidate", {"name": "Caja roja", "batch_id": few["batch_id"], "step_deg": 30})["data"]
    assert not r["accepted"] and [c["ok"] for c in r["checks"]] == [False, True]
    assert one(plant.con, "SELECT COUNT(*) AS n FROM sku_candidates")["n"] == 0


def test_sku_onboarding_accepts_a_new_product_and_promotion_needs_approval(plant):
    ml, qa = plant.user("u-ml-01"), plant.user("u-qa-01")
    views = plant.upload(ml, *[blob(color=(40, 60, 220), shift=i % 20) for i in range(36)])
    args = {"name": "Caja azul", "batch_id": views["batch_id"], "step_deg": 10}
    r = plant.ex.execute(ml, "register_sku_candidate", args)["data"]
    assert r["accepted"] and r["status"] == "STAGING" and r["max_gap_deg"] == 10
    assert r["validation"]["staging_evaluation"]["simulated"] is True
    assert plant.ex.execute(ml, "register_sku_candidate", args)["data"]["already_registered"]
    req = plant.ex.execute(ml, "request_sku_promotion", {"candidate_id": r["candidate_id"]})["data"]
    assert one(plant.con, "SELECT status FROM sku_candidates")["status"] == "STAGING"
    assert plant.ex.decide(qa, req["approval_id"], True)["data"]["result"]["status"] == "PRODUCTION"


@pytest.mark.skipif(not (COIL / "obj5__0.png").is_file(), reason="dataset no disponible")
def test_sku_onboarding_detects_a_product_already_in_the_catalog(plant):
    ml = plant.user("u-ml-01")
    views = [np.asarray(Image.open(COIL / f"obj5__{a}.png").convert("RGB")) for a in range(0, 360, 10)]
    batch = plant.upload(ml, *views)
    r = plant.ex.execute(ml, "register_sku_candidate", {"name": "Producto repetido", "batch_id": batch["batch_id"], "step_deg": 10})["data"]
    assert not r["accepted"] and not r["checks"][-1]["ok"] and "[5]" in r["checks"][-1]["detail"]
