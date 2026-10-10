"""Imágenes cargadas por los usuarios. Se guardan en disco y se referencian por identificador.

El modelo de lenguaje nunca recibe los bytes: solo identificadores y metadatos. Cada imagen pertenece a una
sesión, una planta y un usuario, y caduca (retención por defecto: 72 h).
"""

from __future__ import annotations

import hashlib
import io
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .plant.db import one, rows
from .tools.base import Principal, ToolError

MAX_BYTES = 5_000_000
MAX_FILES = 80


class ImageStore:
    def __init__(self, con: sqlite3.Connection, folder: Path, ttl_hours: int = 72):
        self.con, self.folder, self.ttl = con, Path(folder), timedelta(hours=ttl_hours)

    def save_batch(self, principal: Principal, files: list[tuple[str, bytes]], now: datetime) -> dict:
        """Guarda un lote de imágenes y devuelve identificadores. Rechaza lo que no sea una imagen."""
        if not files or len(files) > MAX_FILES:
            raise ToolError("invalid_upload", f"se admiten entre 1 y {MAX_FILES} imágenes por carga")
        batch_id = f"lote-{uuid.uuid4().hex[:8]}"
        target = self.folder / principal.plant_id / principal.session_id
        target.mkdir(parents=True, exist_ok=True)
        out = []
        for name, data in sorted(files, key=lambda f: f[0] or ""):
            if len(data) > MAX_BYTES:
                raise ToolError("invalid_upload", f"{name}: supera {MAX_BYTES} bytes")
            try:
                Image.open(io.BytesIO(data)).verify()
            except (UnidentifiedImageError, OSError, ValueError):
                raise ToolError("invalid_upload", f"{name}: no es una imagen válida") from None
            image_id = f"img-{uuid.uuid4().hex[:10]}"
            path = target / f"{image_id}.bin"
            path.write_bytes(data)
            self.con.execute(
                "INSERT INTO images VALUES (?,?,?,?,?,?,?,?,?,?)",
                (image_id, hashlib.sha256(data).hexdigest(), str(path), f"{batch_id}/{Path(name or 'imagen').name}",
                 principal.plant_id, None, principal.session_id, principal.user_id, now.isoformat(timespec="seconds"),
                 (now + self.ttl).isoformat(timespec="seconds")))
            out.append({"image_id": image_id, "filename": Path(name or "imagen").name})
        return {"batch_id": batch_id, "images": out}

    def _visible(self, principal: Principal, where: str, param: str, now: datetime) -> list[dict]:
        # aislamiento: solo imágenes de la propia sesión y planta, y no caducadas
        return rows(self.con, f"SELECT * FROM images WHERE {where} AND session_id=? AND plant_id=? AND expires_at>?"
                              " ORDER BY filename",
                    (param, principal.session_id, principal.plant_id, now.isoformat(timespec="seconds")))

    def load(self, principal: Principal, image_id: str, now: datetime) -> tuple[dict, bytes]:
        found = self._visible(principal, "image_id=?", image_id, now)
        if not found:
            raise ToolError("image_not_found", f"no existe la imagen {image_id} en esta sesión (o ha caducado)")
        return found[0], Path(found[0]["path"]).read_bytes()

    def batch(self, principal: Principal, batch_id: str, now: datetime) -> list[dict]:
        found = self._visible(principal, "filename LIKE ? || '/%'", batch_id, now)
        if not found:
            raise ToolError("batch_not_found", f"no existe el lote {batch_id} en esta sesión (o ha caducado)")
        return found

    def get_public(self, image_id: str) -> dict | None:
        return one(self.con, "SELECT image_id, filename, sha256, created_at FROM images WHERE image_id=?", (image_id,))
