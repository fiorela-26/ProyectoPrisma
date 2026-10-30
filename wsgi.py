"""Entrada de producción: Gunicorn carga este módulo y arranca el worker de jobs."""
from app import create_app

app = create_app(con_worker=True)
