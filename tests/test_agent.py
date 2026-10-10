"""Bucle del agente con un LLM guionizado: límites, terminación y memoria, sin red ni costo."""

from dataclasses import replace

import pytest
from conftest import blob, png

from lineops.llm import LLMError, ScriptedProvider, call, say, to_gemini_schema
from lineops.plant.db import one, rows
from lineops.policy import principal_for
from lineops.runtime import build
from lineops.tools import REGISTRY, ToolError
from lineops.vision_client import VisionClient


@pytest.fixture
def make(tmp_path, vision_app):
    def _make(script, **overrides):
        from lineops.settings import AgentSettings
        settings = replace(AgentSettings.from_env(), plant_db=tmp_path / "plant.db", uploads_dir=tmp_path / "up", **overrides)
        vision_app.post("/admin/fault", json={"mode": "none"})
        rt = build(settings, ScriptedProvider(script), VisionClient("http://testserver", client=vision_app))

        def user(user_id):
            sid = rt.sessions.create(user_id, one(rt.con, "SELECT plant_id FROM users WHERE user_id=?", (user_id,))["plant_id"], rt.now)
            return principal_for(rt.con, user_id, sid)
        rt.user = user
        return rt
    return _make


def test_tool_then_answer_and_history_carries_only_text(make):
    rt = make([call("get_line_status", line_id="L1"), say("La línea L1 está en marcha."), say("Sigue en marcha.")])
    sup = rt.user("u-sup-01")
    r = rt.agent.run_turn(sup, "¿cómo está la línea?")
    assert r.stop_reason == "final_answer" and r.text == "La línea L1 está en marcha."
    assert [(s.tool, s.outcome) for s in r.steps] == [("get_line_status", "ok")]
    assert r.usage.llm_calls == 2 and r.usage.total == 240 and r.cost_usd > 0
    tool_msg = rt.agent.llm.calls[1]["messages"][-1]
    assert tool_msg["role"] == "tool" and tool_msg["results"][0]["result"]["data"]["line"]["status"] == "RUNNING"
    rt.agent.run_turn(sup, "¿y ahora?")
    history = rt.agent.llm.calls[2]["messages"]
    assert [m["role"] for m in history] == ["user", "assistant", "user"]
    assert "tools usadas en este turno: get_line_status→ok" in history[1]["text"]
    assert "Laura Pérez (supervisor de turno)" in rt.agent.llm.calls[0]["system"]


def test_model_only_sees_tools_its_role_may_use(make):
    rt = make([say("hola")])
    op, ml = rt.user("u-op-01"), rt.user("u-ml-01")
    rt.agent.run_turn(op, "hola")
    offered = set(rt.agent.llm.calls[0]["tools"])
    assert offered == {"inspect_images", "search_procedures", "get_line_status"}
    assert "promote_model_version" in {t["name"] for t in rt.agent.tools_for(ml)}


def test_agentic_loop_is_cut_and_tool_runs_at_most_twice(make):
    rt = make([call("get_line_status", line_id="L1")])  # el modelo pide lo mismo indefinidamente
    r = rt.agent.run_turn(rt.user("u-sup-01"), "estado")
    assert r.stop_reason == "loop_detected" and "repitiendo" in r.text
    assert [s.outcome for s in r.steps] == ["ok", "ok", "loop_blocked", "loop_blocked"]
    assert one(rt.con, "SELECT COUNT(*) AS n FROM audit_log WHERE tool='get_line_status'")["n"] == 2
    assert r.usage.llm_calls == 4


def test_hard_limits_steps_tool_calls_and_tokens(make):
    varied = [call("get_shift_metrics", line_id="L1", shift=s) for s in (1, 2, 3)] + [call("get_line_status", line_id="L1")]
    rt = make(varied, max_steps=3)
    r = rt.agent.run_turn(rt.user("u-sup-01"), "todo")
    assert r.stop_reason == "max_steps" and len(r.steps) == 3 and "máximo de pasos" in r.text
    rt = make(varied, max_tool_calls=2)
    r = rt.agent.run_turn(rt.user("u-sup-01"), "todo")
    assert r.stop_reason == "max_tool_calls" and len(r.steps) == 2
    rt = make([call("get_line_status", tokens=(40_000, 10), line_id="L1"), call("get_shift_metrics", tokens=(40_000, 10), line_id="L1", shift=1)])
    r = rt.agent.run_turn(rt.user("u-sup-01"), "todo")
    assert r.stop_reason == "token_budget" and r.usage.llm_calls == 2


