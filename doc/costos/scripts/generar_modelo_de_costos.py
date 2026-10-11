"""Modelo de costos Azure + caso de negocio (Reto 6). Todo lo calculado son fórmulas sobre las hojas Supuestos y Precios."""
import sys

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

OUT = sys.argv[1]
wb = Workbook()
F = "Arial"
BLUE, BLACK, GREEN = Font(name=F, color="0000FF", size=10), Font(name=F, size=10), Font(name=F, color="008000", size=10)
BOLD, H = Font(name=F, bold=True, size=10), Font(name=F, bold=True, size=10, color="FFFFFF")
TITLE = Font(name=F, bold=True, size=14, color="00495A")
HEAD_FILL, YELLOW, SOFT = PatternFill("solid", fgColor="00495A"), PatternFill("solid", fgColor="FFFF00"), PatternFill("solid", fgColor="EEF3F2")
THIN = Side(style="thin", color="C9D3D1")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
USD, USD2, USD6, PCT, NUM = '$#,##0;($#,##0);"-"', '$#,##0.00;($#,##0.00);"-"', '$#,##0.000000', '0.0%;(0.0%);"-"', '#,##0;(#,##0);"-"'
WRAP = Alignment(wrap_text=True, vertical="top")


def header(ws, row, labels, widths=None):
    for c, t in enumerate(labels, 1):
        cell = ws.cell(row, c, t)
        cell.font, cell.fill, cell.border, cell.alignment = H, HEAD_FILL, BOX, Alignment(wrap_text=True, vertical="center")
    if widths:
        for c, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(c)].width = w


def put(ws, row, col, value, font=BLACK, fmt=None, fill=None, bold=False):
    cell = ws.cell(row, col, value)
    cell.font = Font(name=F, size=10, bold=bold, color=font.color) if bold else font
    cell.border, cell.alignment = BOX, WRAP
    if fmt:
        cell.number_format = fmt
    if fill:
        cell.fill = fill
    return cell


# ------------------------------------------------------------------ Supuestos
S = wb.active
S.title = "Supuestos"
S["A1"], S["A1"].font = "Supuestos del modelo (celdas azules = entradas editables; amarillo = supuesto sin verificar)", TITLE
header(S, 3, ["Grupo", "Parámetro", "Valor", "Unidad", "Origen / nota"], [20, 52, 14, 16, 78])
A = {}  # nombre -> referencia absoluta
r = 4


def a(key, group, label, value, unit, note, fmt=None, unverified=False, formula=False):
    global r
    put(S, r, 1, group)
    put(S, r, 2, label)
    put(S, r, 3, value, BLACK if formula else BLUE, fmt, YELLOW if unverified else None)
    put(S, r, 4, unit)
    put(S, r, 5, note)
    A[key] = f"Supuestos!$C${r}"
    r += 1


