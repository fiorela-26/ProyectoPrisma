"""Cola de jobs: creación, ejecución, reintentos y worker en segundo plano."""
import logging
import threading
import time
from services.supabase_client import get_service_client

log = logging.getLogger(__name__)

ESTADOS_ACTIVOS = ("queued", "running")
MAX_INTENTOS = 3
HILOS_WORKER = 2

_iniciado = False
_parar = threading.Event()
_lock_inicio = threading.Lock()


def crear_job(sesion_id: str, tipo: str, formato: str | None = None) -> dict:
    """Crea un job. Idempotente: si ya hay uno activo para la misma sesión/tipo/formato lo devuelve."""
    db = get_service_client()
    consulta = (
        db.table("jobs")
        .select("*")
        .eq("sesion_id", sesion_id)
        .eq("tipo", tipo)
        .in_("estado", list(ESTADOS_ACTIVOS))
    )
    consulta = consulta.eq("formato", formato) if formato else consulta.is_("formato", "null")
    existentes = consulta.limit(1).execute().data
    if existentes:
        return existentes[0]

    fila = {"sesion_id": sesion_id, "tipo": tipo, "formato": formato, "estado": "queued"}
    return db.table("jobs").insert(fila).execute().data[0]


def obtener_job(job_id: str) -> dict | None:
    db = get_service_client()
    res = db.table("jobs").select("*").eq("id", job_id).limit(1).execute()
    return res.data[0] if res.data else None


def jobs_en_cola(limite: int = 10) -> list[dict]:
    db = get_service_client()
    return db.table("jobs").select("*").eq("estado", "queued").order("creado_en").limit(limite).execute().data


# ---------------------------------------------------------------------------
# Ejecución
# ---------------------------------------------------------------------------
def _actualizar_job(job_id: str, **campos) -> None:
    get_service_client().table("jobs").update(campos).eq("id", job_id).execute()


def ejecutar_job(job: dict) -> dict:
    """Ejecuta un job de forma síncrona y deja su estado final en la tabla. Devuelve el job actualizado."""
    db = get_service_client()
    intentos = (job.get("intentos") or 0) + 1
    _actualizar_job(job["id"], estado="running", iniciado_en=_ahora(), intentos=intentos, error=None)
    try:
        if job["tipo"] == "extraer":
            _job_extraer(job)
        elif job["tipo"] == "formato":
            _job_formato(job)
        else:
            raise ValueError(f"Tipo de job desconocido: {job['tipo']}")
        _actualizar_job(job["id"], estado="done", progreso=100, terminado_en=_ahora())
    except Exception as exc:  # noqa: BLE001 - el error se persiste en el job
        mensaje = str(exc)[:2000]
        if _es_reintentable(exc) and intentos < MAX_INTENTOS:
            espera = min(2 ** intentos, 30)
            log.warning("Job %s falló (intento %s/%s), reencola en %ss: %s", job["id"], intentos, MAX_INTENTOS, espera, mensaje)
            time.sleep(espera)
            _actualizar_job(job["id"], estado="queued", error=mensaje)
        else:
            _actualizar_job(job["id"], estado="failed", error=mensaje, terminado_en=_ahora())
            if job.get("tipo") == "extraer" and job.get("sesion_id"):
                db.table("sesiones_material").update({"estado": "error"}).eq("id", job["sesion_id"]).execute()
    return obtener_job(job["id"])


def _es_reintentable(exc: Exception) -> bool:
    from services.ai_router import CuotaAgotada
    from services.extractor import ExtraccionNoSoportada
    from services.package_builder import FormatoDesconocido
    from services.transcriber import FfmpegNoDisponible

    return not isinstance(
        exc, (FfmpegNoDisponible, ExtraccionNoSoportada, ValueError, CuotaAgotada, FormatoDesconocido)
    )


def recuperar_colgados() -> int:
    """Los jobs que quedaron en running (p. ej. Render se durmió) vuelven a queued."""
    db = get_service_client()
    res = db.table("jobs").update({"estado": "queued", "error": "recuperado tras reinicio"}).eq("estado", "running").execute()
    n = len(res.data or [])
    if n:
        log.info("Recuperados %s jobs colgados", n)
    return n


def iniciar_worker(hilos: int = HILOS_WORKER) -> None:
    global _iniciado
    with _lock_inicio:
        if _iniciado:
            return
        recuperar_colgados()
        _parar.clear()
        # Hilos daemon: al salir el proceso principal no queda colgado (scripts de prueba).
        for i in range(hilos):
            threading.Thread(target=_bucle, name=f"jobs-worker-{i}", daemon=True).start()
        _iniciado = True
        log.info("Worker de jobs iniciado (%s hilos)", hilos)


