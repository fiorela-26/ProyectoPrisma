"""Lectura de cursos y sesiones publicados para un estudiante inscrito."""
from services import dua
from services.package_builder import FORMATOS_MVP, NOMBRES_UI
from services.supabase_client import get_service_client


def mochila(estudiante_id: str) -> list[dict]:
    db = get_service_client()
    insc = (
        db.table("inscripciones_curso")
        .select("curso_id, preferencias, idioma_preferido")
        .eq("estudiante_id", estudiante_id)
        .execute()
        .data
        or []
    )
    if not insc:
        return []
    ids = [i["curso_id"] for i in insc]
    cursos = {
        c["id"]: c
        for c in db.table("cursos")
        .select("id, nombre_curso, descripcion, nivel_educativo, nivel_educativo_etiqueta")
        .in_("id", ids)
        .execute()
        .data
        or []
    }
    out = []
    for i in insc:
        c = cursos.get(i["curso_id"])
        if not c:
            continue
        sesiones = (
            db.table("sesiones_material")
            .select("id, titulo, estado, creado_en")
            .eq("curso_id", c["id"])
            .eq("estado", "publicado")
            .order("creado_en", desc=True)
            .execute()
            .data
            or []
        )
        out.append(
            {
                **c,
                "preferencias": dua.normalizar_preferencias(i.get("preferencias")),
                "idioma_preferido": dua.normalizar_idioma(i.get("idioma_preferido") or "es"),
                "sesiones": sesiones,
            }
        )
    return out


def inscripcion(curso_id: str, estudiante_id: str) -> dict | None:
    res = (
        get_service_client()
        .table("inscripciones_curso")
        .select("*")
        .eq("curso_id", curso_id)
        .eq("estudiante_id", estudiante_id)
        .limit(1)
        .execute()
        .data
    )
    return res[0] if res else None


def sesion_visible(sesion_id: str, estudiante_id: str) -> tuple[dict, dict] | None:
    db = get_service_client()
    sesion = db.table("sesiones_material").select("*").eq("id", sesion_id).eq("estado", "publicado").limit(1).execute().data
    if not sesion:
        return None
    insc = inscripcion(sesion[0]["curso_id"], estudiante_id)
    if not insc:
        return None
    return sesion[0], insc


def actualizar_mis_preferencias(inscripcion_id: str, estudiante_id: str, preferencias: list[str], idioma: str) -> dict:
    validas = dua.normalizar_preferencias(preferencias)
    return (
        get_service_client()
        .table("inscripciones_curso")
        .update({"preferencias": validas, "idioma_preferido": dua.normalizar_idioma(idioma)})
        .eq("id", inscripcion_id)
        .eq("estudiante_id", estudiante_id)
        .execute()
        .data[0]
    )


def ordenar_formatos(paquetes: list[dict], preferencias: list[str]) -> list[dict]:
    """Las preferencias van primero; el resto sigue disponible."""
    por_clave = {p["formato"]: p for p in paquetes}
    vistos = []
    for p in preferencias:
        if p in por_clave:
            vistos.append(por_clave[p])
    for f in FORMATOS_MVP:
        if f in por_clave and por_clave[f] not in vistos:
            vistos.append(por_clave[f])
    for p in paquetes:
        if p not in vistos:
            vistos.append(p)
    return vistos


def nombres():
    return NOMBRES_UI
