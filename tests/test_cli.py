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


# --- Configuración ----------------------------------------------------------

VALIDO = (
    '{"version": 1, "acciones": [{"nombre": "limpiar", "descripcion": "Borra temporales",'
    ' "tipo": "borrar", "filtro": {"extensiones": [".tmp"]}}]}'
)


def test_validar_fichero_correcto(runner: CliRunner, tmp_path: Path) -> None:
    ruta = tmp_path / "acciones.json"
    ruta.write_text(VALIDO, encoding="utf-8")
    resultado = runner.invoke(app, ["--config", str(ruta), "validar"])
    assert resultado.exit_code == 0
    assert "es válido: 1 acciones" in resultado.output


def test_validar_fichero_invalido_sale_con_3_y_nombra_el_campo(
    runner: CliRunner, tmp_path: Path
) -> None:
    ruta = tmp_path / "acciones.json"
    ruta.write_text(VALIDO.replace('"tipo": "borrar"', '"tipo": "borar"'), encoding="utf-8")
    resultado = runner.invoke(app, ["--config", str(ruta), "validar"])
    assert resultado.exit_code == 3
    assert "acciones[0] (limpiar): tipo desconocido" in resultado.output
    assert "Traceback" not in resultado.output


def test_acciones_sin_fichero_sale_con_3(runner: CliRunner, tmp_path: Path) -> None:
    resultado = runner.invoke(app, ["-c", str(tmp_path / "no.json"), "acciones"])
    assert resultado.exit_code == 3
    assert "apuntes init" in resultado.output


def test_acciones_lista_nombres_y_marcas(runner: CliRunner, tmp_path: Path) -> None:
    ruta = tmp_path / "acciones.json"
    ruta.write_text(VALIDO, encoding="utf-8")
    resultado = runner.invoke(app, ["-c", str(ruta), "acciones"])
    assert resultado.exit_code == 0
    assert "limpiar" in resultado.output
    assert "confirma" in resultado.output  # borrar es destructiva


def test_init_crea_un_fichero_valido(runner: CliRunner, tmp_path: Path) -> None:
    resultado = runner.invoke(app, ["init", str(tmp_path)])
    assert resultado.exit_code == 0
    validacion = runner.invoke(app, ["-c", str(tmp_path / "acciones.json"), "validar"])
    assert validacion.exit_code == 0


def test_init_no_sobrescribe_sin_forzar(runner: CliRunner, tmp_path: Path) -> None:
    ruta = tmp_path / "acciones.json"
    ruta.write_text("mío", encoding="utf-8")
    resultado = runner.invoke(app, ["init", str(ruta)])
    assert resultado.exit_code == 1
    assert ruta.read_text(encoding="utf-8") == "mío"


def test_init_con_forzar_guarda_copia(runner: CliRunner, tmp_path: Path) -> None:
    ruta = tmp_path / "acciones.json"
    ruta.write_text("mío", encoding="utf-8")
    resultado = runner.invoke(app, ["init", str(ruta), "--forzar"])
    assert resultado.exit_code == 0
    assert (tmp_path / "acciones.json.bak").read_text(encoding="utf-8") == "mío"
    assert ruta.read_text(encoding="utf-8") != "mío"
