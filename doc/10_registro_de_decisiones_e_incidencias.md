# 10. Registro de decisiones e incidencias

## 10.1 Cronología (horas aproximadas)

**Viernes 2026-10-09**

| Hora | Fase | Qué se hizo |
|---|---|---|
| ~19:25 | Inicio | Recepción del enunciado (PDF) y del dataset |
| ~19:30–20:00 | Fase 1: análisis | Lectura completa del enunciado; caracterización del dataset; baselines triviales; planteamiento |
| ~20:00–20:45 | Fase 2: modelo y ángulo | Evaluación de YOLO, PCA y 3D; búsqueda bibliográfica; cribado de clasificadores, métodos de ángulo, señales de rechazo, siluetas espejadas, pseudo-render, rechazo de desconocidos |
| ~20:45–21:15 | Fase 2b | Estructura de comparaciones; historia del plato 1995–2026; experimentos del sector ciego (Fourier, espejo, reglas de cobertura, 2a captura); similitud |
| ~21:15–21:40 | Fase 2c | Repaso de los protocolos; decisión de empezar a construir |
| ~21:45–22:10 | Construcción | Repositorio, entorno `uv`, configuración, librería `linevision`, tests, calibración interna de los 4 protocolos |
| ~22:13–22:27 | Notebook v1 | Ejecución completa; selección en 204 s; resultados v1 |
| ~22:30–22:51 | v2 | Diagnóstico en validación interna; control con ambigüedad y calibración en régimen con cobertura; ejecución v2 |
| ~22:53–23:13 | Ejecución final | Re-ejecución determinista con conclusiones (coincidió con otra ejecución del mismo notebook; incidencia 10) |
| ~23:20–23:35 | Pruebas funcionales | Casos individuales y robustez sistemática sobre el artefacto final |
| ~23:40 | Documentación | Carpeta `doc/` |

**Sábado 2026-10-10**

| Hora | Fase | Qué se hizo |
|---|---|---|
| ~12:30 | Historial | Commits del Reto 2 ordenados por tema |
| ~12:40–13:15 | Reto 4 | Servicio de visión con API propia, pruebas, Dockerfile y compose, diagramas |
| ~13:15–14:15 | Reto 3 | Planta simulada, procedimientos, 22 tools, capa de política, bucle del agente, API e interfaz, evaluación de 45 casos |
| ~14:15–17:00 | Evaluación del agente | Corridas repetidas por caso; ajustes del prompt a partir de los fallos reales |
| ~17:30 | Alerta de captura | Monitor por línea ante una subida brusca de desconocidos |
| ~19:15 | Contenedores | Despliegue con Docker probado de punta a punta |
| ~19:45 | Reto 6 | Arquitectura en Azure y modelo de costos |
| ~19:55–20:30 | Cierre | Plan de proyecto, PDF del entregable 3, revisión de la documentación |

## 10.2 Decisiones

