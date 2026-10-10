"""Tipos base del catálogo de tools: identidad de quien llama, contexto, errores y especificación.

Una tool es una función pura sobre (contexto, argumentos validados). No decide permisos ni aprobaciones:
eso lo hace la capa de política (`lineops.policy`), que es la única vía de ejecución.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

Role = Literal["operator", "supervisor", "quality", "maintenance", "ml_engineer", "plant_manager"]
ALL_ROLES: frozenset[str] = frozenset(Role.__args__)
STAFF: frozenset[str] = ALL_ROLES - {"operator"}


class Args(BaseModel):
    """Base de los contratos de entrada: campos desconocidos se rechazan."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


@dataclass(frozen=True)
class Principal:
    """Quién llama. Sale de la sesión autenticada, nunca de lo que diga el LLM."""

    user_id: str
    name: str
    role: str
    plant_id: str
    lines: tuple[str, ...]
    session_id: str


@dataclass
class ToolContext:
    con: sqlite3.Connection
    principal: Principal
    now: datetime
    vision: Any  # lineops.vision_client.VisionClient
    kb: Any  # lineops.knowledge.KnowledgeBase
    images: Any  # lineops.images.ImageStore
    settings: Any
    requested_by: str | None = None  # en una operación aprobada: quién la solicitó (principal = quien aprueba)


class ToolError(Exception):
    """Error esperado de una tool: llega al modelo como dato estructurado, sin trazas."""

    def __init__(self, code: str, message: str, retryable: bool = False, **extra):
        super().__init__(message)
        self.code, self.message, self.retryable, self.extra = code, message, retryable, extra

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "retryable": self.retryable, **self.extra}


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args: type[Args]
    handler: Callable[[ToolContext, Any], dict]
    kind: Literal["read", "write"]
    roles: frozenset[str] = STAFF
    risk: Literal["low", "high"] = "low"  # high: nunca se ejecuta sin aprobación humana
    approvers: frozenset[str] = frozenset()  # roles que pueden aprobar (solo risk=high)
    self_approval: Callable[[Principal, Any], bool] | None = None  # excepción a la separación de funciones
    precheck: Callable[[ToolContext, Any], None] | None = None  # valida la solicitud antes de crearla
    idempotency: str = "n/a"  # cómo se comporta ante repeticiones (documentación del catálogo)
    side_effects: str = "ninguno"
    failure_modes: tuple[str, ...] = ()
    model_sees: str = ""  # qué recibe el modelo y qué queda fuera de su contexto
    use_cases: tuple[str, ...] = field(default_factory=tuple)

    def json_schema(self) -> dict:
        return self.args.model_json_schema()


REGISTRY: dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> ToolSpec:
    if spec.name in REGISTRY:
        raise ValueError(f"tool duplicada: {spec.name}")
    if spec.risk == "high" and not spec.approvers:
        raise ValueError(f"{spec.name}: una tool de riesgo necesita roles aprobadores")
    REGISTRY[spec.name] = spec
    return spec


def line_of(args: Any) -> str | None:
    return getattr(args, "line_id", None)