a("lines", "Operación", "Líneas (estaciones) automatizadas", 2, "líneas", "Supuesto del caso base. El enunciado no fija el número de estaciones.", NUM, True)
a("cycle", "Operación", "Segundos por objeto", 30, "s", "Supuesto: es el ritmo de la planta simulada del asistente. El enunciado no da la velocidad de línea.", NUM, True)
a("hours", "Operación", "Horas de operación por día", 24, "h", "Enunciado: 24 horas al día.", NUM)
a("days", "Operación", "Días de operación por semana", 5, "días", "Enunciado: 5 días a la semana.", NUM)
a("weeks", "Operación", "Semanas por año", 52, "semanas", "Calendario.", NUM)
a("shifts", "Operación", "Turnos por día", 3, "turnos", "Enunciado: 3 turnos de 8 horas.", NUM)
a("ops", "Operación", "Operarios por turno por estación (hoy)", 1, "personas", "Enunciado: 1 operario por turno por estación.", NUM)
a("days_m", "Operación", "Días de operación por mes", f"={A['days']}*{A['weeks']}/12", "días", "Calculado.", "0.00", formula=True)
a("obj_line", "Operación", "Objetos por línea por mes", f"=3600/{A['cycle']}*{A['hours']}*{A['days_m']}", "objetos", "Calculado.", NUM, formula=True)
a("act", "Modelo", "Fracción de objetos que el robot atiende solo (ACT)", 0.876, "fracción", "Resultado medido en el protocolo A (reports/results.json). En planta dependerá de la calidad de captura.", PCT)
a("wage", "Costo laboral", "Costo mensual cargado de un operario", 600, "USD/mes", "SUPUESTO sin verificar: sustituir por el dato de RR. HH. (salario + prestaciones).", USD, True)
a("fte_exc", "Costo laboral", "Personas por turno por línea para atender excepciones", 0.25, "FTE", "SUPUESTO: alguien resuelve la cola de revisión y las segundas capturas. Con 12 % de excepciones, un cuarto de jornada.", "0.00", True)
a("eng_fte", "Costo laboral", "Dedicación de ingeniería de ML y soporte", 0.2, "FTE", "SUPUESTO: monitoreo, recalibración, altas de producto.", "0.00", True)
a("eng_wage", "Costo laboral", "Costo mensual cargado de un ingeniero", 2500, "USD/mes", "SUPUESTO sin verificar.", USD, True)
a("project", "Inversión", "Costo único del proyecto (desarrollo, integración con el robot, piloto)", 40000, "USD", "SUPUESTO sin verificar: depende del plan de proyecto.", USD, True)
a("pc", "Borde (planta)", "PC industrial por estación", 1800, "USD", "SUPUESTO sin verificar. No es un servicio de Azure. El modelo corre en CPU (unos 28 ms por imagen medidos).", USD, True)
a("cam", "Borde (planta)", "Cámara e iluminación controlada por estación", 1200, "USD", "SUPUESTO sin verificar.", USD, True)
a("amort", "Borde (planta)", "Meses de amortización del equipo", 36, "meses", "Supuesto contable.", NUM)
a("maint", "Borde (planta)", "Mantenimiento anual del equipo", 0.10, "% del costo", "Supuesto.", PCT, True)
a("users_line", "Asistente", "Usuarios activos del asistente por línea", 6, "usuarios", "Supuesto: supervisores, calidad, mantenimiento e ingeniería en 3 turnos.", NUM, True)
a("turns", "Asistente", "Peticiones al asistente por usuario y día", 8, "peticiones", "Supuesto.", NUM, True)
a("tok_in", "Asistente", "Tokens de entrada por petición", 6783, "tokens", "MEDIDO: media de 164 ejecuciones de la evaluación (reports/agent_eval.json).", NUM)
a("tok_out", "Asistente", "Tokens de salida por petición", 176, "tokens", "MEDIDO: misma fuente.", NUM)
a("cache", "Asistente", "Fracción de la entrada servida desde caché", 0, "fracción", "Palanca FinOps: las instrucciones y los contratos de tools (~3.300 tokens) se repiten en cada llamada.", PCT)
a("cpu_turn", "Asistente", "Segundos de CPU activa por petición", 3, "s", "Medido en pruebas manuales: 2 a 4 s por turno.", NUM)
a("ag_vcpu", "Asistente", "vCPU del contenedor del asistente", 0.5, "vCPU", "Dimensionamiento.", "0.00")
a("ag_gib", "Asistente", "Memoria del contenedor del asistente", 1, "GiB", "Dimensionamiento.", "0.00")
a("insp", "Visión en nube", "Inspecciones manuales y de staging por línea y mes", 1000, "imágenes", "Supuesto. La inferencia de la línea NO pasa por la nube: corre en el borde.", NUM, True)
a("vi_vcpu", "Visión en nube", "vCPU del contenedor de visión en nube", 1, "vCPU", "Dimensionamiento.", "0.00")
a("vi_gib", "Visión en nube", "Memoria del contenedor de visión en nube", 2, "GiB", "Dimensionamiento (modelo de 34,6 MB más dependencias).", "0.00")
a("vi_s", "Visión en nube", "Segundos facturados por inspección", 1, "s", "Conservador: la inferencia mide 0,03 s; se factura el segundo de arranque y respuesta.", "0.00")
a("img_kb", "Datos", "Tamaño de una imagen de planta guardada", 200, "KB", "SUPUESTO: cámara industrial comprimida. Las de COIL-100 pesan ~15 KB.", NUM, True)
a("img_sample", "Datos", "Muestra de imágenes ACT que se guarda para monitoreo", 0.01, "fracción", "Supuesto: se guardan todas las no ACT y un 1 % de las ACT.", PCT)
a("retention", "Datos", "Meses de retención de imágenes", 3, "meses", "Supuesto. Las del dataset de reentrenamiento se conservan aparte.", NUM)
a("pg_gb", "Datos", "Almacenamiento de PostgreSQL", 32, "GB", "Mínimo del servicio; eventos, auditoría y aprobaciones caben de sobra.", NUM)
a("log_fixed", "Observabilidad", "Registros fijos por mes", 3, "GB", "Supuesto: plataforma y asistente.", NUM, True)
a("log_line", "Observabilidad", "Registros por línea y mes", 2.5, "GB", "Supuesto: una línea de auditoría por inferencia (~1 KB) más métricas.", "0.0", True)
a("log_free", "Observabilidad", "Ingesta gratuita mensual de Log Analytics", 5, "GB", "El medidor de la API empieza a cobrar a partir de 5 GB.", NUM)
a("train_h", "MLOps", "Horas de cómputo de entrenamiento por mes", 10, "h", "Supuesto: el notebook completo tarda ~25 min; reentrenos y validaciones de productos nuevos.", NUM, True)
a("acr_gb", "MLOps", "Imágenes de contenedor almacenadas", 10, "GB", "La imagen actual pesa 3,6 GB; se guardan pocas versiones.", NUM)
a("kv_ops", "Seguridad", "Operaciones de Key Vault por mes", 100000, "operaciones", "Supuesto holgado.", NUM)
a("iot_units", "Telemetría", "Unidades de IoT Hub S1", 1, "unidades", "Según la documentación de Azure, una unidad S1 admite 400.000 mensajes al día (verificar). Dos líneas generan ~5.800.", NUM)
a("h_month", "Constantes", "Horas por mes", 730, "h", "Convención de facturación de Azure.", NUM)

