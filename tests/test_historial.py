"""Tests del historial y de deshacer, de principio a fin en carpetas temporales."""

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from apuntes.cli import app
from apuntes.config import Configuracion
from apuntes.errores import ApuntesError, EjecucionInterrumpida
from apuntes.historial import MAX_EJECUCIONES, Historial
from apuntes.motor import Motor
from apuntes.operaciones import QuitarCarpetaVacia
from tests.conftest import PapeleraFalsa, crear_fichero

ACCIONES = [
    {"nombre": "a-pdf", "descripcion": "d", "tipo": "mover", "destino": "Apuntes/PDF",
     "filtro": {"extensiones": [".pdf"]}},
    {"nombre": "limpiar", "descripcion": "d", "tipo": "borrar",
     "filtro": {"extensiones": [".tmp"]}},
    {"nombre": "copiar", "descripcion": "d", "tipo": "copiar", "destino": "Copia"},
    {"nombre": "indice", "descripcion": "d", "tipo": "indice"},
]  # fmt: skip


def motor(papelera: PapeleraFalsa, historial: Historial) -> Motor:
    texto = json.dumps({"version": 1, "acciones": ACCIONES})
    return Motor(Configuracion.desde_texto(texto), papelera=papelera, historial=historial)


def ejecutar(m: Motor, nombre: str, carpeta: Path) -> None:
    m.aplicar(m.planificar(nombre, carpeta))


def deshacer(historial: Historial, papelera: PapeleraFalsa, id_: int | None = None) -> list[str]:
    """Deshace y devuelve los avisos."""
    from apuntes.motor import aplicar_en_orden

    ejecucion = historial.buscar(id_)
    assert ejecucion is not None
    plan = historial.planificar_deshacer(ejecucion)
    aplicar_en_orden(plan.operaciones, papelera)
    historial.marcar_deshecha(ejecucion.id)
    return plan.avisos


def contenido(carpeta: Path) -> list[str]:
    return sorted(p.relative_to(carpeta).as_posix() for p in carpeta.rglob("*"))


# --- Registro -----------------------------------------------------------------


def test_cada_ejecucion_queda_registrada(
    tmp_path: Path, papelera: PapeleraFalsa, historial: Historial
) -> None:
    crear_fichero(tmp_path / "a.pdf")
    m = motor(papelera, historial)
    ejecutar(m, "a-pdf", tmp_path)

    (registro,) = historial.ejecuciones()
    assert (registro.id, registro.accion, registro.estado) == (1, "a-pdf", "completa")
    assert registro.operaciones[0]["op"] == "mover"


def test_simular_no_deja_rastro(
    tmp_path: Path, papelera: PapeleraFalsa, historial: Historial
) -> None:
    crear_fichero(tmp_path / "a.pdf")
    motor(papelera, historial).planificar("a-pdf", tmp_path)
    assert historial.ejecuciones() == []


def test_una_ejecucion_interrumpida_registra_lo_que_hizo(
    tmp_path: Path, papelera: PapeleraFalsa, historial: Historial
) -> None:
    crear_fichero(tmp_path / "a.pdf")
    crear_fichero(tmp_path / "b.pdf")
    m = motor(papelera, historial)
    plan = m.planificar("a-pdf", tmp_path)
    crear_fichero(tmp_path / "Apuntes" / "PDF" / "b.pdf", b"ajeno")  # bloquea la 2.ª

    with pytest.raises(EjecucionInterrumpida):
        m.aplicar(plan)

    (registro,) = historial.ejecuciones()
    assert registro.estado == "interrumpida"
    assert len(registro.operaciones) == 1  # solo la que llegó a hacerse


def test_el_historial_guarda_solo_las_ultimas(historial: Historial, tmp_path: Path) -> None:
    for _ in range(MAX_EJECUCIONES + 5):
        historial.registrar("x", tmp_path, [{"op": "papelera", "ruta": "x"}], "completa")
    ejecuciones = historial.ejecuciones()
    assert len(ejecuciones) == MAX_EJECUCIONES
    assert ejecuciones[-1].id == MAX_EJECUCIONES + 5  # los números no se reutilizan


def test_un_historial_danado_se_trata_como_vacio(tmp_path: Path) -> None:
    ruta = tmp_path / "historial.json"
    ruta.write_text("{roto")
    assert Historial(ruta).ejecuciones() == []


