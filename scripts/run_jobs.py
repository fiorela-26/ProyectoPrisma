"""Ejecuta manualmente los jobs en cola (hasta que exista el worker automático de la Microfase 2.5).

Uso:
  python scripts/run_jobs.py            # procesa hasta 10 jobs en cola
  python scripts/run_jobs.py <job_id>   # procesa un job concreto
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import jobs  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def main():
    if len(sys.argv) > 1:
        job = jobs.obtener_job(sys.argv[1])
        pendientes = [job] if job else []
    else:
        pendientes = jobs.jobs_en_cola()

    if not pendientes:
        print("No hay jobs en cola.")
        return 0

    fallidos = 0
    for job in pendientes:
        print(f"-> job {job['id']} ({job['tipo']}) ...", end=" ", flush=True)
        final = jobs.ejecutar_job(job)
        print(final["estado"], f"[{final.get('formato') or ''}]", final.get("error") or "")
        fallidos += final["estado"] == "failed"
    return 1 if fallidos else 0


if __name__ == "__main__":
    sys.exit(main())
