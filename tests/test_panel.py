from app import create_app
from services import cursos as svc


DOCENTE = {
    "id": "22222222-2222-2222-2222-222222222222",
    "rol": "docente",
    "nombre": "Doc",
    "email": "d@x.com",
    "token": "t",
}


def test_raiz_redirige_a_entrar():
    c = create_app().test_client()
    resp = c.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/entrar" in resp.headers["Location"]


def test_cursos_sin_sesion_redirige():
    c = create_app().test_client()
    resp = c.get("/docente/cursos", follow_redirects=False)
    assert resp.status_code == 302
    assert "/entrar" in resp.headers["Location"]


def test_cursos_con_docente_muestra_titulo(monkeypatch):
    def fake_usuario():
        from flask import g

        g.usuario = DOCENTE
        return DOCENTE

    monkeypatch.setattr("services.auth.usuario_actual", fake_usuario)
    monkeypatch.setattr(svc, "listar_cursos", lambda did: [{"id": "c1", "nombre_curso": "Biología", "descripcion": ""}])
    c = create_app().test_client()
    resp = c.get("/docente/cursos")
    assert resp.status_code == 200
    assert "Biología".encode() in resp.data
    assert "Tus cursos".encode() in resp.data
    assert b'id="nivel_educativo"' in resp.data
    assert "CINE 1 - Primaria inicial (6 a 8 años)".encode() in resp.data
    assert "CINE 1 - Primaria avanzada (9 a 11 años)".encode() in resp.data
    assert "CINE 2 - Secundaria inferior / Ciclo básico (12 a 14 años)".encode() in resp.data
    assert "CINE 3 - Secundaria superior / Bachillerato (15 a 17 años)".encode() in resp.data
    assert "CINE 6+ - Educación Terciaria / Superior (18+ años)".encode() in resp.data
    assert b'name="nivel_educativo"' in resp.data


def test_crear_curso_exige_nivel_cine():
    try:
        svc.crear_curso("d1", "Biología", "", "")
        assert False
    except ValueError as exc:
        assert "nivel" in str(exc).lower()


def test_crear_curso_guarda_codigo_y_etiqueta(monkeypatch):
    capturado = {}

    class Db:
        def table(self, n):
            return self

        def insert(self, campos):
            capturado.update(campos)
            return self

        def execute(self):
            class R:
                data = [{**capturado, "id": "c1"}]

            return R()

    monkeypatch.setattr(svc, "get_service_client", lambda: Db())
    out = svc.crear_curso("d1", "Álgebra", "", "cine_2")
    assert out["nivel_educativo"] == "cine_2"
    assert out["nivel_educativo_etiqueta"] == "CINE 2 - Secundaria inferior / Ciclo básico (12 a 14 años)"
    assert capturado["nivel_educativo"] == "cine_2"
    assert capturado["nivel_educativo_etiqueta"].startswith("CINE 2")


def test_guardar_edicion_marca_docente_e_incrementa_version(monkeypatch):
    class Db:
        def table(self, n):
            self.n = n
            return self

        def select(self, *a):
            return self

        def eq(self, *a):
            return self

        def limit(self, n):
            return self

        def update(self, campos):
            self.campos = campos
            return self

        def execute(self):
            class R:
                data = [{"id": "p1", "version": 1}] if not getattr(self, "campos", None) else [{**self.campos, "id": "p1"}]

            return R()

    monkeypatch.setattr(svc, "get_service_client", lambda: Db())
    out = svc.guardar_edicion("s1", "modo_enfoque", {"pildoras": []})
    assert out["editado_por_docente"] is True
    assert out["version"] == 2


def test_publicar_solo_en_revision(monkeypatch):
    class Db:
        def table(self, n):
            return self

        def select(self, *a):
            return self

        def eq(self, *a):
            self.estado_fila = {"estado": "procesando"}
            return self

        def limit(self, n):
            return self

        def execute(self):
            class R:
                data = [self.estado_fila]

            return R()

    monkeypatch.setattr(svc, "get_service_client", lambda: Db())
    try:
        svc.publicar_sesion("s1")
        assert False
    except ValueError as exc:
        assert "revisión" in str(exc)
