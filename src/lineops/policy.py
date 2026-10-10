"""Capa de política: la única vía por la que se ejecuta una tool. Todo aquí es determinista.

Decisiones que nunca toma el modelo de lenguaje y dónde se toman:
  - qué tools existen y con qué argumentos        -> validación contra el contrato (pydantic)
  - quién puede usar cada tool                     -> rol de la sesión autenticada
  - sobre qué planta y línea                       -> la planta sale de la sesión; la línea se comprueba
  - si una operación de riesgo se ejecuta          -> solicitud + aprobación humana fuera de la conversación
  - quién puede aprobar                            -> rol aprobador y separación de funciones
  - qué queda registrado                           -> auditoría de cada intento, también de los rechazados

El modelo propone llamadas; esta capa las acepta, las rechaza o las convierte en una solicitud pendiente.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import time
from dataclasses import replace
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from .plant.db import one, rows
from .plant.seed import iso
from .tools import REGISTRY, Principal, ToolContext, ToolError
from .tools.base import line_of

log = logging.getLogger("lineops.policy")
MAX_AUDIT_ARG_CHARS = 2000


def principal_for(con: sqlite3.Connection, user_id: str, session_id: str) -> Principal:
    u = one(con, "SELECT * FROM users WHERE user_id=?", (user_id,))
    if not u:
        raise ToolError("unauthenticated", "usuario desconocido")
    return Principal(u["user_id"], u["name"], u["role"], u["plant_id"], tuple(json.loads(u["lines"])), session_id)


def _error(code: str, message: str, **extra) -> dict:
    return {"ok": False, "error": {"code": code, "message": message, "retryable": False, **extra}}


class Executor:
    def __init__(self, con: sqlite3.Connection, vision: Any, kb: Any, images: Any, settings: Any, now: datetime):
        self.con, self.vision, self.kb, self.images, self.settings, self.now = con, vision, kb, images, settings, now
        self._lock = threading.RLock()  # una conexión compartida: las tools se ejecutan de una en una

    def context(self, principal: Principal, requested_by: str | None = None) -> ToolContext:
        return ToolContext(self.con, principal, self.now, self.vision, self.kb, self.images, self.settings, requested_by)

    def allowed_tools(self, principal: Principal) -> list[str]:
        return sorted(name for name, spec in REGISTRY.items() if principal.role in spec.roles)

    def _audit(self, principal: Principal, tool: str, args: Any, outcome: str, detail: str | None,
               t0: float, source: str = "agent") -> None:
        text = json.dumps(args, ensure_ascii=False, default=str)[:MAX_AUDIT_ARG_CHARS]
        self.con.execute(
            "INSERT INTO audit_log (ts, session_id, user_id, role, plant_id, tool, args, outcome, detail, latency_ms, source)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (iso(self.now), principal.session_id, principal.user_id, principal.role, principal.plant_id, tool, text,
             outcome, detail, round((time.perf_counter() - t0) * 1000, 1), source))

    # ------------------------------------------------------------------ ejecución pedida por el agente
    def execute(self, principal: Principal, name: str, raw_args: Any) -> dict:
        with self._lock:
            return self._execute(principal, name, raw_args)

    def _execute(self, principal: Principal, name: str, raw_args: Any) -> dict:
        t0 = time.perf_counter()
        spec = REGISTRY.get(name)
        if spec is None:
            self._audit(principal, str(name)[:80], raw_args, "invalid", "unknown_tool", t0)
            return _error("unknown_tool", f"no existe la tool '{name}'", available_tools=self.allowed_tools(principal))
        if not isinstance(raw_args, dict):
            raw_args = {}
        try:
            args = spec.args.model_validate(raw_args)
        except ValidationError as e:
            problems = [{"field": ".".join(map(str, err["loc"])), "problem": err["msg"]} for err in e.errors()]
            self._audit(principal, name, raw_args, "invalid", "invalid_arguments", t0)
            return _error("invalid_arguments", "los argumentos no cumplen el contrato de la tool", problems=problems,
                          expected=spec.json_schema().get("properties", {}))
        if principal.role not in spec.roles:
            self._audit(principal, name, raw_args, "denied", "permission_denied", t0)
            return _error("permission_denied", f"el rol '{principal.role}' no puede usar {name}",
                          allowed_roles=sorted(spec.roles))
        line_id = line_of(args)
        if line_id is not None and line_id not in principal.lines:
            self._audit(principal, name, raw_args, "denied", "out_of_scope", t0)
            return _error("out_of_scope", f"no tienes acceso a la línea {line_id} de la planta {principal.plant_id}",
                          your_lines=list(principal.lines))
        ctx = self.context(principal)
        try:
            if spec.risk == "high":
                if spec.precheck:
                    spec.precheck(ctx, args)
                result = self._request_approval(principal, name, args, line_id)
                self._audit(principal, name, raw_args, "pending_approval", result["approval_id"], t0)
                return {"ok": True, "data": result}
            self.con.execute("BEGIN")
            try:
                data = spec.handler(ctx, args)
                self.con.execute("COMMIT")
            except BaseException:
                self.con.execute("ROLLBACK")
                raise
        except ToolError as e:
            self._audit(principal, name, raw_args, "error", e.code, t0)
            return {"ok": False, "error": e.as_dict()}
        except Exception:  # fallo no previsto: se registra completo, el modelo solo ve un mensaje genérico
            log.exception("fallo interno en la tool %s", name)
            self._audit(principal, name, raw_args, "error", "internal_error", t0)
            return _error("internal_error", f"fallo interno al ejecutar {name}; no se aplicó ningún cambio")
        self._audit(principal, name, raw_args, "ok", None, t0)
        return {"ok": True, "data": data}

    def _request_approval(self, principal: Principal, name: str, args: Any, line_id: str | None) -> dict:
        payload = json.dumps(args.model_dump(), sort_keys=True, ensure_ascii=False)
        # misma operación, mismos argumentos y mismo solicitante con una solicitud aún pendiente: se reutiliza
        dup = one(self.con, """SELECT approval_id FROM approvals WHERE action=? AND args=? AND requested_by=?
                               AND plant_id=? AND status='PENDING'""", (name, payload, principal.user_id, principal.plant_id))
        if dup:
            approval_id, created = dup["approval_id"], False
        else:
            digest = hashlib.sha256(f"{name}|{payload}|{principal.user_id}|{iso(self.now)}".encode()).hexdigest()[:6]
            n = one(self.con, "SELECT COUNT(*) AS n FROM approvals")["n"]
            approval_id, created = f"APR-{n + 1:04d}-{digest}", True
            self.con.execute("INSERT INTO approvals VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                             (approval_id, name, payload, principal.plant_id, line_id, principal.user_id,
                              principal.session_id, iso(self.now), "PENDING", None, None, None))
        spec = REGISTRY[name]
        return {"status": "pending_approval", "executed": False, "approval_id": approval_id, "new_request": created,
                "action": name, "args": args.model_dump(), "approver_roles": sorted(spec.approvers),
                "message": "Operación de riesgo: NO se ha ejecutado. Queda pendiente de una aprobación humana "
                           "explícita, que se hace fuera de esta conversación."}

    # ------------------------------------------------------------------ decisión humana (nunca la llama el agente)
    def decide(self, approver: Principal, approval_id: str, approve: bool, comment: str = "") -> dict:
        with self._lock:
            return self._decide(approver, approval_id, approve, comment)

    def _decide(self, approver: Principal, approval_id: str, approve: bool, comment: str) -> dict:
        t0 = time.perf_counter()
        ap = one(self.con, "SELECT * FROM approvals WHERE approval_id=? AND plant_id=?", (approval_id, approver.plant_id))
        if not ap:
            return _error("not_found", f"no existe la solicitud {approval_id} en tu planta")
        spec = REGISTRY[ap["action"]]
        args = spec.args.model_validate(json.loads(ap["args"]))
        audit_args = {"approval_id": approval_id, "approve": approve, "comment": comment}
        if ap["status"] != "PENDING":  # decidir dos veces no vuelve a ejecutar nada
            return {"ok": True, "data": {"approval_id": approval_id, "status": ap["status"], "already_decided": True,
                                         "decided_by": ap["decided_by"],
                                         "result": json.loads(ap["result"]) if ap["result"] else None}}
        if approver.role not in spec.approvers:
            self._audit(approver, f"approval:{ap['action']}", audit_args, "denied", "permission_denied", t0, "human")
            return _error("permission_denied", f"el rol '{approver.role}' no puede aprobar {ap['action']}",
                          approver_roles=sorted(spec.approvers))
        if ap["line_id"] and ap["line_id"] not in approver.lines:
            self._audit(approver, f"approval:{ap['action']}", audit_args, "denied", "out_of_scope", t0, "human")
            return _error("out_of_scope", f"no tienes acceso a la línea {ap['line_id']}")
        if approve and ap["requested_by"] == approver.user_id and not (spec.self_approval and spec.self_approval(approver, args)):
            self._audit(approver, f"approval:{ap['action']}", audit_args, "denied", "separation_of_duties", t0, "human")
            return _error("separation_of_duties", "quien solicita una operación de riesgo no puede aprobarla")
        if not approve:
            self.con.execute("UPDATE approvals SET status='REJECTED', decided_by=?, decided_at=?, result=? WHERE approval_id=?",
                             (approver.user_id, iso(self.now), json.dumps({"comment": comment}, ensure_ascii=False), approval_id))
            self._audit(approver, f"approval:{ap['action']}", audit_args, "ok", "rejected", t0, "human")
            return {"ok": True, "data": {"approval_id": approval_id, "status": "REJECTED", "executed": False}}
        ctx = self.context(replace(approver, session_id=ap["session_id"] or approver.session_id), ap["requested_by"])
        self.con.execute("BEGIN")
        try:
            data = spec.handler(ctx, args)  # las precondiciones se vuelven a comprobar en el momento de ejecutar
            status, result = "EXECUTED", data
        except ToolError as e:
            self.con.execute("ROLLBACK")
            self.con.execute("BEGIN")
            status, result = "FAILED", e.as_dict()
        except BaseException:
            self.con.execute("ROLLBACK")
            raise
        self.con.execute("UPDATE approvals SET status=?, decided_by=?, decided_at=?, result=? WHERE approval_id=?",
                         (status, approver.user_id, iso(self.now), json.dumps(result, ensure_ascii=False), approval_id))
        self.con.execute("COMMIT")
        self._audit(approver, f"approval:{ap['action']}", audit_args, "ok" if status == "EXECUTED" else "error",
                    status.lower(), t0, "human")
        return {"ok": status == "EXECUTED", "data": {"approval_id": approval_id, "status": status,
                                                     "executed": status == "EXECUTED", "result": result}}

    def pending_approvals(self, principal: Principal) -> list[dict]:
        found = rows(self.con, "SELECT * FROM approvals WHERE plant_id=? AND status='PENDING' ORDER BY created_at",
                     (principal.plant_id,))
        out = []
        for ap in found:
            if ap["line_id"] and ap["line_id"] not in principal.lines:
                continue
            spec = REGISTRY[ap["action"]]
            out.append({"approval_id": ap["approval_id"], "action": ap["action"], "args": json.loads(ap["args"]),
                        "line_id": ap["line_id"], "requested_by": ap["requested_by"], "created_at": ap["created_at"],
                        "can_approve": principal.role in spec.approvers})
        return out
