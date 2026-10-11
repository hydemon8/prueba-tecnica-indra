"""Genera el reporte técnico en formato de artículo IEEE (dos columnas) como HTML y lo imprime a PDF.

Uso, desde la raíz del repositorio:
    python doc/reporte_ieee/generar_reporte.py

Requiere `datos.json` (lo produce `calcular_datos.py`) y Chrome o Edge para imprimir el PDF. Las cifras por
protocolo se leen de `reports/results.json`.
"""
import subprocess
import sys
from pathlib import Path

import figuras as fg
from figuras import DATA, RESULTS, es, get, icon_path
from silabas import hyphenate_html

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT_HTML = HERE / "reporte.html"
OUT_PDF = ROOT / "reports" / "reporte_tecnico_ieee.pdf"

FIGS = ["montaje", "sistema", "knn", "protocolos", "seleccion", "pipeline", "lazos", "posterior", "resultados", "agente", "eval"]
TABS = ["feat", "valid", "ident", "gate", "res", "limites", "casos", "apiv", "apir", "apia", "stack"]
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]


def F(key):
    return f"Fig.&nbsp;{FIGS.index(key) + 1}"


def Tb(key):
    return f"Tabla&nbsp;{ROMAN[TABS.index(key)]}"


def figure(key, caption, wide=False):
    return (f'<figure class="{"wide" if wide else "col"}">{fg.FIGURAS[key]()}'
            f'<figcaption>Fig. {FIGS.index(key) + 1}.&ensp;{caption}</figcaption></figure>')


