import json

from config import settings
from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, session, url_for

from services import analitica, chat_service, dua, estudiante as svc, imagen_educativa, mediacion, rate_limit
from services import cursos as cursos_svc
from services.auth import requiere_pagina, requiere_rol
from services.package_builder import FORMATOS_MVP, NOMBRES_UI

bp = Blueprint("estudiante", __name__, url_prefix="/estudiante")


@bp.get("/")
@requiere_pagina("estudiante")
def inicio():
    return redirect(url_for("estudiante.mochila"))


@bp.get("/cursos")
@requiere_pagina("estudiante")
def mochila():
    return render_template(
        "estudiante/mochila.html",
        cursos=svc.mochila(g.usuario["id"]),
    )


@bp.post("/cursos/<uuid:curso_id>/preferencias")
@requiere_pagina("estudiante")
def preferencias(curso_id):
    """Los ajustes del curso los define el docente; el estudiante solo puede cambiar la vista por sesión."""
    flash(
        "Los ajustes DUA de tu curso los configura tu docente. "
        "Entra en una sesión publicada para probar otras formas de ver solo esa clase.",
        "err",
    )
    return redirect(url_for("estudiante.mochila"))


@bp.get("/sesiones/<uuid:sesion_id>")
@requiere_pagina("estudiante")
def sesion(sesion_id):
    visto = svc.sesion_visible(str(sesion_id), g.usuario["id"])
    if visto is None:
        return ("Esa sesión no está publicada o no estás inscrito.", 404)
    sesion, insc = visto
    paquetes = svc.ordenar_formatos(cursos_svc.paquetes_de_sesion(sesion["id"]), insc.get("preferencias") or [])
    clave = f"fmt_{sesion['id']}"
    activos = session.get(clave)
    if activos is None:
        activos = dua.normalizar_preferencias(insc.get("preferencias"))
        session[clave] = activos
    else:
        activos = dua.normalizar_preferencias(activos)
    idioma_actual = session.get(f"idioma_{sesion['id']}") or dua.normalizar_idioma(insc.get("idioma_preferido") or "es")
    conv = chat_service.conversacion(sesion["id"], g.usuario["id"])
    clases = " ".join("dua-" + a for a in activos)
    return render_template(
        "estudiante/sesion.html",
        sesion=sesion,
        insc=insc,
        paquetes=paquetes,
        activos=activos,
        nombres=NOMBRES_UI,
        formatos=FORMATOS_MVP,
        necesidades_dua=dua.NECESIDADES,
        lenguas_dua=dua.LENGUAS,
        idioma_actual=idioma_actual,
        body_dua=clases,
        mensajes=chat_service.mensajes(conv["id"]),
        cuota=chat_service.cuota_hoy(g.usuario["id"]),
        cuota_max=settings.CHAT_LIMITE_DIARIO,
        url_imagen=url_for("estudiante.imagen_educativa_json", sesion_id=sesion["id"]),
        url_mediacion=url_for("estudiante.mediacion_json", sesion_id=sesion["id"]),
        rol_mediacion="estudiante",
    )


@bp.post("/sesiones/<uuid:sesion_id>/vista")
@requiere_pagina("estudiante")
def vista(sesion_id):
    visto = svc.sesion_visible(str(sesion_id), g.usuario["id"])
    if visto is None:
        return ("Esa sesión no está publicada o no estás inscrito.", 404)
    sid = visto[0]["id"]
    session[f"fmt_{sid}"] = dua.normalizar_preferencias(request.form.getlist("activos"))
    if request.form.get("idioma"):
        session[f"idioma_{sid}"] = dua.normalizar_idioma(request.form.get("idioma"))
    return redirect(url_for("estudiante.sesion", sesion_id=sid))


@bp.post("/sesiones/<uuid:sesion_id>/dua_traducir")
@requiere_rol("estudiante")
def dua_traducir(sesion_id):
    visto = svc.sesion_visible(str(sesion_id), g.usuario["id"])
    if visto is None:
        return jsonify({"error": "Sesión no disponible"}), 404
    cuerpo = request.get_json(silent=True) or {}
    out = dua.adaptar_a_lengua(visto[0].get("texto_extraido") or "", cuerpo.get("idioma") or "")
    return jsonify(out)


@bp.get("/sesiones/<uuid:sesion_id>/imagen")
@requiere_rol("estudiante")
def imagen_educativa_json(sesion_id):
    visto = svc.sesion_visible(str(sesion_id), g.usuario["id"])
    if visto is None:
        return jsonify({"error": "Sesión no disponible"}), 404
    try:
        return jsonify(imagen_educativa.para_sesion(visto[0]))
    except Exception as exc:
        return jsonify({"estado": "error", "url": "", "alt": "", "error": str(exc)}), 500


@bp.get("/sesiones/<uuid:sesion_id>/mediacion")
@requiere_rol("estudiante")
def mediacion_json(sesion_id):
    visto = svc.sesion_visible(str(sesion_id), g.usuario["id"])
    if visto is None:
        return jsonify({"error": "Sesión no disponible"}), 404
    try:
        return jsonify(mediacion.para_sesion(visto[0]))
    except Exception as exc:
        return jsonify(
            {
                "estado": "error",
                "pauta_docente": "",
                "pauta_estudiante": "",
                "glosario": [],
                "error": str(exc),
            }
        ), 500


@bp.post("/interacciones")
@requiere_rol("estudiante")
def interacciones():
    cuerpo = request.get_json(silent=True)
    if not isinstance(cuerpo, dict):
        try:
            cuerpo = json.loads(request.get_data(as_text=True) or "{}")
        except json.JSONDecodeError:
            cuerpo = request.form
    if not isinstance(cuerpo, dict):
        cuerpo = {}
    sesion_id = str(cuerpo.get("sesion_id") or "")
    visto = svc.sesion_visible(sesion_id, g.usuario["id"])
    if visto is None:
        return jsonify({"error": "Sesión no disponible"}), 404
    try:
        rate_limit.comprobar(f"inter:{g.usuario['id']}", settings.RATE_INTERACCION_POR_MINUTO)
    except rate_limit.DemasiadoRapido as exc:
        return jsonify({"error": str(exc)}), 429
    raw = cuerpo.get("completado")
    completado = raw is True or raw == 1 or str(raw).lower() in ("1", "true", "si", "yes")
    analitica.registrar(
        g.usuario["id"],
        sesion_id,
        cuerpo.get("formato"),
        cuerpo.get("duracion_segundos") or 0,
        completado,
    )
    return ("", 204)


@bp.post("/sesiones/<uuid:sesion_id>/chat/borrar")
@requiere_pagina("estudiante")
def borrar_chat(sesion_id):
    visto = svc.sesion_visible(str(sesion_id), g.usuario["id"])
    if visto is None:
        return ("Esa sesión no está publicada o no estás inscrito.", 404)
    if request.form.get("confirmar") != "1":
        flash("Marca la casilla para confirmar el borrado.", "error")
        return redirect(url_for("estudiante.sesion", sesion_id=visto[0]["id"]))
    chat_service.borrar_mi_conversacion(visto[0]["id"], g.usuario["id"])
    flash("Se borró tu conversación de esta sesión.", "ok")
    return redirect(url_for("estudiante.sesion", sesion_id=visto[0]["id"]))
