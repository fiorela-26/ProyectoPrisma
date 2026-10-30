"""Identidad del usuario en cada petición.

El cliente manda el access token de Supabase Auth en `Authorization: Bearer <token>`.
Se valida contra Supabase y se carga el perfil (rol) con el cliente de servicio.
"""
from functools import wraps

from flask import g, jsonify, redirect, request, session, url_for

from services.supabase_client import get_anon_client, get_service_client


def _token_de_la_peticion() -> str | None:
    cabecera = request.headers.get("Authorization", "")
    if cabecera.lower().startswith("bearer "):
        return cabecera[7:].strip() or None
    return session.get("access_token") or None


def usuario_actual() -> dict | None:
    """Devuelve {"id", "email", "nombre", "rol", "token"} o None si no hay sesión válida."""
    if getattr(g, "usuario", None):
        return g.usuario
    token = _token_de_la_peticion()
    if not token:
        g.usuario = None
        return None
    try:
        auth_user = get_anon_client().auth.get_user(token).user
    except Exception:
        g.usuario = None
        return None
    if not auth_user:
        g.usuario = None
        return None
    perfil = (
        get_service_client().table("perfiles").select("nombre, rol").eq("id", auth_user.id).limit(1).execute().data
    )
    if not perfil:
        g.usuario = None
        return None
    g.usuario = {
        "id": auth_user.id,
        "email": auth_user.email,
        "nombre": perfil[0]["nombre"],
        "rol": perfil[0]["rol"],
        "token": token,
    }
    return g.usuario


def requiere_rol(*roles: str):
    """Decorador: exige sesión válida y, si se indican, uno de los roles dados."""

    def decorador(fn):
        @wraps(fn)
        def envoltura(*args, **kwargs):
            usuario = usuario_actual()
            if usuario is None:
                return jsonify({"error": "No autenticado"}), 401
            if roles and usuario["rol"] not in roles:
                return jsonify({"error": "Sin permiso"}), 403
            return fn(*args, **kwargs)

        return envoltura

    return decorador


def requiere_pagina(*roles: str):
    """Igual que requiere_rol, pero redirige al login en vez de devolver JSON."""

    def decorador(fn):
        @wraps(fn)
        def envoltura(*args, **kwargs):
            usuario = usuario_actual()
            if usuario is None:
                return redirect(url_for("auth.entrar"))
            if roles and usuario["rol"] not in roles:
                return ("Sin permiso para esta página.", 403)
            return fn(*args, **kwargs)

        return envoltura

    return decorador
