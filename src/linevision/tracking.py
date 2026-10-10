"""Trazabilidad de experimentos con MLflow (parámetros, métricas, versión de datos y artefactos)."""

from __future__ import annotations

import json
import math
import os
import subprocess
from contextlib import contextmanager

import mlflow

from .config import ROOT

EXPERIMENT = "reto2-coil100"
DEFAULT_TAGS: dict = {}  # p. ej. {"iteracion": "v2"}; se añaden a todas las corridas


def setup(experiment: str = EXPERIMENT) -> str:
    uri = os.environ.get("MLFLOW_TRACKING_URI", f"sqlite:///{ROOT / 'mlflow.db'}")
    mlflow.set_tracking_uri(uri)
    if mlflow.get_experiment_by_name(experiment) is None:
        # artefactos siempre en la raíz del repo, independientemente del directorio de trabajo
        mlflow.create_experiment(experiment, artifact_location=(ROOT / "mlruns").as_uri())
    mlflow.set_experiment(experiment)
    return uri


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                       stderr=subprocess.DEVNULL, text=True).strip()
    except (subprocess.CalledProcessError, OSError):
        return "sin-commit"


def flatten(d: dict, prefix: str = "") -> dict:
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(flatten(v, f"{key}."))
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out[key] = float(v)
    return out


@contextmanager
def run(name: str, data_version: str, tags: dict | None = None, params: dict | None = None):
    with mlflow.start_run(run_name=name) as r:
        mlflow.set_tags({"data_version": data_version, "git_commit": git_commit(), **DEFAULT_TAGS, **(tags or {})})
        if params:
            mlflow.log_params({k: str(v)[:500] for k, v in params.items()})
        yield r


def log_metrics(metrics: dict, prefix: str = "") -> None:
    flat = {k.replace("%", "pct"): v for k, v in flatten(metrics, prefix).items() if not math.isnan(v)}
    if flat:
        mlflow.log_metrics(flat)


def log_json(obj, name: str) -> None:
    mlflow.log_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), name)
