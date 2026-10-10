# Prueba técnica AI Engineer — visión para pick & pack

Identificación de producto, estimación del giro (yaw) y decisión segura para un brazo robótico, con ML
clásico sobre COIL-100. *Documento en construcción: el índice de entregables se completa al cierre.*

## Entregables

| # | Entregable | Ubicación | Estado |
|---|---|---|---|
| 2 | Notebook de experimentación reproducible | [`notebooks/01_reto2_experimentacion.ipynb`](notebooks/01_reto2_experimentacion.ipynb) | listo |
| 3 | Reporte por protocolo, análisis de errores y model card | [`reports/model_card.md`](reports/model_card.md), [`reports/results.json`](reports/results.json) (PDF pendiente) | en curso |
| 5 | Repositorio de código | este repo: `src/linevision` (visión) y `src/lineops` (asistente) | listo |
| 7 | Catálogo de tools y contratos | [`doc/13_catalogo_de_tools.md`](doc/13_catalogo_de_tools.md), [`doc/openapi/tools.json`](doc/openapi/tools.json) | listo |
| 8 | Threat model y controles | [`doc/15_threat_model.md`](doc/15_threat_model.md) | listo |
| 10 | Servicio desplegado | despliegue local de un comando (abajo); visión: [`doc/12_servicio_de_vision.md`](doc/12_servicio_de_vision.md); asistente: [`doc/14_asistente_agentico.md`](doc/14_asistente_agentico.md); URL pública pendiente | en curso |
| 12 | Arquitectura Azure y modelo de costos | `doc/` | pendiente |

## Reto 2 en una página

**Sistema = identidad + modelo del plato + similitud híbrida + control de seguridad determinista.**

- **Identidad**: histograma de color HSV + Random Forest, elegido entre 35 candidatos (5 representaciones ×
  7 configuraciones de kNN / regresión logística / SVM-RBF / Random Forest) con un criterio pre-registrado en
  `configs/model.yaml`. La distancia a la vista de referencia más cercana es la puntuación de "desconocido".
- **Modelo del plato** (Murase & Nayar, 1995): el objeto solo gira sobre el eje vertical, así que sus apariencias
  forman una curva cerrada en un espacio PCA; el ángulo es el punto más cercano de la curva y el perfil de
  distancias da un conjunto creíble del 90 % (incertidumbre) y una medida de ambigüedad (simetrías).
- **Control de seguridad**: ACT / ANGLE_UNCERTIFIED / REVIEW / UNKNOWN con umbrales calibrados solo en validación
  interna. La tolerancia del robot (±10°) se traduce en un objetivo de riesgo: ≥ 99,5 % de las acciones dentro de
  ±10°.

| Protocolo (prueba) | Clase | Ángulo ±10° | El robot actúa | Acciones inseguras | Baseline PCA+1-NN: inseguras |
|---|---|---|---|---|---|
| A — interpolación | 99,9 % | 97,0 % | 87,6 % | 0,7 % | 4,1 % |
| B — sector ciego (3 semillas) | 99,0 % | 55,3 % (1 imagen) / 97,4 % (2a captura) | 0 % (1 imagen) / 93,9 % (2a captura) | 0 % / 0,7 % | 72,7 % |
| C — escasez | 99,6 % | 95,0 % | 0 % (no se auto-certifica) | 0 % | 28,3 % |
| D — desconocido (3 semillas) | 99,8 % rechazados | — | 0 % | 0 % | 100 % |

Detalle, comparación con la referencia moderna (DINOv2) y limitaciones: [`reports/model_card.md`](reports/model_card.md).

## Ejecución local

Requisitos: [uv](https://docs.astral.sh/uv/) y el dataset COIL-100 descomprimido.

```bash
cp .env.example .env          # ajustar COIL_DIR si el dataset no está en ./coil-100
uv sync --extra notebook --extra dev --extra reference
uv run pytest

# notebook de punta a punta (~25 min en un portátil; genera reports/, artifacts/ y registra en MLflow)
uv run jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=-1 \
    notebooks/01_reto2_experimentacion.ipynb

# explorar los experimentos registrados
uv run mlflow ui --backend-store-uri sqlite:///mlflow.db
```

### Sistema completo con un comando (Retos 3 y 4)

```bash
cp .env.example .env                                  # y completar GEMINI_API_KEY
uv run --extra service --extra agent lineops-up       # visión en :8001, asistente e interfaz en http://127.0.0.1:8002
```

Levanta dos procesos independientes: el servicio de visión y el asistente con su interfaz web. La planta es
simulada y se siembra sola en `var/plant.db` (borrar `var/` la reinicia). Evaluación del agente:

```bash
uv run --extra service --extra agent python -m lineops.evals.run --repeats 3    # 45 casos x 3 -> reports/agent_eval.md
```

Diseño, escenarios adversos y diagrama del flujo con aprobación humana:
[`doc/14_asistente_agentico.md`](doc/14_asistente_agentico.md). Resultados: [`reports/agent_eval.md`](reports/agent_eval.md).

### Solo el servicio de visión (Reto 4)

```bash
uv run --extra service linevision-serve      # http://127.0.0.1:8001 (documentación en /docs)
curl -F "images=@coil-100/obj5__40.png" "http://127.0.0.1:8001/v1/predict?top_k=3"
```

Con contenedor: `docker compose up --build`. Detalle, diagramas y latencia: [`doc/12_servicio_de_vision.md`](doc/12_servicio_de_vision.md).

El extra `reference` (torch + transformers) solo hace falta para la referencia moderna DINOv2 de la sección 7.

## Estructura

```
configs/            configuración separada del código (protocolos, modelo, umbrales, criterio de selección)
src/linevision/     librería: datos, protocolos, características, identidad, plato (pose), control de
                    seguridad, sistema, experimentos, selección, referencia, tracking, registro y reportes
  service/          servicio de visión: API HTTP, validación de captura y orden para el robot
src/lineops/        asistente agéntico: tools, capa de política, bucle del agente, memoria, API e interfaz,
                    planta simulada y arnés de evaluación
knowledge/sops/     procedimientos de planta que el asistente consulta con cita
evals/              set de evaluación del agente (45 casos) y sus imágenes
tests/              tests unitarios (sin dependencia del dataset)
notebooks/          experimentación de punta a punta (Reto 2)
reports/            model card y resultados por protocolo (generados por el notebook)
artifacts/          artefacto del modelo + manifiesto (sha256, versión de datos, huella de configuración)
doc/                documentación de análisis y construcción: planteamiento, dataset, protocolos, estado del
                    arte del plato 1995–2026, ML estadístico, resultados, robustez, decisiones e incidencias
```
