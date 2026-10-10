"""Contratos de la API del servicio de visión (generan el OpenAPI en /docs y /openapi.json)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Decision = Literal["ACT", "ANGLE_UNCERTIFIED", "REVIEW", "UNKNOWN", "BAD_CAPTURE"]
RobotAction = Literal["PICK", "SECOND_CAPTURE", "DIVERT_TO_REVIEW", "DIVERT_TO_REJECT", "RECAPTURE"]


class Quality(BaseModel):
    ok: bool
    issues: list[str]
    width: int
    height: int
    resized: bool
    foreground_fraction: float
    mean_brightness: float


class RobotCommand(BaseModel):
    action: RobotAction
    object_id: int | None = Field(None, description="Solo con PICK")
    angle_deg: float | None = Field(None, description="Giro a compensar, solo con PICK")


class PoseNeighbour(BaseModel):
    object_id: int
    angle_deg: float
    delta_deg: float = Field(description="Distancia angular al ángulo estimado")


class AppearanceNeighbour(BaseModel):
    object_id: int
    angle_deg: float
    distance: float = Field(description="Distancia en el espacio de características de identidad")


class Inspection(BaseModel):
    filename: str | None
    image_sha256: str
    decision: Decision
    reasons: list[str]
    robot_command: RobotCommand
    quality: Quality
    object_id: int | None = None
    class_confidence: float | None = None
    novelty: float | None = Field(None, description="Distancia a la vista de referencia más cercana")
    angle_deg: float | None = Field(None, ge=0, lt=360)
    angle_credible_width_deg: float | None = Field(None, description="Ancho del conjunto creíble del 90 %")
    topk_pose: list[PoseNeighbour] = []
    topk_appearance: list[AppearanceNeighbour] = []


class PredictResponse(BaseModel):
    request_id: str
    model_version: str
    latency_ms: float
    results: list[Inspection]


class ModelInfo(BaseModel):
    name: str
    version: str
    data_version: str
    artifact_sha256: str
    created_utc: str
    n_objects: int
    identity: str
    policy: dict
    tolerance_deg: float
    metrics: dict


class CatalogEntry(BaseModel):
    object_id: int
    n_reference_views: int
    max_gallery_gap_deg: float
    angle_certified: bool = Field(description="Hueco máximo de galería dentro de la política de catálogo")
    symmetry_order: int = Field(description="1 = sin simetría; 2 = theta equivale a theta+180")


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None = None


class FaultRequest(BaseModel):
    mode: Literal["none", "error", "timeout"] = "none"
    count: int = Field(1, ge=1, le=100, description="Número de peticiones de inferencia afectadas")
    delay_s: float = Field(10.0, ge=0, le=120, description="Retardo en modo timeout")
