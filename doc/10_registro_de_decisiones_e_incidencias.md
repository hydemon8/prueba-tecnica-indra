# 10. Registro de decisiones e incidencias

## 10.1 Cronología (2026-10-09, horas aproximadas)

| Hora | Fase | Qué se hizo |
|---|---|---|
| ~19:25 | Inicio | Se recibe el enunciado (PDF) y el dataset |
| ~19:30–20:00 | Fase 1: análisis | Lectura completa del enunciado; caracterización del dataset; baselines triviales; resumen de planteamiento |
| ~20:00–20:45 | Fase 2: modelo y ángulo | Discusión de YOLO, PCA y 3D; búsqueda bibliográfica; cribado de clasificadores, métodos de ángulo, señales de rechazo, siluetas espejadas, pseudo-render, rechazo de desconocidos |
| ~20:45–21:15 | Fase 2b: aclaraciones | Estructura de comparaciones; historia del plato 1995–2026; experimentos del sector ciego (Fourier, espejo, reglas de cobertura, 2a captura); similitud |
| ~21:15–21:40 | Fase 2c | Explicación de los protocolos; decisión de empezar a construir |
| ~21:45–22:10 | Construcción | Repositorio, entorno `uv`, configuración, librería `linevision`, tests, calibración interna de los 4 protocolos |
| ~22:13–22:27 | Notebook v1 | Ejecución completa; selección en 204 s; resultados v1 |
| ~22:30–22:51 | v2 | Diagnóstico en validación interna; control con ambigüedad y calibración en régimen con cobertura; ejecución v2 |
| ~22:53–23:13 | Ejecución final | Re-ejecución determinista con conclusiones (coincidió con una ejecución paralela del usuario) |
| ~23:20–23:35 | Pruebas funcionales | Casos individuales y robustez sistemática sobre el artefacto final |
| ~23:40 | Documentación | Carpeta `doc/` (creada como `dac/` y renombrada) |

## 10.2 Decisiones

| # | Decisión | Alternativas consideradas | Motivo | Quién |
|---|---|---|---|---|
| 1 | Fase de análisis antes de construir | Empezar a codificar | Petición explícita | Usuario |
| 2 | El LLM no va en la ruta crítica | LLM por objeto | Latencia, costo y no determinismo en una decisión de seguridad; el enunciado pide usar el modelo como tool | Análisis, aceptado |
| 3 | Empezar por el Reto 2 | Empezar por el agente | El agente depende del modelo y de su comportamiento real | Propuesta, aceptada |
| 4 | Gemini como LLM de la demo, detrás de una capa de proveedor | Azure OpenAI, Claude | Sin presupuesto; Azure queda para la arquitectura objetivo | Usuario |
| 5 | Descartar YOLO | YOLO / YOLO-OBB + OpenCV | Nada que detectar; mide rotación en el plano; es profundo | Análisis, aceptado |
| 6 | PCA + 1-NN como baseline | — | Propuesta del usuario; es el método fundacional del dataset | Usuario |
| 7 | Lazo en espacio PCA (Murase & Nayar) para el ángulo | 3D real, Fourier, 1-NN | Mejor en validación interna; formaliza el pseudo-3D | Análisis, aprobado |
| 8 | 3D real fuera (como mucho extra opcional) | Visual hull, NeRF, 3DGS | Calibración rota, IoU 0,74, costo 12–20 h, no aporta donde importa | Usuario |
| 9 | Similitud híbrida | Solo apariencia; solo clase + ángulo | Estabilidad (usuario) + evidencia independiente | Usuario + propuesta |
| 10 | Sector ciego: certificación de cobertura + 2a captura | Estimar con una imagen y actuar | Ninguna regla con una imagen evita 20–40 % de acciones inseguras; la 2a captura da 98 % | Análisis |
| 11 | Criterio de selección pre-registrado | Elegir al ver resultados | Rigor; evita elegir a conveniencia | Análisis |
| 12 | `SoftmaxSVC` en lugar de calibración de Platt con validación cruzada | `CalibratedClassifierCV`, `SVC(probability=True)` | Los pliegues ordenados eran sectores ciegos y cambiaban el argmax | Construcción |
| 13 | PCA antes de estandarizar | Estandarizar antes | Mejor exactitud interna | Construcción |
| 14 | Commits después | Commit por hito | Decisión del usuario | Usuario |
| 15 | Ganador HSV + RF, aunque se esperaba HSV+HOG+LBP | Cambiar a la combinación | Respetar el criterio pre-registrado | Criterio |
| 16 | Iteración v2 del control de seguridad | Dejar v1 y documentar | El problema era visible en validación interna; se corrige calibrando solo ahí y se documenta | Análisis |
| 17 | Re-ejecutar el notebook para que salidas y código coincidan | Editar la celda sin ejecutar | Reproducibilidad | Análisis |
| 18 | Documentar todo en `doc/` | — | Petición del usuario | Usuario |

