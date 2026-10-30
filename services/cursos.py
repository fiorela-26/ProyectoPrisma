"""CRUD de cursos, inscripciones y publicación de sesiones."""
from services import dua
from services.supabase_client import get_service_client

PREFERENCIAS = list(dua.CODIGOS)

# Código CINE (UNESCO) + etiqueta oficial. El formulario guarda ambos en cursos.
NIVELES_CINE = (
    {"codigo": "cine_1_inicial", "etiqueta": "CINE 1 - Primaria inicial (6 a 8 años)"},
    {"codigo": "cine_1_avanzada", "etiqueta": "CINE 1 - Primaria avanzada (9 a 11 años)"},
    {"codigo": "cine_2", "etiqueta": "CINE 2 - Secundaria inferior / Ciclo básico (12 a 14 años)"},
    {"codigo": "cine_3", "etiqueta": "CINE 3 - Secundaria superior / Bachillerato (15 a 17 años)"},
    {"codigo": "cine_6", "etiqueta": "CINE 6+ - Educación Terciaria / Superior (18+ años)"},
)
NIVELES_POR_CODIGO = {n["codigo"]: n["etiqueta"] for n in NIVELES_CINE}


def resolver_nivel(codigo: str) -> tuple[str, str]:
    clave = (codigo or "").strip()
    etiqueta = NIVELES_POR_CODIGO.get(clave)
    if not etiqueta:
        raise ValueError("Elige un nivel educativo CINE")
    return clave, etiqueta


