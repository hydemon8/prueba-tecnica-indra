"""Figuras del reporte, dibujadas como SVG con un único sistema de diseño (misma tipografía, misma paleta,
mismas marcas). Las cifras se leen de `reports/`, de `doc/` y de `datos.json`; nada se escribe a mano salvo
las cifras del diagnóstico inicial, que solo están en el documento 2.

Paleta: tres primeros tonos categóricos validados para daltonismo sobre fondo blanco; el gris es contexto.
"""
import json
import math
import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = json.loads((HERE / "datos.json").read_text(encoding="utf-8"))
RESULTS = json.loads((ROOT / "reports" / "results.json").read_text(encoding="utf-8"))

INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, GRAY = "#2a78d6", "#eb6834", "#b4b2a9"
BLUE_TINT, PAPER = "#e8f1fc", "#ffffff"
SEQ = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6", "#256abf", "#1c5cab",
       "#184f95", "#104281", "#0d366b"]
FONT = 'font-family="Arial, Helvetica, sans-serif"'
COL, WIDE = 336, 696          # ancho de una columna y de la página, en px a 96 ppp (3,5 y 7,25 pulgadas)


# ------------------------------------------------------------------ utilidades
def es(v, dec=1):
    """Número con coma decimal. Redondea la mitad hacia arriba, igual en el texto, las tablas y las figuras."""
    q = Decimal(repr(round(float(v), 9))).quantize(Decimal(1).scaleb(-dec), rounding=ROUND_HALF_UP)
    return f"{q:.{dec}f}".replace(".", ",")


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def T(x, y, s, size=9.5, anchor="start", fill=INK, weight="normal", italic=False):
    it = ' font-style="italic"' if italic else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" {FONT} font-size="{size}" text-anchor="{anchor}" fill="{fill}" '
            f'font-weight="{weight}"{it}>{esc(s)}</text>')


def TL(x, y, lines, size=9.5, anchor="middle", fill=INK, lh=None, bold_first=False):
    lh = lh or size * 1.22
    return "".join(T(x, y + i * lh, s, size, anchor, fill, "bold" if bold_first and i == 0 else "normal")
                   for i, s in enumerate(lines))


def svg(w, h, body, label, fid):
    marker = (f'<defs><marker id="ah-{fid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6.5" markerHeight="6.5" '
              f'orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="{INK2}"/></marker></defs>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
            f'aria-label="{esc(label)}">{marker}{body}</svg>')


def box(x, y, w, h, lines, fill=PAPER, stroke=INK2, size=9.5, bold_first=True, sw=0.8):
    lh = size * 1.22
    y0 = y + h / 2 - (len(lines) - 1) * lh / 2 + size * 0.35
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'
            + TL(x + w / 2, y0, lines, size, "middle", INK, lh, bold_first))


def arrow(pts, fid, both=False):
    d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
    start = f' marker-start="url(#ah-{fid})"' if both else ""
    return f'<path d="{d}" fill="none" stroke="{INK2}" stroke-width="1" marker-end="url(#ah-{fid})"{start}/>'


def col_bar(x, y_base, w, h, fill):
    """Columna con el extremo de datos redondeado y la base recta."""
    r = min(4, h, w / 2)
    y1 = y_base - h
    return (f'<path d="M{x:.1f} {y_base:.1f}L{x:.1f} {y1 + r:.1f}Q{x:.1f} {y1:.1f} {x + r:.1f} {y1:.1f}L{x + w - r:.1f} {y1:.1f}'
            f'Q{x + w:.1f} {y1:.1f} {x + w:.1f} {y1 + r:.1f}L{x + w:.1f} {y_base:.1f}Z" fill="{fill}"/>')


def row_bar(x_base, y, w, h, fill):
    r = min(4, w, h / 2)
    x1 = x_base + w
    return (f'<path d="M{x_base:.1f} {y:.1f}L{x1 - r:.1f} {y:.1f}Q{x1:.1f} {y:.1f} {x1:.1f} {y + r:.1f}L{x1:.1f} {y + h - r:.1f}'
            f'Q{x1:.1f} {y + h:.1f} {x1 - r:.1f} {y + h:.1f}L{x_base:.1f} {y + h:.1f}Z" fill="{fill}"/>')