def test_invalid_tool_and_arguments_go_back_to_the_model_as_errors(make):
    rt = make([call("apagar_planta"), call("get_shift_metrics", line_id="L1", shift=9), say("No puedo hacer eso.")])
    r = rt.agent.run_turn(rt.user("u-sup-01"), "apaga la planta")
    assert [s.outcome for s in r.steps] == ["unknown_tool", "invalid_arguments"] and r.stop_reason == "final_answer"
    seen = rt.agent.llm.calls[2]["messages"]
    assert seen[-1]["results"][0]["result"]["error"]["code"] == "invalid_arguments"


def test_llm_outage_degrades_without_touching_the_plant(make):
    rt = make([LLMError("503")])
    r = rt.agent.run_turn(rt.user("u-sup-01"), "hola")
    assert r.stop_reason == "llm_error" and "sigue operando" in r.text and r.steps == []


def test_vision_outage_reaches_the_model_as_retryable_error(make, vision_app):
    rt = make([call("inspect_images", image_ids=["IMG"]), say("El servicio de visión no responde.")])
    sup = rt.user("u-sup-01")
    up = rt.images.save_batch(sup, [("a.png", png(blob()))], rt.now)
    rt.agent.llm.script[0].tool_calls[0].args["image_ids"] = [up["images"][0]["image_id"]]
    vision_app.post("/admin/fault", json={"mode": "error", "count": 5})
    r = rt.agent.run_turn(sup, "revisa esta imagen", up)
    assert r.steps[0].outcome == "vision_unavailable"
    assert rt.agent.llm.calls[1]["messages"][-1]["results"][0]["result"]["error"]["retryable"] is True
    assert f"lote {up['batch_id']} con 1 imágenes" in rt.agent.llm.calls[0]["messages"][-1]["text"]


def test_risky_request_from_the_agent_is_never_executed(make):
    rt = make([call("set_line_state", line_id="L2", state="PAUSED", reason="agarres fallidos sobre el 5 %"),
               say("He creado la solicitud; falta la aprobación.")])
    r = rt.agent.run_turn(rt.user("u-mnt-01"), "pausa la L2")
    assert r.steps[0].outcome == "pending_approval" and len(r.approvals) == 1
    assert one(rt.con, "SELECT status FROM lines WHERE plant_id='BAQ' AND line_id='L2'")["status"] == "RUNNING"
    assert "decide" not in REGISTRY and not any("approv" in n for n in REGISTRY)  # aprobar no es una tool


def test_sessions_are_private_to_their_user(make):
    rt = make([say("hola")])
    sup = rt.user("u-sup-01")
    rt.agent.run_turn(sup, "hola")
    intruder = principal_for(rt.con, "u-qa-01", sup.session_id)
    with pytest.raises(ToolError) as e:
        rt.agent.run_turn(intruder, "¿de qué hablaban?")
    assert e.value.code == "session_not_found"


def test_old_messages_are_folded_into_a_bounded_summary(make):
    rt = make([say("respuesta " + "x" * 50)], history_max_messages=4, history_keep_chars=20)
    sup = rt.user("u-sup-01")
    for i in range(5):
        rt.agent.run_turn(sup, f"pregunta {i}")
    summary, msgs, turn = rt.sessions.context(sup)
    assert turn == 6 and len(msgs) == 4 and "Usuario: pregunta 0" in summary and "x" * 30 not in summary
    assert len(rows(rt.con, "SELECT 1 FROM messages WHERE session_id=?", (sup.session_id,))) == 10  # nada se borra


def test_every_tool_schema_converts_to_the_provider_format():
    for spec in REGISTRY.values():
        g = to_gemini_schema(spec.json_schema())
        assert g["type"] == "OBJECT" and all("type" in p for p in g.get("properties", {}).values())
    shift = to_gemini_schema(REGISTRY["get_shift_metrics"].json_schema())["properties"]["shift"]
    assert shift["type"] == "INTEGER" and "valores permitidos: 1, 2, 3" in shift["description"]
