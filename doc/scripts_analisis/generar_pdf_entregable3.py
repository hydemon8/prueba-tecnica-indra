"""Genera el PDF del entregable 3: reporte por protocolo, análisis de errores y model card.

Las cifras por protocolo se leen de `reports/results.json`; el resto del contenido resume los documentos 8 y 9 y
`reports/model_card.md`. Requiere reportlab (`pip install reportlab`).

Uso, desde la raíz del repositorio:
    python doc/scripts_analisis/generar_pdf_entregable3.py
"""
import json
from pathlib import Path

import numpy as np
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import CondPageBreak, Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "entregable_3_reporte_errores_model_card.pdf"
RESULTS = json.loads((ROOT / "reports" / "results.json").read_text(encoding="utf-8"))
IMG = ROOT / "doc" / "img"

FONT, BOLD, ITALIC = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"
arial = Path(r"C:\Windows\Fonts")
if (arial / "arial.ttf").exists():
    pdfmetrics.registerFont(TTFont("A", str(arial / "arial.ttf")))
    pdfmetrics.registerFont(TTFont("AB", str(arial / "arialbd.ttf")))
    pdfmetrics.registerFont(TTFont("AI", str(arial / "ariali.ttf")))
    pdfmetrics.registerFontFamily("A", normal="A", bold="AB", italic="AI", boldItalic="AB")
    FONT, BOLD, ITALIC = "A", "AB", "AI"

INK, ACC, SOFT, LINE = colors.HexColor("#1c2526"), colors.HexColor("#00495a"), colors.HexColor("#eef3f2"), colors.HexColor("#c9d3d1")
WARN = colors.HexColor("#fbf1e2")
W = A4[0] - 36 * mm

S = {
    "title": ParagraphStyle("title", fontName=BOLD, fontSize=20, leading=24, textColor=ACC, spaceAfter=2),
    "sub": ParagraphStyle("sub", fontName=FONT, fontSize=10.5, leading=14, textColor=colors.HexColor("#556666"), spaceAfter=8),
    "part": ParagraphStyle("part", fontName=BOLD, fontSize=16, leading=20, textColor=ACC, spaceBefore=4, spaceAfter=6, keepWithNext=1),
    "h1": ParagraphStyle("h1", fontName=BOLD, fontSize=12.5, leading=16, textColor=ACC, spaceBefore=10, spaceAfter=4, keepWithNext=1),
    "p": ParagraphStyle("p", fontName=FONT, fontSize=9.6, leading=13.4, textColor=INK, spaceAfter=4),
    "pk": ParagraphStyle("pk", fontName=FONT, fontSize=9.6, leading=13.4, textColor=INK, spaceAfter=4, keepWithNext=1),
    "b": ParagraphStyle("b", fontName=FONT, fontSize=9.6, leading=13.2, textColor=INK, leftIndent=11, bulletIndent=2, spaceAfter=2),
    "cell": ParagraphStyle("cell", fontName=FONT, fontSize=8.4, leading=10.8, textColor=INK),
    "head": ParagraphStyle("head", fontName=BOLD, fontSize=8.4, leading=10.8, textColor=colors.white),
    "note": ParagraphStyle("note", fontName=ITALIC, fontSize=8.6, leading=11.6, textColor=colors.HexColor("#445555"), spaceAfter=5),
}
story = []


def part(t): story.append(Paragraph(t, S["part"]))
def h1(t): story.append(Paragraph(t, S["h1"]))
def p(t, keep=False): story.append(Paragraph(t, S["pk" if keep else "p"]))
def note(t): story.append(Paragraph(t, S["note"]))


def bl(items):
    story.extend(Paragraph(i, S["b"], bulletText="•") for i in items)
    story.append(Spacer(1, 2))


def box(text, bg=SOFT):
    t = Table([[Paragraph(text, S["p"])]], colWidths=[W])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg), ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                           ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                           ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    story.extend([Spacer(1, 2), t, Spacer(1, 6)])


