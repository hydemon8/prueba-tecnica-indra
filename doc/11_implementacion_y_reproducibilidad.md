# 11. Implementación y reproducibilidad

## 11.1 Estructura del repositorio

```
configs/
  protocols.yaml     protocolos A–D, semillas y repeticiones
  model.yaml         características, candidatos, criterio de selección pre-registrado, plato, umbrales y
                     objetivos del control de seguridad, 2a captura, referencia moderna
src/linevision/
  config.py          rutas y carga de configuración (COIL_DIR, LINEVISION_ROOT)
  data.py            carga de COIL-100 con validación de integridad y huella de versión
  protocols.py       protocolos A–D, particiones internas (inner_splits) y de cobertura (covered_splits)
  features.py        raw, hsv, hog, lbp; caché en disco por versión de datos y configuración
  identity.py        clasificadores (1-NN, LogReg, SoftmaxSVC, RF), galería y vecinos más cercanos
  pose.py            modelo del plato: lazo, perfil, temperatura, conjunto creíble, ambigüedad, simetría
  gate.py            control de seguridad determinista y calibración de umbrales
  system.py          sistema completo y contrato de salida por imagen
  experiment.py      calibración, evaluación, baseline, 2a captura y sistema de producción
  selection.py       AURC, matriz de candidatos, restricción de novedad, criterio, comparación de pose
  reference.py       embeddings DINOv2 (solo comparación)
  tracking.py        MLflow: experimento, etiquetas, métricas, JSON
  registry.py        exportación del artefacto con manifiesto y registro pyfunc en MLflow
  report.py          tablas por protocolo y model card generada desde los resultados
  analysis.py        montajes, pares confundidos, error por objeto, riesgo-cobertura
tests/               25 tests unitarios, sin dependencia del dataset
notebooks/           01_reto2_experimentacion.ipynb (38 celdas)
reports/             model_card.md, results.json (v2), results_v1.json
artifacts/           linevision-4e39f878-rf.joblib + manifest.json
doc/                 esta documentación
```

## 11.2 Entorno

| Componente | Versión |
|---|---|
| Python | 3.12.13 (gestionado con `uv`, `uv.lock` versionado) |
| scikit-learn | 1.9.1 |
| scikit-image | 0.26.0 |
| scipy | 1.18.1 |
| MLflow | 3.17.0 (backend sqlite `mlflow.db`, artefactos en `mlruns/`) |
| torch / transformers (extra `reference`) | 2.14.1 / 5.19.0 (MPS disponible) |

## 11.3 Cómo reproducir

```bash
cp .env.example .env                      # COIL_DIR si el dataset no está en ./coil-100
uv sync --extra notebook --extra dev --extra reference
uv run pytest                             # 25 tests
uv run jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=-1 \
    notebooks/01_reto2_experimentacion.ipynb
uv run mlflow ui --backend-store-uri sqlite:///mlflow.db
```

Tiempos medidos con la CPU libre: selección ~3,5 min, evaluación final ~4,5 min, notebook completo ~15–20 min.
Las características se cachean en `.cache/` por versión de datos y configuración; los embeddings DINOv2, también.

## 11.4 Trazabilidad

- **Datos**: huella `4e39f8783785bc2d`, registrada como etiqueta en cada corrida de MLflow.
- **Experimentos**: experimento `reto2-coil100`; 46 corridas `iteracion=v1` y 46 `iteracion=v2` activas (1 corrida
  padre de selección + 35 candidatos + 8 evaluaciones finales + comparación + producción). Cada corrida registra
  parámetros, métricas de validación interna y de prueba, y JSON de resultados.
- **Artefacto**: `artifacts/linevision-4e39f878-rf.joblib` (34,6 MB), sha256 `6cf13c982c20411c…`, con manifiesto
  (versión de datos, huella de configuración, temperatura, métricas internas, latencia). Registrado en el Model
  Registry de MLflow como `linevision` (modelo pyfunc que recibe PNG en base64).
- **Determinismo**: dos ejecuciones independientes del notebook produjeron el artefacto con **el mismo sha256** y
  las mismas tablas.
- **Generación del notebook**: `doc/scripts_analisis/generar_notebook.py` construye el `.ipynb` celda a celda.

## 11.5 Pruebas automáticas

| Grupo | Qué garantiza |
|---|---|
| Métricas | Error circular con vuelta de 360°, error consciente de simetría (orden 1, 2 e invariante), acciones inseguras solo cuentan cuando se actúa |
| Protocolos | Tamaños exactos y disjuntos; arco de B contiguo de 60°; ninguna partición interna ni de cobertura toca la prueba; desconocidos internos de D disjuntos de los de prueba |
| Plato | Recupera ángulos no vistos en datos sintéticos (mediana < 2°); detecta la ambigüedad de un objeto simétrico |
| Control de seguridad | Orden de las reglas, motivos legibles, umbral de confianza y de ambigüedad que cumplen su objetivo |
| Selección y reportes | AURC premia la confianza que ordena bien los errores; criterio con restricción, peor caso y desempate por latencia; tablas con media ± desviación |