# ------------------------------------------------------------------ Precios
P = wb.create_sheet("Precios")
P["A1"], P["A1"].font = "Precios de lista de Azure usados por el modelo (USD, región East US 2)", TITLE
P["A2"] = ("Fuente: API pública de precios de Azure, https://prices.azure.com/api/retail/prices, consultada el 2026-10-10. "
           "Precio de lista de pago por uso, sin impuestos, descuentos ni reservas.")
P["A2"].font = BLACK
header(P, 4, ["Servicio", "Medidor (nombre en la API)", "Unidad", "Precio USD", "Verificado en la API", "Nota"], [30, 46, 16, 14, 14, 64])
PR = {}
r = 5


def p(key, service, meter, unit, price, verified=True, note=""):
    global r
    put(P, r, 1, service)
    put(P, r, 2, meter)
    put(P, r, 3, unit)
    put(P, r, 4, price, BLUE, USD6, None if verified else YELLOW)
    put(P, r, 5, "sí" if verified else "NO")
    put(P, r, 6, note)
    PR[key] = f"Precios!$D${r}"
    r += 1


p("aca_cpu", "Azure Container Apps", "Standard vCPU Active Usage", "1 segundo", 0.000024)
p("aca_idle", "Azure Container Apps", "Standard vCPU Idle Usage", "1 segundo", 0.000003)
p("aca_mem", "Azure Container Apps", "Standard Memory Active Usage / Idle Usage", "1 GiB-segundo", 0.000003)
p("aca_req", "Azure Container Apps", "Standard Requests", "1 millón", 0.4, note="No se descuenta la franquicia gratuita mensual del servicio: el modelo es conservador.")
p("oai_in", "Azure OpenAI", "gpt 4.1 mini Inp glbl Tokens", "1.000 tokens", 0.0004, note="Despliegue global. En zona de datos: 0,00044.")
p("oai_cached", "Azure OpenAI", "gpt 4.1 mini cached Inp glbl Tokens", "1.000 tokens", 0.0001)
p("oai_out", "Azure OpenAI", "gpt 4.1 mini Outp glbl Tokens", "1.000 tokens", 0.0016, note="En zona de datos: 0,00176.")
p("oai_in_dz", "Azure OpenAI", "gpt 4.1 mini Inp Data Zone Tokens", "1.000 tokens", 0.00044, note="Los datos no salen de la zona geográfica elegida.")
p("oai_out_dz", "Azure OpenAI", "gpt 4.1 mini Outp Data Zone Tokens", "1.000 tokens", 0.00176)
p("nano_in", "Azure OpenAI", "gpt 4.1 nano Inp glbl Tokens", "1.000 tokens", 0.0001, note="Modelo más pequeño: habría que repetir la evaluación del agente antes de adoptarlo.")
p("nano_out", "Azure OpenAI", "gpt 4.1 nano Outp glbl Tokens", "1.000 tokens", 0.0004)
p("pg", "Azure Database for PostgreSQL (servidor flexible)", "B1MS", "1 hora", 0.017, note="En Brazil South el mismo medidor cuesta 0,035: el doble.")
p("pg_sto", "Azure Database for PostgreSQL (servidor flexible)", "Almacenamiento aprovisionado", "1 GB-mes", 0.115, False, "NO verificado: la consulta a la API no devolvió este medidor. Valor de referencia; confirmar en la calculadora de Azure.")
p("blob", "Blob Storage", "Hot LRS Data Stored", "1 GB-mes", 0.0184)
p("blob_w", "Blob Storage", "Hot LRS Write Operations", "10.000 operaciones", 0.05)
p("iot", "IoT Hub", "S1 Unit", "1 unidad-mes", 25, note="El nivel básico (B1, 10 USD) no admite IoT Edge según la documentación (verificar).")
p("acr", "Container Registry", "Basic Registry Unit", "1 día", 0.1666)
p("acr_sto", "Container Registry", "Data Stored", "1 GB-mes", 0.1, note="El nivel básico incluye una cuota de almacenamiento que aquí no se descuenta.")
p("kv", "Key Vault", "Operations (Standard)", "10.000 operaciones", 0.03)
p("log", "Log Analytics", "Analytics Logs Data Ingestion", "1 GB", 2.76)
p("vm", "Máquinas virtuales (cómputo de Azure ML)", "D4s v5 (Linux)", "1 hora", 0.192, note="Azure Machine Learning no cobra por el servicio, solo por el cómputo. Prioridad baja: 0,0384.")
p("search", "Azure AI Search (opcional, no incluido)", "Basic Unit", "1 hora", 0.101)
p("apim", "API Management (opcional, no incluido)", "Basic v2 Unit", "1 hora", 0.20548)

