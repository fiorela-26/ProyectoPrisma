from app import create_app
from services import analitica, estudiante as est
from services import chat_service
from services import cursos as svc
from services import materiales

EST = {
    "id": "33333333-3333-3333-3333-333333333333",
    "rol": "estudiante",
    "nombre": "Alu",
    "email": "a@x.com",
    "token": "t",
}
DOCENTE = {
    "id": "22222222-2222-2222-2222-222222222222",
    "rol": "docente",
    "nombre": "Doc",
    "email": "d@x.com",
    "token": "t",
}
SID = "11111111-1111-1111-1111-111111111111"
CID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _con_g(usuario):
    from flask import g

    g.usuario = usuario
    return usuario


def test_registrar_clampa_duracion_e_ignora_formato_invalido(monkeypatch):
    inserted = []

    class Db:
        def table(self, n):
            return self

        def insert(self, fila):
            inserted.append(fila)
            return self

        def execute(self):
            class R:
                data = [inserted[-1]]

            return R()

    monkeypatch.setattr(analitica, "get_service_client", lambda: Db())
    out = analitica.registrar("e1", "s1", "hack", 999999, False)
    assert out["formato_usado"] is None
    assert out["duracion_segundos"] == 24 * 3600
    analitica.registrar("e1", "s1", "modo_enfoque", "no-num", True)
    assert inserted[-1]["formato_usado"] == "modo_enfoque"
    assert inserted[-1]["duracion_segundos"] == 0
    assert inserted[-1]["completado"] is True


def test_preguntas_frecuentes_agrupa_y_omite_identidad(monkeypatch):
    class Db:
        def table(self, n):
            self.n = n
            return self

        def select(self, *a):
            return self

        def eq(self, *a):
            return self

        def in_(self, *a):
            return self

        def execute(self):
            class R:
                data = []

            if self.n == "conversaciones_chat":
                R.data = [{"id": "c1"}]
            else:
                R.data = [
                    {"contenido": "¿Qué es la célula?", "rol": "user"},
                    {"contenido": "¿qué es la célula?", "rol": "user"},
                    {"contenido": f"{chat_service.MARCA_DUDA}\n¿Qué es la célula?", "rol": "user"},
                    {"contenido": "ok", "rol": "user"},
                ]
            return R()

    monkeypatch.setattr(analitica, "get_service_client", lambda: Db())
    out = analitica.preguntas_frecuentes("s1")
    assert out[0]["veces"] == 3
    assert "célula" in out[0]["pregunta"]
    assert all("email" not in p and "estudiante" not in p for p in out)


def test_resumen_curso_barras_sin_nombres(monkeypatch):
    class Db:
        def table(self, n):
            self.n = n
            return self

        def select(self, *a):
            return self

        def eq(self, *a):
            return self

        def in_(self, *a):
            return self

        def execute(self):
            class R:
                data = []

            if self.n == "sesiones_material":
                R.data = [{"id": SID, "titulo": "Célula", "estado": "publicado"}]
            elif self.n == "interacciones_progreso":
                R.data = [
                    {"sesion_id": SID, "formato_usado": "modo_enfoque", "duracion_segundos": 10, "completado": True},
                    {"sesion_id": SID, "formato_usado": "modo_enfoque", "duracion_segundos": 5, "completado": False},
                    {"sesion_id": SID, "formato_usado": "alto_contraste", "duracion_segundos": 2, "completado": False},
                ]
            elif self.n == "conversaciones_chat":
                R.data = []
            return R()

    monkeypatch.setattr(analitica, "get_service_client", lambda: Db())
    r = analitica.resumen_curso(CID)
    assert r["total_interacciones"] == 3
    assert r["formatos"][0]["clave"] == "modo_enfoque"
    assert r["formatos"][0]["pct"] == 100
    assert r["sesiones"][0]["completadas"] == 1
    blob = str(r)
    assert "Alu" not in blob and "a@x.com" not in blob


def test_interacciones_sin_auth_401():
    c = create_app().test_client()
    resp = c.post("/estudiante/interacciones", json={"sesion_id": SID})
    assert resp.status_code == 401


def test_interacciones_registra_beacon(monkeypatch):
    vistos = []
    regs = []
    monkeypatch.setattr("services.auth.usuario_actual", lambda: _con_g(EST))
    monkeypatch.setattr(est, "sesion_visible", lambda s, e: vistos.append((s, e)) or ({"id": s}, {}))
    monkeypatch.setattr(analitica, "registrar", lambda *a: regs.append(a) or {})
    c = create_app().test_client()
    resp = c.post(
        "/estudiante/interacciones",
        data='{"sesion_id":"%s","formato":"modo_enfoque","duracion_segundos":12,"completado":true}' % SID,
        content_type="text/plain",
    )
    assert resp.status_code == 204
    assert vistos[0][0] == SID
    assert regs[0][2] == "modo_enfoque"
    assert regs[0][3] == 12
    assert regs[0][4] is True


def test_analitica_docente(monkeypatch):
    monkeypatch.setattr("services.auth.usuario_actual", lambda: _con_g(DOCENTE))
    monkeypatch.setattr(materiales, "docente_es_dueno", lambda cid, did: True)
    monkeypatch.setattr(svc, "listar_cursos", lambda did: [{"id": CID, "nombre_curso": "Biología", "descripcion": ""}])
    monkeypatch.setattr(
        analitica,
        "resumen_curso",
        lambda cid: {
            "total_interacciones": 2,
            "formatos": [{"clave": "modo_enfoque", "nombre": "Modo enfoque (píldoras de aprendizaje)", "usos": 2, "segundos": 15, "pct": 100}],
            "sesiones": [{"id": SID, "titulo": "Célula", "estado": "publicado", "completadas": 1, "preguntas": [{"pregunta": "qué es la célula", "veces": 2}]}],
        },
    )
    c = create_app().test_client()
    resp = c.get(f"/docente/cursos/{CID}/analitica")
    assert resp.status_code == 200
    assert "Analítica".encode() in resp.data
    assert "Modo enfoque".encode() in resp.data
    assert "qué es la célula".encode() in resp.data
    assert b"Alu" not in resp.data


def test_offline_y_pwa_estaticos():
    c = create_app().test_client()
    assert c.get("/offline").status_code == 200
    assert b"Sin conexi" in c.get("/offline").data
    man = c.get("/static/manifest.json")
    assert man.status_code == 200
    assert man.get_json()["display"] == "standalone"
    sw = c.get("/static/service-worker.js")
    assert sw.status_code == 200
    assert b"caches" in sw.data
