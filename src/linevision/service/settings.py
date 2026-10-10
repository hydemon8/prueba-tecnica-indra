"""Configuración del servicio por variables de entorno (ver .env.example). Sin secretos en el código."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ..config import ROOT, data_dir

DEFAULT_ARTIFACT = "artifacts/linevision-4e39f878-rf.joblib"


def _flag(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _path(value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else ROOT / p


@dataclass(frozen=True)
class ServiceSettings:
    artifact_path: Path  # el manifiesto se busca junto al artefacto (*.manifest.json)
    reference_dir: Path  # vistas de referencia (COIL_DIR); opcional, solo para servir evidencia
    host: str = "127.0.0.1"
    port: int = 8001
    api_key: str | None = None  # si se define, se exige en la cabecera X-API-Key
    max_image_bytes: int = 5_000_000
    max_batch: int = 16
    fault_injection: bool = False  # habilita /admin/fault (solo demo y pruebas de robustez)
    alert_window: int = 100  # alerta de captura: capturas recientes observadas por línea
    alert_min_samples: int = 30
    alert_unknown_rate: float = 0.10  # tasa de UNKNOWN que activa la alerta

    @classmethod
    def from_env(cls) -> ServiceSettings:
        return cls(
            artifact_path=_path(os.environ.get("VISION_MODEL_PATH", DEFAULT_ARTIFACT)),
            reference_dir=data_dir() if data_dir().is_absolute() else ROOT / data_dir(),
            host=os.environ.get("VISION_HOST", "127.0.0.1"),
            port=int(os.environ.get("VISION_PORT", "8001")),
            api_key=os.environ.get("VISION_API_KEY") or None,
            max_image_bytes=int(os.environ.get("VISION_MAX_IMAGE_BYTES", "5000000")),
            max_batch=int(os.environ.get("VISION_MAX_BATCH", "16")),
            fault_injection=_flag("VISION_FAULT_INJECTION"),
            alert_window=int(os.environ.get("VISION_ALERT_WINDOW", "100")),
            alert_min_samples=int(os.environ.get("VISION_ALERT_MIN_SAMPLES", "30")),
            alert_unknown_rate=float(os.environ.get("VISION_ALERT_UNKNOWN_RATE", "0.10")),
        )

    @property
    def manifest_path(self) -> Path:
        return self.artifact_path.with_suffix(".manifest.json")