# ------------------------------------------------------------------ Costo mensual
C = wb.create_sheet("Costo mensual")
C["A1"], C["A1"].font = "Costo mensual en Azure — caso base (USD/mes)", TITLE
header(C, 3, ["Componente", "Servicio de Azure", "Cómo se calcula", "Fijo", "Variable por línea", "Total caso base"], [30, 30, 70, 14, 16, 16])
turns_line = f"{A['users_line']}*{A['turns']}*{A['days_m']}"  # peticiones por línea y mes
secs = f"{A['h_month']}*3600"
rows = [
    ("Asistente (siempre encendido)", "Container Apps",
     "Una réplica mínima todo el mes en reposo (vCPU en reposo + memoria). Variable: CPU activa y peticiones de cada turno de conversación.",
     f"={A['ag_vcpu']}*{secs}*{PR['aca_idle']}+{A['ag_gib']}*{secs}*{PR['aca_mem']}",
     f"={turns_line}*{A['cpu_turn']}*{A['ag_vcpu']}*({PR['aca_cpu']}-{PR['aca_idle']})+{turns_line}/1000000*{PR['aca_req']}"),
    ("Modelo de lenguaje del asistente", "Azure OpenAI (gpt-4.1-mini)",
     "Peticiones × (entrada no cacheada + entrada cacheada + salida). Precios por 1.000 tokens.",
     "=0",
     f"={turns_line}*({A['tok_in']}*(1-{A['cache']})*{PR['oai_in']}+{A['tok_in']}*{A['cache']}*{PR['oai_cached']}+{A['tok_out']}*{PR['oai_out']})/1000"),
    ("Visión en nube (inspecciones y staging)", "Container Apps, escala a cero",
     "Solo se paga mientras atiende: inspecciones × segundos × (vCPU + memoria). La inferencia de la línea corre en el borde.",
     "=0",
     f"={A['insp']}*{A['vi_s']}*({A['vi_vcpu']}*{PR['aca_cpu']}+{A['vi_gib']}*{PR['aca_mem']})"),
    ("Estado de planta, auditoría y aprobaciones", "PostgreSQL servidor flexible B1ms",
     "Cómputo todo el mes + almacenamiento aprovisionado.",
     f"={A['h_month']}*{PR['pg']}+{A['pg_gb']}*{PR['pg_sto']}", "=0"),
    ("Imágenes (excepciones, muestra y reentrenamiento)", "Blob Storage Hot LRS",
     "Imágenes guardadas = objetos × (no ACT + muestra de ACT). GB retenidos × precio + operaciones de escritura.",
     "=0",
     f"={A['obj_line']}*((1-{A['act']})+{A['act']}*{A['img_sample']})*({A['img_kb']}/1000000*{A['retention']}*{PR['blob']}+{PR['blob_w']}/10000)"),
    ("Telemetría y despliegue al borde", "IoT Hub S1 + IoT Edge",
     "Unidades × precio. El runtime de IoT Edge no tiene costo. Una unidad cubre holgadamente decenas de líneas.",
     f"={A['iot_units']}*{PR['iot']}", "=0"),
    ("Registro de imágenes de contenedor", "Container Registry Basic",
     "Unidad diaria × 365/12 + GB almacenados.",
     f"={PR['acr']}*365/12+{A['acr_gb']}*{PR['acr_sto']}", "=0"),
    ("Secretos", "Key Vault Standard", "Operaciones / 10.000 × precio.", f"={A['kv_ops']}/10000*{PR['kv']}", "=0"),
    ("Registros y monitoreo", "Log Analytics + Application Insights",
     "GB ingeridos por encima de la franquicia × precio. La parte por línea se cobra completa (la franquicia se consume con la parte fija).",
     f"=MAX(0,{A['log_fixed']}-{A['log_free']})*{PR['log']}",
     f"=IF({A['log_fixed']}>={A['log_free']},{A['log_line']},MAX(0,{A['log_line']}-({A['log_free']}-{A['log_fixed']})/{A['lines']}))*{PR['log']}"),
    ("Entrenamiento y registro de modelos", "Azure Machine Learning (cómputo D4s v5)",
     "Horas de cómputo × precio. El clúster escala a cero entre trabajos.",
     f"={A['train_h']}*{PR['vm']}", "=0"),
]
r = 4
for comp, svc, how, fixed, var in rows:
    put(C, r, 1, comp)
    put(C, r, 2, svc)
    put(C, r, 3, how)
    put(C, r, 4, fixed, BLACK, USD2)
    put(C, r, 5, var, BLACK, USD2)
    put(C, r, 6, f"=D{r}+E{r}*{A['lines']}", BLACK, USD2)
    r += 1
