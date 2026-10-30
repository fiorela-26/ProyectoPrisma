from app import create_app
from config import settings
from services import rate_limit


def test_privacidad_y_cabeceras():
    c = create_app().test_client()
    resp = c.get("/privacidad")
    assert resp.status_code == 200
    assert "Ley 29733".encode() in resp.data
    assert "menores".encode() in resp.data.lower() or "menor".encode() in resp.data.lower()
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    html = resp.get_data(as_text=True)
    if settings.SUPABASE_SERVICE_KEY:
        assert settings.SUPABASE_SERVICE_KEY not in html
    assert "service_role" not in html


def test_html_publico_no_filtra_claves():
    c = create_app().test_client()
    secretos = [
        settings.SUPABASE_SERVICE_KEY,
        settings.GROQ_API_KEY,
        settings.GEMINI_API_KEY,
        settings.HUGGINGFACE_API_TOKEN,
        settings.HF_TOKEN,
        settings.CLOUDFLARE_API_TOKEN,
        settings.CLOUDFLARE_ACCOUNT_ID,
    ]
    for ruta in ("/entrar", "/offline", "/static/js/pwa.js", "/static/js/estudiante.js"):
        html = c.get(ruta).get_data(as_text=True)
        for clave in secretos:
            if clave:
                assert clave not in html


def test_rate_limit_bloquea_exceso():
    rate_limit.reiniciar()
    rate_limit.comprobar("t", 2, ventana_s=60)
    rate_limit.comprobar("t", 2, ventana_s=60)
    try:
        rate_limit.comprobar("t", 2, ventana_s=60)
        assert False
    except rate_limit.DemasiadoRapido:
        pass
    rate_limit.reiniciar()
