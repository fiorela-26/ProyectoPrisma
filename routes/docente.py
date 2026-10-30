from flask import Blueprint, g, jsonify, request

from services import jobs, materiales, package_builder
from services.auth import requiere_rol
from services.supabase_client import get_service_client

bp = Blueprint("docente", __name__)


@bp.post("/cursos/<uuid:curso_id>/materiales")
@requiere_rol("docente")
def subir_material(curso_id):
    """Recibe un archivo, lo guarda y encola la extracción. Responde de inmediato con el job_id."""
    curso_id = str(curso_id)
    if not materiales.docente_es_dueno(curso_id, g.usuario["id"]):
        return jsonify({"error": "El curso no existe o no te pertenece"}), 404

    archivo = request.files.get("archivo")
    if archivo is None or not archivo.filename:
        return jsonify({"error": "Falta el campo 'archivo'"}), 400

    try:
        resultado = materiales.registrar_material(
            curso_id=curso_id,
            titulo=request.form.get("titulo", ""),
            nombre_archivo=archivo.filename,
            datos=archivo.read(),
            idioma=request.form.get("idioma", "es"),
        )
    except materiales.MaterialInvalido as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(resultado), 202


@bp.get("/sesiones/<uuid:sesion_id>/formatos")
@requiere_rol("docente")
def listar_formatos(sesion_id):
    sesion = materiales.docente_es_dueno_de_sesion(str(sesion_id), g.usuario["id"])
    if sesion is None:
        return jsonify({"error": "Sesión no encontrada"}), 404
    paquetes = (
        get_service_client()
        .table("paquetes_formato")
        .select("formato, contenido, generado_por_ia, modelo_usado, editado_por_docente, version")
        .eq("sesion_id", str(sesion_id))
        .execute()
        .data
    )
    return jsonify(
        {
            "disponibles": package_builder.FORMATOS_MVP,
            "nombres": package_builder.NOMBRES_UI,
            "paquetes": paquetes,
            "estado_sesion": sesion.get("estado"),
        }
    )


@bp.post("/sesiones/<uuid:sesion_id>/formatos")
@requiere_rol("docente")
def pedir_formato(sesion_id):
    """Encola la generación de un formato. Responde de inmediato con job_id."""
    sesion = materiales.docente_es_dueno_de_sesion(str(sesion_id), g.usuario["id"])
    if sesion is None:
        return jsonify({"error": "Sesión no encontrada"}), 404
    cuerpo = request.get_json(silent=True) or {}
    formato = (cuerpo.get("formato") or request.form.get("formato") or "").strip()
    if formato not in package_builder.FORMATOS_MVP:
        return jsonify({"error": "Formato no soportado", "disponibles": package_builder.FORMATOS_MVP}), 400
    if not (sesion.get("texto_extraido") or "").strip():
        return jsonify({"error": "Aún no hay texto extraído; espera a que termine la extracción"}), 409

    if formato == "alto_contraste":
        paquete = package_builder.guardar_paquete(
            sesion["id"],
            formato,
            package_builder.generar(formato, sesion["texto_extraido"], sesion.get("contenido_hash") or "", sesion.get("idioma_original") or "es"),
        )
        return jsonify({"sesion_id": sesion["id"], "formato": formato, "paquete_id": paquete["id"], "inmediato": True}), 200

    job = jobs.crear_job(sesion["id"], "formato", formato=formato)
    return jsonify({"sesion_id": sesion["id"], "formato": formato, "job_id": job["id"]}), 202
