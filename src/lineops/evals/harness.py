"""Evaluación reproducible del agente: cada caso corre sobre una planta recién sembrada y se juzga con
criterios objetivos (tools usadas, argumentos, estado final de la base y contenido de la respuesta).

El servicio de visión se usa de verdad (el artefacto versionado, en memoria); los fallos de visión se
inyectan de forma determinista. No hay juez LLM: un caso pasa o no pasa por comprobaciones de código.
"""

from __future__ import annotations

import io
import re
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path

import httpx
import numpy as np
from PIL import Image

from ..llm import LLMProvider, ScriptedProvider, call, say
from ..plant.db import one
from ..policy import principal_for
from ..runtime import build
from ..settings import AgentSettings
from ..vision_client import VisionClient

EXECUTED = {"ok", "pending_approval"}


# ------------------------------------------------------------------ imágenes de los casos
def _png(arr: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr.astype(np.uint8)).save(buf, "PNG")
    return buf.getvalue()


def _blob(color, shift=0) -> np.ndarray:
    img = np.full((128, 128, 3), 20, np.uint8)
    img[40:90, 30 + shift:100 + shift] = color
    return img


def generated(kind: str, n: int = 1) -> list[tuple[str, bytes]]:
    """Imágenes sintéticas deterministas: objeto fuera de catálogo, captura negra o ruido."""
    rng = np.random.default_rng(7)
    make = {
        "unknown": lambda i: _blob((200, 40, 40), i % 20),
        "new_sku": lambda i: _blob((40, 60, 220), i % 20),
        "black": lambda i: np.zeros((128, 128, 3)),
        "noise": lambda i: rng.integers(0, 255, (128, 128, 3)),
    }[kind]
    return [(f"vista_{i:03d}.png", _png(make(i))) for i in range(n)]


# ------------------------------------------------------------------ LLM guionizados para dos casos
def scripted(kind: str) -> ScriptedProvider:
    if kind == "loop":  # un modelo que pide la misma tool indefinidamente
        return ScriptedProvider([call("get_line_status", line_id="L1")])
    if kind == "unknown_tool":  # un modelo que inventa una tool y argumentos
        return ScriptedProvider([call("delete_all_data", confirm=True), call("get_shift_metrics", line_id="L1", shift=9),
                                 say("No existe ninguna operación para borrar datos y no puedo hacerlo.")])
    raise ValueError(kind)


class FlakyVision(VisionClient):
    """Cliente de visión con fallos inyectados de forma determinista (5xx o timeout)."""

    def __init__(self, client: httpx.Client, fault: str | None, retries: int = 1):
        super().__init__("http://testserver", retries=retries, client=client)
        self.fault, self.attempts = fault, 0

    def _request(self, method, url, **kw):
        if self.fault and url == "/v1/predict":
            real = self.http.request

            def failing(*a, **k):
                self.attempts += 1
                if self.fault == "timeout":
                    raise httpx.ReadTimeout("timeout inyectado")
                return httpx.Response(503, json={"code": "service_unavailable", "message": "fallo inyectado"})
            self.http.request = failing
            try:
                return super()._request(method, url, **kw)
            finally:
                self.http.request = real
        return super()._request(method, url, **kw)


# ------------------------------------------------------------------ comprobaciones
def _match(expected, actual) -> bool:
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        try:
            return abs(float(actual) - float(expected)) < 1e-6
        except (TypeError, ValueError):
            return False
    if isinstance(expected, str):
        return str(actual).strip().lower() == expected.strip().lower()
    return expected == actual


def _args_ok(want: dict, got: dict) -> bool:
    for k, v in (want or {}).items():
        if k.startswith("len:"):
            if len(got.get(k[4:], [])) != v:
                return False
        elif not _match(v, got.get(k)):
            return False
    return True


@dataclass
class Checks:
    passed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    tools_ok: bool = True
    args_ok: bool = True

    def add(self, ok: bool, label: str, kind: str = "") -> None:
        (self.passed if ok else self.failed).append(label)
        if not ok and kind == "tools":
            self.tools_ok = False
        if not ok and kind == "args":
            self.args_ok = False


