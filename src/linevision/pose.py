"""Modelo del plato: estimación del giro (yaw) con espacio propio paramétrico (Murase & Nayar, 1995).

El objeto solo gira alrededor del eje vertical (1 grado de libertad), así que todas sus apariencias forman
una curva cerrada parametrizada por el ángulo del plato. Las vistas de referencia se proyectan a un espacio
PCA global, se unen con un spline cúbico periódico y el ángulo de una imagen nueva es el punto más cercano
de la curva de su objeto. El perfil de distancias a lo largo de la curva define una distribución sobre el
ángulo; el ancho de su conjunto creíble es la incertidumbre y crece cuando hay ambigüedad (simetrías) o
cuando la imagen cae lejos de lo observado.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.interpolate import CubicSpline
from sklearn.decomposition import PCA

from .metrics import circular_error

AMBIGUITY_EXCLUSION_DEG = 20.0


@dataclass
class PoseConfig:
    pca_dim: int = 50
    grid_step_deg: float = 0.5
    credible_mass: float = 0.9
    block: str = "raw"  # bloque de características de entrada (raw = píxeles; dino = referencia moderna)


@dataclass
class PoseEstimate:
    angle: np.ndarray  # grados [0, 360); NaN si el objeto no está en catálogo
    credible_width: np.ndarray  # grados cubiertos por el conjunto creíble
    ambiguity: np.ndarray  # d_min / d_min fuera de +-20 grados; ~1 => dos ángulos igual de plausibles
    nearest_view_gap: np.ndarray  # distancia de la estimación a la vista de referencia más cercana
    sku_max_gap: np.ndarray  # hueco angular máximo de la galería del objeto (certificación de SKU)


def _closed_curve(a: np.ndarray, z: np.ndarray, grid: np.ndarray) -> np.ndarray:
    """Curva cerrada que pasa por las vistas (a ordenado, en grados), evaluada en `grid`."""
    x = a[0] + (grid - a[0]) % 360
    t = np.r_[a, a[0] + 360]
    pts = np.vstack([z, z[:1]])
    if len(a) >= 3:
        return CubicSpline(t, pts, bc_type="periodic")(x)
    return np.stack([np.interp(x, t, pts[:, j]) for j in range(pts.shape[1])], axis=1)


class PoseModel:
    def __init__(self, cfg: PoseConfig):
        self.cfg = cfg
        self.temperature_scale = 1.0

    def fit(self, raw: np.ndarray, obj: np.ndarray, angle: np.ndarray) -> PoseModel:
        n_comp = min(self.cfg.pca_dim, len(raw) - 1, raw.shape[1])
        self.pca = PCA(n_comp, random_state=0).fit(raw)
        Z = self.pca.transform(raw).astype(np.float32)
        self.grid = np.arange(0, 360, self.cfg.grid_step_deg)
        self.curves, self.curves_sq, self.gallery_angles, self.max_gap = {}, {}, {}, {}
        self.gallery_z, self.symmetry_score = {}, {}
        step_d2 = []
        for o in np.unique(obj):
            m = obj == o
            order = np.argsort(angle[m])
            a, z = angle[m][order].astype(float), Z[m][order]
            curve = _closed_curve(a, z, self.grid).astype(np.float32)
            self.curves[o], self.curves_sq[o] = curve, (curve**2).sum(1)
            self.gallery_angles[o], self.gallery_z[o] = a, z
            self.max_gap[o] = float(np.diff(np.r_[a, a[0] + 360]).max())
            step_d2.append(np.median(((np.roll(z, -1, 0) - z) ** 2).sum(1)))
            self.symmetry_score[o] = self._symmetry(curve)
        # escala natural del ruido: distancia cuadrática típica entre vistas consecutivas de la galería
        self.base_temperature = float(np.median(step_d2))
        return self

    def _symmetry(self, curve: np.ndarray) -> float:
        """d(theta, theta+180) relativa a d(theta, theta+10) sobre la curva: < 1 indica que vistas opuestas se
        parecen más que dos vistas a 10 grados (simetría de orden 2). No depende del espaciado de la galería."""
        per_deg = round(1 / self.cfg.grid_step_deg)
        d180 = ((curve - np.roll(curve, -180 * per_deg, 0)) ** 2).sum(1)
        d10 = ((curve - np.roll(curve, -10 * per_deg, 0)) ** 2).sum(1)
        return float(np.median(d180) / max(np.median(d10), 1e-12))

    def symmetry_order(self, threshold: float = 1.0) -> dict:
        """Orden de simetría rotacional estimado por objeto (1 = ninguna, 2 = theta ~ theta+180)."""
        return {o: 2 if s < threshold else 1 for o, s in self.symmetry_score.items()}

    def nearest_view(self, raw: np.ndarray, obj: np.ndarray) -> np.ndarray:
        """Baseline: ángulo de la vista de referencia más cercana (1-NN), sin curva ni interpolación."""
        Z = self.pca.transform(raw).astype(np.float32)
        out = np.full(len(Z), np.nan)
        for o in np.unique(obj):
            if o in self.gallery_z:
                rows = np.flatnonzero(obj == o)
                d2 = ((Z[rows, None] - self.gallery_z[o][None]) ** 2).sum(-1)
                out[rows] = self.gallery_angles[o][d2.argmin(1)]
        return out

    def _profiles(self, Z: np.ndarray, o) -> np.ndarray:
        C = self.curves[o]
        return np.maximum((Z**2).sum(1)[:, None] + self.curves_sq[o][None] - 2 * Z @ C.T, 0)

    def _posterior(self, d2: np.ndarray, scale: float) -> np.ndarray:
        dmin = d2.min(1, keepdims=True)
        w = np.exp(-(d2 - dmin) / (scale * self.base_temperature))
        return w / w.sum(1, keepdims=True)

    def _credible_count(self, w: np.ndarray) -> np.ndarray:
        cum = np.cumsum(-np.sort(-w, axis=1), axis=1)
        return (cum < self.cfg.credible_mass).sum(1) + 1

    def estimate(self, raw: np.ndarray, obj: np.ndarray) -> PoseEstimate:
        Z = self.pca.transform(raw).astype(np.float32)
        n = len(Z)
        out = {k: np.full(n, np.nan) for k in PoseEstimate.__dataclass_fields__}
        for o in np.unique(obj):
            if o not in self.curves:
                continue
            rows = np.flatnonzero(obj == o)
            d2 = self._profiles(Z[rows], o)
            k = d2.argmin(1)
            ang = self.grid[k]
            dmin = d2[np.arange(len(rows)), k]
            far = circular_error(self.grid[None], ang[:, None]) > AMBIGUITY_EXCLUSION_DEG
            dfar = np.where(far, d2, np.inf).min(1)
            w = self._posterior(d2, self.temperature_scale)
            out["angle"][rows] = ang
            out["credible_width"][rows] = self._credible_count(w) * self.cfg.grid_step_deg
            eps = 1e-3 * self.base_temperature  # regulariza 0/0 cuando la consulta cae sobre la curva
            out["ambiguity"][rows] = np.sqrt((dmin + eps) / (dfar + eps))
            out["nearest_view_gap"][rows] = circular_error(ang[:, None], self.gallery_angles[o][None]).min(1)
            out["sku_max_gap"][rows] = self.max_gap[o]
        return PoseEstimate(**out)

    def coverage(self, raw: np.ndarray, obj: np.ndarray, angle: np.ndarray, scales) -> np.ndarray:
        """Para cada escala de temperatura, si el ángulo verdadero cae en el conjunto creíble.
        Devuelve (n_escalas, n) booleano; sirve para calibrar la incertidumbre en validación interna."""
        Z = self.pca.transform(raw).astype(np.float32)
        hit = np.zeros((len(scales), len(Z)), bool)
        true_k = np.round(np.asarray(angle) / self.cfg.grid_step_deg).astype(int) % len(self.grid)
        for o in np.unique(obj):
            rows = np.flatnonzero(obj == o)
            d2 = self._profiles(Z[rows], o)
            for s, scale in enumerate(scales):
                w = self._posterior(d2, scale)
                cut = -np.sort(-w, axis=1)[np.arange(len(rows)), self._credible_count(w) - 1]
                hit[s, rows] = w[np.arange(len(rows)), true_k[rows]] >= cut
        return hit