def legend(x, y, items, size=9.5, gap=14):
    """items: (color, texto, forma) con forma en {'bar', 'line', 'dot', 'ring'}."""
    out, cx = "", x
    for color, text, shape in items:
        if shape == "bar":
            out += f'<rect x="{cx}" y="{y - 8}" width="10" height="10" rx="2" fill="{color}"/>'
        elif shape == "line":
            out += f'<line x1="{cx}" y1="{y - 3}" x2="{cx + 14}" y2="{y - 3}" stroke="{color}" stroke-width="2" stroke-linecap="round"/>'
        elif shape == "dot":
            out += f'<circle cx="{cx + 5}" cy="{y - 3}" r="3.2" fill="{color}"/>'
        else:
            out += f'<circle cx="{cx + 5}" cy="{y - 3}" r="2.6" fill="{PAPER}" stroke="{color}" stroke-width="1.4"/>'
        off = 19 if shape == "line" else 15
        out += T(cx + off, y, text, size, fill=INK2)
        cx += off + len(text) * size * 0.5 + gap
    return out


def y_axis(x0, x1, y_base, y_top, ticks, vmax, fmt=lambda v: str(v)):
    out = ""
    for t in ticks:
        y = y_base - (y_base - y_top) * t / vmax
        out += f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="{AXIS if t == 0 else GRID}" stroke-width="1"/>'
        out += T(x0 - 5, y + 3.2, fmt(t), 8.5, "end", MUTED)
    return out


def get(d, key):
    for k in key.split("."):
        d = d[k]
    return d


def mean_of(block, proto, key):
    runs = RESULTS[block][proto]
    return sum(get(r, key) for r in runs) / len(runs) * 100


def icon_path(slug):
    """Trazo de un icono de Simple Icons (CC0). Solo se acepta un `d` hecho de órdenes y números de trazo."""
    d = re.search(r'<path d="([^"]+)"', (HERE / "iconos" / f"{slug}.svg").read_text(encoding="utf-8")).group(1)
    assert re.fullmatch(r"[MmLlHhVvCcSsQqTtAaZz0-9eE\s,.\-+]+", d), slug
    return d


def icon(slug, x, y, size=11, fill=INK2):
    return f'<path d="{icon_path(slug)}" transform="translate({x} {y}) scale({size / 24:.4f})" fill="{fill}"/>'


# ------------------------------------------------------------------ Fig.: sistema en dos planos
def fig_sistema():
    f, b = "sis", ""
    b += T(0, 12, "Ruta crítica: cada objeto, unos 28 ms, sin LLM", 9.5, weight="bold")
    b += box(0, 38, 66, 40, ["Cámara"])
    b += f'<rect x="100" y="22" width="424" height="72" rx="6" fill="{BLUE_TINT}" stroke="{BLUE}" stroke-width="1"/>'
    b += T(312, 36, "Servicio de visión (API propia)", 9.5, "middle", weight="bold")
    for x, w, lines in [(108, 92, ["Validación", "de captura"]), (208, 112, ["Identidad", "HSV + Random Forest"]),
                        (328, 92, ["Ángulo", "lazos en PCA"]), (428, 88, ["Control de", "seguridad"])]:
        b += box(x, 44, w, 42, lines, size=9)
    for x in (200, 320, 420):
        b += arrow([(x + 0.5, 65), (x + 7.5, 65)], f)
    b += box(566, 38, 129, 40, ["Robot", "orden determinista"])
    b += arrow([(66, 58), (99, 58)], f) + T(83, 52, "imagen", 8.5, "middle", INK2)
    b += arrow([(524, 58), (565, 58)], f) + T(545, 52, "decisión", 8.5, "middle", INK2)

    b += T(0, 128, "Plano de supervisión: a demanda de una persona", 9.5, weight="bold")
    b += box(0, 150, 100, 44, ["Personal de planta", "rol, planta, líneas"])
    b += f'<rect x="132" y="138" width="300" height="68" rx="6" fill="{PAPER}" stroke="{INK2}" stroke-width="0.8"/>'
    b += T(282, 152, "Asistente agéntico", 9.5, "middle", weight="bold")
    for x, w, lines in [(140, 84, ["LLM", "elige la tool"]), (232, 100, ["Capa de política", "valida y autoriza"]),
                        (340, 84, ["22 tools", "lectura y escritura"])]:
        b += box(x, 158, w, 40, lines, size=9)
    for x in (224, 332):
        b += arrow([(x + 0.5, 178), (x + 7.5, 178)], f)
    b += arrow([(100, 172), (131, 172)], f, both=True)
    for y, text in [(138, "Planta: métricas, cola de revisión, tickets"), (164, "Procedimientos (SOP), con cita"),
                    (190, "Aprobación humana de operaciones de riesgo")]:
        b += f'<rect x="470" y="{y}" width="225" height="20" rx="4" fill="{PAPER}" stroke="{INK2}" stroke-width="0.8"/>'
        b += T(583, y + 13.5, text, 9, "middle")
        b += arrow([(432, 172), (450, 172), (450, y + 10), (469, y + 10)], f)
    b += arrow([(382, 137), (382, 95)], f)
    b += T(390, 119, "usa el modelo como tool: inspect_images → POST /v1/predict", 8.5, fill=INK2)
    return svg(WIDE, 212, b, "El servicio de visión atiende la línea sin LLM; el asistente lo usa como herramienta", f)


