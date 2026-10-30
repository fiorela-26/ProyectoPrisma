from pathlib import Path

import pytest

from services import ai_router, transcriber
from services.vtt import Segmento, desde_segmentos, texto_corrido


@pytest.fixture(autouse=True)
def sin_cache(monkeypatch):
    monkeypatch.setattr("services.transcriber.cache_ia.buscar", lambda *a, **k: None)
    monkeypatch.setattr("services.transcriber.cache_ia.guardar", lambda *a, **k: None)


def test_vtt_marca_tiempos_y_omite_vacios():
    vtt = desde_segmentos(
        [
            Segmento(0, 1.5, "  Hola   mundo "),
            Segmento(1.5, 1.5, ""),
            Segmento(65.2, 66.01, "Segunda cue"),
        ]
    )
    assert vtt.startswith("WEBVTT\n")
    assert "00:00:00.000 --> 00:00:01.500" in vtt
    assert "Hola mundo" in vtt
    assert "00:01:05.200 --> 00:01:06.010" in vtt
    assert vtt.count("\n\n") >= 2
    # El segmento vacío no genera cue
    assert "2\n" in vtt  # segunda cue numerada
    assert texto_corrido([Segmento(0, 1, "Hola"), Segmento(1, 2, "mundo")]) == "Hola\nmundo"


def test_fusionar_solape_quita_duplicados():
    segs = [
        Segmento(598.0, 600.0, "fin del primer trozo"),
        Segmento(598.05, 600.1, "fin del primer trozo"),
        Segmento(601.0, 603.0, "inicio del segundo"),
    ]
    fusion = transcriber._fusionar_solape(segs)
    assert [s.text for s in fusion] == ["fin del primer trozo", "inicio del segundo"]


def test_transcribir_usa_whisper_y_arma_vtt(monkeypatch, tmp_path):
    monkeypatch.setattr(transcriber, "ffmpeg_disponible", lambda: True)

    wav = tmp_path / "audio.wav"
    # WAV mínimo: 1 segundo de silencio a 16 kHz mono 16-bit
    pcm = b"\x00\x00" * transcriber.SAMPLE_RATE
    wav.write_bytes(_wav_header(len(pcm)) + pcm)

    def a_wav(_origen, destino: Path):
        destino.write_bytes(wav.read_bytes())

    def groq_falso(_ruta):
        return ai_router.RespuestaSTT(
            texto="Hola clase",
            modelo="whisper-large-v3-turbo",
            segmentos=[ai_router.SegmentoSTT(0.0, 1.2, "Hola clase")],
        )

    monkeypatch.setattr(transcriber, "_a_wav_mono", a_wav)
    monkeypatch.setattr(ai_router, "groq_transcribir", groq_falso)

    res = transcriber.transcribir(b"falso-mp3", "clase.mp3")
    assert res.modelo_usado == "whisper-large-v3-turbo"
    assert res.texto == "Hola clase"
    assert res.vtt.startswith("WEBVTT")
    assert "Hola clase" in res.vtt
    assert "00:00:00.000 --> 00:00:01.200" in res.vtt


def test_sin_ffmpeg_error_claro(monkeypatch):
    monkeypatch.setattr(transcriber, "ffmpeg_disponible", lambda: False)
    try:
        transcriber.transcribir(b"x", "a.mp3")
        assert False, "debía fallar"
    except transcriber.FfmpegNoDisponible as exc:
        assert "ffmpeg" in str(exc).lower()


