"""Conocimiento recuperado: búsqueda léxica (BM25) sobre los procedimientos, por secciones y con cita.

Los procedimientos son pocos y cortos, así que un índice léxico en memoria es suficiente, determinista y
no añade costo ni otra dependencia. Cada resultado lleva su cita (documento y sección).
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

_STOP = set("a al ante con de del el en es la las lo los o para por que se si sin su un una y no".split())  # noqa: SIM905


def tokens(text: str) -> list[str]:
    text = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return [t for t in re.findall(r"[a-z0-9]+", text) if t not in _STOP and len(t) > 1]


@dataclass(frozen=True)
class Section:
    doc_id: str
    title: str
    section: str
    text: str

    @property
    def citation(self) -> str:
        return f"{self.doc_id} § {self.section}"


def load_sections(folder: Path) -> list[Section]:
    out = []
    for path in sorted(Path(folder).glob("*.md")):
        doc_id = path.stem.split("_")[0]
        lines = path.read_text(encoding="utf-8").splitlines()
        title = lines[0].lstrip("# ").strip()
        current, body = None, []
        for line in lines[1:] + ["## fin"]:
            if line.startswith("## "):
                if current and body:
                    out.append(Section(doc_id, title, current, "\n".join(body).strip()))
                current, body = line[3:].strip(), []
            elif current:
                body.append(line)
    return out


class KnowledgeBase:
    def __init__(self, folder: Path, k1: float = 1.5, b: float = 0.75):
        self.sections = load_sections(folder)
        self.k1, self.b = k1, b
        self.docs = [Counter(tokens(f"{s.title} {s.section} {s.text}")) for s in self.sections]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg = sum(self.lengths) / max(len(self.docs), 1)
        df = Counter(t for d in self.docs for t in d)
        self.idf = {t: math.log(1 + (len(self.docs) - n + 0.5) / (n + 0.5)) for t, n in df.items()}

    def search(self, query: str, k: int = 3) -> list[dict]:
        q = tokens(query)
        scored = []
        for s, d, n in zip(self.sections, self.docs, self.lengths):
            score = sum(self.idf.get(t, 0) * d[t] * (self.k1 + 1) /
                        (d[t] + self.k1 * (1 - self.b + self.b * n / self.avg)) for t in q if t in d)
            if score > 0:
                scored.append((score, s))
        scored.sort(key=lambda x: -x[0])
        return [{"citation": s.citation, "document": s.title, "text": s.text, "score": round(sc, 2)}
                for sc, s in scored[:k]]
