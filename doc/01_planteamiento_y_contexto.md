# 1. Planteamiento y contexto

## 1.1 La prueba

| Dimensión | Condición (enunciado) |
|---|---|
| Cargo | AI Engineer |
| Nivel | Senior+: autonomía total, trade-offs cuantificados, defender un proyecto ante negocio y operación |
| Modalidad | Take-home + defensa técnica en vivo |
| Tiempo | 48 horas desde el envío |
| Tecnología | Libre; se permite IA generativa y herramientas de productividad |
| Dataset | COIL-100 (Columbia Object Image Library) |
| Resultado esperado | Repositorio reproducible + notebook de experimentación + servicio desplegado + asistente agéntico + plan de proyecto + defensa |

Lo que se evalúa, según la propia ficha: si el candidato puede **liderar de punta a punta** la sustitución de una
tarea manual crítica por un sistema de IA **medible y seguro**: criterio técnico, rigor experimental, decisiones
defendibles y capacidad de dirigir un equipo pequeño. La nota no sale de "acertar mucho" sino de demostrar
seguridad, trazabilidad y criterio.

## 1.2 Contexto de negocio

Una empresa de consumo masivo empaca en una línea semiautomática. Hoy un operario recibe cada objeto, identifica
el producto, lo gira a mano hasta una orientación de referencia y lo deja en posición de agarre; un brazo robótico
lo toma asumiendo que ya está alineado y lo empaca.

| Parámetro operativo | Valor |
|---|---|
| Jornada | 24 h/día, 5 días/semana |
| Turnos | 3 de 8 h |
| Personas en la tarea | 1 operario por turno por estación |
| Tarea a sustituir | Identificar el objeto y estimar el ángulo |
| Actor que se conserva | Brazo robótico de pick & pack |

Objetivo: una cámara captura el objeto tal como llega, la IA identifica el producto y su ángulo, y envía esa
información al robot, que compensa la rotación en el agarre. Además, supervisores, calidad y mantenimiento deben
interactuar con el sistema mediante un **asistente conversacional con arquitectura agéntica** (no un formulario ni
un chatbot de preguntas y respuestas).

## 1.3 Problema, propósito y principio de diseño

- **Problema técnico**: dada la imagen de un objeto en orientación arbitraria, decir qué objeto es, en qué ángulo
  está, con qué confianza y si es seguro que el robot actúe. Un error de clase empaca el producto equivocado; un
  error de ángulo produce un agarre fallido, producto dañado o una parada de línea.
- **Propósito de negocio**: mantener o mejorar throughput y calidad sin el operario, con costo total menor y con un
  mecanismo seguro para lo que el modelo no resuelve.
- **Principio de diseño**: no se prescribe arquitectura; el candidato decide qué partes son deterministas, cuáles
  agénticas y dónde se ubica cada una respecto a la línea, justificándolo por latencia, costo y riesgo.

## 1.4 Qué piden los retos

El enunciado incluye los Retos 2, 3, 4 y 6 (faltan 1 y 5; es probable que sea un recorte de una prueba mayor).

| Reto | Qué es | Exigencias clave |
|---|---|---|
| 2 — Visión con ML clásico | Identificar, estimar ángulo [0°, 360°) con incertidumbre, recuperar top-k vistas similares | ≥3 algoritmos de clasificación con esquema de validación; enfoque y métrica de ángulo coherentes; criterio objetivo de casos no confiables; rechazo con confianza válida para decidir; comparación obligatoria con un baseline simple y una referencia moderna (¿justifica la brecha su costo?); traducir la tolerancia ±10° del robot a un criterio de aceptación; notebook reproducible de punta a punta; experimentos trazables (parámetros, métricas, versión de datos, artefactos); model card |
| 3 — Asistente agéntico | Copiloto de la línea para supervisores, calidad, mantenimiento e ingeniería de ML | 7 casos de uso; justificar el patrón y comparar 2 alternativas descartadas; decisiones que nunca toma el LLM; ≥10 tools reales o simuladas con contratos; estado, memoria y aislamiento; ≥8 escenarios adversos (5 obligatorios: fuera de dominio, resultado no confiable, tool o argumentos inválidos, visión con 5xx o timeout, loop agéntico); evaluación reproducible de ≥30 casos |
| 4 — Despliegue | MVP ejecutable | URL pública temporal o despliegue local de un comando; servicio de visión con API propia, independiente del agente; código por responsabilidades y configuración separada; README y `.env.example`; artefacto de modelo versionado; empaquetado reproducible; diagrama de arquitectura y de secuencia de 2 flujos (imagen → robot, y agéntico con aprobación humana) |
| 6 — Cloud y FinOps | Arquitectura en Azure | Servicios concretos con trade-offs, no solo nombres; documento y hoja de costos |

Entregables obligatorios: notebook (.ipynb), reporte por protocolo con análisis de errores y model card (PDF),
repositorio Git con historial razonable, catálogo de tools y contratos, threat model, servicio desplegado (link +
README) y arquitectura Azure con modelo de costos; todo en un único repositorio con un README raíz que indique dónde
está cada entregable.

## 1.5 Huecos del enunciado y supuestos adoptados

