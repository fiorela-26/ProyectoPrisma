"""Prueba real de transcripción (ffmpeg + Groq Whisper) y el job extraer de audio.

Uso: python scripts/smoke_transcribe.py
"""
import io
import os
import sys
import time
from pathlib import Path

# Recarga el PATH del sistema: winget acaba de instalar ffmpeg en otra terminal.
os.environ["PATH"] = (
    os.environ.get("PATH", "")
    + ";"
    + (os.environ.get("Path", "") or "")
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from supabase import create_client  # noqa: E402

from app import create_app  # noqa: E402
from config import settings  # noqa: E402
from scripts.smoke_upload import EMAIL, PASSWORD, asegurar_curso, asegurar_docente  # noqa: E402
from services import jobs, storage, transcriber  # noqa: E402
from services.supabase_client import get_service_client  # noqa: E402


def _refrescar_path() -> None:
    import winreg

    partes = []
    for hive, sub in (
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        (winreg.HKEY_CURRENT_USER, "Environment"),
    ):
        try:
            with winreg.OpenKey(hive, sub) as key:
                val, _ = winreg.QueryValueEx(key, "Path")
                partes.append(val)
        except OSError:
            pass
    os.environ["PATH"] = ";".join(partes + [os.environ.get("PATH", "")])


def sintetizar_wav(destino: Path) -> bytes:
    """Genera un WAV corto con la voz del sistema (sin cuota de IA)."""
    import subprocess

    ruta = str(destino).replace("'", "''")
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.Rate = -2; "
        f"$s.SetOutputToWaveFile('{ruta}'); "
        "$s.Speak('Hola Prisma. Esta es una prueba de transcripcion.'); "
        "$s.Dispose()"
    )
    proc = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
    if proc.returncode != 0 or not destino.exists():
        raise RuntimeError(f"No se pudo sintetizar el WAV: {proc.stderr or proc.stdout}")
    return destino.read_bytes()


def main() -> int:
    _refrescar_path()
    print("ffmpeg:", transcriber.ffmpeg_disponible())
    if not transcriber.ffmpeg_disponible():
        print("ERROR: este proceso aún no ve ffmpeg. Cierra Cursor y ábrelo de nuevo.")
        return 1

    wav = Path(__file__).resolve().parent.parent / "instance" / "prueba_stt.wav"
    wav.parent.mkdir(exist_ok=True)
    datos = sintetizar_wav(wav)
    print(f"WAV {len(datos)} bytes")

    print("Transcribiendo con Groq...")
    res = transcriber.transcribir(datos, "prueba.wav", idioma="es")
    print("  modelo:", res.modelo_usado)
    print("  segmentos:", res.segmentos)
    print("  texto:", repr(res.texto[:200]))
    print("  vtt:\n", res.vtt[:400])
    if not res.texto.strip() or not res.vtt.startswith("WEBVTT"):
        print("ERROR: transcripción vacía o VTT inválido")
        return 1

    storage.ensure_bucket()
    docente_id = asegurar_docente()
    curso_id = asegurar_curso(docente_id)
    login = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
    token = login.auth.sign_in_with_password({"email": EMAIL, "password": PASSWORD}).session.access_token

    cliente = create_app(con_worker=False).test_client()
    resp = cliente.post(
        f"/cursos/{curso_id}/materiales",
        data={"archivo": (io.BytesIO(datos), "prueba.wav"), "titulo": "Audio de prueba STT"},
        content_type="multipart/form-data",
        headers={"Authorization": f"Bearer {token}"},
    )
    print("HTTP", resp.status_code, resp.get_json())
    if resp.status_code != 202:
        return 1

    job_id = resp.get_json()["job_id"]
    sesion_id = resp.get_json()["sesion_id"]
    job = jobs.obtener_job(job_id)
    final = jobs.ejecutar_job(job)
    print("Job:", final["estado"], final.get("formato"), final.get("error") or "")

    db = get_service_client()
    sesion = db.table("sesiones_material").select("estado, texto_extraido, archivo_url").eq("id", sesion_id).execute().data[0]
    print("Sesión:", sesion["estado"], repr((sesion["texto_extraido"] or "")[:120]))
    vtt_ruta = sesion["archivo_url"].rsplit(".", 1)[0] + ".vtt"
    try:
        vtt = storage.download_bytes(vtt_ruta).decode("utf-8")
        print("VTT en Storage:", vtt[:180].replace("\n", " | "))
    except Exception as exc:
        print("ERROR leyendo VTT:", exc)
        return 1
    return 0 if final["estado"] == "done" else 1


if __name__ == "__main__":
    sys.exit(main())
