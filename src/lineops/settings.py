"""Configuración del asistente por variables de entorno (ver .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from linevision.config import ROOT


def _path(name: str, default: str) -> Path:
    p = Path(os.environ.get(name, default))
    return p if p.is_absolute() else ROOT / p


@dataclass(frozen=True)
class AgentSettings:
    plant_db: Path
    sops_dir: Path
    uploads_dir: Path
    vision_url: str = "http://127.0.0.1:8001"
    vision_api_key: str | None = None
    vision_timeout_s: float = 4.0
    vision_retries: int = 1
    llm_provider: str = "gemini"
    llm_model: str = "gemini-3.5-flash-lite"
    gemini_api_key: str | None = None
    max_steps: int = 8                # llamadas al LLM por turno
    max_tool_calls: int = 12          # tools ejecutadas por turno
    max_repeated_calls: int = 2       # misma tool con los mismos argumentos
    max_turn_tokens: int = 60_000     # presupuesto de tokens por turno
    history_max_messages: int = 24    # a partir de aquí se resume el historial
    history_keep_chars: int = 600     # lo que se conserva de cada mensaje antiguo al resumir
    image_ttl_hours: int = 72
    # precios por millón de tokens para estimar el costo (supuesto configurable; verificar la tarifa vigente)
    price_in_per_mtok: float = 0.10
    price_out_per_mtok: float = 0.40
    host: str = "127.0.0.1"
    port: int = 8002

    @classmethod
    def from_env(cls) -> AgentSettings:
        e = os.environ
        return cls(
            plant_db=_path("PLANT_DB", "var/plant.db"),
            sops_dir=_path("SOPS_DIR", "knowledge/sops"),
            uploads_dir=_path("UPLOADS_DIR", "var/uploads"),
            vision_url=e.get("VISION_URL", "http://127.0.0.1:8001").rstrip("/"),
            vision_api_key=e.get("VISION_API_KEY") or None,
            vision_timeout_s=float(e.get("VISION_TIMEOUT_S", "4")),
            vision_retries=int(e.get("VISION_RETRIES", "1")),
            llm_provider=e.get("LLM_PROVIDER", "gemini"),
            llm_model=e.get("LLM_MODEL", "gemini-3.5-flash-lite"),
            gemini_api_key=e.get("GEMINI_API_KEY") or None,
            max_steps=int(e.get("AGENT_MAX_STEPS", "8")),
            max_tool_calls=int(e.get("AGENT_MAX_TOOL_CALLS", "12")),
            max_turn_tokens=int(e.get("AGENT_MAX_TURN_TOKENS", "60000")),
            price_in_per_mtok=float(e.get("LLM_PRICE_IN_PER_MTOK", "0.10")),
            price_out_per_mtok=float(e.get("LLM_PRICE_OUT_PER_MTOK", "0.40")),
            host=e.get("AGENT_HOST", "127.0.0.1"),
            port=int(e.get("AGENT_PORT", "8002")),
        )
