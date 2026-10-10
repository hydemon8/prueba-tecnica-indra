"""Extracción de características clásicas.

- hsv: histograma de color HSV sobre el primer plano (raíz cuadrada = embebido de Hellinger). Casi
  invariante al giro del plato: buena para identidad, inútil para el ángulo.
- hog: gradientes orientados (forma). lbp: patrones binarios locales (textura).
- raw: píxeles 32x32; alimenta el espacio propio del modelo de pose (sensible al ángulo a propósito).
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from skimage.feature import hog, local_binary_pattern
from sklearn.preprocessing import normalize

ALL_BLOCKS = ("raw", "hsv", "hog", "lbp")


@dataclass(frozen=True)
class FeatureConfig:
    fg_threshold: int = 60
    hsv_bins: tuple[int, int, int] = (16, 4, 4)
    hog_size: int = 64
    hog_cell: int = 8
    hog_orientations: int = 9
    lbp: tuple[tuple[int, int], ...] = ((8, 1), (16, 2))
    raw_size: int = 32

    @classmethod
    def from_dict(cls, d: dict) -> FeatureConfig:
        d = dict(d)
        d["hsv_bins"] = tuple(d.get("hsv_bins", cls.hsv_bins))
        d["lbp"] = tuple(tuple(x) for x in d.get("lbp", cls.lbp))
        return cls(**d)


def raw_pixels(img: np.ndarray, cfg: FeatureConfig) -> np.ndarray:
    small = Image.fromarray(img).resize((cfg.raw_size, cfg.raw_size), Image.BILINEAR)
    return np.asarray(small, np.float32).ravel() / 255.0


def hsv_hist(img: np.ndarray, cfg: FeatureConfig) -> np.ndarray:
    hsv = np.asarray(Image.fromarray(img).convert("HSV"))
    fg = img.max(axis=-1) > cfg.fg_threshold
    pixels = hsv[fg] if fg.any() else hsv.reshape(-1, 3)
    hist, _ = np.histogramdd(pixels, bins=cfg.hsv_bins, range=((0, 256),) * 3)
    hist = hist.ravel()
    return np.sqrt(hist / max(hist.sum(), 1.0)).astype(np.float32)


def hog_desc(img: np.ndarray, cfg: FeatureConfig) -> np.ndarray:
    gray = Image.fromarray(img).convert("L").resize((cfg.hog_size, cfg.hog_size), Image.BILINEAR)
    return hog(
        np.asarray(gray, np.float32),
        orientations=cfg.hog_orientations,
        pixels_per_cell=(cfg.hog_cell, cfg.hog_cell),
        cells_per_block=(2, 2),
        feature_vector=True,
    ).astype(np.float32)


def lbp_hist(img: np.ndarray, cfg: FeatureConfig) -> np.ndarray:
    gray = np.asarray(Image.fromarray(img).convert("L"))
    out = []
    for points, radius in cfg.lbp:
        codes = local_binary_pattern(gray, points, radius, method="uniform").astype(np.int64)
        hist = np.bincount(codes.ravel(), minlength=points + 2).astype(np.float32)
        out.append(hist / hist.sum())
    return np.concatenate(out)


_BLOCK_FNS = {"raw": raw_pixels, "hsv": hsv_hist, "hog": hog_desc, "lbp": lbp_hist}


def extract(images: np.ndarray, cfg: FeatureConfig, blocks=ALL_BLOCKS) -> dict[str, np.ndarray]:
    """Devuelve un dict bloque -> matriz (n_imágenes, dim)."""
    if images.ndim == 3:
        images = images[None]
    out: dict[str, list] = {b: [] for b in blocks}
    for img in images:
        for b in blocks:
            out[b].append(_BLOCK_FNS[b](img, cfg))
    return {b: np.stack(v).astype(np.float32) for b, v in out.items()}


def extract_cached(images: np.ndarray, cfg: FeatureConfig, data_version: str, cache: Path,
                   blocks=ALL_BLOCKS) -> dict[str, np.ndarray]:
    key = hashlib.sha256(f"{data_version}|{asdict(cfg)}|{blocks}".encode()).hexdigest()[:12]
    path = Path(cache) / f"features_{key}.npz"
    if path.exists():
        with np.load(path) as z:
            return {b: z[b] for b in blocks}
    feats = extract(images, cfg, blocks)
    np.savez_compressed(path, **feats)
    return feats


def subset(feats: dict[str, np.ndarray], idx: np.ndarray) -> dict[str, np.ndarray]:
    return {b: v[idx] for b, v in feats.items()}


def combine(feats: dict[str, np.ndarray], blocks) -> np.ndarray:
    """Concatena bloques normalizados L2 por fila para que cada familia pese lo mismo."""
    return np.concatenate([normalize(feats[b]) for b in blocks], axis=1).astype(np.float32)
