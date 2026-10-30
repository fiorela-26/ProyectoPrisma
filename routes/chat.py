import json

from config import settings
from flask import Blueprint, Response, g, jsonify, request, stream_with_context

from services import chat_service, estudiante as est, rate_limit
from services.auth import requiere_rol
from services.ai_router import CuotaAgotada

bp = Blueprint("chat", __name__)


@bp.post("/chat/<uuid:sesion_id>")
@requiere_rol("estudiante")
def chat(sesion_id):
    visto = est.sesion_visible(str(sesion_id), g.usuario["id"])
    if visto is None:
        return jsonify({"error": "Sesión no disponible"}), 404
    try:
        rate_limit.comprobar(f"chat:{g.usuario['id']}", settings.RATE_CHAT_POR_MINUTO)
    except rate_limit.DemasiadoRapido as exc:
        return jsonify({"error": str(exc)}), 429
    sesion, insc = visto
    cuerpo = request.get_json(silent=True) or {}
    pregunta = (cuerpo.get("pregunta") or request.form.get("pregunta") or "").strip()
    from services import dua

    prefs = dua.normalizar_preferencias(insc.get("preferencias"))
    idioma = dua.normalizar_idioma(insc.get("idioma_preferido") or "es")

    def eventos():
        try:
            for fragmento in chat_service.responder_stream(sesion, g.usuario["id"], pregunta, prefs, idioma):
                yield f"data: {json.dumps(fragmento, ensure_ascii=False)}\n\n"
            yield "event: done\ndata: ok\n\n"
        except chat_service.CuotaAgotadaChat as exc:
            yield f"event: error\ndata: {exc}\n\n"
        except CuotaAgotada as exc:
            yield f"event: error\ndata: El tutor no está disponible ahora ({exc}).\n\n"
        except ValueError as exc:
            yield f"event: error\ndata: {exc}\n\n"
        except Exception:
            yield "event: error\ndata: No se pudo completar la respuesta.\n\n"

    return Response(stream_with_context(eventos()), mimetype="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@bp.post("/chat/<uuid:sesion_id>/duda")
@requiere_rol("estudiante")
def duda(sesion_id):
    visto = est.sesion_visible(str(sesion_id), g.usuario["id"])
    if visto is None:
        return jsonify({"error": "Sesión no disponible"}), 404
    try:
        rate_limit.comprobar(f"chat:{g.usuario['id']}", settings.RATE_CHAT_POR_MINUTO)
    except rate_limit.DemasiadoRapido as exc:
        return jsonify({"error": str(exc)}), 429
    cuerpo = request.get_json(silent=True) or {}
    pregunta = (cuerpo.get("pregunta") or "").strip()
    try:
        chat_service.enviar_duda_docente(visto[0]["id"], g.usuario["id"], pregunta)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "mensaje": "Tu duda quedó guardada para el docente."})
