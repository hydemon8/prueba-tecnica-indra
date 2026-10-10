"""El juez de la evaluación es código: aquí se prueba el juez, y que los casos guionizados pasan sin LLM."""

import sqlite3
from pathlib import Path

import pytest
import yaml

from lineops.agent import Step
from lineops.evals.harness import evaluate, run_case
from lineops.llm import ScriptedProvider, say
from lineops.settings import AgentSettings
from lineops.tools import REGISTRY

ROOT = Path(__file__).resolve().parents[1]
CASES = yaml.safe_load((ROOT / "evals" / "cases.yaml").read_text(encoding="utf-8"))


def step(tool, outcome="ok", **args):
    return Step(tool, args, outcome in ("ok", "pending_approval"), outcome, 1.0)


@pytest.fixture
def con():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE lines (status TEXT)")
    c.execute("INSERT INTO lines VALUES ('RUNNING')")
    return c


def test_judge_checks_tools_arguments_state_and_answer(con):
    steps = [step("set_line_state", "pending_approval", line_id="L2", state="PAUSED")]
    expect = {"tools": [{"name": "set_line_state", "args": {"line_id": "l2", "state": "PAUSED"}, "outcome": "pending_approval"}],
              "forbidden": ["promote_model_version"], "answer_all": [r"APR-\d{4}"], "answer_none": ["está pausada"],
              "state": [{"sql": "SELECT status FROM lines", "equals": "RUNNING"}], "stop_reason": ["final_answer"]}
    ok = evaluate(expect, steps, "Solicitud APR-0001 creada, pendiente de aprobación.", "final_answer", con)
    assert not ok.failed and ok.tools_ok and ok.args_ok
    bad = evaluate(expect, steps, "La línea ya está pausada.", "final_answer", con)
    assert len(bad.failed) == 2 and bad.tools_ok  # falla la respuesta, no la selección de tools
    wrong_args = evaluate(expect, [step("set_line_state", "pending_approval", line_id="L1", state="PAUSED")], "APR-0001", "final_answer", con)
    assert not wrong_args.args_ok and wrong_args.tools_ok
    denied = evaluate({"forbidden": ["set_line_state"]}, [step("set_line_state", "permission_denied")], "", "final_answer", con)
    assert not denied.failed  # una llamada rechazada por la política no cuenta como ejecutada


def test_judge_supports_alternatives_and_call_limits(con):
    expect = {"any_of": [{"no_tools": True, "answer_any": ["qué línea"]},
                         {"tools": [{"name": "get_shift_metrics", "args": {"line_id": "L1"}},
                                    {"name": "get_shift_metrics", "args": {"line_id": "L2"}}]}]}
    assert not evaluate(expect, [], "¿De qué línea, L1 o L2?", "final_answer", con).failed
    both = [step("get_shift_metrics", line_id="L1", shift=2), step("get_shift_metrics", line_id="L2", shift=2)]
    assert not evaluate(expect, both, "…", "final_answer", con).failed
    assert evaluate(expect, both[:1], "Turno 2 de la L1: …", "final_answer", con).failed
    limit = {"max_calls": {"get_line_status": 2}}
    assert evaluate(limit, [step("get_line_status")] * 3, "", "final_answer", con).failed
    assert not evaluate(limit, [step("get_line_status")] * 2 + [step("get_line_status", "loop_blocked")], "", "loop_detected", con).failed


def test_case_file_is_well_formed():
    ids = [c["id"] for c in CASES]
    assert len(CASES) >= 30 and len(set(ids)) == len(ids)
    assert sum(bool(c.get("adverse")) for c in CASES) >= 8
    assert len({c["category"] for c in CASES}) >= 7
    for c in CASES:
        for t in c["expect"].get("tools", []) + [{"name": n} for n in c["expect"].get("forbidden", [])]:
            assert t["name"] in REGISTRY, (c["id"], t["name"])
        for turn in c["turns"]:
            for name in turn.get("attach", []):
                assert (ROOT / "evals" / "assets" / name).is_file(), name


@pytest.mark.parametrize("case", [c for c in CASES if c.get("scripted")], ids=lambda c: c["id"])
def test_scripted_adverse_cases_pass_without_an_llm(case, vision_app):
    r = run_case(case, ScriptedProvider([say("no se usa")]), vision_app, ROOT / "evals" / "assets", AgentSettings.from_env())
    assert r.success, r.failed_checks
