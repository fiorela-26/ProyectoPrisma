from services import ai_router, imagen_educativa

JPEG_B64 = "ZmFrZWpwZWc="


class _Resp:
    def __init__(self, payload, status=200, content_type="application/json"):
        self.status_code = status
        self.headers = {"content-type": content_type}
        self._payload = payload
        self.content = b'{"success":true,"result":{"image":"' + JPEG_B64.encode() + b'"}}'

    def json(self):
        return self._payload


def _credenciales(monkeypatch):
    monkeypatch.setattr("services.imagen_educativa.settings.CLOUDFLARE_API_TOKEN", "token-prueba")
    monkeypatch.setattr("services.imagen_educativa.settings.CLOUDFLARE_ACCOUNT_ID", "cuenta-prueba")
    monkeypatch.setattr(
        "services.imagen_educativa.settings.CLOUDFLARE_IMAGE_MODEL",
        "@cf/black-forest-labs/flux-1-schnell",
    )


def test_genera_data_uri_con_flux_schnell(monkeypatch):
    visto = {}
    _credenciales(monkeypatch)

    def fake_post(url, headers=None, json=None, timeout=None):
        visto["url"] = url
        visto["headers"] = headers
        visto["json"] = json
        return _Resp({"success": True, "result": {"image": JPEG_B64}})

    monkeypatch.setattr("services.imagen_educativa.requests.post", fake_post)
    url = imagen_educativa.generar_imagen_educativa("detailed biology illustration of a cell")
    assert url.startswith("data:image/jpeg;charset=utf-8;base64,")
    assert JPEG_B64 in url
    assert visto["url"].endswith("/ai/run/@cf/black-forest-labs/flux-1-schnell")
    assert "cuenta-prueba" in visto["url"]
    assert visto["headers"]["Authorization"] == "Bearer token-prueba"
    # Workers AI rechaza propiedades extra: solo prompt y steps.
    assert set(visto["json"].keys()) == {"prompt", "steps"}
    assert visto["json"]["steps"] == 8
    assert "biology" in visto["json"]["prompt"]
    assert "high quality educational illustration" in visto["json"]["prompt"]
    assert len(visto["json"]["prompt"]) <= 2048


def test_error_401_da_mensaje_de_token(monkeypatch):
    _credenciales(monkeypatch)

    class R401(_Resp):
        def __init__(self):
            super().__init__({"success": False, "errors": [{"code": 10000, "message": "Authentication error"}]}, status=401)

    monkeypatch.setattr("services.imagen_educativa.requests.post", lambda *a, **k: R401())
    try:
        imagen_educativa.generar_imagen_educativa("a red apple on a table")
        assert False
    except RuntimeError as exc:
        assert "token" in str(exc).lower()


def test_sin_credenciales_falla_claro(monkeypatch):
    monkeypatch.setattr("services.imagen_educativa.settings.CLOUDFLARE_API_TOKEN", "")
    monkeypatch.setattr("services.imagen_educativa.settings.CLOUDFLARE_ACCOUNT_ID", "")
    try:
        imagen_educativa.generar_imagen_educativa("a red apple on a table")
        assert False
    except RuntimeError as exc:
        assert "CLOUDFLARE_API_TOKEN" in str(exc)


def test_estilo_visual_por_cine():
    assert "Pixar" in imagen_educativa.estilo_visual("cine_1_inicial")
    assert "6-8" in imagen_educativa.estilo_visual("CINE 1 - Primaria inicial (6 a 8 años)")
    assert "infographic" in imagen_educativa.estilo_visual("cine_1_avanzada")
    assert "12-14" in imagen_educativa.estilo_visual("cine_2")
    assert "realistic photo" in imagen_educativa.estilo_visual("cine_3")
    assert "18+" in imagen_educativa.estilo_visual("cine_6")


def test_armar_prompt_ancla_cualquier_materia():
    historia = imagen_educativa.armar_prompt_imagen(
        "crowds storming a stone fortress",
        "La Revolución Francesa",
        "CINE 2 - Secundaria inferior / Ciclo básico (12 a 14 años)",
    )
    assert "revolución francesa" in historia.lower()
    assert "12-14" in historia or "modern graphic" in historia.lower()
    assert "no text" in historia.lower()


