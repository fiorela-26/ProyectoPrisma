"""Construye subtítulos WebVTT a partir de segmentos con marcas de tiempo.

No dependemos de que Whisper/Groq devuelva un .vtt: siempre lo armamos aquí.
"""
from dataclasses import dataclass


@dataclass
class Segmento:
    start: float
    end: float
    text: str


def _marca(segundos: float) -> str:
    if segundos < 0:
        segundos = 0
    total_ms = int(round(segundos * 1000))
    horas, resto = divmod(total_ms, 3_600_000)
    minutos, resto = divmod(resto, 60_000)
    segs, ms = divmod(resto, 1000)
    return f"{horas:02d}:{minutos:02d}:{segs:02d}.{ms:03d}"


def desde_segmentos(segmentos: list[Segmento]) -> str:
    """Devuelve un .vtt válido. Segmentos vacíos se omiten; si no hay ninguno, el archivo queda vacío salvo el encabezado."""
    lineas = ["WEBVTT", ""]
    cue = 1
    for seg in segmentos:
        texto = " ".join((seg.text or "").split())
        if not texto:
            continue
        fin = seg.end if seg.end > seg.start else seg.start + 0.5
        lineas.append(str(cue))
        lineas.append(f"{_marca(seg.start)} --> {_marca(fin)}")
        lineas.append(texto)
        lineas.append("")
        cue += 1
    return "\n".join(lineas)


def texto_corrido(segmentos: list[Segmento]) -> str:
    partes = [" ".join((s.text or "").split()) for s in segmentos]
    return "\n".join(p for p in partes if p)