| # | Decisión | Alternativas consideradas | Motivo |
|---|---|---|---|
| 1 | Fase de análisis antes de construir | Empezar a codificar | Entender el problema antes de comprometer un diseño |
| 2 | El LLM no va en la ruta crítica | LLM por objeto | Latencia, costo y no determinismo en una decisión de seguridad; el enunciado pide usar el modelo como tool |
| 3 | Empezar por el Reto 2 | Empezar por el agente | El agente depende del modelo y de su comportamiento real |
| 4 | Gemini como LLM de la demo, detrás de una capa de proveedor | Azure OpenAI, Claude | Sin presupuesto; Azure queda para la arquitectura objetivo |
| 5 | Descartar YOLO | YOLO / YOLO-OBB + OpenCV | Nada que detectar; mide rotación en el plano; es profundo |
| 6 | PCA + 1-NN como baseline | — | Es el método fundacional del dataset |
| 7 | Lazo en espacio PCA (Murase & Nayar) para el ángulo | 3D real, Fourier, 1-NN | Mejor en validación interna; formaliza el pseudo-3D |
| 8 | 3D real fuera (como mucho extra opcional) | Visual hull, NeRF, 3DGS | Calibración rota, IoU 0,74, costo 12–20 h, no aporta donde importa |
| 9 | Similitud híbrida | Solo apariencia; solo clase + ángulo | Estabilidad de la definición por clase y ángulo, más una evidencia independiente de la predicción |
| 10 | Sector ciego: certificación de cobertura + 2a captura | Estimar con una imagen y actuar | Ninguna regla con una imagen evita 20–40 % de acciones inseguras; la 2a captura da 98 % |
| 11 | Criterio de selección pre-registrado | Elegir al ver resultados | Rigor; evita elegir a conveniencia |
| 12 | `SoftmaxSVC` en lugar de calibración de Platt con validación cruzada | `CalibratedClassifierCV`, `SVC(probability=True)` | Los pliegues ordenados eran sectores ciegos y cambiaban el argmax |
| 13 | PCA antes de estandarizar | Estandarizar antes | Mejor exactitud interna |
| 14 | Commits al cerrar el Reto 2, ordenados por tema | Commit por hito durante la construcción | Se priorizó avanzar; a partir del Reto 4 los commits se hicieron por hito |
| 15 | Ganador HSV + RF, aunque se esperaba HSV+HOG+LBP | Cambiar a la combinación | Respetar el criterio pre-registrado |
| 16 | Iteración v2 del control de seguridad | Dejar v1 y documentar | El problema era visible en validación interna; se corrige calibrando solo ahí y se documenta |
| 17 | Re-ejecutar el notebook para que salidas y código coincidan | Editar la celda sin ejecutar | Reproducibilidad |
| 18 | Documentar el proceso en `doc/` | Solo el README | Dejar trazables las decisiones, también las descartadas |
| 19 | Reto 4 antes que el Reto 3 | Agente primero | Las tools del agente envuelven la API de visión |
| 20 | Despliegue local de un comando | URL pública temporal | El enunciado admite las dos opciones; los alojamientos gratuitos con contenedores ya no lo son |
| 21 | No implementar las correcciones de robustez (v3) | Implementarlas dentro del plazo | Tiempo; quedan diagnosticadas (sección 9.4) y son la fase 1 del plan de proyecto |
| 22 | Artefacto del modelo (34,6 MB) versionado en git | Git LFS; regenerarlo desde el notebook | Permite levantar el servicio sin ejecutar el notebook; el manifiesto fija su sha256 |

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
| 10 | La ejecución final del notebook se lanzó en segundo plano mientras el mismo notebook estaba ejecutándose en el editor | CPU compartida (selección en 812 s en lugar de 204 s); 37 corridas duplicadas en MLflow | Se detuvo una de las dos y se borraron las 37 corridas. Lección: una sola ejecución del notebook a la vez |
| 11 | Los baselines de la fase 1 se midieron sobre las particiones de los protocolos | Ninguno en la selección: modelos fijos, solo diagnóstico | Transparencia: declarado en la sección 2.4; toda selección y calibración posterior usó validación interna |
| 12 | La primera evaluación del agente se contaminó con errores 429 del proveedor de LLM (15 peticiones por minuto) | Casos fallidos por cuota, no por el agente | Control de ritmo, reintento tras la espera indicada y anulación de las corridas afectadas; el reporte cuenta solo ejecuciones válidas |
| 13 | La latencia documentada (1,5–1,7 ms) era por imagen en lote, no por petición | Cifra optimista para una línea que procesa un objeto a la vez | Medida en el servicio: ≈ 28 ms por imagen suelta (sección 12); corregido en los documentos 6 y 8 y en la model card |

## 10.4 Pendientes

| Pendiente | Estado |
|---|---|
| Correcciones de robustez v3 (sección 9.4) | Diagnosticadas, no implementadas |
| Umbral del control con cota superior de confianza del error | Documentado (sección 8.2) |
| Política de simetría por SKU y pinza; alta de SKU con densidad mínima de vistas | Documentado |
| Recalibración con imágenes de planta | Fase 1 del plan de proyecto (documento 17) |
| Conectar la alerta de captura con el asistente | No iniciado |
| Proveedor de Azure OpenAI para el asistente | Diseñado (documento 16), no implementado |
