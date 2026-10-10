"""Sistema de visión completo: identidad + plato + similitud + control de seguridad.

La similitud es híbrida:
- top-k por pose: vistas de referencia del SKU predicho ordenadas por cercanía angular al ángulo estimado
  (explica la decisión: "esto es lo que creo que ves");
- top-k por apariencia: vecinos más cercanos en el espacio de características de identidad, independientes
  de la predicción (es la evidencia; la distancia al primero es la puntuación de novedad).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np

from .features import FeatureConfig, extract
from .gate import GatePolicy, decide
from .identity import IdentityConfig, IdentityModel
from .metrics import circular_error
from .pose import PoseConfig, PoseModel


@dataclass
class SystemConfig:
    features: FeatureConfig = field(default_factory=FeatureConfig)
    identity: IdentityConfig = field(default_factory=IdentityConfig)
    pose: PoseConfig = field(default_factory=PoseConfig)
    policy: GatePolicy = field(default_factory=GatePolicy)
    top_k: int = 5

    @classmethod
    def from_model_config(cls, cfg: dict, identity: IdentityConfig | None = None) -> SystemConfig:
        d = cfg["identity"]["default"]
        identity = identity or IdentityConfig(tuple(d["blocks"]), d["classifier"], dict(d.get("params", {})),
                                              cfg["identity"]["pca_dim"])
        gate = cfg["gate"]
        return cls(
            features=FeatureConfig.from_dict(cfg["features"]),
            identity=identity,
            pose=PoseConfig(cfg["pose"]["pca_dim"], cfg["pose"]["grid_step_deg"], cfg["pose"]["credible_mass"],
                            cfg["pose"].get("block", "raw")),
            policy=GatePolicy(angle_width_max=2 * gate["tolerance_deg"],
                              max_gallery_gap=gate["max_gallery_gap_deg"],
                              require_evidence_agreement=gate["require_evidence_agreement"]),
        )


class VisionSystem:
    def __init__(self, cfg: SystemConfig, version: str = "dev"):
        self.cfg = cfg
        self.version = version
        self.identity = IdentityModel(cfg.identity)
        self.pose = PoseModel(cfg.pose)

    def fit(self, feats: dict[str, np.ndarray], obj: np.ndarray, angle: np.ndarray) -> VisionSystem:
        self.identity.fit(feats, obj, angle)
        self.pose.fit(feats[self.cfg.pose.block], obj, angle)
        return self

    def infer(self, feats: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        """Inferencia por lotes; devuelve arrays (útil para evaluación)."""
        label, conf = self.identity.predict(feats)
        nn_dist, nn_idx = self.identity.neighbours(feats, self.cfg.top_k)
        nn_obj = self.identity.gallery_obj[nn_idx]
        pose = self.pose.estimate(feats[self.cfg.pose.block], label)
        agrees = nn_obj[:, 0] == label
        decision, reasons = decide(self.cfg.policy, nn_dist[:, 0], conf, agrees, pose.sku_max_gap,
                                   pose.credible_width, pose.ambiguity)
        return {
            "label": label, "class_confidence": conf, "novelty": nn_dist[:, 0], "evidence_agrees": agrees,
            "angle": pose.angle, "angle_width": pose.credible_width, "ambiguity": pose.ambiguity,
            "nearest_view_gap": pose.nearest_view_gap, "sku_max_gap": pose.sku_max_gap,
            "decision": decision, "reasons": reasons,
            "nn_obj": nn_obj, "nn_angle": self.identity.gallery_angle[nn_idx], "nn_dist": nn_dist,
        }

    def predict(self, feats: dict[str, np.ndarray]) -> list[dict]:
        """Salida estructurada por imagen (contrato del servicio de visión)."""
        r = self.infer(feats)
        k = self.cfg.top_k
        out = []
        for i in range(len(r["label"])):
            label, ang = int(r["label"][i]), float(r["angle"][i])
            ref = self.pose.gallery_angles.get(label, np.array([]))
            order = np.argsort(circular_error(ref, ang))[:k]
            out.append({
                "decision": r["decision"][i],
                "reasons": r["reasons"][i],
                "object_id": None if r["decision"][i] == "UNKNOWN" else label,
                "class_confidence": float(r["class_confidence"][i]),
                "novelty": float(r["novelty"][i]),
                "angle_deg": None if r["decision"][i] == "UNKNOWN" else ang,
                "angle_credible_width_deg": float(r["angle_width"][i]),
                "topk_pose": [{"object_id": label, "angle_deg": float(ref[j]),
                               "delta_deg": float(circular_error(ref[j], ang))} for j in order],
                "topk_appearance": [{"object_id": int(r["nn_obj"][i, j]), "angle_deg": float(r["nn_angle"][i, j]),
                                     "distance": float(r["nn_dist"][i, j])} for j in range(k)],
                "model_version": self.version,
            })
        return out

    def predict_images(self, images: np.ndarray) -> list[dict]:
        blocks = sorted(set(self.cfg.identity.blocks) | {self.cfg.pose.block})
        return self.predict(extract(images, self.cfg.features, blocks))

    def save(self, path: Path | str) -> None:
        joblib.dump(self, path, compress=3)

    @staticmethod
    def load(path: Path | str) -> VisionSystem:
        return joblib.load(path)
