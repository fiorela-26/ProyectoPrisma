"""Punto único de acceso a los modelos de IA.

Reglas:
- Los nombres de modelo vienen de config/.env, nunca del código.
- Cada llamada recibe una cadena de modelos: si el primero devuelve 429 (cuota agotada)
  o un error transitorio, se intenta con el siguiente.
- Se devuelve siempre el modelo que respondió, para guardarlo en `modelo_usado`.
"""
import logging
import time
from dataclasses import dataclass
from functools import lru_cache

from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from groq import Groq
from groq import APIStatusError as GroqAPIError

from config import settings

log = logging.getLogger(__name__)

# 429: cuota agotada · 404: modelo retirado para la cuenta · 500/503: error o saturación transitoria
CODIGOS_REINTENTABLES = {404, 429, 500, 503}
llamadas: dict[str, int] = {}
errores: dict[str, int] = {}


def _intento(modelo: str) -> None:
    llamadas[modelo] = llamadas.get(modelo, 0) + 1


def _error(codigo: int | None) -> None:
    if codigo is None:
        return
    clave = str(codigo)
    errores[clave] = errores.get(clave, 0) + 1


def resumen_uso() -> dict:
    return {"llamadas": dict(llamadas), "errores": dict(errores)}


class CuotaAgotada(RuntimeError):
    """Todos los modelos de la cadena fallaron por cuota o errores transitorios."""


@dataclass
class RespuestaIA:
    texto: str
    modelo: str


@dataclass
class SegmentoSTT:
    start: float
    end: float
    text: str


@dataclass
class RespuestaSTT:
    texto: str
    modelo: str
    segmentos: list[SegmentoSTT]


@lru_cache(maxsize=1)
def _gemini() -> genai.Client:
    return genai.Client(api_key=settings.GEMINI_API_KEY)


@lru_cache(maxsize=1)
def _groq() -> Groq:
    return Groq(api_key=settings.GROQ_API_KEY)


def _codigo_http(exc: Exception) -> int | None:
    return getattr(exc, "code", None) or getattr(exc, "status_code", None)


def gemini_generar(partes: list, cadena: tuple[str, ...] | None = None, temperatura: float = 0.1) -> RespuestaIA:
    """Genera texto con Gemini probando cada modelo de la cadena hasta que uno responda.

    `partes` es una lista de str y/o google.genai.types.Part (por ejemplo PDF o imágenes).
    """
    cadena = cadena or (settings.MODEL_VISION, settings.MODEL_LITE)
    ultimo_error: Exception | None = None
    for modelo in cadena:
        if not modelo:
            continue
        _intento(modelo)
        try:
            res = _gemini().models.generate_content(
                model=modelo,
                contents=partes,
                config=genai_types.GenerateContentConfig(temperature=temperatura),
            )
            return RespuestaIA(texto=res.text or "", modelo=modelo)
        except genai_errors.APIError as exc:
            ultimo_error = exc
            codigo = _codigo_http(exc)
            if codigo in CODIGOS_REINTENTABLES:
                _error(codigo)
                log.warning("Gemini %s devolvió %s; probando siguiente modelo", modelo, codigo)
                time.sleep(1)
                continue
            raise
    raise CuotaAgotada(f"Sin cuota en Gemini para {cadena}: {ultimo_error}")


def parte_binaria(datos: bytes, mime_type: str) -> genai_types.Part:
    return genai_types.Part.from_bytes(data=datos, mime_type=mime_type)


def _campo(obj, nombre: str, default=""):
    """Groq a veces devuelve segmentos como dict y a veces como objeto."""
    if isinstance(obj, dict):
        return obj.get(nombre, default)
    return getattr(obj, nombre, default)


def _segmento_stt(s) -> SegmentoSTT:
    return SegmentoSTT(
        start=float(_campo(s, "start", 0) or 0),
        end=float(_campo(s, "end", 0) or 0),
        text=str(_campo(s, "text", "") or ""),
    )


