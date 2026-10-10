# Diagnóstico SOLO en validación interna: ¿qué señal separa los errores de ángulo > 10° entre los que pasarían el gate?
import warnings; warnings.filterwarnings("ignore")
import numpy as np
from sklearn.metrics import roc_auc_score
from linevision.config import data_dir, cache_dir, load_config
from linevision.data import load_coil100
from linevision.features import extract_cached
from linevision.protocols import make_protocol, inner_splits, Split
from linevision.pose import PoseModel
from linevision.system import SystemConfig
from linevision.metrics import circular_error
ds = load_coil100(data_dir()); M, P = load_config("model"), load_config("protocols")
cfg = SystemConfig.from_model_config(M); feats = extract_cached(ds.images, cfg.features, ds.version, cache_dir())
O, A = ds.obj, ds.angle
def alt(split):  # alternancia dentro del entrenamiento (régimen con cobertura)
    a = A[split.train]; e = (a // 5) % 2 == 0
    return [Split("alt0", split.train[e], split.train[~e]), Split("alt1", split.train[~e], split.train[e])]
for name in ("A", "B"):
    sp = make_protocol(name, O, A, P)
    folds = inner_splits(sp, O, A) if name == "A" else alt(sp)
    W, AM, E, OB = [], [], [], []
    for f in folds:
        pm = PoseModel(cfg.pose).fit(feats["raw"][f.train], O[f.train], A[f.train]); pm.temperature_scale = 0.0398
        est = pm.estimate(feats["raw"][f.test], O[f.test])
        W.append(est.credible_width); AM.append(est.ambiguity); E.append(circular_error(est.angle, A[f.test])); OB.append(O[f.test])
    W, AM, E, OB = map(np.concatenate, (W, AM, E, OB)); bad = E > 10
    print(f"[{name} interno, {'alternancia' if name=='B' else 'A_in'}] n={len(E)} err>10: {bad.mean():.2%} | entre ancho<=20: {bad[W<=20].mean():.2%} (pasan {np.mean(W<=20):.1%})")
    print(f"   AUROC para detectar err>10 -> ancho {roc_auc_score(bad, W):.3f} | ambigüedad {roc_auc_score(bad, AM):.3f}")
    gate = W <= 20
    for t in (1.0, 0.9, 0.8, 0.7, 0.6):
        ok = gate & (AM <= t)
        print(f"   + ambigüedad<={t}: pasan {ok.mean():.1%}, err>10 entre los que pasan {bad[ok].mean():.2%}")
    u, c = np.unique(OB[gate & bad], return_counts=True); top = np.argsort(-c)[:8]
    print("   objetos con errores que pasan el gate:", dict(zip(u[top].tolist(), c[top].tolist())))
