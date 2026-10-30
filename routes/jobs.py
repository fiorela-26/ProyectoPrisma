from flask import Blueprint, g, jsonify

from services import jobs
from services.auth import requiere_rol

bp = Blueprint("jobs", __name__)


@bp.get("/jobs/<uuid:job_id>")
@requiere_rol("docente")
def ver_job(job_id):
    """Polling del estado. El frontend pinta role=progressbar con progreso y texto."""
    job = jobs.docente_puede_ver_job(str(job_id), g.usuario["id"])
    if job is None:
        return jsonify({"error": "Job no encontrado"}), 404
    return jsonify(
        {
            "id": job["id"],
            "tipo": job["tipo"],
            "estado": job["estado"],
            "progreso": job.get("progreso") or 0,
            "error": job.get("error"),
            "formato": job.get("formato"),
            "intentos": job.get("intentos") or 0,
        }
    )
