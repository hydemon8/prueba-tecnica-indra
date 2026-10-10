"""Control de seguridad determinista: decide qué recibe el robot. Nunca lo decide un LLM.

Orden de reglas (la primera que se cumple gana):
  1. UNKNOWN            novedad > umbral: no se parece a nada del catálogo -> carril de rechazo.
  2. REVIEW             confianza de clase baja o la evidencia por apariencia contradice la clase
                        -> cola de revisión humana.
  3. ANGLE_UNCERTIFIED  el SKU no tiene cobertura angular suficiente (hueco en su galería), el conjunto
                        creíble del ángulo es más ancho que la tolerancia del robot, o hay otra orientación
                        casi igual de plausible (ambigüedad) -> 2a captura / manual.
  4. ACT                el robot recibe clase + ángulo.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np


class Decision(str, Enum):
    ACT = "ACT"
    ANGLE_UNCERTIFIED = "ANGLE_UNCERTIFIED"
    REVIEW = "REVIEW"
    UNKNOWN = "UNKNOWN"


@dataclass
class GatePolicy:
    novelty_max: float = float("inf")
    class_conf_min: float = 0.0
    angle_width_max: float = 20.0  # = 2 x tolerancia de agarre (+-10 grados)
    ambiguity_max: float = float("inf")  # calibrado: P(error > tolerancia | ACT) <= objetivo
    max_gallery_gap: float = 30.0
    require_evidence_agreement: bool = True


def decide(policy: GatePolicy, novelty, class_conf, evidence_agrees, sku_max_gap, angle_width, ambiguity):
    n = len(novelty)
    decision = np.full(n, Decision.ACT.value, dtype=object)
    reasons: list[list[str]] = [[] for _ in range(n)]
    pending = np.ones(n, bool)

    def apply(mask, label, why):
        nonlocal pending
        hit = pending & mask
        for i in np.flatnonzero(hit):
            decision[i] = label
            reasons[i].append(why(i))
        pending &= ~hit

    apply(np.asarray(novelty) > policy.novelty_max, Decision.UNKNOWN.value,
          lambda i: f"novedad {novelty[i]:.3f} > {policy.novelty_max:.3f}: no se parece a ningún SKU del catálogo")
    low_conf = np.asarray(class_conf) < policy.class_conf_min
    disagree = ~np.asarray(evidence_agrees, bool) if policy.require_evidence_agreement else np.zeros(n, bool)
    apply(low_conf | disagree, Decision.REVIEW.value,
          lambda i: (f"confianza de clase {class_conf[i]:.3f} < {policy.class_conf_min:.3f}" if low_conf[i]
                     else "la vista más parecida pertenece a otro SKU"))
    no_cov = np.asarray(sku_max_gap) > policy.max_gallery_gap
    wide = np.asarray(angle_width) > policy.angle_width_max
    ambiguous = np.asarray(ambiguity) > policy.ambiguity_max

    def angle_reason(i):
        if no_cov[i]:
            return f"SKU sin cobertura angular certificada (hueco de {sku_max_gap[i]:.0f} grados)"
        if wide[i]:
            return f"incertidumbre angular {angle_width[i]:.1f} grados > {policy.angle_width_max:.0f}"
        return f"ángulo ambiguo: otra orientación casi igual de plausible ({ambiguity[i]:.2f} > {policy.ambiguity_max:.2f})"

    apply(no_cov | wide | ambiguous, Decision.ANGLE_UNCERTIFIED.value, angle_reason)
    return decision.astype(str), reasons


def calibrate_ambiguity(width, ambiguity, angle_err, width_max: float, tol: float, target_error: float) -> float:
    """Mayor umbral de ambigüedad tal que, entre los casos con ancho <= width_max, la fracción con error
    angular > tol no supere el objetivo. Es la traducción de la tolerancia del robot a un criterio de riesgo."""
    ok_width = np.asarray(width) <= width_max
    amb, bad = np.asarray(ambiguity)[ok_width], np.asarray(angle_err)[ok_width] > tol
    order = np.argsort(amb)
    cum_err = np.cumsum(bad[order]) / np.arange(1, len(order) + 1)
    ok = np.flatnonzero(cum_err <= target_error)
    return float(amb[order][ok.max()]) if ok.size else 0.0


def calibrate_class_conf(conf: np.ndarray, correct: np.ndarray, target_error: float) -> float:
    """Umbral mínimo de confianza tal que el error de clase entre los aceptados no supere el objetivo."""
    order = np.argsort(-conf)
    cum_err = np.cumsum(~np.asarray(correct)[order]) / np.arange(1, len(order) + 1)
    ok = np.flatnonzero(cum_err <= target_error)
    return float(conf[order][ok.max()]) if ok.size else float("inf")
