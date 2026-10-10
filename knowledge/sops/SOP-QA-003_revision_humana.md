# SOP-QA-003 — Cola de revisión humana y reentrenamiento

## 1. Qué llega a la cola
Los objetos con decisión REVIEW: confianza de clase bajo el umbral, o la vista más parecida pertenece a otro
producto. El objeto queda desviado físicamente hasta que alguien lo resuelve.

## 2. Cómo se resuelve un caso
Un supervisor o un analista de calidad mira el objeto y la evidencia, y confirma el producto (SKU) y el ángulo.
El asistente nunca confirma por su cuenta: registra lo que la persona indica.

## 3. Envío a reentrenamiento
Todo caso resuelto se añade al dataset de reentrenamiento con su etiqueta y su ángulo confirmados. Un caso solo
puede añadirse una vez.

## 4. Plazo
Los casos pendientes se resuelven dentro del turno. Los que queden se listan en la entrega de turno.
