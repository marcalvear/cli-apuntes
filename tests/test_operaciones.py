"""Cada operación hace exactamente lo que dice y, si falla, no deja nada a medias."""

import errno
import os
import zipfile
from pathlib import Path

import pytest

from apuntes import operaciones
from apuntes.errores import FicheroError
from apuntes.operaciones import Copiar, CrearZip, EnviarAPapelera, Escribir, Mover
from tests.conftest import PapeleraFalsa


def test_mover_crea_las_carpetas_del_destino(tmp_path: Path, papelera: PapeleraFalsa) -> None:
    origen = tmp_path / "a.pdf"
    origen.write_text("pdf", encoding="utf-8")
    destino = tmp_path / "Apuntes" / "Prog" / "a.pdf"

    Mover(origen, destino).aplicar(papelera)

    assert not origen.exists()
    assert destino.read_text(encoding="utf-8") == "pdf"


def test_mover_no_pisa_un_fichero_que_aparecio_despues(
    tmp_path: Path, papelera: PapeleraFalsa
) -> None:
    origen, destino = tmp_path / "a.pdf", tmp_path / "b.pdf"
    origen.write_text("nuevo", encoding="utf-8")
    destino.write_text("valioso", encoding="utf-8")

    with pytest.raises(FicheroError, match="ya existe"):
        Mover(origen, destino).aplicar(papelera)

    assert destino.read_text(encoding="utf-8") == "valioso"
    assert origen.exists()


def test_mover_sobrescribiendo_manda_el_anterior_a_la_papelera(
    tmp_path: Path, papelera: PapeleraFalsa
) -> None:
    origen, destino = tmp_path / "a.pdf", tmp_path / "b.pdf"
    origen.write_text("nuevo", encoding="utf-8")
    destino.write_text("viejo", encoding="utf-8")

    Mover(origen, destino, sobrescribe=True).aplicar(papelera)

    assert destino.read_text(encoding="utf-8") == "nuevo"
    assert papelera.recibidos == ["b.pdf"]


def test_mover_si_el_origen_desaparecio(tmp_path: Path, papelera: PapeleraFalsa) -> None:
    with pytest.raises(FicheroError, match="ya no existe"):
        Mover(tmp_path / "fantasma.pdf", tmp_path / "x.pdf").aplicar(papelera)


def test_mover_entre_discos_no_deja_el_destino_a_medias(
    tmp_path: Path, papelera: PapeleraFalsa, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulamos otro disco (EXDEV) y que la copia falla: no queda nada a medias."""
    origen = tmp_path / "a.pdf"
    origen.write_text("contenido", encoding="utf-8")
    destino = tmp_path / "otro-disco" / "a.pdf"

    def replace_entre_discos(*_: object) -> None:
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    def copia_que_falla(*_: object) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(operaciones.os, "replace", replace_entre_discos)
    monkeypatch.setattr(operaciones.shutil, "copy2", copia_que_falla)

    with pytest.raises(FicheroError, match="No space left on device"):
        Mover(origen, destino).aplicar(papelera)

    assert origen.read_text(encoding="utf-8") == "contenido"
    assert list(destino.parent.iterdir()) == []  # ni destino ni temporales


def test_copiar_conserva_el_original_y_la_fecha(tmp_path: Path, papelera: PapeleraFalsa) -> None:
    origen = tmp_path / "a.pdf"
    origen.write_text("pdf", encoding="utf-8")
    os.utime(origen, (1_000_000_000, 1_000_000_000))
    destino = tmp_path / "copia" / "a.pdf"

    Copiar(origen, destino).aplicar(papelera)

    assert origen.exists()
    assert destino.read_text(encoding="utf-8") == "pdf"
    assert destino.stat().st_mtime == pytest.approx(1_000_000_000)


def test_enviar_a_papelera(tmp_path: Path, papelera: PapeleraFalsa) -> None:
    ruta = tmp_path / "x.tmp"
    ruta.write_text("basura", encoding="utf-8")
    EnviarAPapelera(ruta).aplicar(papelera)
    assert not ruta.exists()
    assert papelera.recibidos == ["x.tmp"]


def test_escribir_no_reemplaza_si_no_se_planifico(tmp_path: Path, papelera: PapeleraFalsa) -> None:
    ruta = tmp_path / "INDICE.md"
    ruta.write_text("mío", encoding="utf-8")
    with pytest.raises(FicheroError, match="ya existe"):
        Escribir(ruta, "nuevo").aplicar(papelera)
    assert ruta.read_text(encoding="utf-8") == "mío"


def test_crear_zip_con_nombres_relativos(tmp_path: Path, papelera: PapeleraFalsa) -> None:
    (tmp_path / "sub").mkdir()
    a, b = tmp_path / "a.pdf", tmp_path / "sub" / "b.pdf"
    a.write_text("A", encoding="utf-8")
    b.write_text("B", encoding="utf-8")
    zip_ruta = tmp_path / "Archivo" / "viejo.zip"

    CrearZip(zip_ruta, ((a, "a.pdf"), (b, "sub/b.pdf"))).aplicar(papelera)

    with zipfile.ZipFile(zip_ruta) as zf:
        assert sorted(zf.namelist()) == ["a.pdf", "sub/b.pdf"]
        assert zf.read("sub/b.pdf") == b"B"
    assert a.exists()  # comprimir no borra: eso es otra operación


def test_describir_usa_rutas_relativas(tmp_path: Path) -> None:
    operacion = Mover(tmp_path / "a.pdf", tmp_path / "Apuntes" / "a.pdf")
    assert operacion.describir(tmp_path) == ("mover", "a.pdf", "Apuntes/a.pdf")
