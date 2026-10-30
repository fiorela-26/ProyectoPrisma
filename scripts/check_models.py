"""Lista los modelos disponibles en Groq y Gemini y verifica los nombres configurados en .env.

Uso:
  python scripts/check_models.py            # solo compara contra la lista de modelos
  python scripts/check_models.py --probar   # además hace una llamada mínima a cada modelo configurado
                                            # (la lista puede incluir modelos que ya no se sirven: 404)
"""
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402


def groq_models():
    resp = requests.get(
        "https://api.groq.com/openai/v1/models",
        headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
        timeout=20,
    )
    resp.raise_for_status()
    return {m["id"] for m in resp.json().get("data", [])}


def gemini_models():
    names, token = set(), None
    while True:
        params = {"pageSize": 100}
        if token:
            params["pageToken"] = token
        resp = requests.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            headers={"x-goog-api-key": settings.GEMINI_API_KEY},
            params=params,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        names |= {m["name"].removeprefix("models/") for m in data.get("models", [])}
        token = data.get("nextPageToken")
        if not token:
            return names


def check(provider, fetch, configured):
    print(f"\n== {provider} ==")
    try:
        available = fetch()
    except Exception as exc:
        print(f"  ERROR al listar modelos: {exc}")
        return False
    print(f"  {len(available)} modelos disponibles:")
    for name in sorted(available):
        print(f"    - {name}")
    ok = True
    for var, model in configured.items():
        status = "OK" if model in available else "NO ENCONTRADO"
        ok &= model in available
        print(f"  {var}={model!r}: {status}")
    return ok


def probar_llamadas():
    """Llamada mínima real a cada modelo de texto/visión configurado."""
    from google import genai
    from groq import Groq

    print("\n== Prueba real (una llamada mínima por modelo) ==")
    groq = Groq(api_key=settings.GROQ_API_KEY)
    for var in ("MODEL_TEXT_PRIMARY", "MODEL_TEXT_FALLBACK"):
        modelo = getattr(settings, var)
        try:
            groq.chat.completions.create(model=modelo, messages=[{"role": "user", "content": "Responde solo: OK"}], max_tokens=5)
            print(f"  {var}={modelo!r}: responde")
        except Exception as exc:
            print(f"  {var}={modelo!r}: ERROR {str(exc)[:100]}")

    gemini = genai.Client(api_key=settings.GEMINI_API_KEY)
    for var in ("MODEL_VISION", "MODEL_LITE"):
        modelo = getattr(settings, var)
        try:
            gemini.models.generate_content(model=modelo, contents="Responde solo: OK")
            print(f"  {var}={modelo!r}: responde")
        except Exception as exc:
            print(f"  {var}={modelo!r}: ERROR {getattr(exc, 'code', '')} {str(exc)[:100]}")


def main():
    groq_ok = check(
        "Groq",
        groq_models,
        {
            "MODEL_TEXT_PRIMARY": settings.MODEL_TEXT_PRIMARY,
            "MODEL_TEXT_FALLBACK": settings.MODEL_TEXT_FALLBACK,
            "MODEL_STT": settings.MODEL_STT,
            "MODEL_STT_FALLBACK": settings.MODEL_STT_FALLBACK,
        },
    )
    gemini_ok = check(
        "Gemini",
        gemini_models,
        {
            "MODEL_VISION": settings.MODEL_VISION,
            "MODEL_LITE": settings.MODEL_LITE,
        },
    )
    if "--probar" in sys.argv:
        probar_llamadas()
    sys.exit(0 if groq_ok and gemini_ok else 1)


if __name__ == "__main__":
    main()
