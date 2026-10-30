from services import dua


def test_normalizar_mapea_formatos_viejos_y_combina():
    out = dua.normalizar_preferencias(["alto_contraste", "tdah", "alto_contraste", "inventado"])
    assert out == ["baja_vision", "tdah"]


def test_catalogo_tiene_seis_necesidades_y_lenguas():
    codigos = [n["codigo"] for n in dua.NECESIDADES]
    assert codigos == ["ceguera", "baja_vision", "dislexia", "tdah", "apoyo_visual", "lengua"]
    assert {l["codigo"] for l in dua.LENGUAS} >= {"es", "qu", "ay"}


def test_traducir_mismo_idioma_no_llama_ia(monkeypatch):
    monkeypatch.setattr(
        "services.dua.ai_router.groq_texto",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debe llamar IA")),
    )
    assert dua.traducir("Hola clase", "es") == "Hola clase"


def test_validar_idioma_conocido_sin_ia(monkeypatch):
    monkeypatch.setattr(
        "services.dua.ai_router.groq_texto",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debe llamar IA")),
    )
    out = dua.validar_idioma("Quechua")
    assert out["valido"] is True
    assert out["nombre"] == "Quechua"
    assert out["codigo"].startswith("qu")
    assert out["audio"] is False


def test_validar_idioma_invalido_con_ia(monkeypatch):
    from services import ai_router

    monkeypatch.setattr("services.dua.cache_ia.buscar", lambda *a, **k: None)
    monkeypatch.setattr("services.dua.cache_ia.guardar", lambda *a, **k: None)
    monkeypatch.setattr(
        "services.dua.ai_router.groq_texto",
        lambda *a, **k: ai_router.RespuestaIA(texto='{"valido": false, "nombre": "", "codigo": ""}', modelo="lite"),
    )
    out = dua.validar_idioma("xyzzyfoo")
    assert out["valido"] is False


def test_adaptar_a_lengua_rechaza_inventada(monkeypatch):
    monkeypatch.setattr("services.dua.validar_idioma", lambda n: {"valido": False, "nombre": n, "codigo": ""})
    out = dua.adaptar_a_lengua("La fotosíntesis convierte luz en energía.", "idiomainventado")
    assert out["valido"] is False
    assert "no fue reconocido" in out["error"]
    assert "fotosíntesis" in out["texto"]


def test_traducir_usa_json_de_ia(monkeypatch):
    from services import ai_router

    monkeypatch.setattr("services.dua.cache_ia.buscar", lambda *a, **k: None)
    monkeypatch.setattr("services.dua.cache_ia.guardar", lambda *a, **k: None)
    monkeypatch.setattr(
        "services.dua.ai_router.groq_texto",
        lambda *a, **k: ai_router.RespuestaIA(
            texto='{"texto": "Rimayku kay clase de ciencias naturales."}',
            modelo="lite",
        ),
    )
    assert "Rimayku" in dua.traducir("Hola clase de ciencias naturales.", "qu")
