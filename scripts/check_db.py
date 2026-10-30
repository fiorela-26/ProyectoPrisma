"""Verifica que las tablas del esquema existen y que RLS bloquea al cliente anónimo.

Uso: python scripts/check_db.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.supabase_client import get_anon_client, get_service_client  # noqa: E402

TABLAS = [
    "perfiles",
    "cursos",
    "inscripciones_curso",
    "sesiones_material",
    "jobs",
    "paquetes_formato",
    "cache_ia",
    "interacciones_progreso",
    "conversaciones_chat",
    "mensajes_chat",
    "chat_cuota_diaria",
]


def main():
    service = get_service_client()
    anon = get_anon_client()
    ok = True

    print("== Tablas (cliente de servicio) ==")
    for tabla in TABLAS:
        try:
            service.table(tabla).select("*", count="exact").limit(0).execute()
            print(f"  {tabla}: OK")
        except Exception as exc:
            ok = False
            print(f"  {tabla}: ERROR -> {exc}")

    print("\n== RLS (cliente anónimo, sin sesión) ==")
    for tabla in ("jobs", "cache_ia", "perfiles", "mensajes_chat"):
        try:
            res = anon.table(tabla).select("*").limit(1).execute()
            filas = len(res.data)
            estado = "OK (0 filas visibles)" if filas == 0 else f"ATENCION: {filas} filas visibles"
            print(f"  {tabla}: {estado}")
        except Exception as exc:
            print(f"  {tabla}: bloqueado -> {str(exc)[:80]}")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
