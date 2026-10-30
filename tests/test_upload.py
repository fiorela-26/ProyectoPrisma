import io

import pytest

from app import create_app
from services import materiales

CURSO = "11111111-1111-1111-1111-111111111111"
DOCENTE = {"id": "22222222-2222-2222-2222-222222222222", "rol": "docente", "nombre": "Doc", "email": "d@x.com"}


@pytest.fixture
def client():
    return create_app().test_client()


def _post(client, nombre="clase1.pdf", contenido=b"%PDF-1.4 hola", titulo="Clase 1"):
    data = {"archivo": (io.BytesIO(contenido), nombre), "titulo": titulo}
    return client.post(f"/cursos/{CURSO}/materiales", data=data, content_type="multipart/form-data",
                       headers={"Authorization": "Bearer token-falso"})


def test_sin_token_devuelve_401(client):
    resp = client.post(f"/cursos/{CURSO}/materiales", data={}, content_type="multipart/form-data")
    assert resp.status_code == 401


def test_office_e_imagen_se_aceptan(client, monkeypatch):
    monkeypatch.setattr("services.auth.usuario_actual", lambda: _con_g(DOCENTE))
    monkeypatch.setattr("routes.docente.materiales.docente_es_dueno", lambda c, d: True)
    monkeypatch.setattr(materiales.storage, "upload_bytes", lambda ruta, datos, ct: ruta)
    monkeypatch.setattr(materiales, "get_service_client", lambda: _DbFalsa())
    monkeypatch.setattr(materiales.jobs, "crear_job", lambda sesion_id, tipo, formato=None: {"id": "job-1", "tipo": tipo})
    for nombre, esperado in (
        ("clase.docx", "word"),
        ("clase.pptx", "presentacion"),
        ("clase.xlsx", "hoja"),
        ("foto.png", "imagen"),
        ("notas.txt", "texto"),
    ):
        resp = _post(client, nombre=nombre, contenido=b"PK\x03\x04contenido")
        assert resp.status_code == 202, nombre
        assert resp.get_json()["tipo_archivo"] == esperado


def test_extension_no_permitida(client, monkeypatch):
    monkeypatch.setattr("services.auth.usuario_actual", lambda: _con_g(DOCENTE))
    monkeypatch.setattr("routes.docente.materiales.docente_es_dueno", lambda c, d: True)
    resp = _post(client, nombre="virus.exe")
    assert resp.status_code == 400
    assert "no permitido" in resp.get_json()["error"]


def test_subida_correcta_devuelve_202_con_job(client, monkeypatch):
    monkeypatch.setattr("services.auth.usuario_actual", lambda: _con_g(DOCENTE))
    monkeypatch.setattr("routes.docente.materiales.docente_es_dueno", lambda c, d: True)
    subidas = []
    monkeypatch.setattr(materiales.storage, "upload_bytes", lambda ruta, datos, ct: subidas.append((ruta, ct)) or ruta)
    monkeypatch.setattr(materiales, "get_service_client", lambda: _DbFalsa())
    monkeypatch.setattr(materiales.jobs, "crear_job", lambda sesion_id, tipo, formato=None: {"id": "job-1", "tipo": tipo})

    resp = _post(client)
    assert resp.status_code == 202
    cuerpo = resp.get_json()
    assert cuerpo["job_id"] == "job-1"
    assert cuerpo["sesion_id"] == "sesion-1"
    assert cuerpo["tipo_archivo"] == "pdf"
    assert cuerpo["hash"] == materiales.sha256_bytes(b"%PDF-1.4 hola")
    assert subidas[0][0] == f"{CURSO}/{cuerpo['hash']}.pdf"
    assert subidas[0][1] == "application/pdf"


def test_subida_sin_titulo_usa_nombre_del_archivo(client, monkeypatch):
    monkeypatch.setattr("services.auth.usuario_actual", lambda: _con_g(DOCENTE))
    monkeypatch.setattr("routes.docente.materiales.docente_es_dueno", lambda c, d: True)
    monkeypatch.setattr(materiales.storage, "upload_bytes", lambda ruta, datos, ct: ruta)
    db = _DbFalsa()
    monkeypatch.setattr(materiales, "get_service_client", lambda: db)
    monkeypatch.setattr(materiales.jobs, "crear_job", lambda sesion_id, tipo, formato=None: {"id": "job-1", "tipo": tipo})
    resp = _post(client, titulo="")
    assert resp.status_code == 202
    assert db._fila["titulo"] == "clase1.pdf"


def test_previsualizar_no_crea_sesion(monkeypatch):
    monkeypatch.setattr(materiales.storage, "upload_bytes", lambda ruta, datos, ct: ruta)
    monkeypatch.setattr("services.extractor.extraer", lambda *a, **k: type("R", (), {"texto": "Clic para agregar\nLa mitocondria produce ATP."})())
    monkeypatch.setattr(
        "services.extractor.preparar_clase",
        lambda t, idioma="es", fallback_titulo="Sesión", nivel_educativo="": {
            "titulo": "La mitocondria",
            "texto": "## Resumen\nLa mitocondria produce ATP.",
        },
    )
    previa = materiales.previsualizar_material(CURSO, "", "clase.pptx", b"PK\x03\x04abc")
    assert previa["tipo"] == "presentacion"
    assert previa["titulo"] == "La mitocondria"
    assert "mitocondria" in previa["texto"]
    assert previa["ruta"].startswith(CURSO + "/")


