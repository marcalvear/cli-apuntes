"""Tests de la interfaz: se ejecutan las órdenes como lo haría el usuario."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from apuntes import __version__
from apuntes.cli import app
from tests.conftest import PapeleraFalsa
from tests.ia_falsa import IAFalsa


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


# --- ejecutar ---------------------------------------------------------------

CONFIG_EJECUTAR = (
    '{"version": 1, "acciones": ['
    '{"nombre": "limpiar", "descripcion": "d", "tipo": "borrar",'
    ' "filtro": {"extensiones": [".tmp"]}},'
    '{"nombre": "a-pdf", "descripcion": "d", "tipo": "mover", "destino": "PDF",'
    ' "filtro": {"extensiones": [".pdf"]}}]}'
)


@pytest.fixture
def entorno(tmp_path: Path) -> tuple[Path, Path]:
    """(acciones.json, carpeta de trabajo con un .tmp y un .pdf)."""
    config = tmp_path / "acciones.json"
    config.write_text(CONFIG_EJECUTAR, encoding="utf-8")
    trabajo = tmp_path / "trabajo"
    trabajo.mkdir()
    (trabajo / "basura.tmp").write_text("x", encoding="utf-8")
    (trabajo / "tema.pdf").write_text("pdf", encoding="utf-8")
    return config, trabajo


def _ejecutar(runner: CliRunner, config: Path, *args: str, entrada: str | None = None):
    return runner.invoke(app, ["-c", str(config), "ejecutar", *args], input=entrada)


def test_simular_muestra_el_plan_y_no_toca_nada(
    runner: CliRunner, entorno: tuple[Path, Path]
) -> None:
    config, trabajo = entorno
    resultado = _ejecutar(runner, config, "limpiar", str(trabajo), "--simular")

    assert resultado.exit_code == 0
    assert "a la papelera" in resultado.output
    assert "basura.tmp" in resultado.output
    assert "no se ha cambiado nada" in resultado.output
    assert (trabajo / "basura.tmp").exists()


def test_destructiva_pide_confirmacion_y_por_defecto_no_hace_nada(
    runner: CliRunner, entorno: tuple[Path, Path], papelera: PapeleraFalsa
) -> None:
    config, trabajo = entorno
    resultado = _ejecutar(runner, config, "limpiar", str(trabajo), entrada="\n")  # Intro = No

    assert resultado.exit_code == 1
    assert "¿Aplicar estas 1 operaciones?" in resultado.output
    assert "Cancelado" in resultado.output
    assert (trabajo / "basura.tmp").exists()
    assert papelera.recibidos == []


def test_destructiva_confirmada_se_aplica(
    runner: CliRunner, entorno: tuple[Path, Path], papelera: PapeleraFalsa
) -> None:
    config, trabajo = entorno
    resultado = _ejecutar(runner, config, "limpiar", str(trabajo), entrada="y\n")

    assert resultado.exit_code == 0
    assert "1 operaciones aplicadas" in resultado.output
    assert papelera.recibidos == ["basura.tmp"]


def test_si_aplica_sin_preguntar(
    runner: CliRunner, entorno: tuple[Path, Path], papelera: PapeleraFalsa
) -> None:
    config, trabajo = entorno
    resultado = _ejecutar(runner, config, "limpiar", str(trabajo), "--si")

    assert resultado.exit_code == 0
    assert "¿Aplicar" not in resultado.output
    assert papelera.recibidos == ["basura.tmp"]


def test_no_destructiva_se_aplica_sin_preguntar(
    runner: CliRunner, entorno: tuple[Path, Path]
) -> None:
    config, trabajo = entorno
    resultado = _ejecutar(runner, config, "a-pdf", str(trabajo))

    assert resultado.exit_code == 0
    assert (trabajo / "PDF" / "tema.pdf").exists()


def test_nada_que_hacer(runner: CliRunner, entorno: tuple[Path, Path]) -> None:
    config, trabajo = entorno
    (trabajo / "basura.tmp").unlink()
    resultado = _ejecutar(runner, config, "limpiar", str(trabajo))
    assert resultado.exit_code == 0
    assert "Nada que hacer" in resultado.output


def test_accion_inexistente_sale_con_1_y_sugiere(
    runner: CliRunner, entorno: tuple[Path, Path]
) -> None:
    config, trabajo = entorno
    resultado = _ejecutar(runner, config, "volar", str(trabajo))
    assert resultado.exit_code == 1
    assert "limpiar, a-pdf" in resultado.output


def test_simular_y_si_juntas_es_error_de_uso(runner: CliRunner, entorno: tuple[Path, Path]) -> None:
    config, trabajo = entorno
    resultado = _ejecutar(runner, config, "limpiar", str(trabajo), "--simular", "--si")
    assert resultado.exit_code == 2


# --- IA desde la CLI --------------------------------------------------------

CONFIG_IA = (
    '{"version": 1, "acciones": ['
    '{"nombre": "limpiar", "descripcion": "d", "tipo": "borrar",'
    ' "filtro": {"extensiones": [".tmp"]}},'
    '{"nombre": "resumir", "descripcion": "d", "tipo": "ia-resumir"},'
    '{"nombre": "todo", "descripcion": "d", "tipo": "pipeline", "pasos": ["limpiar", "resumir"]}]}'
)


@pytest.fixture
def entorno_ia(tmp_path: Path) -> tuple[Path, Path]:
    config = tmp_path / "acciones.json"
    config.write_text(CONFIG_IA, encoding="utf-8")
    trabajo = tmp_path / "trabajo"
    trabajo.mkdir()
    (trabajo / "basura.tmp").write_text("x", encoding="utf-8")
    (trabajo / "tema1.pdf").write_bytes(b"%PDF-1.4 tema")
    return config, trabajo


def test_resumir_simulado_avisa_de_que_usara_la_ia(
    runner: CliRunner, entorno_ia: tuple[Path, Path], ia: IAFalsa
) -> None:
    config, trabajo = entorno_ia
    resultado = _ejecutar(runner, config, "resumir", str(trabajo), "--simular")
    assert resultado.exit_code == 0
    assert "generar con IA" in resultado.output
    assert "llamarán a la IA" in resultado.output
    assert ia.llamadas == []


def test_sin_ia_la_accion_de_ia_sale_con_1_y_lo_explica(
    runner: CliRunner, entorno_ia: tuple[Path, Path], ia: IAFalsa
) -> None:
    ia.disponible = False
    config, trabajo = entorno_ia
    resultado = _ejecutar(runner, config, "resumir", str(trabajo))
    assert resultado.exit_code == 1
    assert "No hay conexión" in resultado.output
    assert "Traceback" not in resultado.output


def test_sin_ia_el_pipeline_hace_el_resto(
    runner: CliRunner, entorno_ia: tuple[Path, Path], ia: IAFalsa, papelera: PapeleraFalsa
) -> None:
    ia.disponible = False
    config, trabajo = entorno_ia
    resultado = _ejecutar(runner, config, "todo", str(trabajo), "--si")
    assert resultado.exit_code == 0
    assert "Paso omitido" in resultado.output
    assert "se omiten 1 paso(s)" in resultado.output
    assert papelera.recibidos == ["basura.tmp"]


def test_acciones_avisa_si_falta_la_clave(runner: CliRunner, entorno_ia: tuple[Path, Path]) -> None:
    config, _ = entorno_ia
    resultado = runner.invoke(app, ["-c", str(config), "acciones"])
    assert resultado.exit_code == 0
    assert "IA sin configurar" in resultado.output
    assert "las otras 2" in resultado.output


def test_estado_sin_clave(runner: CliRunner, entorno_ia: tuple[Path, Path]) -> None:
    config, _ = entorno_ia
    resultado = runner.invoke(app, ["-c", str(config), "estado"])
    assert resultado.exit_code == 0
    assert "3 acciones" in resultado.output
    assert "falta la clave ANTHROPIC_API_KEY" in resultado.output
