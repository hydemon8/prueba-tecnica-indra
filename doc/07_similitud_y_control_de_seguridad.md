# 7. Similitud y control de seguridad

## 7.1 Similitud híbrida (capacidad 3: top-k vistas más parecidas)

**Idea inicial**: dos imágenes son similares si y solo si son del mismo SKU y sus ángulos están cerca. Es
más estable y más fácil de entender para un operario, y no contradice el enunciado, que pide "top-k vistas más
parecidas con su información asociada" sin definir la métrica.

**Riesgos que se cubren**:
1. **Circularidad**: si el top-k se deriva de la predicción y la clase está mal, las "evidencias" serán
   coherentemente erróneas. El Reto 3 pide mostrar vistas similares *como evidencia*.
2. **Rechazos**: ante un desconocido o un caso dudoso no hay clase ni ángulo que mostrar.

**Diseño adoptado** (`src/linevision/system.py`):

| Salida | Definición | Para qué sirve |
|---|---|---|
| `topk_pose` | Vistas de referencia del SKU predicho, ordenadas por distancia angular circular al ángulo estimado | Explica la decisión: "esto es lo que creo que ves" |
| `topk_appearance` | Vecinos más cercanos en el espacio de características de identidad, sin usar la predicción | Evidencia independiente; la distancia al primero **es** la puntuación de novedad |

No hacen falta embeddings profundos: los vectores clásicos ya son una representación numérica y la distancia al
vecino más cercano ya se calcula para rechazar desconocidos. Si el vecino 1 en apariencia pertenece a otro SKU, la
decisión pasa a revisión. Esa definición sirve además como verdad de referencia para evaluar la
recuperación (relevante = mismo SKU y |Δθ| ≤ 10°).

Ejemplo real de la salida: para la caja obj1 a 0°, el segundo vecino en apariencia es la propia caja a 180°; es la
evidencia de simetría que el operario debe ver.

## 7.2 Contrato de salida por imagen

```json
{
  "decision": "ACT | ANGLE_UNCERTIFIED | REVIEW | UNKNOWN",
  "reasons": ["texto legible por regla que se activó"],
  "object_id": 1,
  "class_confidence": 0.974,
  "novelty": 0.0,
  "angle_deg": 0.0,
  "angle_credible_width_deg": 2.5,
  "topk_pose": [{"object_id": 1, "angle_deg": 0.0, "delta_deg": 0.0}],
  "topk_appearance": [{"object_id": 1, "angle_deg": 0.0, "distance": 0.0}],
  "model_version": "4e39f878-rf"
}
```

`object_id` y `angle_deg` son nulos cuando la decisión es UNKNOWN.

## 7.3 Reglas del control de seguridad (`src/linevision/gate.py`)

Deterministas, en orden; la primera que se cumple gana. Nunca las decide un LLM.

| # | Decisión | Condición | Qué pasa en la línea |
|---|---|---|---|
| 1 | UNKNOWN | novedad > umbral | Carril de rechazo; no se parece a ningún SKU del catálogo |
| 2 | REVIEW | confianza de clase < umbral, o el vecino 1 en apariencia es de otro SKU | Cola de revisión humana |
| 3 | ANGLE_UNCERTIFIED | SKU con hueco > 30° en su galería, o conjunto creíble > 20°, o ambigüedad > umbral | 2a captura o alineación manual |
| 4 | ACT | ninguna de las anteriores | El robot recibe clase y ángulo |

## 7.4 Calibración (`src/linevision/experiment.py`)

| Umbral | Cómo se fija | Datos |
|---|---|---|
| Novedad | Cuantil 0,99 de la novedad de conocidos en validación | Particiones internas que imitan el protocolo |
| Confianza de clase | El menor umbral tal que el error de clase entre los aceptados sea ≤ 0,5 % | Ídem |
| Temperatura de la incertidumbre | La menor escala cuya cobertura del 90 % se cumple | Particiones del régimen con cobertura (v2) |
| Ancho máximo del conjunto creíble | 20° = 2 × tolerancia (fijo) | Traducción geométrica de ±10° |
| Ambigüedad máxima (v2) | El mayor umbral tal que, entre los casos con ancho ≤ 20°, la fracción con error > 10° sea ≤ 0,5 % | Particiones del régimen con cobertura |
| Hueco máximo de galería | 30° (fijo, política de catálogo) | — |

