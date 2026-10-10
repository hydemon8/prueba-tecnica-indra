"""Exportación y versionado del artefacto final: archivo joblib + manifiesto con huellas, y registro en
el Model Registry de MLflow como modelo pyfunc (entrada: imágenes PNG en base64)."""

from __future__ import annotations

import base64
import hashlib
import io
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import mlflow
import numpy as np
from PIL import Image

from . import __version__
from .config import ROOT
from .system import VisionSystem

REGISTERED_NAME = "linevision"


def config_fingerprint(system: VisionSystem) -> str:
    cfg = asdict(system.cfg)
    return hashlib.sha256(json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest()[:8]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def export(system: VisionSystem, out_dir: Path, data_version: str, metrics: dict) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"linevision-{system.version}.joblib"
    system.save(path)
    manifest = {
        "name": REGISTERED_NAME,
        "version": system.version,
        "package_version": __version__,
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "data_version": data_version,
        "config_fingerprint": config_fingerprint(system),
        "artifact": path.name,
        "artifact_sha256": sha256(path),
        "artifact_mb": round(path.stat().st_size / 1e6, 1),
        "config": asdict(system.cfg),
        "temperature_scale": system.pose.temperature_scale,
        "metrics": metrics,
    }
    (out_dir / f"linevision-{system.version}.manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, default=str))
    return manifest


def decode_png_b64(s: str) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(base64.b64decode(s))).convert("RGB").resize((128, 128)))


class LinevisionPyfunc(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        self.system = VisionSystem.load(context.artifacts["system"])

    def predict(self, context, model_input, params=None):
        images = np.stack([decode_png_b64(s) for s in model_input["image_png_b64"]])
        return self.system.predict_images(images)


def register(path: Path, manifest: dict) -> str:
    """Registra el artefacto en el Model Registry de MLflow (dentro de un run activo)."""
    info = mlflow.pyfunc.log_model(
        name=REGISTERED_NAME,
        python_model=LinevisionPyfunc(),
        artifacts={"system": str(path)},
        code_paths=[str(ROOT / "src" / "linevision")],
        pip_requirements=["numpy", "scipy", "scikit-learn", "scikit-image", "pillow", "joblib", "pandas"],
        registered_model_name=REGISTERED_NAME,
        metadata={k: manifest[k] for k in ("version", "data_version", "config_fingerprint", "artifact_sha256")},
    )
    return info.model_uri