# ------------------------------------------------------------------ Fig.: vistas de tres objetos
def fig_montaje():
    m = DATA["montaje"]
    x0, w = 50, COL - 50
    s = w / m["w"]
    h_img = m["h"] * s
    tile = (m["tile"] + m["gap"]) * s
    b = f'<image href="montaje_vistas.png" x="{x0}" y="16" width="{w}" height="{h_img:.1f}"/>'
    for i, a in enumerate(m["angles"]):
        b += T(x0 + i * tile + m["tile"] * s / 2, 10, f"{a}°", 9, "middle", INK2)
    for r, lines in enumerate([["obj74", "pato"], ["obj67", "caja"], ["obj47", "toro"]]):
        cy = 16 + r * tile + m["tile"] * s / 2
        b += TL(0, cy - 2, lines, 9, "start", INK, bold_first=True)
    return svg(COL, 16 + h_img + 2, b, "Tres objetos de COIL-100 vistos cada 90 grados", "mon")


# ------------------------------------------------------------------ Fig.: diagnóstico con vecino más cercano
def fig_knn():
    # documento 2, tabla 2.4: 1-NN sobre píxeles 32x32, sin hiperparámetros
    groups = [("A", "vistas cada 10°", 99.97, 97.8), ("C", "12 vistas", 97.38, 76.0), ("B", "arco no visto", 92.33, 28.8)]
    x0, x1, yb, yt = 30, COL, 150, 30
    b = legend(x0, 12, [(GRAY, "Producto correcto", "bar"), (BLUE, "Ángulo dentro de ±10°", "bar")])
    b += y_axis(x0, x1, yb, yt, [0, 25, 50, 75, 100], 100)
    band = (x1 - x0) / len(groups)
    for i, (name, sub, cls, ang) in enumerate(groups):
        cx = x0 + band * (i + 0.5)
        for j, (v, color) in enumerate([(cls, GRAY), (ang, BLUE)]):
            x = cx - 27 + j * 29
            h = (yb - yt) * v / 100
            b += col_bar(x, yb, 25, h, color)
            b += T(x + 12.5, yb - h - 4, es(v, 2 if v > 99.9 else 1), 8.5, "middle", INK)
        b += T(cx, yb + 13, f"Protocolo {name}", 9.5, "middle", weight="bold") + T(cx, yb + 25, sub, 9, "middle", INK2)
    b += T(0, 22, "%", 8.5, fill=MUTED)
    return svg(COL, 180, b, "Con vecino más cercano el producto se identifica bien y el ángulo se degrada", "knn")


# ------------------------------------------------------------------ Fig.: protocolos
def fig_protocolos():
    f, b = "pro", ""
    r = 31

    def dial(cx, cy, train):
        out = f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{GRID}" stroke-width="1"/>'
        for a in range(0, 360, 5):
            x, y = cx + r * math.sin(math.radians(a)), cy - r * math.cos(math.radians(a))
            if train(a):
                out += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.7" fill="{BLUE}"/>'
            else:
                out += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.3" fill="{PAPER}" stroke="{ORANGE}" stroke-width="1"/>'
        return out

    dials = [(56, 62, "A · Interpolación", lambda a: a % 10 == 0, "36 entrena · 36 prueba"),
             (168, 62, "B · Sector ciego", lambda a: not 100 <= a <= 155, "60 entrena · 12 prueba"),
             (280, 62, "C · Escasez", lambda a: a % 30 == 0, "12 entrena · 60 prueba"),
             (112, 182, None, lambda a: True, "90 objetos conocidos"),
             (224, 182, None, lambda a: False, "10 objetos excluidos")]
    for cx, cy, title, rule, sub in dials:
        b += dial(cx, cy, rule)
        if title:
            b += T(cx, cy - r - 12, title, 9.5, "middle", weight="bold")
        b += T(cx, cy + r + 15, sub, 8.5, "middle", INK2)
    b += T(168, 139, "D · Objeto desconocido", 9.5, "middle", weight="bold")
    b += T(168, 65, "arco de 60°", 8, "middle", INK2)
    b += legend(52, 250, [(BLUE, "vista de entrenamiento", "dot"), (ORANGE, "vista de prueba", "ring")], size=9)
    return svg(COL, 256, b, "Reparto de las 72 vistas de un objeto entre entrenamiento y prueba en cada protocolo", f)