def nivel_de_curso(curso_id: str) -> dict:
    filas = (
        get_service_client()
        .table("cursos")
        .select("nivel_educativo, nivel_educativo_etiqueta")
        .eq("id", curso_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    return filas[0] if filas else {}


def listar_cursos(docente_id: str) -> list[dict]:
    cursos = (
        get_service_client()
        .table("cursos")
        .select("*")
        .eq("docente_id", docente_id)
        .order("creado_en", desc=True)
        .execute()
        .data
        or []
    )
    for c in cursos:
        c["n_sesiones"] = len(sesiones_de_curso(c["id"]))
        c["n_estudiantes"] = len(inscripciones(c["id"]))
    return cursos


def crear_curso(docente_id: str, nombre: str, descripcion: str = "", nivel_educativo: str = "") -> dict:
    nombre = (nombre or "").strip()
    if not nombre:
        raise ValueError("El nombre del curso es obligatorio")
    codigo, etiqueta = resolver_nivel(nivel_educativo)
    fila = {
        "docente_id": docente_id,
        "nombre_curso": nombre,
        "descripcion": descripcion.strip() or None,
        "nivel_educativo": codigo,
        "nivel_educativo_etiqueta": etiqueta,
    }
    try:
        return get_service_client().table("cursos").insert(fila).execute().data[0]
    except Exception as exc:
        if "nivel_educativo" in str(exc):
            raise ValueError(
                "Falta agregar en Supabase las columnas CINE. Ejecuta supabase/003_cine.sql en el editor SQL."
            ) from exc
        raise


def sesiones_de_curso(curso_id: str) -> list[dict]:
    return (
        get_service_client()
        .table("sesiones_material")
        .select("id, titulo, estado, tipo_archivo, creado_en, texto_extraido")
        .eq("curso_id", curso_id)
        .order("creado_en", desc=True)
        .execute()
        .data
        or []
    )


def jobs_de_sesion(sesion_id: str) -> list[dict]:
    return (
        get_service_client()
        .table("jobs")
        .select("id, tipo, formato, estado, progreso, error, intentos, creado_en")
        .eq("sesion_id", sesion_id)
        .order("creado_en", desc=True)
        .execute()
        .data
        or []
    )


def paquetes_de_sesion(sesion_id: str) -> list[dict]:
    return (
        get_service_client()
        .table("paquetes_formato")
        .select("*")
        .eq("sesion_id", sesion_id)
        .execute()
        .data
        or []
    )


def publicar_sesion(sesion_id: str) -> dict:
    db = get_service_client()
    sesion = db.table("sesiones_material").select("*").eq("id", sesion_id).limit(1).execute().data
    if not sesion:
        raise ValueError("La sesión no existe")
    if sesion[0].get("estado") not in ("revision", "publicado"):
        raise ValueError("Solo se puede publicar una sesión en revisión")
    return db.table("sesiones_material").update({"estado": "publicado"}).eq("id", sesion_id).execute().data[0]


def guardar_edicion(sesion_id: str, formato: str, contenido: dict) -> dict:
    db = get_service_client()
    existente = (
        db.table("paquetes_formato")
        .select("id, version")
        .eq("sesion_id", sesion_id)
        .eq("formato", formato)
        .limit(1)
        .execute()
        .data
    )
    if not existente:
        raise ValueError("Ese formato aún no está generado")
    version = (existente[0].get("version") or 1) + 1
    return (
        db.table("paquetes_formato")
        .update({"contenido": contenido, "editado_por_docente": True, "version": version})
        .eq("id", existente[0]["id"])
        .execute()
        .data[0]
    )


def reintentar_job(job_id: str) -> dict:
    db = get_service_client()
    job = db.table("jobs").select("*").eq("id", job_id).limit(1).execute().data
    if not job:
        raise ValueError("Job no encontrado")
    if job[0]["estado"] != "failed":
        raise ValueError("Solo se reintentan jobs fallidos")
    return db.table("jobs").update({"estado": "queued", "error": None, "progreso": 0}).eq("id", job_id).execute().data[0]


def inscripciones(curso_id: str) -> list[dict]:
    db = get_service_client()
    filas = (
        db.table("inscripciones_curso")
        .select("id, estudiante_id, preferencias, idioma_preferido")
        .eq("curso_id", curso_id)
        .execute()
        .data
        or []
    )
    if not filas:
        return []
    ids = [f["estudiante_id"] for f in filas]
    perfiles = {p["id"]: p for p in db.table("perfiles").select("id, nombre, rol").in_("id", ids).execute().data or []}
    out = []
    for f in filas:
        p = perfiles.get(f["estudiante_id"]) or {}
        out.append(
            {
                **f,
                "nombre": p.get("nombre") or "Sin nombre",
                "preferencias": dua.normalizar_preferencias(f.get("preferencias")),
                "idioma_preferido": dua.normalizar_idioma(f.get("idioma_preferido") or "es"),
            }
        )
    return out


def inscribir(
    curso_id: str,
    email: str,
    nombre: str = "",
    preferencias: list[str] | None = None,
    idioma: str = "es",
) -> dict:
    email = (email or "").strip().lower()
    if "@" not in email:
        raise ValueError("Indica un correo válido")
    db = get_service_client()
    user = _usuario_por_email(email)
    if not user or not getattr(user, "id", None):
        admin = db.auth.admin
        creado = admin.create_user(
            {
                "email": email,
                "password": _clave_temporal(),
                "email_confirm": True,
                "user_metadata": {"nombre": (nombre or email.split("@")[0]), "rol": "estudiante"},
            }
        )
        user = creado.user
    existente = (
        db.table("inscripciones_curso")
        .select("id")
        .eq("curso_id", curso_id)
        .eq("estudiante_id", user.id)
        .limit(1)
        .execute()
        .data
    )
    if existente:
        return existente[0]
    return (
        db.table("inscripciones_curso")
        .insert(
            {
                "curso_id": curso_id,
                "estudiante_id": user.id,
                "preferencias": dua.normalizar_preferencias(preferencias),
                "idioma_preferido": dua.normalizar_idioma(idioma),
            }
        )
        .execute()
        .data[0]
    )


def actualizar_preferencias(inscripcion_id: str, curso_id: str, preferencias: list[str], idioma: str = "es") -> dict:
    validas = dua.normalizar_preferencias(preferencias)
    return (
        get_service_client()
        .table("inscripciones_curso")
        .update({"preferencias": validas, "idioma_preferido": dua.normalizar_idioma(idioma)})
        .eq("id", inscripcion_id)
        .eq("curso_id", curso_id)
        .execute()
        .data[0]
    )


def _usuario_por_email(email: str):
    admin = get_service_client().auth.admin
    if hasattr(admin, "get_user_by_email"):
        try:
            res = admin.get_user_by_email(email)
            user = getattr(res, "user", res)
            if user and getattr(user, "id", None):
                return user
        except Exception:
            pass
    usuarios = admin.list_users()
    lista = getattr(usuarios, "users", None) or usuarios
    for u in lista:
        if (getattr(u, "email", "") or "").lower() == email:
            return u
    return None


def _clave_temporal() -> str:
    import secrets

    return "Tmp-" + secrets.token_urlsafe(12)