def table(rows, widths, keep=True):
    data = [[Paragraph(c, S["head"]) for c in rows[0]]] + [[Paragraph(str(c), S["cell"]) for c in r] for r in rows[1:]]
    t = Table(data, colWidths=[W * w for w in widths], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), ACC), ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SOFT]), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    story.extend([KeepTogether([t]) if keep else t, Spacer(1, 6)])


def figure(name, caption, width=W):
    from reportlab.lib.utils import ImageReader
    w, h = ImageReader(str(IMG / name)).getSize()
    story.append(KeepTogether([Image(str(IMG / name), width=width, height=width * h / w), Spacer(1, 2),
                               Paragraph(caption, S["note"])]))


# ------------------------------------------------------------------ cifras desde results.json
def get(d, key):
    for k in key.split("."):
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def cell(runs, key, pct=True, dec=1):
    """Media (± desviación si hay varias repeticiones) de una métrica; '—' si no aplica."""
    vals = [get(r, key) for r in runs]
    vals = [v for v in vals if v is not None and not (isinstance(v, float) and np.isnan(v))]
    if not vals:
        return "—"
    k = 100 if pct else 1
    m, s = np.mean(vals) * k, np.std(vals) * k
    txt = f"{m:.{dec}f}" + (f" ± {s:.{dec}f}" if len(runs) > 1 and round(s, dec) > 0 else "")
    return txt.replace(".", ",")


def runs_of(block, proto):
    r = RESULTS[block][proto]
    return r if isinstance(r, list) else [r]




PROTOS = ["A", "B", "C", "D"]
MODELS = [("baseline", "Baseline PCA + 1-NN"), ("final", "<b>Clásico HSV + RF</b>"), ("reference", "Referencia DINOv2")]


def c(block, proto, key, pct=True, dec=1):
    return cell(runs_of(block, proto), key, pct, dec)


def es(value, dec=1):
    """Número con coma decimal."""
    return f"{value:.{dec}f}".replace(".", ",")


two = RESULTS["two_shot"]
two_mean = {k: float(np.mean([t[k] for t in two])) for k in two[0] if k != "delta_deg"}
risk_on_act_A = 100 * (1 - runs_of("final", "A")[0]["pose_on_act"]["within_tol"])
acts = {x: float(np.mean([r["decision"]["rate_ACT"] for r in runs_of("final", x)])) for x in PROTOS}

# ------------------------------------------------------------------ portada
story.append(Paragraph("Reto 2 — Reporte por protocolo, análisis de errores y model card", S["title"]))
story.append(Paragraph("Entregable 3. Reconocimiento de producto y ángulo para pick &amp; pack con ML clásico sobre "
                       f"COIL-100. Modelo <b>linevision 4e39f878-rf</b> ({RESULTS['selection_winner']}).", S["sub"]))

h1("Resumen")
bl([f"<b>Identidad</b>: {c('final', 'A', 'class_acc')} % en A, {c('final', 'B', 'class_acc')} % en B y "
    f"{c('final', 'C', 'class_acc')} % en C. Clasificar no es la dificultad de este problema.",
    f"<b>Ángulo dentro de ±10°</b>: {c('final', 'A', 'pose_true_class.within_tol')} % con vistas cada 10° (A), "
    f"{c('final', 'C', 'pose_true_class.within_tol')} % con 12 vistas por producto (C) y "
    f"{c('final', 'B', 'pose_true_class.within_tol')} % en una cara nunca vista (B).",
    f"<b>Seguridad</b>: el robot actúa en el {c('final', 'A', 'decision.rate_ACT')} % de los casos de A con "
    f"{c('final', 'A', 'decision.unsafe_rate')} % de acciones inseguras; en B, C y D no produce ninguna. El baseline "
    f"sin control produce {c('baseline', 'A', 'decision.unsafe_rate')} %, {c('baseline', 'B', 'decision.unsafe_rate')} %, "
    f"{c('baseline', 'C', 'decision.unsafe_rate')} % y {c('baseline', 'D', 'decision.unsafe_rate')} %.",
    f"<b>Objetos desconocidos</b>: se rechaza el {c('final', 'D', 'unknown_rejected')} %.",
    f"<b>Objetivo no alcanzado</b>: de las veces que el robot actúa en A, el {es(risk_on_act_A)} % queda fuera de ±10°; "
    "el objetivo era 0,5 %.",
    "<b>Fuera del laboratorio</b>: un objeto desplazado 8 px produce 10,5 % de acciones inseguras, y un cambio de "
    "brillo de +15 % hace rechazar el 66 % del producto conocido. Son las dos correcciones previas a un piloto."])
