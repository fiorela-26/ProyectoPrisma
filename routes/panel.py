from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, url_for

from services import analitica, chat_service, dua, imagen_educativa, jobs, materiales, mediacion, package_builder
from services import cursos as svc
from services.auth import requiere_pagina, requiere_rol

bp = Blueprint("panel", __name__, url_prefix="/docente")


@bp.get("/")
@requiere_pagina("docente")
def inicio():
    return redirect(url_for("panel.cursos"))


@bp.get("/cursos")
@requiere_pagina("docente")
def cursos():
    lista = svc.listar_cursos(g.usuario["id"])
    return render_template("docente/cursos.html", cursos=lista, niveles_cine=svc.NIVELES_CINE)


@bp.post("/cursos")
@requiere_pagina("docente")
def crear_curso():
    try:
        curso = svc.crear_curso(
            g.usuario["id"],
            request.form.get("nombre", ""),
            request.form.get("descripcion", ""),
            request.form.get("nivel_educativo", ""),
        )
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("panel.cursos"))
    flash("Curso creado.", "ok")
    return redirect(url_for("panel.curso", curso_id=curso["id"]))


def _pagina_curso(curso_id: str, previa: dict | None = None, codigo: int = 200):
    lista = svc.listar_cursos(g.usuario["id"])
    curso = next((c for c in lista if c["id"] == curso_id), None)
    if curso is None:
        return ("Curso no encontrado.", 404)
    sesiones = svc.sesiones_de_curso(curso_id)
    for s in sesiones:
        s["jobs"] = svc.jobs_de_sesion(s["id"])
        s["tiene_texto"] = bool((s.get("texto_extraido") or "").strip())
    html = render_template(
        "docente/curso.html",
        curso=curso,
        sesiones=sesiones,
        inscripciones=svc.inscripciones(curso_id),
        preferencias=svc.PREFERENCIAS,
        necesidades_dua=dua.NECESIDADES,
        lenguas_dua=dua.LENGUAS,
        nombres=package_builder.NOMBRES_UI,
        tipos=sorted(materiales.TIPOS_PERMITIDOS),
        accept_archivos=materiales.accept_html(),
        previa=previa,
    )
    return html, codigo


@bp.get("/cursos/<uuid:curso_id>")
@requiere_pagina("docente")
def curso(curso_id):
    curso_id = str(curso_id)
    if not materiales.docente_es_dueno(curso_id, g.usuario["id"]):
        return ("Curso no encontrado.", 404)
    return _pagina_curso(curso_id)


@bp.get("/cursos/<uuid:curso_id>/analitica")
@requiere_pagina("docente")
def analitica_curso(curso_id):
    curso_id = str(curso_id)
    if not materiales.docente_es_dueno(curso_id, g.usuario["id"]):
        return ("Curso no encontrado.", 404)
    lista = svc.listar_cursos(g.usuario["id"])
    curso = next((c for c in lista if c["id"] == curso_id), None)
    if curso is None:
        return ("Curso no encontrado.", 404)
    return render_template("docente/analitica.html", curso=curso, resumen=analitica.resumen_curso(curso_id))


@bp.post("/cursos/<uuid:curso_id>/materiales")
@requiere_pagina("docente")
def subir(curso_id):
    curso_id = str(curso_id)
    if not materiales.docente_es_dueno(curso_id, g.usuario["id"]):
        return ("Curso no encontrado.", 404)
    archivo = request.files.get("archivo")
    titulo = (request.form.get("titulo") or "").strip()
    tiene_archivo = archivo is not None and bool(archivo.filename)
    if not tiene_archivo and not titulo:
        flash("Escribe un título o sube un archivo.", "error")
        return redirect(url_for("panel.curso", curso_id=curso_id))
    try:
        if tiene_archivo:
            previa = materiales.previsualizar_material(
                curso_id=curso_id,
                titulo=titulo,
                nombre_archivo=archivo.filename,
                datos=archivo.read(),
                idioma=request.form.get("idioma", "es"),
            )
        else:
            previa = materiales.previsualizar_desde_titulo(
                curso_id=curso_id,
                titulo=titulo,
                idioma=request.form.get("idioma", "es"),
            )
    except materiales.MaterialInvalido as exc:
        flash(str(exc), "error")
        return redirect(url_for("panel.curso", curso_id=curso_id))
    flash("Revisa lo extraído. Puedes editarlo antes de crear la sesión.", "ok")
    return _pagina_curso(curso_id, previa=previa)


@bp.post("/cursos/<uuid:curso_id>/materiales/confirmar")
@requiere_pagina("docente")
def confirmar_material(curso_id):
    curso_id = str(curso_id)
    if not materiales.docente_es_dueno(curso_id, g.usuario["id"]):
        return ("Curso no encontrado.", 404)
    try:
        sesion = materiales.confirmar_material(
            curso_id=curso_id,
            titulo=request.form.get("titulo", ""),
            texto=request.form.get("texto", ""),
            ruta=request.form.get("ruta", ""),
            hash_contenido=request.form.get("hash", ""),
            tipo=request.form.get("tipo", ""),
            idioma=request.form.get("idioma", "es"),
        )
    except materiales.MaterialInvalido as exc:
        flash(str(exc), "error")
        return redirect(url_for("panel.curso", curso_id=curso_id))
    flash("Sesión creada. Revisa los formatos DUA y publícala cuando quieras.", "ok")
    return redirect(url_for("panel.sesion", sesion_id=sesion["id"]))