def test_previsualizar_pasa_nivel_cine(monkeypatch):
    visto = {}
    monkeypatch.setattr(
        "services.cursos.nivel_de_curso",
        lambda cid: {
            "nivel_educativo": "cine_1_inicial",
            "nivel_educativo_etiqueta": "CINE 1 - Primaria inicial (6 a 8 años)",
        },
    )
    monkeypatch.setattr(
        "services.extractor.extraer",
        lambda *a, **k: type("R", (), {"texto": "La fotosintesis convierte luz en energia."})(),
    )

    def fake_prep(t, idioma="es", fallback_titulo="Sesión", nivel_educativo=""):
        visto["nivel"] = nivel_educativo
        return {"titulo": "Fotosíntesis", "texto": "## Resumen\nLas plantas convierten luz en energía."}

    monkeypatch.setattr("services.extractor.preparar_clase", fake_prep)
    previa = materiales.previsualizar_material(CURSO, "", "clase.pdf", b"%PDF-1.4")
    assert visto["nivel"] == "CINE 1 - Primaria inicial (6 a 8 años)"
    assert previa["titulo"] == "Fotosíntesis"


def test_previsualizar_desde_titulo(monkeypatch):
    monkeypatch.setattr(
        "services.cursos.nivel_de_curso",
        lambda cid: {"nivel_educativo": "cine_2", "nivel_educativo_etiqueta": "CINE 2 - Secundaria inferior / Ciclo básico (12 a 14 años)"},
    )
    visto = {}

    def fake_gen(titulo, idioma="es", nivel_educativo=""):
        visto["titulo"] = titulo
        visto["nivel"] = nivel_educativo
        return {"titulo": titulo, "texto": "## Resumen\nLa fotosíntesis convierte luz en energía."}

    monkeypatch.setattr("services.extractor.generar_clase_desde_titulo", fake_gen)
    previa = materiales.previsualizar_desde_titulo(CURSO, "La fotosíntesis")
    assert previa["tipo"] == "tema"
    assert previa["titulo"] == "La fotosíntesis"
    assert "fotosíntesis" in previa["texto"]
    assert visto["nivel"].startswith("CINE 2")
    assert previa["nombre"] == "Generada desde el título"


def test_previsualizar_desde_titulo_exige_tema():
    try:
        materiales.previsualizar_desde_titulo(CURSO, "ab")
        assert False
    except materiales.MaterialInvalido:
        pass


def test_confirmar_material_crea_revision(monkeypatch):
    db = _DbFalsa()
    monkeypatch.setattr(materiales, "get_service_client", lambda: db)
    monkeypatch.setattr(materiales.storage, "upload_bytes", lambda ruta, datos, ct: ruta)
    monkeypatch.setattr("services.package_builder.guardar_paquete", lambda *a, **k: None)
    monkeypatch.setattr("services.package_builder.generar", lambda *a, **k: {"contenido": {}, "generado_por_ia": False})
    materiales._guardar_previa("abc", b"PK", {"curso_id": CURSO, "content_type": "application/octet-stream"})
    sesion = materiales.confirmar_material(
        CURSO, "La mitocondria", "La mitocondria produce ATP.", f"{CURSO}/abc.pptx", "abc", "presentacion"
    )
    assert sesion["estado"] == "revision"
    assert sesion["texto_extraido"].startswith("La mitocondria")
    assert db._fila["titulo"] == "La mitocondria"


def test_confirmar_tema_no_sube_archivo(monkeypatch):
    subidas = []
    db = _DbFalsa()
    monkeypatch.setattr(materiales, "get_service_client", lambda: db)
    monkeypatch.setattr(materiales.storage, "upload_bytes", lambda *a, **k: subidas.append(a))
    monkeypatch.setattr("services.package_builder.guardar_paquete", lambda *a, **k: None)
    monkeypatch.setattr("services.package_builder.generar", lambda *a, **k: {"contenido": {}, "generado_por_ia": False})
    materiales._guardar_previa("h1", b"", {"curso_id": CURSO, "content_type": "text/plain", "tipo": "tema"})
    sesion = materiales.confirmar_material(
        CURSO, "La célula", "## Resumen\nUnidad de la vida.", f"{CURSO}/tema-h1", "h1", "tema"
    )
    assert subidas == []
    assert sesion["archivo_url"] is None
    assert db._fila["tipo_archivo"] == "tema"
    assert db._fila["titulo"] == "La célula"


def test_confirmar_rechaza_ruta_de_otro_curso():
    materiales._guardar_previa("abc", b"PK", {"curso_id": CURSO, "content_type": "application/octet-stream"})
    try:
        materiales.confirmar_material("otro", "T", "texto de clase", f"{CURSO}/abc.pptx", "abc", "presentacion")
        assert False
    except materiales.MaterialInvalido:
        pass


def test_titulo_provisional_y_inferencia():
    assert materiales.titulo_provisional("  Célula  ", "x.pdf") == "Célula"
    assert materiales.titulo_provisional("", "unidad2.pptx") == "unidad2.pptx"
    assert materiales.debe_inferir_titulo("unidad2.pptx") is True
    assert materiales.debe_inferir_titulo("La célula") is False
    assert materiales.debe_inferir_titulo("") is True


def test_hash_es_sha256_estable():
    assert materiales.sha256_bytes(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def _con_g(usuario):
    from flask import g

    g.usuario = usuario
    return usuario


class _DbFalsa:
    """Simula lo mínimo de supabase-py usado por registrar_material."""

    def table(self, nombre):
        assert nombre == "sesiones_material"
        return self

    def insert(self, fila):
        assert fila["estado"] in ("procesando", "revision")
        assert fila["curso_id"] == CURSO
        self._fila = fila
        return self

    def execute(self):
        class R:
            data = [{"id": "sesion-1", **self._fila}]

        return R()
