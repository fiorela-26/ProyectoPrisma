"""Catálogo de docentes, estudiantes y cursos de prueba (seed / mock DUA)."""

CLAVE_DOCENTE = "Prueba-Docente-123!"
CLAVE_ESTUDIANTE = "Prueba-Estudiante-123!"

DOCENTES = (
    {
        "email": "docente1@prueba.com",
        "nombre": "Docente de prueba 1",
        "password": CLAVE_DOCENTE,
    },
    {
        "email": "docente2@prueba.com",
        "nombre": "Docente de prueba 2",
        "password": CLAVE_DOCENTE,
    },
    {
        "email": "docente3@prueba.com",
        "nombre": "Docente de prueba 3",
        "password": CLAVE_DOCENTE,
    },
)

# Un caso por alumno: las 6 necesidades sueltas + dobles + un triple.
ESTUDIANTES = (
    {
        "email": "estudiante1@prueba.com",
        "nombre": "Ana Ceguera",
        "preferencias": ["ceguera"],
        "idioma": "es",
    },
    {
        "email": "estudiante2@prueba.com",
        "nombre": "Bruno Baja visión",
        "preferencias": ["baja_vision"],
        "idioma": "es",
    },
    {
        "email": "estudiante3@prueba.com",
        "nombre": "Carla Dislexia",
        "preferencias": ["dislexia"],
        "idioma": "es",
    },
    {
        "email": "estudiante4@prueba.com",
        "nombre": "Diego TDAH",
        "preferencias": ["tdah"],
        "idioma": "es",
    },
    {
        "email": "estudiante5@prueba.com",
        "nombre": "Elena Apoyo visual",
        "preferencias": ["apoyo_visual"],
        "idioma": "es",
    },
    {
        "email": "estudiante6@prueba.com",
        "nombre": "Fátima Quechua",
        "preferencias": ["lengua"],
        "idioma": "quechua",
    },
    {
        "email": "estudiante7@prueba.com",
        "nombre": "Gabriel Baja visión y dislexia",
        "preferencias": ["baja_vision", "dislexia"],
        "idioma": "es",
    },
    {
        "email": "estudiante8@prueba.com",
        "nombre": "Helena Ceguera y Quechua",
        "preferencias": ["ceguera", "lengua"],
        "idioma": "quechua",
    },
    {
        "email": "estudiante9@prueba.com",
        "nombre": "Iván TDAH y apoyo visual",
        "preferencias": ["tdah", "apoyo_visual"],
        "idioma": "es",
    },
    {
        "email": "estudiante10@prueba.com",
        "nombre": "Julia Baja visión, dislexia y TDAH",
        "preferencias": ["baja_vision", "dislexia", "tdah"],
        "idioma": "es",
    },
)

CURSOS = (
    {
        "docente_email": "docente1@prueba.com",
        "nombre": "Prueba DUA · Primaria inicial",
        "descripcion": "Curso de prueba (CINE 1, 6 a 8 años) con roster DUA completo.",
        "nivel_educativo": "cine_1_inicial",
    },
    {
        "docente_email": "docente2@prueba.com",
        "nombre": "Prueba DUA · Secundaria inferior",
        "descripcion": "Curso de prueba (CINE 2, 12 a 14 años) con roster DUA completo.",
        "nivel_educativo": "cine_2",
    },
    {
        "docente_email": "docente3@prueba.com",
        "nombre": "Prueba DUA · Bachillerato",
        "descripcion": "Curso de prueba (CINE 3, 15 a 17 años) con roster DUA completo.",
        "nivel_educativo": "cine_3",
    },
)

CODIGOS_DUA_REQUERIDOS = (
    "ceguera",
    "baja_vision",
    "dislexia",
    "tdah",
    "apoyo_visual",
    "lengua",
)


def cobertura_dua(estudiantes=ESTUDIANTES) -> dict:
    """Códigos cubiertos, combinaciones dobles/triples y huecos."""
    individuales = set()
    dobles = []
    triples = []
    for e in estudiantes:
        prefs = tuple(e.get("preferencias") or [])
        individuales.update(prefs)
        if len(prefs) == 2:
            dobles.append(prefs)
        elif len(prefs) >= 3:
            triples.append(prefs)
    return {
        "codigos": individuales,
        "dobles": dobles,
        "triples": triples,
        "faltan": [c for c in CODIGOS_DUA_REQUERIDOS if c not in individuales],
    }
