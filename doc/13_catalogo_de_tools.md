# 13. Catálogo de tools y contratos (Reto 3)

Generado desde el código con `python -m lineops.tools.catalog`; no editar a mano. Contratos en JSON Schema:
[`openapi/tools.json`](openapi/tools.json). Implementación: `src/lineops/tools/` y `src/lineops/policy.py`.

## Reglas comunes a todas las tools

- **Única vía de ejecución**: la capa de política (`Executor.execute`). El modelo propone una llamada; el código
  la valida, la autoriza y la ejecuta, la rechaza o la convierte en una solicitud de aprobación.
- **Entrada**: se valida contra el contrato; los campos desconocidos se rechazan (`invalid_arguments`, con el
  detalle por campo). La planta nunca es un argumento: sale de la sesión autenticada.
- **Salida**: sobre uniforme `{"ok": true, "data": {...}}` o
  `{"ok": false, "error": {"code", "message", "retryable"}}`. Un fallo inesperado devuelve `internal_error` con
  un mensaje genérico; la traza queda en el log del servidor, no en el contexto del modelo.
- **Permisos**: por rol (columna «Roles») y por línea: una tool con `line_id` solo actúa sobre las líneas del
  usuario (`out_of_scope`); los identificadores de otra planta devuelven `not_found`.
- **Operaciones de riesgo**: no se ejecutan. Se comprueba la precondición, se crea una solicitud `PENDING` y se
  devuelve `status: pending_approval`. La ejecuta una persona con rol aprobador desde
  `POST /api/approvals/{id}/decision`, que no es una tool. Quien solicita no puede aprobar. Las precondiciones se
  vuelven a comprobar al aprobar.
- **Auditoría**: cada intento, también los rechazados, deja una fila en `audit_log` con sesión, usuario, rol,
  planta, tool, argumentos, resultado, latencia y origen (`agent` o `human`).
- **Contexto del modelo**: recibe el resultado en JSON (truncado a 9.000 caracteres). Nunca recibe bytes de
  imágenes, credenciales ni datos de otra planta. El texto escrito por usuarios (tickets) y los procedimientos
  se tratan como datos, no como instrucciones.
- **Límites por turno**: 8 llamadas al modelo, 12 tools, la misma llamada con los mismos argumentos como mucho
  2 veces y 60.000 tokens.

## Resumen

