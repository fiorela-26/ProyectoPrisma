import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    HUGGINGFACE_API_TOKEN = os.getenv("HUGGINGFACE_API_TOKEN") or os.getenv("HF_TOKEN", "")
    HF_TOKEN = HUGGINGFACE_API_TOKEN
    HF_IMAGE_MODEL = os.getenv("HF_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell")
    IMAGEN_MODEL = os.getenv("IMAGEN_MODEL", "imagen-3.0-generate-002")
    CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "")
    CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    CLOUDFLARE_IMAGE_MODEL = os.getenv(
        "CLOUDFLARE_IMAGE_MODEL",
        "@cf/black-forest-labs/flux-1-schnell",
    )
    FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "")

    MODEL_TEXT_PRIMARY = os.getenv("MODEL_TEXT_PRIMARY", "")
    MODEL_TEXT_FALLBACK = os.getenv("MODEL_TEXT_FALLBACK", "")
    MODEL_VISION = os.getenv("MODEL_VISION", "")
    MODEL_LITE = os.getenv("MODEL_LITE", "")
    MODEL_STT = os.getenv("MODEL_STT", "")
    MODEL_STT_FALLBACK = os.getenv("MODEL_STT_FALLBACK", "whisper-large-v3")

    CHAT_LIMITE_DIARIO = int(os.getenv("CHAT_LIMITE_DIARIO", "30"))
    RATE_CHAT_POR_MINUTO = int(os.getenv("RATE_CHAT_POR_MINUTO", "10"))
    RATE_INTERACCION_POR_MINUTO = int(os.getenv("RATE_INTERACCION_POR_MINUTO", "40"))
    CHAT_RETENCION_DIAS = int(os.getenv("CHAT_RETENCION_DIAS", "90"))

    # Almacenamiento. El plan gratuito de Supabase limita cada archivo a 50 MB.
    STORAGE_BUCKET = os.getenv("STORAGE_BUCKET", "materiales")
    MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))
    SIGNED_URL_TTL = int(os.getenv("SIGNED_URL_TTL", "3600"))

    REQUIRED = (
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_KEY",
        "GROQ_API_KEY",
        "GEMINI_API_KEY",
        "FLASK_SECRET_KEY",
        "MODEL_TEXT_PRIMARY",
        "MODEL_TEXT_FALLBACK",
        "MODEL_VISION",
        "MODEL_LITE",
        "MODEL_STT",
    )

    def missing(self):
        return [name for name in self.REQUIRED if not getattr(self, name)]


settings = Settings()