def evaluate(expect: dict, steps: list, answer: str, stop_reason: str, con) -> Checks:
    c = Checks()
    executed = [s for s in steps if s.outcome in EXECUTED]
    for want in expect.get("tools", []):
        outcome = want.get("outcome")
        same = [s for s in steps if s.tool == want["name"] and (s.outcome == outcome if outcome else s.outcome in EXECUTED)]
        c.add(bool(same), f"usa {want['name']}" + (f" → {outcome}" if outcome else ""), "tools")
        if same and want.get("args"):
            c.add(any(_args_ok(want["args"], s.args) for s in same), f"argumentos de {want['name']}: {want['args']}", "args")
    if "tools_any" in expect:
        c.add(any(s.tool in expect["tools_any"] for s in executed), f"usa alguna de {expect['tools_any']}", "tools")
    for name in expect.get("forbidden", []):
        c.add(not any(s.tool == name for s in executed), f"no ejecuta {name}", "tools")
    for name, limit in expect.get("max_calls", {}).items():
        c.add(sum(s.tool == name for s in executed) <= limit, f"{name} se ejecuta como máximo {limit} veces", "tools")
    for code in expect.get("outcomes", []):
        c.add(any(s.outcome == code for s in steps), f"aparece el resultado '{code}'")
    if "no_tools" in expect:
        c.add(not executed, "no ejecuta ninguna tool", "tools")
    for pattern in expect.get("answer_all", []):
        c.add(re.search(pattern, answer, re.IGNORECASE | re.DOTALL) is not None, f"la respuesta contiene /{pattern}/")
    if "answer_any" in expect:
        c.add(any(re.search(p, answer, re.IGNORECASE | re.DOTALL) for p in expect["answer_any"]),
              f"la respuesta contiene alguna de {expect['answer_any']}")
    for pattern in expect.get("answer_none", []):
        c.add(re.search(pattern, answer, re.IGNORECASE | re.DOTALL) is None, f"la respuesta no contiene /{pattern}/")
    for check in expect.get("state", []):
        row = one(con, check["sql"])
        value = next(iter(row.values())) if row else None
        c.add(_match(check["equals"], value), f"estado: {check['sql']} = {check['equals']} (obtenido: {value})")
    if "stop_reason" in expect:
        c.add(stop_reason in expect["stop_reason"], f"termina por {expect['stop_reason']} (obtenido: {stop_reason})")
    if "any_of" in expect:  # basta con que se cumpla una de las alternativas completas
        options = [evaluate(alt, steps, answer, stop_reason, con) for alt in expect["any_of"]]
        best = min(options, key=lambda o: len(o.failed))
        c.add(not best.failed, "cumple alguna alternativa: " + " | ".join("; ".join(o.passed + [f"✗ {f}" for f in o.failed]) for o in options))
        c.tools_ok &= best.tools_ok
        c.args_ok &= best.args_ok
    return c


# ------------------------------------------------------------------ ejecución de un caso
@dataclass
class CaseResult:
    id: str
    title: str
    category: str
    adverse: bool
    user: str
    scripted: bool
    success: bool
    tools_ok: bool
    args_ok: bool
    failed_checks: list[str]
    passed_checks: list[str]
    steps: list[dict]
    answer: str
    stop_reason: str
    llm_calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_s: float


def run_case(case: dict, llm: LLMProvider, vision_http: httpx.Client, assets: Path, settings: AgentSettings) -> CaseResult:
    tmp = Path(tempfile.mkdtemp(prefix="lineops-eval-"))
    cfg = replace(settings, plant_db=tmp / "plant.db", uploads_dir=tmp / "uploads")
    provider = scripted(case["scripted"]) if case.get("scripted") else llm
    rt = build(cfg, provider, FlakyVision(vision_http, case.get("vision_fault")))
    for sql in case.get("setup_sql", []):
        rt.con.execute(sql)
    plant = one(rt.con, "SELECT plant_id FROM users WHERE user_id=?", (case["user"],))["plant_id"]
    principal = principal_for(rt.con, case["user"], rt.sessions.create(case["user"], plant, rt.now))
    steps, answer, stop = [], "", ""
    totals = {"llm_calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "latency_s": 0.0}
    for turn in case["turns"]:
        files = [(name, (assets / name).read_bytes()) for name in turn.get("attach", [])]
        if "generate" in turn:
            files += generated(turn["generate"]["kind"], turn["generate"].get("n", 1))
        attachments = rt.images.save_batch(principal, files, rt.now) if files else None
        r = rt.agent.run_turn(principal, turn["say"], attachments)
        steps += r.steps
        answer, stop = r.text, r.stop_reason
        totals["llm_calls"] += r.usage.llm_calls
        totals["input_tokens"] += r.usage.input_tokens
        totals["output_tokens"] += r.usage.output_tokens
        totals["cost_usd"] += r.cost_usd
        totals["latency_s"] += r.latency_s
    checks = evaluate(case["expect"], steps, answer, stop, rt.con)
    rt.con.close()
    return CaseResult(
        case["id"], case["title"], case["category"], bool(case.get("adverse")), case["user"], bool(case.get("scripted")),
        not checks.failed, checks.tools_ok, checks.args_ok, checks.failed, checks.passed,
        [{"tool": s.tool, "args": s.args, "outcome": s.outcome} for s in steps], answer, stop,
        totals["llm_calls"], totals["input_tokens"], totals["output_tokens"], round(totals["cost_usd"], 6),
        round(totals["latency_s"], 2))
