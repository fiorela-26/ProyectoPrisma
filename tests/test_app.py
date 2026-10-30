import httpx

from app import create_app


def test_ping():
    client = create_app().test_client()
    resp = client.get("/ping")
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}


def test_corte_de_red_no_muestra_traceback():
    app = create_app(con_worker=False)

    @app.get("/__boom_red")
    def boom_red():
        raise httpx.ReadError("WinError 10035")

    resp = app.test_client().get("/__boom_red")
    html = resp.get_data(as_text=True)
    assert resp.status_code == 503
    assert "Recargar" in html
    assert "Traceback" not in html
    assert "httpx.ReadError" not in html


def test_cliente_supabase_desactiva_http2():
    from services.supabase_client import _httpx_cliente

    cliente = _httpx_cliente()
    try:
        assert cliente._transport._pool._http2 is False
    finally:
        cliente.close()


def test_health_config_lists_missing_vars():
    client = create_app().test_client()
    resp = client.get("/health/config")
    assert resp.status_code == 200
    assert isinstance(resp.get_json()["faltantes"], list)
