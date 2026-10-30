from services import jobs


def test_reintento_reencola_si_queda_margen(monkeypatch):
    actualizaciones = []
    monkeypatch.setattr(jobs, "_actualizar_job", lambda jid, **c: actualizaciones.append(c))
    monkeypatch.setattr(jobs, "_job_extraer", lambda job: (_ for _ in ()).throw(RuntimeError("fallo transitorio")))
    monkeypatch.setattr(jobs, "_es_reintentable", lambda exc: True)
    monkeypatch.setattr(jobs.time, "sleep", lambda s: None)
    monkeypatch.setattr(jobs, "obtener_job", lambda jid: {"id": jid, "estado": actualizaciones[-1]["estado"]})
    monkeypatch.setattr(jobs, "get_service_client", lambda: None)

    final = jobs.ejecutar_job({"id": "j1", "tipo": "extraer", "intentos": 0, "sesion_id": "s1"})
    estados = [c.get("estado") for c in actualizaciones if "estado" in c]
    assert "queued" in estados
    assert "failed" not in estados
    assert final["estado"] == "queued"


def test_tercer_intento_marca_failed(monkeypatch):
    actualizaciones = []
    sesion_error = []

    class Db:
        def table(self, n):
            return self

        def update(self, campos):
            sesion_error.append(campos)
            return self

        def eq(self, *a, **k):
            return self

        def execute(self):
            return None

    monkeypatch.setattr(jobs, "_actualizar_job", lambda jid, **c: actualizaciones.append(c))
    monkeypatch.setattr(jobs, "_job_extraer", lambda job: (_ for _ in ()).throw(RuntimeError("sigue fallando")))
    monkeypatch.setattr(jobs, "_es_reintentable", lambda exc: True)
    monkeypatch.setattr(jobs.time, "sleep", lambda s: None)
    monkeypatch.setattr(jobs, "obtener_job", lambda jid: {"id": jid, "estado": actualizaciones[-1]["estado"]})
    monkeypatch.setattr(jobs, "get_service_client", lambda: Db())

    final = jobs.ejecutar_job({"id": "j1", "tipo": "extraer", "intentos": 2, "sesion_id": "s1"})
    assert final["estado"] == "failed"
    assert sesion_error[0]["estado"] == "error"


def test_ffmpeg_faltante_no_reintenta(monkeypatch):
    from services.transcriber import FfmpegNoDisponible

    actualizaciones = []
    monkeypatch.setattr(jobs, "_actualizar_job", lambda jid, **c: actualizaciones.append(c))
    monkeypatch.setattr(jobs, "_job_extraer", lambda job: (_ for _ in ()).throw(FfmpegNoDisponible("no ffmpeg")))
    monkeypatch.setattr(jobs.time, "sleep", lambda s: None)
    monkeypatch.setattr(jobs, "obtener_job", lambda jid: {"id": jid, "estado": actualizaciones[-1]["estado"]})

    class Db:
        def table(self, n):
            return self

        def update(self, c):
            return self

        def eq(self, *a, **k):
            return self

        def execute(self):
            return None

    monkeypatch.setattr(jobs, "get_service_client", lambda: Db())
    final = jobs.ejecutar_job({"id": "j1", "tipo": "extraer", "intentos": 0, "sesion_id": "s1"})
    assert final["estado"] == "failed"
    assert not any(c.get("estado") == "queued" for c in actualizaciones)


def test_polling_job_requiere_auth(client=None):
    from app import create_app

    c = create_app(con_worker=False).test_client()
    resp = c.get("/jobs/11111111-1111-1111-1111-111111111111")
    assert resp.status_code == 401
