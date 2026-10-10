"""Alerta de captura por línea: detecta una subida brusca de objetos "desconocidos".

Con el umbral de novedad calibrado, alrededor del 1 % de los productos conocidos sale como UNKNOWN. Una tasa
sostenida muy por encima de eso casi nunca son objetos ajenos: es la iluminación, la cámara o un lote nuevo.
Rechazar en ese estado tira producto bueno, así que mientras la alerta está activa los UNKNOWN se retienen para
revisión humana en lugar de ir al carril de rechazo.

Es una regla determinista sobre una ventana deslizante; no interviene ningún modelo de lenguaje.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field

BRIGHTNESS_SHIFT = 0.10  # cambio relativo de brillo que apunta a la iluminación como causa


@dataclass(frozen=True)
class MonitorConfig:
    window: int = 100  # capturas válidas recientes que se observan
    min_samples: int = 30  # no se evalúa con menos capturas que estas
    raise_at: float = 0.10  # tasa de UNKNOWN que activa la alerta (unas 10 veces la esperada)
    clear_at: float = 0.03  # tasa a la que se desactiva (histéresis: no parpadea alrededor del umbral)
    baseline: int = 500  # capturas aceptadas con las que se estima el brillo normal de la línea


@dataclass
class _Line:
    unknown: deque
    brightness: deque
    normal: deque
    active: bool = False
    raised: int = 0
    seen: int = 0
    reason: str = field(default="")


class CaptureMonitor:
    def __init__(self, cfg: MonitorConfig | None = None):
        self.cfg = cfg or MonitorConfig()
        self._lines: dict[str, _Line] = {}
        self._lock = threading.Lock()

    def _line(self, line_id: str) -> _Line:
        if line_id not in self._lines:
            c = self.cfg
            self._lines[line_id] = _Line(deque(maxlen=c.window), deque(maxlen=c.window), deque(maxlen=c.baseline))
        return self._lines[line_id]

    def observe(self, line_id: str, decision: str, brightness: float) -> tuple[dict, str | None]:
        """Registra una captura válida. Devuelve (estado de la línea, transición 'raised' | 'cleared' | None)."""
        with self._lock:
            ln = self._line(line_id)
            ln.seen += 1
            ln.unknown.append(decision == "UNKNOWN")
            ln.brightness.append(brightness)
            if decision == "ACT" and not ln.active:  # el brillo normal se aprende solo de capturas aceptadas
                ln.normal.append(brightness)
            rate = sum(ln.unknown) / len(ln.unknown)
            change = None
            if len(ln.unknown) >= self.cfg.min_samples:
                if not ln.active and rate >= self.cfg.raise_at:
                    ln.active, ln.raised, change = True, ln.raised + 1, "raised"
                elif ln.active and rate <= self.cfg.clear_at:
                    ln.active, change = False, "cleared"
            return self._snapshot(line_id, ln), change

    def snapshot(self, line_id: str) -> dict:
        with self._lock:
            return self._snapshot(line_id, self._line(line_id))

    def _snapshot(self, line_id: str, ln: _Line) -> dict:
        n = len(ln.unknown)
        rate = sum(ln.unknown) / n if n else 0.0
        shift = None
        if len(ln.normal) >= self.cfg.min_samples and ln.brightness:
            normal = sum(ln.normal) / len(ln.normal)
            recent = list(ln.brightness)[-self.cfg.min_samples:]
            shift = (sum(recent) / len(recent)) / normal - 1 if normal > 0 else None
        if not ln.active:
            cause = None
        elif shift is not None and abs(shift) >= BRIGHTNESS_SHIFT:
            cause = (f"el brillo de las capturas cambió {shift:+.0%} respecto al normal de la línea: "
                     "revisar la iluminación (SOP-CAM-002)")
        else:
            cause = "el brillo no ha cambiado: revisar cámara, posición del objeto o un lote de producto no dado de alta"
        return {
            "line_id": line_id, "active": ln.active, "unknown_rate": round(rate, 4), "window_samples": n,
            "total_samples": ln.seen, "raise_at": self.cfg.raise_at, "clear_at": self.cfg.clear_at,
            "brightness_change": None if shift is None else round(shift, 4), "probable_cause": cause,
            "times_raised": ln.raised,
            "effect": "los UNKNOWN se retienen para revisión humana en lugar de rechazarse" if ln.active else None,
        }
