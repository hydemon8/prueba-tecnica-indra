"""Ayudas de análisis exploratorio y de errores para el notebook."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .metrics import circular_error


def montage(images: np.ndarray, ncols: int, titles=None, size: float = 1.1):
    n = len(images)
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * size, nrows * size * (1.25 if titles else 1)))
    for ax in np.ravel(axes):
        ax.axis("off")
    for i, ax in enumerate(np.ravel(axes)[:n]):
        ax.imshow(images[i])
        if titles is not None:
            ax.set_title(titles[i], fontsize=7)
    fig.tight_layout()
    return fig


def confusion_pairs(detail: dict, top: int = 10) -> pd.DataFrame:
    wrong = detail["label"] != detail["obj"]
    pairs = pd.DataFrame({"verdadero": detail["obj"][wrong], "predicho": detail["label"][wrong]})
    return pairs.value_counts().head(top).rename("n").reset_index()


def per_object_pose(detail: dict, tol: float, symmetry_score: dict | None = None) -> pd.DataFrame:
    err = circular_error(detail["pose_true_class_angle"], detail["true_angle"])
    df = pd.DataFrame({"obj": detail["obj"], "err": err})
    out = df.groupby("obj")["err"].agg(mae="mean", within_tol=lambda e: np.mean(e <= tol),
                                       flips_gt150=lambda e: np.mean(e > 150))
    if symmetry_score:
        out["symmetry_score"] = out.index.map(symmetry_score)
    return out.sort_values("mae", ascending=False)


def risk_coverage(conf: np.ndarray, correct: np.ndarray):
    order = np.argsort(-conf, kind="stable")
    err = ~np.asarray(correct)[order]
    n = np.arange(1, len(err) + 1)
    return n / len(err), np.cumsum(err) / n