| Hueco | Supuesto o decisión |
|---|---|
| Dice "cuatro capacidades" y lista tres | La cuarta, implícita en la sección 3, es **decidir si es seguro que el robot actúe** (control de seguridad) |
| El índice dice "Azure vs AWS"; el cuerpo solo Azure | Azure es lo obligatorio; AWS como tabla comparativa opcional |
| La ficha pide "plan de proyecto"; la tabla de entregables no | Se incluirá: se evalúa liderazgo |
| No dice dónde va el arco de 60° de B ni qué 10 objetos excluye D | Semillas fijas, 3 repeticiones, y un escenario adverso de "gemelos" en el análisis de D |
| No da velocidad de línea, costo del operario ni costo de un error | Supuestos explícitos y parametrizados en la hoja de costos (Reto 6) |
| La tolerancia ±10° es "supuesta" | Se toma como dada y se traduce a un objetivo de riesgo |
| D solo pone objetos desconocidos en prueba | Rechazar todo daría 100 %: la tasa de conocidos rechazados se mide en validación interna |

## 1.6 ¿El LLM usa el modelo en producción? Separación de planos

Duda inicial: ¿conviene empezar por el agente, dado que en producción el LLM usa el modelo? La
respuesta es que el LLM **no está en la línea**:

```
RUTA CRÍTICA (cada objeto, milisegundos, 24×5, sin LLM)
Cámara → API de visión (clase, ángulo, confianza, top-k) → control de seguridad determinista → Robot
                                                            └→ si no es confiable: carril de revisión / 2a captura

PLANO DE SUPERVISIÓN (a demanda de una persona)
Supervisor / calidad / mantenimiento ⇄ Agente (LLM) → tools → API de visión, cola de revisión, métricas, tickets, SOPs
```

- El enunciado dice que el agente "debe usar el modelo del Reto 2 como herramienta, no reimplementarlo dentro de
  un prompt": lo invoca cuando una persona sube una imagen o pregunta por qué se decidió algo.
- Un LLM por objeto añadiría segundos de latencia, costo por pieza y no determinismo en una decisión de seguridad.
- **Consecuencia para el orden de trabajo**: el agente depende del modelo (sus tools envuelven la API de visión y sus
  escenarios adversos necesitan el comportamiento real del modelo). Se decidió empezar por el Reto 2.

## 1.7 Ideas iniciales evaluadas

### YOLO para detectar, medir inclinación y similitud
Idea inicial: detección con YOLO, inclinación con procesamiento adicional (OpenCV), similitud con
embeddings de las últimas capas. Se descartó por tres razones:
1. **No hay nada que detectar**: un objeto por imagen, centrado, recortado y sobre fondo oscuro; localizarlo es un
   umbral. El problema es clasificación + pose.
2. **YOLO (incluido OBB) y OpenCV miden rotación en el plano de la imagen**; el ángulo pedido es un giro sobre el
   eje vertical, fuera del plano. Una caja a 0° y a 180° tiene la misma caja delimitadora.
3. Es un modelo profundo; el enunciado solo lo admite como referencia comparativa.
Lo que se rescató: usar embeddings como **referencia moderna**, mejor con DINOv2 y con el mismo pipeline.

### PCA sobre imágenes aplanadas + clasificador clásico
Idea inicial, tomada como punto de partida. Se adoptó como **baseline** (PCA + 1-NN) y se buscó algo mejor; la
literatura mostró que PCA sobre píxeles es justamente el método fundacional de este dataset (sección 4), y los
experimentos mostraron que como identidad es claramente superado por representaciones de color (sección 6).

### Modelo o render 3D de los objetos
Idea inicial: aprovechar las 72 perspectivas para construir un modelo 3D real y estimar el ángulo por
comparación con su render; alternativamente un "pseudo-3D", porque el objeto nunca se mueve en Z: solo gira en el
plano horizontal. Resultado del análisis (detalle en las secciones 4 y 5):
- La intuición del pseudo-3D es correcta y formalizable: con 1 grado de libertad, todas las apariencias de un objeto
  forman una **curva cerrada** (topológicamente un círculo). Ese lazo es el "modelo 3D" necesario.
- El 3D real (visual hull, NeRF, 3DGS) **no es viable** como núcleo: calibración rota por la normalización de cada
  imagen, geometría que no cumple los supuestos (IoU de siluetas espejadas 0,74), concavidades no recuperables,
  NeRF es una red neuronal, 3DGS depende de CUDA, y costaría 12–20 h de 48. Además, donde el 3D aportaría
  información nueva (el sector ciego) lo correcto es abstenerse.
- Decisión: enfoque de curva; 3D real fuera (como mucho un extra opcional).

### Similitud "por construcción"
Idea inicial: dos imágenes son similares si y solo si son del mismo SKU y tienen ángulos cercanos; así la
similitud sale de los modelos de identidad y de ángulo. Decisión: **adoptada como top-k principal**, más una
evidencia por apariencia independiente de la predicción (sección 7).

## 1.8 Decisiones sobre el proceso

| Decisión | Detalle |
|---|---|
| Trabajo por fases | Primero análisis; después construcción |
| Orden | Modelo (Reto 2) primero; el agente al final |
| LLM del asistente | API de Gemini para la demo (clave temporal, solo en `.env`, nunca en el repositorio); la arquitectura de destino será Azure (Reto 6), con una capa de proveedor intercambiable |
| Commits | Al cerrar el Reto 2, ordenados por tema; después, por hito |
| Notebook | Los 5 bloques (selección con MLflow, evaluación, baseline y referencia, análisis de errores con 2a captura, model card y artefacto) de una vez |
