# Model card — linevision 4e39f878-rf

## Uso previsto
Identificar el producto (SKU) que llega a la estación de pick & pack, estimar su giro sobre el eje vertical
(yaw, 0–360°) con una medida de incertidumbre, recuperar las vistas de referencia más parecidas y decidir de
forma determinista si el robot puede actuar. Sustituye la tarea manual de identificación y alineación.

Salidas: `decision` (ACT / ANGLE_UNCERTIFIED / REVIEW / UNKNOWN) con motivos, `object_id`, confianza de clase,
puntuación de novedad, `angle_deg` con ancho del conjunto creíble del 90 %, top-k por pose y top-k por apariencia.

## Cuándo NO debe usarse
- Objetos fuera del catálogo con galería de referencia (se rechazan como UNKNOWN; no se identifican).
- SKUs sin cobertura angular completa en su galería (hueco > 30°): el ángulo no está
  certificado y el sistema lo marca ANGLE_UNCERTIFIED; requiere 2a captura o alineación manual.
- Escenas con varios objetos, oclusión, fondo no controlado, otra iluminación o cámara distinta a la de
  referencia sin recalibrar: el dataset de desarrollo no cubre esas condiciones.
- Rotaciones fuera del eje vertical (objeto volcado o inclinado): el modelo solo conoce 1 grado de libertad.

## Datos
COIL-100 (100 objetos × 72 vistas cada 5°, 128×128 RGB, plato giratorio, fondo oscuro, imágenes normalizadas en
tamaño). Versión de datos: `4e39f8783785bc2d`. Sustituto controlado de las imágenes de planta.

## Modelo
1. **Identidad**: hsv|rf(n_estimators=500). Elegido por criterio pre-registrado (peor caso entre validaciones internas A/B/C
   con restricción de novedad en D). Novedad = distancia a la vista de referencia más cercana.
2. **Plato (yaw)**: espacio propio paramétrico (Murase & Nayar, 1995): PCA global sobre píxeles 32×32 y curva
   cerrada por objeto (spline cúbico periódico); el ángulo es el punto más cercano de la curva. La distribución
   sobre el ángulo (temperatura calibrada en validación interna) da el conjunto creíble del 90 %.
3. **Control de seguridad**: reglas deterministas con umbrales calibrados en validación interna. La tolerancia del
   robot (±10°) se traduce en: conjunto creíble del 90 % ≤ 20°, SKU con cobertura angular
   certificada y ambigüedad bajo un umbral calibrado para que ≥ 99,5 % de los casos ACT queden dentro de ±10°.

## Resultados por protocolo (prueba, evaluada una sola vez; % salvo indicación)
| protocolo   |   corridas | clase      | ángulo ±tol (clase dada)   | ángulo ±tol (con simetría)   | mediana error (°)   | ACT       | ángulo no certificado   | revisión   | desconocido   | acciones inseguras   | ángulo ±tol cuando actúa   | desconocidos rechazados   | latencia (ms/img)   |
|:------------|-----------:|:-----------|:---------------------------|:-----------------------------|:--------------------|:----------|:------------------------|:-----------|:--------------|:---------------------|:---------------------------|:--------------------------|:--------------------|
| A           |          1 | 99.9       | 97.0                       | 97.1                         | 0.5                 | 87.6      | 12.1                    | 0.2        | 0.1           | 0.7                  | 99.2                       | —                         | 0.2                 |
| B           |          3 | 99.0 ± 0.4 | 55.3 ± 1.6                 | 60.9 ± 1.6                   | 8.2 ± 0.5           | 0.0 ± 0.0 | 93.1 ± 1.8              | 6.1 ± 1.7  | 0.8 ± 0.4     | 0.0 ± 0.0            | —                          | —                         | 0.2 ± 0.1           |
| C           |          1 | 99.6       | 95.0                       | 95.5                         | 1.5                 | 0.0       | 99.3                    | 0.7        | 0.0           | 0.0                  | —                          | —                         | 0.1                 |
| D           |          3 | —          | —                          | —                            | —                   | 0.0 ± 0.0 | 0.1 ± 0.2               | 0.0 ± 0.1  | 99.8 ± 0.3    | 0.0 ± 0.0            | —                          | 99.8 ± 0.3                | 0.1 ± 0.0           |

## Comparación con baseline y referencia moderna
| protocolo   | modelo                             | clase      | ángulo ±tol (clase dada)   | acciones inseguras   | desconocidos rechazados   | latencia (ms/img)   |
|:------------|:-----------------------------------|:-----------|:---------------------------|:---------------------|:--------------------------|:--------------------|
| A           | baseline PCA+1-NN                  | 99.8       | 96.1                       | 4.1                  | —                         | 0.0                 |
| A           | clásico (hsv|rf(n_estimators=500)) | 99.9       | 97.0                       | 0.7                  | —                         | 0.2                 |
| A           | referencia DINOv2                  | 100.0      | 95.3                       | 0.4                  | —                         | 0.0                 |
| B           | baseline PCA+1-NN                  | 84.2 ± 0.8 | 28.2 ± 0.1                 | 72.7 ± 0.1           | —                         | 0.0 ± 0.0           |
| B           | clásico (hsv|rf(n_estimators=500)) | 99.0 ± 0.4 | 55.3 ± 1.6                 | 0.0 ± 0.0            | —                         | 0.2 ± 0.1           |
| B           | referencia DINOv2                  | 99.8 ± 0.3 | 21.8 ± 0.3                 | 0.0 ± 0.0            | —                         | 0.0 ± 0.0           |
| C           | baseline PCA+1-NN                  | 94.2       | 74.1                       | 28.3                 | —                         | 0.0                 |
| C           | clásico (hsv|rf(n_estimators=500)) | 99.6       | 95.0                       | 0.0                  | —                         | 0.1                 |
| C           | referencia DINOv2                  | 100.0      | 87.7                       | 0.0                  | —                         | 0.0                 |
| D           | baseline PCA+1-NN                  | —          | —                          | 100.0 ± 0.0          | 0.0 ± 0.0                 | 0.0 ± 0.0           |
| D           | clásico (hsv|rf(n_estimators=500)) | —          | —                          | 0.0 ± 0.0            | 99.8 ± 0.3                | 0.1 ± 0.0           |
| D           | referencia DINOv2                  | —          | —                          | 0.0 ± 0.1            | 93.1 ± 2.7                | 0.0 ± 0.0           |

La columna de latencia mide solo la decisión con las características ya extraídas, en lote. De punta a punta (imagen a decisión), una imagen suelta tarda ≈ 28 ms en CPU a través del servicio; en lotes de 64, ≈ 2 ms por imagen.

## Sector ciego: mitigación con 2a captura (protocolo B)
Girar el objeto 180° (o 2a cámara) y re-estimar: ángulo dentro de ±10° en
97.4 % de los casos; el robot actúa en 93.9 % con
0.72 % de acciones inseguras.

## Limitaciones conocidas
- El objetivo de riesgo angular (≤ 0,5 % de ACT fuera de ±10°) se cumple en validación interna pero en la
  prueba de A se observa 0.8 %: la validación interna duplica el espaciado entre vistas y no
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
Artefacto `linevision-4e39f878-rf.joblib` con manifiesto (sha256, versión de datos, huella de configuración) y
registro en MLflow Model Registry. Notebook `notebooks/01_reto2_experimentacion.ipynb` reproduce todo de punta a
punta con semillas fijas.