first, last = 4, r - 1
put(C, r, 1, "Total Azure", bold=True)
put(C, r, 2, "")
put(C, r, 3, "Suma de los componentes. Precio de lista, sin impuestos ni descuentos.")
for col in (4, 5, 6):
    L = get_column_letter(col)
    put(C, r, col, f"=SUM({L}{first}:{L}{last})", BLACK, USD2, SOFT, bold=True)
AZ_FIXED, AZ_VAR, AZ_TOTAL = f"'Costo mensual'!$D${r}", f"'Costo mensual'!$E${r}", f"'Costo mensual'!$F${r}"
r += 2
put(C, r, 1, "Equipo en planta (no es Azure)", bold=True)
r += 1
header(C, r, ["Componente", "Qué es", "Cómo se calcula", "Fijo", "Variable por línea", "Total caso base"])
r += 1
put(C, r, 1, "PC industrial, cámara e iluminación")
put(C, r, 2, "Equipo propio en cada estación")
put(C, r, 3, "(PC + cámara) / meses de amortización + mantenimiento anual / 12.")
put(C, r, 4, "=0", BLACK, USD2)
put(C, r, 5, f"=({A['pc']}+{A['cam']})/{A['amort']}+({A['pc']}+{A['cam']})*{A['maint']}/12", BLACK, USD2)
put(C, r, 6, f"=D{r}+E{r}*{A['lines']}", BLACK, USD2)
EDGE_VAR, EDGE_TOTAL = f"'Costo mensual'!$E${r}", f"'Costo mensual'!$F${r}"
r += 2
put(C, r, 1, "Opcionales no incluidos (para el análisis de trade-offs)", bold=True)
r += 1
for name, svc, how, f in [
    ("Búsqueda de procedimientos gestionada", "Azure AI Search Basic", "Unidad × horas del mes. No se incluye: con 6 procedimientos, la búsqueda léxica en proceso basta.", f"={A['h_month']}*{PR['search']}"),
    ("Pasarela de API con cuotas por usuario", "API Management Basic v2", "Unidad × horas del mes. No se incluye a esta escala; se justifica con varias plantas.", f"={A['h_month']}*{PR['apim']}"),
]:
    put(C, r, 1, name)
    put(C, r, 2, svc)
    put(C, r, 3, how)
    put(C, r, 4, f, BLACK, USD2)
    put(C, r, 5, "")
    put(C, r, 6, f"=D{r}", BLACK, USD2)
    r += 1
