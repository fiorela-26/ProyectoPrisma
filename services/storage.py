"""Acceso a Supabase Storage. Siempre desde el servidor con la clave de servicio.

El bucket es privado: el navegador nunca recibe la ruta interna, solo URLs firmadas
con vencimiento que genera el backend cuando hacen falta.
"""
from config import settings
from services.supabase_client import get_service_client


def ensure_bucket() -> None:
    client = get_service_client()
    existentes = {b.name for b in client.storage.list_buckets()}
    if settings.STORAGE_BUCKET not in existentes:
        client.storage.create_bucket(
            settings.STORAGE_BUCKET,
            options={"public": False, "file_size_limit": settings.MAX_UPLOAD_MB * 1024 * 1024},
        )


def upload_bytes(ruta: str, datos: bytes, content_type: str) -> str:
    """Sube el archivo y devuelve la ruta interna. Si ya existe (mismo hash) lo sobrescribe."""
    client = get_service_client()
    client.storage.from_(settings.STORAGE_BUCKET).upload(
        ruta, datos, {"content-type": content_type, "upsert": "true"}
    )
    return ruta


def signed_url(ruta: str, ttl: int | None = None) -> str:
    client = get_service_client()
    res = client.storage.from_(settings.STORAGE_BUCKET).create_signed_url(
        ruta, ttl or settings.SIGNED_URL_TTL
    )
    return res["signedURL"]


def download_bytes(ruta: str) -> bytes:
    client = get_service_client()
    return client.storage.from_(settings.STORAGE_BUCKET).download(ruta)
