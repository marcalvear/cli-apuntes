"""Tests de la interfaz: se ejecutan las órdenes como lo haría el usuario."""

from pathlib import Path

from typer.testing import CliRunner

from apuntes import __version__
from apuntes.cli import app


def test_sin_argumentos_muestra_la_ayuda(runner: CliRunner) -> None:
    resultado = runner.invoke(app, [])
    assert "listar" in resultado.output
    assert "version" in resultado.output


def test_version_muestra_la_version_instalada(runner: CliRunner) -> None:
    resultado = runner.invoke(app, ["version"])
    assert resultado.exit_code == 0
    assert resultado.output.strip() == f"apuntes {__version__}"


def test_listar_muestra_cada_fichero_con_su_tipo(runner: CliRunner, carpeta_apuntes: Path) -> None:
    resultado = runner.invoke(app, ["listar", str(carpeta_apuntes)])

    assert resultado.exit_code == 0
    assert "Tema3_POO.pdf" in resultado.output
    assert "presentación" in resultado.output
    assert "4 elementos" in resultado.output


def test_listar_carpeta_vacia_lo_dice(runner: CliRunner, tmp_path: Path) -> None:
    resultado = runner.invoke(app, ["listar", str(tmp_path)])
    assert resultado.exit_code == 0
    assert "vacía" in resultado.output


# --- Casos feos -------------------------------------------------------------


def test_listar_carpeta_inexistente_sale_con_1_sin_traceback(
    runner: CliRunner, tmp_path: Path
) -> None:
    resultado = runner.invoke(app, ["listar", str(tmp_path / "fantasma")])

    assert resultado.exit_code == 1
    assert "no existe" in resultado.output
    assert "Traceback" not in resultado.output
    assert resultado.exception is None or isinstance(resultado.exception, SystemExit)


def test_opcion_invalida_es_error_de_uso_con_codigo_2(runner: CliRunner) -> None:
    resultado = runner.invoke(app, ["listar", "--orden", "inventado"])
    assert resultado.exit_code == 2
