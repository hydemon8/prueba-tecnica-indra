# Scripts de análisis

Scripts exploratorios que produjeron los números de las fases de análisis, antes de existir la librería
`linevision`, más las pruebas funcionales posteriores. Se conservan por trazabilidad; el código de producción está
en `src/linevision/` y el flujo reproducible en el notebook.

| Script | Fase | Qué produce | Documento |
|---|---|---|---|
| `f1_montajes.py` | 1 | Montaje de los 100 objetos y tiras de giro | 2 |
| `f1_eda_y_baselines.py` | 1 | Estadísticas de fondo y primer plano; baselines 1-NN por protocolo; objetos con peor ángulo; confusiones; rechazo de desconocidos | 2 |
| `f1_eda_primer_plano.py` | 1 | Primer plano con umbrales 60 y 80; duplicados; tiras de objetos ambiguos | 2 |
| `f2_caracteristicas.py` | 2 | Banco de características (raw, hsv, hog, lbp, silueta y sus versiones espejadas) | 6 |
| `f2_cribado_clasificadores.py` | 2 | Cribado representación × clasificador en validación interna (uso: `<feats.npz> A_in\|C_in\|B_in`) | 6 |
| `f2_cribado_angulo.py` | 2 | Métodos de ángulo (1-NN, 2-NN, lazo) por espacio; IoU de siluetas espejadas | 5 |
| `f2_pseudo_render_y_rechazo.py` | 2 | Síntesis de vistas desde el lazo; primera heurística de rechazo | 5 |
| `f2_senales_de_rechazo.py` | 2 | AUROC de ambigüedad, distancia mínima y hueco | 5 |
| `f2_desconocidos.py` | 2 | Rechazo de desconocidos por representación, aleatorio y gemelos | 6 |
| `f2b_sector_ciego.py` | 2b | Lazo, Fourier, simetría de espejo, reglas de cobertura y de hueco, 2a captura | 4, 5 |
| `f3_diagnostico_control_v2.py` | v1→v2 | Por qué fallaba el control v1, solo con validación interna | 7 |
| `f4_prueba_funcional_casos.py` | Funcional | 14 casos sobre el artefacto final | 9 |
| `f4_robustez_perturbaciones.py` | Funcional | 200 imágenes × 10 perturbaciones, dos identidades | 9 |
| `generar_notebook.py` | Construcción | Genera `notebooks/01_reto2_experimentacion.ipynb` | 11 |
| `generar_pdf_entregable3.py` | Entrega | Genera `reports/entregable_3_reporte_errores_model_card.pdf` a partir de `reports/results.json`; requiere `reportlab` | 8, 9 |

Los scripts de la fase 1 usaron las particiones de los protocolos con modelos fijos, como diagnóstico (sección 2.4).
Los de las fases 2 y 2b usan solo validación interna. Los `f2*` leen el banco `feats.npz` que genera
`f2_caracteristicas.py`; los `f3*` y `f4*` usan la librería y se ejecutan con el entorno del repositorio
(`uv run python doc/scripts_analisis/<script>.py`). Las rutas de entrada y salida se pasan como argumentos donde
aplica.
