from pathlib import Path

from services import ai_router, mediacion

SESION = {
    "id": "s1",
    "titulo": "El bloqueo naval",
    "contenido_hash": "abc123",
    "texto_extraido": "La escuadra rodeó el puerto para que nadie pudiera entrar ni salir.",
    "nivel_educativo_etiqueta": "CINE 2 - Secundaria inferior / Ciclo básico (12 a 14 años)",
}

JSON_OK = (
    '{"pauta_docente":"Utilice un mapa físico o digital para trazar las rutas marítimas '
    'mencionadas en el texto y facilitar la comprensión espacial de los estudiantes '
    'antes de debatir las decisiones estratégicas.",'
    '"pauta_estudiante":"Puedes marcar en un mapa los puertos del texto y explicar '
    'con tus palabras por qué un bloqueo cierra la entrada y la salida.",'
    '"glosario":[{"termino":"Bloqueo","definicion":"Cercar un puerto con barcos para que nadie pueda entrar ni salir."},'
    '{"termino":"Escuadra","definicion":"Conjunto de barcos de guerra de un país."},'
    '{"termino":"Estrategia","definicion":"Plan cuidadosamente pensado para lograr un objetivo."}]}'
)


def test_json_ia_limpia_cercas():
    datos = mediacion._json_ia("```json\n{\"pauta_docente\":\"ok ok ok ok ok ok ok\"}\n```")
    assert datos["pauta_docente"].startswith("ok")


def test_glosario_descarta_vacios_y_limita():
    items = [{"termino": "A", "definicion": "corta"}] + [
        {"termino": f"Termino{i}", "definicion": f"Definición suficientemente larga {i}"}
        for i in range(12)
    ]
    out = mediacion._limpiar_glosario(items)
    assert len(out) == 8
    assert out[0]["termino"] == "Termino0"


def test_para_sesion_sin_texto():
    out = mediacion.para_sesion({"titulo": "X", "texto_extraido": ""})
    assert out["estado"] == "sin_texto"
    assert out["glosario"] == []
    assert out["pauta_docente"] == ""


def test_para_sesion_usa_ia_y_datos(monkeypatch):
    visto = {}

    def fake(mensajes, **k):
        visto["mensajes"] = mensajes
        visto["json_mode"] = k.get("json_mode", False)
        return ai_router.RespuestaIA(texto=JSON_OK, modelo="lite")

    monkeypatch.setattr("services.mediacion.ai_router.groq_texto", fake)
    monkeypatch.setattr("services.mediacion.cache_ia.buscar", lambda *a, **k: None)
    monkeypatch.setattr("services.mediacion.cache_ia.guardar", lambda *a, **k: None)
    out = mediacion.para_sesion(SESION)
    assert out["estado"] == "lista"
    assert "mapa" in out["pauta_docente"].lower()
    assert "puertos" in out["pauta_estudiante"].lower()
    assert out["glosario"][0]["termino"] == "Bloqueo"
    assert visto["json_mode"] is True
    user = visto["mensajes"][1]["content"]
    assert "<DATOS>" in user and "</DATOS>" in user
    assert "El bloqueo naval" in user
    assert "CINE 2" in user
    assert "pauta_docente" in user
    assert "pauta_estudiante" in user


def test_para_sesion_usa_cache(monkeypatch):
    monkeypatch.setattr(
        "services.mediacion.cache_ia.buscar",
        lambda *a, **k: {
            "pauta_docente": "Invite al grupo a representar el bloqueo con fichas.",
            "pauta_estudiante": "Fíjate qué puertos quedaron cerrados y por qué.",
            "glosario": [{"termino": "Puerto", "definicion": "Lugar donde llegan y salen los barcos."}],
            "origen": "ia",
        },
    )

    def boom(*a, **k):
        raise AssertionError("no debe llamar a Groq si hay caché")

    monkeypatch.setattr("services.mediacion.ai_router.groq_texto", boom)
    out = mediacion.para_sesion(SESION)
    assert out["estado"] == "lista"
    assert "fichas" in out["pauta_docente"]
    assert out["glosario"][0]["termino"] == "Puerto"


def test_fallback_local_si_ia_falla(monkeypatch):
    monkeypatch.setattr("services.mediacion.cache_ia.buscar", lambda *a, **k: None)
    monkeypatch.setattr("services.mediacion.cache_ia.guardar", lambda *a, **k: None)
    monkeypatch.setattr(
        "services.mediacion.ai_router.groq_texto",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("sin red")),
    )
    out = mediacion.para_sesion(SESION)
    assert out["origen"] == "local"
    assert "bloqueo naval" in out["pauta_docente"].lower()
    assert "bloqueo naval" in out["pauta_estudiante"].lower()


def test_plantillas_y_js_separan_roles():
    root = Path(__file__).resolve().parents[1]
    docente = (root / "templates" / "docente" / "sesion.html").read_text(encoding="utf-8")
    estudiante = (root / "templates" / "estudiante" / "sesion.html").read_text(encoding="utf-8")
    parcial = (root / "templates" / "_mediacion.html").read_text(encoding="utf-8")
    js = (root / "static" / "js" / "mediacion.js").read_text(encoding="utf-8")
    assert '{% include "_mediacion.html" %}' in docente
    assert '{% include "_mediacion.html" %}' in estudiante
    assert "mediacion.js" in docente and "mediacion.js" in estudiante
    assert "Pauta de mediación para el docente" in parcial
    assert "Pauta de apoyo para estudiar" in parcial
    assert "Glosario de apoyo" in parcial
    assert "pauta_docente" in js and "pauta_estudiante" in js
    assert 'data-med-rol' in parcial