note("Todas las cifras por protocolo salen de reports/results.json, generado por el notebook. La prueba de cada "
     "protocolo se evaluó una sola vez; ningún umbral se ajustó con ella.")

# ------------------------------------------------------------------ parte 1
part("Parte 1 — Reporte por protocolo")

h1("1.1 Qué mide cada protocolo")
p("Un protocolo es una forma de repartir las fotos entre entrenamiento y prueba para poner a prueba una capacidad. "
  "El sistema y el código son los mismos en los cuatro; cambia con qué fotos se entrena.")
table([["Protocolo", "Entrena / prueba (por objeto)", "Pregunta", "Imágenes"],
       ["A — Interpolación", "Vistas a 0°, 10°, 20°… / vistas a 5°, 15°…", "¿Estima bien entre vistas conocidas?", "3.600 / 3.600"],
       ["B — Sector ciego", "Todo menos un arco de 60° / ese arco", "¿Qué hace ante una cara nunca vista?", "6.000 / 1.200"],
       ["C — Escasez", "1 vista cada 30° (12) / las 60 restantes", "¿Sirve un producto nuevo con pocas fotos?", "1.200 / 6.000"],
       ["D — Desconocido", "90 objetos / 10 objetos excluidos", "¿Sabe decir «no lo conozco»?", "6.480 / 720"]],
      [0.19, 0.33, 0.33, 0.15])
note("B y D dependen de un sorteo (dónde cae el arco, qué objetos se excluyen): se repiten con 3 semillas y se reporta "
     "media ± desviación.")

h1("1.2 Resultados del sistema final (%)")
table([["Protocolo", "Clase correcta", "Ángulo ±10° (clase dada)", "Ídem contando simetría", "Mediana del error (°)"]] +
      [[x, c("final", x, "class_acc"), c("final", x, "pose_true_class.within_tol"),
        c("final", x, "pose_true_class_sym.within_tol"), c("final", x, "pose_true_class.median", pct=False)]
       for x in PROTOS],
      [0.16, 0.19, 0.24, 0.22, 0.19])
table([["Protocolo", "Actúa (ACT)", "Ángulo no certificado", "Revisión", "Desconocido", "<b>Acciones inseguras</b>",
        "±10° cuando actúa"]] +
      [[x, c("final", x, "decision.rate_ACT"), c("final", x, "decision.rate_ANGLE_UNCERTIFIED"),
        c("final", x, "decision.rate_REVIEW"), c("final", x, "decision.rate_UNKNOWN"),
        f"<b>{c('final', x, 'decision.unsafe_rate')}</b>",
        c("final", x, "pose_on_act.within_tol") if acts[x] > 0 else "—"] for x in PROTOS],
      [0.13, 0.13, 0.16, 0.13, 0.15, 0.16, 0.14])
bl(["<b>Ángulo ±10° (clase dada)</b>: se mide el ángulo suponiendo conocido el producto, para separar el error del "
    "estimador de ángulo del error de identidad.",
    "<b>Acción insegura</b>: el robot actúa con el producto equivocado o con el ángulo fuera de ±10°. Es la métrica "
    "que decide si el sistema sirve.",
    "Las cuatro decisiones suman 100 %: actuar, pedir segunda captura (ángulo no certificado), enviar a revisión o "
    "rechazar por desconocido."])

