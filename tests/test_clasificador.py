import pytest

from apuntes.clasificador import Clasificador, normalizar
from apuntes.config import Asignatura

ASIGNATURAS = [
    Asignatura(nombre="Programacion", palabras_clave=["prog", "java", "poo"]),
    Asignatura(nombre="Bases de Datos", palabras_clave=["bd", "sql", "normalizacion"]),
    Asignatura(nombre="Sistemas Informaticos", palabras_clave=["si", "redes"]),
]


@pytest.fixture
def clasificador() -> Clasificador:
    return Clasificador(ASIGNATURAS)


def test_normalizar_quita_tildes_y_mayusculas() -> None:
    assert normalizar("Programación UD4") == "programacion ud4"


@pytest.mark.parametrize(
    ("nombre", "esperada"),
    [
        ("Tema3_POO.pdf", "Programacion"),  # palabra suelta junto a un número
        ("BBDD-normalizacion3FN.pdf", "Bases de Datos"),  # clave larga dentro de otra palabra
        ("bases_de_datos_t1.pdf", "Bases de Datos"),  # el nombre de la asignatura, como frase
        ("Programación UD4.pptx", "Programacion"),  # con tilde
        ("SI_tema2.pdf", "Sistemas Informaticos"),  # clave corta como palabra suelta
    ],
)
def test_reconoce_la_asignatura(clasificador: Clasificador, nombre: str, esperada: str) -> None:
    assert clasificador.clasificar(nombre).asignatura == esperada


def test_una_clave_corta_no_cuenta_dentro_de_otra_palabra(clasificador: Clasificador) -> None:
    """«si» no debe hacer que «sistema_solar.pdf» sea de Sistemas Informáticos."""
    resultado = clasificador.clasificar("sistema_solar.pdf")
    assert resultado.asignatura is None
    assert resultado.motivo == "no encaja con ninguna asignatura"


def test_empate_no_decide(clasificador: Clasificador) -> None:
    resultado = clasificador.clasificar("java y sql.pdf")
    assert resultado.asignatura is None
    assert resultado.motivo == "dudoso entre Bases de Datos y Programacion"


def test_gana_la_que_mas_coincide(clasificador: Clasificador) -> None:
    # java + poo (2) frente a sql (1)
    assert clasificador.clasificar("java poo con sql.pdf").asignatura == "Programacion"
