"""API e interfaz web del asistente. La interfaz no es el foco: una página, sin dependencias de front.

Autenticación de la demo: se elige un usuario sembrado y se recibe un token de sesión. En producción este
punto se sustituye por el proveedor de identidad corporativo (Microsoft Entra ID); el resto del sistema solo
ve un `Principal` con rol, planta y líneas, así que no cambia.

Las aprobaciones se deciden aquí, por un endpoint que usa una persona. No existe como tool: el agente no
tiene forma de aprobar nada.
"""

from __future__ import annotations

import logging
import secrets
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from .demo import simulate_captures
from .plant.db import one, rows
from .policy import principal_for
from .runtime import Runtime, build
from .tools import REGISTRY, Principal, ToolError
from .tools.read import capture_alert

log = logging.getLogger("lineops.api")
STATIC = Path(__file__).parent / "static"
MAX_MESSAGE_CHARS = 4000


class LoginBody(BaseModel):
    user_id: str
    access_code: str = ""


class DecisionBody(BaseModel):
    approve: bool
    comment: str = Field("", max_length=300)


class DemoCapturesBody(BaseModel):
    line_id: str = Field(pattern=r"^L\d{1,2}$")
    scenario: Literal["lamp_fault", "normal"]


def create_app(runtime: Runtime | None = None, access_code: str | None = None, demo_controls: bool = False) -> FastAPI:
    rt = runtime or build()
    app = FastAPI(title="lineops — asistente de operación de visión", version="1.0.0")
    tokens: dict[str, str] = {}  # token -> user_id (en memoria: la demo es de un solo proceso)

    def user_of(authorization: str | None = Header(None)) -> str:
        token = (authorization or "").removeprefix("Bearer ").strip()
        if token not in tokens:
            raise HTTPException(401, "sesión no iniciada o caducada")
        return tokens[token]

    def principal(session_id: str, user_id: str) -> Principal:
        p = principal_for(rt.con, user_id, session_id)
        try:
            rt.sessions.check(p)
        except ToolError as e:
            raise HTTPException(404, e.message) from None
        return p

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index():
        return (STATIC / "index.html").read_text(encoding="utf-8")

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "model": rt.agent.llm.model}

    @app.get("/api/users")
    def users():
        """Usuarios de la demo (identidades sembradas; no hay datos personales reales)."""
        return {"access_code_required": bool(access_code),
                "users": rows(rt.con, "SELECT user_id, name, role, plant_id, lines FROM users ORDER BY plant_id, role")}

    @app.post("/api/login")
    def login(body: LoginBody):
        if access_code and not secrets.compare_digest(body.access_code, access_code):
            raise HTTPException(401, "código de acceso incorrecto")
        u = one(rt.con, "SELECT user_id, name, role, plant_id, lines FROM users WHERE user_id=?", (body.user_id,))
        if not u:
            raise HTTPException(404, "usuario desconocido")
        token = secrets.token_urlsafe(24)
        tokens[token] = u["user_id"]
        session_id = rt.sessions.create(u["user_id"], u["plant_id"], rt.now)
        return {"token": token, "session_id": session_id, "user": u, "plant_time": rt.now.isoformat(timespec="minutes"),
                "tools": rt.executor.allowed_tools(principal_for(rt.con, u["user_id"], session_id))}

    @app.post("/api/sessions")
    def new_session(user_id: str = Depends(user_of)):
        u = one(rt.con, "SELECT plant_id FROM users WHERE user_id=?", (user_id,))
        return {"session_id": rt.sessions.create(user_id, u["plant_id"], rt.now)}

    @app.post("/api/chat")
    def chat(session_id: str = Form(...), message: str = Form(..., max_length=MAX_MESSAGE_CHARS),
             files: list[UploadFile] = File(default=[]), user_id: str = Depends(user_of)):  # noqa: B008
        p = principal(session_id, user_id)
        attachments = None
        if files:
            try:
                attachments = rt.images.save_batch(p, [(f.filename or "imagen", f.file.read(6_000_000)) for f in files], rt.now)
            except ToolError as e:
                raise HTTPException(422, e.message) from None
        result = rt.agent.run_turn(p, message.strip(), attachments)
        return {**result.as_dict(), "attachments": attachments}

    @app.get("/api/sessions/{session_id}/messages")
    def messages(session_id: str, user_id: str = Depends(user_of)):
        return {"messages": rt.sessions.transcript(principal(session_id, user_id))}

    @app.get("/api/images/{image_id}")
    def image(image_id: str, session_id: str, user_id: str = Depends(user_of)):
        try:
            meta, _ = rt.images.load(principal(session_id, user_id), image_id, rt.now)
        except ToolError as e:
            raise HTTPException(404, e.message) from None
        return FileResponse(meta["path"], media_type="image/png")

    @app.get("/api/reference/{object_id}/{angle_deg}")
    def reference(object_id: int, angle_deg: int):
        """Vista de referencia del catálogo, servida a través del asistente (el navegador no ve el servicio de visión)."""
        data = rt.executor.vision.reference_png(object_id, angle_deg)
        if data is None:
            raise HTTPException(404, "vista de referencia no disponible")
        return Response(data, media_type="image/png", headers={"Cache-Control": "max-age=3600"})

    @app.get("/api/lines")
    def lines(user_id: str = Depends(user_of)):
        """Estado de las líneas del usuario y su alerta de captura, para la interfaz."""
        p = principal_for(rt.con, user_id, "lines")
        out = []
        for line_id in p.lines:
            line = one(rt.con, "SELECT line_id, status, class_conf_min, model_version FROM lines WHERE plant_id=? AND line_id=?",
                       (p.plant_id, line_id))
            if line:
                out.append({**line, "capture_alert": capture_alert(rt.executor.vision, p.plant_id, line_id)})
        return {"lines": out, "demo_controls": demo_controls}

    @app.post("/api/demo/captures")
    def demo_captures(body: DemoCapturesBody, user_id: str = Depends(user_of)):
        """Hace de controlador de línea para la demostración: envía capturas simuladas al servicio de visión."""
        if not demo_controls:
            raise HTTPException(404, "los controles de demostración están desactivados")
        p = principal_for(rt.con, user_id, "demo")
        if body.line_id not in p.lines:
            raise HTTPException(403, f"no tienes acceso a la línea {body.line_id}")
        try:
            return simulate_captures(rt.executor.vision, p.plant_id, body.line_id, body.scenario)
        except ToolError as e:
            raise HTTPException(503, e.message) from None

    @app.get("/api/approvals")
    def approvals(user_id: str = Depends(user_of)):
        p = principal_for(rt.con, user_id, "approvals")
        return {"pending": rt.executor.pending_approvals(p),
                "recent": rows(rt.con, """SELECT approval_id, action, status, requested_by, decided_by, decided_at FROM approvals
                                          WHERE plant_id=? AND status!='PENDING' ORDER BY decided_at DESC LIMIT 5""", (p.plant_id,))}

    @app.post("/api/approvals/{approval_id}/decision")
    def decide(approval_id: str, body: DecisionBody, user_id: str = Depends(user_of)):
        """Decisión humana explícita sobre una operación de riesgo. No es una tool: el agente no puede llamarla."""
        return rt.executor.decide(principal_for(rt.con, user_id, "approvals"), approval_id, body.approve, body.comment)

    @app.get("/api/audit")
    def audit(limit: int = 30, user_id: str = Depends(user_of)):
        p = principal_for(rt.con, user_id, "audit")
        if p.role not in {"plant_manager", "quality", "ml_engineer", "supervisor"}:
            raise HTTPException(403, "tu rol no puede consultar la auditoría")
        return {"entries": rows(rt.con, """SELECT ts, user_id, role, tool, outcome, detail, source, latency_ms FROM audit_log
                                           WHERE plant_id=? ORDER BY id DESC LIMIT ?""", (p.plant_id, min(limit, 200)))}

    @app.get("/api/tools")
    def tools():
        """Catálogo de tools generado desde el código (entregable 7)."""
        return {"tools": [{"name": s.name, "kind": s.kind, "risk": s.risk, "description": s.description,
                           "roles": sorted(s.roles), "approvers": sorted(s.approvers), "input_schema": s.json_schema()}
                          for s in REGISTRY.values()]}

    return app
