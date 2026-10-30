"""Registro de interacciones y resúmenes para el docente. Sin nombres si no hacen falta."""
from collections import Counter

from services.package_builder import NOMBRES_UI
from services.supabase_client import get_service_client

def registrar(estudiante_id: str, sesion_id: str, formato: str | None, duracion: int, completado: bool) -> dict:
    try:
        duracion = max(0, min(int(duracion or 0), 24 * 3600))
    except (TypeError, ValueError):
        duracion = 0
    formato = formato if formato in NOMBRES_UI else None
    fila = {
        "estudiante_id": estudiante_id,
        "sesion_id": sesion_id,
        "formato_usado": formato,
        "duracion_segundos": duracion,
        "completado": bool(completado),
    }
    data = get_service_client().table("interacciones_progreso").insert(fila).execute().data or []
    return data[0] if data else fila


def resumen_curso(curso_id: str) -> dict:
    db = get_service_client()
    sesiones = db.table("sesiones_material").select("id, titulo, estado").eq("curso_id", curso_id).execute().data or []
    ids = [s["id"] for s in sesiones]
    inter = []
    if ids:
        inter = db.table("interacciones_progreso").select("*").in_("sesion_id", ids).execute().data or []
    por_formato = Counter((i.get("formato_usado") or "sin_formato") for i in inter)
    tiempo = Counter()
    for i in inter:
        tiempo[i.get("formato_usado") or "sin_formato"] += int(i.get("duracion_segundos") or 0)
    completadas = Counter(i["sesion_id"] for i in inter if i.get("completado"))
    max_uso = max(por_formato.values()) if por_formato else 1
    formatos = [
        {
            "clave": k,
            "nombre": NOMBRES_UI.get(k, k),
            "usos": n,
            "segundos": tiempo.get(k, 0),
            "pct": round(100 * n / max_uso),
        }
        for k, n in por_formato.most_common()
    ]
    sesiones_out = []
    for s in sesiones:
        sesiones_out.append(
            {
                "id": s["id"],
                "titulo": s["titulo"],
                "estado": s["estado"],
                "completadas": completadas.get(s["id"], 0),
                "preguntas": preguntas_frecuentes(s["id"], limite=5),
            }
        )
    return {
        "total_interacciones": len(inter),
        "formatos": formatos,
        "sesiones": sesiones_out,
    }


def preguntas_frecuentes(sesion_id: str, limite: int = 8) -> list[dict]:
    """Agrupa preguntas del chat. No incluye identidad del estudiante."""
    from services.chat_service import MARCA_DUDA

    db = get_service_client()
    convs = db.table("conversaciones_chat").select("id").eq("sesion_id", sesion_id).execute().data or []
    if not convs:
        return []
    msgs = (
        db.table("mensajes_chat")
        .select("contenido, rol")
        .in_("conversacion_id", [c["id"] for c in convs])
        .eq("rol", "user")
        .execute()
        .data
        or []
    )
    conteo = Counter()
    for m in msgs:
        t = (m.get("contenido") or "").strip()
        if t.startswith(MARCA_DUDA):
            t = t.split("\n", 1)[-1].strip()
        clave = " ".join(t.lower().split())
        if len(clave) < 4:
            continue
        conteo[clave] += 1
    return [{"pregunta": p, "veces": n} for p, n in conteo.most_common(limite)]
