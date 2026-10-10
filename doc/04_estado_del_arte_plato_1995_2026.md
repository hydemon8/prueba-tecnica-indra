# 4. Estado del arte del "plato": reconocimiento y pose por vistas, 1995–2026

Este documento reconstruye cómo ha evolucionado el problema que plantea la prueba (identificar un objeto y
estimar su giro sobre un plato giratorio a partir de vistas de referencia) desde el trabajo que dio origen a COIL
hasta 2026, y qué tomamos, probamos o descartamos de cada época.

**Nota de verificación.** Las referencias marcadas con ✔ se comprobaron durante el análisis (búsqueda web y
lectura de la fuente o de su resumen). Las marcadas con ◐ son de conocimiento general y no se verificaron en esta
sesión; deben comprobarse antes de citarlas en un entregable formal.

## 4.1 La idea que atraviesa toda la línea

En todos los trabajos de esta línea, **el ángulo del plato es el parámetro del modelo**. Las 72 vistas cada 5°
son el muestreo de un círculo. Lo que cambia entre épocas es **cómo se rellena el espacio entre muestras**: con
splines, con series de Fourier, con un círculo latente compartido, con embeddings profundos o reconstruyendo el
objeto en 3D. Ningún método crea información de una cara que nunca se fotografió; los modernos la reconstruyen
en 3D, con requisitos de calibración, GPU y cobertura densa.

## 4.2 Línea temporal

| Año | Trabajo | Idea | Cómo modela el plato | Aporte para nosotros |
|---|---|---|---|---|
| 1993–1995 ✔ | Murase & Nayar, *Visual learning and recognition of 3-D objects from appearance* (IJCV 14:5–24, 1995; versión SPIE 1993) | Espacio propio paramétrico | Curva cerrada en un espacio PCA, parametrizada por el ángulo, interpolada con spline cúbico | **Es nuestro modelo del plato** |
| 1996 ✔ | Nene, Nayar & Murase, COIL-20 (CUCS-005-96) y COIL-100 (CUCS-006-96) | Publicación del dataset | Plato motorizado, pasos de 5°, 72 vistas | El dataset de la prueba |
| 1998 ◐ | Pontil & Verri, *Support vector machines for 3D object recognition* (IEEE TPAMI) | SVM sobre vistas de COIL-100 | No modela la pose | Discriminativo clásico como alternativa |
| 2000–2002 ✔ | Yang, Roth & Ahuja (ECCV 2000); Roth, Yang & Ahuja, *Learning to recognize three-dimensional objects* (Neural Computation 2002) | SNoW frente a SVM y vecino más cercano en COIL-100 | Estudian cuánto cae el reconocimiento con menos vistas | Equivale al protocolo C; SNoW degrada con más gracia que SVM |
| 2000–2008 ◐ | Isomap (Tenenbaum et al., 2000), LLE (Roweis & Saul, 2000), Laplacian Eigenmaps (Belkin & Niyogi, 2003), t-SNE (van der Maaten & Hinton, 2008) | Aprendizaje de variedades no supervisado | COIL-20 se usa como demo: cada objeto aparece como un lazo cerrado | Confirma la topología de círculo sin supervisión |
| 2009 ✔ | Tamaki, Amano & Kaneda, *Representing images of a rotating object with cyclic permutation for view-based pose estimation* (CVIU 113(12):1210–1221) | Grupo cíclico: la imagen siguiente es una matriz G aplicada a la actual; G por diagonalización real por bloques; potencias reales de G | La rotación es periódica; cada píxel es una señal periódica del ángulo (relación con la DFT y la regresión lineal) | Inspiró nuestra prueba de "Fourier global": **empeora** en el sector ciego |
| 2013–2015 ✔ | Zhang, El-Gaaly, Elgammal & Jiang, *Joint object and pose recognition using homeomorphic manifold analysis* (AAAI 2013, 27:1012–1019); extensión *Factorization of view-object manifolds…* (CVIU, arXiv 1503.06813) | Variedades homeomorfas | Todos los objetos son deformaciones del **mismo círculo latente**; se resuelven categoría, instancia y pose a la vez | Comparte estructura entre objetos, pero sigue interpolando |
| 2015 ◐ | Wohlhart & Lepetit, *Learning descriptors for object recognition and 3D pose estimation* (CVPR 2015) | Descriptores con pérdida de tripletes | La distancia en el embedding refleja la diferencia de pose | Similitud aprendida (profundo) |
| 2015 ◐ | Beyer, Hermans & Leibe, *Biternion nets* (GCPR 2015) | Regresión angular continua con (cos, sin) y pérdida von Mises | El ángulo como punto del círculo unidad | Justifica la métrica circular |
| 2017 ✔ | Ninomiya et al., *Deep manifold embedding for 3D object pose estimation* (SciTePress, 2017; precedido por un informe IEICE de 2016) | La PCA maximiza variación de apariencia, no de pose: falla cuando un giro cambia poco la apariencia | Variedad construida con características profundas entrenadas con información de pose | Señala la debilidad de PCA con objetos simétricos; solución profunda (solo referencia) |
| 2018 ✔ | Prokudin, Gehler & Nowozin, *Deep directional statistics* (ECCV 2018, pp. 534–551) | Distribución von Mises (y mezclas) sobre el ángulo | Salida probabilística multimodal y calibrada | **Inspiró nuestra incertidumbre**: distribución sobre el lazo, conjunto creíble y ambigüedad, en versión clásica |
| 2022 ✔ | Gen6D (ECCV 2022) | Pose de objetos nuevos sin CAD a partir de imágenes de referencia con pose: detector, selector de vista y refinador | Selección de la vista de referencia más parecida + refinado | Nuestro problema en versión 6-DoF; su debilidad declarada: casos fuera de distribución y oclusión |
| 2022–2023 ✔ | OnePose / OnePose++ | Nube de puntos por SfM a partir de un vídeo; emparejamiento 2D-3D | Requiere capturas densas; la cobertura condiciona el resultado | La cobertura de referencia es el límite, igual que en B |
| 2024 ✔ | FoundationPose (NVIDIA, CVPR 2024) | Pose y seguimiento de objetos nuevos con CAD o con pocas imágenes de referencia | Representación implícita neuronal para sintetizar vistas nuevas | El "render" que se propuso inicialmente; depende de suficientes vistas con pose |
| 2025 ✔ | One2Any; BoxDreamer | Pose desde una sola vista de referencia; esquinas de caja como representación | Reducir la dependencia de referencias densas | Tendencia actual: menos referencias, más priors aprendidos |
| 2026 ✔ | Kosaka et al., *Turntable-Constrained Camera Pose Estimation* (CVPR 2026 Workshops, IMW) | SfM con restricción de plato: un solo eje, un ángulo por vista | La geometría moderna también explota el grado de libertad único | Confirma que el plato se aprovecha incluso en pipelines 3D actuales |

