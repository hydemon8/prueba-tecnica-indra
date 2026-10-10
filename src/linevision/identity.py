"""Modelo de identidad: características clásicas -> clasificador estadístico, más la galería de vistas
de referencia que da la puntuación de novedad (objeto desconocido) y la evidencia por apariencia."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from .features import combine


class SoftmaxSVC(ClassifierMixin, BaseEstimator):
    """SVM RBF cuya confianza es el softmax de sus puntuaciones one-vs-rest.

    No se usa calibración de Platt con validación cruzada interna: con vistas ordenadas por ángulo los
    pliegues son sectores ciegos y las sigmoides por clase cambian el argmax. La confianza no pretende ser
    una probabilidad: su validez como base de decisión se demuestra con curvas riesgo-cobertura y su
    umbral se fija en validación interna por bloques de ángulo.
    """

    def __init__(self, C: float = 10.0):
        self.C = C

    def fit(self, X, y):
        self.svc_ = SVC(C=self.C, gamma="scale", decision_function_shape="ovr").fit(X, y)
        self.classes_ = self.svc_.classes_
        return self

    def decision_function(self, X):
        return self.svc_.decision_function(X)

    def predict(self, X):
        return self.classes_[self.decision_function(X).argmax(1)]

    def predict_proba(self, X):
        s = self.decision_function(X)
        e = np.exp(s - s.max(1, keepdims=True))
        return e / e.sum(1, keepdims=True)


CLASSIFIERS = {
    "knn1": lambda **p: KNeighborsClassifier(n_neighbors=1),
    "logreg": lambda C=10.0, **_: LogisticRegression(C=C, max_iter=2000),
    "svm_rbf": lambda C=10.0, **_: SoftmaxSVC(C=C),
    "rf": lambda n_estimators=500, **_: RandomForestClassifier(n_estimators=n_estimators, n_jobs=-1,
                                                              random_state=0),
}


@dataclass
class IdentityConfig:
    blocks: tuple[str, ...] = ("hsv", "hog", "lbp")
    classifier: str = "svm_rbf"
    params: dict = field(default_factory=dict)
    pca_dim: int | None = 150

    @property
    def name(self) -> str:
        p = ",".join(f"{k}={v}" for k, v in sorted(self.params.items()))
        return f"{'+'.join(self.blocks)}|{self.classifier}({p})"


class IdentityModel:
    def __init__(self, cfg: IdentityConfig):
        self.cfg = cfg

    def fit(self, feats: dict[str, np.ndarray], obj: np.ndarray, angle: np.ndarray) -> IdentityModel:
        X = combine(feats, self.cfg.blocks)
        # PCA antes de estandarizar: estandarizar >2000 dims (bins casi vacíos de HSV/HOG) amplifica ruido
        steps = []
        if self.cfg.pca_dim and X.shape[1] > self.cfg.pca_dim:
            steps.append(PCA(self.cfg.pca_dim, random_state=0))
        steps += [StandardScaler(), CLASSIFIERS[self.cfg.classifier](**self.cfg.params)]
        self.pipe = make_pipeline(*steps).fit(X, obj)
        self.gallery = X
        self.gallery_sq = (X**2).sum(1)
        self.gallery_obj = np.asarray(obj)
        self.gallery_angle = np.asarray(angle)
        return self

    def predict(self, feats: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
        """Clase top-1 y su probabilidad estimada (confianza de clase)."""
        proba = self.pipe.predict_proba(combine(feats, self.cfg.blocks))
        k = proba.argmax(1)
        return self.pipe.classes_[k], proba[np.arange(len(k)), k]

    def neighbours(self, feats: dict[str, np.ndarray], k: int = 5):
        """k vistas de la galería más cercanas en apariencia: (distancias, índices de galería).
        La distancia al vecino 1 es la puntuación de novedad."""
        return nearest(self.gallery, combine(feats, self.cfg.blocks), k, self.gallery_sq)


def nearest(gallery: np.ndarray, X: np.ndarray, k: int = 1, gallery_sq: np.ndarray | None = None,
            chunk: int = 1024) -> tuple[np.ndarray, np.ndarray]:
    """k vecinos euclídeos más cercanos de cada fila de X en `gallery`, por bloques (memoria acotada)."""
    gallery_sq = (gallery**2).sum(1) if gallery_sq is None else gallery_sq
    k = min(k, len(gallery))
    dist = np.empty((len(X), k), np.float32)
    idx = np.empty((len(X), k), np.int64)
    for s in range(0, len(X), chunk):
        q = X[s : s + chunk]
        d2 = np.maximum((q**2).sum(1)[:, None] + gallery_sq[None] - 2 * q @ gallery.T, 0)
        part = np.argpartition(d2, k - 1, axis=1)[:, :k]
        order = np.take_along_axis(d2, part, 1).argsort(1)
        idx[s : s + chunk] = np.take_along_axis(part, order, 1)
        dist[s : s + chunk] = np.sqrt(np.take_along_axis(d2, idx[s : s + chunk], 1))
    return dist, idx
