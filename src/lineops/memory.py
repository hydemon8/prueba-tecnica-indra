"""Estado y memoria del asistente. Cuatro cosas distintas, guardadas en sitios distintos:

  - Estado de ejecución: los pasos de un turno (llamadas a tools y sus resultados). Vive en memoria mientras
    dura el turno y no se reutiliza como contexto en turnos posteriores; queda en la auditoría.
  - Historial conversacional: lo que dijeron el usuario y el asistente, por sesión (tabla `messages`).
  - Memoria persistente: el estado de la planta (casos, tickets, aprobaciones, entregas de turno). No es
    memoria del modelo: se consulta con tools, así que siempre está al día y sujeta a permisos.
  - Conocimiento recuperado: secciones de procedimientos traídas por `search_procedures` en el turno.

Control del crecimiento del contexto: entre turnos solo viaja texto (nunca resultados de tools ni
imágenes); los últimos mensajes van íntegros y los anteriores se pliegan en un resumen acotado.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime

from .plant.db import one, rows
from .plant.seed import iso
from .tools.base import Principal, ToolError

SUMMARY_MAX_CHARS = 2400


class SessionStore:
    def __init__(self, con: sqlite3.Connection, keep_messages: int = 24, keep_chars: int = 600):
        self.con, self.keep_messages, self.keep_chars = con, keep_messages, keep_chars

    def create(self, user_id: str, plant_id: str, now: datetime) -> str:
        session_id = f"ses-{uuid.uuid4().hex[:12]}"
        self.con.execute("INSERT INTO sessions (session_id, user_id, plant_id, created_at) VALUES (?,?,?,?)",
                         (session_id, user_id, plant_id, iso(now)))
        return session_id

    def check(self, principal: Principal) -> dict:
        """Una sesión pertenece a un usuario y a una planta: nadie más puede leerla ni continuarla."""
        s = one(self.con, "SELECT * FROM sessions WHERE session_id=?", (principal.session_id,))
        if not s or s["user_id"] != principal.user_id or s["plant_id"] != principal.plant_id:
            raise ToolError("session_not_found", "la sesión no existe o no pertenece a este usuario")
        return s

    def append(self, principal: Principal, turn: int, role: str, text: str, meta: dict, now: datetime) -> None:
        self.con.execute("INSERT INTO messages (session_id, turn, role, text, meta, created_at) VALUES (?,?,?,?,?,?)",
                         (principal.session_id, turn, role, text, json.dumps(meta, ensure_ascii=False), iso(now)))
        if role == "assistant":
            self.con.execute("UPDATE sessions SET turns=? WHERE session_id=?", (turn, principal.session_id))
            self._compact(principal.session_id)

    def _compact(self, session_id: str) -> None:
        msgs = rows(self.con, "SELECT id, role, text FROM messages WHERE session_id=? AND meta NOT LIKE '%\"folded\": true%'"
                              " ORDER BY id", (session_id,))
        overflow = msgs[:-self.keep_messages] if len(msgs) > self.keep_messages else []
        if not overflow:
            return
        summary = one(self.con, "SELECT summary FROM sessions WHERE session_id=?", (session_id,))["summary"]
        for m in overflow:
            who = "Usuario" if m["role"] == "user" else "Asistente"
            summary += f"\n{who}: {m['text'][:self.keep_chars]}"
            self.con.execute("UPDATE messages SET meta=json_set(meta, '$.folded', json('true')) WHERE id=?", (m["id"],))
        self.con.execute("UPDATE sessions SET summary=? WHERE session_id=?", (summary[-SUMMARY_MAX_CHARS:], session_id))

    def context(self, principal: Principal) -> tuple[str, list[dict], int]:
        """Resumen de lo antiguo, mensajes recientes en formato neutro y número del siguiente turno."""
        s = self.check(principal)
        recent = rows(self.con, "SELECT role, text, meta FROM messages WHERE session_id=? ORDER BY id", (principal.session_id,))
        msgs = []
        for m in recent:
            meta = json.loads(m["meta"])
            if meta.get("folded"):
                continue
            text = m["text"]
            if m["role"] == "assistant" and meta.get("tools"):
                text += f"\n[tools usadas en este turno: {', '.join(meta['tools'])}]"
            msgs.append({"role": m["role"], "text": text})
        return s["summary"], msgs, s["turns"] + 1

    def transcript(self, principal: Principal) -> list[dict]:
        self.check(principal)
        return [{"role": m["role"], "text": m["text"], "meta": json.loads(m["meta"]), "created_at": m["created_at"]}
                for m in rows(self.con, "SELECT * FROM messages WHERE session_id=? ORDER BY id", (principal.session_id,))]
