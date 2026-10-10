"""Qué recibe el robot para cada decisión. Tabla fija: no la decide un LLM ni depende de la confianza.

El robot solo recibe un ángulo cuando la decisión es ACT. En cualquier otro caso recibe una orden que no
implica agarre, de modo que un fallo del modelo nunca se convierte en un movimiento con datos dudosos.
"""

from __future__ import annotations

BAD_CAPTURE = "BAD_CAPTURE"  # decisión del servicio: la imagen no pasa la validación de captura

ROBOT_ACTION = {
    "ACT": "PICK",  # agarrar compensando el giro
    "ANGLE_UNCERTIFIED": "SECOND_CAPTURE",  # girar 180 grados (o 2a cámara) y volver a estimar
    "REVIEW": "DIVERT_TO_REVIEW",  # desviar a la cola de revisión humana
    "UNKNOWN": "DIVERT_TO_REJECT",  # desviar al carril de rechazo
    BAD_CAPTURE: "RECAPTURE",  # repetir la captura; no mover el objeto
}


def robot_command(decision: str, object_id: int | None, angle_deg: float | None, hold_unknown: bool = False) -> dict:
    """`hold_unknown`: hay una alerta de captura activa en la línea; un UNKNOWN se retiene para revisión humana
    en lugar de rechazarse, porque lo más probable es que sea producto conocido mal capturado."""
    action = "DIVERT_TO_REVIEW" if hold_unknown and decision == "UNKNOWN" else ROBOT_ACTION[decision]
    act = action == "PICK"
    return {
        "action": action,
        "object_id": object_id if act else None,
        "angle_deg": angle_deg if act else None,
    }