**Criterio de aceptación** (traducción de la tolerancia del robot ±10°): el robot solo actúa si la clase es
confiable y coincide con la evidencia, el SKU tiene cobertura certificada, el conjunto creíble del 90 % cabe en ±10°
y la ambigüedad está bajo el umbral calibrado para que **≥ 99,5 % de los casos ACT queden dentro de ±10°**.

## 7.5 De v1 a v2: por qué se añadió la ambigüedad

En la v1 el control usaba solo "conjunto creíble ≤ 20°". La primera evaluación dio **1,0 % de acciones inseguras en
A**. Se comprobó que el problema **ya era visible en validación interna**, sin usar la prueba:

| Validación interna | Errores > 10° | Entre los que pasan "ancho ≤ 20°" | Pasan | AUROC ancho | AUROC ambigüedad |
|---|---|---|---|---|---|
| A (A_in) | 3,64 % | **1,05 %** | 71,7 % | 0,833 | **0,945** |
| B (alternancia de vistas) | 2,63 % | 0,89 % | 88,3 % | 0,847 | **0,981** |

Efecto de añadir un tope de ambigüedad (A interno): ≤ 0,9 → pasan 70,8 %, error 0,51 %; ≤ 0,8 → 69,9 %, 0,36 %;
≤ 0,7 → 68,6 %, 0,20 %; ≤ 0,6 → 65,8 %, 0,13 %. Objetos cuyos errores pasaban el control en A: 11 (5), 67 (5),
84 (4), 63 (2), 81 (2), 1, 10, 12. En B: 11 (10), 70 (7), 83, 82 (4), 18, 45, 99 (3), 100 (2).

Segundo cambio de la v2: en B, la temperatura se calibraba dentro de sectores ciegos y los conjuntos creíbles salían
anchísimos en todas partes (escala 10–12,6), lo que dejaba la 2a captura actuando solo en el 6–9 % de los casos.
Ahora la incertidumbre se calibra en el régimen con cobertura (escala 0,04–0,05) y el sector ciego queda gobernado
por la regla de cobertura.

## 7.6 Umbrales calibrados

Validación interna de la evaluación final (v2):

| Protocolo | Clase interna | Ángulo interno ±10° | Escala T | Cobertura 90 % | Ambigüedad máx. | Pasan control de ángulo | Error entre los que pasan | Confianza mín. | Novedad máx. | AUROC novedad (D) | Desconocidos aceptados (D) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 99,75 % | 96,36 % | 0,0398 | 90,64 % | 0,891 | 70,69 % | 0,47 % | 0,198 | 0,248 | — | — |
| B rep0 | 98,67 % | 97,37 % | 0,0398 | 90,65 % | 0,778 | 87,65 % | 0,49 % | 0,392 | 0,362 | — | — |
| B rep1 | 98,03 % | 97,53 % | 0,0501 | 91,22 % | 0,748 | 86,40 % | 0,48 % | 0,482 | 0,385 | — | — |
| B rep2 | 97,28 % | 97,42 % | 0,0501 | 91,42 % | 0,785 | 86,25 % | 0,48 % | 0,544 | 0,363 | — | — |
| C | 98,50 % | 51,58 % | 0,2509 | 90,33 % | **0,000** | **0 %** | — | 0,226 | 0,410 | — | — |
| D rep0 | 99,93 % | 97,22 % | 0,0398 | 90,88 % | 0,775 | 86,68 % | 0,50 % | 0,298 | 0,183 | 0,9976 | 1,02 % |
| D rep1 | 99,91 % | 97,55 % | 0,0398 | 91,08 % | 0,786 | 87,08 % | 0,50 % | 0,306 | 0,184 | 0,9925 | 2,50 % |
| D rep2 | 99,97 % | 97,38 % | 0,0398 | 91,11 % | 0,770 | 87,48 % | 0,49 % | 0,282 | 0,187 | 0,9723 | 4,49 % |

En C, ningún umbral de ambigüedad cumple el objetivo con huecos internos de 60° (la precisión angular interna es
51,6 %), así que el umbral queda en 0 y el sistema **no se auto-certifica**.

Sistema de producción (100 objetos, 72 vistas, calibrado con particiones tipo D): novedad máx. 0,185; confianza
mín. 0,334; ambigüedad máx. 0,769; ancho máx. 20°; hueco máx. 30°.
