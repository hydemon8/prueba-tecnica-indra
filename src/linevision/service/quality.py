"""Validación de la captura antes de inferir: criterios objetivos y deterministas.

El modelo se desarrolló con COIL-100 (un objeto sobre fondo oscuro, 128x128). Una imagen que no cumple esas
condiciones mínimas no se envía al modelo: se devuelve BAD_CAPTURE con los motivos.
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image, UnidentifiedImageError

MODEL_SIZE = 128
MIN_SIDE = 32
MIN_FOREGROUND = 0.02  # menos primer plano que esto: imagen vacía o apagada
MAX_FOREGROUND = 0.98  # más que esto: no hay fondo oscuro, fuera de las condiciones de captura
MAX_ASPECT = 1.5


class ImageDecodeError(ValueError):
    pass


def decode(raw: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except (UnidentifiedImageError, OSError, ValueError) as e:
        raise ImageDecodeError("el archivo no es una imagen PNG/JPEG válida") from e
    return img.convert("RGB")


def check(img: Image.Image, fg_threshold: int) -> tuple[np.ndarray, dict]:
    """Devuelve la imagen llevada al tamaño del modelo y el informe de calidad."""
    w, h = img.size
    issues = []
    if min(w, h) < MIN_SIDE:
        issues.append(f"resolución insuficiente ({w}x{h}; mínimo {MIN_SIDE} px por lado)")
    if max(w, h) / max(min(w, h), 1) > MAX_ASPECT:
        issues.append(f"relación de aspecto {w}x{h} lejos de la captura cuadrada de referencia")
    arr = np.asarray(img if (w, h) == (MODEL_SIZE, MODEL_SIZE) else img.resize((MODEL_SIZE, MODEL_SIZE),
                                                                                Image.BILINEAR))
    foreground = float((arr.max(axis=-1) > fg_threshold).mean())
    if foreground < MIN_FOREGROUND:
        issues.append(f"imagen vacía o demasiado oscura (primer plano {foreground:.1%})")
    elif foreground > MAX_FOREGROUND:
        issues.append(f"sin fondo oscuro (primer plano {foreground:.1%}): fuera de las condiciones de captura")
    report = {
        "ok": not issues,
        "issues": issues,
        "width": w,
        "height": h,
        "resized": (w, h) != (MODEL_SIZE, MODEL_SIZE),
        "foreground_fraction": round(foreground, 4),
        "mean_brightness": round(float(arr.mean()) / 255, 4),
    }
    return arr, report
