"""Tools de escritura. Las de riesgo bajo se ejecutan directamente; las de riesgo alto solo las ejecuta
la capa de política después de una aprobación humana (su handler es lo que ocurre al aprobar)."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Literal

from pydantic import Field

from ..plant.db import one, rows
from ..plant.seed import iso, shift_window
from .base import Args, Principal, ToolContext, ToolError, ToolSpec, register
from .read import LINE, CaseArgs, ShiftArgs, _rates, _where, get_shift_metrics, load_case

REVIEWERS = frozenset({"supervisor", "quality"})
MIN_SKU_VIEWS, MAX_SKU_GAP = 36, 30.0  # SOP-ML-004 § 1


def _line(ctx: ToolContext, line_id: str) -> dict:
    line = one(ctx.con, "SELECT * FROM lines WHERE plant_id=? AND line_id=?", (ctx.principal.plant_id, line_id))
    if not line:
        raise ToolError("not_found", f"no existe la línea {line_id} en la planta {ctx.principal.plant_id}")
    return line


def _line_event(ctx: ToolContext, line_id: str, kind: str, detail: str) -> None:
    actor = ctx.principal.user_id if not ctx.requested_by else f"{ctx.requested_by} (aprobó {ctx.principal.user_id})"
    ctx.con.execute("INSERT INTO line_events (ts, plant_id, line_id, type, detail, actor) VALUES (?,?,?,?,?,?)",
                    (iso(ctx.now), ctx.principal.plant_id, line_id, kind, detail, actor))


# ---------- 12. resolver un caso de revisión ----------
class ResolveArgs(Args):
    case_id: str = Field(description="Caso a resolver, por ejemplo RC-0003", pattern=r"^RC-\d{4}$")
    confirmed_object_id: int = Field(description="Producto (SKU) confirmado por la persona", ge=1, le=100000)
    confirmed_angle_deg: float = Field(description="Ángulo confirmado por la persona, en grados", ge=0, lt=360)


def resolve_review_case(ctx: ToolContext, a: ResolveArgs) -> dict:
    case = load_case(ctx, a.case_id)
    same = (case["confirmed_object_id"], case["confirmed_angle_deg"]) == (a.confirmed_object_id, a.confirmed_angle_deg)
    if case["status"] == "RESOLVED":
        if same:
            return {"case_id": a.case_id, "status": "RESOLVED", "already_resolved": True, "resolved_by": case["resolved_by"]}
        raise ToolError("conflict", f"{a.case_id} ya fue resuelto por {case['resolved_by']} con SKU "
                                    f"{case['confirmed_object_id']} y ángulo {case['confirmed_angle_deg']}")
    ctx.con.execute("""UPDATE review_cases SET status='RESOLVED', confirmed_object_id=?, confirmed_angle_deg=?,
                       resolved_by=?, resolved_at=? WHERE case_id=? AND status='PENDING'""",
                    (a.confirmed_object_id, a.confirmed_angle_deg, ctx.principal.user_id, iso(ctx.now), a.case_id))
    return {"case_id": a.case_id, "status": "RESOLVED", "confirmed_object_id": a.confirmed_object_id,
            "confirmed_angle_deg": a.confirmed_angle_deg, "resolved_by": ctx.principal.user_id}


register(ToolSpec(
    "resolve_review_case", "Registra la etiqueta (SKU) y el ángulo que una persona ha confirmado para un caso de "
    "la cola de revisión. Úsala solo con valores que el usuario haya dado explícitamente en la conversación.",
    ResolveArgs, resolve_review_case, "write", roles=REVIEWERS,
    side_effects="marca el caso como resuelto con el usuario de la sesión como responsable",
    idempotency="repetir con los mismos valores devuelve already_resolved; con otros valores, error conflict",
    failure_modes=("not_found", "conflict", "permission_denied"), use_cases=("cola de revisión humana",)))


# ---------- 13. enviar a reentrenamiento ----------
def add_to_retraining_dataset(ctx: ToolContext, a: CaseArgs) -> dict:
    case = load_case(ctx, a.case_id)
    if case["status"] != "RESOLVED":
        raise ToolError("precondition_failed", f"{a.case_id} aún no tiene etiqueta y ángulo confirmados por una persona")
    cur = ctx.con.execute(
        "INSERT OR IGNORE INTO retraining_items (case_id, plant_id, line_id, object_id, angle_deg, added_by, added_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (a.case_id, case["plant_id"], case["line_id"], case["confirmed_object_id"], case["confirmed_angle_deg"],
         ctx.principal.user_id, iso(ctx.now)))
    size = one(ctx.con, "SELECT COUNT(*) AS n FROM retraining_items WHERE plant_id=?", (case["plant_id"],))["n"]
    return {"case_id": a.case_id, "added": cur.rowcount == 1, "already_in_dataset": cur.rowcount == 0,
            "object_id": case["confirmed_object_id"], "angle_deg": case["confirmed_angle_deg"], "dataset_size": size}


register(ToolSpec(
    "add_to_retraining_dataset", "Añade un caso de revisión ya resuelto al dataset de reentrenamiento, con su "
    "etiqueta y su ángulo confirmados.",
    CaseArgs, add_to_retraining_dataset, "write", roles=REVIEWERS,
    side_effects="inserta un elemento en el dataset de reentrenamiento",
    idempotency="un caso solo entra una vez (restricción única); repetir devuelve already_in_dataset",
    failure_modes=("not_found", "precondition_failed"), use_cases=("cola de revisión humana",)))


# ---------- 14 y 15. tickets ----------
class CreateTicketArgs(Args):
    line_id: str = LINE
    title: str = Field(min_length=5, max_length=120)
    description: str = Field(min_length=10, max_length=2000,
                             description="Ventana horaria, SKU afectados, comprobaciones hechas y diagnóstico")
    severity: Literal["low", "medium", "high", "critical"]


def create_ticket(ctx: ToolContext, a: CreateTicketArgs) -> dict:
    _line(ctx, a.line_id)
    dup = one(ctx.con, """SELECT ticket_id, status FROM tickets WHERE plant_id=? AND line_id=? AND created_by=?
                          AND lower(title)=lower(?) AND status!='RESOLVED'""",
              (ctx.principal.plant_id, a.line_id, ctx.principal.user_id, a.title))
    if dup:
        return {**dup, "deduplicated": True, "message": "ya existe un ticket abierto igual; no se creó otro"}
    n = one(ctx.con, "SELECT COUNT(*) AS n FROM tickets")["n"]
    ticket_id = f"TCK-{1042 + n}"
    ctx.con.execute("INSERT INTO tickets VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (ticket_id, ctx.principal.plant_id, a.line_id, a.title, a.description, a.severity, "OPEN",
                     ctx.principal.user_id, iso(ctx.now), None, iso(ctx.now)))
    return {"ticket_id": ticket_id, "status": "OPEN", "severity": a.severity, "deduplicated": False}


class EscalateArgs(Args):
    ticket_id: str = Field(pattern=r"^TCK-\d{3,6}$")
    reason: str = Field(min_length=10, max_length=500)


def escalate_ticket(ctx: ToolContext, a: EscalateArgs) -> dict:
    t = one(ctx.con, "SELECT * FROM tickets WHERE ticket_id=? AND plant_id=?", (a.ticket_id, ctx.principal.plant_id))
    if not t or t["line_id"] not in ctx.principal.lines:
        raise ToolError("not_found", f"no existe el ticket {a.ticket_id} en tus líneas")
    if t["status"] == "RESOLVED":
        raise ToolError("precondition_failed", f"{a.ticket_id} está resuelto; crea uno nuevo si el problema volvió")
    if t["status"] == "ESCALATED":
        return {"ticket_id": a.ticket_id, "status": "ESCALATED", "already_escalated": True, "assignee": t["assignee"]}
    manager = one(ctx.con, "SELECT user_id FROM users WHERE plant_id=? AND role='plant_manager'", (ctx.principal.plant_id,))
    assignee = manager["user_id"] if manager else None
    ctx.con.execute("UPDATE tickets SET status='ESCALATED', assignee=?, updated_at=?, description=description || ? WHERE ticket_id=?",
                    (assignee, iso(ctx.now), f"\n[Escalado por {ctx.principal.user_id}: {a.reason}]", a.ticket_id))
    return {"ticket_id": a.ticket_id, "status": "ESCALATED", "already_escalated": False, "assignee": assignee}


TICKET_ROLES = frozenset({"supervisor", "maintenance", "quality", "plant_manager"})
register(ToolSpec(
    "create_ticket", "Crea un ticket de mantenimiento o incidencia para una línea.",
    CreateTicketArgs, create_ticket, "write", roles=TICKET_ROLES, side_effects="crea un ticket abierto",
    idempotency="mismo usuario, línea y título con un ticket aún abierto: devuelve el existente (deduplicated)",
    failure_modes=("not_found", "invalid_arguments"), use_cases=("diagnóstico de falla",)))
register(ToolSpec(
    "escalate_ticket", "Escala un ticket abierto al gerente de planta, con el motivo.",
    EscalateArgs, escalate_ticket, "write", roles=TICKET_ROLES,
    side_effects="cambia el estado a ESCALATED y asigna al gerente de planta",
    idempotency="escalar un ticket ya escalado no cambia nada (already_escalated)",
    failure_modes=("not_found", "precondition_failed"), use_cases=("diagnóstico de falla",)))


# ---------- 16. entrega de turno ----------
def create_shift_handover(ctx: ToolContext, a: ShiftArgs) -> dict:
    m = get_shift_metrics(ctx, a)
    start, end = shift_window(a.shift, ctx.now)
    s, e = iso(start), iso(min(end, ctx.now))
    w, p = _where(ctx, a.line_id)
    incidents = [{"at": r["ts"], "type": r["type"], "detail": r["detail"]} for r in rows(
        ctx.con, f"SELECT ts, type, detail FROM line_events WHERE {w} AND ts>=? AND ts<? ORDER BY ts", (*p, s, e))]
    cam = one(ctx.con, f"""SELECT MIN(ts) AS a, MAX(ts) AS b, ROUND(MIN(brightness),3) AS low FROM camera_health
                           WHERE {w} AND ts>=? AND ts<? AND status='DEGRADED'""", (*p, s, e))
    if cam["a"]:
        incidents.append({"at": cam["a"], "type": "CAMERA_DEGRADED",
                          "detail": f"cámara degradada hasta {cam['b']}; brillo mínimo {cam['low']}"})
    t = start
    while t < min(end, ctx.now):  # SOP-OPS-006 § 2: intervalos de 30 min con rechazos sobre el 10 %
        r = _rates(ctx, a.line_id, iso(t), iso(t + timedelta(minutes=30)))
        rejected = (r["unknown_pct"] or 0) + (r["review_pct"] or 0)
        if r["objects"] and rejected > 10:
            incidents.append({"at": iso(t), "type": "HIGH_REJECTIONS", "detail": f"{rejected:.1f} % de rechazos en 30 min"})
        t += timedelta(minutes=30)
    if (m["totals"]["grasp_failure_pct"] or 0) > 5:
        incidents.append({"at": s, "type": "GRASP_FAILURES",
                          "detail": f"{m['totals']['grasp_failure_pct']} % de agarres fallidos en el turno"})
    report = {
        "line_id": a.line_id, "shift": a.shift, "window": m["window"], "in_progress": m["in_progress"],
        "totals": m["totals"], "line": {k: _line(ctx, a.line_id)[k] for k in ("status", "class_conf_min", "model_version")},
        "incidents": sorted(incidents, key=lambda i: i["at"]),
        "open_tickets": rows(ctx.con, f"SELECT ticket_id, title, severity, status FROM tickets WHERE {w} AND status!='RESOLVED'", p),
        "pending_review_cases": [r["case_id"] for r in rows(
            ctx.con, f"SELECT case_id FROM review_cases WHERE {w} AND status='PENDING' ORDER BY case_id", p)],
        "pending_approvals": [r["approval_id"] for r in rows(
            ctx.con, "SELECT approval_id FROM approvals WHERE plant_id=? AND line_id=? AND status='PENDING'", p)],
    }
    handover_id = f"HO-{ctx.principal.plant_id}-{a.line_id}-{start:%Y%m%d}-T{a.shift}"
    existed = one(ctx.con, "SELECT 1 AS x FROM handovers WHERE handover_id=?", (handover_id,)) is not None
    ctx.con.execute("INSERT OR REPLACE INTO handovers VALUES (?,?,?,?,?,?,?,?)",
                    (handover_id, ctx.principal.plant_id, a.line_id, a.shift, s, ctx.principal.user_id, iso(ctx.now),
                     json.dumps(report, ensure_ascii=False)))
    return {"handover_id": handover_id, "replaced_previous": existed, **report}


register(ToolSpec(
    "create_shift_handover", "Genera y guarda el reporte de entrega de un turno: métricas, incidentes detectados "
    "con las reglas del procedimiento, tickets abiertos, casos pendientes de revisión y aprobaciones pendientes.",
    ShiftArgs, create_shift_handover, "write", roles=frozenset({"supervisor", "plant_manager"}),
    side_effects="guarda el reporte con un identificador por línea, fecha y turno",
    idempotency="un reporte por línea y turno: regenerarlo reemplaza el anterior (replaced_previous)",
    model_sees="el reporte estructurado; las cifras salen de la base, no del modelo",
    use_cases=("entrega de turno",)))


# ---------- 17. alta de producto en staging ----------
class RegisterSkuArgs(Args):
    name: str = Field(description="Nombre del producto nuevo", min_length=3, max_length=60)
    batch_id: str = Field(description="Lote de imágenes cargado en esta sesión (lote-...)", pattern=r"^lote-[0-9a-f]{8}$")
    step_deg: float = Field(description="Giro del plato entre vistas consecutivas, en grados. Las vistas se "
                                        "ordenan por nombre de archivo empezando en 0°", gt=0, le=120)


def register_sku_candidate(ctx: ToolContext, a: RegisterSkuArgs) -> dict:
    existing = one(ctx.con, "SELECT * FROM sku_candidates WHERE plant_id=? AND lower(name)=lower(?)",
                   (ctx.principal.plant_id, a.name))
    if existing:
        existing["validation"] = json.loads(existing["validation"])
        return {"accepted": True, "already_registered": True, **existing}
    images = ctx.images.batch(ctx.principal, a.batch_id, ctx.now)
    n = len(images)
    max_gap = max(a.step_deg, 360 - (n - 1) * a.step_deg) if n * a.step_deg <= 360 + 1e-6 else None
    checks = [
        {"check": "vistas suficientes", "ok": n >= MIN_SKU_VIEWS, "detail": f"{n} vistas (mínimo {MIN_SKU_VIEWS})"},
        {"check": "cobertura angular", "ok": max_gap is not None and max_gap <= MAX_SKU_GAP,
         "detail": f"hueco máximo {max_gap}° (máximo {MAX_SKU_GAP}°)" if max_gap is not None
         else f"{n} vistas × {a.step_deg}° superan una vuelta completa"},
    ]
    bad_capture, clashes = [], {}
    if all(c["ok"] for c in checks):  # solo se gasta inferencia si el material básico alcanza
        for i in range(0, n, 16):
            chunk = images[i:i + 16]
            resp = ctx.vision.predict([(m["image_id"], ctx.images.load(ctx.principal, m["image_id"], ctx.now)[1])
                                       for m in chunk], 1)
            for m, r in zip(chunk, resp["results"]):
                if r["decision"] == "BAD_CAPTURE":
                    bad_capture.append(m["filename"].split("/")[-1])
                elif r["decision"] != "UNKNOWN":
                    clashes[r["object_id"]] = clashes.get(r["object_id"], 0) + 1
        clash_n = sum(clashes.values())
        checks += [
            {"check": "calidad de captura", "ok": not bad_capture, "detail": f"{len(bad_capture)} capturas inválidas: {bad_capture[:5]}"},
            {"check": "no se confunde con el catálogo", "ok": clash_n <= 0.1 * n,
             "detail": f"{clash_n} de {n} vistas se identifican como SKU existentes {sorted(clashes)}"},
        ]
    if not all(c["ok"] for c in checks):
        return {"accepted": False, "name": a.name, "checks": checks,
                "message": "material insuficiente: no se incorporó a staging (SOP-ML-004 § 1)"}
    # evaluación en staging SIMULADA: la demo no reentrena el modelo; depende solo de la densidad de vistas
    within = 99.7 if a.step_deg <= 5 else 99.5 if a.step_deg <= 10 else 98.9
    validation = {"checks": checks, "staging_evaluation": {
        "simulated": True, "held_out_views": n // 4, "robot_actions_within_10deg_pct": within,
        "confusions_with_catalog": 0, "meets_acceptance_criterion": within >= 99.5}}
    count = one(ctx.con, "SELECT COUNT(*) AS n FROM sku_candidates")["n"]
    candidate_id = f"SKU-C-{count + 1:03d}"
    ctx.con.execute("INSERT INTO sku_candidates VALUES (?,?,?,?,?,?,?,?,?)",
                    (candidate_id, ctx.principal.plant_id, a.name, "STAGING", n, max_gap,
                     json.dumps(validation, ensure_ascii=False), ctx.principal.user_id, iso(ctx.now)))
    return {"accepted": True, "already_registered": False, "candidate_id": candidate_id, "name": a.name,
            "status": "STAGING", "n_views": n, "max_gap_deg": max_gap, "validation": validation}


SKU_ROLES = frozenset({"ml_engineer", "quality"})
register(ToolSpec(
    "register_sku_candidate", "Alta de un producto nuevo en staging a partir de un lote de vistas: valida que el "
    "material sea suficiente (número de vistas, cobertura angular, calidad de captura y que no se confunda con el "
    "catálogo), lo incorpora en el entorno controlado y devuelve la verificación de desempeño.",
    RegisterSkuArgs, register_sku_candidate, "write", roles=SKU_ROLES,
    side_effects="crea un candidato en staging; nunca toca producción",
    idempotency="un candidato por nombre y planta: repetir devuelve el existente (already_registered)",
    failure_modes=("batch_not_found", "vision_unavailable (reintentable)"),
    model_sees="resultado de cada comprobación; la evaluación en staging está simulada y así se marca",
    use_cases=("alta de producto nuevo",)))


# =====================  OPERACIONES DE RIESGO: solo se ejecutan tras aprobación humana  =====================
APPROVE_OPS = frozenset({"supervisor", "plant_manager"})
APPROVE_QUALITY = frozenset({"plant_manager", "quality"})


class CandidateArgs(Args):
    candidate_id: str = Field(pattern=r"^SKU-C-\d{3}$")


def _candidate(ctx: ToolContext, a: CandidateArgs) -> dict:
    c = one(ctx.con, "SELECT * FROM sku_candidates WHERE candidate_id=? AND plant_id=?", (a.candidate_id, ctx.principal.plant_id))
    if not c:
        raise ToolError("not_found", f"no existe el candidato {a.candidate_id}")
    if c["status"] != "STAGING":
        raise ToolError("precondition_failed", f"{a.candidate_id} está en estado {c['status']}, no en staging")
    if not json.loads(c["validation"])["staging_evaluation"]["meets_acceptance_criterion"]:
        raise ToolError("precondition_failed", f"{a.candidate_id} no cumple el criterio de aceptación en staging")
    return c


def promote_sku(ctx: ToolContext, a: CandidateArgs) -> dict:
    c = _candidate(ctx, a)
    ctx.con.execute("UPDATE sku_candidates SET status='PRODUCTION' WHERE candidate_id=?", (a.candidate_id,))
    return {"candidate_id": a.candidate_id, "name": c["name"], "status": "PRODUCTION"}


register(ToolSpec(
    "request_sku_promotion", "Solicita pasar a producción un producto que está en staging y cumple el criterio "
    "de aceptación. No lo ejecuta: crea una solicitud que debe aprobar calidad o el gerente de planta.",
    CandidateArgs, promote_sku, "write", roles=SKU_ROLES, risk="high", approvers=APPROVE_QUALITY,
    precheck=lambda ctx, a: _candidate(ctx, a) and None,
    side_effects="al aprobarse, el candidato pasa a producción",
    idempotency="una solicitud pendiente por operación y argumentos; aprobar dos veces no la re-ejecuta",
    failure_modes=("not_found", "precondition_failed"), use_cases=("alta de producto nuevo", "operación de riesgo")))


class ThresholdArgs(Args):
    line_id: str = LINE
    value: float = Field(description="Nuevo umbral mínimo de confianza de clase", ge=0.20, le=0.95)
    reason: str = Field(min_length=10, max_length=300)


def set_confidence_threshold(ctx: ToolContext, a: ThresholdArgs) -> dict:
    old = _line(ctx, a.line_id)["class_conf_min"]
    ctx.con.execute("UPDATE lines SET class_conf_min=?, updated_at=? WHERE plant_id=? AND line_id=?",
                    (a.value, iso(ctx.now), ctx.principal.plant_id, a.line_id))
    _line_event(ctx, a.line_id, "THRESHOLD_CHANGED", f"{old} -> {a.value}: {a.reason}")
    return {"line_id": a.line_id, "previous": old, "class_conf_min": a.value}


register(ToolSpec(
    "set_confidence_threshold", "Solicita cambiar el umbral de confianza de una línea (entre 0,20 y 0,95). No lo "
    "ejecuta: crea una solicitud que debe aprobar calidad o el gerente de planta.",
    ThresholdArgs, set_confidence_threshold, "write", roles=frozenset({"ml_engineer", "quality"}), risk="high",
    approvers=APPROVE_QUALITY, precheck=lambda ctx, a: _line(ctx, a.line_id) and None,
    side_effects="al aprobarse, cambia el umbral de la línea y registra el evento",
    idempotency="una solicitud pendiente por operación y argumentos; aprobar dos veces no la re-ejecuta",
    failure_modes=("invalid_arguments (fuera de 0,20–0,95)", "not_found"), use_cases=("operación de riesgo",)))


class LineStateArgs(Args):
    line_id: str = LINE
    state: Literal["PAUSED", "RUNNING"] = Field(description="PAUSED para pausar, RUNNING para reanudar")
    reason: str = Field(min_length=10, max_length=300)


def _state_precheck(ctx: ToolContext, a: LineStateArgs) -> None:
    if _line(ctx, a.line_id)["status"] == a.state:
        raise ToolError("no_change", f"la línea {a.line_id} ya está en estado {a.state}")


def set_line_state(ctx: ToolContext, a: LineStateArgs) -> dict:
    _state_precheck(ctx, a)
    ctx.con.execute("UPDATE lines SET status=?, updated_at=? WHERE plant_id=? AND line_id=?",
                    (a.state, iso(ctx.now), ctx.principal.plant_id, a.line_id))
    _line_event(ctx, a.line_id, "LINE_PAUSED" if a.state == "PAUSED" else "LINE_RESUMED", a.reason)
    return {"line_id": a.line_id, "status": a.state}


def _supervisor_can_pause(p: Principal, a: LineStateArgs) -> bool:
    return p.role == "supervisor" and a.state == "PAUSED"  # SOP-OPS-005 § 4


register(ToolSpec(
    "set_line_state", "Solicita pausar o reanudar una línea. No lo ejecuta: crea una solicitud que debe aprobar "
    "un supervisor o el gerente de planta.",
    LineStateArgs, set_line_state, "write", roles=frozenset({"supervisor", "maintenance", "plant_manager"}),
    risk="high", approvers=APPROVE_OPS, self_approval=_supervisor_can_pause, precheck=_state_precheck,
    side_effects="al aprobarse, cambia el estado de la línea y registra el evento",
    idempotency="si la línea ya está en ese estado devuelve no_change; una solicitud pendiente por argumentos",
    failure_modes=("not_found", "no_change"), use_cases=("operación de riesgo", "diagnóstico de falla")))


class ManualAngleArgs(Args):
    line_id: str = LINE
    object_id: int = Field(ge=1, le=100000, description="Producto que está en la posición de agarre")
    angle_deg: float = Field(ge=0, lt=360, description="Ángulo que el robot debe compensar")
    reason: str = Field(min_length=10, max_length=300)


def _paused(ctx: ToolContext, a: ManualAngleArgs) -> None:
    if _line(ctx, a.line_id)["status"] != "PAUSED":
        raise ToolError("precondition_failed", "un ángulo manual solo se envía con la línea en pausa (SOP-OPS-005 § 5)")


def send_manual_angle(ctx: ToolContext, a: ManualAngleArgs) -> dict:
    _paused(ctx, a)
    _line_event(ctx, a.line_id, "MANUAL_ANGLE", f"SKU {a.object_id} a {a.angle_deg}°: {a.reason}")
    return {"line_id": a.line_id, "sent_to_robot": {"action": "PICK", "object_id": a.object_id, "angle_deg": a.angle_deg}}


register(ToolSpec(
    "send_manual_angle", "Solicita enviar al robot un ángulo indicado manualmente para el objeto que está en la "
    "posición de agarre. Solo con la línea en pausa. No lo ejecuta: requiere aprobación de un supervisor o gerente.",
    ManualAngleArgs, send_manual_angle, "write", roles=frozenset({"supervisor", "maintenance"}), risk="high",
    approvers=APPROVE_OPS, precheck=_paused,
    side_effects="al aprobarse, el robot recibe la orden y se registra el evento",
    idempotency="una solicitud pendiente por argumentos; una solicitud ejecutada no se puede repetir",
    failure_modes=("precondition_failed (línea en marcha)", "invalid_arguments"), use_cases=("operación de riesgo",)))


class PromoteModelArgs(Args):
    line_id: str = LINE
    version: str = Field(description="Versión de modelo en staging que se quiere poner en producción", min_length=3, max_length=40)
    reason: str = Field(min_length=10, max_length=300)


def _staging(ctx: ToolContext, a: PromoteModelArgs) -> None:
    _line(ctx, a.line_id)
    v = one(ctx.con, "SELECT stage FROM model_versions WHERE version=?", (a.version,))
    if not v:
        raise ToolError("not_found", f"no existe la versión de modelo {a.version}")
    if v["stage"] != "staging":
        raise ToolError("precondition_failed", f"{a.version} está en '{v['stage']}'; solo se promueve desde staging")


def promote_model_version(ctx: ToolContext, a: PromoteModelArgs) -> dict:
    _staging(ctx, a)
    old = _line(ctx, a.line_id)["model_version"]
    ctx.con.execute("UPDATE lines SET model_version=?, updated_at=? WHERE plant_id=? AND line_id=?",
                    (a.version, iso(ctx.now), ctx.principal.plant_id, a.line_id))
    ctx.con.execute("UPDATE model_versions SET stage='production' WHERE version=?", (a.version,))
    _line_event(ctx, a.line_id, "MODEL_PROMOTED", f"{old} -> {a.version}: {a.reason}")
    return {"line_id": a.line_id, "previous": old, "model_version": a.version}


register(ToolSpec(
    "promote_model_version", "Solicita promover a producción en una línea una versión de modelo que está en "
    "staging. No lo ejecuta: crea una solicitud que debe aprobar calidad o el gerente de planta.",
    PromoteModelArgs, promote_model_version, "write", roles=frozenset({"ml_engineer"}), risk="high",
    approvers=APPROVE_QUALITY, precheck=_staging,
    side_effects="al aprobarse, la línea pasa a usar la versión y se registra el evento",
    idempotency="una solicitud pendiente por argumentos; tras ejecutarse la versión ya no está en staging",
    failure_modes=("not_found", "precondition_failed"), use_cases=("operación de riesgo",)))
