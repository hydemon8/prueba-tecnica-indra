"""Calibración en validación interna y evaluación por protocolo.

Flujo por protocolo:
  1) para cada partición interna (solo vistas de entrenamiento): entrenar, inferir en validación y
     recoger señales (novedad, confianza, acierto, cobertura del conjunto creíble del ángulo);
  2) fijar umbrales del control de seguridad y la temperatura de la incertidumbre con esas señales;
  3) reentrenar con todo el entrenamiento del protocolo y evaluar UNA vez en su prueba.
"""

from __future__ import annotations

import time
from copy import deepcopy

import numpy as np

from .features import subset
from .gate import calibrate_ambiguity, calibrate_class_conf
from .identity import IdentityConfig, IdentityModel
from .metrics import angle_report, circular_error, decision_report, openset_report, symmetric_error
from .pose import AMBIGUITY_EXCLUSION_DEG, PoseConfig, PoseModel, _closed_curve
from .protocols import Split, covered_splits, inner_splits
from .system import SystemConfig, VisionSystem

TEMPERATURE_SCALES = np.geomspace(1e-3, 50, 48)
GRID = np.arange(0, 360, 5)


def _fit(cfg: SystemConfig, feats, obj, angle, idx, version="dev") -> VisionSystem:
    return VisionSystem(deepcopy(cfg), version).fit(subset(feats, idx), obj[idx], angle[idx])


def calibrate(cfg: SystemConfig, feats, obj, angle, split: Split, gate_cfg: dict, seed: int = 0):
    """Fija umbrales y temperatura con validación interna. Devuelve (cfg calibrada, escala, diagnóstico).

    - Identidad y novedad: particiones internas que imitan el protocolo (inner_splits).
    - Ángulo (temperatura e umbral de ambigüedad): particiones del régimen con cobertura (covered_splits);
      el sector ciego lo gobierna la regla determinista de cobertura del SKU, no la incertidumbre.
    """
    tol = gate_cfg["tolerance_deg"]
    nov_known, nov_unknown, conf, correct = [], [], [], []
    for sp in inner_splits(split, obj, angle, seed):
        system = _fit(cfg, feats, obj, angle, sp.train)
        val = sp.test
        known = ~np.isin(obj[val], sp.unknown_objects)
        r = system.infer(subset(feats, val))
        nov_known.append(r["novelty"][known])
        nov_unknown.append(r["novelty"][~known])
        conf.append(r["class_confidence"][known])
        correct.append(r["label"][known] == obj[val][known])
    nov_known, nov_unknown = np.concatenate(nov_known), np.concatenate(nov_unknown)
    conf, correct = np.concatenate(conf), np.concatenate(correct)

    block = cfg.pose.block
    poses, cover = [], []
    for sp in covered_splits(split, obj, angle):
        pm = PoseModel(cfg.pose).fit(feats[block][sp.train], obj[sp.train], angle[sp.train])
        cover.append(pm.coverage(feats[block][sp.test], obj[sp.test], angle[sp.test], TEMPERATURE_SCALES))
        poses.append((pm, sp.test))
    cover = np.concatenate(cover, axis=1).mean(1)
    ok = np.flatnonzero(cover >= cfg.pose.credible_mass)
    k = ok.min() if ok.size else len(TEMPERATURE_SCALES) - 1
    scale = float(TEMPERATURE_SCALES[k])
    width, amb, err = [], [], []
    for pm, val in poses:
        pm.temperature_scale = scale
        est = pm.estimate(feats[block][val], obj[val])
        width.append(est.credible_width)
        amb.append(est.ambiguity)
        err.append(circular_error(est.angle, angle[val]))
    width, amb, err = map(np.concatenate, (width, amb, err))

    out = deepcopy(cfg)
    out.policy.novelty_max = float(np.quantile(nov_known, gate_cfg["novelty_known_quantile"]))
    out.policy.class_conf_min = calibrate_class_conf(conf, correct, gate_cfg["target_class_error_on_act"])
    out.policy.ambiguity_max = calibrate_ambiguity(width, amb, err, out.policy.angle_width_max, tol,
                                                   gate_cfg["target_angle_error_on_act"])
    passes = (width <= out.policy.angle_width_max) & (amb <= out.policy.ambiguity_max)
    diag = {
        "inner_class_acc": float(correct.mean()),
        "inner_pose": angle_report(err, tol),
        "temperature_scale": scale,
        "credible_coverage": float(cover[k]),
        "novelty_max": out.policy.novelty_max,
        "class_conf_min": out.policy.class_conf_min,
        "ambiguity_max": out.policy.ambiguity_max,
        "inner_angle_gate": {"pass_rate": float(passes.mean()),
                             "error_rate_on_pass": float(np.mean(err[passes] > tol)) if passes.any() else float("nan")},
    }
    if len(nov_unknown):
        diag["inner_openset"] = openset_report(nov_known, nov_unknown)
    return out, scale, diag


