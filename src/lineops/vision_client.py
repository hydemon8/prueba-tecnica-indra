"""Cliente HTTP del servicio de visión. El asistente usa el modelo solo a través de esta API.

Plazo corto y reintentos acotados: si el servicio no responde, la tool devuelve un error estructurado y el
agente lo comunica; nunca inventa un resultado.
"""

from __future__ import annotations

import time
import uuid

import httpx

from .tools.base import ToolError


class VisionClient:
    def __init__(self, base_url: str, api_key: str | None = None, timeout_s: float = 4.0, retries: int = 1,
                 client: httpx.Client | None = None):
        headers = {"X-API-Key": api_key} if api_key else {}
        # `client` permite inyectar un cliente en pruebas (por ejemplo, contra la app en memoria)
        self.http = client or httpx.Client(base_url=base_url, headers=headers, timeout=timeout_s)
        self.retries = retries
        self.base_url = base_url

    def _request(self, method: str, url: str, headers: dict | None = None, **kw) -> dict:
        request_id = uuid.uuid4().hex
        last = "sin respuesta"
        for attempt in range(self.retries + 1):
            try:
                r = self.http.request(method, url, headers={"X-Request-ID": request_id, **(headers or {})}, **kw)
            except httpx.TimeoutException:
                last = "timeout"
            except httpx.HTTPError as e:
                last = f"error de conexión ({type(e).__name__})"
            else:
                if r.status_code < 500:
                    if r.status_code >= 400:
                        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                        raise ToolError("vision_rejected", body.get("message", f"HTTP {r.status_code}"),
                                        status=r.status_code, request_id=request_id)
                    return r.json()
                last = f"HTTP {r.status_code}"
            if attempt < self.retries:
                time.sleep(0.3 * (attempt + 1))
        raise ToolError("vision_unavailable",
                        f"el servicio de visión no respondió ({last}) tras {self.retries + 1} intentos",
                        retryable=True, request_id=request_id)

    def predict(self, files: list[tuple[str, bytes]], top_k: int = 3, line_id: str | None = None) -> dict:
        """`line_id` solo lo envía quien hace de controlador de línea: sus capturas cuentan para la alerta."""
        payload = [("images", (name, data, "image/png")) for name, data in files]
        headers = {"X-Line-ID": line_id} if line_id else None
        return self._request("POST", "/v1/predict", headers=headers, params={"top_k": top_k}, files=payload)

    def line_alert(self, line_id: str) -> dict:
        """Estado de la alerta de captura de una línea (regla determinista del servicio de visión)."""
        return self._request("GET", f"/v1/lines/{line_id}/monitor")

    def model_info(self) -> dict:
        return self._request("GET", "/v1/model")

    def reference_url(self, object_id: int, angle_deg: float) -> str:
        """Ruta relativa en la API del asistente, que hace de intermediario: el navegador no ve el servicio de visión."""
        return f"/api/reference/{object_id}/{int(angle_deg)}"

    def reference_png(self, object_id: int, angle_deg: int) -> bytes | None:
        try:
            r = self.http.get(f"/v1/reference/{object_id}/{angle_deg}")
        except httpx.HTTPError:
            return None
        return r.content if r.status_code == 200 else None
