"""Crea un estudiante de prueba, lo inscribe y verifica mochila + sesión publicada."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from supabase import create_client  # noqa: E402

from app import create_app  # noqa: E402
from config import settings  # noqa: E402
from services import cursos as svc  # noqa: E402
from services.supabase_client import get_service_client  # noqa: E402

EMAIL = "estudiante.prueba@prisma.local"
PASSWORD = "Prueba-Estudiante-123!"


def asegurar_estudiante():
    admin = get_service_client().auth.admin
    for u in admin.list_users():
        if u.email == EMAIL:
            return u.id
    creado = admin.create_user(
        {
            "email": EMAIL,
            "password": PASSWORD,
            "email_confirm": True,
            "user_metadata": {"nombre": "Estudiante de prueba", "rol": "estudiante"},
        }
    )
    return creado.user.id


def main() -> int:
    est_id = asegurar_estudiante()
    db = get_service_client()
    perfil = db.table("perfiles").select("rol").eq("id", est_id).execute().data
    if not perfil or perfil[0]["rol"] != "estudiante":
        print("ERROR: perfil estudiante no creado. ¿002_rls_fix.sql aplicado?")
        return 1
    curso = db.table("cursos").select("id").eq("nombre_curso", "Curso de prueba").limit(1).execute().data
    if not curso:
        print("ERROR: no existe Curso de prueba")
        return 1
    svc.inscribir(curso[0]["id"], EMAIL, "Estudiante de prueba")
    svc.actualizar_preferencias(
        db.table("inscripciones_curso").select("id").eq("curso_id", curso[0]["id"]).eq("estudiante_id", est_id).execute().data[0]["id"],
        curso[0]["id"],
        ["alto_contraste", "modo_enfoque"],
        "es",
    )

    login = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
    token = login.auth.sign_in_with_password({"email": EMAIL, "password": PASSWORD}).session.access_token
    cliente = create_app(con_worker=False).test_client()
    with cliente.session_transaction() as s:
        s["access_token"] = token
    r = cliente.get("/estudiante/cursos")
    print("mochila", r.status_code, "Curso de prueba" in r.get_data(as_text=True))
    sesion = (
        db.table("sesiones_material")
        .select("id, titulo")
        .eq("curso_id", curso[0]["id"])
        .eq("estado", "publicado")
        .limit(1)
        .execute()
        .data
    )
    if not sesion:
        print("ERROR: no hay sesión publicada")
        return 1
    r2 = cliente.get(f"/estudiante/sesiones/{sesion[0]['id']}")
    html = r2.get_data(as_text=True)
    print("sesion", r2.status_code, sesion[0]["titulo"], "tema-contraste" in html, "Tutor de esta sesión" in html)
    r3 = cliente.post(f"/chat/{sesion[0]['id']}/duda", json={"pregunta": "No entiendo el saludo"})
    print("duda", r3.status_code, r3.get_json())
    return 0 if r.status_code == 200 and r2.status_code == 200 and r3.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