# ------------------------------------------------------------------ Fig.: selección de la identidad
def tabla_candidatos():
    """Los 35 candidatos de la tabla 6.5 del documento 6: (representación, clasificador) -> fila."""
    out = {}
    text = (ROOT / "doc" / "06_ml_estadistico_identidad.md").read_text(encoding="utf-8")
    sec = text[text.index("## 6.5"):text.index("## 6.6")]
    for line in sec.splitlines():
        m = re.match(r"\|\s*\**([a-z+]+) \\\| ([a-z_0-9]+(?:\([^)]*\))?)[^|]*\|(.+)\|", line)
        if m:
            vals = [float(v.strip(" *").replace(",", ".")) for v in m.group(3).split("|")]
            out[(m.group(1), m.group(2))] = dict(zip(["A", "B", "C", "peor", "aurc", "desc", "auroc"], vals))
    assert len(out) == 35, len(out)
    return out


def fig_seleccion():
    cand = tabla_candidatos()
    rows = [("raw", "Píxeles"), ("hsv", "Color HSV"), ("hog", "Forma HOG"), ("lbp", "Textura LBP"), ("hsv+hog+lbp", "HSV+HOG+LBP")]
    cols = [("knn1", "—"), ("logreg(C=1)", "1"), ("logreg(C=10)", "10"), ("svm_rbf(C=1)", "1"), ("svm_rbf(C=10)", "10"),
            ("svm_rbf(C=100)", "100"), ("rf(500)", "500")]
    x0, y0, cw, ch = 70, 38, 28, 22
    b = ""
    for label, a, c in [("1-NN", 0, 1), ("Reg. log.", 1, 3), ("SVM-RBF", 3, 6), ("RF", 6, 7)]:
        xa, xb = x0 + a * cw, x0 + c * cw
        b += T((xa + xb) / 2, 12, label, 9, "middle", weight="bold")
        b += f'<line x1="{xa + 3}" y1="17" x2="{xb - 3}" y2="17" stroke="{AXIS}" stroke-width="1"/>'
    b += T(x0 - 6, 31, "C o árboles", 8.5, "end", MUTED)
    b += TL(x0 + 7 * cw + 20, 12, ["Desc.", "acept."], 8.5, "middle", INK2, lh=10) + T(x0 + 7 * cw + 50, 22, "≤ 5 %", 8.5, "middle", INK2)
    for j, (_, sub) in enumerate(cols):
        b += T(x0 + j * cw + cw / 2, 31, sub, 8.5, "middle", INK2)
    lo, hi = 45, 100
    for i, (key, name) in enumerate(rows):
        y = y0 + i * ch
        b += T(x0 - 6, y + ch / 2 + 3.2, name, 8.5, "end")
        for j, (ck, _) in enumerate(cols):
            v = cand[(key, ck)]["peor"]
            k = min(len(SEQ) - 1, max(0, round((v - lo) / (hi - lo) * (len(SEQ) - 1))))
            b += f'<rect x="{x0 + j * cw + 1}" y="{y + 1}" width="{cw - 2}" height="{ch - 2}" rx="2" fill="{SEQ[k]}"/>'
            b += T(x0 + j * cw + cw / 2, y + ch / 2 + 3.2, es(v), 8.5, "middle", PAPER if k >= 6 else INK)
        d = cand[(key, "knn1")]["desc"]
        ok = d <= 5
        b += T(x0 + 7 * cw + 20, y + ch / 2 + 3.2, f"{es(d)} %", 8.5, "middle", INK)
        b += T(x0 + 7 * cw + 50, y + ch / 2 + 3.2, "sí" if ok else "no", 8.5, "middle", INK2 if ok else INK, "normal" if ok else "bold")
    wi, wj = 1, 6      # ganador: hsv | rf(500)
    b += (f'<rect x="{x0 + wj * cw}" y="{y0 + wi * ch}" width="{cw}" height="{ch}" rx="3" fill="none" stroke="{INK}" '
          f'stroke-width="1.6"/>')
    ys = y0 + 5 * ch + 14
    b += T(0, ys + 8.5, "Peor caso interno:", 8.5, fill=INK2)
    for k, c in enumerate(SEQ):
        b += f'<rect x="{94 + k * 12}" y="{ys}" width="12" height="9" fill="{c}"/>'
    b += T(92, ys + 20, "45 %", 8, "middle", MUTED) + T(94 + len(SEQ) * 12, ys + 20, "100 %", 8, "middle", MUTED)
    b += f'<rect x="262" y="{ys - 1}" width="11" height="11" rx="2" fill="none" stroke="{INK}" stroke-width="1.6"/>'
    b += T(277, ys + 8.5, "elegido", 8.5, fill=INK2)
    return svg(COL, ys + 24, b, "Exactitud del peor caso de los 35 candidatos de identidad", "sel")


