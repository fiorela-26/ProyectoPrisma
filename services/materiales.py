"""Alta de material de una sesión: validación, hash, subida y creación del job de extracción."""
import hashlib
import json
import os
import tempfile
from pathlib import Path

from services import jobs, storage
from services.supabase_client import get_service_client

_PREVIA_DIR = Path(tempfile.gettempdir()) / "prisma-previas"

# Extensión -> (tipo lógico usado por el extractor, content-type para Storage)
TIPOS_PERMITIDOS = {
    ".pdf": ("pdf", "application/pdf"),
    ".txt": ("texto", "text/plain"),
    ".md": ("texto", "text/markdown"),
    ".doc": ("word", "application/msword"),
    ".docx": ("word", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ".ppt": ("presentacion", "application/vnd.ms-powerpoint"),
    ".pptx": ("presentacion", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    ".xls": ("hoja", "application/vnd.ms-excel"),
    ".xlsx": ("hoja", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ".png": ("imagen", "image/png"),
    ".jpg": ("imagen", "image/jpeg"),
    ".jpeg": ("imagen", "image/jpeg"),
    ".webp": ("imagen", "image/webp"),
    ".mp3": ("audio", "audio/mpeg"),
    ".m4a": ("audio", "audio/mp4"),
    ".wav": ("audio", "audio/wav"),
    ".ogg": ("audio", "audio/ogg"),
    ".mp4": ("video", "video/mp4"),
    ".webm": ("video", "video/webm"),
}


def accept_html() -> str:
    """Valor de accept= del <input type=file>: extensiones y MIME para el diálogo de Windows."""
    extensiones = sorted(TIPOS_PERMITIDOS)
    mimes = sorted({ct for _, ct in TIPOS_PERMITIDOS.values()})
    return ",".join(extensiones + mimes)


class MaterialInvalido(ValueError):
    pass


TIPO_TEMA = "tema"


def titulo_provisional(titulo: str, nombre_archivo: str) -> str:
    """Si el docente no escribe título, se usa el nombre del archivo hasta que la IA proponga el tema."""
    t = (titulo or "").strip()
    return t or os.path.basename(nombre_archivo or "") or "Sesión"


def debe_inferir_titulo(titulo: str) -> bool:
    """True si el título está vacío o es solo el nombre del archivo subido."""
    t = (titulo or "").strip()
    if not t:
        return True
    return os.path.splitext(t)[1].lower() in TIPOS_PERMITIDOS


def sha256_bytes(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def clasificar_archivo(nombre: str) -> tuple[str, str, str]:
    """Devuelve (extensión, tipo lógico, content-type) o lanza MaterialInvalido."""
    ext = os.path.splitext(nombre or "")[1].lower()
    if ext not in TIPOS_PERMITIDOS:
        permitidas = ", ".join(sorted(TIPOS_PERMITIDOS))
        raise MaterialInvalido(f"Tipo de archivo no permitido. Usa: {permitidas}")
    tipo, content_type = TIPOS_PERMITIDOS[ext]
    return ext, tipo, content_type


def docente_es_dueno_de_sesion(sesion_id: str, docente_id: str) -> dict | None:
    """Devuelve la sesión si el docente es dueño del curso; si no, None."""
    db = get_service_client()
    sesion = db.table("sesiones_material").select("*").eq("id", sesion_id).limit(1).execute().data
    if not sesion:
        return None
    if docente_es_dueno(sesion[0]["curso_id"], docente_id):
        return sesion[0]
    return None


def docente_es_dueno(curso_id: str, docente_id: str) -> bool:
    res = (
        get_service_client()
        .table("cursos")
        .select("id")
        .eq("id", curso_id)
        .eq("docente_id", docente_id)
        .limit(1)
        .execute()
    )
    return bool(res.data)


def registrar_material(curso_id: str, titulo: str, nombre_archivo: str, datos: bytes, idioma: str = "es") -> dict:
    """Sube el archivo, crea la sesión en estado 'procesando' y encola el job 'extraer'."""
    if not datos:
        raise MaterialInvalido("El archivo está vacío")
    ext, tipo, content_type = clasificar_archivo(nombre_archivo)
    hash_contenido = sha256_bytes(datos)

    ruta = f"{curso_id}/{hash_contenido}{ext}"
    storage.upload_bytes(ruta, datos, content_type)

    db = get_service_client()
    sesion = (
        db.table("sesiones_material")
        .insert(
            {
                "curso_id": curso_id,
                "titulo": titulo_provisional(titulo, nombre_archivo),
                "archivo_url": ruta,
                "tipo_archivo": tipo,
                "contenido_hash": hash_contenido,
                "idioma_original": idioma,
                "estado": "procesando",
            }
        )
        .execute()
        .data[0]
    )
    job = jobs.crear_job(sesion["id"], "extraer")
    return {"sesion_id": sesion["id"], "job_id": job["id"], "tipo_archivo": tipo, "hash": hash_contenido}


def _nivel_etiqueta(curso_id: str) -> str:
    try:
        from services import cursos as svc_cursos

        nivel = svc_cursos.nivel_de_curso(curso_id) or {}
        return (nivel.get("nivel_educativo_etiqueta") or nivel.get("nivel_educativo") or "").strip()
    except Exception:
        return ""


def _guardar_previa(hash_contenido: str, datos: bytes, meta: dict) -> None:
    _PREVIA_DIR.mkdir(parents=True, exist_ok=True)
    (_PREVIA_DIR / f"{hash_contenido}.bin").write_bytes(datos)
    (_PREVIA_DIR / f"{hash_contenido}.json").write_text(json.dumps(meta), encoding="utf-8")


def _leer_previa(hash_contenido: str) -> tuple[bytes, dict]:
    binario = _PREVIA_DIR / f"{hash_contenido}.bin"
    meta = _PREVIA_DIR / f"{hash_contenido}.json"
    if not binario.is_file() or not meta.is_file():
        raise MaterialInvalido("La vista previa expiró. Vuelve a extraer el archivo.")
    return binario.read_bytes(), json.loads(meta.read_text(encoding="utf-8"))


def previsualizar_material(curso_id: str, titulo: str, nombre_archivo: str, datos: bytes, idioma: str = "es") -> dict:
    """Extrae el texto en local. La subida a Storage ocurre al aprobar la sesión."""
    if not datos:
        raise MaterialInvalido("El archivo está vacío")
    ext, tipo, content_type = clasificar_archivo(nombre_archivo)
    hash_contenido = sha256_bytes(datos)
    ruta = f"{curso_id}/{hash_contenido}{ext}"
    nombre = os.path.basename(nombre_archivo)

    from services import extractor

    try:
        if tipo in ("audio", "video"):
            raise MaterialInvalido("El audio y el video se procesan al crear la sesión, no en la vista previa.")
        texto_crudo = extractor.extraer(datos, tipo, idioma=idioma or "es").texto
    except extractor.ExtraccionNoSoportada as exc:
        raise MaterialInvalido(str(exc)) from exc
    except MaterialInvalido:
        raise
    except Exception as exc:
        raise MaterialInvalido(f"No se pudo extraer el archivo: {exc}") from exc

    texto_crudo = (texto_crudo or "").strip()
    if not texto_crudo:
        raise MaterialInvalido("No se encontró contenido útil sobre el tema. Prueba con otro archivo.")
    fallback_titulo = (titulo or "").strip() or os.path.splitext(nombre)[0].replace("-", " ").replace("_", " ").strip() or "Sesión"
    nivel_etiqueta = _nivel_etiqueta(curso_id)
    preparado = extractor.preparar_clase(
        texto_crudo, idioma or "es", fallback_titulo, nivel_educativo=nivel_etiqueta
    )
    propuesto = (titulo or "").strip() or preparado["titulo"]
    texto = (preparado.get("texto") or "").strip()
    if not texto:
        raise MaterialInvalido("No se pudo armar un resumen del tema. Prueba de nuevo o pega el texto a mano.")
    _guardar_previa(
        hash_contenido,
        datos,
        {"ruta": ruta, "tipo": tipo, "content_type": content_type, "ext": ext, "nombre": nombre, "curso_id": curso_id},
    )
    return {
        "titulo": propuesto,
        "texto": texto,
        "ruta": ruta,
        "hash": hash_contenido,
        "tipo": tipo,
        "idioma": idioma or "es",
        "nombre": nombre,
    }


def previsualizar_desde_titulo(curso_id: str, titulo: str, idioma: str = "es") -> dict:
    """Genera la clase a partir del título, sin archivo."""
    tema = (titulo or "").strip()
    if len(tema) < 3:
        raise MaterialInvalido("Escribe un título de al menos 3 caracteres o sube un archivo.")
    from services import extractor

    hash_contenido = sha256_bytes(f"{curso_id}|tema|{tema}|{idioma or 'es'}".encode("utf-8"))
    ruta = f"{curso_id}/tema-{hash_contenido}"
    preparado = extractor.generar_clase_desde_titulo(tema, idioma or "es", _nivel_etiqueta(curso_id))
    propuesto = preparado.get("titulo") or tema
    texto = (preparado.get("texto") or "").strip()
    if not texto:
        raise MaterialInvalido("No se pudo armar la clase a partir del título. Prueba de nuevo o pega el texto a mano.")
    _guardar_previa(
        hash_contenido,
        b"",
        {"ruta": ruta, "tipo": TIPO_TEMA, "content_type": "text/plain", "ext": "", "nombre": "Generada desde el título", "curso_id": curso_id},
    )
    return {
        "titulo": propuesto,
        "texto": texto,
        "ruta": ruta,
        "hash": hash_contenido,
        "tipo": TIPO_TEMA,
        "idioma": idioma or "es",
        "nombre": "Generada desde el título",
    }


def confirmar_material(
    curso_id: str,
    titulo: str,
    texto: str,
    ruta: str,
    hash_contenido: str,
    tipo: str,
    idioma: str = "es",
) -> dict:
    """Crea la sesión en revisión con el texto que el docente ya vio y pudo editar."""
    if not ruta.startswith(f"{curso_id}/"):
        raise MaterialInvalido("La vista previa no corresponde a este curso.")
    texto = (texto or "").strip()
    if not texto:
        raise MaterialInvalido("El texto extraído está vacío. Edítalo o elige otro archivo.")
    tipos_ok = {t for t, _ in TIPOS_PERMITIDOS.values()} | {TIPO_TEMA}
    if tipo not in tipos_ok:
        raise MaterialInvalido("Tipo de archivo no permitido.")
    datos, meta = _leer_previa(hash_contenido)
    if meta.get("curso_id") != curso_id:
        raise MaterialInvalido("La vista previa no corresponde a este curso.")
    archivo_url = None
    if tipo != TIPO_TEMA:
        try:
            storage.upload_bytes(ruta, datos, meta.get("content_type") or "application/octet-stream")
        except Exception as exc:
            raise MaterialInvalido(f"No se pudo guardar el archivo: {exc}") from exc
        archivo_url = ruta
    elif not (titulo or "").strip():
        raise MaterialInvalido("El título de la sesión es obligatorio.")
    db = get_service_client()
    sesion = (
        db.table("sesiones_material")
        .insert(
            {
                "curso_id": curso_id,
                "titulo": titulo_provisional(titulo, os.path.basename(ruta) if archivo_url else ""),
                "archivo_url": archivo_url,
                "tipo_archivo": tipo,
                "contenido_hash": hash_contenido,
                "idioma_original": idioma or "es",
                "texto_extraido": texto,
                "estado": "revision",
            }
        )
        .execute()
        .data[0]
    )
    from services import package_builder

    try:
        package_builder.guardar_paquete(
            sesion["id"],
            "alto_contraste",
            package_builder.generar("alto_contraste", texto, hash_contenido or "", idioma or "es"),
        )
    except Exception:
        pass
    from services import imagen_educativa, mediacion

    imagen_educativa.generar_en_fondo(sesion)
    mediacion.generar_en_fondo(sesion)
    return sesion
