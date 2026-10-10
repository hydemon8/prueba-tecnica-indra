"""Referencia moderna (solo comparación, no va a producción): embeddings auto-supervisados DINOv2.

Se usan como un bloque de características más ("dino") para que el resto del pipeline sea idéntico:
mismo clasificador candidato, misma curva cerrada del plato, mismo control de seguridad. Así la
comparación aísla el efecto de la representación profunda frente a la clásica.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

MODEL_NAME = "facebook/dinov2-small"


def _device():
    import torch

    return "mps" if torch.backends.mps.is_available() else "cpu"


def dino_embeddings(images: np.ndarray, data_version: str, cache: Path, batch: int = 64) -> tuple[np.ndarray, dict]:
    """Embedding = [token CLS, media de tokens de parche] de DINOv2-small (768-d). Cacheado en disco."""
    path = Path(cache) / f"dino_{MODEL_NAME.split('/')[-1]}_{data_version}.npz"
    if path.exists():
        with np.load(path) as z:
            return z["emb"], {"model": MODEL_NAME, "ms_per_image": float(z["ms_per_image"]), "device": str(z["device"])}

    import torch
    from transformers import AutoImageProcessor, AutoModel

    device = _device()
    processor = AutoImageProcessor.from_pretrained(MODEL_NAME)
    model = AutoModel.from_pretrained(MODEL_NAME).eval().to(device)
    out = []
    t0 = time.perf_counter()
    with torch.inference_mode():
        for s in range(0, len(images), batch):
            inputs = processor(images=list(images[s : s + batch]), return_tensors="pt").to(device)
            h = model(**inputs).last_hidden_state
            out.append(torch.cat([h[:, 0], h[:, 1:].mean(1)], dim=1).float().cpu().numpy())
    ms = (time.perf_counter() - t0) / len(images) * 1000
    emb = np.concatenate(out).astype(np.float32)
    np.savez_compressed(path, emb=emb, ms_per_image=ms, device=device)
    return emb, {"model": MODEL_NAME, "ms_per_image": ms, "device": device}
