"""Métricas: error angular circular (y consciente de simetría), identidad, rechazo y decisión selectiva."""

from __future__ import annotations

import numpy as np
from sklearn.metrics import roc_auc_score


def circular_error(pred, true) -> np.ndarray:
    """Distancia angular mínima en grados, en [0, 180]."""
    e = np.abs(np.asarray(pred, float) - np.asarray(true, float)) % 360
    return np.minimum(e, 360 - e)


def symmetric_error(pred, true, order) -> np.ndarray:
    """Error módulo la simetría rotacional del objeto: order=1 sin simetría, 2 si theta ~ theta+180,
    0 si es invariante al giro (rosca): el ángulo no es observable ni relevante para el agarre."""
    pred, true = np.asarray(pred, float), np.asarray(true, float)
    order = np.broadcast_to(np.asarray(order), pred.shape)
    err = circular_error(pred, true)
    err = np.where(order == 2, np.minimum(err, circular_error(pred + 180, true)), err)
    return np.where(order == 0, 0.0, err)


def angle_report(err: np.ndarray, tol: float = 10.0) -> dict:
    err = np.asarray(err, float)
    if err.size == 0:
        return {"n": 0}
    return {
        "n": int(err.size),
        "within_tol": float(np.mean(err <= tol)),
        "mae": float(err.mean()),
        "median": float(np.median(err)),
        "p90": float(np.percentile(err, 90)),
        "gt90": float(np.mean(err > 90)),
    }


def openset_report(score_known: np.ndarray, score_unknown: np.ndarray, known_recall: float = 0.95) -> dict:
    """score más alto = más 'desconocido'. Reporta AUROC y desconocidos aceptados al umbral que acepta
    `known_recall` de los conocidos."""
    y = np.r_[np.zeros(len(score_known)), np.ones(len(score_unknown))]
    thr = np.quantile(score_known, known_recall)
    return {
        "auroc": float(roc_auc_score(y, np.r_[score_known, score_unknown])),
        "unknown_accepted": float(np.mean(score_unknown <= thr)),
        "known_recall": known_recall,
    }


def decision_report(decision: np.ndarray, class_ok: np.ndarray, angle_err: np.ndarray, tol: float) -> dict:
    """Seguridad de la decisión final. Una acción es insegura si el robot actúa (ACT) con la clase
    equivocada o con el ángulo fuera de tolerancia."""
    decision = np.asarray(decision)
    act = decision == "ACT"
    angle_ok = np.asarray(angle_err) <= tol
    unsafe = act & ~(np.asarray(class_ok) & angle_ok)
    out = {f"rate_{d}": float(np.mean(decision == d)) for d in ("ACT", "ANGLE_UNCERTIFIED", "REVIEW", "UNKNOWN")}
    out["unsafe_rate"] = float(unsafe.mean())
    out["precision_on_act"] = float(1 - unsafe[act].mean()) if act.any() else float("nan")
    return out
