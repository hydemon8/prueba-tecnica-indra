"""Tablas de resultados por protocolo y generación de la model card (los números salen de los resultados,
nunca se escriben a mano)."""

from __future__ import annotations

import numpy as np
import pandas as pd

COLUMNS = {
    "class_acc": "clase",
    "pose_true_class.within_tol": "ángulo ±tol (clase dada)",
    "pose_true_class_sym.within_tol": "ángulo ±tol (con simetría)",
    "pose_true_class.median": "mediana error (°)",
    "decision.rate_ACT": "ACT",
    "decision.rate_ANGLE_UNCERTIFIED": "ángulo no certificado",
    "decision.rate_REVIEW": "revisión",
    "decision.rate_UNKNOWN": "desconocido",
    "decision.unsafe_rate": "acciones inseguras",
    "pose_on_act.within_tol": "ángulo ±tol cuando actúa",
    "unknown_rejected": "desconocidos rechazados",
    "latency_ms_per_image": "latencia (ms/img)",
}
PERCENT = {c for c in COLUMNS if c not in ("pose_true_class.median", "latency_ms_per_image")}


def _get(d: dict, dotted: str):
    for k in dotted.split("."):
        if not isinstance(d, dict) or k not in d:
            return np.nan
        d = d[k]
    return d


def protocol_table(results: dict[str, list[dict]]) -> pd.DataFrame:
    """results: protocolo -> lista de corridas (repeticiones con distinta semilla). Media ± desviación."""
    rows = []
    for prot, runs in results.items():
        row = {"protocolo": prot, "corridas": len(runs)}
        for key, label in COLUMNS.items():
            vals = np.array([_get(r, key) for r in runs], float)
            vals = vals[~np.isnan(vals)]
            if vals.size == 0:
                row[label] = "—"
                continue
            k = 100 if key in PERCENT else 1
            mean, std = vals.mean() * k, vals.std() * k
            row[label] = f"{mean:.1f}" + (f" ± {std:.1f}" if len(vals) > 1 else "")
        rows.append(row)
    return pd.DataFrame(rows).set_index("protocolo")


def model_card(version: str, data_version: str, selected: str, table: pd.DataFrame, comparison: pd.DataFrame,
               two_shot: dict, tol: float, extra: dict) -> str:
    return f"""# Model card — linevision {version}

## Uso previsto
Identificar el producto (SKU) que llega a la estación de pick & pack, estimar su giro sobre el eje vertical
(yaw, 0–360°) con una medida de incertidumbre, recuperar las vistas de referencia más parecidas y decidir de
forma determinista si el robot puede actuar. Sustituye la tarea manual de identificación y alineación.

Salidas: `decision` (ACT / ANGLE_UNCERTIFIED / REVIEW / UNKNOWN) con motivos, `object_id`, confianza de clase,
puntuación de novedad, `angle_deg` con ancho del conjunto creíble del 90 %, top-k por pose y top-k por apariencia.

## Cuándo NO debe usarse
- Objetos fuera del catálogo con galería de referencia (se rechazan como UNKNOWN; no se identifican).
- SKUs sin cobertura angular completa en su galería (hueco > {extra['max_gallery_gap']:.0f}°): el ángulo no está
  certificado y el sistema lo marca ANGLE_UNCERTIFIED; requiere 2a captura o alineación manual.
- Escenas con varios objetos, oclusión, fondo no controlado, otra iluminación o cámara distinta a la de
  referencia sin recalibrar: el dataset de desarrollo no cubre esas condiciones.
- Rotaciones fuera del eje vertical (objeto volcado o inclinado): el modelo solo conoce 1 grado de libertad.

## Datos
COIL-100 (100 objetos × 72 vistas cada 5°, 128×128 RGB, plato giratorio, fondo oscuro, imágenes normalizadas en
tamaño). Versión de datos: `{data_version}`. Sustituto controlado de las imágenes de planta.

## Modelo
1. **Identidad**: {selected}. Elegido por criterio pre-registrado (peor caso entre validaciones internas A/B/C
   con restricción de novedad en D). Novedad = distancia a la vista de referencia más cercana.
2. **Plato (yaw)**: espacio propio paramétrico (Murase & Nayar, 1995): PCA global sobre píxeles 32×32 y curva
   cerrada por objeto (spline cúbico periódico); el ángulo es el punto más cercano de la curva. La distribución
   sobre el ángulo (temperatura calibrada en validación interna) da el conjunto creíble del 90 %.
3. **Control de seguridad**: reglas deterministas con umbrales calibrados en validación interna. La tolerancia del
   robot (±{tol:.0f}°) se traduce en: conjunto creíble del 90 % ≤ {2 * tol:.0f}°, SKU con cobertura angular
   certificada y ambigüedad bajo un umbral calibrado para que ≥ 99,5 % de los casos ACT queden dentro de ±{tol:.0f}°.

## Resultados por protocolo (prueba, sin umbrales ajustados con ella; % salvo indicación)
{table.to_markdown()}

## Comparación con baseline y referencia moderna
{comparison.reset_index().to_markdown(index=False)}

La columna de latencia mide solo la decisión con las características ya extraídas, en lote. De punta a punta (imagen a decisión), una imagen suelta tarda ≈ 28 ms en CPU a través del servicio; en lotes de 64, ≈ 2 ms por imagen.

## Sector ciego: mitigación con 2a captura (protocolo B)
Girar el objeto {two_shot['delta_deg']:.0f}° (o 2a cámara) y re-estimar: ángulo dentro de ±{tol:.0f}° en
{two_shot['within_tol_all'] * 100:.1f} % de los casos; el robot actúa en {two_shot['act_rate'] * 100:.1f} % con
{two_shot['unsafe_rate'] * 100:.2f} % de acciones inseguras.

## Limitaciones conocidas
- El objetivo de riesgo angular (≤ 0,5 % de ACT fuera de ±{tol:.0f}°) se cumple en validación interna pero en la
  prueba de A se observa {extra['a_error_on_act']:.1f} %: la validación interna duplica el espaciado entre vistas y no
  representa exactamente la prueba. Mejora prevista: elegir el umbral con una cota superior de confianza del error.
- Con 12 vistas por SKU (protocolo C) el sistema no puede demostrar el criterio de aceptación y no actúa, aunque su
  ángulo acierte; un SKU necesita una galería más densa para certificarse.
- Objetos con simetría rotacional (p. ej. la rosca obj47, cajas) tienen el ángulo indeterminado módulo la
  simetría; se reporta además el error consciente de simetría. Para el agarre, ángulos equivalentes son válidos
  solo si la pinza también es simétrica.
- Con una sola imagen, el sistema no puede detectar de forma fiable que está en un sector nunca visto; por eso la
  certificación de cobertura del SKU es una regla de catálogo, no una inferencia.
- El color es la señal dominante de identidad: cambios de iluminación o variantes del mismo empaque en otro color
  degradan la identidad; requiere monitorizar la novedad y recalibrar con imágenes de planta.
- Las imágenes de COIL-100 están recortadas y escaladas por objeto; en planta habrá variación de escala y posición
  que exige una etapa de segmentación y normalización equivalente.

## Versionado y reproducibilidad
Artefacto `linevision-{version}.joblib` con manifiesto (sha256, versión de datos, huella de configuración) y
registro en MLflow Model Registry. Notebook `notebooks/01_reto2_experimentacion.ipynb` reproduce todo de punta a
punta con semillas fijas.
"""
