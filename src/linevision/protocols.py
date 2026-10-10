"""Protocolos de partición A–D (sección 4 del enunciado) y particiones internas de validación.

Las particiones internas se construyen SOLO con vistas de entrenamiento e imitan el protocolo externo,
de modo que hiperparámetros y umbrales nunca ven la prueba. Las vistas a 5 grados son casi duplicados,
así que nunca se usa K-fold aleatorio: siempre se parte por bloques de ángulo u objeto.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

STEP = 5


@dataclass(frozen=True, eq=False)
class Split:
    name: str
    train: np.ndarray  # índices del dataset
    test: np.ndarray  # índices del dataset (en particiones internas: validación)
    unknown_objects: tuple[int, ...] = ()  # objetos fuera de catálogo (protocolo D)
    meta: dict = field(default_factory=dict)


def _idx(mask: np.ndarray) -> np.ndarray:
    return np.flatnonzero(mask)


def _arc_mask(obj: np.ndarray, angle: np.ndarray, starts: dict[int, int], arc_deg: int) -> np.ndarray:
    """Máscara de un arco contiguo [start, start+arc_deg) por objeto, en aritmética circular."""
    offset = (angle - np.array([starts[o] for o in obj])) % 360
    return offset < arc_deg


def protocol_a(obj: np.ndarray, angle: np.ndarray, step: int = 10) -> Split:
    train = angle % step == 0
    return Split("A", _idx(train), _idx(~train))


def protocol_b(obj: np.ndarray, angle: np.ndarray, seed: int, arc_deg: int = 60) -> Split:
    rng = np.random.default_rng(seed)
    objects = np.unique(obj)
    starts = {int(o): int(s) * STEP for o, s in zip(objects, rng.integers(0, 360 // STEP, len(objects)))}
    test = _arc_mask(obj, angle, starts, arc_deg)
    return Split("B", _idx(~test), _idx(test), meta={"arc_start": starts, "arc_deg": arc_deg, "seed": seed})


def protocol_c(obj: np.ndarray, angle: np.ndarray, step: int = 30) -> Split:
    train = angle % step == 0
    return Split("C", _idx(train), _idx(~train))


def protocol_d(obj: np.ndarray, angle: np.ndarray, seed: int, n_unknown: int = 10) -> Split:
    rng = np.random.default_rng(seed)
    unknown = np.sort(rng.choice(np.unique(obj), n_unknown, replace=False))
    test = np.isin(obj, unknown)
    return Split("D", _idx(~test), _idx(test), tuple(int(u) for u in unknown), meta={"seed": seed})


def make_protocol(name: str, obj: np.ndarray, angle: np.ndarray, cfg: dict, repeat: int = 0) -> Split:
    seed = cfg["seed"] + repeat
    if name == "A":
        return protocol_a(obj, angle, cfg["A"]["train_step_deg"])
    if name == "B":
        return protocol_b(obj, angle, seed, cfg["B"]["arc_deg"])
    if name == "C":
        return protocol_c(obj, angle, cfg["C"]["train_step_deg"])
    if name == "D":
        return protocol_d(obj, angle, seed, cfg["D"]["n_unknown"])
    raise ValueError(f"protocolo desconocido: {name}")


def _alternate(train_idx: np.ndarray, angle: np.ndarray, step: int, name: str) -> list[Split]:
    """Dos pliegues que alternan vistas del entrenamiento: entrena con múltiplos de 2*step, valida con
    los intermedios, y al revés. Duplica el espaciado: es más exigente que el protocolo externo."""
    a = angle[train_idx]
    even = (a // step) % 2 == 0
    return [
        Split(f"{name}/in{k}", train_idx[tr], train_idx[~tr])
        for k, tr in enumerate((even, ~even))
    ]


def inner_splits(split: Split, obj: np.ndarray, angle: np.ndarray, seed: int = 0) -> list[Split]:
    if split.name == "A":
        return _alternate(split.train, angle, 10, "A")
    if split.name == "C":
        return _alternate(split.train, angle, 30, "C")
    if split.name == "B":
        # un segundo arco ciego de igual ancho, contenido en la región vista (300 grados), en 3 posiciones
        arc = split.meta["arc_deg"]
        out = []
        for k, off in enumerate((30, 120, 210)):
            starts = {o: (s + arc + off) % 360 for o, s in split.meta["arc_start"].items()}
            inner = _arc_mask(obj[split.train], angle[split.train], starts, arc)
            out.append(Split(f"B/in{k}", split.train[~inner], split.train[inner],
                             meta={"arc_start": starts, "arc_deg": arc}))
        return out
    if split.name == "D":
        # objetos de catálogo que hacen de "desconocidos" internos; los conocidos se validan como en A
        known = np.setdiff1d(np.unique(obj[split.train]), split.unknown_objects)
        groups = np.random.default_rng(seed).permutation(known)[:30].reshape(3, 10)
        out = []
        for k, pseudo in enumerate(groups):
            in_pseudo = np.isin(obj, pseudo)
            base = np.isin(np.arange(len(obj)), split.train) & ~in_pseudo
            tr = base & (angle % 10 == 0)
            va = (base & (angle % 10 == 5)) | in_pseudo
            out.append(Split(f"D/in{k}", _idx(tr), _idx(va), tuple(int(p) for p in pseudo)))
        return out
    raise ValueError(f"protocolo desconocido: {split.name}")


def covered_splits(split: Split, obj: np.ndarray, angle: np.ndarray) -> list[Split]:
    """Particiones del régimen con cobertura: alternan vistas consecutivas del entrenamiento (sin crear
    huecos grandes). Calibran la incertidumbre del ángulo y su umbral de riesgo; el sector ciego no se
    calibra aquí porque lo gobierna la regla determinista de cobertura del SKU."""
    step = int(np.diff(np.unique(angle[split.train])).min())
    return _alternate(split.train, angle, step, f"{split.name}/cov")