def run_protocol(cfg: SystemConfig, feats, obj, angle, split: Split, gate_cfg: dict, version="dev"):
    calibrated, scale, diag = calibrate(cfg, feats, obj, angle, split, gate_cfg)
    system = _fit(calibrated, feats, obj, angle, split.train, version)
    system.pose.temperature_scale = scale
    return system, diag


def summarize(r: dict, y, a, unknown_objects, tol: float, pose_true_angle=None, sym_order=None) -> dict:
    """Métricas comunes a sistema, baseline y referencia. `r` necesita label, angle y decision."""
    known = ~np.isin(y, unknown_objects)
    class_ok = (r["label"] == y) & known
    angle_err = np.where(class_ok, circular_error(r["angle"], a), np.inf)
    res = {"n_test": len(y), "decision": decision_report(r["decision"], class_ok, angle_err, tol)}
    if known.any():
        res["class_acc"] = float(class_ok[known].mean())
        res["pose_end_to_end"] = angle_report(angle_err[known], tol)
        act = (r["decision"] == "ACT") & known
        res["pose_on_act"] = angle_report(angle_err[act], tol)
        if pose_true_angle is not None:  # pose aislada: con la clase verdadera, mide solo el plato
            res["pose_true_class"] = angle_report(circular_error(pose_true_angle[known], a[known]), tol)
            if sym_order is not None:
                order = np.array([sym_order.get(o, 1) for o in y[known]])
                res["pose_true_class_sym"] = angle_report(symmetric_error(pose_true_angle[known], a[known], order), tol)
    if (~known).any():
        res["unknown_rejected"] = float(np.mean(r["decision"][~known] == "UNKNOWN"))
    return res


def evaluate(system: VisionSystem, feats, obj, angle, split: Split, tol: float):
    """Evalúa en la prueba del protocolo. Devuelve (métricas, detalle por imagen para análisis de errores)."""
    idx = split.test
    t0 = time.perf_counter()
    r = system.infer(subset(feats, idx))
    latency_ms = (time.perf_counter() - t0) / len(idx) * 1000
    y, a = obj[idx], angle[idx]
    block = system.cfg.pose.block
    true_pose = system.pose.estimate(feats[block][idx], y).angle
    res = summarize(r, y, a, split.unknown_objects, tol, true_pose, system.pose.symmetry_order())
    res["latency_ms_per_image"] = latency_ms
    detail = {k: v for k, v in r.items() if k != "reasons"}
    detail.update({"idx": idx, "obj": y, "true_angle": a, "pose_true_class_angle": true_pose})
    return res, detail