def test_prompt_usa_datos_universal_y_no_json(monkeypatch):
    visto = {}

    def fake(mensajes, **k):
        visto["mensajes"] = mensajes
        visto["json_mode"] = k.get("json_mode", True)
        return ai_router.RespuestaIA(
            texto="Storming of the Bastille, 1789 street crowds, stone fortress, no text.",
            modelo="lite",
        )

    monkeypatch.setattr("services.imagen_educativa.ai_router.groq_texto", fake)
    prompt = imagen_educativa.prompt_desde_texto(
        "El pueblo asalta la Bastilla en 1789.",
        nivel_educativo="CINE 2 - Secundaria inferior / Ciclo básico (12 a 14 años)",
        titulo="La Revolución Francesa",
    )
    assert "bastille" in prompt.lower()
    assert visto["json_mode"] is False
    sistema = visto["mensajes"][0]["content"]
    user = visto["mensajes"][1]["content"]
    assert "ilustraciones educativas universales" in sistema
    assert "religión" in sistema
    assert "<DATOS>" in user
    assert "CINE 2" in user
    assert "NUNCA incluyas texto" in user


def test_para_sesion_usa_cache(monkeypatch):
    monkeypatch.setattr(
        "services.imagen_educativa.cache_ia.buscar",
        lambda *a, **k: {"url": "data:image/jpeg;charset=utf-8;base64,cached", "alt": "ok"},
    )
    monkeypatch.setattr(
        "services.imagen_educativa.prompt_desde_texto",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debe llamar al LLM")),
    )
    out = imagen_educativa.para_sesion({"texto_extraido": "La célula", "titulo": "Célula", "contenido_hash": "abc"})
    assert out["estado"] == "lista"
    assert out["url"].endswith("cached")


def test_para_sesion_devuelve_data_uri_cloudflare(monkeypatch):
    visto = {}
    _credenciales(monkeypatch)
    monkeypatch.setattr("services.imagen_educativa.cache_ia.buscar", lambda *a, **k: None)
    monkeypatch.setattr("services.imagen_educativa.cache_ia.guardar", lambda *a, **k: None)

    def fake_prompt(contenido, nivel_educativo="", titulo=""):
        visto["nivel"] = nivel_educativo
        visto["titulo"] = titulo
        return "Photorealistic diagram of the water cycle with evaporation condensation precipitation collection."

    def fake_post(url, headers=None, json=None, timeout=None):
        visto["prompt"] = json["prompt"]
        return _Resp({"success": True, "result": {"image": JPEG_B64}})

    monkeypatch.setattr("services.imagen_educativa.prompt_desde_texto", fake_prompt)
    monkeypatch.setattr("services.imagen_educativa.requests.post", fake_post)
    out = imagen_educativa.para_sesion(
        {
            "texto_extraido": "Evaporación, condensación y precipitación.",
            "titulo": "El ciclo del agua",
            "contenido_hash": "agua-1",
            "nivel_educativo_etiqueta": "CINE 1 - Primaria inicial (6 a 8 años)",
        }
    )
    assert out["estado"] == "lista"
    assert out["url"].startswith("data:image/jpeg")
    assert JPEG_B64 in out["url"]
    assert visto["titulo"] == "El ciclo del agua"
    assert "CINE 1" in visto["nivel"]
    assert "ciclo del agua" in visto["prompt"].lower()
    assert "high quality educational illustration" in visto["prompt"]
    assert "ciclo del agua" in out["prompt_ingles"].lower()


def test_para_sesion_sin_texto():
    out = imagen_educativa.para_sesion({"texto_extraido": "", "titulo": "Vacía"})
    assert out["estado"] == "sin_texto"
    assert out["url"] == ""


def test_version_cloudflare_flux():
    assert imagen_educativa.VERSION == "img-edu-v8"
    assert "universales" in imagen_educativa.SISTEMA
    assert imagen_educativa.PASOS_FLUX == 8