put(C, r + 1, 1, "No modelado: red privada (private endpoints, VPN o ExpressRoute), Microsoft Entra ID (se asume inquilino existente), "
                 "copias de seguridad adicionales, soporte de Azure, impuestos y tráfico de salida.").font = BLACK

# ------------------------------------------------------------------ Caso de negocio
B = wb.create_sheet("Caso de negocio")
B["A1"], B["A1"].font = "Caso de negocio — operación actual frente a la automatizada (USD/mes, caso base)", TITLE
header(B, 3, ["Concepto", "USD/mes", "Cómo se calcula"], [58, 16, 90])
biz = [
    ("OPERACIÓN ACTUAL", None, None),
    ("Operarios de identificación y alineación", f"={A['lines']}*{A['shifts']}*{A['ops']}*{A['wage']}", "Líneas × turnos × operarios por turno × costo mensual."),
    ("OPERACIÓN AUTOMATIZADA", None, None),
    ("Azure", f"={AZ_TOTAL}", "Hoja «Costo mensual»."),
    ("Equipo en planta (amortización y mantenimiento)", f"={EDGE_TOTAL}", "Hoja «Costo mensual»."),
    ("Personal para excepciones (revisión y segundas capturas)", f"={A['lines']}*{A['shifts']}*{A['fte_exc']}*{A['wage']}", "Líneas × turnos × fracción de jornada × costo mensual."),
    ("Ingeniería de ML y soporte", f"={A['eng_fte']}*{A['eng_wage']}", "Dedicación × costo mensual."),
]
r = 4
idx = {}
for label, f, how in biz:
    if f is None:
        put(B, r, 1, label, bold=True, fill=SOFT)
        put(B, r, 2, "", fill=SOFT)
        put(B, r, 3, "", fill=SOFT)
    else:
        put(B, r, 1, label)
        put(B, r, 2, f, GREEN if f.startswith("='Costo") else BLACK, USD)
        put(B, r, 3, how)
        idx[label] = r
    r += 1
