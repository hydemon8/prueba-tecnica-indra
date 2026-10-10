"""API HTTP del servicio de visión: imagen -> identidad, ángulo, evidencia, decisión y orden para el robot.

Es determinista y no depende del asistente agéntico: la ruta crítica imagen -> robot pasa solo por aquí.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import threading
import time
import uuid
from contextlib import asynccontextmanager

import numpy as np
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from ..system import VisionSystem
from . import quality
from .monitor import CaptureMonitor, MonitorConfig
from .robot import BAD_CAPTURE, robot_command
from .schemas import CatalogEntry, ErrorBody, FaultRequest, Inspection, LineAlert, ModelInfo, PredictResponse
from .settings import ServiceSettings

log = logging.getLogger("linevision.service")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_LINE_ID = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


class ApiError(HTTPException):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(status, {"code": code, "message": message})


class FaultState:
    """Fallos inyectados para la demo de robustez (5xx y timeout). Solo activo con VISION_FAULT_INJECTION."""

    def __init__(self):
        self._lock = threading.Lock()
        self.mode, self.count, self.delay_s = "none", 0, 0.0

    def set(self, req: FaultRequest) -> dict:
        with self._lock:
            self.mode = req.mode
            self.count = 0 if req.mode == "none" else req.count
            self.delay_s = req.delay_s
            return self.snapshot()

    def snapshot(self) -> dict:
        return {"mode": self.mode, "remaining": self.count, "delay_s": self.delay_s}

    def take(self) -> tuple[str, float]:
        with self._lock:
            if self.mode == "none" or self.count <= 0:
                return "none", 0.0
            self.count -= 1
            mode, delay = self.mode, self.delay_s
            if self.count == 0:
                self.mode = "none"
            return mode, delay


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_system(settings: ServiceSettings) -> tuple[VisionSystem, dict]:
    """Carga el artefacto solo si su sha256 coincide con el manifiesto versionado."""
    manifest = json.loads(settings.manifest_path.read_text(encoding="utf-8"))
    actual = sha256(settings.artifact_path)
    if actual != manifest["artifact_sha256"]:
        raise RuntimeError(f"el artefacto {settings.artifact_path.name} no coincide con su manifiesto")
    system = VisionSystem.load(settings.artifact_path)
    # una imagen por petición: los hilos del clasificador solo añaden latencia
    clf = system.identity.pipe.steps[-1][1]
    if hasattr(clf, "n_jobs"):
        clf.n_jobs = 1
    return system, manifest


def _finite(x):
    return None if x is None or not math.isfinite(x) else float(x)


def create_app(settings: ServiceSettings | None = None, system: VisionSystem | None = None,
               manifest: dict | None = None) -> FastAPI:
    settings = settings or ServiceSettings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if system is None:
            app.state.system, app.state.manifest = load_system(settings)
        else:
            app.state.system, app.state.manifest = system, manifest or {}
        log.info(json.dumps({"event": "model_loaded", "model_version": app.state.system.version}))
        yield

    app = FastAPI(title="linevision — servicio de visión", version="1.0.0", lifespan=lifespan,
                  description="Identificación de producto, giro (yaw) y decisión segura para pick & pack.")
    faults = FaultState()
    monitor = CaptureMonitor(MonitorConfig(settings.alert_window, settings.alert_min_samples, settings.alert_unknown_rate,
                                           settings.alert_unknown_rate * 0.3))

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {"code": "http_error", "message": str(exc.detail)}
        body = ErrorBody(**detail, request_id=getattr(request.state, "request_id", None))
        return JSONResponse(body.model_dump(), status_code=exc.status_code, headers=exc.headers)

    def request_id(request: Request, response: Response, x_request_id: str | None = Header(None)) -> str:
        rid = x_request_id if x_request_id and _REQUEST_ID.match(x_request_id) else uuid.uuid4().hex
        request.state.request_id = rid
        response.headers["X-Request-ID"] = rid
        return rid

    def authorize(x_api_key: str | None = Header(None)) -> None:
        if settings.api_key and x_api_key != settings.api_key:
            raise ApiError(401, "unauthorized", "falta la cabecera X-API-Key o no es válida")

    secured = [Depends(request_id), Depends(authorize)]
    errors = {code: {"model": ErrorBody} for code in (401, 413, 422, 503)}

    @app.get("/healthz", tags=["operación"])
    def healthz():
        return {"status": "ok"}

    @app.get("/readyz", tags=["operación"])
    def readyz(request: Request):
        ready = getattr(request.app.state, "system", None) is not None
        return JSONResponse({"status": "ready" if ready else "loading",
                             "model_version": request.app.state.system.version if ready else None},
                            status_code=200 if ready else 503)

    @app.get("/v1/model", response_model=ModelInfo, dependencies=secured, tags=["modelo"])
    def model_info(request: Request):
        s, m = request.app.state.system, request.app.state.manifest
        policy = {k: _finite(v) if isinstance(v, float) else v for k, v in vars(s.cfg.policy).items()}
        return ModelInfo(
            name=m.get("name", "linevision"), version=s.version, data_version=m.get("data_version", ""),
            artifact_sha256=m.get("artifact_sha256", ""), created_utc=m.get("created_utc", ""),
            n_objects=len(s.pose.curves), identity=s.cfg.identity.name, policy=policy,
            tolerance_deg=s.cfg.policy.angle_width_max / 2, metrics=m.get("metrics", {}),
        )

    @app.get("/v1/catalog", response_model=list[CatalogEntry], dependencies=secured, tags=["modelo"])
    def catalog(request: Request):
        s = request.app.state.system
        order = s.pose.symmetry_order()
        return [
            CatalogEntry(object_id=int(o), n_reference_views=len(s.pose.gallery_angles[o]),
                         max_gallery_gap_deg=s.pose.max_gap[o],
                         angle_certified=s.pose.max_gap[o] <= s.cfg.policy.max_gallery_gap,
                         symmetry_order=order[o])
            for o in sorted(s.pose.curves)
        ]

    @app.get("/v1/reference/{object_id}/{angle_deg}", dependencies=secured, tags=["modelo"],
             responses={404: {"model": ErrorBody}})
    def reference_view(request: Request, object_id: int, angle_deg: int):
        """Vista de referencia (PNG) de un SKU del catálogo: la evidencia que acompaña a una decisión."""
        angles = request.app.state.system.pose.gallery_angles.get(object_id)
        if angles is None or angle_deg not in angles:
            raise ApiError(404, "reference_not_found", f"no hay vista de referencia obj{object_id} a {angle_deg} grados")
        path = settings.reference_dir / f"obj{object_id}__{angle_deg}.png"
        if not path.is_file():
            raise ApiError(404, "reference_unavailable", "las vistas de referencia no están desplegadas en este servicio")
        return FileResponse(path, media_type="image/png")

    @app.post("/v1/predict", response_model=PredictResponse, dependencies=[Depends(authorize)],
              responses=errors, tags=["inferencia"])
    def predict(request: Request, rid: str = Depends(request_id),
                images: list[UploadFile] = File(..., description="Una o varias imágenes PNG/JPEG"),  # noqa: B008
                top_k: int = Query(5, ge=1, le=20, description="Vistas similares a devolver"),
                x_line_id: str | None = Header(None, description="Línea de producción que envía la captura. Activa la "
                                               "alerta de captura para esa línea; las inspecciones manuales no la envían")):
        if x_line_id is not None and not _LINE_ID.match(x_line_id):
            raise ApiError(422, "invalid_line_id", "X-Line-ID admite letras, números, guion y guion bajo (máximo 32)")
        if len(images) > settings.max_batch:
            raise ApiError(413, "batch_too_large", f"máximo {settings.max_batch} imágenes por petición")
        mode, delay = faults.take() if settings.fault_injection else ("none", 0.0)
        if mode == "error":
            raise ApiError(503, "service_unavailable", "fallo inyectado: servicio de visión no disponible")
        if mode == "timeout":
            time.sleep(delay)

        s: VisionSystem = request.app.state.system
        t0 = time.perf_counter()
        entries, arrays = [], []
        for up in images:
            raw = up.file.read(settings.max_image_bytes + 1)
            if len(raw) > settings.max_image_bytes:
                raise ApiError(413, "image_too_large", f"{up.filename}: supera {settings.max_image_bytes} bytes")
            entry = {"filename": up.filename, "image_sha256": hashlib.sha256(raw).hexdigest()}
            try:
                arr, q = quality.check(quality.decode(raw), s.cfg.features.fg_threshold)
            except quality.ImageDecodeError as e:
                arr, q = None, {"ok": False, "issues": [str(e)], "width": 0, "height": 0, "resized": False,
                                "foreground_fraction": 0.0, "mean_brightness": 0.0}
            entry["quality"] = q
            if q["ok"]:
                entry["slot"] = len(arrays)
                arrays.append(arr)
            entries.append(entry)

        preds = s.predict_images(np.stack(arrays), top_k) if arrays else []
        results = []
        for e in entries:
            if "slot" in e:
                p = preds[e.pop("slot")]
                p.pop("model_version")
                for key in ("class_confidence", "novelty", "angle_deg", "angle_credible_width_deg"):
                    p[key] = _finite(p[key])
                item = {**e, **p}
            else:
                item = {**e, "decision": BAD_CAPTURE, "reasons": e["quality"]["issues"]}
            hold = False
            if x_line_id and item["decision"] != BAD_CAPTURE:  # la alerta se evalúa captura a captura, en orden
                alert, change = monitor.observe(x_line_id, item["decision"], e["quality"]["mean_brightness"])
                hold = alert["active"]
                if change:
                    log.warning(json.dumps({"event": f"capture_alert_{change}", "request_id": rid, **alert}, ensure_ascii=False))
                if hold and item["decision"] == "UNKNOWN":
                    why = (f"alerta de captura activa en {x_line_id}: {alert['unknown_rate']:.0%} de desconocidos en las "
                           f"últimas {alert['window_samples']} capturas; se retiene para revisión en lugar de rechazarse")
                    item["reasons"] = [*item["reasons"], why]
            item["robot_command"] = robot_command(item["decision"], item.get("object_id"), item.get("angle_deg"), hold)
            results.append(Inspection(**item))
        latency_ms = (time.perf_counter() - t0) * 1000

        for r in results:  # auditoría: una línea por imagen, sin el contenido de la imagen
            log.info(json.dumps({
                "event": "inference", "request_id": rid, "image_sha256": r.image_sha256,
                "model_version": s.version, "decision": r.decision, "robot_action": r.robot_command.action,
                "object_id": r.object_id, "angle_deg": r.angle_deg, "latency_ms": round(latency_ms, 2),
            }, ensure_ascii=False))
        return PredictResponse(request_id=rid, model_version=s.version, latency_ms=round(latency_ms, 2),
                               results=results, line_alert=monitor.snapshot(x_line_id) if x_line_id else None)

    @app.get("/v1/lines/{line_id}/monitor", response_model=LineAlert, dependencies=secured, tags=["operación"])
    def line_monitor(line_id: str):
        """Estado de la alerta de captura de una línea: tasa reciente de desconocidos, cambio de brillo y causa probable."""
        if not _LINE_ID.match(line_id):
            raise ApiError(422, "invalid_line_id", "identificador de línea no válido")
        return monitor.snapshot(line_id)

    if settings.fault_injection:
        @app.get("/admin/fault", dependencies=secured, tags=["demo de robustez"])
        def get_fault():
            return faults.snapshot()

        @app.post("/admin/fault", dependencies=secured, tags=["demo de robustez"])
        def set_fault(req: FaultRequest):
            log.warning(json.dumps({"event": "fault_injection", **req.model_dump()}))
            return faults.set(req)

    return app
