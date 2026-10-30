from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from services.auth import usuario_actual
from services.supabase_client import get_anon_client

bp = Blueprint("auth", __name__)


@bp.get("/entrar")
def entrar():
    u = usuario_actual()
    if u and u["rol"] == "docente":
        return redirect(url_for("panel.cursos"))
    if u and u["rol"] == "estudiante":
        return redirect(url_for("estudiante.mochila"))
    return render_template("auth/entrar.html")


@bp.post("/entrar")
def entrar_post():
    email = (request.form.get("email") or "").strip()
    password = request.form.get("password") or ""
    if not email or not password:
        flash("Escribe correo y contraseña.", "error")
        return render_template("auth/entrar.html"), 400
    try:
        res = get_anon_client().auth.sign_in_with_password({"email": email, "password": password})
    except Exception:
        flash("No se pudo iniciar sesión. Revisa el correo y la contraseña.", "error")
        return render_template("auth/entrar.html"), 401
    session.clear()
    session["access_token"] = res.session.access_token
    session.permanent = True
    usuario = usuario_actual()
    if usuario is None:
        session.clear()
        flash("Tu cuenta no tiene perfil. Vuelve a registrarte o avisa a quien administra el sistema.", "error")
        return render_template("auth/entrar.html"), 403
    if usuario["rol"] == "docente":
        return redirect(url_for("panel.cursos"))
    if usuario["rol"] == "estudiante":
        return redirect(url_for("estudiante.mochila"))
    session.clear()
    flash("Este perfil no tiene un panel asignado.", "error")
    return render_template("auth/entrar.html"), 403


@bp.post("/salir")
def salir():
    session.clear()
    return redirect(url_for("auth.entrar"))
