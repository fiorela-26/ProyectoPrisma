"""Caché de resultados de IA. Solo contenido generado, nunca datos personales.

Clave = SHA-256(hash del archivo + formato + idioma + versión del prompt).
Si cambia el prompt, cambia VERSION_* y las entradas viejas dejan de usarse.
No cruza docentes: la clave no incluye usuario, solo el material y el tipo de salida.
"""
import hashlib
import logging

from services.supabase_client import get_service_client

log = logging.getLogger(__name__)

VERSION_OCR = "ocr-v1"
VERSION_STT = "stt-v1"


def clave(hash_contenido: str, formato: str, idioma: str, version_prompt: str) -> str:
    crudo = f"{hash_contenido}|{formato}|{idioma}|{version_prompt}"
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()


def buscar(hash_contenido: str, formato: str, idioma: str, version_prompt: str) -> dict | None:
    k = clave(hash_contenido, formato, idioma, version_prompt)
    try:
        res = get_service_client().table("cache_ia").select("contenido").eq("clave", k).limit(1).execute()
    except Exception as exc:  # noqa: BLE001
        log.warning("Caché IA no disponible (lectura): %s", exc)
        return None
    if res.data:
        log.info("Caché IA hit formato=%s", formato)
        return res.data[0]["contenido"]
    return None


def guardar(hash_contenido: str, formato: str, idioma: str, version_prompt: str, contenido: dict) -> None:
    k = clave(hash_contenido, formato, idioma, version_prompt)
    try:
        get_service_client().table("cache_ia").upsert(
            {"clave": k, "formato": formato, "contenido": contenido}
        ).execute()
    except Exception as exc:  # noqa: BLE001
        log.warning("Caché IA no disponible (escritura): %s", exc)