def table(key, title, head, rows, wide=False, widths=None, note=None):
    cols = "".join(f'<col style="width:{w}%">' for w in widths) if widths else ""
    th = "".join(f"<th>{h}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    foot = f'<div class="tnote">{note}</div>' if note else ""
    return (f'<figure class="tab {"wide" if wide else "col"}"><div class="tcap">Tabla {ROMAN[TABS.index(key)]}<br>'
            f'<span>{title}</span></div><table><colgroup>{cols}</colgroup><thead><tr>{th}</tr></thead><tbody>{body}</tbody>'
            f'</table>{foot}</figure>')


def runs(block, proto):
    return RESULTS[block][proto]


def c(block, proto, key, dec=1):
    """Media (± desviación si el protocolo se repite con varias semillas), en %."""
    vals = []
    for r in runs(block, proto):
        try:
            vals.append(get(r, key) * 100)
        except (KeyError, TypeError):
            pass
    if not vals:
        return "—"
    m = sum(vals) / len(vals)
    s = (sum((v - m) ** 2 for v in vals) / len(vals)) ** 0.5
    return es(m, dec) + (f" ± {es(s, dec)}" if len(vals) > 1 and round(s, dec) > 0 else "")


def ico(slug):
    return (f'<svg viewBox="0 0 24 24" width="10" height="10" style="vertical-align:-1px;margin-right:3px" aria-hidden="true">'
            f'<path d="{icon_path(slug)}" fill="#52514e"/></svg>')


two = RESULTS["two_shot"]
two_m = {k: sum(t[k] for t in two) / len(two) for k in two[0] if k != "delta_deg"}
risk_A = 100 * (1 - runs("final", "A")[0]["pose_on_act"]["within_tol"])
two_risk = 100 * (1 - two_m["within_tol_on_act"])
P, L = DATA["posterior"], DATA["lazos"]

CSS = """
@page { size: 8.5in 11in; margin: 0.75in 0.625in 0.95in 0.625in; }
* { box-sizing: border-box; }
html { font-size: 10pt; }
body { margin: 0; font-family: "Times New Roman", Times, serif; font-size: 10pt; line-height: 1.17; color: #000;
       -webkit-print-color-adjust: exact; print-color-adjust: exact; }
.title { text-align: center; font-size: 22pt; line-height: 1.12; margin: 0 0 10pt; font-weight: normal; }
.authors { text-align: center; font-size: 11pt; margin: 0 0 3pt; }
.affil { text-align: center; font-size: 10pt; font-style: italic; margin: 0; }
.context { text-align: center; font-size: 8.5pt; margin: 6pt 0.6in 14pt; line-height: 1.25; }
.cols { column-count: 2; column-gap: 0.25in; text-align: justify; hyphens: manual; orphans: 2; widows: 2; }
p { margin: 0; text-indent: 1em; }
.abstract { font-weight: bold; font-size: 9pt; line-height: 1.15; margin-bottom: 5pt; }
.abstract i, .keywords i { font-weight: bold; }
.keywords { font-weight: bold; font-size: 9pt; line-height: 1.15; margin-bottom: 8pt; }
h2 { font-size: 10pt; font-weight: normal; font-variant: small-caps; text-align: center; margin: 10pt 0 4pt; letter-spacing: 0.02em;
     break-after: avoid; hyphens: none; }
h3 { font-size: 10pt; font-weight: normal; font-style: italic; text-align: left; margin: 6pt 0 2pt; break-after: avoid; hyphens: none; }
figure { margin: 8pt 0 9pt; break-inside: avoid; text-align: center; }
figure.col { display: inline-block; width: 100%; text-indent: 0; }
figure.wide { column-span: all; margin: 10pt 0 11pt; }
figure > svg { max-width: 100%; height: auto; display: block; margin: 0 auto; }
figcaption { font-size: 8pt; line-height: 1.2; text-align: justify; margin-top: 5pt; hyphens: manual; }
.tcap { font-size: 8pt; line-height: 1.25; text-align: center; margin-bottom: 4pt; text-transform: uppercase; letter-spacing: 0.03em; }
.tcap span { font-variant: small-caps; text-transform: none; letter-spacing: 0.02em; }
table { border-collapse: collapse; width: 100%; font-size: 8pt; line-height: 1.2; text-align: left; hyphens: none;
        border-top: 1pt solid #000; border-bottom: 1pt solid #000; }
th { font-weight: bold; border-bottom: 0.5pt solid #000; padding: 2.5pt 3pt; vertical-align: bottom; }
td { padding: 2pt 3pt; vertical-align: top; }
tbody tr + tr td { border-top: 0.25pt solid #c3c2b7; }
td.n, th.n { text-align: right; white-space: nowrap; }
.tnote { font-size: 7.5pt; text-align: left; margin-top: 3pt; line-height: 1.2; }
.eq { display: flex; align-items: center; justify-content: space-between; margin: 5pt 0 5pt 1em; text-indent: 0; text-align: left;
      hyphens: none; }
.eq .m { flex: 1; text-align: center; font-size: 10pt; }
.frac { display: inline-flex; flex-direction: column; vertical-align: middle; text-align: center; margin: 0 2pt; }
.frac span:first-child { border-bottom: 0.5pt solid #000; padding: 0 3pt 1pt; }
.frac span:last-child { padding: 1pt 3pt 0; }
code { font-family: "Courier New", monospace; font-size: 8.6pt; }
table code { font-size: 7.6pt; }
pre.code { font-family: "Courier New", monospace; font-size: 7.1pt; line-height: 1.22; text-align: left; white-space: pre;
           margin: 5pt 0 7pt; padding: 4pt 5pt; background: #f4f4f1; border: 0.5pt solid #c3c2b7; overflow: hidden;
           break-inside: avoid; hyphens: none; text-indent: 0; }
ol.list { margin: 2pt 0 2pt 0; padding-left: 1.7em; }
ol.list li { margin: 0; }
.refs { font-size: 8pt; line-height: 1.2; margin: 0; padding: 0; list-style: none; }
.refs li { display: flex; gap: 4pt; margin-bottom: 1.5pt; text-align: justify; }
.refs li span:first-child { flex: 0 0 1.9em; }
"""

# ====================================================================================== contenido
head = f"""
<h1 class="title">Identificación de producto y estimación de ángulo con aprendizaje automático clásico,
y un asistente agéntico para operar una línea de <i>pick &amp; pack</i></h1>
<p class="authors">Sara Guerra</p>
<p class="affil">Prueba técnica de Ingeniero de IA — Indra Group</p>
<p class="context">Informe técnico elaborado como entregable de una prueba técnica para Indra Group (octubre de 2026).
No es una publicación arbitrada: el formato de artículo IEEE se usa como convención de presentación.
Código, datos de evaluación y artefactos: github.com/hydemon8/prueba-tecnica-indra</p>
"""

abstract = f"""
<p class="abstract"><i>Resumen</i>—Este informe documenta la solución a una prueba técnica de Ingeniero de IA de Indra
Group. El problema es sustituir la identificación y la alineación manual de productos en una línea de <i>pick &amp;
pack</i> por un sistema de visión que diga qué producto es, en qué ángulo está y si un brazo robótico puede actuar
con seguridad. Sobre COIL-100, y con la restricción de usar aprendizaje automático clásico, un diagnóstico con vecino
más cercano muestra que identificar el producto es fácil y que la dificultad está en el ángulo cuando faltan vistas.
La identidad se resuelve con un histograma de color HSV y un bosque aleatorio, elegido entre 35 candidatos con un
criterio fijado de antemano. El ángulo se estima con un lazo cerrado por objeto en un espacio de componentes
principales, que además produce una distribución sobre el ángulo de la que salen dos medidas de incertidumbre. Con
ellas, un control determinista deja actuar al robot en el {c('final', 'A', 'decision.rate_ACT')}&nbsp;% de los casos
con vistas cada 10°, con {c('final', 'A', 'decision.unsafe_rate')}&nbsp;% de acciones inseguras frente al
{c('baseline', 'A', 'decision.unsafe_rate')}&nbsp;% de una referencia simple, y se abstiene cuando falta un arco de
vistas o hay solo doce por producto. Un asistente agéntico usa ese sistema
como herramienta en siete tareas de operación, con permisos y aprobación humana aplicados en código, y completa la
tarea en el 95&nbsp;% de 174 ejecuciones de evaluación.</p>
<p class="keywords"><i>Palabras clave</i>—visión por computador, aprendizaje automático clásico, estimación de pose,
espacio propio paramétrico, clasificación selectiva, agentes con herramientas, COIL-100.</p>
"""

s1 = f"""
<h2>I. Introducción y contexto del problema</h2>
<p>En una línea de <i>pick &amp; pack</i>, un operario identifica cada producto y lo gira hasta una orientación fija
para que un brazo robótico lo agarre. La prueba pide sustituir esa tarea por una cámara y un sistema que entregue,
por cada imagen, cuatro salidas: el producto, su giro sobre el eje vertical con una medida de incertidumbre, las
vistas de referencia más parecidas como evidencia, y la decisión de si el robot puede actuar. La cuarta es la que
define el problema. Un robot que actúa con el producto equivocado empaca mal, y con el ángulo equivocado daña el
producto o detiene la línea; el sistema debe saber abstenerse.</p>
<p>El enunciado fija tres condiciones. El modelo productivo debe ser de aprendizaje automático clásico, con
características diseñadas y modelos estadísticos; un modelo profundo solo se admite como referencia de comparación.
El robot tolera un error de ±10° en el ángulo. Y sobre el modelo debe construirse un asistente conversacional
agéntico para el personal de planta, que lo use como herramienta y no lo reimplemente dentro de un <i>prompt</i>.</p>
<p>Los datos son COIL-100 [1]: 100 objetos fotografiados sobre un plato giratorio cada 5°, es decir, 72 vistas por
objeto y 7.200 imágenes de 128&nbsp;×&nbsp;128 píxeles ({F('montaje')}). Son un sustituto controlado de las imágenes
de una planta: fondo oscuro, objeto centrado e iluminación fija.</p>
{figure('montaje', 'Tres objetos de COIL-100 cada 90°, usados como ejemplo en el resto del documento: un pato (cada vista es distinta), una caja de chicles (se ve casi igual a 0° y a 180°) y un toro (se ve igual desde cualquier ángulo).')}
<p>La solución separa dos planos ({F('sistema')}). En la ruta crítica, un servicio de visión determinista decide
sobre cada objeto en unos 28&nbsp;ms, sin intervención de un modelo de lenguaje (LLM). En el plano de supervisión, un
asistente atiende a las personas y usa ese mismo servicio como herramienta. El documento sigue el orden en que se
construyó: diagnóstico inicial (Sección&nbsp;II), características (III), protocolos y validación (IV), modelos de
clasificación (V), modelo de ángulo (VI), asistente (VII y VIII),
API y despliegue (IX) y conclusiones (X).</p>
"""

s2 = f"""
<h2>II. Punto de partida: vecino más cercano</h2>
<h3>A. Método</h3>
<p>Antes de diseñar nada se midió la dificultad con el método más simple disponible [2]. Cada imagen se reduce a
32&nbsp;×&nbsp;32 píxeles promediando bloques de 4&nbsp;×&nbsp;4 (<i>average pooling</i>), se aplana en un vector de
3.072 valores, se centra y se lleva a norma unitaria. La similitud entre dos imágenes es la distancia euclídea entre
sus vectores, que con norma unitaria equivale a la similitud coseno. A una imagen nueva se le asigna el producto de
su vecina más cercana. Para el ángulo se busca la vecina más cercana solo entre las vistas del producto correcto,
de modo que la dificultad del ángulo se mide aparte de la de la identidad.</p>
<h3>B. Resultados y limitaciones</h3>
<p>La {F('knn')} resume el resultado. Con vistas de referencia cada 10°, el producto se identifica en el
99,97&nbsp;% de los casos: clasificar no es la dificultad. El ángulo sí se degrada. Queda dentro de la tolerancia en
el 97,8&nbsp;% de los casos con vistas cada 10°, en el 76,0&nbsp;% con doce vistas por producto y en el 28,8&nbsp;%
cuando la imagen cae en un arco de 60° que nunca se vio.</p>
<p>El método tiene cuatro límites que orientan el resto del diseño. Solo puede responder con un ángulo que ya vio,
así que su error crece con el espaciado de las vistas. No extrapola: en el arco no visto, el 30,1&nbsp;% de las
estimaciones se equivoca en más de 90°. No indica cuánto confiar en su respuesta, de modo que no puede abstenerse. Y compara píxeles
alineados, por lo que depende de que el objeto llegue centrado. La conclusión es que el problema está en estimar el
ángulo cuando faltan vistas y en saber cuándo no responder. Este diagnóstico se midió sobre las particiones de
prueba (en B, con un sorteo distinto de los finales); el método no tiene hiperparámetros y no se eligió ningún modelo
con estas cifras.</p>
{figure('knn', 'Diagnóstico con vecino más cercano sobre píxeles de 32&nbsp;×&nbsp;32. La identidad se mantiene y el ángulo cae cuando faltan vistas. A, C y B son los protocolos de la Sección&nbsp;IV-A.')}
"""

s3 = f"""
<h2>III. Extracción de características</h2>
<p>Un modelo clásico no opera sobre imágenes sino sobre vectores, y rinde según lo bien que esos vectores describan
lo que importa. Se construyeron cuatro descriptores ({Tb('feat')}): los píxeles reducidos, un histograma de color
en el espacio HSV, el histograma de gradientes orientados (HOG) [3] para la forma, y los patrones binarios locales
(LBP) [4] para la textura. El histograma de color se calcula solo sobre los píxeles del objeto, separados del fondo
con un umbral de brillo, y se le aplica la raíz cuadrada para comparar con la distancia de Hellinger.</p>
<p>Las combinaciones concatenan bloques normalizados a norma unitaria, para que cada familia pese lo mismo. Los
bloques de más de 150 dimensiones se reducen a 150 con análisis de componentes principales (PCA) ajustado solo con
las vistas de entrenamiento, y después se estandarizan.</p>
<p>La propiedad que organiza el diseño es que cada descriptor sirve para una tarea distinta. El color casi no cambia
cuando el objeto gira: identifica bien el producto y no dice nada del ángulo. Los píxeles sí cambian con el giro, y
por eso contienen el ángulo. De ahí salen dos modelos, uno para la identidad y otro para el ángulo, como en el
trabajo original sobre este conjunto de datos [5].</p>
{table('feat', 'Descriptores de imagen', ['Bloque', 'Definición', '<span class="n">Dim.</span>', 'Qué describe'], [
    ['Píxeles', 'RGB reducido a 32&nbsp;×&nbsp;32 con interpolación bilineal, en [0,&nbsp;1]', '3.072', 'Apariencia completa; cambia con el giro'],
    ['Color HSV', 'Histograma de 16&nbsp;×&nbsp;4&nbsp;×&nbsp;4 intervalos sobre los píxeles del objeto, con raíz cuadrada', '256', 'Color; casi no cambia con el giro'],
    ['Forma HOG', 'Gris a 64&nbsp;×&nbsp;64, celdas de 8&nbsp;×&nbsp;8, bloques de 2&nbsp;×&nbsp;2 y 9 orientaciones', '1.764', 'Forma, por sus bordes'],
    ['Textura LBP', 'Patrones uniformes con (8,&nbsp;1) y (16,&nbsp;2) vecinos y radio', '28', 'Textura'],
], widths=[17, 44, 11, 28])}
"""

s4 = f"""
<h2>IV. Protocolos, validación y criterio de selección</h2>
<h3>A. Protocolos de evaluación</h3>
<p>El enunciado define cuatro protocolos ({F('protocolos')}). Un protocolo no es un modelo distinto: es una forma de
repartir las vistas entre entrenamiento y prueba para medir una capacidad concreta. El sistema y el código son los
mismos en los cuatro. El protocolo A mide la interpolación entre vistas conocidas (3.600 imágenes de entrenamiento y
3.600 de prueba). El B esconde un arco de 60° de cada objeto y pregunta por él (6.000 y 1.200). El C deja doce
vistas por producto (1.200 y 6.000). El D excluye diez objetos por completo y mide si el sistema sabe decir que no
los conoce (6.480 y 720). B y D dependen de un sorteo, así que se repiten con tres semillas y se reportan la media y
la desviación.</p>
<h3>B. Validación interna</h3>
<p>Dos vistas separadas 5° son casi la misma imagen, de modo que una validación cruzada con particiones al azar
filtraría información. Por eso la validación interna se construye solo con vistas de entrenamiento y por bloques de
ángulo o de objeto, imitando cada protocolo ({Tb('valid')}). Ningún umbral se ajusta con la prueba, que se evaluó dos
veces: con la primera versión del control de seguridad y con la definitiva (Sección&nbsp;VI-D). Los modelos de
identidad y de ángulo son los mismos en las dos. La representación se eligió una sola vez para los cuatro
protocolos, con particiones internas que comparten imágenes entre ellos.</p>
{table('valid', 'Validación interna de cada protocolo', ['Prot.', 'Particiones internas, solo con vistas de entrenamiento'], [
    ['A', 'Dos: entrena con 0°, 20°, 40°… y valida con 10°, 30°…, y al revés. Espaciado doble que en la prueba'],
    ['B', 'Tres: se retira otro arco de 60° dentro de los 300° vistos'],
    ['C', 'Dos: entrena con 0°, 60°… y valida con 30°, 90°…, y al revés. Huecos de 60°'],
    ['D', 'Tres: diez objetos del catálogo hacen de desconocidos, distintos de los de la prueba'],
], widths=[10, 90])}
<h3>C. Búsqueda en rejilla con criterio fijado de antemano</h3>
<p>La identidad se eligió con una búsqueda en rejilla sobre 35 candidatos: cinco representaciones (píxeles, color,
forma, textura y la combinación de las tres últimas) por siete configuraciones de clasificador. Cada candidato se
ajusta en las siete particiones internas de A, B y C. El criterio se escribió en el archivo de configuración antes de
ejecutar ninguna selección:</p>
<ol class="list">
<li>Restricción de novedad: en la validación interna de D, como máximo el 5&nbsp;% de los objetos desconocidos
puede aceptarse cuando se acepta el 95&nbsp;% de los conocidos.</li>
<li>Entre los que la cumplen, gana la mayor exactitud en el peor caso entre A, B y C.</li>
<li>Si la diferencia es menor de 0,5 puntos, gana el de menor latencia.</li>
</ol>
<p>La puntuación de novedad es la distancia a la vista de referencia más cercana en la representación del candidato.
Se registra además el área bajo la curva de riesgo y cobertura [6], que mide si la confianza del clasificador
ordena bien sus errores. La rejilla es pequeña a propósito: una exploración previa mostró que la representación pesa
mucho más que el clasificador.</p>
"""

s5 = f"""
<h2>V. Modelos de clasificación: selección y resultados</h2>
<h3>A. Clasificadores</h3>
<p>Se compararon cuatro familias, con scikit-learn [7]: vecino más cercano (1-NN); regresión logística multinomial con
regularización <i>C</i>&nbsp;∈&nbsp;{{1,&nbsp;10}}; máquina de vectores de soporte con núcleo gaussiano (SVM-RBF) [8] y
<i>C</i>&nbsp;∈&nbsp;{{1,&nbsp;10,&nbsp;100}}; y bosque aleatorio (<i>random forest</i>, RF) [9] de 500 árboles. La confianza de la máquina de
vectores de soporte se obtiene con una función <i>softmax</i> sobre sus puntuaciones. La calibración habitual por
validación cruzada bajaba la exactitud interna del protocolo C al 75,7&nbsp;%, porque sus particiones sin barajar eran, de
hecho, sectores ciegos.</p>
<h3>B. Selección</h3>
<p>La {F('seleccion')} muestra el peor caso de los 35 candidatos. La representación domina: el mejor candidato sobre
píxeles (78,2&nbsp;%) queda veinte puntos por debajo del mejor sobre color (98,5&nbsp;%), mientras que con el mismo
descriptor de color los clasificadores difieren en unos cinco puntos. La forma y la textura por separado incumplen
la restricción de novedad, con 15,5&nbsp;% y 65,4&nbsp;% de desconocidos aceptados.</p>
<p>Ganó el histograma de color con bosque aleatorio: mejor peor caso (98,5&nbsp;%, en C), entre 1,0&nbsp;% y
4,5&nbsp;% de desconocidos aceptados según la repetición de D, y la mejor curva de riesgo y cobertura de toda la
rejilla. La hipótesis previa era que
ganaría la combinación de color, forma y textura, que quedó segunda con regresión logística (97,0&nbsp;%). Se
respetó el criterio.</p>
{figure('seleccion', 'Exactitud del peor caso entre las validaciones internas de A, B y C para los 35 candidatos. «Desc. acept.» es el porcentaje de desconocidos aceptados en la primera repetición de D; «≤ 5 %» indica si la representación cumple la restricción de novedad.')}
<h3>C. Resultados en prueba</h3>
<p>La {Tb('ident')} compara el modelo elegido con un método de referencia simple (PCA de píxeles con vecino más
cercano, sin rechazo) y con una referencia moderna: DINOv2 [10] como extractor de características, con regresión
logística. El modelo clásico mantiene la identidad en el 99&nbsp;% o más en los tres protocolos y rechaza el
{c('final', 'D', 'unknown_rejected')}&nbsp;% de los objetos desconocidos.</p>
{table('ident', 'Identidad en prueba (%)', ['Medida', 'Referencia simple', 'Propuesto', 'DINOv2'], [
    ['Clase, protocolo A', c('baseline', 'A', 'class_acc'), c('final', 'A', 'class_acc'), c('reference', 'A', 'class_acc')],
    ['Clase, protocolo B', c('baseline', 'B', 'class_acc'), c('final', 'B', 'class_acc'), c('reference', 'B', 'class_acc')],
    ['Clase, protocolo C', c('baseline', 'C', 'class_acc'), c('final', 'C', 'class_acc'), c('reference', 'C', 'class_acc')],
    ['Desconocidos rechazados, D', c('baseline', 'D', 'unknown_rejected'), c('final', 'D', 'unknown_rejected'), c('reference', 'D', 'unknown_rejected')],
], widths=[37, 22, 20, 21])}
<h3>D. Análisis</h3>
<p>En C, los errores de identidad se concentran en pocos pares: piezas de madera del mismo tono, como los objetos
51, 11 y 12. Es coherente con un modelo que se apoya en el color. La referencia moderna mejora la identidad menos de
un punto, rechaza peor los desconocidos ({c('reference', 'D', 'unknown_rejected')}&nbsp;%) y cuesta más: su extractor tiene unos 22
millones de parámetros y se ejecutó en GPU.</p>
<p>La debilidad del modelo elegido también viene del color. En pruebas posteriores sobre imágenes alteradas, un
aumento del brillo del 15&nbsp;% hizo que el 66&nbsp;% del producto conocido se rechazara como desconocido (200
imágenes de catálogo alteradas). Es sobre todo un fallo de disponibilidad, que detendría una línea, pero no solo: en
esa condición el 2,0&nbsp;% de las imágenes terminó en una acción insegura. El segundo candidato del criterio rechazó solo
el 0,5&nbsp;% en esa condición, lo que sugiere añadir un término de robustez al criterio de selección.</p>
"""

s6 = f"""
<h2>VI. Modelo de lazos para el ángulo</h2>
<h3>A. Idea</h3>
<p>El objeto solo puede girar sobre el eje vertical, así que su apariencia depende de un único parámetro. Si cada
imagen se representa como un punto, al girar el objeto ese punto se mueve de forma continua y vuelve al inicio al
completar la vuelta. Las vistas de un objeto forman una curva cerrada, un lazo. Es el espacio propio paramétrico de
Murase y Nayar [5].</p>
<h3>B. Construcción</h3>
<p>La {F('pipeline')} resume los pasos. La imagen se reduce a 32&nbsp;×&nbsp;32 píxeles y se aplana en 3.072
valores ({Tb('feat')}); a diferencia del diagnóstico inicial, no se centra ni se normaliza. Una PCA global, ajustada una vez con las vistas de
entrenamiento de todos los objetos, la comprime a 50 componentes, que conservan el
{es(DATA['varianza_50d'] * 100)}&nbsp;% de la varianza. Después, para cada objeto se toman los puntos de sus vistas
conocidas, ordenados por ángulo, y se unen con un <i>spline</i> cúbico periódico, componente a componente. La curva
se evalúa cada 0,5°, lo que da 720 puntos por objeto: la apariencia esperada en cada ángulo, también en los que no
se fotografiaron. El ángulo estimado de una imagen nueva es el del punto más cercano del lazo de su producto.</p>
{figure('pipeline', 'Del píxel al ángulo. La PCA y los lazos se ajustan una vez; la distancia y la distribución se calculan para cada imagen.')}
<h3>C. Forma del lazo y simetría</h3>
<p>La forma del lazo anticipa si el ángulo se puede estimar ({F('lazos')}). En un objeto sin simetría cada ángulo
ocupa un lugar distinto. En uno que se ve igual de frente que de espaldas, las vistas opuestas coinciden y el lazo se
recorre dos veces. La simetría de media vuelta se mide con la razón</p>
<div class="eq"><span class="m"><i>r</i> = <span class="frac"><span>med<sub><i>θ</i></sub>
<i>d</i><sup>2</sup>(<i>θ</i>, <i>θ</i> + 180°)</span><span>med<sub><i>θ</i></sub> <i>d</i><sup>2</sup>(<i>θ</i>,
<i>θ</i> + 10°)</span></span></span><span>(1)</span></div>
<p>donde <i>d</i><sup>2</sup> es la distancia al cuadrado entre dos puntos del lazo. Si <i>r</i>&nbsp;&lt;&nbsp;1, la
vista opuesta está más cerca que la vecina; ocurre en diez de los cien objetos. La razón es relativa y no ve el
tamaño del lazo. El toro (obj47) tiene <i>r</i>&nbsp;=&nbsp;{es(L['47']['razon'], 2)}, pero su lazo mide
{es(L['47']['tamano'], 2)} frente a una mediana de {es(DATA['tamano_mediano'])}: es el tercero más pequeño. Se ve
igual desde cualquier ángulo y su ángulo no es observable. Son dos simetrías distintas y se detectan con medidas
distintas.</p>
{figure('lazos', f"Lazos de tres objetos, cada uno en su plano principal (las dos direcciones en que más varía, que reúnen entre el {round(min(L[o]['varianza_plano'] for o in L) * 100)}&nbsp;% y el {round(max(L[o]['varianza_plano'] for o in L) * 100)}&nbsp;% de su varianza). En el pato cada ángulo ocupa un lugar; en la caja las dos medias vueltas coinciden; el toro, a escala real, es casi un punto. «Razón» es <i>r</i> en (1); «tamaño» es la distancia al cuadrado mediana al centro del lazo.")}
<h3>D. Incertidumbre a partir de una distribución</h3>
<p>Un ángulo sin una medida de confianza no permite abstenerse. Se supone que la imagen observada es un punto del
lazo más ruido gaussiano, y que todos los ángulos son igual de probables a priori. La probabilidad de cada ángulo
<i>θ<sub>k</sub></i> de la rejilla, dada la imagen, es entonces</p>
<div class="eq"><span class="m"><i>p</i>(<i>θ<sub>k</sub></i>) ∝ exp<span style="font-size:13pt">(</span>−<span class="frac"><span><i>d<sub>k</sub></i><sup>2</sup> −
<i>d</i><sup>2</sup><sub>mín</sub></span><span><i>s</i> <i>τ</i><sub>0</sub></span></span><span style="font-size:13pt">)</span></span><span>(2)</span></div>
<p>donde <i>d<sub>k</sub></i> es la distancia de la imagen al punto <i>k</i> del lazo, <i>τ</i><sub>0</sub> es la
distancia al cuadrado mediana entre vistas consecutivas, que fija la escala del ruido, y <i>s</i> se calibra en
validación interna para que el conjunto creíble del 90&nbsp;% contenga el ángulo real el 90&nbsp;% de las veces
(<i>s</i>&nbsp;=&nbsp;0,040 y cobertura del 90,6&nbsp;% en la validación interna de A). De la distribución salen dos medidas. El <i>ancho</i>
es el tamaño, en grados, del menor conjunto de ángulos que reúne el 90&nbsp;% de la probabilidad. La
<i>ambigüedad</i> compara el mejor ángulo con el mejor candidato situado a más de 20° de él:</p>
<div class="eq"><span class="m"><i>a</i> = <span style="font-size:13pt">(</span><span class="frac"><span><i>d</i><sup>2</sup><sub>mín</sub> + <i>ε</i></span><span><i>d</i><sup>2</sup><sub>lejos</sub> + <i>ε</i></span></span><span style="font-size:13pt">)</span><sup>1/2</sup></span><span>(3)</span></div>
<p>donde <i>d</i><sub>lejos</sub> es la distancia a ese candidato y <i>ε</i>&nbsp;=&nbsp;10<sup>−3</sup><i>τ</i><sub>0</sub> evita un cociente indeterminado. Si <i>a</i> se acerca a 1, hay un segundo ángulo lejano casi tan bueno como el primero. La {F('posterior')}
muestra los tres comportamientos con vistas reales de prueba. En el pato, el perfil de distancia tiene un único
valle y la distribución un único pico (ancho de {es(P['74']['ancho'])}°). En el toro el perfil es casi plano y la
probabilidad se reparte (ancho de {es(P['47']['ancho'])}°). En la caja de chicles, a 105°, hay dos valles de
profundidad casi igual y dos picos; el modelo elige el equivocado y estima {es(P['67']['angulo'], 0)}°, con 180° de
error y un ancho de solo {es(P['67']['ancho'])}°. El ancho lo aceptaría; la ambigüedad
({es(P['67']['ambiguedad'], 2)}) lo detiene.</p>
<p>Ese caso ilustra la segunda medida, que se añadió en una segunda versión. La primera versión del control usaba
solo el ancho y, al evaluarla en la prueba de A, dio 1,0&nbsp;% de acciones inseguras. El defecto se reprodujo en la
validación interna de A, donde dejaba pasar un 1,05&nbsp;% de casos con más de 10° de error; el umbral de ambigüedad
se calibró solo ahí, y lo bajó al 0,47&nbsp;%. Conviene precisar el alcance: con 50 componentes, las vistas opuestas
de esta caja casi siempre se distinguen. De sus 36 vistas de prueba, solo esa supera el umbral.</p>
<h3>E. Control de seguridad</h3>
<p>La decisión la toman cuatro reglas deterministas, en orden ({Tb('gate')}). Los umbrales de novedad, confianza y
ambigüedad se calibran en validación interna; el ancho y el hueco máximos son fijos. La tolerancia de ±10° se traduce en un objetivo de riesgo: que al menos el 99,5&nbsp;% de las
veces que el robot actúa, el ángulo esté dentro de la tolerancia. El ancho máximo es de 20°, el doble de la
tolerancia, y el umbral de ambigüedad es el mayor que cumple ese objetivo entre los casos aceptados.</p>
{figure('posterior', 'Perfil de distancia al lazo (arriba) y distribución sobre el ángulo (abajo) para tres vistas de prueba del protocolo A, con un modelo ajustado con las vistas de entrenamiento de A. Cada panel tiene su propia escala vertical; la distancia máxima del toro es unas diez veces menor que la de los otros dos.', wide=True)}
{table('gate', 'Reglas del control de seguridad', ['Decisión', 'Condición', 'Orden al robot'], [
    ['Desconocido', 'Novedad por encima de su umbral', 'Carril de rechazo'],
    ['Revisión', 'Confianza de clase baja, o la vista más parecida es de otro producto', 'Revisión humana'],
    ['Ángulo no certificado', 'Hueco de más de 30° entre las vistas de referencia del producto, ancho mayor de 20° o ambigüedad alta', 'Segunda captura'],
    ['Actuar', 'Ninguna de las anteriores', 'Agarrar, con producto y ángulo'],
], widths=[25, 50, 25])}
<h3>F. Resultados</h3>
<p>La {F('resultados')} y la {Tb('res')} resumen la prueba. El modelo de lazos supera a la referencia simple en los
tres protocolos, sobre todo cuando faltan vistas ({c('final', 'C', 'pose_true_class.within_tol')}&nbsp;% frente a
{c('baseline', 'C', 'pose_true_class.within_tol')}&nbsp;% en C). En A, a ±10°, no supera al diagnóstico de la
Sección&nbsp;II ({c('final', 'A', 'pose_true_class.within_tol')}&nbsp;% frente a 97,8&nbsp;%): con vistas cada 10°, el
vecino más cercano se queda a 5° del valor real, dentro de la tolerancia. La ventaja del lazo ahí es el error
mediano (0,5° frente a 5,0°) y la distribución. Con las características de DINOv2 el mismo método
estima peor el ángulo, lo que es coherente con un extractor entrenado para no depender del punto de vista.</p>
{figure('resultados', 'Ángulo dentro de ±10° en prueba, con la clase conocida. La etiqueta corresponde al modelo propuesto.')}
<p>En A, el robot actúa en el {c('final', 'A', 'decision.rate_ACT')}&nbsp;% de los casos y el
{c('final', 'A', 'decision.unsafe_rate')}&nbsp;% de todas las imágenes termina en una acción insegura, frente al
{c('baseline', 'A', 'decision.unsafe_rate')}&nbsp;% de la referencia simple, que actúa siempre. El objetivo de
riesgo se cumplió en validación interna (0,47&nbsp;%) y no en prueba ({es(risk_A, 2)}&nbsp;% de las acciones, frente
a 0,5&nbsp;%): el umbral se eligió sin margen estadístico, y la validación interna no representa exactamente la
prueba. En B el sistema no actúa, por la regla del hueco angular. Una simulación de segunda captura, con la vista a
180° tomada de las de referencia y retirada del lazo, y solo con las reglas de ángulo, recupera el ángulo en el
{es(two_m['within_tol_all'] * 100)}&nbsp;% de los casos y actuaría en el {es(two_m['act_rate'] * 100)}&nbsp;%, con
{es(two_m['unsafe_rate'] * 100, 2)}&nbsp;% de acciones inseguras ({es(two_risk, 2)}&nbsp;% de las acciones). El
servicio emite la orden de segunda captura, pero no combina las dos imágenes. En C acierta el ángulo pero no puede demostrar el
criterio con doce vistas, y no actúa. En D rechaza el {c('final', 'D', 'unknown_rejected')}&nbsp;% de los objetos
desconocidos.</p>
{table('res', 'Ángulo y decisión en prueba (%)', ['Prot.', 'Modelo', 'Ángulo ±10°', 'Actúa', 'Acciones inseguras'],
       [[f"{p}", n, c(b, p, 'pose_true_class.within_tol'), c(b, p, 'decision.rate_ACT'), c(b, p, 'decision.unsafe_rate')]
        for p in 'ABCD' for b, n in [('baseline', 'Referencia simple'), ('final', '<b>Propuesto</b>'), ('reference', 'DINOv2')]],
       widths=[9, 29, 22, 18, 22],
       note='Media ± desviación de tres semillas en B y D. El ángulo se mide con la clase conocida. Una acción insegura es actuar con el producto equivocado o con el ángulo fuera de la tolerancia; se cuenta sobre todas las imágenes de prueba. La referencia simple no tiene control y actúa siempre.')}
"""

s7 = f"""
<h2>VII. Asistente agéntico: planteamiento</h2>
<h3>A. Qué es agéntico y qué no</h3>
<p>El asistente no está en la línea. La decisión sobre cada objeto la toma el servicio de visión, que es
determinista; un modelo de lenguaje ahí añadiría segundos, costo por objeto y respuestas no repetibles en una
decisión de seguridad. Lo agéntico se reserva para lo que un modelo de lenguaje hace bien: entender una petición
abierta, elegir y encadenar herramientas, pedir lo que falta y explicar el resultado. Si el asistente o el modelo de
lenguaje fallan, la línea sigue funcionando.</p>
<h3>B. Patrón</h3>
<p>Es un solo agente con herramientas (<i>tools</i>) que razona y actúa por turnos [11], bajo una capa de política
determinista. Se descartaron tres alternativas. Un sistema multiagente multiplicaría los tokens por dos o tres,
añadiría errores de enrutamiento y obligaría a replicar los permisos. Los flujos fijos sin agente son más baratos y
predecibles, pero cada pregunta nueva exige código; se adoptaron solo para lo que debe ser fijo. Planificar primero y
ejecutar después fija el plan antes de ver los datos, y en un diagnóstico el siguiente paso depende del resultado
anterior.</p>
<h3>C. Bucle y arnés</h3>
<p>El bucle del agente y el código que lo rodea (el arnés, <i>harness</i>) están escritos a mano, sin bibliotecas de
agentes ({F('agente')}). En cada turno, el arnés arma el contexto, selecciona las <i>tools</i> que corresponden al
rol de la persona y llama al modelo. Si el modelo responde con texto, el turno termina. Si pide una <i>tool</i>, la
capa de política la valida y la ejecuta o la rechaza, y el resultado vuelve al modelo en JSON. El ciclo se repite
hasta una respuesta o hasta un límite ({Tb('limites')}). Al alcanzar un límite no se llama otra vez al modelo: se
responde con un texto fijo que indica qué se completó. El modelo de lenguaje es Gemini
(<code>gemini-3.5-flash-lite</code>, con temperatura 0), detrás de una interfaz de proveedor neutra. Un proveedor guionizado lo sustituye en las pruebas, para forzar comportamientos que un modelo real no
produce a voluntad, como repetir la misma llamada sin fin.</p>
{table('limites', 'Límites de un turno', ['Límite', '<span class="n">Valor</span>', 'Al alcanzarlo'], [
    ['Llamadas al modelo', '8', 'Fin del turno'],
    ['<i>Tools</i> ejecutadas', '12', 'Fin del turno'],
    ['Misma llamada con los mismos argumentos', '2', 'La tercera se bloquea'],
    ['Tokens', '60.000', 'Fin del turno'],
    ['Plazo del servicio de visión', '4 s', 'Un reintento y error estructurado'],
], widths=[50, 14, 36])}
<h3>D. Manejo del contexto y memoria</h3>
<p>Se distinguen cuatro cosas. El estado de ejecución dura un turno. El historial conversacional se guarda por
sesión. La memoria persistente, con casos, tickets y aprobaciones, vive en la base de datos de la planta y no es
memoria del modelo: se consulta con <i>tools</i>, así que siempre está al día y pasa por los mismos permisos. El
conocimiento recuperado son secciones de procedimientos, obtenidas con BM25 [12] y devueltas con su cita.</p>
<p>El contexto se mantiene acotado con cuatro reglas. Entre turnos solo viaja texto; los resultados de las
<i>tools</i> y las imágenes no se reinyectan. Los últimos 24 mensajes van íntegros y los anteriores se pliegan en un
resumen de 2.400 caracteres como máximo. Cada resultado de <i>tool</i> se trunca a 9.000 caracteres. Y el modelo
solo recibe las <i>tools</i> de su rol: un operario ve 3 de 22 y una supervisora 18.</p>
{figure('agente', 'Arquitectura del asistente. El modelo de lenguaje propone y la capa de política ejecuta. Las operaciones de riesgo terminan en una solicitud que decide una persona con rol aprobador.', wide=True)}
<h3>E. Políticas</h3>
<p>La capa de política es la única vía de ejecución. Valida los argumentos contra el contrato de cada <i>tool</i>,
autoriza por rol y por línea, y registra en una tabla de auditoría cada llamada que le llega, también las
rechazadas. La planta nunca es un argumento: sale de la sesión. Una regla del <i>prompt</i> indica tratar como dato,
y no como instrucción, el texto que devuelven las <i>tools</i>, como un ticket o un procedimiento.</p>
<p>Las cinco operaciones de riesgo (pausar o reanudar una línea, cambiar el umbral de confianza, enviar un ángulo
manual al robot, promover una versión de modelo y pasar un producto a producción) no se ejecutan desde el
asistente. La <i>tool</i> comprueba las precondiciones y crea una solicitud pendiente. La decide una persona con
rol aprobador, desde un punto de acceso que no es una <i>tool</i>, y las precondiciones se vuelven a comprobar al
aprobar. Quien solicita no puede aprobar, con una excepción documentada en el procedimiento: la supervisora de turno
puede aprobar su propia pausa de línea, no la reanudación. El asistente no puede aprobarse a sí mismo porque aprobar no está
a su alcance.</p>
"""

casos = [
    ['Inspección de imagen†', '<code>inspect_images</code>'],
    ['Cola de revisión humana', '<code>list_review_cases</code>, <code>resolve_review_case</code>, <code>add_to_retraining_dataset</code>'],
    ['Consulta operativa†', '<code>get_shift_metrics</code>, <code>get_line_timeline</code>, <code>get_camera_health</code>, <code>get_line_status</code>'],
    ['Diagnóstico de fallos', '<code>get_grasp_failures</code>, <code>search_procedures</code>, <code>create_ticket</code>'],
    ['Alta de producto nuevo†', '<code>register_sku_candidate</code>, <code>request_sku_promotion</code>'],
    ['Operación de riesgo', '<code>set_line_state</code>, <code>set_confidence_threshold</code>, <code>send_manual_angle</code>, <code>promote_model_version</code>'],
    ['Entrega de turno', '<code>create_shift_handover</code>'],
]

s8 = f"""
<h2>VIII. Capacidades e incorporación de los sistemas de aprendizaje automático</h2>
<h3>A. Capacidades</h3>
<p>El asistente cubre los siete casos de uso del enunciado con 22 <i>tools</i>, once de lectura y once de escritura
({Tb('casos')}). Atiende a supervisores, calidad, mantenimiento, ingeniería de modelos, gerencia y operarios, cada
uno con las <i>tools</i> de su rol.</p>
{table('casos', 'Casos de uso y <i>tools</i> principales', ['Caso de uso', '<i>Tools</i> principales'], casos, widths=[31, 69], note='† Usa el modelo de visión.')}
<h3>B. Cómo se incorpora el modelo de visión</h3>
<p>Para el asistente, la clasificación y la estimación de ángulo no son dos sistemas sino una sola
<i>tool</i>. <code>inspect_images</code> envía las imágenes que sube la persona al mismo servicio que usa el robot y
devuelve, por imagen, la decisión del control con sus motivos, el producto y su confianza, la novedad, el ángulo y su
ancho, la calidad de la captura, las vistas más parecidas y la acción recomendada, que es una tabla fija por
decisión. El modelo de lenguaje solo recibe ese resultado; nunca los píxeles. Una regla del <i>prompt</i> establece
que el producto y el ángulo los determina únicamente esa <i>tool</i>. Ante la imagen del toro, por ejemplo, el
asistente informa que es el producto 47, que el ángulo no está certificado porque su ancho es de 51,5° (vista de
90°, con el modelo final de 72 vistas), y propone
una segunda captura. Si el servicio de visión falla, hay un reintento y después un error estructurado: el asistente
dice que no pudo analizar la imagen y no inventa un resultado.</p>
<p>El segundo punto de entrada es el alta de un producto nuevo. <code>register_sku_candidate</code> comprueba que
haya al menos 36 vistas y ningún hueco de más de 30°, las condiciones que el modelo de ángulo necesita para
certificar. Después pasa cada vista por el servicio de visión, para confirmar que las capturas son válidas y que el
producto no se confunde con uno del catálogo. Si lo supera, queda registrado en un entorno de prueba; el paso a
producción es una operación de riesgo.</p>
<p>El tercero es de solo lectura. El servicio de visión vigila, por línea, la tasa de objetos desconocidos, y activa
una alerta de captura si sube de forma brusca; mientras dura, los desconocidos se retienen para revisión en lugar
de rechazarse. <code>get_line_status</code> incluye esa alerta, con su causa probable, y la interfaz la muestra en
un panel de líneas. En esta demostración, la planta es simulada y la evaluación de desempeño del
producto nuevo también, porque no se reentrena el modelo. El servicio de visión es real.</p>
<h3>C. Evaluación</h3>
<p>El asistente se evaluó con 45 casos reproducibles, 19 de ellos adversos: imágenes fuera de dominio, resultados no
confiables, argumentos inválidos, caídas del servicio de visión, bucles e intentos de saltarse los permisos. Cada
caso se ejecuta sobre una planta recién creada y lo juzga código, no otro modelo: qué <i>tools</i> se llamaron y con
qué argumentos, el estado final de la base de datos y el contenido de la respuesta. Se lanzaron 225 ejecuciones,
cinco por caso; 51 se anularon por la cuota del proveedor del modelo de lenguaje y quedaron 174 válidas, entre tres y
cinco por caso.</p>
<p>La tarea se completó en el 95&nbsp;% de las ejecuciones (166 de 174), con la <i>tool</i> correcta en el
98&nbsp;% y argumentos correctos en el 100&nbsp;% ({F('eval')}). En los casos adversos el éxito fue del 93&nbsp;%.
Ninguna ejecución cambió indebidamente el estado de la planta: los fallos son de contenido de la respuesta o de no
haber consultado una <i>tool</i>. El peor
resultado está en el diagnóstico, con un fallo sistemático ante la pregunta por un procedimiento que no existe. Las
cifras son optimistas, porque el <i>prompt</i> se ajustó con estos mismos casos y no hay un conjunto reservado. La
alerta de captura se conectó al asistente después de esta evaluación: la cubren pruebas automáticas, no una corrida
nueva de los 45 casos.</p>
{figure('eval', 'Éxito de la tarea por categoría, sobre las ejecuciones válidas. Entre paréntesis, el número de casos de cada categoría.')}
"""

def ruta(s):
    """Ruta en letra de código, con puntos de corte tras cada barra para que quepa en la columna."""
    return "<code>" + s.replace("/", "/<wbr>") + "</code>"


api_vision = [
    [ruta('POST /v1/predict'), 'Una o varias imágenes; devuelve decisión, orden para el robot, identidad, ángulo y vistas similares'],
    [ruta('GET /v1/model'), 'Versión del modelo y de los datos, huella del artefacto y umbrales del control'],
    [ruta('GET /v1/catalog'), 'Productos del catálogo: vistas de referencia, hueco angular máximo y simetría'],
    [ruta('GET /v1/reference/{producto}/{ángulo}'), 'Vista de referencia en PNG, usada como evidencia'],
    [ruta('GET /v1/lines/{línea}/monitor'), 'Estado de la alerta de captura de una línea'],
    [ruta('GET /healthz') + '<br>' + ruta('GET /readyz'), 'Proceso vivo; modelo cargado y verificado'],
    [ruta('GET|POST /admin/fault'), 'Simula errores y demoras. Solo si se habilita, para las pruebas de robustez'],
]
api_campos = [
    ['<code>decision</code>', '<code>ACT</code>, <code>ANGLE_UNCERTIFIED</code>, <code>REVIEW</code>, <code>UNKNOWN</code> o <code>BAD_CAPTURE</code>'],
    ['<code>reasons</code>', 'Reglas que impidieron actuar, en texto'],
    ['<code>robot_command</code>', 'Orden para el robot: <code>action</code> y, si es <code>PICK</code>, producto y ángulo'],
    ['<code>object_id</code>, <code>class_confidence</code>, <code>novelty</code>', 'Producto, confianza del clasificador y distancia a la vista conocida más cercana'],
    ['<code>angle_deg</code>, <code>angle_credible_<wbr>width_deg</code>', 'Ángulo y ancho del conjunto creíble del 90&nbsp;%'],
    ['<code>topk_pose</code>, <code>topk_appearance</code>', 'Vistas similares por ángulo y por apariencia'],
    ['<code>quality</code>', 'Validación de la captura: tamaño, fracción de objeto y brillo'],
    ['<code>request_id</code>, <code>model_version</code>, <code>latency_ms</code>, <code>line_alert</code>', 'Por petición: identificador, versión del modelo, tiempo y alerta de la línea'],
]
api_asistente = [
    [ruta('POST /api/login'), 'Inicia sesión con un usuario; devuelve el token y las <i>tools</i> de su rol'],
    [ruta('POST /api/chat'), 'Un turno: mensaje e imágenes; devuelve respuesta, pasos, evidencia y consumo'],
    [ruta('GET /api/approvals'), 'Solicitudes pendientes y recientes'],
    [ruta('POST /api/approvals/{id}/decision'), 'Aprueba o rechaza una operación de riesgo. No es una <i>tool</i>'],
    [ruta('GET /api/audit'), 'Registro de auditoría, para los roles autorizados'],
    [ruta('GET /api/tools') + '<br>' + ruta('GET /api/lines'), 'Catálogo de <i>tools</i>; estado de las líneas y alerta de captura'],
    [ruta('GET /api/sessions/{id}/messages') + '<br>' + ruta('GET /api/images/{id}'), 'Historial de la sesión e imágenes subidas'],
]

ejemplo = """$ curl -F "images=@obj5__40.png" \\
    "http://127.0.0.1:8001/v1/predict?top_k=2"

{"request_id": "4c4e8e05…",
 "model_version": "4e39f878-rf",
 "results": [{
   "filename": "obj5__40.png",
   "decision": "ACT", "reasons": [],
   "robot_command": {"action": "PICK",
       "object_id": 5, "angle_deg": 40.0},
   "object_id": 5, "class_confidence": 0.974,
   "novelty": 0.0, "angle_deg": 40.0,
   "angle_credible_width_deg": 6.0,
   "quality": {"ok": true, "issues": [], …},
   "topk_pose": [{"object_id": 5,
       "angle_deg": 40.0, "delta_deg": 0.0}, …],
   "topk_appearance": [{"object_id": 5,
       "angle_deg": 40.0, "distance": 0.0}, …]}]}"""

s_api = f"""
<h2>IX. API y despliegue</h2>
<h3>A. API del servicio de visión</h3>
<p>El modelo se sirve con una API HTTP propia, independiente del asistente ({Tb('apiv')}). El servicio publica su
documentación interactiva en <code>/docs</code>, y el contrato OpenAPI está versionado en el repositorio
(<code>doc/openapi/vision.json</code>).</p>
{table('apiv', 'API del servicio de visión', ['Método y ruta', 'Qué hace'], api_vision, widths=[40, 60])}
<p>La operación principal es <code>POST /v1/predict</code>. Recibe una o varias imágenes PNG o JPEG en un
formulario, en el campo <code>images</code>: hasta 16 por petición y 5&nbsp;MB cada una. El parámetro
<code>top_k</code> fija cuántas vistas similares se devuelven, entre 1 y 20. Hay tres cabeceras opcionales:
<code>X-API-Key</code>, que solo se exige si el servicio se configura con una clave; <code>X-Line-ID</code>, que
identifica la línea y activa su alerta de captura; y <code>X-Request-ID</code>, para seguir la petición. La
respuesta trae un resultado por imagen ({Tb('apir')}). A continuación, una llamada real con la respuesta
abreviada:</p>
<pre class="code">{ejemplo}</pre>
<p>Los errores propios del servicio comparten un cuerpo, con <code>code</code>, <code>message</code> y
<code>request_id</code>: 401 si falta la clave, 404 si no existe la vista de referencia y 413 si se supera el tamaño
o el número de imágenes. Un parámetro no válido devuelve 422 con el formato estándar de FastAPI. Una imagen ilegible o vacía no es un error:
devuelve la decisión <code>BAD_CAPTURE</code>, con la orden de repetir la captura.</p>
{table('apir', 'Campos de la respuesta de <code>POST /v1/predict</code>', ['Campo', 'Contenido'], api_campos, widths=[45, 55])}
<h3>B. API del asistente</h3>
<p>El asistente tiene su propia API, que es la que consume la interfaz web ({Tb('apia')}). El acceso empieza en
<code>POST /api/login</code>, que devuelve un token de sesión; las demás llamadas lo envían en la cabecera
<code>Authorization</code>. La autenticación es de demostración: se elige uno de los usuarios sembrados, sin
contraseña. <code>POST /api/chat</code> recibe el mensaje y las imágenes, si las hay, y devuelve el
texto de la respuesta, el motivo por el que terminó el turno, los pasos ejecutados con su resultado y su latencia,
la evidencia de las inspecciones, las solicitudes creadas y el consumo de tokens. La decisión sobre una operación
de riesgo tiene su propia ruta, que el modelo de lenguaje no puede llamar. La documentación interactiva también
está en <code>/docs</code>, y los contratos de las 22 <i>tools</i> en <code>doc/openapi/tools.json</code>.</p>
{table('apia', 'API del asistente', ['Método y ruta', 'Qué hace'], api_asistente, widths=[42, 58])}
<h3>C. Despliegue</h3>
<p>El sistema no se desplegó en ninguna plataforma: no hay servidor ni servicio en la nube. Se ejecuta en un equipo
local, con un comando o con Docker Compose, que levanta dos contenedores: el servicio de visión en el puerto 8001 y
el asistente en el 8002. Para dar acceso desde fuera durante la demostración se abre un túnel de ngrok hacia el
puerto del asistente (<code>ngrok http 8002</code>), que publica una dirección HTTPS temporal mientras el equipo está
encendido. El túnel no forma parte del repositorio. La API de visión no pasa por él: el asistente la consume por la
red local. Las herramientas usadas se resumen en la {Tb('stack')}.</p>
<p>Esta forma de exposición tiene límites. La dirección cambia en cada sesión y la disponibilidad depende de un solo
equipo. Con una dirección pública hay que activar el código de acceso del asistente y desactivar la inyección de
fallos del servicio de visión y los controles de demostración. La arquitectura objetivo en Azure, con la inferencia junto a la línea, está diseñada
en el repositorio y no desplegada.</p>
"""

stack = [
    [ico('python') + 'Python', 'Lenguaje de todo el proyecto'],
    [ico('scikitlearn') + 'scikit-learn, ' + ico('numpy') + 'NumPy', 'Características, clasificadores, PCA y lazos'],
    [ico('mlflow') + 'MLflow', 'Registro de experimentos y de modelos'],
    [ico('fastapi') + 'FastAPI', 'Servicio de visión y servicio del asistente'],
    [ico('sqlite') + 'SQLite', 'Planta simulada, sesiones y auditoría'],
    [ico('googlegemini') + 'Gemini', 'Modelo de lenguaje del asistente'],
    [ico('docker') + 'Docker', 'Despliegue local con un comando'],
    [ico('ngrok') + 'ngrok', 'Túnel HTTPS temporal para la demostración'],
    [ico('github') + 'GitHub', 'Repositorio con el código y los reportes'],
]

s9 = f"""
<h2>X. Conclusiones</h2>
<p>El trabajo deja cinco conclusiones. Primera, en este problema la dificultad no está en clasificar sino en estimar
el ángulo cuando faltan vistas y en saber abstenerse; medirlo antes de construir orientó el resto. Segunda, la
representación pesa más que el clasificador, y un criterio fijado de antemano eligió un modelo distinto del que se
esperaba. Tercera, tratar las vistas de un objeto como un lazo da un ángulo continuo y, además, una distribución de
la que salen dos medidas de incertidumbre que se complementan: el ancho detecta los objetos que se ven igual desde
cualquier lado y la ambigüedad detecta el segundo candidato a media vuelta. Cuarta, un control determinista, con
umbrales calibrados solo en validación interna, reduce las acciones inseguras del
{c('baseline', 'A', 'decision.unsafe_rate')}&nbsp;% al {c('final', 'A', 'decision.unsafe_rate')}&nbsp;% en A; en B y
C no hay ninguna porque el sistema no actúa, y en D porque rechaza los desconocidos. La referencia moderna no mejora
el ángulo ni el rechazo de desconocidos; en A comete menos acciones inseguras
({c('reference', 'A', 'decision.unsafe_rate')}&nbsp;%) porque actúa menos. Quinta, en el asistente lo útil del modelo de lenguaje es entender y
explicar; las decisiones que importan quedan en el código y en las personas.</p>
<p>Las limitaciones son concretas. El objetivo de riesgo no se alcanza del todo en prueba ({es(risk_A, 2)}&nbsp;%
frente a 0,5&nbsp;%). Con doce vistas por producto el sistema no actúa, aunque acierta el ángulo en el
{c('final', 'C', 'pose_true_class.within_tol')}&nbsp;%. Los datos son de laboratorio: con el objeto desplazado 8
píxeles, las acciones inseguras suben del 0 al 10,5&nbsp;% (200 imágenes alteradas), y un cambio de brillo hace
rechazar producto conocido. Las correcciones están diagnosticadas y no
implementadas: localizar y centrar el objeto antes de describirlo, normalizar el brillo, y una regla que compare la
distancia de la imagen a su lazo. La evaluación del asistente no tiene conjunto reservado, y la planta es simulada. El sistema no está desplegado en
ninguna plataforma: corre en un equipo local y se expone con un túnel temporal.
Antes de un piloto habría que recalibrar todo con imágenes de la propia línea.</p>
{table('stack', 'Implementación', ['Herramienta', 'Uso'], stack, widths=[42, 58],
       note='Iconos de Simple Icons (licencia CC0). Las marcas pertenecen a sus titulares.')}
<h2>Referencias</h2>
<ol class="refs">
<li><span>[1]</span><span>S. A. Nene, S. K. Nayar y H. Murase, «Columbia Object Image Library (COIL-100)», Columbia Univ., Nueva York, inf. téc. CUCS-006-96, 1996.</span></li>
<li><span>[2]</span><span>T. Cover y P. Hart, «Nearest neighbor pattern classification», <i>IEEE Trans. Inf. Theory</i>, vol. 13, n.º 1, pp. 21–27, 1967.</span></li>
<li><span>[3]</span><span>N. Dalal y B. Triggs, «Histograms of oriented gradients for human detection», en <i>Proc. IEEE Conf. Comput. Vis. Pattern Recognit.</i>, 2005, pp. 886–893.</span></li>
<li><span>[4]</span><span>T. Ojala, M. Pietikäinen y T. Mäenpää, «Multiresolution gray-scale and rotation invariant texture classification with local binary patterns», <i>IEEE Trans. Pattern Anal. Mach. Intell.</i>, vol. 24, n.º 7, pp. 971–987, 2002.</span></li>
<li><span>[5]</span><span>H. Murase y S. K. Nayar, «Visual learning and recognition of 3-D objects from appearance», <i>Int. J. Comput. Vis.</i>, vol. 14, n.º 1, pp. 5–24, 1995.</span></li>
<li><span>[6]</span><span>Y. Geifman y R. El-Yaniv, «Selective classification for deep neural networks», en <i>Adv. Neural Inf. Process. Syst.</i>, vol. 30, 2017.</span></li>
<li><span>[7]</span><span>F. Pedregosa <i>et al.</i>, «Scikit-learn: Machine learning in Python», <i>J. Mach. Learn. Res.</i>, vol. 12, pp. 2825–2830, 2011.</span></li>
<li><span>[8]</span><span>C. Cortes y V. Vapnik, «Support-vector networks», <i>Mach. Learn.</i>, vol. 20, n.º 3, pp. 273–297, 1995.</span></li>
<li><span>[9]</span><span>L. Breiman, «Random forests», <i>Mach. Learn.</i>, vol. 45, n.º 1, pp. 5–32, 2001.</span></li>
<li><span>[10]</span><span>M. Oquab <i>et al.</i>, «DINOv2: Learning robust visual features without supervision», <i>Trans. Mach. Learn. Res.</i>, 2024.</span></li>
<li><span>[11]</span><span>S. Yao <i>et al.</i>, «ReAct: Synergizing reasoning and acting in language models», en <i>Proc. Int. Conf. Learn. Represent.</i>, 2023.</span></li>
<li><span>[12]</span><span>S. Robertson y H. Zaragoza, «The probabilistic relevance framework: BM25 and beyond», <i>Found. Trends Inf. Retr.</i>, vol. 3, n.º 4, pp. 333–389, 2009.</span></li>
</ol>
"""

wide_intro = figure('sistema', 'Los dos planos de la solución. El servicio de visión decide sobre cada objeto sin modelo de lenguaje; el asistente lo usa como herramienta. El robot recibe una de cuatro órdenes: agarrar, segunda captura, revisión o rechazo; si la imagen no es válida, la de repetir la captura.', wide=True)
fig_prot = figure('protocolos', 'Reparto de las 72 vistas de un objeto en cada protocolo. En B el arco se sortea por objeto; en D se excluyen objetos completos.')

body = (head + '<div class="cols">' + abstract + s1 + wide_intro + s2 + s3 + s4.replace('<h3>B. Validación interna</h3>', fig_prot + '<h3>B. Validación interna</h3>')
        + s5 + s6 + s7 + s8 + s_api + s9 + '</div>')
html = (f'<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Identificación de producto y estimación de '
        f'ángulo con aprendizaje automático clásico — Prueba técnica Indra Group</title><meta name="author" content="Sara Guerra">'
        f'<style>{CSS}</style></head><body>{hyphenate_html(body)}</body></html>')
OUT_HTML.write_text(html, encoding="utf-8")

browsers = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]
exe = next((b for b in browsers if Path(b).exists()), None)
if not exe:
    sys.exit(f"HTML generado en {OUT_HTML}; no se encontró Chrome ni Edge para imprimir el PDF")
subprocess.run([exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={OUT_PDF}",
                OUT_HTML.as_uri()], check=True, capture_output=True, timeout=120)
print(OUT_PDF)
