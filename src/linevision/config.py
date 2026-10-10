"""Rutas y carga de configuración. La configuración vive en configs/*.yaml, separada del código."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("LINEVISION_ROOT", Path(__file__).resolve().parents[2]))


def data_dir() -> Path:
    return Path(os.environ.get("COIL_DIR", ROOT / "coil-100"))


def cache_dir() -> Path:
    path = ROOT / ".cache"
    path.mkdir(exist_ok=True)
    return path


def load_config(name: str) -> dict:
    with open(ROOT / "configs" / f"{name}.yaml") as f:
        return yaml.safe_load(f)