# --- Deshacer -----------------------------------------------------------------


def test_deshacer_mover_devuelve_los_ficheros_y_quita_las_carpetas_creadas(
    tmp_path: Path, papelera: PapeleraFalsa, historial: Historial
) -> None:
    crear_fichero(tmp_path / "a.pdf")
    crear_fichero(tmp_path / "b.pdf")
    antes = contenido(tmp_path)
    ejecutar(motor(papelera, historial), "a-pdf", tmp_path)
    assert contenido(tmp_path) != antes

    deshacer(historial, papelera)

    assert contenido(tmp_path) == antes  # ni siquiera queda Apuntes/PDF/
    assert historial.ejecuciones()[0].estado == "deshecha"


def test_deshacer_no_quita_una_carpeta_que_ya_existia(
    tmp_path: Path, papelera: PapeleraFalsa, historial: Historial
) -> None:
    (tmp_path / "Apuntes" / "PDF").mkdir(parents=True)
    crear_fichero(tmp_path / "a.pdf")
    ejecutar(motor(papelera, historial), "a-pdf", tmp_path)
    deshacer(historial, papelera)
    assert (tmp_path / "Apuntes" / "PDF").is_dir()


def test_deshacer_no_quita_una_carpeta_que_ya_no_esta_vacia(
    tmp_path: Path, papelera: PapeleraFalsa, historial: Historial
) -> None:
    crear_fichero(tmp_path / "a.pdf")
    ejecutar(motor(papelera, historial), "a-pdf", tmp_path)
    crear_fichero(tmp_path / "Apuntes" / "PDF" / "mio.txt")  # el usuario guardó algo después
    deshacer(historial, papelera)
    assert (tmp_path / "Apuntes" / "PDF" / "mio.txt").exists()


def test_deshacer_copiar_manda_las_copias_a_la_papelera(
    tmp_path: Path, papelera: PapeleraFalsa, historial: Historial
) -> None:
    crear_fichero(tmp_path / "a.txt")
    ejecutar(motor(papelera, historial), "copiar", tmp_path)
    deshacer(historial, papelera)
    assert contenido(tmp_path) == ["a.txt"]
    assert papelera.recibidos == ["a.txt"]  # la copia, nunca el original


def test_deshacer_un_indice_reemplazado_restaura_el_anterior(
    tmp_path: Path, papelera: PapeleraFalsa, historial: Historial
) -> None:
    crear_fichero(tmp_path / "a.txt")
    crear_fichero(tmp_path / "INDICE.md", "mi índice a mano".encode())
    ejecutar(motor(papelera, historial), "indice", tmp_path)
    assert (tmp_path / "INDICE.md").read_text("utf-8") != "mi índice a mano"

    deshacer(historial, papelera)

    assert (tmp_path / "INDICE.md").read_text("utf-8") == "mi índice a mano"


def test_deshacer_borrar_avisa_de_que_esta_en_la_papelera(
    tmp_path: Path, papelera: PapeleraFalsa, historial: Historial
) -> None:
    crear_fichero(tmp_path / "x.tmp")
    ejecutar(motor(papelera, historial), "limpiar", tmp_path)
    ejecucion = historial.buscar()
    assert ejecucion is not None
    plan = historial.planificar_deshacer(ejecucion)
    assert plan.operaciones == []
    assert plan.avisos == ["x.tmp: está en la Papelera; recupéralo desde allí"]


# --- Casos feos -----------------------------------------------------------------


def test_si_el_fichero_ya_no_esta_se_avisa_y_no_falla(
    tmp_path: Path, papelera: PapeleraFalsa, historial: Historial
) -> None:
    crear_fichero(tmp_path / "a.pdf")
    crear_fichero(tmp_path / "b.pdf")
    ejecutar(motor(papelera, historial), "a-pdf", tmp_path)
    (tmp_path / "Apuntes" / "PDF" / "a.pdf").unlink()  # el usuario lo borró después

    avisos = deshacer(historial, papelera)

    assert (tmp_path / "b.pdf").exists()
    assert any("a.pdf: ya no está" in a for a in avisos)


