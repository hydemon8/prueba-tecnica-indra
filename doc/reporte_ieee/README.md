# Reporte técnico en formato de artículo IEEE

Fuentes del PDF [`reports/reporte_tecnico_ieee.pdf`](../../reports/reporte_tecnico_ieee.pdf): un resumen de toda la
prueba (Retos 2, 3 y 4) con el formato de un artículo técnico de dos columnas.

## Cómo regenerarlo

Desde la raíz del repositorio:

```bash
# 1. Datos de las figuras que no están ya en reports/ ni en doc/ (necesita el dataset y el entorno del proyecto)
uv run python doc/reporte_ieee/calcular_datos.py

# 2. Figuras, texto y PDF (solo biblioteca estándar; imprime con Chrome o Edge)
python doc/reporte_ieee/generar_reporte.py
```

El paso 2 escribe `reporte.html` y lo imprime a PDF con el navegador en modo sin ventana.

## Qué hace cada archivo

| Archivo | Contenido |
|---|---|
| `calcular_datos.py` | Lazos, perfiles de distancia, distribuciones sobre el ángulo y montaje de imágenes; escribe `datos.json` y `montaje_vistas.png` |
| `figuras.py` | Las once figuras, dibujadas como SVG con una sola paleta y una sola tipografía |
| `generar_reporte.py` | Texto, tablas, maquetación y salida a PDF |
| `silabas.py` | División silábica del español, para partir palabras en las columnas justificadas |
| `iconos/` | Diez iconos de [Simple Icons](https://github.com/simple-icons/simple-icons) (licencia CC0) |

## De dónde sale cada cifra

- Resultados por protocolo: `reports/results.json`.
- Los 35 candidatos de identidad: tabla 6.5 de `doc/06_ml_estadistico_identidad.md`.
- Evaluación del asistente: `reports/agent_eval.md`.
- Diagnóstico con vecino más cercano: tabla 2.4 de `doc/02_dataset_y_analisis_exploratorio.md`.
- Lazos y distribuciones: se calculan con la librería `linevision`. Los lazos usan el modelo con las 72 vistas; los
  perfiles y las distribuciones usan un modelo entrenado como en el protocolo A y vistas de su prueba, solo para
  ilustrar el mecanismo. Ningún umbral se ajustó con ellas.

## Sobre el formato

No usa la plantilla oficial `IEEEtran` de LaTeX: reproduce sus convenciones (tamaño carta, dos columnas, Times de
10 puntos, secciones en versalitas con números romanos, pies de figura y títulos de tabla) con HTML y CSS.