def test_job_audio_guarda_vtt(monkeypatch):
    from services import jobs

    subidas = []
    sesion = {
        "id": "s1",
        "archivo_url": "curso/abc.mp3",
        "tipo_archivo": "audio",
        "texto_extraido": None,
    }

    class Db:
        def table(self, nombre):
            self.nombre = nombre
            return self

        def select(self, *a, **k):
            return self

        def eq(self, *a, **k):
            return self

        def limit(self, n):
            return self

        def update(self, campos):
            self.campos = campos
            return self

        def execute(self):
            class R:
                data = [sesion] if self.nombre == "sesiones_material" and not getattr(self, "campos", None) else []

            if getattr(self, "campos", None) and self.nombre == "sesiones_material":
                sesion.update(self.campos)
            return R()

    monkeypatch.setattr(jobs, "get_service_client", lambda: Db())
    monkeypatch.setattr("services.storage.download_bytes", lambda ruta: b"audio")
    monkeypatch.setattr("services.storage.upload_bytes", lambda ruta, datos, ct: subidas.append((ruta, ct, datos)) or ruta)
    monkeypatch.setattr(
        "services.transcriber.transcribir",
            lambda datos, nombre, idioma="es": transcriber.ResultadoTranscripcion(
            texto="transcripción",
            vtt="WEBVTT\n\n1\n00:00:00.000 --> 00:00:01.000\nHola\n",
            modelo_usado="whisper-large-v3-turbo",
            segmentos=1,
        ),
    )
    actualizaciones = []
    monkeypatch.setattr(jobs, "_actualizar_job", lambda jid, **c: actualizaciones.append(c))

    jobs._job_extraer({"id": "j1", "sesion_id": "s1"})
    assert sesion["texto_extraido"] == "transcripción"
    assert sesion["estado"] == "revision"
    assert subidas[0][0] == "curso/abc.vtt"
    assert subidas[0][1] == "text/vtt"
    assert any(c.get("formato") == "whisper:whisper-large-v3-turbo" for c in actualizaciones)


def test_segmento_stt_acepta_dict_y_objeto():
    desde_dict = ai_router._segmento_stt({"start": 0.5, "end": 1.2, "text": "hola"})

    class Obj:
        start, end, text = 2, 3, "mundo"

    desde_obj = ai_router._segmento_stt(Obj())
    assert (desde_dict.start, desde_dict.end, desde_dict.text) == (0.5, 1.2, "hola")
    assert (desde_obj.start, desde_obj.end, desde_obj.text) == (2.0, 3.0, "mundo")


def test_groq_stt_fallback_en_429(monkeypatch):
    class Err429(ai_router.GroqAPIError):
        def __init__(self):
            Exception.__init__(self, "quota")
            self.status_code = 429
            self.response = None
            self.body = None

    intentos = []

    class Audio:
        class transcriptions:
            @staticmethod
            def create(file, model, response_format, timestamp_granularities):
                intentos.append(model)
                if model == "primario":
                    raise Err429()

                class Seg:
                    start, end, text = 0.0, 1.0, "ok"

                class R:
                    text = "ok"
                    segments = [Seg()]

                return R()

    class Cliente:
        audio = Audio()

    monkeypatch.setattr(ai_router, "_groq", lambda: Cliente())
    monkeypatch.setattr(ai_router.time, "sleep", lambda s: None)
    tmp = Path("no-existe")  # groq_transcribir lee bytes; mockeamos read_bytes
    monkeypatch.setattr(Path, "read_bytes", lambda self: b"wav", raising=False)
    res = ai_router.groq_transcribir(tmp, cadena=("primario", "respaldo"))
    assert res.modelo == "respaldo"
    assert intentos == ["primario", "respaldo"]


def _wav_header(pcm_len: int) -> bytes:
    # RIFF WAV PCM 16-bit mono 16 kHz
    riff_size = 36 + pcm_len
    return (
        b"RIFF"
        + riff_size.to_bytes(4, "little")
        + b"WAVEfmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")  # PCM
        + (1).to_bytes(2, "little")  # mono
        + (16000).to_bytes(4, "little")
        + (32000).to_bytes(4, "little")  # byte rate
        + (2).to_bytes(2, "little")  # block align
        + (16).to_bytes(2, "little")  # bits
        + b"data"
        + pcm_len.to_bytes(4, "little")
    )
