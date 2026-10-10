"""Ejecuta el set de evaluación y escribe reports/agent_eval.{json,md}.

    uv run --extra service --extra agent python -m lineops.evals.run            # todos los casos
    uv run --extra service --extra agent python -m lineops.evals.run rev- sec-  # solo los que empiezan así
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from dataclasses import asdict, replace

import yaml

from linevision.config import ROOT
from linevision.service.cli import load_env_file

from ..llm import build_provider
from ..settings import AgentSettings
from .harness import CaseResult, run_case

CASES, ASSETS, OUT = ROOT / "evals" / "cases.yaml", ROOT / "evals" / "assets", ROOT / "reports"


def _mark(ok: bool) -> str:
    return "sí" if ok else "**no**"


def _pct(xs: list[bool]) -> str:
    return f"{100 * sum(xs) / len(xs):.0f} % ({sum(xs)}/{len(xs)})" if xs else "—"


def report(results: list[CaseResult], model: str, settings: AgentSettings, elapsed_s: float) -> str:
    live = [r for r in results if not r.scripted]
    cost = sum(r.cost_usd for r in live)
    tokens = [r.input_tokens + r.output_tokens for r in live]
    lines = [
        "# Evaluación del asistente agéntico",
        "",
        f"Modelo: `{model}` · casos: {len(results)} ({sum(r.adverse for r in results)} adversos, "
        f"{sum(r.scripted for r in results)} con modelo guionizado) · duración: {elapsed_s / 60:.1f} min.",
        "",
        "Generado por `python -m lineops.evals.run` desde [`evals/cases.yaml`](../evals/cases.yaml). Cada caso corre "
        "sobre una planta recién sembrada, con el servicio de visión real, y se juzga con comprobaciones de código "
        "(tools y argumentos, estado final de la base y contenido de la respuesta). No hay juez LLM.",
        "",
        "## Resumen",
        "",
        "| Métrica | Resultado |",
        "|---|---|",
        f"| Éxito de la tarea | {_pct([r.success for r in results])} |",
        f"| Selección correcta de tools | {_pct([r.tools_ok for r in results])} |",
        f"| Argumentos correctos | {_pct([r.args_ok for r in results])} |",
        f"| Éxito en escenarios adversos | {_pct([r.success for r in results if r.adverse])} |",
        f"| Tokens por caso (mediana / máximo) | {statistics.median(tokens):.0f} / {max(tokens)} |" if tokens else "",
        f"| Costo estimado por caso (media) | ${cost / max(len(live), 1):.5f} |",
        f"| Costo estimado total | ${cost:.4f} |",
        f"| Latencia por caso (mediana / máximo) | {statistics.median(r.latency_s for r in live):.1f} s / "
        f"{max(r.latency_s for r in live):.1f} s |" if live else "",
        f"| Llamadas al LLM por caso (media) | {sum(r.llm_calls for r in live) / max(len(live), 1):.1f} |",
        "",
        f"Costo estimado con ${settings.price_in_per_mtok:.2f} por millón de tokens de entrada y "
        f"${settings.price_out_per_mtok:.2f} de salida (supuesto configurable; no es la tarifa verificada del "
        "proveedor). Los casos guionizados no llaman al LLM y no cuentan en tokens, costo ni latencia.",
        "",
        "## Por categoría",
        "",
        "| Categoría | Casos | Éxito | Tools | Argumentos |",
        "|---|---|---|---|---|",
    ]
    for cat in dict.fromkeys(r.category for r in results):
        rs = [r for r in results if r.category == cat]
        lines.append(f"| {cat} | {len(rs)} | {_pct([r.success for r in rs])} | {_pct([r.tools_ok for r in rs])} | "
                     f"{_pct([r.args_ok for r in rs])} |")
    lines += ["", "## Por caso", "",
              "| Caso | Qué prueba | Usuario | Adverso | Éxito | Tools | Args | Tools usadas | Tokens | Costo | Latencia |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        used = ", ".join(f"{s['tool']}→{s['outcome']}" for s in r.steps) or "—"
        lines.append(f"| `{r.id}` | {r.title} | {r.user} | {'sí' if r.adverse else ''} | {_mark(r.success)} | "
                     f"{_mark(r.tools_ok)} | {_mark(r.args_ok)} | {used} | "
                     f"{'guion' if r.scripted else r.input_tokens + r.output_tokens} | "
                     f"{'—' if r.scripted else f'${r.cost_usd:.5f}'} | {'—' if r.scripted else f'{r.latency_s} s'} |")
    failed = [r for r in results if not r.success]
    lines += ["", f"## Casos fallidos ({len(failed)})", ""]
    for r in failed:
        lines += [f"### `{r.id}` — {r.title}", "", "No cumplió:", *[f"- {c}" for c in r.failed_checks], "",
                  "Respuesta del asistente:", "", "> " + r.answer.replace("\n", "\n> ")[:1500], ""]
    if not failed:
        lines.append("Ninguno.")
    return "\n".join(line for line in lines if line is not None) + "\n"


def main() -> None:
    from fastapi.testclient import TestClient

    from linevision.service.app import create_app
    from linevision.service.settings import ServiceSettings

    load_env_file()
    filters = sys.argv[1:]
    cases = [c for c in yaml.safe_load(CASES.read_text(encoding="utf-8"))
             if not filters or any(c["id"].startswith(f) for f in filters)]
    settings = AgentSettings.from_env()
    llm = build_provider(settings)
    results, t0 = [], time.perf_counter()
    with TestClient(create_app(replace(ServiceSettings.from_env(), api_key=None, fault_injection=False))) as vision:
        for i, case in enumerate(cases, 1):
            r = run_case(case, llm, vision, ASSETS, settings)
            if r.stop_reason == "llm_error":  # cuota o caída del proveedor: no es un resultado del agente; se repite
                print(f"         proveedor de LLM no disponible en {case['id']}: se repite en 65 s", flush=True)
                time.sleep(65)
                r = run_case(case, llm, vision, ASSETS, settings)
            results.append(r)
            print(f"[{i:02d}/{len(cases)}] {'OK  ' if r.success else 'FALLA'} {r.id:34s} "
                  f"{', '.join(s['tool'] + '→' + s['outcome'] for s in r.steps) or '—'}", flush=True)
            for c in r.failed_checks:
                print(f"         ✗ {c}", flush=True)
    elapsed = time.perf_counter() - t0
    print(f"\néxito {sum(r.success for r in results)}/{len(results)} · tools {sum(r.tools_ok for r in results)}/{len(results)}"
          f" · costo ${sum(r.cost_usd for r in results):.4f} · {elapsed / 60:.1f} min")
    if not filters:  # solo una corrida completa reemplaza el reporte versionado
        OUT.mkdir(exist_ok=True)
        (OUT / "agent_eval.json").write_text(json.dumps(
            {"model": llm.model, "n_cases": len(results), "elapsed_s": round(elapsed, 1),
             "results": [asdict(r) for r in results]}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        (OUT / "agent_eval.md").write_text(report(results, llm.model, settings, elapsed), encoding="utf-8", newline="\n")
        print(f"reporte: {OUT / 'agent_eval.md'}")


if __name__ == "__main__":
    main()
