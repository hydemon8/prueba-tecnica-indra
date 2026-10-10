# SOP-MNT-001 — Diagnóstico de agarres fallidos

Aplica a: mantenimiento. Estación de pick & pack con cámara y brazo robótico.

## 1. Información mínima antes de diagnosticar
Línea y turno, hora de inicio, número aproximado de fallos, si se concentran en algunos productos (SKU) y si hubo
cambios recientes: mantenimiento, cambio de lámpara, promoción de modelo o cambio de umbral.

## 2. Descartar la cámara
Revisar la salud de la cámara en la ventana del problema. Brillo fuera de ±15 % del nominal o estado DEGRADED
indican un problema de iluminación: seguir SOP-CAM-002. Con iluminación degradada lo habitual es que suban los
rechazos (UNKNOWN), no los agarres fallidos.

## 3. Descartar el modelo
Si la tasa de fallos cambia justo después de una promoción de modelo o de un cambio de umbral, y afecta a todos
los SKU por igual, escalar a ingeniería de ML. No revertir el modelo sin aprobación (SOP-OPS-005).

## 4. Fallos concentrados en pocos SKU con cámara y modelo sanos
Apunta a la pinza o a la ventosa. Comprobar en este orden: presión de vacío (nominal 0,6–0,8 bar), desgaste de
la ventosa, holgura de la pinza y calibración mano-ojo. Si la presión está bajo 0,6 bar, sustituir la ventosa.

## 5. Cuándo pausar la línea
Si la tasa de agarres fallidos supera el 5 % durante 15 minutos, solicitar la pausa de la línea. La pausa es una
operación de riesgo y requiere aprobación (SOP-OPS-005).

## 6. Registro
Crear un ticket con línea, ventana horaria, SKU afectados, comprobaciones hechas y diagnóstico. Severidad alta si
hay producto dañado; crítica si hay riesgo para personas.