h1("1.3 Lectura por protocolo")
bl([f"<b>A</b>: el robot actúa en el {c('final', 'A', 'decision.rate_ACT')} % y el "
    f"{c('final', 'A', 'pose_on_act.within_tol')} % de esas acciones queda dentro de ±10°. El objetivo de 99,5 % se "
    "cumplió en validación interna (error 0,47 %) y no del todo en prueba; el motivo está en la sección 2.5.",
    f"<b>B</b>: la identidad se mantiene ({c('final', 'B', 'class_acc')} %). Con una sola imagen el ángulo en el arco "
    f"acierta el {c('final', 'B', 'pose_true_class.within_tol')} %, así que <b>por política el robot no actúa</b> sobre "
    "productos sin cobertura angular completa. Con una segunda captura se recupera (1.5).",
    f"<b>C</b>: clase {c('final', 'C', 'class_acc')} % y ángulo {c('final', 'C', 'pose_true_class.within_tol')} %, pero el "
    "sistema <b>no se certifica a sí mismo</b>: con 12 vistas, la validación interna tiene huecos de 60° y no puede "
    "demostrar el criterio de aceptación. No actúa. Es conservador y coherente con exigir una galería más densa al dar "
    "de alta un producto.",
    f"<b>D</b>: {c('final', 'D', 'unknown_rejected')} % de los objetos nuevos rechazados y ninguna acción insegura."])

h1("1.4 Comparación con el baseline y la referencia moderna (%)")
table([["Protocolo", "Modelo", "Clase", "Ángulo ±10° (clase dada)", "<b>Acciones inseguras</b>", "Desconocidos rechazados"]] +
      [[x, name, c(b, x, "class_acc"), c(b, x, "pose_true_class.within_tol"), c(b, x, "decision.unsafe_rate"),
        c(b, x, "unknown_rejected")] for x in PROTOS for b, name in MODELS],
      [0.11, 0.25, 0.14, 0.19, 0.15, 0.16], keep=False)
p("El <b>baseline</b> es PCA sobre píxeles con vecino más cercano y sin control de seguridad: actúa siempre. La "
  "<b>referencia moderna</b> es DINOv2 (unos 22 M de parámetros) como extractor de características, con el mismo "
  "control de seguridad.")
box("<b>¿Justifica la referencia moderna su costo? No.</b> DINOv2 mejora la identidad menos de un punto en B y C, pero "
    f"empeora el ángulo (B: {c('reference', 'B', 'pose_true_class.within_tol')} % frente a "
    f"{c('final', 'B', 'pose_true_class.within_tol')} %; C: {c('reference', 'C', 'pose_true_class.within_tol')} % frente a "
    f"{c('final', 'C', 'pose_true_class.within_tol')} %) y el rechazo de desconocidos "
    f"({c('reference', 'D', 'unknown_rejected')} % frente a {c('final', 'D', 'unknown_rejected')} %), y pide GPU. El "
    "sistema clásico es mejor en las métricas que determinan la seguridad del agarre.")

story.append(CondPageBreak(60 * mm))
h1("1.5 Sector ciego con segunda captura (protocolo B)")
p("Cuando el ángulo no está certificado, el objeto se gira 180° (o se usa una segunda cámara) y se estima de nuevo.", keep=True)
TWO_COLS = [("within_tol_all", 100, " %"), ("act_rate", 100, " %"), ("within_tol_on_act", 100, " %"),
            ("unsafe_rate", 100, " %"), ("mae_on_act", 1, "°")]
table([["Semilla", "Ángulo ±10° (todos)", "El robot actúa", "±10° cuando actúa", "Acciones inseguras", "Error medio al actuar"]] +
      [[str(2026 + i)] + [es(t[k] * m, 2) + u for k, m, u in TWO_COLS] for i, t in enumerate(two)] +
      [["<b>Media</b>"] + [f"<b>{es(two_mean[k] * m, 2)}{u}</b>" for k, m, u in TWO_COLS]],
      [0.12, 0.19, 0.16, 0.18, 0.18, 0.17])

h1("1.6 Primera iteración frente a la final")
p("La primera evaluación (v1) dio 1,0 % de acciones inseguras en A. El problema ya era visible en validación interna, "
  "así que se corrigió sin usar la prueba: se añadió una regla de ambigüedad al control y se recalibró la "
  "incertidumbre. La identidad y el estimador de ángulo no cambiaron.")