cur = f"B{idx['Operarios de identificación y alineación']}"
new_rows = [idx[k] for k in ("Azure", "Equipo en planta (amortización y mantenimiento)", "Personal para excepciones (revisión y segundas capturas)", "Ingeniería de ML y soporte")]
put(B, r, 1, "Total operación automatizada", bold=True)
put(B, r, 2, f"=SUM(B{new_rows[0]}:B{new_rows[-1]})", BLACK, USD, SOFT, bold=True)
put(B, r, 3, "Suma de los cuatro conceptos.")
NEW = f"B{r}"
r += 2
out = [
    ("Ahorro mensual", f"={cur}-{NEW}", USD, "Actual − automatizada. Negativo significa que automatizar cuesta más."),
    ("Ahorro mensual (%)", f"=IF({cur}=0,0,({cur}-{NEW})/{cur})", PCT, "Sobre el costo actual."),
    ("Inversión única del proyecto", f"={A['project']}", USD, "Hoja «Supuestos»."),
    ("Meses para recuperar la inversión", f"=IF({cur}-{NEW}<=0,\"no se recupera\",{A['project']}/({cur}-{NEW}))", "0.0", "Inversión / ahorro mensual."),
    ("Objetos procesados por mes", f"={A['obj_line']}*{A['lines']}", NUM, "Objetos por línea × líneas."),
    ("Costo de Azure por cada 1.000 objetos", f"=IF({A['obj_line']}*{A['lines']}=0,0,{AZ_TOTAL}/({A['obj_line']}*{A['lines']})*1000)", USD2, "Indicador unitario de FinOps."),
    ("Costo total automatizado por cada 1.000 objetos", f"=IF({A['obj_line']}*{A['lines']}=0,0,{NEW}/({A['obj_line']}*{A['lines']})*1000)", USD2, "Incluye personas y equipo."),
    ("Costo actual por cada 1.000 objetos", f"=IF({A['obj_line']}*{A['lines']}=0,0,{cur}/({A['obj_line']}*{A['lines']})*1000)", USD2, "Referencia."),
    ("Peso de Azure en el costo automatizado", f"=IF({NEW}=0,0,B{idx['Azure']}/{NEW})", PCT, "Cuánto del costo recurrente es nube."),
]
for label, f, fmt, how in out:
    put(B, r, 1, label, bold=True)
    put(B, r, 2, f, GREEN if f == f"={A['project']}" else BLACK, fmt)
    put(B, r, 3, how)
    r += 1
put(B, r + 1, 1, "El resultado depende sobre todo de tres supuestos sin verificar (amarillos en «Supuestos»): el costo del operario, "
                 "el personal que queda para excepciones y la inversión del proyecto. Sustituirlos antes de usar la cifra.").font = BLACK

# ------------------------------------------------------------------ Escenarios
E = wb.create_sheet("Escenarios")
E["A1"], E["A1"].font = "Escenarios — cómo escala el costo con el número de líneas (USD/mes)", TITLE
header(E, 3, ["Líneas", "Azure", "Azure por línea", "Equipo en planta", "Personas (excepciones + ingeniería)", "Total automatizado",
              "Operación actual", "Ahorro mensual", "Meses para recuperar"], [10, 14, 16, 16, 22, 18, 18, 16, 18])
r = 4
for n in (1, 2, 5, 10, 20):
    put(E, r, 1, n, BLUE, NUM)
    put(E, r, 2, f"={AZ_FIXED}+{AZ_VAR}*A{r}", BLACK, USD)
    put(E, r, 3, f"=B{r}/A{r}", BLACK, USD)
    put(E, r, 4, f"={EDGE_VAR}*A{r}", BLACK, USD)
    put(E, r, 5, f"=A{r}*{A['shifts']}*{A['fte_exc']}*{A['wage']}+{A['eng_fte']}*{A['eng_wage']}", BLACK, USD)
    put(E, r, 6, f"=B{r}+D{r}+E{r}", BLACK, USD)
    put(E, r, 7, f"=A{r}*{A['shifts']}*{A['ops']}*{A['wage']}", BLACK, USD)
    put(E, r, 8, f"=G{r}-F{r}", BLACK, USD)
    put(E, r, 9, f"=IF(H{r}<=0,\"no se recupera\",{A['project']}/H{r})", BLACK, "0.0")
    r += 1
