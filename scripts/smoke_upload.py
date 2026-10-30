"""Prueba real de la Microfase 2.1 contra tu Supabase (sin levantar servidor).

1. Crea (o reutiliza) un docente de prueba en Supabase Auth.
2. Inicia sesión para obtener un access token real.
3. Crea un curso de prueba si no existe.
4. Sube un PDF pequeño por el endpoint POST /cursos/<id>/materiales.
5. Muestra la sesión y el job creados.

Uso: python scripts/smoke_upload.py
"""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from supabase import create_client  # noqa: E402

from app import create_app  # noqa: E402
from config import settings  # noqa: E402
from services import storage  # noqa: E402
from services.supabase_client import get_service_client  # noqa: E402

EMAIL = "docente.prueba@prisma.local"
PASSWORD = "Prueba-Docente-123!"
PDF_MINIMO = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
    b"4 0 obj<</Length 44>>stream\nBT /F1 18 Tf 20 100 Td (Hola Prisma) Tj ET\nendstream\nendobj\n"
    b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)


def asegurar_docente():
    admin = get_service_client().auth.admin
    for u in admin.list_users():
        if u.email == EMAIL:
            return u.id
    creado = admin.create_user(
        {
            "email": EMAIL,
            "password": PASSWORD,
            "email_confirm": True,
            "user_metadata": {"nombre": "Docente de prueba", "rol": "docente"},
        }
    )
    return creado.user.id


def asegurar_curso(docente_id):
    db = get_service_client()
    res = db.table("cursos").select("id").eq("docente_id", docente_id).eq("nombre_curso", "Curso de prueba").execute()
    if res.data:
        return res.data[0]["id"]
    return db.table("cursos").insert({"docente_id": docente_id, "nombre_curso": "Curso de prueba"}).execute().data[0]["id"]


def main():
    storage.ensure_bucket()
    docente_id = asegurar_docente()
    perfil = get_service_client().table("perfiles").select("rol").eq("id", docente_id).execute().data
    if not perfil or perfil[0]["rol"] != "docente":
        print("ERROR: el perfil del docente no existe o no tiene rol 'docente'.")
        print("       Ejecuta supabase/002_rls_fix.sql en el SQL Editor y vuelve a correr este script.")
        return 1

    # Cliente propio para el login: el cliente anónimo compartido nunca debe cargar una sesión.
    login_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
    sesion_auth = login_client.auth.sign_in_with_password({"email": EMAIL, "password": PASSWORD})
    token = sesion_auth.session.access_token
    curso_id = asegurar_curso(docente_id)

    cliente = create_app().test_client()
    resp = cliente.post(
        f"/cursos/{curso_id}/materiales",
        data={"archivo": (io.BytesIO(PDF_MINIMO), "hola.pdf"), "titulo": "Material de prueba"},
        content_type="multipart/form-data",
        headers={"Authorization": f"Bearer {token}"},
    )
    print("HTTP", resp.status_code, resp.get_json())
    if resp.status_code != 202:
        return 1

    db = get_service_client()
    job = db.table("jobs").select("tipo, estado, formato").eq("id", resp.get_json()["job_id"]).execute().data[0]
    sesion = db.table("sesiones_material").select("titulo, estado, archivo_url").eq("id", resp.get_json()["sesion_id"]).execute().data[0]
    print("Sesión:", sesion)
    print("Job:   ", job)
    print("URL firmada (1h):", storage.signed_url(sesion["archivo_url"])[:90] + "...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