| # | Tool | Tipo | Riesgo | Roles | Casos de uso |
|---|---|---|---|---|---|
| 1 | [`inspect_images`](#1-inspect_images) | lectura | bajo | todos | inspección de imagen |
| 2 | [`get_model_info`](#2-get_model_info) | lectura | bajo | mantenimiento, ingeniería de ML, gerente, calidad, supervisor | consulta operativa, operación de riesgo |
| 3 | [`get_shift_metrics`](#3-get_shift_metrics) | lectura | bajo | mantenimiento, ingeniería de ML, gerente, calidad, supervisor | consulta operativa, entrega de turno |
| 4 | [`get_line_timeline`](#4-get_line_timeline) | lectura | bajo | mantenimiento, ingeniería de ML, gerente, calidad, supervisor | consulta operativa, diagnóstico de falla |
| 5 | [`get_camera_health`](#5-get_camera_health) | lectura | bajo | mantenimiento, ingeniería de ML, gerente, calidad, supervisor | consulta operativa, diagnóstico de falla |
| 6 | [`get_grasp_failures`](#6-get_grasp_failures) | lectura | bajo | mantenimiento, ingeniería de ML, gerente, calidad, supervisor | diagnóstico de falla |
| 7 | [`list_review_cases`](#7-list_review_cases) | lectura | bajo | ingeniería de ML, gerente, calidad, supervisor | cola de revisión humana, entrega de turno |
| 8 | [`get_review_case`](#8-get_review_case) | lectura | bajo | ingeniería de ML, gerente, calidad, supervisor | cola de revisión humana |
| 9 | [`search_procedures`](#9-search_procedures) | lectura | bajo | todos | diagnóstico de falla, operación de riesgo, alta de producto nuevo |
| 10 | [`list_tickets`](#10-list_tickets) | lectura | bajo | mantenimiento, ingeniería de ML, gerente, calidad, supervisor | diagnóstico de falla, entrega de turno, consulta operativa |
| 11 | [`get_line_status`](#11-get_line_status) | lectura | bajo | todos | consulta operativa, operación de riesgo, entrega de turno |
| 12 | [`resolve_review_case`](#12-resolve_review_case) | escritura | bajo | calidad, supervisor | cola de revisión humana |
| 13 | [`add_to_retraining_dataset`](#13-add_to_retraining_dataset) | escritura | bajo | calidad, supervisor | cola de revisión humana |
| 14 | [`create_ticket`](#14-create_ticket) | escritura | bajo | mantenimiento, gerente, calidad, supervisor | diagnóstico de falla |
| 15 | [`escalate_ticket`](#15-escalate_ticket) | escritura | bajo | mantenimiento, gerente, calidad, supervisor | diagnóstico de falla |
| 16 | [`create_shift_handover`](#16-create_shift_handover) | escritura | bajo | gerente, supervisor | entrega de turno |
| 17 | [`register_sku_candidate`](#17-register_sku_candidate) | escritura | bajo | ingeniería de ML, calidad | alta de producto nuevo |
| 18 | [`request_sku_promotion`](#18-request_sku_promotion) | escritura | **alto** | ingeniería de ML, calidad | alta de producto nuevo, operación de riesgo |
| 19 | [`set_confidence_threshold`](#19-set_confidence_threshold) | escritura | **alto** | ingeniería de ML, calidad | operación de riesgo |
| 20 | [`set_line_state`](#20-set_line_state) | escritura | **alto** | mantenimiento, gerente, supervisor | operación de riesgo, diagnóstico de falla |
| 21 | [`send_manual_angle`](#21-send_manual_angle) | escritura | **alto** | mantenimiento, supervisor | operación de riesgo |
| 22 | [`promote_model_version`](#22-promote_model_version) | escritura | **alto** | ingeniería de ML | operación de riesgo |

22 tools: 11 de lectura y 11 de escritura, de las cuales 5 son operaciones de riesgo.

## Detalle

### 1. `inspect_images`

Analiza con el servicio de visión una o varias imágenes cargadas: valida la captura, identifica el producto, estima el ángulo con su incertidumbre, da la decisión del control de seguridad con sus motivos y devuelve las vistas de referencia más parecidas como evidencia.

- **Tipo**: lectura · **Riesgo**: bajo
- **Roles que pueden usarla**: todos
- **Efectos laterales**: ninguno
- **Ante repeticiones**: lectura pura: repetirla da el mismo resultado para la misma versión de modelo
- **Errores propios**: `image_not_found`, `vision_unavailable (reintentable)`, `vision_rejected`
- **Qué ve el modelo**: identificadores, decisión, métricas y URLs de referencia; nunca los bytes de la imagen

| Argumento | Tipo | Obligatorio | Restricciones | Descripción |
|---|---|---|---|---|
| `image_ids` | lista de string | sí | elementos ≥ `1`; elementos ≤ `8` | Identificadores de imágenes cargadas en esta sesión (img-...) |
| `top_k` | entero | no | ≥ `1`; ≤ `5`; por defecto `3` | Vistas similares a devolver como evidencia |

### 2. `get_model_info`

Versión del modelo que está sirviendo el servicio de visión, sus umbrales del control de seguridad y el registro de versiones (producción, staging, archivadas).

- **Tipo**: lectura · **Riesgo**: bajo
- **Roles que pueden usarla**: mantenimiento, ingeniería de ML, gerente, calidad, supervisor
- **Efectos laterales**: ninguno
- **Ante repeticiones**: n/a
- **Errores propios**: `vision_unavailable (reintentable)`
- **Qué ve el modelo**: versión, umbrales y métricas de calibración; no el artefacto

Sin argumentos.

### 3. `get_shift_metrics`

Métricas de un turno de una línea: objetos procesados, porcentaje atendido por el robot, rechazos por tipo, agarres fallidos, desglose por hora y la referencia de las 24 horas anteriores.

- **Tipo**: lectura · **Riesgo**: bajo
- **Roles que pueden usarla**: mantenimiento, ingeniería de ML, gerente, calidad, supervisor
- **Efectos laterales**: ninguno
- **Ante repeticiones**: n/a
- **Errores propios**: ninguno además de los comunes
- **Qué ve el modelo**: agregados por turno y por hora; no eventos individuales

| Argumento | Tipo | Obligatorio | Restricciones | Descripción |
|---|---|---|---|---|
| `line_id` | texto | sí | patrón `^L\d{1,2}$` | Identificador de la línea, por ejemplo L1 |
| `shift` | `1` \| `2` \| `3` | sí |  | Turno: 1 (06-14), 2 (14-22), 3 (22-06). Devuelve su ocurrencia más reciente |

### 4. `get_line_timeline`

Línea de tiempo de una línea en una ventana: por intervalo, rechazos, agarres fallidos, brillo y estado de la cámara y versión de modelo, más los eventos de la línea (promoción de modelo, mantenimiento, pausas, cambios de umbral). Sirve para explicar por qué cambió una métrica.

- **Tipo**: lectura · **Riesgo**: bajo
- **Roles que pueden usarla**: mantenimiento, ingeniería de ML, gerente, calidad, supervisor
- **Efectos laterales**: ninguno
- **Ante repeticiones**: n/a
- **Errores propios**: `invalid_arguments (ventana > 72 h o mal formada)`
- **Qué ve el modelo**: agregados por intervalo; como máximo 432 filas

| Argumento | Tipo | Obligatorio | Restricciones | Descripción |
|---|---|---|---|---|
| `line_id` | texto | sí | patrón `^L\d{1,2}$` | Identificador de la línea, por ejemplo L1 |
| `start` | texto | sí |  | Inicio de la ventana, fecha y hora ISO local, por ejemplo 2026-10-10T02:00 |
| `end` | texto | sí |  | Fin de la ventana, fecha y hora ISO local |
| `bucket_minutes` | `10` \| `30` \| `60` | no | por defecto `30` | Tamaño del intervalo |

### 5. `get_camera_health`

Salud de la cámara de una línea en una ventana: brillo medio y mínimo frente al nominal, enfoque, fotogramas perdidos e intervalo en estado degradado.

- **Tipo**: lectura · **Riesgo**: bajo
- **Roles que pueden usarla**: mantenimiento, ingeniería de ML, gerente, calidad, supervisor
- **Efectos laterales**: ninguno
- **Ante repeticiones**: n/a
- **Errores propios**: `invalid_arguments`, `no_data`

| Argumento | Tipo | Obligatorio | Restricciones | Descripción |
|---|---|---|---|---|
| `line_id` | texto | sí | patrón `^L\d{1,2}$` | Identificador de la línea, por ejemplo L1 |
| `start` | texto | sí |  | Inicio de la ventana, fecha y hora ISO local, por ejemplo 2026-10-10T02:00 |
| `end` | texto | sí |  | Fin de la ventana, fecha y hora ISO local |

### 6. `get_grasp_failures`

Agarres fallidos del robot en una ventana: total, tasa, primer fallo y desglose por producto (SKU), con la concentración en los tres más afectados.

- **Tipo**: lectura · **Riesgo**: bajo
- **Roles que pueden usarla**: mantenimiento, ingeniería de ML, gerente, calidad, supervisor
- **Efectos laterales**: ninguno
- **Ante repeticiones**: n/a
- **Errores propios**: `invalid_arguments`

| Argumento | Tipo | Obligatorio | Restricciones | Descripción |
|---|---|---|---|---|
| `line_id` | texto | sí | patrón `^L\d{1,2}$` | Identificador de la línea, por ejemplo L1 |
| `start` | texto | sí |  | Inicio de la ventana, fecha y hora ISO local, por ejemplo 2026-10-10T02:00 |
| `end` | texto | sí |  | Fin de la ventana, fecha y hora ISO local |

### 7. `list_review_cases`

Lista los casos de la cola de revisión humana de una línea (rechazados por baja confianza).

- **Tipo**: lectura · **Riesgo**: bajo
- **Roles que pueden usarla**: ingeniería de ML, gerente, calidad, supervisor
- **Efectos laterales**: ninguno
- **Ante repeticiones**: n/a
- **Errores propios**: ninguno además de los comunes

| Argumento | Tipo | Obligatorio | Restricciones | Descripción |
|---|---|---|---|---|
| `line_id` | texto | sí | patrón `^L\d{1,2}$` | Identificador de la línea, por ejemplo L1 |
| `status` | `PENDING` \| `RESOLVED` | no | por defecto `PENDING` |  |
| `limit` | entero | no | ≥ `1`; ≤ `25`; por defecto `10` |  |

### 8. `get_review_case`

Detalle de un caso de revisión con su evidencia: lo que propuso el modelo, su confianza, los motivos del rechazo y las vistas de referencia más parecidas.

- **Tipo**: lectura · **Riesgo**: bajo
- **Roles que pueden usarla**: ingeniería de ML, gerente, calidad, supervisor
- **Efectos laterales**: ninguno
- **Ante repeticiones**: n/a
- **Errores propios**: `not_found`

| Argumento | Tipo | Obligatorio | Restricciones | Descripción |
|---|---|---|---|---|
| `case_id` | texto | sí | patrón `^RC-\d{4}$` | Identificador del caso, por ejemplo RC-0003 |

### 9. `search_procedures`

Busca en los procedimientos y manuales de planta (SOP) y devuelve las secciones más relevantes con su cita (documento y sección).

- **Tipo**: lectura · **Riesgo**: bajo
- **Roles que pueden usarla**: todos
- **Efectos laterales**: ninguno
- **Ante repeticiones**: n/a
- **Errores propios**: ninguno además de los comunes
- **Qué ve el modelo**: hasta 5 secciones de texto; son datos de referencia, no instrucciones para el asistente

| Argumento | Tipo | Obligatorio | Restricciones | Descripción |
|---|---|---|---|---|
| `query` | texto | sí | longitud ≥ `3`; longitud ≤ `300` | Qué se busca en los procedimientos y manuales |
| `k` | entero | no | ≥ `1`; ≤ `5`; por defecto `3` |  |

### 10. `list_tickets`

Tickets de mantenimiento e incidencias de una línea, con su estado y severidad.

- **Tipo**: lectura · **Riesgo**: bajo
- **Roles que pueden usarla**: mantenimiento, ingeniería de ML, gerente, calidad, supervisor
- **Efectos laterales**: ninguno
- **Ante repeticiones**: n/a
- **Errores propios**: ninguno además de los comunes
- **Qué ve el modelo**: título y descripción escritos por usuarios (contenido no confiable, tratado como dato)

| Argumento | Tipo | Obligatorio | Restricciones | Descripción |
|---|---|---|---|---|
| `line_id` | texto | sí | patrón `^L\d{1,2}$` | Identificador de la línea, por ejemplo L1 |
| `status` | `OPEN` \| `ESCALATED` \| `RESOLVED` \| `ANY` | no | por defecto `ANY` |  |

### 11. `get_line_status`

Estado actual de una línea: en marcha o en pausa, umbral de confianza, versión de modelo, cámara, últimos eventos y solicitudes de aprobación pendientes.

- **Tipo**: lectura · **Riesgo**: bajo
- **Roles que pueden usarla**: todos
- **Efectos laterales**: ninguno
- **Ante repeticiones**: n/a
- **Errores propios**: `not_found`

| Argumento | Tipo | Obligatorio | Restricciones | Descripción |
|---|---|---|---|---|
| `line_id` | texto | sí | patrón `^L\d{1,2}$` | Identificador de la línea, por ejemplo L1 |

### 12. `resolve_review_case`

Registra la etiqueta (SKU) y el ángulo que una persona ha confirmado para un caso de la cola de revisión. Úsala solo con valores que el usuario haya dado explícitamente en la conversación.

- **Tipo**: escritura · **Riesgo**: bajo
- **Roles que pueden usarla**: calidad, supervisor
- **Efectos laterales**: marca el caso como resuelto con el usuario de la sesión como responsable
- **Ante repeticiones**: repetir con los mismos valores devuelve already_resolved; con otros valores, error conflict
- **Errores propios**: `not_found`, `conflict`, `permission_denied`

| Argumento | Tipo | Obligatorio | Restricciones | Descripción |
|---|---|---|---|---|
| `case_id` | texto | sí | patrón `^RC-\d{4}$` | Caso a resolver, por ejemplo RC-0003 |
| `confirmed_object_id` | entero | sí | ≥ `1`; ≤ `100000` | Producto (SKU) confirmado por la persona |
| `confirmed_angle_deg` | número | sí | ≥ `0`; < `360` | Ángulo confirmado por la persona, en grados |

### 13. `add_to_retraining_dataset`

Añade un caso de revisión ya resuelto al dataset de reentrenamiento, con su etiqueta y su ángulo confirmados.

- **Tipo**: escritura · **Riesgo**: bajo
- **Roles que pueden usarla**: calidad, supervisor
- **Efectos laterales**: inserta un elemento en el dataset de reentrenamiento
- **Ante repeticiones**: un caso solo entra una vez (restricción única); repetir devuelve already_in_dataset
- **Errores propios**: `not_found`, `precondition_failed`

| Argumento | Tipo | Obligatorio | Restricciones | Descripción |
|---|---|---|---|---|
| `case_id` | texto | sí | patrón `^RC-\d{4}$` | Identificador del caso, por ejemplo RC-0003 |

### 14. `create_ticket`

Crea un ticket de mantenimiento o incidencia para una línea.

- **Tipo**: escritura · **Riesgo**: bajo
- **Roles que pueden usarla**: mantenimiento, gerente, calidad, supervisor
- **Efectos laterales**: crea un ticket abierto
- **Ante repeticiones**: mismo usuario, línea y título con un ticket aún abierto: devuelve el existente (deduplicated)
- **Errores propios**: `not_found`, `invalid_arguments`

| Argumento | Tipo | Obligatorio | Restricciones | Descripción |
|---|---|---|---|---|
| `line_id` | texto | sí | patrón `^L\d{1,2}$` | Identificador de la línea, por ejemplo L1 |
| `title` | texto | sí | longitud ≥ `5`; longitud ≤ `120` |  |
| `description` | texto | sí | longitud ≥ `10`; longitud ≤ `2000` | Ventana horaria, SKU afectados, comprobaciones hechas y diagnóstico |
| `severity` | `low` \| `medium` \| `high` \| `critical` | sí |  |  |

### 15. `escalate_ticket`

Escala un ticket abierto al gerente de planta, con el motivo.

- **Tipo**: escritura · **Riesgo**: bajo
- **Roles que pueden usarla**: mantenimiento, gerente, calidad, supervisor
- **Efectos laterales**: cambia el estado a ESCALATED y asigna al gerente de planta
- **Ante repeticiones**: escalar un ticket ya escalado no cambia nada (already_escalated)
- **Errores propios**: `not_found`, `precondition_failed`

| Argumento | Tipo | Obligatorio | Restricciones | Descripción |
|---|---|---|---|---|
| `ticket_id` | texto | sí | patrón `^TCK-\d{3,6}$` |  |
| `reason` | texto | sí | longitud ≥ `10`; longitud ≤ `500` |  |

### 16. `create_shift_handover`

Genera y guarda el reporte de entrega de un turno: métricas, incidentes detectados con las reglas del procedimiento, tickets abiertos, casos pendientes de revisión y aprobaciones pendientes.

- **Tipo**: escritura · **Riesgo**: bajo
- **Roles que pueden usarla**: gerente, supervisor
- **Efectos laterales**: guarda el reporte con un identificador por línea, fecha y turno
- **Ante repeticiones**: un reporte por línea y turno: regenerarlo reemplaza el anterior (replaced_previous)
- **Errores propios**: ninguno además de los comunes
- **Qué ve el modelo**: el reporte estructurado; las cifras salen de la base, no del modelo

| Argumento | Tipo | Obligatorio | Restricciones | Descripción |
|---|---|---|---|---|
| `line_id` | texto | sí | patrón `^L\d{1,2}$` | Identificador de la línea, por ejemplo L1 |
| `shift` | `1` \| `2` \| `3` | sí |  | Turno: 1 (06-14), 2 (14-22), 3 (22-06). Devuelve su ocurrencia más reciente |

### 17. `register_sku_candidate`

Alta de un producto nuevo en staging a partir de un lote de vistas: valida que el material sea suficiente (número de vistas, cobertura angular, calidad de captura y que no se confunda con el catálogo), lo incorpora en el entorno controlado y devuelve la verificación de desempeño.

- **Tipo**: escritura · **Riesgo**: bajo
- **Roles que pueden usarla**: ingeniería de ML, calidad
- **Efectos laterales**: crea un candidato en staging; nunca toca producción
- **Ante repeticiones**: un candidato por nombre y planta: repetir devuelve el existente (already_registered)
- **Errores propios**: `batch_not_found`, `vision_unavailable (reintentable)`
- **Qué ve el modelo**: resultado de cada comprobación; la evaluación en staging está simulada y así se marca

| Argumento | Tipo | Obligatorio | Restricciones | Descripción |
|---|---|---|---|---|
| `name` | texto | sí | longitud ≥ `3`; longitud ≤ `60` | Nombre del producto nuevo |
| `batch_id` | texto | sí | patrón `^lote-[0-9a-f]{8}$` | Lote de imágenes cargado en esta sesión (lote-...) |
| `step_deg` | número | sí | ≤ `120`; > `0` | Giro del plato entre vistas consecutivas, en grados. Las vistas se ordenan por nombre de archivo empezando en 0° |

### 18. `request_sku_promotion`

Solicita pasar a producción un producto que está en staging y cumple el criterio de aceptación. No lo ejecuta: crea una solicitud que debe aprobar calidad o el gerente de planta.

- **Tipo**: escritura · **Riesgo**: alto, requiere aprobación humana
- **Roles que pueden usarla**: ingeniería de ML, calidad
- **Roles que pueden aprobarla**: gerente, calidad
- **Efectos laterales**: al aprobarse, el candidato pasa a producción
- **Ante repeticiones**: una solicitud pendiente por operación y argumentos; aprobar dos veces no la re-ejecuta
- **Errores propios**: `not_found`, `precondition_failed`

| Argumento | Tipo | Obligatorio | Restricciones | Descripción |
|---|---|---|---|---|
| `candidate_id` | texto | sí | patrón `^SKU-C-\d{3}$` |  |

### 19. `set_confidence_threshold`

Solicita cambiar el umbral de confianza de una línea (entre 0,20 y 0,95). No lo ejecuta: crea una solicitud que debe aprobar calidad o el gerente de planta.

- **Tipo**: escritura · **Riesgo**: alto, requiere aprobación humana
- **Roles que pueden usarla**: ingeniería de ML, calidad
- **Roles que pueden aprobarla**: gerente, calidad
- **Efectos laterales**: al aprobarse, cambia el umbral de la línea y registra el evento
- **Ante repeticiones**: una solicitud pendiente por operación y argumentos; aprobar dos veces no la re-ejecuta
- **Errores propios**: `invalid_arguments (fuera de 0,20–0,95)`, `not_found`

| Argumento | Tipo | Obligatorio | Restricciones | Descripción |
|---|---|---|---|---|
| `line_id` | texto | sí | patrón `^L\d{1,2}$` | Identificador de la línea, por ejemplo L1 |
| `value` | número | sí | ≥ `0.2`; ≤ `0.95` | Nuevo umbral mínimo de confianza de clase |
| `reason` | texto | sí | longitud ≥ `10`; longitud ≤ `300` |  |

### 20. `set_line_state`

Solicita pausar o reanudar una línea. No lo ejecuta: crea una solicitud que debe aprobar un supervisor o el gerente de planta.

- **Tipo**: escritura · **Riesgo**: alto, requiere aprobación humana
- **Roles que pueden usarla**: mantenimiento, gerente, supervisor
- **Roles que pueden aprobarla**: gerente, supervisor (con la excepción de separación de funciones documentada en SOP-OPS-005 § 4)
- **Efectos laterales**: al aprobarse, cambia el estado de la línea y registra el evento
- **Ante repeticiones**: si la línea ya está en ese estado devuelve no_change; una solicitud pendiente por argumentos
- **Errores propios**: `not_found`, `no_change`

| Argumento | Tipo | Obligatorio | Restricciones | Descripción |
|---|---|---|---|---|
| `line_id` | texto | sí | patrón `^L\d{1,2}$` | Identificador de la línea, por ejemplo L1 |
| `state` | `PAUSED` \| `RUNNING` | sí |  | PAUSED para pausar, RUNNING para reanudar |
| `reason` | texto | sí | longitud ≥ `10`; longitud ≤ `300` |  |

### 21. `send_manual_angle`

Solicita enviar al robot un ángulo indicado manualmente para el objeto que está en la posición de agarre. Solo con la línea en pausa. No lo ejecuta: requiere aprobación de un supervisor o gerente.

- **Tipo**: escritura · **Riesgo**: alto, requiere aprobación humana
- **Roles que pueden usarla**: mantenimiento, supervisor
- **Roles que pueden aprobarla**: gerente, supervisor
- **Efectos laterales**: al aprobarse, el robot recibe la orden y se registra el evento
- **Ante repeticiones**: una solicitud pendiente por argumentos; una solicitud ejecutada no se puede repetir
- **Errores propios**: `precondition_failed (línea en marcha)`, `invalid_arguments`

| Argumento | Tipo | Obligatorio | Restricciones | Descripción |
|---|---|---|---|---|
| `line_id` | texto | sí | patrón `^L\d{1,2}$` | Identificador de la línea, por ejemplo L1 |
| `object_id` | entero | sí | ≥ `1`; ≤ `100000` | Producto que está en la posición de agarre |
| `angle_deg` | número | sí | ≥ `0`; < `360` | Ángulo que el robot debe compensar |
| `reason` | texto | sí | longitud ≥ `10`; longitud ≤ `300` |  |

### 22. `promote_model_version`

Solicita promover a producción en una línea una versión de modelo que está en staging. No lo ejecuta: crea una solicitud que debe aprobar calidad o el gerente de planta.

- **Tipo**: escritura · **Riesgo**: alto, requiere aprobación humana
- **Roles que pueden usarla**: ingeniería de ML
- **Roles que pueden aprobarla**: gerente, calidad
- **Efectos laterales**: al aprobarse, la línea pasa a usar la versión y se registra el evento
- **Ante repeticiones**: una solicitud pendiente por argumentos; tras ejecutarse la versión ya no está en staging
- **Errores propios**: `not_found`, `precondition_failed`

| Argumento | Tipo | Obligatorio | Restricciones | Descripción |
|---|---|---|---|---|
| `line_id` | texto | sí | patrón `^L\d{1,2}$` | Identificador de la línea, por ejemplo L1 |
| `version` | texto | sí | longitud ≥ `3`; longitud ≤ `40` | Versión de modelo en staging que se quiere poner en producción |
| `reason` | texto | sí | longitud ≥ `10`; longitud ≤ `300` |  |
