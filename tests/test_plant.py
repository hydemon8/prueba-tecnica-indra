from datetime import datetime

import pytest

from lineops.knowledge import KnowledgeBase
from lineops.plant.db import connect, one, rows
from lineops.plant.seed import SIM_NOW, seed, shift_of, shift_window
from lineops.settings import AgentSettings


@pytest.fixture(scope="module")
def con(tmp_path_factory):
    c = connect(tmp_path_factory.mktemp("plant") / "plant.db")
    seed(c)
    return c


def rate(con, where, params):
    return one(con, f"SELECT AVG(decision='UNKNOWN') AS r, COUNT(*) AS n FROM inference_events WHERE {where}", params)


def test_shifts():
    assert [shift_of(datetime(2026, 1, 1, h)) for h in (5, 6, 13, 14, 21, 22)] == [3, 1, 1, 2, 2, 3]
    assert shift_window(2) == (datetime(2026, 10, 10, 14), datetime(2026, 10, 10, 22))  # en curso
    assert shift_window(3) == (datetime(2026, 10, 9, 22), datetime(2026, 10, 10, 6))  # el último completo


def test_seed_is_idempotent_and_reproducible(con, tmp_path):
    n = one(con, "SELECT COUNT(*) AS n FROM inference_events")["n"]
    seed(con)
    assert one(con, "SELECT COUNT(*) AS n FROM inference_events")["n"] == n
    other = connect(tmp_path / "otra.db")
    seed(other)
    q = "SELECT decision, COUNT(*) AS n FROM inference_events GROUP BY decision ORDER BY decision"
    assert rows(other, q) == rows(con, q)
    assert one(con, "SELECT MAX(ts) AS t FROM inference_events")["t"] <= SIM_NOW.isoformat()


def test_lamp_fault_raises_rejections_only_on_baq_l1(con):
    window = ("2026-10-10T03:00:00", "2026-10-10T04:00:00")
    during = rate(con, "plant_id='BAQ' AND line_id='L1' AND ts>=? AND ts<?", window)
    before = rate(con, "plant_id='BAQ' AND line_id='L1' AND ts>=? AND ts<?",
                  ("2026-10-09T23:00:00", "2026-10-10T02:00:00"))
    other = rate(con, "plant_id='BAQ' AND line_id='L2' AND ts>=? AND ts<?", window)
    assert during["r"] > 0.35 and before["r"] < 0.04 and other["r"] < 0.04
    cam = one(con, "SELECT MIN(brightness) AS b FROM camera_health WHERE line_id='L1' AND plant_id='BAQ'")
    assert cam["b"] < 0.17


def test_gripper_fault_is_concentrated_in_three_skus(con):
    q = ("SELECT AVG(grasp_ok=0) AS r FROM inference_events WHERE plant_id='BAQ' AND line_id='L2'"
         " AND ts>='2026-10-10T15:30:00' AND decision='ACT' AND object_id {} (23,47,81)")
    assert one(con, q.format("IN"))["r"] > 0.25 and one(con, q.format("NOT IN"))["r"] < 0.03


def test_review_queue_and_isolation_keys(con):
    pending = one(con, "SELECT COUNT(*) AS n FROM review_cases WHERE plant_id='BAQ' AND line_id='L1'"
                       " AND status='PENDING'")
    assert pending["n"] == 8
    assert {r["plant_id"] for r in rows(con, "SELECT DISTINCT plant_id FROM inference_events")} == {"BAQ", "BOG"}


def test_knowledge_search_returns_cited_sections():
    kb = KnowledgeBase(AgentSettings.from_env().sops_dir)
    hits = kb.search("agarres fallidos concentrados en pocos SKU, presión de vacío de la ventosa")
    assert hits[0]["citation"].startswith("SOP-MNT-001 § 4")
    assert kb.search("quién aprueba promover una versión de modelo")[0]["citation"].startswith("SOP-OPS-005")
    assert kb.search("xyzzy") == []
