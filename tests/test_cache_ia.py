import hashlib

from services import cache_ia, extractor


def test_clave_cambia_con_prompt_o_idioma():
    h = "abc"
    a = cache_ia.clave(h, "ocr-pdf", "es", "ocr-v1")
    b = cache_ia.clave(h, "ocr-pdf", "es", "ocr-v2")
    c = cache_ia.clave(h, "ocr-pdf", "qu", "ocr-v1")
    d = cache_ia.clave(h, "stt", "es", "ocr-v1")
    assert len({a, b, c, d}) == 4
    assert a == hashlib.sha256(b"abc|ocr-pdf|es|ocr-v1").hexdigest()


def test_ocr_reutiliza_cache_sin_llamar_gemini(monkeypatch):
    llamadas = []
    monkeypatch.setattr(extractor, "_tesseract_disponible", lambda: False)
    monkeypatch.setattr(
        extractor.ai_router,
        "gemini_generar",
        lambda *a, **k: llamadas.append(1) or (_ for _ in ()).throw(AssertionError("no debe llamar IA")),
    )
    monkeypatch.setattr(
        extractor.cache_ia,
        "buscar",
        lambda *a, **k: {"texto": "desde caché", "modelo": "modelo-x", "paginas": 1},
    )
    monkeypatch.setattr(extractor.cache_ia, "guardar", lambda *a, **k: None)

    from tests.test_extractor import _pdf_sin_texto

    res = extractor.extraer(_pdf_sin_texto(), "pdf")
    assert res.metodo == "cache"
    assert res.texto == "desde caché"
    assert llamadas == []