def test_si_el_sitio_original_esta_ocupado_no_se_pisa(
    tmp_path: Path, papelera: PapeleraFalsa, historial: Historial
) -> None:
    crear_fichero(tmp_path / "a.pdf", b"original")
    ejecutar(motor(papelera, historial), "a-pdf", tmp_path)
    crear_fichero(tmp_path / "a.pdf", b"otro nuevo con el mismo nombre")

    avisos = deshacer(historial, papelera)

    assert (tmp_path / "a.pdf").read_bytes() == b"otro nuevo con el mismo nombre"
    assert (tmp_path / "Apuntes" / "PDF" / "a.pdf").read_bytes() == b"original"
    assert any("ocupado" in a for a in avisos)


def test_no_se_deshace_dos_veces(
    tmp_path: Path, papelera: PapeleraFalsa, historial: Historial
) -> None:
    crear_fichero(tmp_path / "a.pdf")
    ejecutar(motor(papelera, historial), "a-pdf", tmp_path)
    deshacer(historial, papelera)
    assert historial.buscar() is None
    with pytest.raises(ApuntesError, match="ya estaba deshecha"):
        historial.buscar(1)


def test_ejecucion_inexistente(historial: Historial) -> None:
    with pytest.raises(ApuntesError, match="No hay ninguna ejecución #7"):
        historial.buscar(7)


def test_las_carpetas_se_quitan_de_dentro_afuera(tmp_path: Path) -> None:
    registro = {
        "op": "mover",
        "origen": str(tmp_path / "a.pdf"),
        "destino": str(tmp_path / "x" / "y" / "a.pdf"),
        "carpetas_creadas": [str(tmp_path / "x" / "y"), str(tmp_path / "x")],
    }
    crear_fichero(tmp_path / "x" / "y" / "a.pdf")
    historial = Historial(tmp_path / "h.json")
    ejecucion = historial.registrar("m", tmp_path, [registro], "completa")
    quitar = [
        op.ruta for op in historial.planificar_deshacer(ejecucion).operaciones
        if isinstance(op, QuitarCarpetaVacia)
    ]  # fmt: skip
    assert quitar == [tmp_path / "x" / "y", tmp_path / "x"]


# --- CLI --------------------------------------------------------------------------


@pytest.fixture
def config(tmp_path: Path) -> Path:
    ruta = tmp_path / "acciones.json"
    ruta.write_text(json.dumps({"version": 1, "acciones": ACCIONES}))
    return ruta


def _cli(runner: CliRunner, config: Path, *args: str, entrada: str | None = None) -> Any:
    return runner.invoke(app, ["-c", str(config), *args], input=entrada)


def test_cli_historial_vacio(runner: CliRunner, config: Path) -> None:
    resultado = _cli(runner, config, "historial")
    assert resultado.exit_code == 0
    assert "Todavía no se ha ejecutado" in resultado.output


def test_cli_ejecutar_historial_y_deshacer(runner: CliRunner, config: Path, tmp_path: Path) -> None:
    trabajo = tmp_path / "trabajo"
    crear_fichero(trabajo / "tema.pdf")

    assert _cli(runner, config, "ejecutar", "a-pdf", str(trabajo)).exit_code == 0
    historial = _cli(runner, config, "historial")
    assert "a-pdf" in historial.output
    assert "completa" in historial.output

    simulado = _cli(runner, config, "deshacer", "--simular")
    assert "devolver" in simulado.output
    assert (trabajo / "Apuntes" / "PDF" / "tema.pdf").exists()  # simular no toca nada

    cancelado = _cli(runner, config, "deshacer", entrada="\n")
    assert cancelado.exit_code == 1
    assert (trabajo / "Apuntes" / "PDF" / "tema.pdf").exists()

    hecho = _cli(runner, config, "deshacer", entrada="y\n")
    assert hecho.exit_code == 0
    assert (trabajo / "tema.pdf").exists()
    assert not (trabajo / "Apuntes").exists()

    assert "No hay nada que deshacer" in _cli(runner, config, "deshacer").output
    assert "deshecha" in _cli(runner, config, "historial").output


def test_cli_deshacer_un_numero_que_no_existe_sale_con_1(runner: CliRunner, config: Path) -> None:
    resultado = _cli(runner, config, "deshacer", "99")
    assert resultado.exit_code == 1
    assert "No hay ninguna ejecución #99" in resultado.output
