# SOP-OPS-005 — Operaciones de riesgo y aprobaciones

## 1. Qué es una operación de riesgo
Cambiar el umbral de confianza, pausar o reanudar la línea, enviar un ángulo manual al robot, promover una
versión de modelo y pasar un producto nuevo a producción.

## 2. Regla general
Ninguna se ejecuta sin una aprobación humana explícita, registrada y hecha fuera de la conversación con el
asistente. El asistente solo puede crear la solicitud.

## 3. Quién puede solicitar y quién aprueba
| Operación | Solicita | Aprueba |
|---|---|---|
| Pausar o reanudar la línea | supervisor, mantenimiento, gerente | supervisor o gerente |
| Cambiar el umbral de confianza | ingeniería de ML, calidad | gerente o calidad |
| Ángulo manual al robot | supervisor, mantenimiento | supervisor o gerente |
| Promover versión de modelo | ingeniería de ML | gerente o calidad |
| Producto nuevo a producción | ingeniería de ML, calidad | gerente o calidad |

## 4. Separación de funciones
Quien solicita no puede aprobar su propia solicitud, salvo la pausa de línea por seguridad, que el supervisor de
turno puede solicitar y aprobar.

## 5. Límites
El umbral de confianza debe estar entre 0,20 y 0,95. Un ángulo manual debe estar en [0°, 360°) y solo se envía
con la línea en pausa.