def _bucle() -> None:
    while not _parar.is_set():
        try:
            pendientes = jobs_en_cola(limite=1)
            if not pendientes:
                _parar.wait(2)
                continue
            ejecutar_job(pendientes[0])
        except Exception:
            log.exception("Worker: error al tomar un job")
            from services.supabase_client import invalidar_clientes

            invalidar_clientes()
            _parar.wait(5)


def docente_puede_ver_job(job_id: str, docente_id: str) -> dict | None:
    job = obtener_job(job_id)
    if not job or not job.get("sesion_id"):
        return None
    db = get_service_client()
    sesion = db.table("sesiones_material").select("curso_id").eq("id", job["sesion_id"]).limit(1).execute().data
    if not sesion:
        return None
    curso = db.table("cursos").select("id").eq("id", sesion[0]["curso_id"]).eq("docente_id", docente_id).limit(1).execute().data
    return job if curso else None


def _job_extraer(job: dict) -> None:
    from pathlib import PurePosixPath

    from services import extractor, materiales as mats, storage, transcriber

    db = get_service_client()
    sesion = db.table("sesiones_material").select("*").eq("id", job["sesion_id"]).limit(1).execute().data
    if not sesion:
        raise ValueError("La sesión del job ya no existe")
    sesion = sesion[0]

    _actualizar_job(job["id"], progreso=10)
    datos = storage.download_bytes(sesion["archivo_url"])
    _actualizar_job(job["id"], progreso=30)

    tipo = sesion["tipo_archivo"]
    idioma = sesion.get("idioma_original") or "es"
    if tipo in ("audio", "video"):
        resultado = transcriber.transcribir(datos, sesion["archivo_url"], idioma=idioma)
        vtt_ruta = str(PurePosixPath(sesion["archivo_url"]).with_suffix(".vtt"))
        storage.upload_bytes(vtt_ruta, resultado.vtt.encode("utf-8"), "text/vtt")
        metodo = f"whisper:{resultado.modelo_usado}"
        texto_crudo = resultado.texto
    else:
        extraido = extractor.extraer(datos, tipo, idioma=idioma)
        metodo = extraido.metodo + (f":{extraido.modelo_usado}" if extraido.modelo_usado else "")
        texto_crudo = extraido.texto
    texto = extractor.depurar_contenido(texto_crudo, idioma)

    _actualizar_job(job["id"], progreso=90)
    cambios = {"texto_extraido": texto, "estado": "revision"}
    if mats.debe_inferir_titulo(sesion.get("titulo") or ""):
        try:
            cambios["titulo"] = extractor.proponer_titulo(texto, sesion.get("titulo") or "Sesión")
        except Exception:
            log.exception("No se pudo proponer título para %s", sesion["id"])
    db.table("sesiones_material").update(cambios).eq("id", sesion["id"]).execute()
    _actualizar_job(job["id"], formato=metodo)
    # Alto contraste no gasta IA: se materializa al terminar la extracción.
    from services import package_builder

    try:
        package_builder.guardar_paquete(
            sesion["id"],
            "alto_contraste",
            package_builder.generar("alto_contraste", texto, sesion.get("contenido_hash") or "", idioma),
        )
    except Exception:
        log.exception("No se pudo guardar alto_contraste para %s", sesion["id"])
    from services import imagen_educativa, mediacion

    actualizada = {**sesion, **cambios}
    imagen_educativa.generar_en_fondo(actualizada)
    mediacion.generar_en_fondo(actualizada)


def _job_formato(job: dict) -> None:
    from services import package_builder

    formato = job.get("formato")
    if not formato:
        raise package_builder.FormatoDesconocido("El job de formato no indica qué formato generar")
    db = get_service_client()
    sesion = db.table("sesiones_material").select("*").eq("id", job["sesion_id"]).limit(1).execute().data
    if not sesion:
        raise ValueError("La sesión del job ya no existe")
    sesion = sesion[0]
    texto = (sesion.get("texto_extraido") or "").strip()
    if not texto:
        raise ValueError("Aún no hay texto extraído; espera a que termine la extracción")
    _actualizar_job(job["id"], progreso=40)
    resultado = package_builder.generar(
        formato, texto, sesion.get("contenido_hash") or "", sesion.get("idioma_original") or "es"
    )
    _actualizar_job(job["id"], progreso=80)
    package_builder.guardar_paquete(sesion["id"], formato, resultado)
    _actualizar_job(job["id"], formato=f"{formato}:{resultado.get('modelo_usado') or 'local'}")


def _ahora() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