def groq_transcribir(ruta: Path, cadena: tuple[str, ...] | None = None) -> RespuestaSTT:
    """Transcribe un archivo de audio con Groq Whisper. Pide verbose_json con segmentos."""
    cadena = cadena or (settings.MODEL_STT, settings.MODEL_STT_FALLBACK)
    audio = ruta.read_bytes()
    ultimo_error: Exception | None = None
    for modelo in cadena:
        if not modelo:
            continue
        _intento(modelo)
        try:
            res = _groq().audio.transcriptions.create(
                file=(ruta.name, audio),
                model=modelo,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )
            segmentos = [_segmento_stt(s) for s in (getattr(res, "segments", None) or [])]
            return RespuestaSTT(texto=res.text or "", modelo=modelo, segmentos=segmentos)
        except GroqAPIError as exc:
            ultimo_error = exc
            codigo = _codigo_http(exc)
            if codigo in CODIGOS_REINTENTABLES:
                _error(codigo)
                log.warning("Groq STT %s devolvió %s; probando siguiente modelo", modelo, codigo)
                time.sleep(1)
                continue
            raise
    raise CuotaAgotada(f"Sin cuota en Groq STT para {cadena}: {ultimo_error}")


def groq_texto(mensajes: list[dict], cadena: tuple[str, ...] | None = None, temperatura: float = 0.1, json_mode: bool = True) -> RespuestaIA:
    """Chat de texto. Cadena: modelo primario Groq → respaldo Groq → Gemini lite."""
    cadena = cadena or (settings.MODEL_TEXT_PRIMARY, settings.MODEL_TEXT_FALLBACK, settings.MODEL_LITE)
    ultimo_error: Exception | None = None
    for modelo in cadena:
        if not modelo:
            continue
        _intento(modelo)
        try:
            if modelo.startswith("gemini"):
                partes = []
                for m in mensajes:
                    partes.append(f"{m.get('role', 'user')}: {m.get('content', '')}")
                return gemini_generar(["\n\n".join(partes)], cadena=(modelo,), temperatura=temperatura)
            kwargs = {
                "model": modelo,
                "messages": mensajes,
                "temperature": temperatura,
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            res = _groq().chat.completions.create(**kwargs)
            return RespuestaIA(texto=(res.choices[0].message.content or ""), modelo=modelo)
        except GroqAPIError as exc:
            ultimo_error = exc
            codigo = _codigo_http(exc)
            if codigo in CODIGOS_REINTENTABLES:
                _error(codigo)
                log.warning("Groq texto %s devolvió %s; probando siguiente modelo", modelo, codigo)
                time.sleep(1)
                continue
            raise
        except genai_errors.APIError as exc:
            ultimo_error = exc
            codigo = _codigo_http(exc)
            if codigo in CODIGOS_REINTENTABLES:
                _error(codigo)
                log.warning("Gemini texto %s devolvió %s; probando siguiente modelo", modelo, codigo)
                time.sleep(1)
                continue
            raise
    raise CuotaAgotada(f"Sin cuota de texto para {cadena}: {ultimo_error}")


def groq_texto_stream(mensajes: list[dict], cadena: tuple[str, ...] | None = None, temperatura: float = 0.3):
    """Genera texto en streaming. Primero el modelo de chat, si hay 429 pasa a MODEL_LITE.

    Produce tuplas ('modelo', nombre) y luego ('delta', fragmento).
    """
    cadena = cadena or (settings.MODEL_TEXT_PRIMARY, settings.MODEL_LITE)
    ultimo_error: Exception | None = None
    for modelo in cadena:
        if not modelo:
            continue
        _intento(modelo)
        try:
            if modelo.startswith("gemini"):
                partes = [f"{m.get('role', 'user')}: {m.get('content', '')}" for m in mensajes]
                res = gemini_generar(["\n\n".join(partes)], cadena=(modelo,), temperatura=temperatura)
                yield ("modelo", res.modelo)
                yield ("delta", res.texto)
                return
            stream = _groq().chat.completions.create(
                model=modelo,
                messages=mensajes,
                temperature=temperatura,
                stream=True,
            )
            yield ("modelo", modelo)
            for chunk in stream:
                delta = ""
                if chunk.choices:
                    delta = chunk.choices[0].delta.content or ""
                if delta:
                    yield ("delta", delta)
            return
        except GroqAPIError as exc:
            ultimo_error = exc
            codigo = _codigo_http(exc)
            if codigo in CODIGOS_REINTENTABLES:
                _error(codigo)
                log.warning("Groq stream %s devolvió %s; probando siguiente modelo", modelo, codigo)
                time.sleep(1)
                continue
            raise
        except genai_errors.APIError as exc:
            ultimo_error = exc
            codigo = _codigo_http(exc)
            if codigo in CODIGOS_REINTENTABLES:
                _error(codigo)
                log.warning("Gemini stream %s devolvió %s; probando siguiente modelo", modelo, codigo)
                time.sleep(1)
                continue
            raise
    raise CuotaAgotada(f"Sin cuota de chat para {cadena}: {ultimo_error}")