## 4.3 Murase & Nayar en detalle (la base del modelo elegido)

Datos de la fuente (resumen de caso del artículo IJCV 1995):

- **Adquisición original**: plato motorizado con precisión de 0,1°, 90 poses (cada 4°) × 5 direcciones de
  iluminación = 450 imágenes por objeto.
- **Normalización de escala**: segmentar el objeto, poner el fondo a cero y reescalar la región para que su
  dimensión mayor ocupe 128×128. **Es la misma normalización que trae COIL** y la que habrá que replicar en planta.
- **Normalización de brillo**: cada imagen como vector con norma 1.
- **Espacios propios**: *universal* (todos los objetos, para reconocer) y *de objeto* (un objeto, para la pose).
  Bastaron 20 o menos vectores propios.
- **Variedad**: las proyecciones de vistas consecutivas quedan cerca; con iluminación fija la apariencia es una
  **curva de un parámetro** (el giro); se interpola con splines cúbicos, lo que permite tratar poses no vistas.
- **Reconocimiento y pose**: proyectar al espacio universal (objeto = curva más cercana) y luego al del objeto
  (pose = posición sobre la curva). Si las curvas de dos objetos se cruzan, esas vistas son ambiguas.
- **Resultado con 20 objetos × 72 imágenes**, 20 vectores propios universales: **100 % de reconocimiento en 320
  imágenes de prueba y error medio de pose de 1,59° (desviación 1,53°)**, menos de 1 s en una SUN Sparc.

Dos lecciones aplicadas: (1) nuestro plato usa este método con PCA global sobre píxeles 32×32; (2) la
normalización de brillo y de escala que ellos aplicaban es justamente lo que nos falta según las pruebas
funcionales (sección 9).

## 4.4 Lo que probamos de cada época (validación interna, sector ciego B)

