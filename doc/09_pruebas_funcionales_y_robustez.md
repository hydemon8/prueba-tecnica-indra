# 9. Pruebas funcionales y robustez

Hechas **después** de la v2, sobre el artefacto final de producción (`artifacts/linevision-4e39f878-rf.joblib`,
sha256 verificado contra el manifiesto). Ninguna usa la prueba de los protocolos: son imágenes nuevas generadas
perturbando imágenes del catálogo, más imágenes sintéticas fuera de dominio. Scripts:
`scripts_analisis/f4_prueba_funcional_casos.py` y `scripts_analisis/f4_robustez_perturbaciones.py`.

## 9.1 Casos individuales

| Caso | Decisión | Detalle | Valoración |
|---|---|---|---|
| Nominal, obj5 a 40° | ACT | obj5, confianza 0,97, ángulo 40,0° (error 0°) | Correcto |
| Brillo +15 %, obj5 40° | UNKNOWN | novedad 0,361 > 0,185 | Seguro, pero rechaza un producto conocido |
| Brillo −30 %, obj5 40° | UNKNOWN | novedad 0,485 | Ídem |
| Ruido σ=8, obj19 120° | UNKNOWN | novedad 0,222 | Ídem |
| Desenfoque r=1,5, obj82 200° | ACT | ángulo 200,0° (error 0°) | Correcto |
| Desplazado 10 px, obj82 200° | ACT | ángulo 194,5° (error 5,5°) | Correcto, dentro de tolerancia |
| Escala 80 %, obj82 200° | ANGLE_UNCERTIFIED | estimó 149° (error 51°) pero ambigüedad 0,86 > 0,77 | Seguro: el control lo detectó |
| **Volcado (rotado 90° en el plano), obj19 120°** | **ACT** | obj19, novedad 0,000, ángulo 263,5°, ancho 0,5° | **Inseguro**: actúa con un ángulo sin sentido |
| Ocluido al 50 %, obj19 | UNKNOWN | novedad 0,196 | Seguro |
| Otro color (variante del mismo empaque), obj5 | UNKNOWN | novedad 1,001 | Correcto: es otro SKU |
| Ruido puro | UNKNOWN | novedad 1,078 | Correcto |
| Imagen negra | UNKNOWN | novedad 1,348 | Correcto |
| Rosca obj47 a 90° | ANGLE_UNCERTIFIED | ancho 51,5° | Correcto: ángulo inobservable |
| Caja obj65 a 90° (de canto) | ACT | ángulo 90,0° (error 0°) | Correcto |

## 9.2 Robustez sistemática

200 imágenes del catálogo elegidas al azar, cada una con cada perturbación. Se comparan la identidad ganadora y la
segunda del criterio, cada una con el resto del sistema igual y calibrada como en producción. En %.