@bp.post("/cursos/<uuid:curso_id>/materiales/preview_json")
@requiere_rol("docente")
def preview_material_json(curso_id):
    """API: recibe archivo y devuelve la previsualización (JSON) sin crear la sesión."""
    curso_id = str(curso_id)
    if not materiales.docente_es_dueno(curso_id, g.usuario["id"]):
        return jsonify({"error": "El curso no existe o no te pertenece"}), 404
    archivo = request.files.get("archivo")
    titulo = (request.form.get("titulo") or "").strip()
    tiene_archivo = archivo is not None and bool(archivo.filename)
    if not tiene_archivo and not titulo:
        return jsonify({"error": "Escribe un título o sube un archivo"}), 400
    try:
        if tiene_archivo:
            previa = materiales.previsualizar_material(
                curso_id=curso_id,
                titulo=titulo,
                nombre_archivo=archivo.filename,
                datos=archivo.read(),
                idioma=request.form.get("idioma", "es"),
            )
        else:
            previa = materiales.previsualizar_desde_titulo(
                curso_id=curso_id,
                titulo=titulo,
                idioma=request.form.get("idioma", "es"),
            )
    except materiales.MaterialInvalido as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"No se pudo extraer el archivo: {exc}"}), 500
    return jsonify(previa), 200


@bp.post("/cursos/<uuid:curso_id>/alumnos")
@requiere_pagina("docente")
def inscribir(curso_id):
    curso_id = str(curso_id)
    if not materiales.docente_es_dueno(curso_id, g.usuario["id"]):
        return ("Curso no encontrado.", 404)
    try:
        svc.inscribir(
            curso_id,
            request.form.get("email", ""),
            request.form.get("nombre", ""),
            request.form.getlist("preferencias"),
            request.form.get("idioma", "es"),
        )
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("panel.curso", curso_id=curso_id))
    flash("Estudiante inscrito. Puedes actualizar sus necesidades DUA cuando las identifiques.", "ok")
    return redirect(url_for("panel.curso", curso_id=curso_id))


@bp.post("/cursos/<uuid:curso_id>/inscripciones/<uuid:inscripcion_id>")
@requiere_pagina("docente")
def preferencias(curso_id, inscripcion_id):
    curso_id = str(curso_id)
    if not materiales.docente_es_dueno(curso_id, g.usuario["id"]):
        return ("Curso no encontrado.", 404)
    prefs = request.form.getlist("preferencias")
    svc.actualizar_preferencias(str(inscripcion_id), curso_id, prefs, request.form.get("idioma", "es"))
    flash("Necesidades DUA actualizadas. El estudiante las verá combinadas en la clase.", "ok")
    return redirect(url_for("panel.curso", curso_id=curso_id))


@bp.get("/sesiones/<uuid:sesion_id>")
@requiere_pagina("docente")
def sesion(sesion_id):
    sesion = materiales.docente_es_dueno_de_sesion(str(sesion_id), g.usuario["id"])
    if sesion is None:
        return ("Sesión no encontrada.", 404)
    paquetes = {p["formato"]: p for p in svc.paquetes_de_sesion(sesion["id"])}
    return render_template(
        "docente/sesion.html",
        sesion=sesion,
        jobs=svc.jobs_de_sesion(sesion["id"]),
        paquetes=paquetes,
        formatos=package_builder.FORMATOS_MVP,
        nombres=package_builder.NOMBRES_UI,
        necesidades_dua=dua.NECESIDADES,
        lenguas_dua=dua.LENGUAS,
        dudas=chat_service.dudas_de_sesion(sesion["id"]),
        url_imagen=url_for("panel.imagen_educativa_json", sesion_id=sesion["id"]),
        url_mediacion=url_for("panel.mediacion_json", sesion_id=sesion["id"]),
        rol_mediacion="docente",
    )


@bp.post("/sesiones/<uuid:sesion_id>/dua_traducir")
@requiere_rol("docente")
def dua_traducir(sesion_id):
    sesion = materiales.docente_es_dueno_de_sesion(str(sesion_id), g.usuario["id"])
    if sesion is None:
        return jsonify({"error": "Sesión no encontrada"}), 404
    cuerpo = request.get_json(silent=True) or {}
    out = dua.adaptar_a_lengua(sesion.get("texto_extraido") or "", cuerpo.get("idioma") or "")
    return jsonify(out)