## 10.3 Incidencias y errores propios

| # | Qué pasó | Impacto | Cómo se resolvió |
|---|---|---|---|
| 1 | El cribado de clasificadores tardaba > 20 min (regresión logística sobre 1.764 dimensiones de HOG) | Tiempo | Se redujo con PCA(150) ajustada en entrenamiento y se paralelizó por partición |
| 2 | El script de desconocidos reventaba la memoria (difusión 1.600 × 1.440 × 1.764) | Tiempo | Distancias por producto escalar |
| 3 | El paquete no se instalaba en modo editable (se creó después del primer `uv sync`) | Tests no importaban | `uv sync --reinstall-package linevision` |
| 4 | Caso borde 0/0 en la ambigüedad cuando la consulta cae sobre el lazo | Detectado por un test | Regularización con ε relativo a la escala natural |
| 5 | `CalibratedClassifierCV` bajó la exactitud interna de C a 75,7 % | Detectado en la prueba de humo | `SoftmaxSVC` (decisión 12) |
| 6 | La temperatura quedó en el límite inferior de su rejilla | Calibración sesgada | Rejilla ampliada a 10⁻³–50 |
| 7 | MLflow guardaba artefactos relativos al directorio de trabajo (el notebook corre en `notebooks/`) | Artefactos dispersos | Ubicación de artefactos fijada en la raíz del repo |
| 8 | En v1, 1,0 % de acciones inseguras en A y 2a captura que casi no actuaba | Seguridad | Iteración v2 (sección 7.5) |
| 9 | Al borrar corridas v2 duplicadas, la comparación de versiones del registro (texto frente a número en MLflow 3) borró también la versión 1 registrada | Se perdió la entrada del registro del modelo v1 (descartado); sus corridas, métricas y `results_v1.json` se conservan | Documentado; el registro actual tiene la versión 3 (modelo v2) |
| 10 | Se lanzó la ejecución final en segundo plano mientras el usuario ejecutaba el mismo notebook en su editor | CPU compartida (selección en 812 s en lugar de 204 s); 37 corridas duplicadas en MLflow; el editor mostraba su ejecución interrumpida | El usuario detuvo la suya; se borraron las 37 corridas; se le indicó revertir el archivo sin guardar. Lección: no ejecutar el notebook en segundo plano si el usuario lo tiene abierto |
| 11 | Los baselines de la fase 1 se midieron sobre las particiones de los protocolos | Ninguno en la selección: modelos fijos, solo diagnóstico | Transparencia: declarado en la sección 2.4; toda selección y calibración posterior usó validación interna |

## 10.4 Pendientes

| Pendiente | Estado |
|---|---|
| Decisión sobre la iteración v3 de robustez (sección 9.4) | Esperando al usuario |
| Reporte PDF por protocolo, análisis de errores y model card (entregable 3) | El contenido existe en `reports/model_card.md` y en este documento |
| Commits con historial razonable | El usuario los pidió para más adelante |
| ¿Artefacto de 34,6 MB en git, Git LFS, o regenerarlo desde el notebook y el registro de MLflow? | Por decidir |
| Reto 4: servicio de visión con API, despliegue de un comando, diagramas | No iniciado |
| Reto 3: asistente agéntico, ≥10 tools, catálogo, threat model, ≥8 escenarios adversos, evaluación de ≥30 casos | No iniciado |
| Reto 6: arquitectura Azure y hoja de costos | No iniciado |
| Plan de proyecto (equipo pequeño, fases, piloto, despliegue, riesgos) | No iniciado |
| Mejoras priorizadas del modelo: umbral con cota superior de confianza; política de simetría por SKU y pinza; alta de SKU con densidad de vistas; recalibración con datos de planta | Documentadas |