| Captura | Sistema | ACT | Inseguras | UNKNOWN | REVIEW | Ángulo no cert. | Clase correcta |
|---|---|---|---|---|---|---|---|
| Limpia | HSV + RF (ganador) | 97,0 | 0,0 | 0,0 | 0,0 | 3,0 | 100,0 |
| Limpia | HSV+HOG+LBP + LogReg | 97,0 | 0,0 | 0,0 | 0,0 | 3,0 | 100,0 |
| Brillo +15 % | ganador | 25,5 | 2,0 | 66,0 | 1,5 | 7,0 | 94,0 |
| Brillo +15 % | 2º | 61,5 | 2,0 | 0,5 | 1,0 | 37,0 | 99,5 |
| Brillo −15 % | ganador | 6,0 | 1,0 | 87,0 | 2,0 | 5,0 | 85,0 |
| Brillo −15 % | 2º | 42,0 | 1,5 | 1,5 | 6,0 | 50,5 | 99,0 |
| Brillo −30 % | ganador | 0,0 | 0,0 | 97,5 | 0,0 | 2,5 | 40,5 |
| Brillo −30 % | 2º | 4,0 | 2,5 | 64,5 | 6,0 | 25,5 | 75,5 |
| Ruido σ=4 | ganador | 32,5 | 0,0 | 64,0 | 1,5 | 2,0 | 86,0 |
| Ruido σ=4 | 2º | 26,5 | 0,0 | 73,5 | 0,0 | 0,0 | 100,0 |
| Ruido σ=8 | ganador | 7,5 | 0,0 | 90,5 | 0,0 | 2,0 | 67,0 |
| Ruido σ=8 | 2º | 4,5 | 0,0 | 95,5 | 0,0 | 0,0 | 95,5 |
| Desenfoque r=1 | ganador | 81,0 | 0,0 | 15,0 | 0,5 | 3,5 | 99,0 |
| Desenfoque r=1 | 2º | 97,0 | 0,0 | 0,0 | 0,0 | 3,0 | 100,0 |
| **Desplazado 8 px** | ganador | 44,0 | **10,5** | 0,0 | 0,0 | 56,0 | 100,0 |
| **Desplazado 8 px** | 2º | 42,0 | **9,0** | 7,5 | 0,5 | 50,0 | 100,0 |
| Volcado 90° (fuera de dominio) | ganador | 0,0 | 0,0 | 0,0 | 0,0 | 100,0 | 100,0 |
| Volcado 90° | 2º | 0,0 | 0,0 | 100,0 | 0,0 | 0,0 | 68,5 |
| Volcado 180° | ganador | 1,0 | 1,0 | 0,0 | 0,0 | 99,0 | 100,0 |
| Volcado 180° | 2º | 0,0 | 0,0 | 92,5 | 0,5 | 7,0 | 82,5 |

En los casos fuera de dominio, cualquier ACT cuenta como inseguro.

## 9.3 Diagnóstico

| Fallo | Gravedad | Causa | Solución clásica propuesta |
|---|---|---|---|
| Desplazamiento → ángulo erróneo con confianza (9–10,5 % de acciones inseguras con 8 px) | **Seguridad** | COIL viene centrado y recortado; el plato compara píxeles alineados | Replicar en la entrada la normalización de COIL (segmentar → recortar → reescalar la dimensión mayor → centrar). En planta hace falta igualmente |
| Brillo → ángulo erróneo (1–2,5 % inseguras) | **Seguridad** | Murase & Nayar normalizaban el brillo (norma 1) y la entrada del plato no lo hace | Normalizar el brillo de la entrada del plato |
| Volcado → ACT en algunos casos (1 caso individual; 1 % con 180°) | **Seguridad** | La novedad usa solo el histograma de color, invariante a rotaciones en el plano; nada comprueba que la imagen esté cerca de alguna orientación conocida | Regla de "residuo de pose": distancia de la imagen al lazo de su SKU frente a un umbral calibrado en validación interna → REVIEW |
| Brillo ±15 % o ruido leve → producto conocido rechazado | Disponibilidad (pararía la línea) | Identidad dominada por el color; umbral de novedad calibrado con capturas limpias del mismo laboratorio | Declarar condiciones nominales de captura (brillo ±15 %, ruido σ ≤ 4, desenfoque leve, desplazamiento ≤ 10 px), calibrar la novedad con esas variaciones y añadir un término de robustez al criterio de selección |

La segunda opción (HSV+HOG+LBP) es claramente más robusta a la luz y detecta mejor los volcados como desconocidos,
pero también falla con el desplazamiento: ese problema está en el plato, no en la identidad.

## 9.4 Propuesta v3 (pendiente de aprobación)

1. Normalización de captura al estilo COIL antes de extraer características.
2. Normalización de brillo de la entrada del plato.
3. Regla de residuo de pose en el control de seguridad, calibrada en validación interna.
4. Condiciones nominales de captura declaradas; novedad calibrada con esas variaciones; criterio de selección con
   un término de robustez (previsiblemente ganaría HSV+HOG+LBP, la intuición inicial del usuario).
5. Nueva sección del notebook con las pruebas de robustez y fuera de dominio como demostración funcional; sirve
   también de base para los escenarios adversos del Reto 3.

Se documentaría como las demás iteraciones: motivada por pruebas funcionales, sin usar la prueba de los protocolos.
Costo estimado: ~1 h de trabajo y ~25 min de ejecución. Argumento para hacerlo: en la defensa preguntarán qué pasa
si cambia la luz, y hoy la respuesta honesta es "se para la línea".