# ------------------------------------------------------------------ Fig.: del píxel al ángulo
def fig_pipeline():
    f, b = "pip", ""
    w, h, gap = 176, 24, 11
    steps = ["Imagen de 128 × 128 píxeles (RGB)", "Reducción a 32 × 32", "Aplanado: 3.072 valores",
             "PCA global: 50 componentes", "Lazo por objeto: spline periódico",
             "Distancia a los 720 puntos del lazo", "Distribución sobre el ángulo"]
    ys = [i * (h + gap) for i in range(len(steps))]
    for i, text in enumerate(steps):
        fitted = i in (3, 4)
        b += box(0, ys[i], w, h, [text], fill=BLUE_TINT if fitted else PAPER, stroke=BLUE if fitted else INK2, size=9, bold_first=False)
        if i:
            b += arrow([(w / 2, ys[i - 1] + h + 1), (w / 2, ys[i] - 1)], f)
    for a, c, lines in [(0, 2, ["descripción", "de la imagen"]), (3, 4, ["se ajusta una vez, con las", "vistas de entrenamiento"]),
                        (5, 6, ["se calcula para", "cada imagen nueva"])]:
        ya, yb = ys[a] + 2, ys[c] + h - 2
        b += f'<path d="M{w + 6} {ya}L{w + 11} {ya}L{w + 11} {yb}L{w + 6} {yb}" fill="none" stroke="{AXIS}" stroke-width="1"/>'
        b += TL(w + 18, (ya + yb) / 2 - 2, lines, 9, "start", INK2)
    yo = ys[-1] + h + 15
    b += T(0, yo, "Salidas: ángulo, ancho del 90 % y ambigüedad", 9, weight="bold")
    return svg(COL, yo + 5, b, "Pasos del modelo de ángulo, de la imagen a la distribución sobre el ángulo", f)


