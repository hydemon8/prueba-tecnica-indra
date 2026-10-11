"""Calcula los datos de las figuras del reporte que no están ya en `reports/` ni en `doc/`:
lazos del modelo de ángulo, perfiles de distancia y distribuciones posteriores, y el montaje de imágenes.

Uso, desde la raíz del repositorio (necesita el dataset y el entorno del proyecto):
    .venv/Scripts/python.exe doc/reporte_ieee/calcular_datos.py
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image

from linevision.config import cache_dir, data_dir, load_config
from linevision.data import load_coil100
from linevision.features import extract_cached
from linevision.pose import PoseConfig, PoseModel
from linevision.system import SystemConfig

HERE = Path(__file__).resolve().parent
OBJS = [74, 67, 47]               # ángulo claro, simetría de media vuelta, simetría de revolución (toro)
SYM = 67
QUERY_DEG = 45                    # vista de prueba del protocolo A
SCALE_A = 0.0398                  # escala de temperatura calibrada en validación interna de A (documento 7, tabla 7.6)

ds = load_coil100(data_dir())
model_cfg, prot_cfg = load_config("model"), load_config("protocols")
cfg = SystemConfig.from_model_config(model_cfg)
feats = extract_cached(ds.images, cfg.features, ds.version, cache_dir())
raw, OBJ, ANG = feats["raw"], ds.obj, ds.angle
out = {"objs": OBJS, "query_deg": QUERY_DEG}

# ---- montaje de imágenes: tres objetos cada 45 grados
angles = list(range(0, 360, 90))
tile, gap = 96, 4
W = len(angles) * tile + (len(angles) - 1) * gap
H = len(OBJS) * tile + (len(OBJS) - 1) * gap
sheet = Image.new("RGB", (W, H), "white")
for r, o in enumerate(OBJS):
    for c, a in enumerate(angles):
        img = ds.images[(OBJ == o) & (ANG == a)][0]
        sheet.paste(Image.fromarray(img).resize((tile, tile), Image.LANCZOS), (c * (tile + gap), r * (tile + gap)))
sheet.save(HERE / "montaje_vistas.png")
out["montaje"] = {"angles": angles, "tile": tile, "gap": gap, "w": W, "h": H}

# ---- lazos: modelo con las 72 vistas (como el de producción), proyectado a sus dos primeras componentes
full = PoseModel(PoseConfig(pca_dim=model_cfg["pose"]["pca_dim"])).fit(raw, OBJ, ANG)
out["varianza_2d"] = float(full.pca.explained_variance_ratio_[:2].sum())
out["varianza_50d"] = float(full.pca.explained_variance_ratio_.sum())
out["lazos"] = {}
size_all = {int(o): float(np.median(((c - c.mean(0)) ** 2).sum(1))) for o, c in full.curves.items()}
out["tamano_mediano"] = float(np.median(list(size_all.values())))
for o in OBJS:
    c = full.curves[o]
    d180 = float(np.median(((c - np.roll(c, -360, 0)) ** 2).sum(1)))
    d10 = float(np.median(((c - np.roll(c, -20, 0)) ** 2).sum(1)))
    # plano principal del propio lazo: las dos direcciones en que más varía este objeto
    cc = c - c.mean(0)
    _, sv, vt = np.linalg.svd(cc, full_matrices=False)
    plano = np.round(cc[::4] @ vt[:2].T, 3).tolist()
    var_plano = float((sv[:2] ** 2).sum() / (sv ** 2).sum())
    out["lazos"][o] = {
        "curva": np.round(c[::4, :2], 3).tolist(),                # un punto cada 2 grados
        "vistas": np.round(full.gallery_z[o][:, :2], 3).tolist(),  # una por vista (cada 5 grados)
        "d10": d10, "d180": d180, "razon": d180 / d10, "tamano": size_all[o],
        "plano": plano, "varianza_plano": var_plano,
        "puesto_tamano": sorted(size_all, key=size_all.get).index(o) + 1,
    }

# ---- perfil de distancia y posterior: modelo entrenado como en el protocolo A y consulta en una vista de prueba
train = ANG % 10 == 0
assert not train[(ANG == QUERY_DEG)].any()
pa = PoseModel(PoseConfig(pca_dim=model_cfg["pose"]["pca_dim"])).fit(raw[train], OBJ[train], ANG[train])
pa.temperature_scale = SCALE_A
out["posterior"] = {"grid_step": 0.5, "escala": SCALE_A, "temperatura_base": float(pa.base_temperature)}
AMB_MAX_A = 0.891                 # umbral de ambigüedad calibrado en A (documento 7, tabla 7.6)
test_angles = np.arange(5, 360, 10)
for o in OBJS:
    # en el objeto simétrico se elige la vista de prueba más ambigua, para mostrar el mecanismo; en los otros, 45 grados
    qs = (OBJ == o) & ~train
    est_all = pa.estimate(raw[qs], OBJ[qs])
    amb = dict(zip(ANG[qs].tolist(), est_all.ambiguity.tolist()))
    wid = dict(zip(ANG[qs].tolist(), est_all.credible_width.tolist()))
    query = max(amb, key=amb.get) if o == SYM else QUERY_DEG
    q = (OBJ == o) & (ANG == query)
    Z = pa.pca.transform(raw[q]).astype(np.float32)
    d2 = pa._profiles(Z, o)
    w = pa._posterior(d2, pa.temperature_scale)[0]
    est = pa.estimate(raw[q], OBJ[q])
    out["posterior"][o] = {
        "consulta": int(query), "d": np.round(np.sqrt(d2[0]), 4).tolist(), "w": np.round(w, 6).tolist(),
        "angulo": float(est.angle[0]), "ancho": float(est.credible_width[0]), "ambiguedad": float(est.ambiguity[0]),
        "vistas_ambiguas": int(sum(v > AMB_MAX_A for v in amb.values())),
        "vistas_anchas": int(sum(v > 20 for v in wid.values())), "vistas_prueba": len(amb),
    }
    err = min(abs(est.angle[0] - query), 360 - abs(est.angle[0] - query))
    print(f"obj{o}: consulta {query}, estimado {est.angle[0]:.1f} (error {err:.1f}), ancho {est.credible_width[0]:.1f}, "
          f"ambigüedad {est.ambiguity[0]:.2f}, pico {w.max():.3f} | vistas de prueba con ambigüedad>{AMB_MAX_A}: "
          f"{out['posterior'][o]['vistas_ambiguas']}/36, con ancho>20: {out['posterior'][o]['vistas_anchas']}/36")
    if o == SYM:
        k = int(np.argmax(w)); far = np.abs(((np.arange(720) - k + 360) % 720) - 360) > 40
        print("   simétrico: segundo pico (lejos del primero):", round(float(w[far].max()), 4), "en", float(np.argmax(np.where(far, w, 0)) * 0.5),
              "| masa cerca del 1er pico:", round(float(w[~far].sum()), 3), "| ambigüedades:", {k: round(v, 2) for k, v in sorted(amb.items())})

(HERE / "datos.json").write_text(json.dumps(out), encoding="utf-8")
print("varianza 2D:", round(out["varianza_2d"], 3), "| 50D:", round(out["varianza_50d"], 3), "| tamaño mediano:", round(out["tamano_mediano"], 2))
