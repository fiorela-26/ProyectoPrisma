"""Transcripción de audio y video: ffmpeg (local) + Groq Whisper.

1. Extrae audio a mono 16 kHz.
2. Si el WAV supera el límite de subida del tier gratuito, lo trocea con solape.
3. Llama a MODEL_STT pidiendo verbose_json (segmentos con marcas de tiempo).
4. Arma el .vtt con services.vtt; no usa un VTT que venga de la API.
"""
import hashlib
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from services import ai_router, cache_ia
from services.vtt import Segmento, desde_segmentos, texto_corrido

log = logging.getLogger(__name__)

# Límite práctico de Groq (25 MB). 16 kHz mono 16-bit ≈ 1.92 MB/min → 10 min ≈ 19 MB.
MAX_TROZO_SEGUNDOS = 600
SOLAPE_SEGUNDOS = 2
SAMPLE_RATE = 16_000
BYTES_POR_SEGUNDO = SAMPLE_RATE * 2  # PCM s16le mono


class FfmpegNoDisponible(RuntimeError):
    pass


@dataclass
class ResultadoTranscripcion:
    texto: str
    vtt: str
    modelo_usado: str
    segmentos: int


def ffmpeg_disponible() -> bool:
    return shutil.which("ffmpeg") is not None


def transcribir(datos: bytes, nombre: str = "entrada", idioma: str = "es") -> ResultadoTranscripcion:
    h = hashlib.sha256(datos).hexdigest()
    hit = cache_ia.buscar(h, "stt", idioma, cache_ia.VERSION_STT)
    if hit and hit.get("texto") is not None:
        return ResultadoTranscripcion(
            texto=hit["texto"],
            vtt=hit.get("vtt") or "",
            modelo_usado=hit.get("modelo") or "cache",
            segmentos=hit.get("segmentos") or 0,
        )

    if not ffmpeg_disponible():
        raise FfmpegNoDisponible(
            "ffmpeg no está instalado. En Windows: winget install Gyan.FFmpeg "
            "(cierra y abre la terminal después). En el Dockerfile de producción sí se instala."
        )
    with tempfile.TemporaryDirectory(prefix="stt-") as tmp:
        tmp = Path(tmp)
        origen = tmp / (nombre if Path(nombre).suffix else "entrada.bin")
        origen.write_bytes(datos)
        wav = tmp / "audio.wav"
        _a_wav_mono(origen, wav)
        trozos = _trocear(wav, tmp)
        segmentos: list[Segmento] = []
        modelo = ""
        for offset, trozo in trozos:
            res = ai_router.groq_transcribir(trozo)
            modelo = res.modelo
            for seg in res.segmentos:
                segmentos.append(Segmento(start=seg.start + offset, end=seg.end + offset, text=seg.text))
        segmentos = _fusionar_solape(segmentos)
        resultado = ResultadoTranscripcion(
            texto=texto_corrido(segmentos),
            vtt=desde_segmentos(segmentos),
            modelo_usado=modelo,
            segmentos=len(segmentos),
        )
        cache_ia.guardar(
            h, "stt", idioma, cache_ia.VERSION_STT,
            {"texto": resultado.texto, "vtt": resultado.vtt, "modelo": resultado.modelo_usado, "segmentos": resultado.segmentos},
        )
        return resultado


def _a_wav_mono(origen: Path, destino: Path) -> None:
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(origen),
        "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le",
        str(destino),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not destino.exists():
        detalle = (proc.stderr or proc.stdout or "sin detalle").strip()[:500]
        raise RuntimeError(f"ffmpeg no pudo extraer el audio: {detalle}")


def _duracion_wav(ruta: Path) -> float:
    # Encabezado WAV estándar: bytes 40-43 = tamaño de datos (little-endian).
    datos = ruta.read_bytes()
    if len(datos) < 44 or datos[0:4] != b"RIFF":
        raise RuntimeError("ffmpeg no produjo un WAV válido")
    tam_datos = int.from_bytes(datos[40:44], "little")
    return tam_datos / BYTES_POR_SEGUNDO


def _trocear(wav: Path, tmp: Path) -> list[tuple[float, Path]]:
    """Lista de (offset_en_segundos, ruta). Un solo trozo si cabe entero."""
    duracion = _duracion_wav(wav)
    if duracion <= MAX_TROZO_SEGUNDOS:
        return [(0.0, wav)]
    trozos = []
    inicio = 0.0
    n = 0
    while inicio < duracion:
        n += 1
        destino = tmp / f"trozo_{n:03d}.wav"
        largo = min(MAX_TROZO_SEGUNDOS, duracion - inicio)
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{inicio:.3f}", "-t", f"{largo:.3f}",
            "-i", str(wav), "-c", "copy", str(destino),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0 or not destino.exists():
            raise RuntimeError(f"ffmpeg no pudo trocear el audio: {(proc.stderr or '')[:300]}")
        trozos.append((inicio, destino))
        if inicio + largo >= duracion:
            break
        inicio = inicio + MAX_TROZO_SEGUNDOS - SOLAPE_SEGUNDOS
    return trozos


def _fusionar_solape(segmentos: list[Segmento]) -> list[Segmento]:
    """Quita duplicados del solape: si dos segmentos empiezan casi iguales, se queda el primero."""
    if not segmentos:
        return []
    ordenados = sorted(segmentos, key=lambda s: (s.start, s.end))
    fusionados = [ordenados[0]]
    for seg in ordenados[1:]:
        anterior = fusionados[-1]
        if abs(seg.start - anterior.start) < 0.4 and _parecido(seg.text, anterior.text):
            continue
        if seg.start < anterior.end - 0.3 and _parecido(seg.text, anterior.text):
            continue
        fusionados.append(seg)
    return fusionados


def _parecido(a: str, b: str) -> bool:
    na, nb = " ".join(a.lower().split()), " ".join(b.lower().split())
    return bool(na) and na == nb
