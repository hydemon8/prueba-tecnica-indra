"""Carga de COIL-100 con validación de integridad y huella de versión (trazabilidad de datos)."""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

N_OBJECTS = 100
N_VIEWS = 72
STEP_DEG = 5
IMAGE_SHAPE = (128, 128, 3)

_NAME = re.compile(r"^obj(\d+)__(\d+)\.png$")


@dataclass(frozen=True)
class Coil100:
    """Dataset ordenado por (objeto, ángulo): el índice i corresponde a obj=i//72+1, ángulo=(i%72)*5."""

    images: np.ndarray  # (N, 128, 128, 3) uint8
    obj: np.ndarray  # (N,) int 1..100
    angle: np.ndarray  # (N,) int, grados en [0, 360)
    version: str  # sha256 truncado sobre nombres + bytes de los PNG

    def __len__(self) -> int:
        return len(self.obj)


def load_coil100(root: Path | str) -> Coil100:
    root = Path(root)
    files = sorted(
        (int(m.group(1)), int(m.group(2)), p)
        for p in root.iterdir()
        if (m := _NAME.match(p.name))
    )
    if len(files) != N_OBJECTS * N_VIEWS:
        raise ValueError(f"se esperaban {N_OBJECTS * N_VIEWS} imágenes y hay {len(files)} en {root}")

    digest = hashlib.sha256()
    images = np.empty((len(files), *IMAGE_SHAPE), np.uint8)
    for i, (_, _, path) in enumerate(files):
        raw = path.read_bytes()
        digest.update(path.name.encode())
        digest.update(raw)
        images[i] = np.asarray(Image.open(io.BytesIO(raw)).convert("RGB"))

    obj = np.array([f[0] for f in files])
    angle = np.array([f[1] for f in files])
    expected = np.arange(0, 360, STEP_DEG)
    for o in range(1, N_OBJECTS + 1):
        if not np.array_equal(angle[obj == o], expected):
            raise ValueError(f"obj{o}: vistas incompletas o fuera de la rejilla de {STEP_DEG} grados")
    return Coil100(images, obj, angle, digest.hexdigest()[:16])
