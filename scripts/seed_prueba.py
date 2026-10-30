"""Crea (o actualiza) docentes/cursos/estudiantes de prueba DUA (solo desarrollo).

Uso:
  python scripts/seed_prueba.py              # usuarios y cursos vacíos
  python scripts/seed_prueba.py --roster     # además inscribe los 10 en los 3 cursos

Para volver al entorno prisma.local: python scripts/limpiar_seed_prueba.py
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import cursos as svc_cursos  # noqa: E402
from services import dua  # noqa: E402
from services.datos_prueba import CLAVE_ESTUDIANTE, CURSOS, DOCENTES, ESTUDIANTES  # noqa: E402
from services.supabase_client import get_service_client  # noqa: E402


def _asegurar_usuario(email: str, password: str, nombre: str, rol: str) -> str:
    email = email.strip().lower()
    admin = get_service_client().auth.admin
    user = svc_cursos._usuario_por_email(email)
    meta = {"nombre": nombre, "rol": rol}
    if user and getattr(user, "id", None):
        admin.update_user_by_id(
            user.id,
            {"password": password, "email_confirm": True, "user_metadata": meta},
        )
        uid = user.id
    else:
        creado = admin.create_user(
            {
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": meta,
            }
        )
        uid = creado.user.id
    db = get_service_client()
    perfil = db.table("perfiles").select("id").eq("id", uid).limit(1).execute().data
    fila = {"id": uid, "nombre": nombre, "rol": rol}
    if perfil:
        db.table("perfiles").update({"nombre": nombre, "rol": rol}).eq("id", uid).execute()
    else:
        db.table("perfiles").insert(fila).execute()
    return uid


def _asegurar_curso(docente_id: str, nombre: str, descripcion: str, nivel: str) -> str:
    db = get_service_client()
    exist = (
        db.table("cursos")
        .select("id")
        .eq("docente_id", docente_id)
        .eq("nombre_curso", nombre)
        .limit(1)
        .execute()
        .data
    )
    if exist:
        try:
            codigo, etiqueta = svc_cursos.resolver_nivel(nivel)
            db.table("cursos").update(
                {
                    "descripcion": descripcion,
                    "nivel_educativo": codigo,
                    "nivel_educativo_etiqueta": etiqueta,
                }
            ).eq("id", exist[0]["id"]).execute()
        except Exception:
            pass
        return exist[0]["id"]
    return svc_cursos.crear_curso(docente_id, nombre, descripcion, nivel)["id"]


def _inscribir(curso_id: str, est: dict) -> None:
    fila = svc_cursos.inscribir(
        curso_id,
        est["email"],
        est["nombre"],
        est["preferencias"],
        est["idioma"],
    )
    svc_cursos.actualizar_preferencias(
        fila["id"],
        curso_id,
        dua.normalizar_preferencias(est["preferencias"]),
        est["idioma"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed de prueba DUA (desarrollo)")
    parser.add_argument(
        "--roster",
        action="store_true",
        help="Inscribe los 10 estudiantes en los 3 cursos (solo para QA; no usar en demo real)",
    )
    args = parser.parse_args()

    docentes = {}
    print("== Docentes ==")
    for d in DOCENTES:
        uid = _asegurar_usuario(d["email"], d["password"], d["nombre"], "docente")
        docentes[d["email"]] = uid
        print(f"  {d['email']}  /  {d['password']}")

    cursos_ids = []
    print("\n== Cursos ==")
    for c in CURSOS:
        cid = _asegurar_curso(docentes[c["docente_email"]], c["nombre"], c["descripcion"], c["nivel_educativo"])
        cursos_ids.append(cid)
        print(f"  {c['nombre']}  ({c['docente_email']})")

    print("\n== Estudiantes (cuentas, sin inscribir salvo --roster) ==")
    for e in ESTUDIANTES:
        _asegurar_usuario(e["email"], CLAVE_ESTUDIANTE, e["nombre"], "estudiante")
        prefs = ", ".join(e["preferencias"])
        print(f"  {e['email']}  /  {CLAVE_ESTUDIANTE}  ·  {prefs}  ·  idioma={e['idioma']}")
        if args.roster:
            for cid in cursos_ids:
                _inscribir(cid, e)

    if args.roster:
        print("\nListo. Los 10 estudiantes están inscritos en los 3 cursos (--roster).")
    else:
        print("\nListo. Cuentas creadas; inscribe alumnos desde el panel del docente o usa --roster.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
