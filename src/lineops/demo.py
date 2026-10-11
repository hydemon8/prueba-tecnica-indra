"""Simulador de capturas de una línea, solo para demostrar la alerta de captura.

En una planta, quien envía las capturas al servicio de visión es el controlador de la línea, con la cabecera
`X-Line-ID`. En esta demostración no hay línea física, así que este módulo hace de controlador: toma vistas de
referencia del catálogo, las envía como si fueran capturas y, en el escenario de fallo, las oscurece para imitar
una lámpara degradada. La alerta la decide el servicio de visión; aquí no se calcula nada.

Solo se puede llamar desde la API si `LINEOPS_DEMO_CONTROLS=true`.
"""

from __future__ import annotations

import io
from collections import Counter

from PIL import Image, ImageEnhance

from .tools.base import ToolError

OBJECTS = (74, 80, 57, 21, 85, 39, 40, 14)   # productos con ángulo bien observable: una captura limpia acaba en ACT
ANGLES = (0, 45, 90, 135, 180)
BATCH = 16
SCENARIOS = {
    # (capturas normales, capturas oscurecidas, factor de brillo)
    "lamp_fault": (40, 30, 0.70),   # una línea sana y después la lámpara pierde un 30 % de brillo
    "normal": (100, 0, 1.0),        # iluminación reparada: llena la ventana de capturas normales
}


def line_key(plant_id: str, line_id: str) -> str:
    """Identificador de la línea en el servicio de visión; incluye la planta para no mezclar líneas homónimas."""
    return f"{plant_id}-{line_id}"


def _darken(png: bytes, factor: float) -> bytes:
    out = io.BytesIO()
    ImageEnhance.Brightness(Image.open(io.BytesIO(png)).convert("RGB")).enhance(factor).save(out, "PNG")
    return out.getvalue()


def simulate_captures(vision, plant_id: str, line_id: str, scenario: str) -> dict:
    normal, dark, factor = SCENARIOS[scenario]
    views = [(o, a) for a in ANGLES for o in OBJECTS]
    cache: dict[tuple[int, int], bytes] = {}

    def view(i: int) -> bytes:
        key = views[i % len(views)]
        if key not in cache:
            png = vision.reference_png(*key)
            if png is None:
                raise ToolError("vision_unavailable", "el servicio de visión no entregó las vistas de referencia",
                                retryable=True)
            cache[key] = png
        return cache[key]

    captures = [(f"captura_{i:03d}.png", view(i)) for i in range(normal)]
    captures += [(f"captura_{normal + i:03d}.png", _darken(view(i), factor)) for i in range(dark)]
    decisions, orders, alert = Counter(), Counter(), None
    key = line_key(plant_id, line_id)
    for i in range(0, len(captures), BATCH):
        resp = vision.predict(captures[i:i + BATCH], top_k=1, line_id=key)
        alert = resp["line_alert"]
        for r in resp["results"]:
            decisions[r["decision"]] += 1
            orders[r["robot_command"]["action"]] += 1
    return {"line_id": line_id, "scenario": scenario, "captures_sent": len(captures), "decisions": dict(decisions),
            "robot_orders": dict(orders), "capture_alert": alert}