table([["Protocolo", "Métrica", "v1", "v2 (final)"],
       ["A", "Actúa / inseguras / ±10° cuando actúa", "87,9 % / <b>1,0 %</b> / 98,8 %", "87,6 % / <b>0,7 %</b> / 99,2 %"],
       ["C", "Actúa / inseguras", "10,4 % / 0,2 %", "0 % / 0 %"],
       ["D", "Inseguras / desconocidos rechazados", "0,1 % / 99,8 %", "0,0 % / 99,8 %"],
       ["B con 2ª captura", "Actúa / inseguras", "5,7–9,5 % / 0–0,17 %", "93,3–94,3 % / 0,5–1,0 %"]],
      [0.17, 0.33, 0.25, 0.25])
note("Resultados de v1 en reports/results_v1.json.")

h1("1.7 Latencia")
table([["Medida", "Valor", "Condición"],
       ["Decisión con características ya extraídas", "0,1–0,3 ms por imagen", "En lote; es la cifra de results.json"],
       ["Imagen → decisión, en lote", "1,5–2,1 ms por imagen", "CPU, lotes de 64 o más"],
       ["<b>Imagen → decisión, una sola imagen</b>", "<b>≈ 28 ms</b> (p95 29 ms)",
        "CPU, a través del servicio; es la cifra relevante para la línea"],
       ["Referencia DINOv2, solo el embedding", "8,6 ms por imagen", "GPU de un Mac (MPS)"]],
      [0.38, 0.24, 0.38])
p("Con una sola imagen, el Random Forest de 500 árboles ocupa 24 de los 28 ms. Sigue muy por debajo del ciclo de una "
  "línea de empaque.")

# ------------------------------------------------------------------ parte 2
story.append(PageBreak())
part("Parte 2 — Análisis de errores")

h1("2.1 Errores de identidad")
p("En C, el protocolo con menos fotos, las confusiones se concentran en pocos pares (verdadero → predicho, número de "
  "imágenes): 51→12 (7), 11→12 (4), 51→80 (3), 12→77 (2), 41→80 (2), 80→41 (2), 9→97 (1), 51→41 (1). Son piezas de "
  "madera y objetos del mismo tono: la identidad se apoya en el color y dos objetos del mismo color se parecen.")
figure("errores_pares_confundidos.png", "Pares más confundidos en el protocolo C.", W * 0.9)

h1("2.2 Errores de ángulo")
p("Objetos con mayor error de ángulo en A (clase dada):", keep=True)
table([["Objeto", "Error medio", "Dentro de ±10°"], ["obj95", "13,8°", "58 %"], ["obj50", "12,8°", "69 %"],
       ["obj47 (rosca)", "7,1°", "67 %"], ["obj25, obj94, obj18, obj34, obj83", "5,9°–6,6°", "—"]], [0.5, 0.25, 0.25])
bl(["Son objetos que se ven casi igual desde varios ángulos: el ángulo no se puede observar en la imagen. No es un "
    "fallo de ajuste.",
    "Ningún error supera 150°: no hay confusiones «frente por espalda» en A.",
    "Diez objetos tienen simetría de orden 2 (se ven igual cada 180°), detectada sin mirar la prueba: 1, 12, 31, 33, "
    "65, 66, 67, 79, 84 y 98. Por eso se reporta también el acierto contando la simetría."])

h1("2.3 Sector ciego")
p("En el arco nunca visto (B, semilla 2026) el ángulo de una sola imagen cae dentro de ±10° en el 53,8 % de los casos "
  "y el 17,7 % de los errores supera 90°. El estimador no puede extrapolar a una cara que no conoce, y con una sola "
  "imagen tampoco puede saber con fiabilidad que está en esa zona. Por eso la protección es una <b>regla de "
  "catálogo</b>: si la galería de un producto tiene un hueco mayor de 30°, su ángulo no se certifica. Decisiones en "
  "el arco: ángulo no certificado 94,2 %, revisión 4,6 %, desconocido 1,3 %.")

h1("2.4 Confianza y novedad")
figure("riesgo_cobertura_y_novedad.png", "Izquierda: al aceptar solo los casos con más confianza, el error baja. "
       "Derecha: la novedad separa los objetos conocidos de los desconocidos.")

