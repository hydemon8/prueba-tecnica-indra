# Robustez del sistema de PRODUCCIÓN ante perturbaciones de captura (no usa la prueba de ningún protocolo:
# son imágenes nuevas generadas a partir del catálogo). Compara la identidad ganadora con la 2a opción.
import warnings; warnings.filterwarnings("ignore")
import time, numpy as np, pandas as pd
from PIL import Image, ImageFilter
from linevision.config import data_dir, cache_dir, load_config
from linevision.data import load_coil100
from linevision.features import extract, extract_cached
from linevision.identity import IdentityConfig
from linevision.system import SystemConfig, VisionSystem
from linevision.experiment import production_system
from linevision.metrics import circular_error
ds = load_coil100(data_dir()); M = load_config("model")
rng = np.random.default_rng(1)
pick = rng.choice(len(ds), 200, replace=False)
def bright(x, f): return np.clip(x.astype(float) * f, 0, 255).astype(np.uint8)
def noise(x, s): return np.clip(x + rng.normal(0, s, x.shape), 0, 255).astype(np.uint8)
def blur(x, r): return np.asarray(Image.fromarray(x).filter(ImageFilter.GaussianBlur(r)))
def rot(x, d): return np.asarray(Image.fromarray(x).rotate(d, fillcolor=(26, 26, 26)))
def shift(x, dx): return np.roll(x, dx, axis=1)
P = {"limpia": lambda x: x, "brillo +15%": lambda x: bright(x, 1.15), "brillo -15%": lambda x: bright(x, 0.85),
     "brillo -30%": lambda x: bright(x, 0.7), "ruido σ=4": lambda x: noise(x, 4), "ruido σ=8": lambda x: noise(x, 8),
     "desenfoque r=1": lambda x: blur(x, 1), "desplazado 8px": lambda x: shift(x, 8),
     "volcado 90° (OOD)": lambda x: rot(x, 90), "volcado 180° (OOD)": lambda x: rot(x, 180)}
feats = extract_cached(ds.images, SystemConfig.from_model_config(M).features, ds.version, cache_dir())
systems = {}
for name, ident in [("HSV+RF (ganador)", IdentityConfig(("hsv",), "rf", {"n_estimators": 500}, 150)),
                    ("HSV+HOG+LBP+LogReg (2o)", IdentityConfig(("hsv", "hog", "lbp"), "logreg", {"C": 10.0}, 150))]:
    t = time.time(); systems[name], _ = production_system(SystemConfig.from_model_config(M, ident), feats, ds.obj, ds.angle, M["gate"], "probe")
    print(f"{name} calibrado en {time.time()-t:.0f}s", flush=True)
rows = []
for pname, f in P.items():
    imgs = np.stack([f(ds.images[i]) for i in pick])
    for sname, s in systems.items():
        blocks = sorted(set(s.cfg.identity.blocks) | {"raw"})
        r = s.infer(extract(imgs, s.cfg.features, blocks))
        ok_cls = r["label"] == ds.obj[pick]
        err = np.where(ok_cls, circular_error(r["angle"], ds.angle[pick]), np.inf)
        act = r["decision"] == "ACT"
        ood = "OOD" in pname
        unsafe = act if ood else act & (err > 10)
        rows.append({"perturbación": pname, "sistema": sname, "ACT": act.mean(), "inseguras": unsafe.mean(),
                     "UNKNOWN": np.mean(r["decision"] == "UNKNOWN"), "REVIEW": np.mean(r["decision"] == "REVIEW"),
                     "ANGLE_UNCERT": np.mean(r["decision"] == "ANGLE_UNCERTIFIED"), "clase ok": ok_cls.mean()})
df = pd.DataFrame(rows)
pd.set_option("display.width", 200)
print((df.set_index(["perturbación", "sistema"]) * 100).round(1).to_string())