# ------------------------------------------------------------------ Fig.: lazos
def fig_lazos():
    """Cada lazo se dibuja en su propio plano principal (las dos direcciones en que más varía ese objeto)."""
    b = legend(0, 9, [(BLUE, "primera media vuelta (0°–180°)", "line")], size=9)
    b += legend(0, 22, [(ORANGE, "segunda media vuelta (180°–360°)", "line")], size=9)
    names = {"74": "obj74 · ángulo observable", "67": "obj67 · simetría de media vuelta", "47": "obj47 · simetría de revolución"}
    pw, ph = 158, 128
    pos = [(0, 46), (178, 46), (0, 46 + ph + 44), (178, 46 + ph + 44)]

    def bounds_of(points):
        px, py = [p[0] for p in points], [p[1] for p in points]
        return min(px), max(px), min(py), max(py)

    def place(points, cx, cy, s):
        xa, xb, ya, yb = bounds_of(points)
        mx, my = (xa + xb) / 2, (ya + yb) / 2
        return [(cx + (px - mx) * s, cy - (py - my) * s) for px, py in points]

    def frame(x0, top, title, sub):
        return (f'<rect x="{x0}" y="{top}" width="{pw}" height="{ph}" rx="4" fill="{PAPER}" stroke="{GRID}" stroke-width="1"/>'
                + T(x0 + pw / 2, top - 7, title, 8.5, "middle", weight="bold") + T(x0 + pw / 2, top + ph + 12, sub, 8.5, "middle", INK2))

    def path(pts, color, width):
        d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
        return f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"/>'

    for i, o in enumerate(["74", "67", "47"]):
        x0, top = pos[i]
        L = DATA["lazos"][o]
        curve = L["plano"] + L["plano"][:1]
        xa, xb, ya, yb = bounds_of(curve)
        s = min((pw - 66) / (xb - xa), (ph - 50) / (yb - ya))
        cx, cy = x0 + pw / 2, top + ph / 2
        pts = place(curve, cx, cy, s)
        b += frame(x0, top, names[o], f"razón {es(L['razon'], 2)} · tamaño {es(L['tamano'], 1 if L['tamano'] > 1 else 2)}")
        half = len(L["plano"]) // 2
        b += path(pts[:half + 1], BLUE, 2) + path(pts[half:], ORANGE, 2)
        groups = []                               # las marcas de ángulo que coinciden comparten etiqueta
        for a in (0, 90, 180, 270):
            p = pts[a // 2]
            for g in groups:
                if math.hypot(g["p"][0] - p[0], g["p"][1] - p[1]) < 12:
                    g["a"].append(a)
                    break
            else:
                groups.append({"a": [a], "p": p})
        gx, gy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
        for g in groups:
            x, y = g["p"]
            b += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.4" fill="{INK}" stroke="{PAPER}" stroke-width="1.6"/>'
            n = math.hypot(x - gx, y - gy) or 1
            lx, ly = x + (x - gx) / n * 10, y + (y - gy) / n * 10 + 3
            anchor = "start" if lx > x + 3 else "end" if lx < x - 3 else "middle"
            text = " y ".join(f"{a}°" for a in g["a"])
            tw = len(text) * 4.4
            if (anchor == "start" and lx + tw > x0 + pw - 3) or (anchor == "end" and lx - tw < x0 + 3):
                left = x < gx                                            # no cabe fuera: dentro del lazo, escalonadas
                lx, ly, anchor = (x + 9, y - 4, "start") if left else (x - 9, y + 11, "end")
            b += T(lx, ly, text, 8.5, anchor, INK)

    x0, top = pos[3]
    b += frame(x0, top, "Los tres, a la misma escala", "el toro se reduce casi a un punto")
    loops = {o: DATA["lazos"][o]["plano"] + DATA["lazos"][o]["plano"][:1] for o in ["74", "67", "47"]}
    widths = {o: bounds_of(c)[1] - bounds_of(c)[0] for o, c in loops.items()}
    heights = {o: bounds_of(c)[3] - bounds_of(c)[2] for o, c in loops.items()}
    gap = 12
    s = min((pw - 20 - 2 * gap) / sum(widths.values()), (ph - 40) / max(heights.values()))
    x = x0 + (pw - (sum(widths.values()) * s + 2 * gap)) / 2
    for o in ["74", "47", "67"]:
        cx, cy = x + widths[o] * s / 2, top + ph / 2 - 4
        b += path(place(loops[o], cx, cy, s), INK2, 1.2)
        if o == "47":
            b += f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="7" fill="none" stroke="{INK}" stroke-width="0.8"/>'
        b += T(cx, top + ph - 8, f"obj{o}", 8.5, "middle")
        x += widths[o] * s + gap
    return svg(COL, pos[3][1] + ph + 17, b, "Lazos de tres objetos, cada uno en su plano principal", "laz")


# ------------------------------------------------------------------ Fig.: perfil de distancia y distribución
def fig_posterior():
    titles = {"74": "obj74, vista de 45°", "67": "obj67, vista de 105°", "47": "obj47, vista de 45°"}
    pw, gap, left = 196, 30, 34
    b = ""
    rows = [("d", "Distancia al lazo", 22, 86), ("w", "Probabilidad", 128, 86)]
    for i, o in enumerate(["74", "67", "47"]):
        P = DATA["posterior"][o]
        x0 = left + i * (pw + gap)
        b += T(x0 + pw / 2, 10, titles[o], 9.5, "middle", weight="bold")
        w = P["w"]
        order = sorted(w, reverse=True)
        acc, cut = 0.0, order[-1]
        for v in order:
            acc += v
            if acc >= 0.9:
                cut = v
                break
        for key, ylabel, top, h in rows:
            vals = P[key]
            vmax = max(vals) * 1.08
            yb = top + h
            b += f'<line x1="{x0}" y1="{yb}" x2="{x0 + pw}" y2="{yb}" stroke="{AXIS}" stroke-width="1"/>'
            b += f'<line x1="{x0}" y1="{top}" x2="{x0 + pw}" y2="{top}" stroke="{GRID}" stroke-width="1"/>'
            b += T(x0 - 4, top + 3.5, es(vmax / 1.08, 2 if vmax < 2 else 1), 8, "end", MUTED) + T(x0 - 4, yb + 3, "0", 8, "end", MUTED)
            if i == 0:
                b += T(0, top - 6, ylabel, 8.5, fill=INK2)
            X = lambda k: x0 + pw * k / len(vals)
            Y = lambda v: yb - h * v / vmax
            if key == "w":
                k = 0
                while k < len(vals):          # conjunto creíble del 90 %: tramos de mayor probabilidad
                    if w[k] >= cut:
                        j = k
                        while j < len(vals) and w[j] >= cut:
                            j += 1
                        seg = " L".join(f"{X(m):.1f} {Y(vals[m]):.1f}" for m in range(k, j))
                        b += f'<path d="M{X(k):.1f} {yb} L{seg} L{X(j - 1):.1f} {yb}Z" fill="{BLUE}" fill-opacity="0.22"/>'
                        k = j
                    else:
                        k += 1
            d = "M" + " L".join(f"{X(k):.1f} {Y(v):.1f}" for k, v in enumerate(vals))
            b += f'<path d="{d}" fill="none" stroke="{BLUE}" stroke-width="1.6" stroke-linejoin="round"/>'
            xt = x0 + pw * P["consulta"] / 360
            b += f'<path d="M{xt:.1f} {yb + 1}l-3.5 6h7z" fill="{INK}"/>'
            if key == "w":
                for a in (0, 90, 180, 270, 360):
                    b += T(x0 + pw * a / 360, yb + 18, f"{a}°", 8, "middle", MUTED)
        verdict = {"74": "actúa", "67": "no actúa: ambigüedad", "47": "no actúa: ancho"}[o]
        b += T(x0 + pw / 2, 248, f"estimado {es(P['angulo'])}° · ancho {es(P['ancho'])}° · ambigüedad {es(P['ambiguedad'], 2)}",
               8.5, "middle", INK2)
        b += T(x0 + pw / 2, 261, verdict, 9, "middle", weight="bold")
    b += f'<path d="M{left} 277l-3.5 6h7z" fill="{INK}"/>' + T(left + 8, 284, "ángulo real de la vista", 8.5, fill=INK2)
    b += f'<rect x="{left + 130}" y="275" width="10" height="10" rx="2" fill="{BLUE}" fill-opacity="0.22"/>'
    b += T(left + 145, 284, "conjunto creíble del 90 %", 8.5, fill=INK2)
    return svg(WIDE, 290, b, "Perfil de distancia al lazo y distribución sobre el ángulo en tres vistas de prueba", "pos")


# ------------------------------------------------------------------ Fig.: ángulo por protocolo y modelo
def fig_resultados():
    key = "pose_true_class.within_tol"
    groups = [("A", "vistas cada 10°"), ("C", "12 vistas"), ("B", "arco no visto")]
    series = [("baseline", "Referencia simple", GRAY), ("final", "Lazos (propuesto)", BLUE), ("reference", "Lazos sobre DINOv2", ORANGE)]
    x0, x1, yb, yt = 30, COL, 162, 42
    b = legend(0, 10, [(c, n, "bar") for _, n, c in series[:2]]) + legend(0, 24, [(series[2][2], series[2][1], "bar")])
    b += y_axis(x0, x1, yb, yt, [0, 25, 50, 75, 100], 100)
    band = (x1 - x0) / len(groups)
    for i, (p, sub) in enumerate(groups):
        cx = x0 + band * (i + 0.5)
        for j, (blk, _, color) in enumerate(series):
            v = mean_of(blk, p, key)
            x = cx - 35 + j * 24
            h = (yb - yt) * v / 100
            b += col_bar(x, yb, 22, h, color)
            if blk == "final":
                b += T(x + 11, yb - h - 4, es(v), 8.5, "middle", INK, "bold")
        b += T(cx, yb + 13, f"Protocolo {p}", 9.5, "middle", weight="bold") + T(cx, yb + 25, sub, 9, "middle", INK2)
    b += T(0, 40, "%", 8.5, fill=MUTED)
    return svg(COL, 192, b, "Ángulo dentro de la tolerancia por protocolo y modelo", "res")


# ------------------------------------------------------------------ Fig.: arquitectura del asistente
def fig_agente():
    f, b = "age", ""
    b += box(0, 96, 92, 44, ["Personal", "de planta"])
    b += box(116, 96, 92, 44, ["API e", "interfaz web"]) + icon("fastapi", 122, 101)
    b += arrow([(92, 118), (115, 118)], f, both=True)
    b += f'<rect x="232" y="6" width="288" height="226" rx="6" fill="{PAPER}" stroke="{INK2}" stroke-width="0.8"/>'
    b += T(376, 22, "Bucle del agente (harness propio)", 9.5, "middle", weight="bold")
    b += box(244, 32, 264, 38, ["Contexto del turno", "resumen + últimos 24 mensajes + tools del rol"], size=9)
    b += box(244, 100, 100, 40, ["LLM", "propone texto o tool"], size=9) + icon("googlegemini", 250, 105)
    b += box(388, 100, 120, 40, ["Capa de política", "valida · autoriza · audita"], fill=BLUE_TINT, stroke=BLUE, size=9)
    b += box(244, 170, 264, 50, ["Límites del turno", "8 llamadas al LLM · 12 tools · 60.000 tokens",
                                 "la tercera llamada idéntica se bloquea"], size=9)
    b += arrow([(208, 118), (243, 118)], f, both=True)
    b += arrow([(294, 70), (294, 99)], f)
    b += arrow([(344, 112), (387, 112)], f) + T(366, 107, "tool", 8.5, "middle", INK2)
    b += arrow([(388, 129), (345, 129)], f) + T(366, 141, "JSON", 8.5, "middle", INK2)
    b += arrow([(294, 169), (294, 141)], f)
    right = [(14, ["Servicio de visión", "identidad, ángulo, decisión"], "scikitlearn"),
             (66, ["Planta simulada", "eventos, casos, tickets"], "sqlite"),
             (118, ["Procedimientos", "búsqueda BM25 con cita"], None),
             (184, ["Aprobación humana", "recibe la solicitud y decide"], None)]
    for y, lines, ic in right:
        b += box(552, y, 143, 40, lines, size=9)
        if ic:
            b += icon(ic, 558, y + 5)
        b += arrow([(508, 120), (530, 120), (530, y + 20), (551, y + 20)], f)
    b += icon("docker", 0, 219, 12) + T(17, 229, "Dos contenedores: visión y asistente", 8.5, fill=INK2)
    return svg(WIDE, 238, b, "El LLM propone y la capa de política ejecuta; las operaciones de riesgo pasan por una persona", f)


# ------------------------------------------------------------------ Fig.: evaluación del agente
def tabla_categorias():
    text = (ROOT / "reports" / "agent_eval.md").read_text(encoding="utf-8")
    sec = text[text.index("## Por categoría"):text.index("## Por caso")]
    out = []
    for line in sec.splitlines():
        m = re.match(r"\| ([a-zó ]+) \| (\d+) \| (\d+) % \((\d+)/(\d+)\)", line)
        if m:
            out.append((m.group(1), int(m.group(2)), int(m.group(4)), int(m.group(5))))
    assert len(out) == 8, out
    return out


def fig_eval():
    cats = tabla_categorias()
    x0, top, rh = 108, 18, 19
    xmax = COL - 72
    b = ""
    for t in (0, 50, 100):
        x = x0 + (xmax - x0) * t / 100
        b += f'<line x1="{x:.1f}" y1="{top - 4}" x2="{x:.1f}" y2="{top + len(cats) * rh}" stroke="{AXIS if t == 0 else GRID}" stroke-width="1"/>'
        b += T(x, top - 8, f"{t} %", 8.5, "middle", MUTED)
    for i, (name, n, ok, tot) in enumerate(cats):
        y = top + i * rh
        b += T(x0 - 6, y + 12.5, f"{name.capitalize()} ({n})", 9, "end")
        wbar = (xmax - x0) * ok / tot
        b += row_bar(x0, y + 3, wbar, 13, BLUE)
        b += T(x0 + wbar + 7, y + 12.5, f"{round(100 * ok / tot)} % ({ok}/{tot})", 8.5, fill=INK)
    return svg(COL, top + len(cats) * rh + 4, b, "Éxito de la tarea por categoría en la evaluación del asistente", "eva")


FIGURAS = {"sistema": fig_sistema, "montaje": fig_montaje, "knn": fig_knn, "protocolos": fig_protocolos,
           "seleccion": fig_seleccion, "pipeline": fig_pipeline, "lazos": fig_lazos, "posterior": fig_posterior,
           "resultados": fig_resultados, "agente": fig_agente, "eval": fig_eval}

if __name__ == "__main__":
    html = "".join(f"<h3>{k}</h3>{f()}" for k, f in FIGURAS.items())
    (HERE / "_vista_figuras.html").write_text(f'<meta charset="utf-8"><body style="margin:20px">{html}', encoding="utf-8")
    print("ok")
