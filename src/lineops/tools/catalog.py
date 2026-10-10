"""Genera el catálogo de tools desde el código (entregable 7): Markdown para personas y JSON Schema.

    uv run --extra agent python -m lineops.tools.catalog
"""

from __future__ import annotations

import json

from linevision.config import ROOT

from . import REGISTRY
from .base import ALL_ROLES, ToolSpec

ROLES = {"operator": "operario", "supervisor": "supervisor", "quality": "calidad", "maintenance": "mantenimiento",
         "ml_engineer": "ingeniería de ML", "plant_manager": "gerente"}
MD, JS = ROOT / "doc" / "13_catalogo_de_tools.md", ROOT / "doc" / "openapi" / "tools.json"

HEADER = """# 13. Catálogo de tools y contratos (Reto 3)

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
"""


def _roles(roles) -> str:
    return "todos" if set(roles) == set(ALL_ROLES) else ", ".join(ROLES[r] for r in sorted(roles))


def _type(prop: dict) -> str:
    t = prop.get("type", "")
    if "enum" in prop:
        return " \\| ".join(f"`{v}`" for v in prop["enum"])
    if t == "array":
        return f"lista de {prop.get('items', {}).get('type', 'valores')}"
    return {"string": "texto", "integer": "entero", "number": "número", "boolean": "booleano"}.get(t, t)


def _limits(prop: dict) -> str:
    names = {"minimum": "≥", "maximum": "≤", "exclusiveMinimum": ">", "exclusiveMaximum": "<", "minLength": "longitud ≥",
             "maxLength": "longitud ≤", "minItems": "elementos ≥", "maxItems": "elementos ≤", "pattern": "patrón"}
    out = [f"{label} `{prop[k]}`" for k, label in names.items() if k in prop]
    if "default" in prop:
        out.append(f"por defecto `{prop['default']}`")
    return "; ".join(out)


def _section(i: int, s: ToolSpec) -> str:
    schema = s.json_schema()
    required = set(schema.get("required", []))
    lines = [f"### {i}. `{s.name}`", "", s.description, "",
             f"- **Tipo**: {'lectura' if s.kind == 'read' else 'escritura'} · **Riesgo**: "  # noqa: ISC004
             f"{'alto, requiere aprobación humana' if s.risk == 'high' else 'bajo'}",
             f"- **Roles que pueden usarla**: {_roles(s.roles)}"]
    if s.risk == "high":
        extra = " (con la excepción de separación de funciones documentada en SOP-OPS-005 § 4)" if s.self_approval else ""
        lines.append(f"- **Roles que pueden aprobarla**: {_roles(s.approvers)}{extra}")
    lines += [f"- **Efectos laterales**: {s.side_effects}",
              f"- **Ante repeticiones**: {s.idempotency}",
              f"- **Errores propios**: {', '.join(f'`{f}`' for f in s.failure_modes) or 'ninguno además de los comunes'}"]
    if s.model_sees:
        lines.append(f"- **Qué ve el modelo**: {s.model_sees}")
    props = schema.get("properties", {})
    if props:
        lines += ["", "| Argumento | Tipo | Obligatorio | Restricciones | Descripción |", "|---|---|---|---|---|"]
        for name, p in props.items():
            lines.append(f"| `{name}` | {_type(p)} | {'sí' if name in required else 'no'} | {_limits(p)} | "
                         f"{p.get('description', '')} |")
    else:
        lines += ["", "Sin argumentos."]
    return "\n".join(lines) + "\n"


def main() -> None:
    specs = list(REGISTRY.values())
    md = HEADER
    for i, s in enumerate(specs, 1):
        md += (f"| {i} | [`{s.name}`](#{i}-{s.name}) | {'lectura' if s.kind == 'read' else 'escritura'} | "
               f"{'**alto**' if s.risk == 'high' else 'bajo'} | {_roles(s.roles)} | {', '.join(s.use_cases)} |\n")
    kinds = [s.kind for s in specs]
    md += (f"\n{len(specs)} tools: {kinds.count('read')} de lectura y {kinds.count('write')} de escritura, de las "
           f"cuales {sum(s.risk == 'high' for s in specs)} son operaciones de riesgo.\n\n## Detalle\n\n")
    md += "\n".join(_section(i, s) for i, s in enumerate(specs, 1))
    MD.write_text(md, encoding="utf-8", newline="\n")
    JS.parent.mkdir(exist_ok=True)
    JS.write_text(json.dumps({"tools": [
        {"name": s.name, "kind": s.kind, "risk": s.risk, "description": s.description, "roles": sorted(s.roles),
         "approver_roles": sorted(s.approvers), "use_cases": list(s.use_cases), "side_effects": s.side_effects,
         "idempotency": s.idempotency, "errors": list(s.failure_modes), "input_schema": s.json_schema(),
         "output_envelope": {"ok": "boolean", "data": "object si ok", "error": "{code, message, retryable} si no ok"}}
        for s in specs]}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(specs)} tools -> {MD.name}, {JS.name}")


if __name__ == "__main__":
    main()
