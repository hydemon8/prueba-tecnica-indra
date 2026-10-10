"""Selección de modelo en validación interna con criterio pre-registrado (configs/model.yaml).

Identidad: matriz representaciones x clasificadores evaluada en las particiones internas de A, B y C;
restricción de seguridad de novedad en las particiones internas de D; elección del peor caso.
Pose: comparación de métodos (1-NN frente a la curva cerrada) con la clase verdadera.
"""

from __future__ import annotations

import time
from itertools import product

import numpy as np
import pandas as pd

from .features import combine, subset
from .identity import IdentityConfig, IdentityModel, nearest
from .metrics import angle_report, circular_error, openset_report
from .pose import PoseConfig, PoseModel


def aurc(conf: np.ndarray, correct: np.ndarray) -> float:
    """Área bajo la curva riesgo-cobertura: error medio al aceptar primero lo más confiado. Menor es mejor."""
    order = np.argsort(-conf, kind="stable")
    err = ~np.asarray(correct)[order]
    return float((np.cumsum(err) / np.arange(1, len(err) + 1)).mean())


def candidates(cfg: dict) -> list[IdentityConfig]:
    ident = cfg["identity"]
    out = []
    for blocks, (clf, grid) in product(ident["candidates"]["blocks"], ident["candidates"]["classifiers"].items()):
        for params in grid:
            out.append(IdentityConfig(tuple(blocks), clf, dict(params), ident["pca_dim"]))
    return out


def screen_identity(icfg: IdentityConfig, feats, obj, angle, inner: dict) -> dict:
    """Exactitud y AURC por protocolo interno, más tiempos de entrenamiento e inferencia."""
    row = {"candidate": icfg.name, "blocks": "+".join(icfg.blocks), "classifier": icfg.classifier,
           "params": str(icfg.params)}
    fit_s, pred_ms = [], []
    for prot, splits in inner.items():
        correct, conf = [], []
        for sp in splits:
            t0 = time.perf_counter()
            model = IdentityModel(icfg).fit(subset(feats, sp.train), obj[sp.train], angle[sp.train])
            fit_s.append(time.perf_counter() - t0)
            t0 = time.perf_counter()
            label, c = model.predict(subset(feats, sp.test))
            pred_ms.append((time.perf_counter() - t0) / len(sp.test) * 1000)
            correct.append(label == obj[sp.test])
            conf.append(c)
        correct, conf = np.concatenate(correct), np.concatenate(conf)
        row[f"acc_{prot}"] = float(correct.mean())
        row[f"aurc_{prot}"] = aurc(conf, correct)
    row["fit_s"] = float(np.mean(fit_s))
    row["predict_ms"] = float(np.mean(pred_ms))
    return row


def openset_by_blocks(blocks, feats, obj, angle, splits_d) -> dict:
    """Restricción de novedad: depende solo de la representación (distancia a la galería), no del
    clasificador. Se mide en las particiones internas de D (objetos de catálogo que hacen de desconocidos)."""
    known_s, unknown_s = [], []
    for sp in splits_d:
        g = combine(subset(feats, sp.train), blocks)
        q = combine(subset(feats, sp.test), blocks)
        d = nearest(g, q, 1)[0][:, 0]
        unk = np.isin(obj[sp.test], sp.unknown_objects)
        known_s.append(d[~unk])
        unknown_s.append(d[unk])
    return openset_report(np.concatenate(known_s), np.concatenate(unknown_s))


def select(table: pd.DataFrame, max_unknown_accepted: float, tie_pp: float) -> pd.Series:
    """Criterio pre-registrado: (1) cumple la restricción de novedad; (2) máxima exactitud del peor caso
    entre A, B y C; (3) empates dentro de `tie_pp` puntos porcentuales se resuelven por latencia."""
    ok = table[table["unknown_accepted"] <= max_unknown_accepted]
    if ok.empty:
        raise ValueError("ningún candidato cumple la restricción de novedad")
    best = ok["worst_acc"].max()
    tied = ok[ok["worst_acc"] >= best - tie_pp / 100]
    return tied.sort_values("predict_ms").iloc[0]


def compare_pose_methods(feats, obj, angle, inner: dict, cfg: PoseConfig, tol: float) -> pd.DataFrame:
    """1-NN (vista más cercana) frente a la curva cerrada, con la clase verdadera, por protocolo interno."""
    rows = []
    for prot, splits in inner.items():
        err = {"1-NN (vista más cercana)": [], "curva cerrada (spline periódico)": []}
        for sp in splits:
            model = PoseModel(cfg).fit(feats[cfg.block][sp.train], obj[sp.train], angle[sp.train])
            q, y, a = feats[cfg.block][sp.test], obj[sp.test], angle[sp.test]
            err["1-NN (vista más cercana)"].append(circular_error(model.nearest_view(q, y), a))
            err["curva cerrada (spline periódico)"].append(circular_error(model.estimate(q, y).angle, a))
        for method, e in err.items():
            rows.append({"protocolo": prot, "método": method, **angle_report(np.concatenate(e), tol)})
    return pd.DataFrame(rows)
