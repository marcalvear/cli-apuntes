from pathlib import Path

import pytest

from apuntes.errores import CarpetaNoValida
from apuntes.ficheros import TipoFichero, listar_carpeta, tamano_legible, tipo_de


@pytest.mark.parametrize(
    ("nombre", "esperado"),
    [
        ("tema1.pdf", TipoFichero.PDF),
        ("TEMA1.PDF", TipoFichero.PDF),  # la extensión no distingue mayúsculas
        ("clase.pptx", TipoFichero.PRESENTACION),
        ("Main.java", TipoFichero.CODIGO),
        ("notas.md", TipoFichero.TEXTO),
        ("sin_extension", TipoFichero.OTRO),
        ("raro.xyz", TipoFichero.OTRO),
    ],
)
def test_tipo_de_clasifica_por_extension(nombre: str, esperado: TipoFichero) -> None:
    assert tipo_de(Path(nombre)) is esperado


@pytest.mark.parametrize(
    ("num_bytes", "esperado"),
    [(0, "0 B"), (1023, "1023 B"), (1024, "1.0 KB"), (1536, "1.5 KB"), (5 * 1024**3, "5.0 GB")],
)
def test_tamano_legible(num_bytes: int, esperado: str) -> None:
    assert tamano_legible(num_bytes) == esperado


def test_listar_ordena_carpetas_primero_y_oculta_ocultos(carpeta_apuntes: Path) -> None:
    nombres = [i.nombre for i in listar_carpeta(carpeta_apuntes)]

    assert nombres == ["Programacion", "ejercicio.py", "presentacion.PPTX", "Tema3_POO.pdf"]
    assert ".DS_Store" not in nombres


def test_listar_incluye_ocultos_si_se_pide(carpeta_apuntes: Path) -> None:
    nombres = [i.nombre for i in listar_carpeta(carpeta_apuntes, incluir_ocultos=True)]
    assert ".DS_Store" in nombres


def test_listar_da_tamano_cero_a_las_carpetas(carpeta_apuntes: Path) -> None:
    carpeta = next(i for i in listar_carpeta(carpeta_apuntes) if i.tipo is TipoFichero.CARPETA)
    assert carpeta.tamano == 0


# --- Casos feos -------------------------------------------------------------


def test_listar_carpeta_inexistente_lanza_error_propio(tmp_path: Path) -> None:
    with pytest.raises(CarpetaNoValida, match="no existe"):
        listar_carpeta(tmp_path / "no-esta")


def test_listar_un_fichero_lanza_error_propio(tmp_path: Path) -> None:
    fichero = tmp_path / "a.txt"
    fichero.write_text("hola")
    with pytest.raises(CarpetaNoValida, match="no una carpeta"):
        listar_carpeta(fichero)


def test_listar_ignora_enlaces_rotos(tmp_path: Path) -> None:
    try:
        (tmp_path / "roto").symlink_to(tmp_path / "destino-que-no-existe")
    except OSError:
        pytest.skip("este sistema no permite crear enlaces simbólicos (Windows sin permisos)")
    (tmp_path / "bueno.txt").write_text("ok")

    assert [i.nombre for i in listar_carpeta(tmp_path)] == ["bueno.txt"]
