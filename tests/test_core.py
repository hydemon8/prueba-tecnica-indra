import numpy as np
import pytest

from linevision.gate import GatePolicy, calibrate_ambiguity, calibrate_class_conf, decide
from linevision.metrics import circular_error, decision_report, symmetric_error
from linevision.pose import PoseConfig, PoseModel
from linevision.protocols import covered_splits, inner_splits, protocol_a, protocol_b, protocol_c, protocol_d

OBJ = np.repeat(np.arange(1, 101), 72)
ANG = np.tile(np.arange(0, 360, 5), 100)


# ---------- métricas ----------
def test_circular_error_wraps():
    assert circular_error(355, 5) == 10
    assert circular_error(0, 180) == 180
    assert circular_error(370, 10) == 0


def test_symmetric_error():
    assert symmetric_error(185, 5, 2) == 0  # objeto de orden 2: theta y theta+180 equivalen
    assert symmetric_error(185, 5, 1) == 180
    assert symmetric_error(90, 5, 0) == 0  # invariante al giro


def test_unsafe_counts_only_act():
    rep = decision_report(np.array(["ACT", "ACT", "REVIEW"]), np.array([True, False, False]),
                          np.array([5.0, 5.0, 50.0]), tol=10)
    assert rep["unsafe_rate"] == pytest.approx(1 / 3)
    assert rep["precision_on_act"] == pytest.approx(0.5)


# ---------- protocolos ----------
@pytest.mark.parametrize("split,n_train,n_test", [
    (protocol_a(OBJ, ANG), 3600, 3600),
    (protocol_b(OBJ, ANG, seed=1), 6000, 1200),
    (protocol_c(OBJ, ANG), 1200, 6000),
    (protocol_d(OBJ, ANG, seed=1), 6480, 720),
])
def test_protocol_sizes_and_disjoint(split, n_train, n_test):
    assert len(split.train) == n_train and len(split.test) == n_test
    assert not set(split.train) & set(split.test)


def test_protocol_b_arc_is_contiguous_60deg():
    sp = protocol_b(OBJ, ANG, seed=3)
    for o in (1, 50, 100):
        a = np.sort(ANG[sp.test][OBJ[sp.test] == o])
        start = sp.meta["arc_start"][o]
        assert set(a) == {(start + 5 * k) % 360 for k in range(12)}


@pytest.mark.parametrize("split", [protocol_a(OBJ, ANG), protocol_b(OBJ, ANG, 1), protocol_c(OBJ, ANG),
                                   protocol_d(OBJ, ANG, 1)])
def test_inner_splits_never_touch_test(split):
    test = set(split.test)
    for sp in inner_splits(split, OBJ, ANG):
        assert not set(sp.train) & test and not set(sp.test) & test
        assert not set(sp.train) & set(sp.test)


def test_protocol_d_inner_pseudo_unknowns_are_known_objects():
    sp = protocol_d(OBJ, ANG, seed=1)
    for inner in inner_splits(sp, OBJ, ANG):
        assert not set(inner.unknown_objects) & set(sp.unknown_objects)
        assert not np.isin(OBJ[inner.train], inner.unknown_objects).any()


# ---------- modelo del plato ----------
def _toy_views(angles, n_obj=3, noise=0.0, seed=0):
    """Objetos sintéticos cuya apariencia depende suavemente del ángulo (lazo cerrado)."""
    rng = np.random.default_rng(seed)
    proj = rng.normal(size=(n_obj, 6, 40))
    th = np.deg2rad(angles)
    basis = np.stack([np.cos(th), np.sin(th), np.cos(2 * th), np.sin(2 * th), np.cos(3 * th), np.sin(3 * th)], 1)
    X = np.concatenate([basis @ proj[o] + o * 5 for o in range(n_obj)])
    X += rng.normal(scale=noise, size=X.shape)
    return X.astype(np.float32), np.repeat(np.arange(n_obj), len(angles)), np.tile(angles, n_obj)


def test_pose_recovers_unseen_angles():
    X, o, a = _toy_views(np.arange(0, 360, 20.0))
    model = PoseModel(PoseConfig(pca_dim=10)).fit(X, o, a)
    Xq, oq, aq = _toy_views(np.arange(10, 360, 20.0))
    est = model.estimate(Xq, oq)
    assert np.median(circular_error(est.angle, aq)) < 2.0
    assert (est.sku_max_gap == 20).all()


def test_pose_flags_ambiguity_for_symmetric_object():
    angles = np.arange(0, 360, 10.0)
    th = np.deg2rad(angles)
    X = np.stack([np.cos(2 * th), np.sin(2 * th), np.cos(4 * th), np.sin(4 * th)], 1).astype(np.float32)
    model = PoseModel(PoseConfig(pca_dim=4)).fit(X, np.zeros(len(X), int), angles)
    est = model.estimate(X[:1], np.zeros(1, int))
    assert est.ambiguity[0] == pytest.approx(1.0, abs=1e-3)  # theta y theta+180 son indistinguibles
    assert est.credible_width[0] > 1.0


# ---------- control de seguridad ----------
def test_gate_rule_order():
    policy = GatePolicy(novelty_max=1.0, class_conf_min=0.8, angle_width_max=20, ambiguity_max=0.8,
                        max_gallery_gap=30)
    dec, reasons = decide(
        policy,
        novelty=np.array([2.0, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]),
        class_conf=np.array([0.99, 0.5, 0.99, 0.99, 0.99, 0.99, 0.99]),
        evidence_agrees=np.array([True, True, False, True, True, True, True]),
        sku_max_gap=np.array([5, 5, 5, 65, 5, 5, 5]),
        angle_width=np.array([5, 5, 5, 5, 40, 5, 5]),
        ambiguity=np.array([0.1, 0.1, 0.1, 0.1, 0.1, 0.95, 0.1]),
    )
    assert list(dec) == ["UNKNOWN", "REVIEW", "REVIEW", "ANGLE_UNCERTIFIED", "ANGLE_UNCERTIFIED",
                         "ANGLE_UNCERTIFIED", "ACT"]
    assert "ambiguo" in reasons[5][0]
    assert all(r for r in reasons[:6]) and reasons[6] == []


def test_ambiguity_threshold_meets_angle_risk_target():
    width = np.array([5, 5, 5, 5, 5, 50])
    amb = np.array([0.1, 0.2, 0.3, 0.9, 0.95, 0.1])
    err = np.array([1, 2, 1, 3, 170, 100])  # el error grande está en el caso más ambiguo
    assert calibrate_ambiguity(width, amb, err, width_max=20, tol=10, target_error=0.0) == 0.9


@pytest.mark.parametrize("split,step", [(protocol_a(OBJ, ANG), 10), (protocol_b(OBJ, ANG, 1), 5),
                                        (protocol_c(OBJ, ANG), 30)])
def test_covered_splits_alternate_without_touching_test(split, step):
    for sp in covered_splits(split, OBJ, ANG):
        assert not set(sp.train) & set(split.test) and not set(sp.test) & set(split.test)
        assert set(np.unique(ANG[sp.test] % (2 * step))) <= {0, step}


def test_class_conf_threshold_meets_target():
    conf = np.array([0.99, 0.95, 0.9, 0.8, 0.6, 0.5])
    correct = np.array([True, True, True, True, False, False])
    thr = calibrate_class_conf(conf, correct, target_error=0.0)
    assert thr == 0.8
