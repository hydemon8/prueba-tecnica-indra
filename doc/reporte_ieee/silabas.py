"""Separación silábica mínima del español para insertar guiones opcionales en el texto justificado.

Chrome no parte palabras en español al imprimir si no tiene el diccionario instalado, y las columnas estrechas
quedan con huecos. Las reglas son las de la división silábica entre consonantes; nunca se separan dos vocales,
así que no hay que decidir entre diptongo e hiato. Solo se tocan palabras en minúsculas.
"""
import re

VOWELS = "aeiouáéíóúü"
CLUSTERS = {"bl", "br", "cl", "cr", "dr", "fl", "fr", "gl", "gr", "pl", "pr", "tr", "ch", "ll", "rr"}
SHY = "­"
WORD = re.compile(r"[a-záéíóúüñ]{7,}")


def breaks(word):
    """Posiciones donde la palabra admite guion."""
    out, i, n = [], 0, len(word)
    while i < n:
        if word[i] in VOWELS:
            j = i + 1
            while j < n and word[j] not in VOWELS:
                j += 1
            cons = j - (i + 1)
            if j < n and cons:                      # vocal + consonantes + vocal
                if cons == 1:
                    cut = i + 1
                elif word[j - 2:j] in CLUSTERS:
                    cut = j - 2
                else:
                    cut = j - 1
                out.append(cut)
            i = j
        else:
            i += 1
    return [k for k in out if k >= 2 and n - k >= 3]


def hyphenate_word(word):
    cuts = breaks(word)
    if not cuts:
        return word
    parts, last = [], 0
    for k in cuts:
        parts.append(word[last:k])
        last = k
    parts.append(word[last:])
    return SHY.join(parts)


def hyphenate_text(text):
    return WORD.sub(lambda m: m.group(0) if m.start() and text[m.start() - 1].isalnum() else hyphenate_word(m.group(0)), text)


def hyphenate_html(html):
    """Parte las palabras del texto corrido: párrafos, pies de figura y listas. No toca etiquetas, entidades,
    código, texto en cursiva (términos en otro idioma) ni fórmulas."""
    def block(m):
        out, skip = [], 0
        for piece in re.split(r"(<[^>]+>|&[a-z#0-9]+;)", m.group(0)):
            if piece.startswith("<"):
                tag = re.match(r"</?([a-z0-9]+)", piece)
                name = tag.group(1) if tag else ""
                if name in ("i", "code", "svg", "sub", "sup", "span"):
                    skip += -1 if piece.startswith("</") else (0 if piece.endswith("/>") else 1)
                out.append(piece)
            elif piece.startswith("&") or skip > 0:
                out.append(piece)
            else:
                out.append(hyphenate_text(piece))
        return "".join(out)

    return re.sub(r"<(p|figcaption|li)\b[^>]*>.*?</\1>", block, html, flags=re.S)


if __name__ == "__main__":
    for w in ["construyó", "abstenerse", "instrucción", "exactitud", "desarrollo", "transporte", "obstáculo", "identificación",
              "características", "entrenamiento", "aprendizaje", "automático", "representación", "incertidumbre", "ambigüedad",
              "distribución", "probabilidad", "herramienta", "procedimientos", "perfectamente", "inglés", "pequeño", "alguien",
              "prohibir", "adhesión", "anchura", "guerra", "subrayar", "continuo", "reúnen", "había", "validación", "ejecución"]:
        print(hyphenate_word(w).replace(SHY, "-"), end="  ")