h1("2.5 El objetivo de riesgo no se alcanzó del todo")
box("El control se calibró para que, cuando el robot actúa, como máximo el 0,5 % quede fuera de ±10°. En validación "
    f"interna dio 0,47 %. En la prueba de A dio <b>{es(risk_on_act_A, 2)} %</b>.", WARN)
bl(["<b>Causa</b>: la validación interna se construye solo con vistas de entrenamiento. En A hay que quitar una de "
    "cada dos, y queda una vista cada 20° en lugar de cada 10°. Esa validación no representa exactamente la prueba.",
    "<b>Mejora prevista</b>: elegir el umbral con una cota superior de confianza del error en lugar de su valor "
    "puntual, lo que deja margen para esa diferencia.",
    "<b>Qué no se hizo</b>: reajustar el umbral mirando la prueba. Habría dado la cifra buscada y un resultado sin valor."])

h1("2.6 Pruebas funcionales: casos individuales")
p("Hechas después de cerrar el modelo, sobre el artefacto final. No usan la prueba de los protocolos: son imágenes "
  "del catálogo alteradas e imágenes sintéticas.")
table([["Caso", "Decisión", "Detalle", "Valoración"],
       ["Nominal, obj5 a 40°", "ACT", "Confianza 0,97; ángulo 40,0°", "Correcto"],
       ["Brillo +15 %", "UNKNOWN", "Novedad 0,361 &gt; 0,185", "Seguro, pero rechaza producto conocido"],
       ["Brillo −30 %", "UNKNOWN", "Novedad 0,485", "Ídem"],
       ["Ruido σ = 8", "UNKNOWN", "Novedad 0,222", "Ídem"],
       ["Desenfoque r = 1,5", "ACT", "Error 0°", "Correcto"],
       ["Desplazado 10 px", "ACT", "Error 5,5°", "Correcto, dentro de tolerancia"],
       ["Escala 80 %", "ANGLE_UNCERTIFIED", "Estimó con 51° de error; ambigüedad 0,86 &gt; 0,77", "Seguro: el control lo detectó"],
       ["<b>Volcado 90° en el plano</b>", "<b>ACT</b>", "Novedad 0,000; ángulo sin sentido", "<b>Inseguro</b>"],
       ["Ocluido al 50 %", "UNKNOWN", "Novedad 0,196", "Seguro"],
       ["Mismo empaque en otro color", "UNKNOWN", "Novedad 1,001", "Correcto: es otro producto"],
       ["Ruido puro / imagen negra", "UNKNOWN", "Novedad 1,08 / 1,35", "Correcto"],
       ["Rosca obj47 a 90°", "ANGLE_UNCERTIFIED", "Ancho de incertidumbre 51,5°", "Correcto: ángulo inobservable"]],
      [0.24, 0.23, 0.29, 0.24], keep=False)

h1("2.7 Robustez sistemática")
p("200 imágenes del catálogo al azar, cada una con cada alteración. Se compara el modelo elegido con el segundo del "
  "criterio de selección (HSV + HOG + LBP con regresión logística). En %.")
table([["Captura", "Modelo", "Actúa", "<b>Inseguras</b>", "Desconocido", "Clase correcta"],
       ["Limpia", "Elegido", "97,0", "0,0", "0,0", "100,0"], ["Limpia", "Segundo", "97,0", "0,0", "0,0", "100,0"],
       ["Brillo +15 %", "Elegido", "25,5", "2,0", "66,0", "94,0"], ["Brillo +15 %", "Segundo", "61,5", "2,0", "0,5", "99,5"],
       ["Brillo −15 %", "Elegido", "6,0", "1,0", "87,0", "85,0"], ["Brillo −15 %", "Segundo", "42,0", "1,5", "1,5", "99,0"],
       ["Ruido σ = 4", "Elegido", "32,5", "0,0", "64,0", "86,0"], ["Ruido σ = 4", "Segundo", "26,5", "0,0", "73,5", "100,0"],
       ["Desenfoque r = 1", "Elegido", "81,0", "0,0", "15,0", "99,0"], ["Desenfoque r = 1", "Segundo", "97,0", "0,0", "0,0", "100,0"],
       ["<b>Desplazado 8 px</b>", "Elegido", "44,0", "<b>10,5</b>", "0,0", "100,0"],
       ["<b>Desplazado 8 px</b>", "Segundo", "42,0", "<b>9,0</b>", "7,5", "100,0"],
       ["Volcado 180°", "Elegido", "1,0", "1,0", "0,0", "100,0"], ["Volcado 180°", "Segundo", "0,0", "0,0", "92,5", "82,5"]],
      [0.24, 0.16, 0.13, 0.15, 0.16, 0.16], keep=False)
