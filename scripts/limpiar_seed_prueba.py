"""Elimina usuarios y cursos creados por seed_prueba.py. No toca prisma.local ni «Curso de prueba».

Uso: python scripts/limpiar_seed_prueba.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import cursos as svc_cursos  # noqa: E402
from services.datos_prueba import CURSOS, DOCENTES, ESTUDIANTES  # noqa: E402
from services.supabase_client import get_service_client  # noqa: E402

PROTEGIDOS = {
    "docente.prueba@prisma.local",
    "estudiante.prueba@prisma.local",
}
CURSO_PROTEGIDO = "Curso de prueba"


def _uids_por_emails(emails: set[str]) -> list[str]:
    uids = []
    for email in sorted(emails):
        if email in PROTEGIDOS:
            continue
        user = svc_cursos._usuario_por_email(email)
        if user and getattr(user, "id", None):
            uids.append(user.id)
    return uids


def _borrar_cursos_seed(db) -> int:
    nombres = {c["nombre"] for c in CURSOS}
    nombres.discard(CURSO_PROTEGIDO)
    borrados = 0
    for nombre in sorted(nombres):
        filas = db.table("cursos").select("id, nombre_curso").eq("nombre_curso", nombre).execute().data or []
        for fila in filas:
            db.table("cursos").delete().eq("id", fila["id"]).execute()
            borrados += 1
            print(f"  Curso eliminado: {fila['nombre_curso']}")
    return borrados


def _limpiar_filas_estudiante(db, uid: str) -> None:
    db.table("inscripciones_curso").delete().eq("estudiante_id", uid).execute()
    db.table("interacciones_progreso").delete().eq("estudiante_id", uid).execute()
    db.table("chat_cuota_diaria").delete().eq("estudiante_id", uid).execute()
    convs = db.table("conversaciones_chat").select("id").eq("estudiante_id", uid).execute().data or []
    for c in convs:
        db.table("conversaciones_chat").delete().eq("id", c["id"]).execute()


def _borrar_usuarios(admin, db, emails: set[str]) -> int:
    n = 0
    for email in sorted(emails):
        if email in PROTEGIDOS:
            print(f"  (omitido) {email}")
            continue
        user = svc_cursos._usuario_por_email(email)
        if not user or not getattr(user, "id", None):
            print(f"  (no existe) {email}")
            continue
        uid = user.id
        _limpiar_filas_estudiante(db, uid)
        db.table("perfiles").delete().eq("id", uid).execute()
        admin.delete_user(uid)
        n += 1
        print(f"  Usuario eliminado: {email}")
    return n


def main() -> int:
    db = get_service_client()
    admin = db.auth.admin
    emails = {e["email"] for e in ESTUDIANTES} | {d["email"] for d in DOCENTES}

    print("== Cursos del seed (Prueba DUA) ==")
    cursos = _borrar_cursos_seed(db)
    print(f"Total cursos eliminados: {cursos}")

    print("\n== Usuarios @prueba.com del seed ==")
    usuarios = _borrar_usuarios(admin, db, emails)
    print(f"Total usuarios eliminados: {usuarios}")

    print("\nListo. Conservados: docente/estudiante.prisma.local y «Curso de prueba».")
    print("Para recrear el docente/curso original: python scripts/smoke_upload.py && python scripts/smoke_estudiante.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
