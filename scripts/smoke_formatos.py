"""Genera los 3 formatos MVP sobre una sesión que ya tiene texto extraído."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from supabase import create_client  # noqa: E402

from app import create_app  # noqa: E402
from config import settings  # noqa: E402
from scripts.smoke_upload import EMAIL, PASSWORD  # noqa: E402
from services import jobs  # noqa: E402
from services.supabase_client import get_service_client  # noqa: E402


def main() -> int:
    db = get_service_client()
    sesiones = (
        db.table("sesiones_material")
        .select("id, titulo, estado, texto_extraido")
        .eq("estado", "revision")
        .not_.is_("texto_extraido", "null")
        .order("creado_en", desc=True)
        .limit(1)
        .execute()
        .data
    )
    if not sesiones:
        print("No hay sesión en revisión con texto. Sube un PDF/audio primero.")
        return 1
    sesion = sesiones[0]
    print("Sesión:", sesion["id"], sesion["titulo"], repr((sesion["texto_extraido"] or "")[:80]))

    login = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
    token = login.auth.sign_in_with_password({"email": EMAIL, "password": PASSWORD}).session.access_token
    cliente = create_app(con_worker=False).test_client()
    headers = {"Authorization": f"Bearer {token}"}

    for formato in ("alto_contraste", "lectura_accesible", "modo_enfoque"):
        resp = cliente.post(f"/sesiones/{sesion['id']}/formatos", json={"formato": formato}, headers=headers)
        print(formato, "HTTP", resp.status_code, resp.get_json())
        if resp.status_code == 202:
            job = jobs.obtener_job(resp.get_json()["job_id"])
            final = jobs.ejecutar_job(job)
            print("  job ->", final["estado"], final.get("formato"), final.get("error") or "")
            if final["estado"] != "done":
                return 1
        elif resp.status_code != 200:
            return 1

    lista = cliente.get(f"/sesiones/{sesion['id']}/formatos", headers=headers)
    print("GET", lista.status_code)
    for p in lista.get_json().get("paquetes", []):
        print(" ", p["formato"], "ia=", p["generado_por_ia"], "modelo=", p.get("modelo_usado"), "keys=", list((p.get("contenido") or {}).keys()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