@bp.get("/sesiones/<uuid:sesion_id>/imagen")
@requiere_rol("docente")
def imagen_educativa_json(sesion_id):
    sesion = materiales.docente_es_dueno_de_sesion(str(sesion_id), g.usuario["id"])
    if sesion is None:
        return jsonify({"error": "Sesión no encontrada"}), 404
    try:
        return jsonify(imagen_educativa.para_sesion(sesion))
    except Exception as exc:
        return jsonify({"estado": "error", "url": "", "alt": "", "error": str(exc)}), 500


@bp.get("/sesiones/<uuid:sesion_id>/mediacion")
@requiere_rol("docente")
def mediacion_json(sesion_id):
    sesion = materiales.docente_es_dueno_de_sesion(str(sesion_id), g.usuario["id"])
    if sesion is None:
        return jsonify({"error": "Sesión no encontrada"}), 404
    try:
        return jsonify(mediacion.para_sesion(sesion))
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


@bp.post("/sesiones/<uuid:sesion_id>/formatos")
@requiere_pagina("docente")
def pedir_formato(sesion_id):
    sesion = materiales.docente_es_dueno_de_sesion(str(sesion_id), g.usuario["id"])
    if sesion is None:
        return ("Sesión no encontrada.", 404)
    formato = (request.form.get("formato") or "").strip()
    if formato not in package_builder.FORMATOS_MVP:
        flash("Formato no soportado.", "error")
        return redirect(url_for("panel.sesion", sesion_id=sesion["id"]))
    if not (sesion.get("texto_extraido") or "").strip():
        flash("Aún no hay texto extraído.", "error")
        return redirect(url_for("panel.sesion", sesion_id=sesion["id"]))
    if formato == "alto_contraste":
        package_builder.guardar_paquete(
            sesion["id"],
            formato,
            package_builder.generar(
                formato, sesion["texto_extraido"], sesion.get("contenido_hash") or "", sesion.get("idioma_original") or "es"
            ),
        )
        flash("Alto contraste listo (sin IA).", "ok")
    else:
        jobs.crear_job(sesion["id"], "formato", formato=formato)
        flash("Generación en cola. Recarga en unos segundos.", "ok")
    return redirect(url_for("panel.sesion", sesion_id=sesion["id"]))


@bp.post("/sesiones/<uuid:sesion_id>/formatos/<formato>")
@requiere_pagina("docente")
def editar_formato(sesion_id, formato):
    sesion = materiales.docente_es_dueno_de_sesion(str(sesion_id), g.usuario["id"])
    if sesion is None:
        return ("Sesión no encontrada.", 404)
    try:
        contenido = _contenido_desde_form(formato, request.form)
        svc.guardar_edicion(sesion["id"], formato, contenido)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("panel.sesion", sesion_id=sesion["id"]))
    flash("Cambios guardados. Quedaron marcados como editados por el docente.", "ok")
    return redirect(url_for("panel.sesion", sesion_id=sesion["id"]))


@bp.post("/sesiones/<uuid:sesion_id>/publicar")
@requiere_pagina("docente")
def publicar(sesion_id):
    sesion = materiales.docente_es_dueno_de_sesion(str(sesion_id), g.usuario["id"])
    if sesion is None:
        return ("Sesión no encontrada.", 404)
    try:
        svc.publicar_sesion(sesion["id"])
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("panel.sesion", sesion_id=sesion["id"]))
    flash("Publicado. Los estudiantes inscritos ya pueden ver todos los formatos.", "ok")
    return redirect(url_for("panel.sesion", sesion_id=sesion["id"]))


@bp.post("/jobs/<uuid:job_id>/reintentar")
@requiere_pagina("docente")
def reintentar(job_id):
    job = jobs.docente_puede_ver_job(str(job_id), g.usuario["id"])
    if job is None:
        return ("Job no encontrado.", 404)
    try:
        svc.reintentar_job(job["id"])
    except ValueError as exc:
        flash(str(exc), "error")
    else:
        flash("Job vuelto a la cola.", "ok")
    return redirect(url_for("panel.sesion", sesion_id=job["sesion_id"]))


def _contenido_desde_form(formato: str, form) -> dict:
    if formato == "lectura_accesible":
        avisos = [a.strip() for a in (form.get("avisos") or "").split("\n") if a.strip()]
        return {"markdown": form.get("markdown") or "", "avisos": avisos}
    if formato == "alto_contraste":
        return {
            "tokens": {
                "fondo": form.get("fondo") or "#000000",
                "texto": form.get("texto") or "#FFFFFF",
                "enlace": form.get("enlace") or "#FFFF00",
                "foco": form.get("foco") or "#00FFFF",
                "aviso": form.get("aviso") or "#FFD700",
            },
            "tamano_base_px": int(form.get("tamano_base_px") or 20),
            "tamano_min_px": 16,
            "tamano_max_px": 32,
        }
    if formato == "modo_enfoque":
        titulos = form.getlist("pildora_titulo")
        textos = form.getlist("pildora_texto")
        pildoras = [{"titulo": t.strip(), "texto": x.strip()} for t, x in zip(titulos, textos) if t.strip() or x.strip()]
        return {"pildoras": pildoras}
    raise ValueError("Formato no editable")
