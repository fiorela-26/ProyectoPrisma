from app import create_app


def test_entrar_tiene_saltar_etiquetas_y_autocomplete():
    html = create_app().test_client().get("/entrar").get_data(as_text=True)
    assert 'lang="es"' in html
    assert 'href="#contenido"' in html
    assert 'Saltar al contenido' in html
    assert 'for="email"' in html
    assert 'for="password"' in html
    assert 'autocomplete="username"' in html
    assert 'autocomplete="current-password"' in html
    assert 'id="contenido"' in html
    assert "tabindex=\"-1\"" in html
    assert "Privacidad" in html


def test_css_objetivos_tactiles_y_foco():
    css = create_app().test_client().get("/static/css/app.css").get_data(as_text=True)
    assert "min-height: 2.75rem" in css or "min-height:2.75rem" in css
    assert "min-width: 1.5rem" in css or "min-width:1.5rem" in css
    assert ":focus-visible" in css
    assert "scroll-margin-top" in css
    assert "prefers-reduced-motion" in css
    assert "#1f5bff" in css
    assert "backdrop-filter: blur(18px)" in css or "backdrop-filter:blur(18px)" in css
    assert "Figtree" in css
    assert "Sora" in css
    assert "OpenDyslexic" in css
    assert "dua-preview" in css
    assert "img-edu" in css
    assert "med-pauta" in css
    assert "med-glosario" in css
    assert "med-lista" in css
    assert "border-radius:16px" in css or "border-radius: 16px" in css


def test_offline_y_privacidad_saltar():
    c = create_app().test_client()
    off = c.get("/offline").get_data(as_text=True)
    assert 'href="#contenido"' in off
    assert 'lang="es"' in off
    priv = c.get("/privacidad").get_data(as_text=True)
    assert 'href="#contenido"' in priv


def test_health_ia():
    resp = create_app().test_client().get("/health/ia")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "llamadas" in data and "errores" in data