def evaluate_baseline(feats, obj, angle, split: Split, tol: float, pca_dim: int = 150) -> dict:
    """Baseline simple: PCA sobre píxeles + 1-NN para la clase y ángulo de la vista más cercana.
    Sin control de seguridad: siempre actúa."""
    tr, te = split.train, split.test
    ident = IdentityModel(IdentityConfig(("raw",), "knn1", {}, pca_dim)).fit(subset(feats, tr), obj[tr], angle[tr])
    pose = PoseModel(PoseConfig()).fit(feats["raw"][tr], obj[tr], angle[tr])
    t0 = time.perf_counter()
    label, _ = ident.predict(subset(feats, te))
    r = {"label": label, "angle": pose.nearest_view(feats["raw"][te], label),
         "decision": np.full(len(te), "ACT")}
    latency_ms = (time.perf_counter() - t0) / len(te) * 1000
    res = summarize(r, obj[te], angle[te], split.unknown_objects, tol,
                    pose.nearest_view(feats["raw"][te], obj[te]))
    res["latency_ms_per_image"] = latency_ms
    return res


def two_shot(system: VisionSystem, feats, obj, angle, split: Split, delta: float, tol: float) -> dict:
    """Mitigación operativa del sector ciego: tras la 1a captura se gira el objeto `delta` grados (o se usa
    una 2a cámara desplazada `delta`) y se estima el ángulo con esa 2a imagen: theta = theta_2 - delta.
    La 2a vista existe en la galería de entrenamiento; para que sea una imagen nueva se excluye de la curva
    (leave-one-out) antes de estimar. Se actúa solo si la 2a estimación cae lejos de los huecos de cobertura
    y su conjunto creíble cabe en la tolerancia."""
    pose, block = system.pose, system.cfg.pose.block
    idx = split.test
    label = system.infer(subset(feats, idx))["label"]
    lookup = {(o, a): i for i, (o, a) in enumerate(zip(obj, angle))}
    est, act = np.full(len(idx), np.nan), np.zeros(len(idx), bool)
    for n, (i, lab) in enumerate(zip(idx, label)):
        t2 = (angle[i] + delta) % 360
        j = lookup[(obj[i], t2)]
        ga, gz = pose.gallery_angles[lab], pose.gallery_z[lab]
        keep = ga != t2
        curve = _closed_curve(ga[keep], gz[keep], pose.grid)
        z = pose.pca.transform(feats[block][j : j + 1])
        d2 = ((curve - z) ** 2).sum(1)[None]
        k = int(d2.argmin())
        th2 = pose.grid[k]
        width = pose._credible_count(pose._posterior(d2, pose.temperature_scale))[0] * pose.cfg.grid_step_deg
        far = circular_error(pose.grid, th2) > AMBIGUITY_EXCLUSION_DEG
        eps = 1e-3 * pose.base_temperature
        ambiguity = np.sqrt((d2[0, k] + eps) / (d2[0, far].min() + eps))
        missing = np.setdiff1d(GRID, ga)
        far_from_gap = missing.size == 0 or circular_error(th2, missing).min() > tol
        policy = system.cfg.policy
        est[n] = (th2 - delta) % 360
        act[n] = far_from_gap and width <= policy.angle_width_max and ambiguity <= policy.ambiguity_max
    class_ok = label == obj[idx]
    err = np.where(class_ok, circular_error(est, angle[idx]), np.inf)
    return {
        "delta_deg": delta,
        "within_tol_all": float(np.mean(err <= tol)),
        "act_rate": float(act.mean()),
        "within_tol_on_act": float(np.mean(err[act] <= tol)) if act.any() else float("nan"),
        "unsafe_rate": float(np.mean(act & (err > tol))),
        "mae_on_act": float(err[act & class_ok].mean()) if (act & class_ok).any() else float("nan"),
    }


def production_system(cfg: SystemConfig, feats, obj, angle, gate_cfg: dict, version: str):
    """Sistema final con los 100 objetos y las 72 vistas. Se calibra con las particiones internas tipo D
    (conocidos a 10 grados / validación a 5 grados + objetos que hacen de desconocidos)."""
    split = Split("D", np.arange(len(obj)), np.array([], int))
    return run_protocol(cfg, feats, obj, angle, split, gate_cfg, version)