note("Tabla completa, con brillo −30 %, ruido σ = 8 y volcado 90°, en doc/09_pruebas_funcionales_y_robustez.md.")

h1("2.8 Diagnóstico y corrección propuesta")
table([["Fallo", "Gravedad", "Causa", "Corrección"],
       ["Objeto desplazado → ángulo erróneo con confianza", "<b>Seguridad</b>",
        "COIL-100 viene centrado y recortado; el estimador compara píxeles alineados",
        "Localizar, recortar y centrar el objeto antes de analizarlo, como hace COIL"],
       ["Cambio de brillo → ángulo erróneo (1–2,5 %)", "<b>Seguridad</b>",
        "La entrada del estimador de ángulo no normaliza el brillo", "Normalizar el brillo de esa entrada"],
       ["Objeto volcado → actúa en algunos casos", "<b>Seguridad</b>",
        "La novedad usa solo el color, que no cambia al girar la imagen",
        "Regla nueva: distancia de la imagen a la curva de su producto; si es alta, a revisión"],
       ["Brillo ±15 % o ruido leve → producto conocido rechazado", "Disponibilidad",
        "Identidad dominada por el color; umbral calibrado con capturas limpias",
        "Declarar condiciones nominales de captura, calibrar con ellas y añadir robustez al criterio de selección"]],
      [0.25, 0.13, 0.30, 0.32], keep=False)
p("El segundo modelo aguanta mejor la luz y detecta los volcados, pero falla igual con el desplazamiento: ese problema "
  "está en el estimador de ángulo, no en la identidad. Estas correcciones no están implementadas; son el primer "
  "trabajo de la fase 1 del plan de proyecto. Mientras tanto, el servicio de visión incluye una alerta que detecta "
  "una racha anómala de rechazos en una línea y la atribuye a la captura.")

# ------------------------------------------------------------------ parte 3
story.append(PageBreak())
part("Parte 3 — Model card")
table([["Campo", "Valor"],
       ["Modelo", "linevision 4e39f878-rf"],
       ["Artefacto", "artifacts/linevision-4e39f878-rf.joblib, con manifiesto (sha256, versión de datos, huella de configuración)"],
       ["Datos", "COIL-100, versión 4e39f8783785bc2d"],
       ["Tipo", "ML clásico; se ejecuta en CPU"]], [0.2, 0.8])

h1("Uso previsto")
p("Identificar el producto que llega a la estación de pick &amp; pack, estimar su giro sobre el eje vertical (0–360°) con "
  "una medida de incertidumbre, recuperar las vistas de referencia más parecidas y decidir de forma determinista si el "
  "robot puede actuar. Sustituye la tarea manual de identificación y alineación.")
p("<b>Salidas</b>: decisión (ACT, ANGLE_UNCERTIFIED, REVIEW o UNKNOWN) con sus motivos, producto, confianza de clase, "
  "puntuación de novedad, ángulo con el ancho del conjunto creíble del 90 %, y las vistas más parecidas por ángulo y "
  "por apariencia.")

h1("Cuándo no debe usarse")
bl(["Objetos fuera del catálogo: se rechazan como desconocidos, no se identifican.",
    "Productos sin cobertura angular completa en su galería (hueco mayor de 30°): el ángulo no se certifica y hace "
    "falta segunda captura o alineación manual.",
    "Escenas con varios objetos, oclusión, fondo no controlado, otra iluminación u otra cámara, sin recalibrar.",
    "Objetos volcados o inclinados: el modelo solo conoce el giro sobre el eje vertical."])

