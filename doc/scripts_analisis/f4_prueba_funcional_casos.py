import warnings; warnings.filterwarnings("ignore")
import json, numpy as np
from PIL import Image, ImageFilter
from linevision.config import ROOT, data_dir
from linevision.data import load_coil100
from linevision.system import VisionSystem
from linevision.registry import sha256
man = json.load(open(ROOT / "artifacts/linevision-4e39f878-rf.manifest.json"))
path = ROOT / "artifacts" / man["artifact"]
assert sha256(path) == man["artifact_sha256"]
sysm = VisionSystem.load(path)
ds = load_coil100(data_dir())
def img(o, a): return ds.images[(ds.obj == o) & (ds.angle == a)][0]
rng = np.random.default_rng(0)
def bright(x, f): return np.clip(x.astype(float) * f, 0, 255).astype(np.uint8)
def noise(x, s): return np.clip(x + rng.normal(0, s, x.shape), 0, 255).astype(np.uint8)
def blur(x, r): return np.asarray(Image.fromarray(x).filter(ImageFilter.GaussianBlur(r)))
def rot(x, d): return np.asarray(Image.fromarray(x).rotate(d, fillcolor=(26, 26, 26)))
def occl(x): y = x.copy(); y[:, 64:] = 26; return y
def hue(x, s): h = np.asarray(Image.fromarray(x).convert("HSV")).copy(); h[..., 0] = (h[..., 0].astype(int) + s) % 256; return np.asarray(Image.fromarray(h, "HSV").convert("RGB"))
def shift(x, dx): return np.roll(x, dx, axis=1)
def scale(x, f):
    s = int(128 * f); y = np.full_like(x, 26); im = np.asarray(Image.fromarray(x).resize((s, s)))
    o = (128 - s) // 2; y[o:o + s, o:o + s] = im; return y
cases = [
  ("nominal obj5 40°", img(5, 40), 5, 40),
  ("brillo +15% obj5 40°", bright(img(5, 40), 1.15), 5, 40),
  ("brillo -30% obj5 40°", bright(img(5, 40), 0.7), 5, 40),
  ("ruido σ=8 obj19 120°", noise(img(19, 120), 8), 19, 120),
  ("desenfoque r=1.5 obj82 200°", blur(img(82, 200), 1.5), 82, 200),
  ("desplazado 10px obj82 200°", shift(img(82, 200), 10), 82, 200),
  ("escala 80% obj82 200°", scale(img(82, 200), 0.8), 82, 200),
  ("volcado (rot. 90° en plano) obj19 120°", rot(img(19, 120), 90), 19, None),
  ("ocluido 50% obj19 120°", occl(img(19, 120)), 19, None),
  ("otro color (variante) obj5 40°", hue(img(5, 40), 60), None, None),
  ("ruido puro", rng.integers(0, 255, (128, 128, 3)).astype(np.uint8), None, None),
  ("imagen negra", np.full((128, 128, 3), 26, np.uint8), None, None),
  ("simétrico obj47 rosca 90°", img(47, 90), 47, 90),
  ("simétrico obj65 caja 90°", img(65, 90), 65, 90),
]
out = sysm.predict_images(np.stack([c[1] for c in cases]))
for (name, _, o, a), r in zip(cases, out):
    ang = r["angle_deg"]; err = "" if (a is None or ang is None) else f" err={min(abs(ang-a)%360, 360-abs(ang-a)%360):.1f}°"
    print(f"{name:42s} -> {r['decision']:18s} obj={r['object_id']} conf={r['class_confidence']:.2f} nov={r['novelty']:.3f} ang={ang} ancho={r['angle_credible_width_deg']}{err} | {'; '.join(r['reasons'])[:80]}")
print("umbrales:", {k: round(v, 3) if isinstance(v, float) else v for k, v in vars(sysm.cfg.policy).items()})
