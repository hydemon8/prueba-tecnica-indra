"""Capa de proveedor de LLM. El agente habla con una interfaz neutra; cambiar de proveedor no toca el bucle.

Mensajes neutros:
  {"role": "user", "text": str}
  {"role": "assistant", "text": str, "tool_calls": [ToolCall], "raw": <opaco del proveedor>}
  {"role": "tool", "results": [{"id", "name", "result": dict}]}
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0  # incluye los tokens de razonamiento, que se facturan como salida
    llm_calls: int = 0

    def add(self, other: Usage) -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.llm_calls += other.llm_calls

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[ToolCall]
    usage: Usage
    raw: Any = None
    finish_reason: str = ""


class LLMError(RuntimeError):
    pass


class LLMProvider(Protocol):
    model: str

    def generate(self, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse: ...


# ------------------------------------------------------------------ Gemini
_TYPES = {"string": "STRING", "integer": "INTEGER", "number": "NUMBER", "boolean": "BOOLEAN", "array": "ARRAY",
          "object": "OBJECT"}


def to_gemini_schema(schema: dict) -> dict:
    """Subconjunto de JSON Schema que acepta Gemini. Las restricciones finas (patrones, rangos, enteros
    enumerados) se describen en texto: quien las hace cumplir es la validación de la capa de política."""
    out: dict = {"type": _TYPES[schema.get("type", "string")]}
    hints = []
    if "enum" in schema:
        if schema.get("type") == "string":
            out["enum"] = list(schema["enum"])
        else:
            hints.append("valores permitidos: " + ", ".join(map(str, schema["enum"])))
    for key, label in (("minimum", "mínimo"), ("maximum", "máximo"), ("exclusiveMaximum", "menor que"),
                       ("exclusiveMinimum", "mayor que"), ("maxItems", "máximo de elementos")):
        if key in schema:
            hints.append(f"{label} {schema[key]}")
    desc = schema.get("description", "")
    if hints:
        desc = f"{desc} ({'; '.join(hints)})".strip()
    if desc:
        out["description"] = desc
    if out["type"] == "ARRAY":
        out["items"] = to_gemini_schema(schema.get("items", {"type": "string"}))
    if out["type"] == "OBJECT":
        out["properties"] = {k: to_gemini_schema(v) for k, v in schema.get("properties", {}).items()}
        if schema.get("required"):
            out["required"] = list(schema["required"])
    return out


class GeminiProvider:
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, api_key: str, model: str, timeout_s: float = 60, retries: int = 3,
                 client: httpx.Client | None = None):
        if not api_key:
            raise LLMError("falta GEMINI_API_KEY")
        self.model, self.retries = model, retries
        # la clave viaja en una cabecera, nunca en la URL
        self.http = client or httpx.Client(timeout=timeout_s, headers={"x-goog-api-key": api_key})

    @staticmethod
    def _contents(messages: list[dict]) -> list[dict]:
        out = []
        for m in messages:
            if m["role"] == "user":
                out.append({"role": "user", "parts": [{"text": m["text"]}]})
            elif m["role"] == "assistant":
                parts = m.get("raw")  # se devuelven las partes originales (incluyen la firma de razonamiento)
                if not parts:
                    parts = [{"text": m["text"]}] if m.get("text") else []
                    parts += [{"functionCall": {"name": c["name"], "args": c["args"]}} for c in m.get("tool_calls", [])]
                out.append({"role": "model", "parts": parts})
            else:
                out.append({"role": "user", "parts": [
                    {"functionResponse": {"name": r["name"], "id": r["id"], "response": r["result"]}}
                    for r in m["results"]]})
        return out

    def generate(self, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": self._contents(messages),
            "generationConfig": {"temperature": 0, "maxOutputTokens": 2048},
        }
        if tools:
            body["tools"] = [{"functionDeclarations": [
                {"name": t["name"], "description": t["description"], "parameters": to_gemini_schema(t["schema"])}
                if t["schema"].get("properties") else {"name": t["name"], "description": t["description"]}
                for t in tools]}]
        last = ""
        for attempt in range(self.retries + 1):
            try:
                r = self.http.post(self.URL.format(model=self.model), json=body)
            except httpx.HTTPError as e:
                last = f"error de red ({type(e).__name__})"
            else:
                if r.status_code == 200:
                    return self._parse(r.json())
                last = f"HTTP {r.status_code}: {r.text[:300]}"
                if r.status_code not in (429, 500, 502, 503, 504):
                    break
            if attempt < self.retries:
                time.sleep(min(2 ** attempt * 2, 20))
        raise LLMError(f"el proveedor de LLM falló: {last}")

    @staticmethod
    def _parse(data: dict) -> LLMResponse:
        cand = (data.get("candidates") or [{}])[0]
        parts = cand.get("content", {}).get("parts", []) or []
        text = "".join(p["text"] for p in parts if "text" in p and not p.get("thought"))
        calls = [ToolCall(p["functionCall"].get("id") or f"call_{i}", p["functionCall"]["name"],
                          dict(p["functionCall"].get("args") or {}))
                 for i, p in enumerate(parts) if "functionCall" in p]
        u = data.get("usageMetadata", {})
        usage = Usage(u.get("promptTokenCount", 0),
                      u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0), 1)
        return LLMResponse(text.strip(), calls, usage, parts, cand.get("finishReason", ""))


# ------------------------------------------------------------------ proveedor guionizado (pruebas sin red)
@dataclass
class ScriptedProvider:
    """Devuelve respuestas predefinidas. Permite probar el bucle (límites, loops, errores) sin LLM."""

    script: list[LLMResponse | Exception]
    model: str = "scripted"
    calls: list[dict] = field(default_factory=list)

    def generate(self, system: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        self.calls.append({"system": system, "messages": [dict(m) for m in messages], "tools": [t["name"] for t in tools]})
        step = self.script[min(len(self.calls) - 1, len(self.script) - 1)]  # el último paso se repite indefinidamente
        if isinstance(step, Exception):
            raise step
        return LLMResponse(step.text, [ToolCall(c.id, c.name, dict(c.args)) for c in step.tool_calls],
                           Usage(step.usage.input_tokens, step.usage.output_tokens, 1), None, step.finish_reason)


def say(text: str, tokens: tuple[int, int] = (100, 20)) -> LLMResponse:
    return LLMResponse(text, [], Usage(*tokens, 1))


def call(name: str, tokens: tuple[int, int] = (100, 20), **args) -> LLMResponse:
    return LLMResponse("", [ToolCall(f"c-{name}", name, args)], Usage(*tokens, 1))


def build_provider(settings) -> LLMProvider:
    if settings.llm_provider == "gemini":
        return GeminiProvider(settings.gemini_api_key or "", settings.llm_model)
    raise LLMError(f"proveedor de LLM no soportado: {settings.llm_provider}")
