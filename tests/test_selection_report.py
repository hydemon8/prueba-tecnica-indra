import numpy as np
import pandas as pd
import pytest

from linevision.report import protocol_table
from linevision.selection import aurc, select


def test_aurc_rewards_confidence_that_ranks_errors_last():
    correct = np.array([True, True, True, False])
    good = aurc(np.array([0.9, 0.8, 0.7, 0.1]), correct)  # el error tiene la menor confianza
    bad = aurc(np.array([0.1, 0.8, 0.7, 0.9]), correct)  # el error tiene la mayor confianza
    assert good < bad


def _table():
    return pd.DataFrame([
        {"candidate": "a", "worst_acc": 0.990, "unknown_accepted": 0.40, "predict_ms": 0.01},  # inseguro
        {"candidate": "b", "worst_acc": 0.970, "unknown_accepted": 0.01, "predict_ms": 0.50},
        {"candidate": "c", "worst_acc": 0.968, "unknown_accepted": 0.02, "predict_ms": 0.05},  # empate, más rápido
        {"candidate": "d", "worst_acc": 0.950, "unknown_accepted": 0.00, "predict_ms": 0.01},
    ])


def test_select_applies_safety_constraint_then_worst_case_then_latency():
    assert select(_table(), max_unknown_accepted=0.05, tie_pp=0.5)["candidate"] == "c"
    assert select(_table(), max_unknown_accepted=0.05, tie_pp=0.0)["candidate"] == "b"


def test_select_fails_when_nothing_is_safe():
    with pytest.raises(ValueError):
        select(_table(), max_unknown_accepted=-1, tie_pp=0.5)


def test_protocol_table_mean_and_std():
    runs = [{"class_acc": 0.9, "latency_ms_per_image": 1.0}, {"class_acc": 1.0, "latency_ms_per_image": 3.0}]
    t = protocol_table({"B": runs})
    assert t.loc["B", "clase"] == "95.0 ± 5.0"
    assert t.loc["B", "latencia (ms/img)"] == "2.0 ± 1.0"
    assert t.loc["B", "desconocidos rechazados"] == "—"