| Idea | Época | Resultado dentro de ±10° | Veredicto |
|---|---|---|---|
| Vista más cercana (1-NN) | baseline | 27,8 % | Referencia |
| **Curva con spline (Murase & Nayar)** | 1995 | **53,5 %** | **Adoptado** |
| Fourier global (inspirado en Tamaki 2009), K=4 / K=8 | 2009 | 41,0 % / 31,7 % | Descartado: una aproximación global de baja frecuencia no recupera caras no vistas |
| Relleno por simetría de espejo verificada con datos | — | 54,4 % (solo 5 de 100 objetos simétricos en apariencia: 21,7 % → 40,0 % en ellos) | Marginal: la textura y el texto rompen la simetría |
| "3D gratis": silueta espejada a θ+180° | geometría | 28,8 % | Descartado: IoU de siluetas 0,744 frente a 0,932 de la vista a 5° |
| Distribución sobre el ángulo + conjunto creíble (inspirado en Prokudin 2018) | 2018 | — | Adoptado como incertidumbre |
| **2a captura girando un ángulo conocido** (visión activa) | — | **98,0 % (Δ=180°), 98,1 % (Δ=90°)** | **Adoptado como mitigación operativa** |
| Reconstrucción 3D (visual hull, NeRF, 3DGS, al estilo FoundationPose) | 2022–2024 | no implementado | Descartado: ver sección 5.7 |

Conclusión: **ningún método, clásico ni moderno, resuelve el sector ciego con una sola imagen sin información
adicional**. Los modernos reconstruyen 3D y su debilidad declarada es la cobertura de referencia. La respuesta
correcta es operativa: certificar la cobertura del SKU y, si falta, pedir una 2a captura o enviar a manual.

## 4.5 Fuentes consultadas

- Murase & Nayar — resumen de caso del artículo IJCV 1995: https://www.cse.unr.edu/~bebis/MathMethods/PCA/case_study_pca2.pdf
- Parametric eigenspace representation, SPIE 1993: https://electronicimaging.spiedigitallibrary.org/conference-proceedings-of-spie/2031/0000/Parametric-eigenspace-representation-for-visual-learning-and-recognition/10.1117/12.146641.full
- Tamaki, Amano, Kaneda, CVIU 2009: https://hiroshima.repo.nii.ac.jp/records/2006701
- Roth, Yang, Ahuja, Neural Computation 2002: https://mlanthology.org/neco/2002/roth2002neco-learning
- Yang, Roth, Ahuja, ECCV 2000: https://mlanthology.org/eccv/2000/yang2000eccv-learning
- Zhang et al., AAAI 2013: https://ojs.aaai.org/index.php/AAAI/article/view/8634
- Factorization of View-Object Manifolds (arXiv 1503.06813): https://arxiv.org/html/1503.06813
- Ninomiya et al., 2017: https://www.scitepress.org/Papers/2017/61012/
- Prokudin, Gehler, Nowozin, ECCV 2018: https://openaccess.thecvf.com/content_ECCV_2018/html/Sergey_Prokudin_Deep_Directional_Statistics_ECCV_2018_paper.html
- Gen6D, ECCV 2022: https://ecva.net/papers/eccv_2022/papers_ECCV/html/3378_ECCV_2022_paper.php
- FoundationPose, 2024: https://research.nvidia.com/publication/2024-06_foundationpose-unified-6d-pose-estimation-and-tracking-novel-objects
- One2Any (arXiv 2505.04109): https://arxiv.org/html/2505.04109v1 · BoxDreamer (arXiv 2504.07955): https://arxiv.org/pdf/2504.07955
- Turntable-Constrained Camera Pose Estimation, CVPRW 2026: https://openaccess.thecvf.com/content/CVPR2026W/IMW/html/Kosaka_Turntable-Constrained_Camera_Pose_Estimation_CVPRW_2026_paper.html
- COIL-100 en TFDS: https://www.tensorflow.org/datasets/catalog/coil100
- Visual hulls: Matusik et al., Image-Based Visual Hulls (MIT LCS TR): https://ftp.mirrorservice.org/sites/www.bitsavers.org/pdf/mit/lcs/tr/MIT-LCS-TR-0780.pdf · Towards Real-Time Novel View Synthesis Using Visual Hulls: https://diglib.eg.org/handle/10.2312/14682
