from services.datos_prueba import (
    CODIGOS_DUA_REQUERIDOS,
    CURSOS,
    DOCENTES,
    ESTUDIANTES,
    cobertura_dua,
)
from services.dua import CODIGOS


def test_diez_estudiantes_secuenciales_y_tres_docentes():
    assert len(ESTUDIANTES) == 10
    assert [e["email"] for e in ESTUDIANTES] == [f"estudiante{i}@prueba.com" for i in range(1, 11)]
    assert len(DOCENTES) == 3
    assert [d["email"] for d in DOCENTES] == [
        "docente1@prueba.com",
        "docente2@prueba.com",
        "docente3@prueba.com",
    ]


def test_cobertura_dua_completa_con_combinaciones():
    cob = cobertura_dua()
    assert cob["faltan"] == []
    assert set(CODIGOS_DUA_REQUERIDOS) <= cob["codigos"]
    assert set(CODIGOS) <= cob["codigos"]
    assert len(cob["dobles"]) >= 2
    assert len(cob["triples"]) >= 1
    assert ("baja_vision", "dislexia") in cob["dobles"]
    assert ("ceguera", "lengua") in cob["dobles"]
    assert ("tdah", "apoyo_visual") in cob["dobles"]
    assert any(e["idioma"].lower() == "quechua" for e in ESTUDIANTES if "lengua" in e["preferencias"])


def test_cursos_de_prueba_tienen_dueno_y_cine():
    assert len(CURSOS) == 3
    duenos = {c["docente_email"] for c in CURSOS}
    assert duenos == {d["email"] for d in DOCENTES}
    assert {c["nivel_educativo"] for c in CURSOS} == {"cine_1_inicial", "cine_2", "cine_3"}
