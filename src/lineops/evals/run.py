"""Ejecuta el set de evaluación y escribe reports/agent_eval.{json,md}.

    uv run --extra service --extra agent python -m lineops.evals.run                # todos los casos, 1 corrida
    uv run --extra service --extra agent python -m lineops.evals.run --repeats 5    # 5 corridas de cada caso
    uv run --extra service --extra agent python -m lineops.evals.run rev- sec-      # solo los que empiezan así

El modelo no es determinista ni con temperatura 0: con `--repeats` cada caso se repite sobre una planta
recién sembrada y se reporta en cuántas corridas pasa.
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


def _rate(xs: list[bool]) -> str:
    return f"{100 * sum(xs) / len(xs):.0f} % ({sum(xs)}/{len(xs)})" if xs else "—"


def _frac(xs: list[bool]) -> str:
    text = f"{sum(xs)}/{len(xs)}"
    return text if all(xs) else f"**{text}**"


def report(runs: dict[str, list[CaseResult]], model: str, settings: AgentSettings, elapsed_s: float, skipped: int) -> str:
    """`runs`: id de caso -> resultados válidos de cada corrida (sin las anuladas por el proveedor)."""
    flat = [r for rs in runs.values() for r in rs]
    live = [r for r in flat if not r.scripted]
    n_rep = max(len(rs) for rs in runs.values())
    first = {cid: rs[0] for cid, rs in runs.items()}
    always = [cid for cid, rs in runs.items() if all(r.success for r in rs)]
    never = [cid for cid, rs in runs.items() if not any(r.success for r in rs)]
    flaky = [cid for cid in runs if cid not in always and cid not in never]
    per_run = [sum(rs[i].success for rs in runs.values() if len(rs) > i) / sum(len(rs) > i for rs in runs.values())
               for i in range(n_rep)]
    cost = sum(r.cost_usd for r in live)
    tokens = [r.input_tokens + r.output_tokens for r in live]
    lines = [
        "# Evaluación del asistente agéntico",
        "",
        f"Modelo: `{model}` · {len(runs)} casos ({sum(r.adverse for r in first.values())} adversos, "
        f"{sum(r.scripted for r in first.values())} con modelo guionizado) × {n_rep} corridas lanzadas = "
        f"{len(flat)} ejecuciones válidas (entre {min(len(rs) for rs in runs.values())} y "
        f"{max(len(rs) for rs in runs.values())} por caso) · duración: {elapsed_s / 60:.1f} min.",
        "",
        "Generado por `python -m lineops.evals.run` desde [`evals/cases.yaml`](../evals/cases.yaml). Cada ejecución "
        "corre sobre una planta recién sembrada, con el servicio de visión real, y se juzga con comprobaciones de "
        "código (tools y argumentos, estado final de la base y contenido de la respuesta). No hay juez LLM.",
        "",
        "## Resumen",
        "",
        "| Métrica | Resultado |",
        "|---|---|",
        f"| Éxito de la tarea (sobre todas las ejecuciones) | {_rate([r.success for r in flat])} |",
        f"| Éxito por corrida (mínimo – máximo) | {100 * min(per_run):.0f} % – {100 * max(per_run):.0f} % |",
        f"| Casos que pasan en todas las corridas | {len(always)} de {len(runs)} |",
        f"| Casos inestables (pasan en algunas) | {len(flaky)} |",
        f"| Casos que no pasan en ninguna | {len(never)} |",
        f"| Selección correcta de tools | {_rate([r.tools_ok for r in flat])} |",
        f"| Argumentos correctos | {_rate([r.args_ok for r in flat])} |",
        f"| Éxito en escenarios adversos | {_rate([r.success for r in flat if r.adverse])} |",
        f"| Tokens por ejecución (mediana / máximo) | {statistics.median(tokens):.0f} / {max(tokens)} |",
        f"| Llamadas al LLM por ejecución (media) | {sum(r.llm_calls for r in live) / len(live):.1f} |",
        f"| Costo estimado por ejecución (media) | ${cost / len(live):.5f} |",
        f"| Costo estimado total | ${cost:.4f} |",
        f"| Latencia por ejecución (mediana) | {statistics.median(r.latency_s for r in live):.1f} s |",
        f"| Ejecuciones anuladas por fallo del proveedor de LLM | {skipped} |",
        "",
        f"Costo estimado con ${settings.price_in_per_mtok:.2f} por millón de tokens de entrada y "
        f"${settings.price_out_per_mtok:.2f} de salida (supuesto configurable; no es la tarifa verificada del "
        "proveedor). Los casos guionizados no llaman al LLM y no cuentan en tokens, costo ni latencia. La latencia "
        f"incluye la espera del límite de ritmo ({settings.llm_rpm or 'sin límite de'} peticiones por minuto). Las "
        "ejecuciones anuladas (cuota o caída del proveedor tras un reintento) no cuentan en ninguna métrica.",
        "",
        "## Por categoría",
        "",
        "| Categoría | Casos | Éxito | Tools | Argumentos |",
        "|---|---|---|---|---|",
    ]
    for cat in dict.fromkeys(r.category for r in first.values()):
        rs = [r for r in flat if r.category == cat]
        lines.append(f"| {cat} | {sum(r.category == cat for r in first.values())} | {_rate([r.success for r in rs])} | "
                     f"{_rate([r.tools_ok for r in rs])} | {_rate([r.args_ok for r in rs])} |")
    lines += ["", "## Por caso", "",
              "Éxito, tools y argumentos: corridas correctas sobre corridas válidas. Tools usadas: las de la primera corrida.",
              "",
              "| Caso | Qué prueba | Usuario | Adverso | Éxito | Tools | Args | Tools usadas (corrida 1) | Tokens (media) | Costo (media) |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for cid, rs in runs.items():
        r = rs[0]
        used = ", ".join(f"{s['tool']}→{s['outcome']}" for s in r.steps) or "—"
        tok = "guion" if r.scripted else f"{statistics.mean(x.input_tokens + x.output_tokens for x in rs):.0f}"
        usd = "—" if r.scripted else f"${statistics.mean(x.cost_usd for x in rs):.5f}"
        lines.append(f"| `{cid}` | {r.title} | {r.user} | {'sí' if r.adverse else ''} | {_frac([x.success for x in rs])} | "
                     f"{_frac([x.tools_ok for x in rs])} | {_frac([x.args_ok for x in rs])} | {used} | {tok} | {usd} |")
    lines += ["", f"## Casos con fallos ({len(flaky) + len(never)})", ""]
    for cid in never + flaky:
        rs = runs[cid]
        bad = [r for r in rs if not r.success]
        reasons: dict[str, int] = {}
        for r in bad:
            for c in r.failed_checks:
                reasons[c] = reasons.get(c, 0) + 1
        lines += [f"### `{cid}` — {rs[0].title}", "",
                  f"Pasa en {sum(r.success for r in rs)} de {len(rs)} corridas. Comprobaciones incumplidas:", "",
                  *[f"- {c} ({n} {'vez' if n == 1 else 'veces'})" for c, n in sorted(reasons.items(), key=lambda x: -x[1])],
                  "", "Respuesta del asistente en una corrida fallida:", "",
                  "> " + bad[0].answer.replace("\n", "\n> ")[:1200], ""]
    if not flaky and not never:
        lines.append("Ninguno.")
    return "\n".join(lines) + "\n"


def main() -> None:
    from fastapi.testclient import TestClient

    from linevision.service.app import create_app
    from linevision.service.settings import ServiceSettings

    load_env_file()
    args = sys.argv[1:]
    if "--report-only" in args:  # regenera el Markdown desde el JSON guardado, sin llamar al LLM
        d = json.loads((OUT / "agent_eval.json").read_text(encoding="utf-8"))
        runs = {cid: [CaseResult(**r) for r in rs] for cid, rs in d["runs"].items()}
        (OUT / "agent_eval.md").write_text(report(runs, d["model"], AgentSettings.from_env(), d["elapsed_s"], d["skipped_runs"]),
                                           encoding="utf-8", newline="\n")
        return
    repeats = int(args.pop(args.index("--repeats") + 1)) if "--repeats" in args else 1
    filters = [a for a in args if a != "--repeats"]
    cases = [c for c in yaml.safe_load(CASES.read_text(encoding="utf-8"))
             if not filters or any(c["id"].startswith(f) for f in filters)]
    settings = AgentSettings.from_env()
    llm = build_provider(settings)
    runs: dict[str, list[CaseResult]] = {c["id"]: [] for c in cases}
    skipped, t0 = 0, time.perf_counter()
    with TestClient(create_app(replace(ServiceSettings.from_env(), api_key=None, fault_injection=False))) as vision:
        for rep in range(1, repeats + 1):
            for i, case in enumerate(cases, 1):
                r = run_case(case, llm, vision, ASSETS, settings)
                if r.stop_reason == "llm_error":  # cuota o caída del proveedor: no es un resultado del agente
                    print(f"         proveedor de LLM no disponible en {case['id']}: se repite en 65 s", flush=True)
                    time.sleep(65)
                    r = run_case(case, llm, vision, ASSETS, settings)
                if r.stop_reason == "llm_error":
                    skipped += 1
                    print(f"[{rep}/{repeats} {i:02d}/{len(cases)}] ANULADO {r.id}", flush=True)
                    continue
                runs[r.id].append(r)
                print(f"[{rep}/{repeats} {i:02d}/{len(cases)}] {'OK  ' if r.success else 'FALLA'} {r.id:34s} "
                      f"{', '.join(s['tool'] + '→' + s['outcome'] for s in r.steps) or '—'}", flush=True)
                for c in r.failed_checks:
                    print(f"         ✗ {c}", flush=True)
    elapsed = time.perf_counter() - t0
    runs = {cid: rs for cid, rs in runs.items() if rs}
    flat = [r for rs in runs.values() for r in rs]
    print(f"\néxito {sum(r.success for r in flat)}/{len(flat)} · tools {sum(r.tools_ok for r in flat)}/{len(flat)}"
          f" · anuladas {skipped} · costo ${sum(r.cost_usd for r in flat):.4f} · {elapsed / 60:.1f} min")
    if not filters and runs:  # solo una corrida completa reemplaza el reporte versionado
        OUT.mkdir(exist_ok=True)
        (OUT / "agent_eval.json").write_text(json.dumps(
            {"model": llm.model, "n_cases": len(runs), "repeats": repeats, "skipped_runs": skipped,
             "elapsed_s": round(elapsed, 1), "runs": {cid: [asdict(r) for r in rs] for cid, rs in runs.items()}},
            indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        (OUT / "agent_eval.md").write_text(report(runs, llm.model, settings, elapsed, skipped), encoding="utf-8", newline="\n")
        print(f"reporte: {OUT / 'agent_eval.md'}")


if __name__ == "__main__":
    main()