h1("Datos")
p("COIL-100: 100 objetos × 72 vistas cada 5°, 128×128 RGB, plato giratorio, fondo oscuro, imágenes recortadas y "
  "escaladas por objeto. Es un sustituto controlado de las imágenes de planta, no datos de planta.")

h1("Modelo")
table([["Pieza", "Método", "Cómo se fijó"],
       ["Identidad", "Histograma de color HSV (256 valores) + Random Forest de 500 árboles",
        "Elegido entre 35 candidatos con un criterio fijado antes de ver resultados: mejor peor caso entre las "
        "validaciones internas, con restricción de rechazo de desconocidos"],
       ["Novedad", "Distancia a la vista de referencia más cercana",
        "Umbral: cuantil 0,99 de los conocidos en validación interna"],
       ["Ángulo", "Espacio propio paramétrico (Murase y Nayar, 1995): PCA global de píxeles 32×32 y una curva cerrada "
                  "por objeto (spline cúbico periódico)",
        "La escala de la incertidumbre se calibra para que el conjunto creíble del 90 % cubra el 90 %"],
       ["Control de seguridad", "Reglas deterministas: desconocido → revisión → ángulo no certificado → actuar",
        "Umbrales calibrados en validación interna para que ≥ 99,5 % de las acciones queden dentro de ±10°"]],
      [0.17, 0.42, 0.41])

h1("Resultados")
table([["Protocolo", "Clase", "Ángulo ±10°", "Actúa", "Acciones inseguras", "Desconocidos rechazados"]] +
      [[x, c("final", x, "class_acc"), c("final", x, "pose_true_class.within_tol"), c("final", x, "decision.rate_ACT"),
        c("final", x, "decision.unsafe_rate"), c("final", x, "unknown_rejected")] for x in PROTOS],
      [0.15, 0.17, 0.17, 0.15, 0.18, 0.18])
p(f"Con segunda captura en B: ángulo dentro de ±10° en el {es(two_mean['within_tol_all'] * 100)} % de los casos; el "
  f"robot actúa en el {es(two_mean['act_rate'] * 100)} % con {es(two_mean['unsafe_rate'] * 100, 2)} % de acciones "
  "inseguras. Detalle y comparaciones en la parte 1.")

h1("Limitaciones conocidas")
bl(["El objetivo de riesgo (≤ 0,5 % de las acciones fuera de ±10°) se cumple en validación interna y no en la prueba "
    f"de A ({es(risk_on_act_A)} %).",
    "Con 12 vistas por producto el sistema no puede demostrar el criterio de aceptación y no actúa, aunque su ángulo "
    "acierte. Un producto necesita una galería más densa para certificarse.",
    "En objetos con simetría, el ángulo queda indeterminado salvo esa simetría. Para el agarre solo es válido si la "
    "pinza también es simétrica.",
    "Con una sola imagen no detecta de forma fiable que está ante una cara nunca vista; por eso la cobertura es una "
    "regla de catálogo.",
    "El color domina la identidad: cambios de luz o variantes de color del mismo empaque la degradan.",
    "No tolera objetos descentrados ni volcados (parte 2): antes de una planta hace falta localizar y centrar el objeto."])

h1("Versionado y reproducibilidad")
p("El notebook notebooks/01_reto2_experimentacion.ipynb reproduce todo de punta a punta con semillas fijas. Los "
  "experimentos quedan en MLflow (experimento reto2-coil100) y el modelo en su registro. El servicio de visión "
  "comprueba el sha256 del artefacto al arrancar.")


def footer(canvas, doc):
    canvas.setFont(FONT, 8)
    canvas.setFillColor(colors.HexColor("#778888"))
    canvas.drawString(18 * mm, 10 * mm, "Reto 2 — Reporte por protocolo, análisis de errores y model card")
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, str(doc.page))


SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=17 * mm,
                  title="Reto 2 — Reporte por protocolo, análisis de errores y model card",
                  author="Sara Guerra").build(story, onFirstPage=footer, onLaterPages=footer)
print(OUT)