put(E, r + 1, 1, "Se mantienen constantes la inversión del proyecto y la dedicación de ingeniería: es una simplificación. "
                 "Con más líneas, ambas crecerían, aunque menos que proporcionalmente.").font = BLACK
r += 4
E.cell(r, 1, "Sensibilidad del modelo de lenguaje (caso base de líneas)").font = BOLD
r += 1
header(E, r, ["Opción", "USD/mes", "", "", "Qué cambia"])
r += 1
turns_all = f"{turns_line}*{A['lines']}"
for label, f, note in [
    ("gpt-4.1-mini, despliegue global (base)", f"={turns_all}*({A['tok_in']}*{PR['oai_in']}+{A['tok_out']}*{PR['oai_out']})/1000", "El del modelo de costos, sin caché."),
    ("gpt-4.1-mini, zona de datos", f"={turns_all}*({A['tok_in']}*{PR['oai_in_dz']}+{A['tok_out']}*{PR['oai_out_dz']})/1000", "Los datos no salen de la zona geográfica: +10 %."),
    ("gpt-4.1-mini con el 50 % de la entrada en caché", f"={turns_all}*({A['tok_in']}*0.5*{PR['oai_in']}+{A['tok_in']}*0.5*{PR['oai_cached']}+{A['tok_out']}*{PR['oai_out']})/1000", "Instrucciones y contratos de tools repetidos en cada llamada."),
    ("gpt-4.1-nano, despliegue global", f"={turns_all}*({A['tok_in']}*{PR['nano_in']}+{A['tok_out']}*{PR['nano_out']})/1000", "Cuatro veces más barato; exige repetir la evaluación del agente."),
]:
    put(E, r, 1, label)
    put(E, r, 2, f, BLACK, USD2)
    put(E, r, 5, note)
    r += 1
E.column_dimensions["A"].width = 44
E.column_dimensions["E"].width = 46

# ------------------------------------------------------------------ Léeme
R = wb.create_sheet("Léeme", 0)
R["A1"], R["A1"].font = "Modelo de costos — arquitectura Azure para pick & pack con visión (Reto 6)", TITLE
lines = [
    "Qué es: costo mensual de la arquitectura propuesta en Azure y caso de negocio frente a la operación manual actual.",
    "Cómo usarlo: cambiar SOLO las celdas con texto azul de la hoja «Supuestos» (y los precios de «Precios» si cambian). Todo lo demás son fórmulas.",
    "Colores: texto azul = entrada editable · negro = fórmula · verde = dato traído de otra hoja · relleno amarillo = supuesto sin verificar.",
    "Hojas: Supuestos (entradas) · Precios (tarifas de Azure con su medidor) · Costo mensual (por componente) · Caso de negocio · Escenarios.",
    "Precios: lista de pago por uso en East US 2, tomados de la API pública de precios de Azure el 2026-10-10. Sin impuestos, descuentos ni reservas.",
    "Advertencia: las cifras laborales, de equipo y de inversión son supuestos del autor, no datos del cliente. El caso de negocio no es válido hasta sustituirlos.",
    "Documento que lo acompaña: doc/16_arquitectura_azure_y_finops.md.",
]
for i, t in enumerate(lines, 3):
    R.cell(i, 1, t).font = BLACK
R.column_dimensions["A"].width = 150

for ws in wb.worksheets:
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A4" if ws.title in ("Supuestos", "Costo mensual", "Caso de negocio", "Escenarios") else None
P.freeze_panes = "A5"
S["C4"].comment = Comment("Cambia este valor para ver otro tamaño de planta. La hoja «Escenarios» ya compara 1, 2, 5, 10 y 20 líneas.", "Modelo")
wb.save(OUT)
print("guardado", OUT)
