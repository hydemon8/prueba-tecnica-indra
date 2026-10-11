# Documentación de análisis y construcción

Registro completo del trabajo sobre la prueba técnica *Ingeniero IA* de Indra: planteamiento, análisis del
dataset, protocolos, estado del arte del "modelo del plato" (1995–2026), el ML estadístico, resultados,
pruebas funcionales y todas las decisiones tomadas, incluidas las descartadas y las incidencias. Nada de
esto sustituye a los entregables formales (notebook, reporte, model card); es la memoria técnica de la que
salen y el material de preparación para la defensa.

Estado a 2026-10-09 (≈23:45): **Reto 2 construido y evaluado (iteración v2)**. Pendientes: decisión sobre la
iteración v3 de robustez, reporte PDF, commits, Retos 3, 4 y 6, plan de proyecto.

## Orden de lectura

| # | Documento | Qué contiene |
|---|---|---|
| 1 | [Planteamiento y contexto](01_planteamiento_y_contexto.md) | La prueba, el negocio, qué piden los retos, huecos del enunciado, rol del LLM, ideas iniciales evaluadas (YOLO, PCA, 3D) |
| 2 | [Dataset y análisis exploratorio](02_dataset_y_analisis_exploratorio.md) | COIL-100 caracterizado con números, propiedades que condicionan el diseño, brecha con planta, baselines triviales |
| 3 | [Protocolos y validación](03_protocolos_y_validacion.md) | Qué es cada protocolo A–D, qué estresa, cómo se resuelve, validación interna sin fugas |
| 4 | [Estado del arte del plato, 1995–2026](04_estado_del_arte_plato_1995_2026.md) | Línea histórica del reconocimiento y la pose por vistas sobre plato giratorio y qué probamos de cada época |
| 5 | [Modelo del plato](05_modelo_del_plato.md) | El método elegido (curva cerrada en espacio PCA), incertidumbre, simetría, sector ciego, 2a captura, 3D descartado |
| 6 | [ML estadístico: identidad](06_ml_estadistico_identidad.md) | Características, clasificadores, cribado, selección pre-registrada de 35 candidatos, baseline y referencia DINOv2 |
| 7 | [Similitud y control de seguridad](07_similitud_y_control_de_seguridad.md) | Similitud híbrida, reglas del control, calibración, traducción de la tolerancia ±10° |
| 8 | [Resultados](08_resultados.md) | Todas las tablas: validación interna, prueba por protocolo (v1 y v2), comparación, 2a captura, análisis de errores |
| 9 | [Pruebas funcionales y robustez](09_pruebas_funcionales_y_robustez.md) | El artefacto final ante capturas perturbadas y fuera de dominio; fallos encontrados; propuesta v3 |
| 10 | [Registro de decisiones e incidencias](10_registro_de_decisiones_e_incidencias.md) | Cronología, decisiones del usuario y técnicas, errores cometidos y cómo se corrigieron, pendientes |
| 11 | [Implementación y reproducibilidad](11_implementacion_y_reproducibilidad.md) | Estructura del código, cómo ejecutar, MLflow, artefacto, tests |
| 12 | [Servicio de visión](12_servicio_de_vision.md) | Reto 4: API, qué recibe el robot, validación de captura, controles, latencia medida, arquitectura y secuencia imagen → robot |
| 13 | [Catálogo de tools](13_catalogo_de_tools.md) | Reto 3: las 22 tools con contrato, permisos, errores, repeticiones y auditoría (generado desde el código) |
| 14 | [Asistente agéntico](14_asistente_agentico.md) | Reto 3: patrón y alternativas, límites, memoria, aislamiento, flujo con aprobación humana, escenarios adversos y evaluación |
| 15 | [Threat model](15_threat_model.md) | Reto 3: activos, fronteras de confianza, amenazas y controles con su evidencia, riesgo residual |
| 16 | [Arquitectura Azure y FinOps](16_arquitectura_azure_y_finops.md) | Reto 6: qué va en la planta y qué en la nube, servicios con sus alternativas, modelo de costos con precios reales, caso de negocio y palancas |
| 17 | [Plan de proyecto](17_plan_de_proyecto.md) | Criterios de éxito, equipo, fases con puertas de salida, riesgos, personas y presupuesto |

`img/` contiene las figuras citadas; `scripts_analisis/` los scripts exploratorios que produjeron los números de
las fases de análisis (antes de existir la librería).

## Resumen ejecutivo

- **Problema real**: no es "detectar" (hay un objeto centrado por imagen) sino **identificar el SKU, estimar su
  giro fuera del plano sobre el eje vertical y decidir si el robot puede actuar**. Un error de clase empaca el
  producto equivocado; un error de ángulo rompe el agarre.
- **Clasificar es casi trivial** en este dataset (1-NN sobre píxeles da 99,97 % en A). La dificultad está en el
  ángulo cuando faltan vistas (B, C), en el rechazo calibrado y en la robustez a condiciones de planta.
- **Modelo del plato**: espacio propio paramétrico de Murase & Nayar (1995): las 72 vistas de un objeto forman un
  lazo cerrado en un espacio PCA; el ángulo es el punto más cercano del lazo. Es el "pseudo-3D" correcto para un
  giro de 1 grado de libertad; la reconstrucción 3D real se evaluó y se descartó con datos.
- **Identidad**: histograma HSV + Random Forest, elegido entre 35 candidatos con un criterio pre-registrado. La
  representación pesa mucho más que el clasificador.
- **Control de seguridad determinista** (ACT / ANGLE_UNCERTIFIED / REVIEW / UNKNOWN), calibrado solo en
  validación interna; la tolerancia ±10° se traduce en "≥ 99,5 % de las acciones dentro de ±10°".
- **Resultados en prueba (v2)**: acciones inseguras 0,7 % (A), 0 % (B, C, D) frente a 4,1 % / 72,7 % / 28,3 % /
  100 % del baseline. Sector ciego: con una 2a captura girando 180°, 97,4 % dentro de ±10°.
- **Pruebas funcionales** (después de la v2): el sistema es frágil ante cambios de iluminación y ruido (rechaza
  producto conocido) y actúa con ángulo erróneo si el objeto llega desplazado (10,5 % de acciones inseguras con
  8 px). Hay una propuesta v3 pendiente de aprobación.
